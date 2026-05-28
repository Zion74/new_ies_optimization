from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from carrier_units import CarrierUnitRegistry, UnitConversionError


class GenericEnergyHubInputs:
    """Build linear Energy Hub dispatch specs from resolved generic scenarios."""

    @classmethod
    def load_monthly_profiles(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        month: int = 1,
        periods: int = 24,
    ) -> dict[str, Any]:
        registry = CarrierUnitRegistry.default()
        demands = {
            carrier: [0.0] * periods
            for carrier in resolved.get("energy_carriers", {}).get("demands", []) or []
        }
        resources = {
            carrier: [0.0] * periods
            for carrier in resolved.get("energy_carriers", {}).get("resources", []) or []
        }
        units: dict[str, str] = {}
        warnings: list[str] = []

        load_path = _resolve_data_path(resolved, project_root, "load_file")
        for row in _read_rows(load_path):
            if _int(row.get("month")) != month:
                continue
            carrier = str(row.get("demand_id") or row.get("profile_type") or "").strip()
            if carrier not in demands:
                continue
            idx = _hour_index(row.get("hour"), periods)
            if idx is None:
                continue
            unit = str(row.get("unit") or "").strip()
            try:
                demands[carrier][idx] = registry.convert_power(row.get("value"), carrier=carrier, from_unit=unit)
                units[carrier] = registry.internal_power_unit(carrier)
            except UnitConversionError as exc:
                warnings.append(str(exc))

        resource_file = (resolved.get("data", {}) or {}).get("resource_file")
        if resource_file:
            resource_path = _resolve_data_path(resolved, project_root, "resource_file")
            raw_resources = _load_resource_rows(resource_path, month, registry, warnings)
            for carrier in resources:
                values = raw_resources.get(carrier, {})
                resources[carrier] = _series_from_sparse(values, periods)
                units[carrier] = registry.internal_power_unit(carrier)
                if not values:
                    warnings.append(f"resource profile missing for {carrier}; filled with zeros")
        else:
            warnings.append("data.resource_file is missing; resource profiles filled with zeros")

        for carrier in demands:
            units.setdefault(carrier, registry.internal_power_unit(carrier))

        return {
            "demands": demands,
            "resources": resources,
            "units": units,
            "warnings": warnings,
        }

    @classmethod
    def build_dispatch_spec(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        month: int = 1,
        periods: int = 24,
        capacity_assignment: dict[str, dict[str, float]] | None = None,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        profiles = cls.load_monthly_profiles(resolved, project_root, month=month, periods=periods)
        assignment = capacity_assignment or {}
        demands = profiles["demands"]
        resources = profiles["resources"]
        buses = sorted(_required_buses(resolved, demands, resources))
        peak = {carrier: max(values or [0.0]) for carrier, values in demands.items()}
        resource_peak = {carrier: max(values or [0.0]) for carrier, values in resources.items()}

        spec: dict[str, Any] = {
            "backend": "future_generic / linear_energy_hub",
            "month": month,
            "periods": periods,
            "buses": [{"id": bus} for bus in buses],
            "demand_sinks": [
                {"id": f"{carrier}_demand", "input_carrier": carrier, "profile": values}
                for carrier, values in demands.items()
            ],
            "components": [],
            "warnings": profiles.get("warnings", []),
            "units": profiles.get("units", {}),
        }

        spec["components"].extend(_external_sources(resolved, peak))
        spec["components"].extend(_resource_sources(resources))
        for device_id, device in sorted((resolved.get("devices", {}) or {}).items()):
            if not device.get("enabled"):
                continue
            component = _device_component(
                device_id,
                device,
                assignment.get(device_id, {}),
                peak,
                resource_peak,
                resources,
                periods,
                accept_default_bounds,
            )
            if component:
                spec["components"].append(component)
        spec["components"].extend(_spill_sinks(buses, peak, resource_peak))
        return spec


def _resolve_data_path(resolved: dict[str, Any], project_root: str | Path, key: str) -> Path:
    value = (resolved.get("data", {}) or {}).get(key)
    if not value:
        raise ValueError(f"data.{key} is required")
    path = Path(value)
    if path.is_absolute():
        return path
    source_path = (resolved.get("_meta", {}) or {}).get("source_path")
    if source_path:
        candidate = Path(source_path).parent / path
        if candidate.exists():
            return candidate
    return Path(project_root) / path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_resource_rows(
    path: Path,
    month: int,
    registry: CarrierUnitRegistry,
    warnings: list[str],
) -> dict[str, dict[int, float]]:
    output: dict[str, dict[int, float]] = {}
    for row in _read_rows(path):
        if _int(row.get("month")) != month:
            continue
        carrier = str(row.get("input_id") or row.get("carrier_id") or "").strip()
        if not carrier:
            continue
        idx = _hour_index(row.get("hour"), 24)
        if idx is None:
            continue
        unit = str(row.get("unit") or "").strip()
        try:
            output.setdefault(carrier, {})[idx] = registry.convert_power(row.get("value"), carrier=carrier, from_unit=unit)
        except UnitConversionError:
            output.setdefault(carrier, {})[idx] = _float(row.get("value"))
            if row.get("value") not in (None, ""):
                warnings.append(f"resource {carrier} kept without unit conversion from {unit or '<missing>'}")
    return output


def _series_from_sparse(values: dict[int, float], periods: int) -> list[float]:
    series: list[float] = []
    last = 0.0
    for idx in range(periods):
        if idx in values:
            last = values[idx]
        series.append(last)
    return series


def _required_buses(
    resolved: dict[str, Any],
    demands: dict[str, list[float]],
    resources: dict[str, list[float]],
) -> set[str]:
    buses = set(demands)
    buses.update(["electricity", "natural_gas"])
    buses.update(resources)
    for device in (resolved.get("devices", {}) or {}).values():
        if not device.get("enabled"):
            continue
        buses.update(device.get("input_carriers", []) or [])
        buses.update(device.get("output_carriers", []) or [])
    return {bus for bus in buses if bus and bus not in {"solar_resource", "temperature"}}


def _external_sources(resolved: dict[str, Any], peak: dict[str, float]) -> list[dict[str, Any]]:
    ele_peak = sum(peak.values()) or 1.0
    gas_peak = max(ele_peak * 3, peak.get("steam", 0.0) * 3, 1.0)
    return [
        {
            "id": "grid_electricity",
            "component_type": "Source",
            "output_carriers": ["electricity"],
            "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
            "applied_capacities": {"capacity_kw": ele_peak * 2},
            "variable_costs": _price(resolved, "electricity"),
        },
        {
            "id": "natural_gas_source",
            "component_type": "Source",
            "output_carriers": ["natural_gas"],
            "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
            "applied_capacities": {"capacity_kw": gas_peak},
            "variable_costs": _price(resolved, "gas"),
        },
    ]


def _resource_sources(resources: dict[str, list[float]]) -> list[dict[str, Any]]:
    components = []
    if "waste_heat" in resources:
        components.append({
            "id": "waste_heat_resource",
            "component_type": "Source",
            "output_carriers": ["waste_heat"],
            "fixed_profile": resources["waste_heat"],
            "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
            "applied_capacities": {"capacity_kw": max(resources["waste_heat"] or [0.0])},
            "variable_costs": 0,
        })
    return components


def _device_component(
    device_id: str,
    device: dict[str, Any],
    assignment: dict[str, float],
    peak: dict[str, float],
    resource_peak: dict[str, float],
    resources: dict[str, list[float]],
    periods: int,
    accept_default_bounds: bool,
) -> dict[str, Any] | None:
    abstract_type = device.get("abstract_type", "")
    input_carriers = list(device.get("input_carriers", []) or [])
    output_carriers = list(device.get("output_carriers", []) or [])
    parameters = device.get("parameters", {}) or {}
    capacity = device.get("capacity", {}) or {}
    primary_var = capacity.get("primary_var") or "capacity_kw"
    primary = _assigned_or_default(device_id, primary_var, assignment, device, peak, resource_peak, accept_default_bounds)
    primary_source = _bound_source(primary_var, assignment, device, accept_default_bounds)

    if abstract_type == "renewable_power":
        solar = resources.get("solar_resource", [0.0] * periods)
        temperature = resources.get("temperature", [25.0] * periods)
        derating = _float(parameters.get("derating_factor", 0.9)) or 0.9
        temp_coeff = _float(parameters.get("temp_coeff", 0.0035))
        reference = _float(parameters.get("reference_temperature_c", 25))
        return {
            "id": device_id,
            "component_type": "Source",
            "output_carriers": ["electricity"],
            "fixed_profile": [
                max(0.0, primary * derating * radiation / 1000 * (1 - temp_coeff * (temp - reference)))
                for radiation, temp in zip(solar, temperature)
            ],
            "capacity_variables": [_capacity_variable(primary_var, "primary_capacity", primary, primary_source, capacity.get("default_unit", "kW"))],
            "applied_capacities": {primary_var: primary},
            "variable_costs": 0,
        }
    if abstract_type == "storage":
        energy_var = capacity.get("energy_var") or "capacity_kwh"
        energy = _assigned_or_default(device_id, energy_var, assignment, device, peak, resource_peak, accept_default_bounds)
        energy_source = _bound_source(energy_var, assignment, device, accept_default_bounds)
        carrier = output_carriers[0] if output_carriers else input_carriers[0]
        return {
            "id": device_id,
            "component_type": "GenericStorage",
            "input_carriers": [carrier],
            "output_carriers": [carrier],
            "capacity_variables": [
                _capacity_variable(primary_var, "primary_capacity", primary, primary_source, capacity.get("default_unit", "kW")),
                _capacity_variable(energy_var, "energy_capacity", energy or primary * 2, energy_source, "kWh"),
            ],
            "applied_capacities": {primary_var: primary, energy_var: energy or primary * 2},
            "charge_efficiency": _float(parameters.get("charge_efficiency", 0.9)) or 0.9,
            "discharge_efficiency": _float(parameters.get("discharge_efficiency", 0.9)) or 0.9,
            "loss_rate": _float(parameters.get("loss_rate", 0.0)),
        }
    if abstract_type in {"power_to_heat", "power_to_cooling", "heat_to_cooling", "fuel_to_steam", "fuel_to_heat"}:
        return _transformer(device_id, input_carriers, output_carriers[:1], primary_var, primary, _single_factor(device, abstract_type), primary_source, capacity.get("default_unit", "kW"))
    if abstract_type == "cogeneration":
        return _transformer(
            device_id,
            input_carriers,
            output_carriers,
            primary_var,
            primary,
            {
                "electricity": _float(parameters.get("eta_e", 0.35)) or 0.35,
                "heat": _float(parameters.get("eta_h", 0.45)) or 0.45,
            },
            primary_source,
            capacity.get("default_unit", "kW"),
        )
    if abstract_type == "recoverable_energy_to_heat":
        return _transformer(device_id, ["waste_heat"], ["steam"], primary_var, primary, 1.0, primary_source, capacity.get("default_unit", "kW"))
    return None


def _transformer(
    device_id: str,
    inputs: list[str],
    outputs: list[str],
    primary_var: str,
    primary: float,
    factor: float | dict[str, float],
    bound_source: str,
    unit: str,
) -> dict[str, Any]:
    component: dict[str, Any] = {
        "id": device_id,
        "component_type": "Transformer",
        "input_carriers": inputs,
        "output_carriers": outputs,
        "capacity_variables": [_capacity_variable(primary_var, "primary_capacity", primary, bound_source, unit)],
        "applied_capacities": {primary_var: primary},
    }
    if isinstance(factor, dict):
        component["conversion_factors"] = factor
    else:
        component["conversion_factor"] = factor
    return component


def _capacity_variable(
    variable_name: str,
    role: str,
    upper_bound: float,
    bound_source: str,
    unit: str,
) -> dict[str, Any]:
    return {
        "variable_name": variable_name,
        "role": role,
        "unit": unit,
        "upper_bound": upper_bound,
        "bound_source": bound_source,
    }


def _single_factor(device: dict[str, Any], abstract_type: str) -> float:
    parameters = device.get("parameters", {}) or {}
    if abstract_type in {"power_to_heat", "power_to_cooling", "heat_to_cooling"}:
        return _float(parameters.get("cop", 1.0)) or 1.0
    return _float(parameters.get("eta", parameters.get("efficiency", 0.9))) or 0.9


def _spill_sinks(buses: list[str], peak: dict[str, float], resource_peak: dict[str, float]) -> list[dict[str, Any]]:
    sinks = []
    for carrier in buses:
        if carrier == "natural_gas":
            continue
        capacity = max(peak.get(carrier, 0.0), resource_peak.get(carrier, 0.0), 1.0) * 10
        sinks.append({
            "id": f"{carrier}_spill",
            "component_type": "Sink",
            "input_carriers": [carrier],
            "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
            "applied_capacities": {"capacity_kw": capacity},
            "variable_costs": 0,
        })
    return sinks


def _assigned_or_default(
    device_id: str,
    variable_name: str,
    assignment: dict[str, float],
    device: dict[str, Any],
    peak: dict[str, float],
    resource_peak: dict[str, float],
    accept_default_bounds: bool,
) -> float:
    if variable_name in assignment:
        return _float(assignment[variable_name])
    for key in ["capacity_ub_kw", "power_ub_kw", "energy_capacity_ub_kwh", "capacity_ub_kwh"]:
        if device.get(key) not in (None, ""):
            return _float(device.get(key))
    if not accept_default_bounds:
        return 0.0
    if device_id == "steam_boiler":
        return peak.get("steam", 0.0)
    if device_id == "waste_heat_recovery":
        return max(resource_peak.get("waste_heat", 0.0), peak.get("steam", 0.0))
    if device_id == "pv":
        return max(peak.get("electricity", 0.0), 5000.0)
    if device_id == "chp":
        return peak.get("electricity", 0.0)
    if device_id in {"electric_chiller", "absorption_chiller", "cold_storage"}:
        return peak.get("cooling", 0.0)
    if device_id in {"electric_storage"}:
        return peak.get("electricity", 0.0)
    if device_id in {"heat_storage", "electric_heat_pump"}:
        return max(peak.get("steam", 0.0), peak.get("heat", 0.0))
    return max(peak.values() or [0.0])


def _bound_source(
    variable_name: str,
    assignment: dict[str, float],
    device: dict[str, Any],
    accept_default_bounds: bool,
) -> str:
    if variable_name in assignment:
        return "candidate"
    for key in ["capacity_ub_kw", "power_ub_kw", "energy_capacity_ub_kwh", "capacity_ub_kwh"]:
        if device.get(key) not in (None, ""):
            return "user_or_library"
    return "acceptance_default" if accept_default_bounds else "missing"


def _price(resolved: dict[str, Any], key: str) -> float:
    item = (resolved.get("prices", {}) or {}).get(key, {}) or {}
    if "value" in item:
        return _float(item.get("value"))
    values = item.get("values") or []
    if values:
        return sum(_float(value) for value in values) / len(values)
    return 0.0


def _hour_index(value: Any, periods: int) -> int | None:
    hour = _int(value)
    if hour is None:
        return None
    if 1 <= hour <= periods:
        return hour - 1
    if 0 <= hour < periods:
        return hour
    return None


def _int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
