from __future__ import annotations

from typing import Any


class GenericOemofFactory:
    """Create oemof.solph nodes from generic component specs.

    This factory is deliberately small: it binds `applied_capacities` to
    oemof flow/storage nominal values and returns auditable node specs.
    Dispatch solving stays in a later layer.
    """

    @classmethod
    def build(cls, spec: dict[str, Any], periods: int = 24) -> dict[str, Any]:
        try:
            import pandas as pd
            import oemof.solph as solph
            from oemof.solph import Sink, Source, Transformer
            from oemof.solph.components import GenericStorage
        except Exception as exc:
            return {
                "created": False,
                "error": f"oemof unavailable: {exc}",
                "energy_system": None,
                "node_specs": [],
                "skipped_components": [],
            }

        try:
            timeindex = pd.date_range("2026-01-01", periods=periods, freq="h")
            energy_system = solph.EnergySystem(timeindex=timeindex)
            buses = {item["id"]: solph.Bus(label=item["id"]) for item in spec.get("buses", [])}
            if buses:
                energy_system.add(*buses.values())

            nodes = []
            node_specs: list[dict[str, Any]] = []
            skipped_components: list[dict[str, str]] = []
            zero_profile = [0.0] * periods

            for demand in spec.get("demand_sinks", []) or []:
                carrier = demand.get("input_carrier", "")
                if carrier not in buses:
                    skipped_components.append({"id": demand.get("id", ""), "reason": f"missing bus {carrier}"})
                    continue
                node = Sink(
                    label=demand.get("id", ""),
                    inputs={buses[carrier]: solph.Flow(fix=zero_profile, nominal_value=1)},
                )
                nodes.append(node)
                node_specs.append({
                    "id": demand.get("id", ""),
                    "component_type": "Sink",
                    "inputs": {carrier: {"nominal_value": 1}},
                    "outputs": {},
                })

            for component in spec.get("components", []) or []:
                node = _build_node(component, buses, solph, Source, Sink, Transformer, GenericStorage)
                if node["node"] is None:
                    skipped_components.append({"id": component.get("id", ""), "reason": node["reason"]})
                    continue
                nodes.append(node["node"])
                node_specs.append(node["spec"])

            if nodes:
                energy_system.add(*nodes)

            return {
                "created": True,
                "error": "",
                "energy_system": energy_system,
                "node_specs": node_specs,
                "skipped_components": skipped_components,
                "node_count": len(energy_system.nodes),
            }
        except Exception as exc:
            return {
                "created": False,
                "error": str(exc),
                "energy_system": None,
                "node_specs": [],
                "skipped_components": [],
            }


def _build_node(
    component: dict[str, Any],
    buses: dict[str, Any],
    solph: Any,
    Source: Any,
    Sink: Any,
    Transformer: Any,
    GenericStorage: Any,
) -> dict[str, Any]:
    component_id = component.get("id", "")
    component_type = component.get("component_type", "")
    inputs = [carrier for carrier in component.get("input_carriers", []) or [] if carrier in buses]
    outputs = [carrier for carrier in component.get("output_carriers", []) or [] if carrier in buses]
    primary_capacity = _capacity_by_role(component, "primary_capacity")
    energy_capacity = _capacity_by_role(component, "energy_capacity")

    if component_type == "Source" and outputs:
        output = outputs[0]
        return {
            "node": Source(label=component_id, outputs={buses[output]: solph.Flow(nominal_value=primary_capacity)}),
            "spec": _node_spec(component_id, component_type, {}, {output: primary_capacity}),
            "reason": "",
        }

    if component_type == "Sink" and inputs:
        input_carrier = inputs[0]
        return {
            "node": Sink(label=component_id, inputs={buses[input_carrier]: solph.Flow(nominal_value=primary_capacity)}),
            "spec": _node_spec(component_id, component_type, {input_carrier: primary_capacity}, {}),
            "reason": "",
        }

    if component_type == "Transformer" and inputs and outputs:
        return {
            "node": Transformer(
                label=component_id,
                inputs={buses[inputs[0]]: solph.Flow()},
                outputs={buses[carrier]: solph.Flow(nominal_value=primary_capacity) for carrier in outputs},
            ),
            "spec": _node_spec(
                component_id,
                component_type,
                {inputs[0]: None},
                {carrier: primary_capacity for carrier in outputs},
            ),
            "reason": "",
        }

    if component_type == "GenericStorage" and inputs and outputs:
        carrier = outputs[0]
        return {
            "node": GenericStorage(
                label=component_id,
                inputs={buses[carrier]: solph.Flow(nominal_value=primary_capacity)},
                outputs={buses[carrier]: solph.Flow(nominal_value=primary_capacity)},
                nominal_storage_capacity=energy_capacity,
            ),
            "spec": {
                **_node_spec(component_id, component_type, {carrier: primary_capacity}, {carrier: primary_capacity}),
                "nominal_storage_capacity": energy_capacity,
            },
            "reason": "",
        }

    return {"node": None, "spec": {}, "reason": f"unsupported or incomplete component_type {component_type}"}


def _capacity_by_role(component: dict[str, Any], role: str) -> float:
    capacities = component.get("applied_capacities", {}) or {}
    for variable in component.get("capacity_variables", []) or []:
        if variable.get("role") == role:
            return _float(capacities.get(variable.get("variable_name", "")))
    if role == "primary_capacity" and capacities:
        return _float(next(iter(capacities.values())))
    return 0.0


def _node_spec(
    component_id: str,
    component_type: str,
    inputs: dict[str, float | None],
    outputs: dict[str, float | None],
) -> dict[str, Any]:
    return {
        "id": component_id,
        "component_type": component_type,
        "inputs": {
            carrier: {"nominal_value": value}
            for carrier, value in inputs.items()
        },
        "outputs": {
            carrier: {"nominal_value": value}
            for carrier, value in outputs.items()
        },
    }


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
