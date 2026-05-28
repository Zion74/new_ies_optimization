from __future__ import annotations

from copy import deepcopy
from typing import Any

from generic_capacity_space import GenericCapacitySpace
from generic_dispatch_inputs import GenericDispatchInputs
from generic_energy_hub_inputs import GenericEnergyHubInputs
from generic_model_builder import GenericModelBuilder
from generic_oemof_factory import GenericOemofFactory


class GenericDispatchModel:
    """Evaluate a dynamic capacity vector against the generic model layer.

    This first implementation is intentionally build-only: it creates the
    generic model artifacts and investment-cost term, but does not solve dispatch.
    """

    def __init__(self, resolved: dict[str, Any]):
        self.resolved = resolved
        self.model_spec = GenericModelBuilder.build(resolved, build_oemof=False)
        self.capacity_space = GenericCapacitySpace.from_model_spec(self.model_spec)

    def evaluate(
        self,
        vector: list[float],
        project_root: str | None = None,
        solve_electric_dispatch: bool = False,
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        assignment = self.capacity_space.vector_to_assignment(vector)
        applied_components = _apply_capacity_assignment(
            self.model_spec.get("components", []),
            assignment,
        )
        oemof_build = GenericOemofFactory.build(
            {**self.model_spec, "components": applied_components},
        )
        real_dispatch = _solve_real_electric_dispatch(
            self.resolved,
            project_root=project_root,
            enabled=solve_electric_dispatch,
            scope=electric_dispatch_scope,
            assignment=assignment,
            periods=dispatch_periods,
        )
        if solve_generic_dispatch:
            real_dispatch = _solve_generic_dispatch(
                self.resolved,
                project_root=project_root,
                assignment=assignment,
                periods=dispatch_periods,
                month=dispatch_month,
                accept_default_bounds=accept_default_bounds,
            )
        dispatch_solved = bool(real_dispatch.get("dispatch_solved", False))
        return {
            "status": "dispatch_solved" if dispatch_solved else "build_only",
            "dispatch_solved": dispatch_solved,
            "capacity_assignment": assignment,
            "investment_cost": _investment_cost(self.resolved, assignment),
            "build_gaps": self.model_spec.get("build_gaps", []),
            "generic_model": {
                "scenario": self.model_spec.get("scenario", {}),
                "component_count": len(self.model_spec.get("components", [])),
                "capacity_variable_count": len(self.capacity_space.variables),
                "capacity_applied": True,
                "components": applied_components,
                "oemof": _oemof_summary(oemof_build),
                "real_dispatch": real_dispatch,
            },
        }


def _apply_capacity_assignment(
    components: list[dict[str, Any]],
    assignment: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    applied = deepcopy(components)
    for component in applied:
        component_id = component.get("id", "")
        values = assignment.get(component_id, {})
        component["applied_capacities"] = {
            variable.get("variable_name", ""): values.get(variable.get("variable_name", ""), 0.0)
            for variable in component.get("capacity_variables", []) or []
        }
    return applied


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


def _oemof_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "created": result.get("created", False),
        "error": result.get("error", ""),
        "node_count": result.get("node_count", 0),
        "node_specs": result.get("node_specs", []),
        "skipped_components": result.get("skipped_components", []),
    }


def _solve_generic_dispatch(
    resolved: dict[str, Any],
    project_root: str | None,
    assignment: dict[str, dict[str, float]],
    periods: int,
    month: int,
    accept_default_bounds: bool,
) -> dict[str, Any]:
    if not project_root:
        return {"scope": "linear_energy_hub", "dispatch_solved": False, "skipped": True, "reason": "project_root is required"}
    try:
        spec = GenericEnergyHubInputs.build_dispatch_spec(
            resolved,
            project_root=project_root,
            month=month,
            periods=periods,
            capacity_assignment=assignment,
            accept_default_bounds=accept_default_bounds,
        )
        result = GenericOemofFactory.solve_dispatch(spec, periods=periods, solver_names=["glpk"])
        return {
            "scope": "linear_energy_hub",
            "dispatch_solved": result.get("dispatch_solved", False),
            "solver": result.get("solver", ""),
            "termination_condition": result.get("termination_condition", ""),
            "objective_value": result.get("objective_value"),
            "dispatch_summary": result.get("dispatch_summary", {"flow_totals": [], "storage_content": []}),
            "node_specs": result.get("node_specs", []),
            "skipped_components": result.get("skipped_components", []),
            "error": result.get("error", ""),
            "node_count": result.get("node_count", 0),
            "month": month,
        }
    except Exception as exc:
        return {
            "scope": "linear_energy_hub",
            "dispatch_solved": False,
            "solver": "",
            "termination_condition": "",
            "objective_value": None,
            "dispatch_summary": {"flow_totals": [], "storage_content": []},
            "node_specs": [],
            "skipped_components": [],
            "error": str(exc),
            "node_count": 0,
            "month": month,
        }


def _solve_real_electric_dispatch(
    resolved: dict[str, Any],
    project_root: str | None,
    enabled: bool,
    scope: str,
    assignment: dict[str, dict[str, float]],
    periods: int,
) -> dict[str, Any]:
    if not enabled:
        return {"scope": "", "dispatch_solved": False, "skipped": True, "reason": "not requested"}
    if not project_root:
        return {"scope": "grid_electric", "dispatch_solved": False, "skipped": True, "reason": "project_root is required"}
    if scope == "grid_pv_storage_cchp":
        pv_capacity = _float(assignment.get("pv", {}).get("capacity_kw"))
        storage_power = _float(assignment.get("electric_storage", {}).get("power_kw"))
        storage_capacity = _float(assignment.get("electric_storage", {}).get("capacity_kwh")) or storage_power * 2
        heat_pump_capacity = _assignment_capacity(
            assignment,
            "electric_heat_pump",
            ["heat_capacity_kw", "capacity_kw", "power_kw"],
        )
        electric_chiller_capacity = _assignment_capacity(
            assignment,
            "electric_chiller",
            ["cooling_capacity_kw", "capacity_kw", "power_kw"],
        )
        chp_capacity = _assignment_capacity(
            assignment,
            "chp",
            ["electric_capacity_kw", "capacity_kw", "power_kw"],
        )
        absorption_chiller_capacity = _assignment_capacity(
            assignment,
            "absorption_chiller",
            ["cooling_capacity_kw", "capacity_kw", "power_kw"],
        )
        spec = GenericDispatchInputs.build_grid_pv_storage_cchp_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity,
            storage_power_kw=storage_power,
            storage_capacity_kwh=storage_capacity,
            heat_pump_capacity_kw=heat_pump_capacity,
            electric_chiller_capacity_kw=electric_chiller_capacity,
            chp_capacity_kw=chp_capacity,
            absorption_chiller_capacity_kw=absorption_chiller_capacity,
        )
        dispatch_scope = "grid_pv_storage_cchp"
    elif scope == "grid_pv_storage_heat_cool":
        pv_capacity = _float(assignment.get("pv", {}).get("capacity_kw"))
        storage_power = _float(assignment.get("electric_storage", {}).get("power_kw"))
        storage_capacity = _float(assignment.get("electric_storage", {}).get("capacity_kwh")) or storage_power * 2
        heat_pump_capacity = _assignment_capacity(
            assignment,
            "electric_heat_pump",
            ["heat_capacity_kw", "capacity_kw", "power_kw"],
        )
        electric_chiller_capacity = _assignment_capacity(
            assignment,
            "electric_chiller",
            ["cooling_capacity_kw", "capacity_kw", "power_kw"],
        )
        spec = GenericDispatchInputs.build_grid_pv_storage_heat_cool_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity,
            storage_power_kw=storage_power,
            storage_capacity_kwh=storage_capacity,
            heat_pump_capacity_kw=heat_pump_capacity,
            electric_chiller_capacity_kw=electric_chiller_capacity,
        )
        dispatch_scope = "grid_pv_storage_heat_cool"
        chp_capacity = 0.0
        absorption_chiller_capacity = 0.0
    elif scope == "grid_pv_storage":
        pv_capacity = _float(assignment.get("pv", {}).get("capacity_kw"))
        storage_power = _float(assignment.get("electric_storage", {}).get("power_kw"))
        storage_capacity = _float(assignment.get("electric_storage", {}).get("capacity_kwh")) or storage_power * 2
        heat_pump_capacity = 0.0
        electric_chiller_capacity = 0.0
        chp_capacity = 0.0
        absorption_chiller_capacity = 0.0
        spec = GenericDispatchInputs.build_grid_pv_storage_electric_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity,
            storage_power_kw=storage_power,
            storage_capacity_kwh=storage_capacity,
        )
        dispatch_scope = "grid_pv_storage_electric"
    elif scope == "grid_pv":
        pv_capacity = _float(assignment.get("pv", {}).get("capacity_kw"))
        storage_power = 0.0
        storage_capacity = 0.0
        heat_pump_capacity = 0.0
        electric_chiller_capacity = 0.0
        chp_capacity = 0.0
        absorption_chiller_capacity = 0.0
        spec = GenericDispatchInputs.build_grid_pv_electric_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity,
        )
        dispatch_scope = "grid_pv_electric"
    else:
        pv_capacity = 0.0
        storage_power = 0.0
        storage_capacity = 0.0
        heat_pump_capacity = 0.0
        electric_chiller_capacity = 0.0
        chp_capacity = 0.0
        absorption_chiller_capacity = 0.0
        spec = GenericDispatchInputs.build_grid_electric_spec(
            resolved,
            project_root=project_root,
            periods=periods,
        )
        dispatch_scope = "grid_electric"
    result = GenericOemofFactory.solve_dispatch(spec, periods=periods, solver_names=["glpk"])
    return {
        "scope": dispatch_scope,
        "dispatch_solved": result.get("dispatch_solved", False),
        "solver": result.get("solver", ""),
        "termination_condition": result.get("termination_condition", ""),
        "objective_value": result.get("objective_value"),
        "pv_capacity_kw": pv_capacity,
        "storage_power_kw": storage_power,
        "storage_capacity_kwh": storage_capacity,
        "heat_pump_capacity_kw": heat_pump_capacity,
        "electric_chiller_capacity_kw": electric_chiller_capacity,
        "chp_capacity_kw": chp_capacity,
        "absorption_chiller_capacity_kw": absorption_chiller_capacity,
        "dispatch_summary": result.get("dispatch_summary", {"flow_totals": [], "storage_content": []}),
        "node_specs": result.get("node_specs", []),
        "error": result.get("error", ""),
        "node_count": result.get("node_count", 0),
    }


def _assignment_capacity(
    assignment: dict[str, dict[str, float]],
    device_id: str,
    variable_names: list[str],
) -> float:
    values = assignment.get(device_id, {}) or {}
    for name in variable_names:
        if name in values:
            return _float(values.get(name))
    return 0.0


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
