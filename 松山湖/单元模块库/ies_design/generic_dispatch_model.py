from __future__ import annotations

from typing import Any

from generic_capacity_space import GenericCapacitySpace
from generic_model_builder import GenericModelBuilder


class GenericDispatchModel:
    """Evaluate a dynamic capacity vector against the generic model layer.

    This first implementation is intentionally build-only: it creates the
    generic model artifacts and investment-cost term, but does not solve dispatch.
    """

    def __init__(self, resolved: dict[str, Any]):
        self.resolved = resolved
        self.model_spec = GenericModelBuilder.build(resolved, build_oemof=False)
        self.capacity_space = GenericCapacitySpace.from_model_spec(self.model_spec)

    def evaluate(self, vector: list[float]) -> dict[str, Any]:
        assignment = self.capacity_space.vector_to_assignment(vector)
        return {
            "status": "build_only",
            "dispatch_solved": False,
            "capacity_assignment": assignment,
            "investment_cost": _investment_cost(self.resolved, assignment),
            "build_gaps": self.model_spec.get("build_gaps", []),
            "generic_model": {
                "scenario": self.model_spec.get("scenario", {}),
                "component_count": len(self.model_spec.get("components", [])),
                "capacity_variable_count": len(self.capacity_space.variables),
            },
        }


def _investment_cost(resolved: dict[str, Any], assignment: dict[str, dict[str, float]]) -> float:
    devices = _devices_with_top_level_carnot(resolved)
    total = 0.0
    for device_id, values in assignment.items():
        device = devices.get(device_id, {})
        economics = device.get("economics", {}) or {}
        invest_coeff = _float(economics.get("invest_coeff"))
        invest_power = _float(economics.get("invest_power_coeff"))
        invest_capacity = _float(economics.get("invest_capacity_coeff"))
        for variable_name, value in values.items():
            if variable_name.endswith("capacity_kwh") or variable_name.endswith("storage_capacity_kg"):
                total += value * (invest_capacity or invest_coeff)
            elif variable_name.endswith("power_kw"):
                total += value * (invest_power or invest_coeff)
            else:
                total += value * invest_coeff
    return total


def _devices_with_top_level_carnot(resolved: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = dict(resolved.get("devices", {}) or {})
    carnot = resolved.get("carnot_battery", {}) or {}
    if carnot.get("enabled"):
        base = dict(resolved.get("device_library", {}).get("devices", {}).get("carnot_battery", {}))
        base["economics"] = {
            **(base.get("economics", {}) or {}),
            "invest_power_coeff": carnot.get("invest_power_coeff"),
            "invest_capacity_coeff": carnot.get("invest_capacity_coeff"),
        }
        devices["carnot_battery"] = base
    return devices


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

