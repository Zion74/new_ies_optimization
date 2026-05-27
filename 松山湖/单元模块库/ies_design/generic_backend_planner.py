from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GenericBackendPlanner:
    """Build a lightweight component plan for future generic backends."""

    @staticmethod
    def plan(resolved: dict[str, Any]) -> dict[str, Any]:
        carriers = resolved.get("energy_carriers", {})
        carrier_dictionary = resolved.get("device_library", {}).get("carrier_dictionary", {})
        buses = set()
        for group in ("demands", "inputs", "resources"):
            buses.update(carriers.get(group, []) or [])

        mappings = resolved.get("component_mapping", {}).get("component_mappings", {})
        components: list[dict[str, Any]] = []
        missing_mappings: list[str] = []
        parameter_gaps: list[dict[str, Any]] = []
        capacity_variables: list[dict[str, Any]] = []

        for instance_id, device in _enabled_devices(resolved).items():
            if not device.get("enabled", False):
                continue

            input_carriers = list(device.get("input_carriers", []) or [])
            output_carriers = list(device.get("output_carriers", []) or [])
            buses.update(input_carriers)
            buses.update(output_carriers)

            abstract_type = device.get("abstract_type")
            mapping = mappings.get(abstract_type)
            if not mapping:
                missing_mappings.append(instance_id)

            component_parameter_gaps = _device_parameter_gaps(instance_id, device, mapping)
            parameter_gaps.extend(component_parameter_gaps)
            device_capacity_variables = _device_capacity_variables(instance_id, device)
            capacity_variables.extend(device_capacity_variables)

            components.append({
                "instance_id": instance_id,
                "library_id": device.get("library_id"),
                "name": device.get("name", instance_id),
                "abstract_type": abstract_type,
                "component_type": mapping.get("component") if mapping else None,
                "input_carriers": input_carriers,
                "output_carriers": output_carriers,
                "mapping_found": mapping is not None,
                "capacity_variables": device_capacity_variables,
                "parameter_gaps": component_parameter_gaps,
            })

        scenario = resolved.get("scenario", {})
        system = resolved.get("system", {})
        backend = resolved.get("system_template", {}).get("supported_backend", "")
        input_data_gaps = _input_data_gaps(resolved)
        current_unsolved_reasons = _unsolved_reasons(backend, missing_mappings, input_data_gaps, parameter_gaps)
        conversion_type_summary = _conversion_type_summary(components)
        return {
            "scenario": {
                "id": scenario.get("id", ""),
                "name": scenario.get("name", ""),
                "scenario_type": scenario.get("scenario_type", ""),
            },
            "system": {
                "template": system.get("template", ""),
                "backend": backend,
            },
            "backend": backend or "unknown",
            "readiness_status": "planned_not_solved",
            "message": "This plan maps the scenario to generic components; optimization solving is not implemented yet.",
            "buses": sorted(bus for bus in buses if bus),
            "carrier_units": {
                bus: {
                    "name": carrier_dictionary.get(bus, {}).get("name", bus),
                    "default_unit": carrier_dictionary.get(bus, {}).get("default_unit", ""),
                    "category": carrier_dictionary.get(bus, {}).get("category", ""),
                }
                for bus in sorted(bus for bus in buses if bus)
            },
            "components": components,
            "conversion_type_count": conversion_type_summary["type_count"],
            "conversion_type_summary": conversion_type_summary,
            "capacity_variables": capacity_variables,
            "parameter_gaps": parameter_gaps,
            "input_data_gaps": input_data_gaps,
            "unsolved_reasons": current_unsolved_reasons,
            "next_steps": _next_steps(current_unsolved_reasons, parameter_gaps, missing_mappings),
            "missing_mappings": missing_mappings,
            "runnable": False,
        }

    @classmethod
    def export(cls, resolved: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = cls.plan(resolved)

        json_path = output_dir / "generic_component_plan.json"
        md_path = output_dir / "generic_component_plan.md"
        json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_plan_markdown(plan), encoding="utf-8")
        return {"component_plan_json": json_path, "component_plan_report": md_path}


def _plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# 通用后端组件映射计划",
        "",
        f"- 场景 ID: `{plan.get('scenario', {}).get('id', '')}`",
        f"- 场景名称: {plan.get('scenario', {}).get('name', '')}",
        f"- 场景类型: `{plan.get('scenario', {}).get('scenario_type', '')}`",
        f"- 系统模板: `{plan.get('system', {}).get('template', '')}`",
        f"- 后端状态: `{plan.get('readiness_status', '')}`",
        f"- 说明: {plan.get('message', '')}",
        "",
        "## 能源母线 / 载体",
        "",
    ]
    lines.extend(f"- `{bus}`" for bus in plan.get("buses", []))
    lines.extend([
        "",
        "## 载体单位规范",
        "",
        "| 载体 | 中文名 | 默认单位 | 类型 |",
        "|---|---|---|---|",
    ])
    for carrier, meta in plan.get("carrier_units", {}).items():
        lines.append(
            f"| {carrier} | {meta.get('name', '')} | {meta.get('default_unit', '')} | {meta.get('category', '')} |"
        )
    lines.extend([
        "",
        "## 组件映射",
        "",
        "| 设备实例 | 设备名称 | 抽象类型 | 通用组件 | 输入载体 | 输出载体 | 映射状态 |",
        "|---|---|---|---|---|---|---|",
    ])
    for component in plan.get("components", []):
        lines.append(
            "| {instance} | {name} | {abstract} | {ctype} | {inputs} | {outputs} | {status} |".format(
                instance=component.get("instance_id", ""),
                name=component.get("name", ""),
                abstract=component.get("abstract_type", ""),
                ctype=component.get("component_type") or "",
                inputs=", ".join(component.get("input_carriers", []) or []),
                outputs=", ".join(component.get("output_carriers", []) or []),
                status="已映射" if component.get("mapping_found") else "缺少映射",
            )
        )
    summary = plan.get("conversion_type_summary", {}) or {}
    lines.extend([
        "",
        "## 多能转换类型统计",
        "",
        f"- 转换/模块类型数量: {summary.get('type_count', 0)}",
        f"- 启用设备数量: {summary.get('device_count', 0)}",
        "",
        "| 抽象类型 | 通用组件 | 设备数量 | 设备实例 | 输入载体 | 输出载体 |",
        "|---|---|---:|---|---|---|",
    ])
    for item in summary.get("types", []) or []:
        lines.append(
            "| {abstract} | {ctypes} | {count} | {devices} | {inputs} | {outputs} |".format(
                abstract=item.get("abstract_type", ""),
                ctypes=", ".join(item.get("component_types", []) or []),
                count=item.get("device_count", 0),
                devices=", ".join(item.get("device_ids", []) or []),
                inputs=", ".join(item.get("input_carriers", []) or []),
                outputs=", ".join(item.get("output_carriers", []) or []),
            )
        )
    missing = plan.get("missing_mappings", [])
    if missing:
        lines.extend(["", "## 缺失映射", ""])
        lines.extend(f"- `{item}`" for item in missing)
    lines.extend(["", "## 设备容量变量抽象", ""])
    if plan.get("capacity_variables"):
        lines.extend([
            "| 设备实例 | 变量名 | 角色 | 单位 | 上界 | 来源字段 |",
            "|---|---|---|---|---:|---|",
        ])
        for item in plan.get("capacity_variables", []):
            lines.append(
                "| {device} | {name} | {role} | {unit} | {upper} | {source} |".format(
                    device=item.get("device_id", ""),
                    name=item.get("variable_name", ""),
                    role=item.get("role", ""),
                    unit=item.get("unit", ""),
                    upper=item.get("upper_bound", ""),
                    source=item.get("source_field", ""),
                )
            )
    else:
        lines.append("- 无启用设备容量变量。")
    lines.extend(["", "## 输入数据缺口", ""])
    if plan.get("input_data_gaps"):
        lines.extend(f"- {gap}" for gap in plan.get("input_data_gaps", []))
    else:
        lines.append("- 未发现阻断性的输入数据缺口。")
    lines.extend(["", "## 设备参数缺口", ""])
    if plan.get("parameter_gaps"):
        for gap in plan.get("parameter_gaps", []):
            lines.append(f"- `{gap.get('device_id')}` 缺少 {gap.get('field')}：{gap.get('reason')}")
    else:
        lines.append("- 未发现明显设备参数缺口。")
    lines.extend(["", "## 当前不可求解原因", ""])
    if plan.get("unsolved_reasons"):
        lines.extend(f"- {reason}" for reason in plan.get("unsolved_reasons", []))
    else:
        lines.append("- 组件计划本身不执行求解；若需优化，应交给对应后端。")
    lines.extend(["", "## 后续补齐项", ""])
    lines.extend(f"- {item}" for item in plan.get("next_steps", []))
    return "\n".join(lines) + "\n"


def _device_parameter_gaps(instance_id: str, device: dict[str, Any], mapping: dict[str, Any] | None) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    parameters = device.get("parameters", {}) or {}
    economics = device.get("economics", {}) or {}
    mapping_params = (mapping or {}).get("parameter_mapping", {}) or {}
    for field in mapping_params:
        if parameters.get(field) in (None, ""):
            gaps.append({"device_id": instance_id, "field": f"parameters.{field}", "reason": "组件映射需要该技术参数"})
    for field, value in parameters.items():
        if value in (None, ""):
            gaps.append({"device_id": instance_id, "field": f"parameters.{field}", "reason": "设备库中该参数为空"})
    if device.get("optimize_capacity", False) and device.get("unit_group") not in {"external"}:
        if not any(economics.get(key) not in (None, "") for key in ["invest_coeff", "invest_power_coeff", "invest_capacity_coeff"]):
            gaps.append({"device_id": instance_id, "field": "economics.invest_coeff", "reason": "优化容量需要投资成本参数"})
        has_power_bound = _has_power_capacity_upper_bound(device)
        has_energy_bound = _energy_capacity_upper_bound(device) not in (None, "")
        if not has_power_bound and not has_energy_bound:
            gaps.append({"device_id": instance_id, "field": "capacity upper bound", "reason": "优化容量需要容量或功率上界"})
        elif not has_power_bound and has_energy_bound and (device.get("capacity", {}) or {}).get("primary_var"):
            gaps.append({
                "device_id": instance_id,
                "field": f"capacity.{(device.get('capacity', {}) or {}).get('primary_var')}",
                "reason": "已提供储能能量容量上界，但仍缺少功率容量上界；若只优化能量容量可忽略",
            })
    capacity = device.get("capacity", {}) or {}
    if capacity.get("energy_var") and _energy_capacity_upper_bound(device) in (None, ""):
        gaps.append({"device_id": instance_id, "field": f"capacity.{capacity.get('energy_var')}", "reason": "储能类设备建议提供能量容量边界"})
    return gaps


def _enabled_devices(resolved: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = dict(resolved.get("devices", {}) or {})
    carnot = resolved.get("carnot_battery", {}) or {}
    if carnot.get("enabled"):
        library_device = resolved.get("device_library", {}).get("devices", {}).get("carnot_battery", {})
        merged = dict(library_device)
        merged["enabled"] = True
        merged["optimize_capacity"] = True
        merged["power_ub_kw"] = carnot.get("power_ub_kw", 0)
        merged["capacity_ub_kwh"] = carnot.get("capacity_ub_kwh", 0)
        merged.setdefault("parameters", {})
        merged["parameters"]["round_trip_efficiency"] = carnot.get("round_trip_efficiency")
        merged.setdefault("economics", {})
        merged["economics"]["invest_power_coeff"] = carnot.get("invest_power_coeff")
        merged["economics"]["invest_capacity_coeff"] = carnot.get("invest_capacity_coeff")
        devices["carnot_battery"] = merged
    return devices


def _conversion_type_summary(components: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for component in components:
        abstract_type = component.get("abstract_type") or "unknown"
        group = grouped.setdefault(
            abstract_type,
            {
                "abstract_type": abstract_type,
                "component_types": set(),
                "device_ids": [],
                "device_names": [],
                "input_carriers": set(),
                "output_carriers": set(),
            },
        )
        component_type = component.get("component_type")
        if component_type:
            group["component_types"].add(component_type)
        group["device_ids"].append(component.get("instance_id", ""))
        group["device_names"].append(component.get("name", component.get("instance_id", "")))
        group["input_carriers"].update(component.get("input_carriers", []) or [])
        group["output_carriers"].update(component.get("output_carriers", []) or [])

    types = []
    for item in grouped.values():
        types.append({
            "abstract_type": item["abstract_type"],
            "component_types": sorted(item["component_types"]),
            "device_count": len([device_id for device_id in item["device_ids"] if device_id]),
            "device_ids": sorted(device_id for device_id in item["device_ids"] if device_id),
            "device_names": sorted(name for name in item["device_names"] if name),
            "input_carriers": sorted(item["input_carriers"]),
            "output_carriers": sorted(item["output_carriers"]),
        })
    types.sort(key=lambda item: item["abstract_type"])
    return {
        "type_count": len(types),
        "device_count": sum(item["device_count"] for item in types),
        "types": types,
    }


def _device_capacity_variables(instance_id: str, device: dict[str, Any]) -> list[dict[str, Any]]:
    capacity = device.get("capacity", {}) or {}
    unit = capacity.get("default_unit", "")
    variables: list[dict[str, Any]] = []
    primary = capacity.get("primary_var")
    if primary:
        variables.append({
            "device_id": instance_id,
            "variable_name": primary,
            "role": "primary_capacity",
            "unit": unit,
            "upper_bound": device.get("capacity_ub_kw") or device.get("power_ub_kw") or device.get("fixed_capacity_kw") or "",
            "source_field": capacity.get("scenario_field") or "",
        })
    energy = capacity.get("energy_var")
    if energy:
        energy_bound = _energy_capacity_upper_bound(device)
        variables.append({
            "device_id": instance_id,
            "variable_name": energy,
            "role": "energy_capacity",
            "unit": _energy_unit_for(unit),
            "upper_bound": energy_bound or "",
            "source_field": capacity.get("scenario_fields", {}).get("capacity", ""),
        })
    return variables


def _energy_capacity_upper_bound(device: dict[str, Any]) -> float | str | None:
    for key in ["capacity_ub_kwh", "energy_capacity_ub_kwh", "energy_ub_kwh", "fixed_capacity_kwh"]:
        value = device.get(key)
        if value not in (None, ""):
            return value
    capacity = device.get("capacity", {}) or {}
    duration = _as_float(capacity.get("default_energy_duration_h"))
    power_bound = _as_float(device.get("capacity_ub_kw") or device.get("power_ub_kw") or device.get("fixed_capacity_kw"))
    if duration > 0 and power_bound > 0:
        return duration * power_bound
    return None


def _has_power_capacity_upper_bound(device: dict[str, Any]) -> bool:
    return any(device.get(key) not in (None, "", 0) for key in ["capacity_ub_kw", "power_ub_kw", "fixed_capacity_kw"])


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _energy_unit_for(unit: str) -> str:
    if unit == "kW":
        return "kWh"
    if unit == "kg/h":
        return "kg"
    return unit


def _input_data_gaps(resolved: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    data = resolved.get("data", {}) or {}
    if not data.get("load_file"):
        gaps.append("data.load_file 未提供，无法读取逐时负荷或资源数据。")
    if not (data.get("typical_day_file") or resolved.get("typical_day", {}).get("file")):
        gaps.append("typical_day_file 未提供，无法进行典型日加权年化。")
    carriers = resolved.get("energy_carriers", {}) or {}
    for demand in carriers.get("demands", []) or []:
        gaps.append(f"需要确认 `{demand}` 负荷曲线的单位、时间步长和全年代表性。")
    for resource in carriers.get("resources", []) or []:
        gaps.append(f"需要确认 `{resource}` 资源/环境曲线来源与时间分辨率。")
    if (data.get("input_type") or "") in {"placeholder", "excel_template"}:
        gaps.append(f"当前 data.input_type={data.get('input_type')}，真实求解前需要替换为可计算数据文件。")
    return gaps


def _unsolved_reasons(
    backend: str,
    missing_mappings: list[str],
    input_data_gaps: list[str],
    parameter_gaps: list[dict[str, Any]],
) -> list[str]:
    reasons = []
    if backend == "future_generic":
        reasons.append("future_generic 目前只完成组件映射规划，尚未实现 Pyomo/OEMOF 求解构建器。")
    if missing_mappings:
        reasons.append(f"存在 {len(missing_mappings)} 个设备缺少通用组件映射。")
    if input_data_gaps:
        reasons.append("输入数据仍需人工确认或补齐，尤其是负荷/资源曲线和典型日。")
    if parameter_gaps:
        reasons.append("部分设备缺少效率、成本或容量边界等求解必需参数。")
    return reasons


def _next_steps(
    unsolved_reasons: list[str],
    parameter_gaps: list[dict[str, Any]],
    missing_mappings: list[str],
) -> list[str]:
    steps = ["用真实 Excel/YAML 场景替换占位数据，并重新导出组件计划。"]
    if missing_mappings:
        steps.append("为缺失映射的设备补充 component_mapping.yaml 条目。")
    if parameter_gaps:
        steps.append("补齐设备效率、投资成本、容量上界和储能能量容量等参数。")
    if unsolved_reasons:
        steps.append("实现 GenericModelBuilder，将组件计划转换为 Pyomo/OEMOF 可求解模型。")
    return steps
