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

        for instance_id, device in resolved.get("devices", {}).items():
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
        if not any(device.get(key) not in (None, "") for key in ["capacity_ub_kw", "power_ub_kw", "fixed_capacity_kw"]):
            gaps.append({"device_id": instance_id, "field": "capacity upper bound", "reason": "优化容量需要容量或功率上界"})
    capacity = device.get("capacity", {}) or {}
    if capacity.get("energy_var") and not any(device.get(key) not in (None, "") for key in ["capacity_ub_kwh", "energy_ub_kwh", "fixed_capacity_kwh"]):
        gaps.append({"device_id": instance_id, "field": f"capacity.{capacity.get('energy_var')}", "reason": "储能类设备建议提供能量容量边界"})
    return gaps


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
        variables.append({
            "device_id": instance_id,
            "variable_name": energy,
            "role": "energy_capacity",
            "unit": _energy_unit_for(unit),
            "upper_bound": device.get("capacity_ub_kwh") or device.get("energy_ub_kwh") or device.get("fixed_capacity_kwh") or "",
            "source_field": capacity.get("scenario_fields", {}).get("capacity", ""),
        })
    return variables


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
