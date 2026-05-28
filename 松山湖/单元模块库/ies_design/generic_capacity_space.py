from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapacityVariable:
    device_id: str
    variable_name: str
    role: str
    unit: str
    lower_bound: float
    upper_bound: float
    bound_source: str = ""

    @property
    def name(self) -> str:
        return f"{self.device_id}.{self.variable_name}"


class GenericCapacitySpace:
    """Ordered dynamic capacity variable space for generic design optimization."""

    def __init__(self, variables: list[CapacityVariable]):
        self.variables = variables

    @classmethod
    def from_model_spec(cls, spec: dict[str, Any]) -> "GenericCapacitySpace":
        variables = []
        for item in spec.get("capacity_variables", []) or []:
            upper = _to_float(item.get("upper_bound"))
            if upper <= 0:
                continue
            variables.append(CapacityVariable(
                device_id=str(item.get("device_id", "")),
                variable_name=str(item.get("variable_name", "")),
                role=str(item.get("role", "")),
                unit=str(item.get("unit", "")),
                lower_bound=0.0,
                upper_bound=upper,
                bound_source=str(item.get("bound_source", "")),
            ))
        return cls(variables)

    @classmethod
    def from_dispatch_spec(cls, spec: dict[str, Any]) -> "GenericCapacitySpace":
        variables = []
        for component in spec.get("components", []) or []:
            device_id = str(component.get("id", ""))
            capacities = component.get("applied_capacities", {}) or {}
            for item in component.get("capacity_variables", []) or []:
                name = str(item.get("variable_name", ""))
                upper = _to_float(item.get("upper_bound", capacities.get(name)))
                if upper <= 0:
                    continue
                variables.append(CapacityVariable(
                    device_id=device_id,
                    variable_name=name,
                    role=str(item.get("role", "")),
                    unit=str(item.get("unit", "")),
                    lower_bound=0.0,
                    upper_bound=upper,
                    bound_source=str(item.get("bound_source", "")),
                ))
        return cls(variables)

    @property
    def names(self) -> list[str]:
        return [variable.name for variable in self.variables]

    @property
    def lower_bounds(self) -> list[float]:
        return [variable.lower_bound for variable in self.variables]

    @property
    def upper_bounds(self) -> list[float]:
        return [variable.upper_bound for variable in self.variables]

    @property
    def defaulted_bounds(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": variable.device_id,
                "variable_name": variable.variable_name,
                "upper_bound": variable.upper_bound,
                "bound_source": variable.bound_source,
            }
            for variable in self.variables
            if variable.bound_source in {"library_default", "acceptance_default"}
        ]

    def vector_to_assignment(self, values: list[float]) -> dict[str, dict[str, float]]:
        if len(values) != len(self.variables):
            raise ValueError(f"expected {len(self.variables)} capacity values, got {len(values)}")
        assignment: dict[str, dict[str, float]] = {}
        for variable, value in zip(self.variables, values):
            assignment.setdefault(variable.device_id, {})[variable.variable_name] = float(value)
        return assignment


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
