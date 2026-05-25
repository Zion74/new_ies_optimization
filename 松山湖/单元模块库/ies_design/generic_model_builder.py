from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from generic_backend_planner import GenericBackendPlanner


class GenericModelBuilder:
    """Build an auditable generic model layer from a resolved scenario."""

    @classmethod
    def build(cls, resolved: dict[str, Any], build_oemof: bool = True) -> dict[str, Any]:
        plan = GenericBackendPlanner.plan(resolved)
        spec = {
            "scenario": plan["scenario"],
            "system": plan["system"],
            "backend": plan["backend"],
            "solve_status": "not_solved",
            "buses": [{"id": bus, **plan.get("carrier_units", {}).get(bus, {})} for bus in plan["buses"]],
            "demand_sinks": _demand_sink_specs(resolved),
            "components": _component_specs(plan),
            "capacity_variables": plan.get("capacity_variables", []),
            "build_gaps": _build_gaps(plan),
            "next_step": "connect capacity_variables to a dynamic outer optimizer, then solve dispatch for each candidate capacity set",
        }

        oemof_status = _try_build_oemof(spec) if build_oemof else {"attempted": False, "created": False, "error": ""}
        spec["oemof"] = oemof_status
        return spec

    @classmethod
    def export(cls, resolved: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        spec = cls.build(resolved)

        components_path = output_dir / "generic_model_components.json"
        gaps_path = output_dir / "generic_model_build_gaps.csv"
        report_path = output_dir / "generic_model_build_report.md"
        components_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_gaps(gaps_path, spec.get("build_gaps", []))
        report_path.write_text(_build_report(spec), encoding="utf-8")
        return {
            "generic_model_components": components_path,
            "generic_model_build_gaps": gaps_path,
            "generic_model_build_report": report_path,
        }


def _demand_sink_specs(resolved: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{carrier}_demand",
            "component_type": "Sink",
            "input_carrier": carrier,
            "profile_ref": f"{carrier}_load",
        }
        for carrier in resolved.get("energy_carriers", {}).get("demands", []) or []
    ]


def _component_specs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    specs = []
    for item in plan.get("components", []):
        specs.append({
            "id": item.get("instance_id", ""),
            "name": item.get("name", ""),
            "abstract_type": item.get("abstract_type", ""),
            "component_type": _normalize_component_type(item.get("component_type")),
            "input_carriers": item.get("input_carriers", []) or [],
            "output_carriers": item.get("output_carriers", []) or [],
            "capacity_variables": item.get("capacity_variables", []) or [],
            "mapping_found": item.get("mapping_found", False),
        })
    return specs


def _normalize_component_type(component_type: str | None) -> str:
    if not component_type:
        return "MissingMapping"
    if component_type in {"Source_plus_Transformer", "GenericStorage_plus_Transformer"}:
        return "Composite"
    return component_type


def _build_gaps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in plan.get("missing_mappings", []):
        gaps.append({"category": "mapping", "target": item, "message": "missing component mapping"})
    for item in plan.get("input_data_gaps", []):
        gaps.append({"category": "input_data", "target": "scenario", "message": item})
    for item in plan.get("parameter_gaps", []):
        gaps.append({
            "category": "parameter",
            "target": item.get("device_id", ""),
            "message": f"{item.get('field', '')}: {item.get('reason', '')}",
        })
    return gaps


def _try_build_oemof(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        import pandas as pd
        import oemof.solph as solph
        from oemof.solph import Sink, Source, Transformer
        from oemof.solph.components import GenericStorage
    except Exception as exc:
        return {"attempted": True, "created": False, "error": f"oemof unavailable: {exc}"}

    try:
        timeindex = pd.date_range("2026-01-01", periods=24, freq="h")
        energy_system = solph.EnergySystem(timeindex=timeindex)
        buses = {item["id"]: solph.Bus(label=item["id"]) for item in spec["buses"]}
        energy_system.add(*buses.values())

        nodes = []
        zero_profile = [0.0] * len(timeindex)
        for sink in spec.get("demand_sinks", []):
            carrier = sink["input_carrier"]
            if carrier in buses:
                nodes.append(Sink(label=sink["id"], inputs={buses[carrier]: solph.Flow(fix=zero_profile, nominal_value=1)}))

        for component in spec.get("components", []):
            ctype = component.get("component_type")
            inputs = [carrier for carrier in component.get("input_carriers", []) if carrier in buses]
            outputs = [carrier for carrier in component.get("output_carriers", []) if carrier in buses]
            label = component.get("id", "")
            if ctype == "Source" and outputs:
                nodes.append(Source(label=label, outputs={buses[outputs[0]]: solph.Flow(nominal_value=1)}))
            elif ctype == "Sink" and inputs:
                nodes.append(Sink(label=label, inputs={buses[inputs[0]]: solph.Flow(nominal_value=1)}))
            elif ctype == "Transformer" and inputs and outputs:
                nodes.append(Transformer(
                    label=label,
                    inputs={buses[inputs[0]]: solph.Flow()},
                    outputs={buses[out]: solph.Flow(nominal_value=1) for out in outputs},
                ))
            elif ctype == "GenericStorage" and inputs and outputs:
                carrier = outputs[0]
                nodes.append(GenericStorage(
                    label=label,
                    inputs={buses[carrier]: solph.Flow(nominal_value=1)},
                    outputs={buses[carrier]: solph.Flow(nominal_value=1)},
                    nominal_storage_capacity=1,
                ))
        if nodes:
            energy_system.add(*nodes)
        return {"attempted": True, "created": True, "error": "", "node_count": len(energy_system.nodes)}
    except Exception as exc:
        return {"attempted": True, "created": False, "error": str(exc)}


def _write_gaps(path: Path, gaps: list[dict[str, Any]]) -> None:
    columns = ["category", "target", "message"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for gap in gaps:
            writer.writerow({column: gap.get(column, "") for column in columns})


def _build_report(spec: dict[str, Any]) -> str:
    lines = [
        "# GenericModelBuilder 构建报告",
        "",
        f"- 场景 ID: `{spec.get('scenario', {}).get('id', '')}`",
        f"- 系统模板: `{spec.get('system', {}).get('template', '')}`",
        f"- 后端: `{spec.get('backend', '')}`",
        f"- 求解状态: `{spec.get('solve_status', '')}`",
        f"- OEMOF 构建: {'成功' if spec.get('oemof', {}).get('created') else '未成功/未启用'}",
        f"- OEMOF 节点数: {spec.get('oemof', {}).get('node_count', '')}",
        "",
        "## 动态容量变量",
        "",
        "| 设备 | 变量 | 角色 | 单位 | 上界 |",
        "|---|---|---|---|---:|",
    ]
    for item in spec.get("capacity_variables", []):
        lines.append(f"| {item.get('device_id', '')} | {item.get('variable_name', '')} | {item.get('role', '')} | {item.get('unit', '')} | {item.get('upper_bound', '')} |")
    lines.extend(["", "## 构建缺口", ""])
    gaps = spec.get("build_gaps", [])
    if gaps:
        lines.extend(f"- [{gap.get('category')}] {gap.get('target')}: {gap.get('message')}" for gap in gaps)
    else:
        lines.append("- 暂未发现阻断组件构建的缺口。")
    lines.extend(["", "## 后续接入双层优化", "", f"- {spec.get('next_step', '')}"])
    return "\n".join(lines) + "\n"

