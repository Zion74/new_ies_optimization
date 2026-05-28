from __future__ import annotations

from pathlib import Path
from typing import Any

from generic_capacity_space import GenericCapacitySpace
from generic_dispatch_model import GenericDispatchModel
from generic_energy_hub_inputs import GenericEnergyHubInputs


class GenericSystem:
    """Stable consumer-facing API for generic system dispatch evaluation."""

    def __init__(self, resolved: dict[str, Any], project_root: str | Path | None = None):
        self.resolved = resolved
        self.project_root = Path(project_root) if project_root is not None else None
        self.dispatch_model = GenericDispatchModel(resolved)
        self.model_spec = self.dispatch_model.model_spec

    @classmethod
    def from_resolved(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path | None = None,
    ) -> "GenericSystem":
        return cls(resolved, project_root=project_root)

    def capacity_space(
        self,
        month: int = 1,
        periods: int = 24,
        accept_default_bounds: bool = False,
    ) -> GenericCapacitySpace:
        if accept_default_bounds and self.project_root is not None:
            dispatch_spec = GenericEnergyHubInputs.build_dispatch_spec(
                self.resolved,
                project_root=self.project_root,
                month=month,
                periods=periods,
                capacity_assignment={},
                accept_default_bounds=True,
            )
            return GenericCapacitySpace.from_dispatch_spec(dispatch_spec)
        return self.dispatch_model.capacity_space

    def default_capacity_assignment(
        self,
        level: float = 1.0,
        month: int = 1,
        periods: int = 24,
        accept_default_bounds: bool = False,
    ) -> dict[str, float]:
        if level < 0 or level > 1:
            raise ValueError("level must be between 0 and 1")
        space = self.capacity_space(
            month=month,
            periods=periods,
            accept_default_bounds=accept_default_bounds,
        )
        return {
            variable.name: variable.lower_bound + (variable.upper_bound - variable.lower_bound) * level
            for variable in space.variables
        }

    def solve_dispatch(
        self,
        capacities: dict[str, Any],
        month: int = 1,
        periods: int = 24,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        space = self.capacity_space(
            month=month,
            periods=periods,
            accept_default_bounds=accept_default_bounds,
        )
        assignment = self._normalize_capacities(capacities, space)
        vector = [
            assignment.get(variable.device_id, {}).get(variable.variable_name, 0.0)
            for variable in space.variables
        ]
        evaluation = self.dispatch_model.evaluate(
            vector,
            project_root=str(self.project_root) if self.project_root else None,
            solve_generic_dispatch=True,
            dispatch_periods=periods,
            dispatch_month=month,
            accept_default_bounds=accept_default_bounds,
            capacity_space=space,
        )
        dispatch = evaluation.get("generic_model", {}).get("real_dispatch", {}) or {}
        dispatch_summary = dispatch.get("dispatch_summary", {"flow_totals": [], "storage_content": []})
        return {
            "dispatch_solved": dispatch.get("dispatch_solved", False),
            "solver": dispatch.get("solver", ""),
            "termination_condition": dispatch.get("termination_condition", ""),
            "objective_value": dispatch.get("objective_value"),
            "dispatch_summary": dispatch_summary,
            "energy_flow_summary": dispatch_summary.get("flow_totals", []),
            "capacity_assignment": evaluation.get("capacity_assignment", {}),
            "build_gaps": evaluation.get("build_gaps", []),
            "error": dispatch.get("error", ""),
            "generic_model": evaluation.get("generic_model", {}),
        }

    def _normalize_capacities(
        self,
        capacities: dict[str, Any],
        space: GenericCapacitySpace,
    ) -> dict[str, dict[str, float]]:
        allowed = set(space.names)
        assignment: dict[str, dict[str, float]] = {}
        unknown: list[str] = []
        for key, value in capacities.items():
            if isinstance(value, dict):
                for parameter, nested_value in value.items():
                    full_name = f"{key}.{parameter}"
                    if full_name not in allowed:
                        unknown.append(full_name)
                        continue
                    assignment.setdefault(str(key), {})[str(parameter)] = float(nested_value)
            else:
                if key not in allowed:
                    unknown.append(str(key))
                    continue
                device_id, parameter = str(key).split(".", 1)
                assignment.setdefault(device_id, {})[parameter] = float(value)
        if unknown:
            accepted = ", ".join(sorted(allowed)[:12])
            raise ValueError(f"unknown capacity variable(s): {', '.join(unknown)}; accepted examples: {accepted}")
        return assignment
