from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GenericBackendPlanner:
    """Build a lightweight component plan for future generic backends."""

    @staticmethod
    def plan(resolved: dict[str, Any]) -> dict[str, Any]:
        carriers = resolved.get("energy_carriers", {})
        buses = set()
        for group in ("demands", "inputs", "resources"):
            buses.update(carriers.get(group, []) or [])

        mappings = resolved.get("component_mapping", {}).get("component_mappings", {})
        components: list[dict[str, Any]] = []
        missing_mappings: list[str] = []

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

            components.append({
                "instance_id": instance_id,
                "library_id": device.get("library_id"),
                "name": device.get("name", instance_id),
                "abstract_type": abstract_type,
                "component_type": mapping.get("component") if mapping else None,
                "input_carriers": input_carriers,
                "output_carriers": output_carriers,
                "mapping_found": mapping is not None,
            })

        scenario = resolved.get("scenario", {})
        system = resolved.get("system", {})
        return {
            "scenario": {
                "id": scenario.get("id", ""),
                "name": scenario.get("name", ""),
                "scenario_type": scenario.get("scenario_type", ""),
            },
            "system": {
                "template": system.get("template", ""),
                "backend": resolved.get("system_template", {}).get("supported_backend", ""),
            },
            "backend": "future_generic",
            "readiness_status": "planned_not_solved",
            "message": "This plan maps the scenario to generic components; optimization solving is not implemented yet.",
            "buses": sorted(bus for bus in buses if bus),
            "components": components,
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
    return "\n".join(lines) + "\n"
