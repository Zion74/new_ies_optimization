from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class GenericDispatchInputs:
    """Build minimal dispatch specs from resolved scenario input data."""

    @classmethod
    def build_grid_electric_spec(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        periods: int = 24,
    ) -> dict[str, Any]:
        profile = _read_profile(
            Path(project_root),
            resolved,
            column_key="ele_load_kw",
            periods=periods,
        )
        price = _float(
            resolved.get("prices", {})
            .get("electricity", {})
            .get("value")
        )
        capacity = max(profile) if profile else 0.0
        return {
            "buses": [{"id": "electricity"}],
            "demand_sinks": [
                {
                    "id": "electricity_demand",
                    "input_carrier": "electricity",
                    "profile": profile,
                }
            ],
            "components": [
                {
                    "id": "grid_electricity",
                    "component_type": "Source",
                    "output_carriers": ["electricity"],
                    "capacity_variables": [
                        {"variable_name": "capacity_kw", "role": "primary_capacity"}
                    ],
                    "applied_capacities": {"capacity_kw": capacity},
                    "variable_costs": price,
                }
            ],
        }

    @classmethod
    def build_grid_pv_electric_spec(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        periods: int = 24,
        pv_capacity_kw: float = 0.0,
    ) -> dict[str, Any]:
        project_root = Path(project_root)
        load_profile = _read_profile(
            project_root,
            resolved,
            column_key="ele_load_kw",
            periods=periods,
        )
        solar_profile = _read_profile(
            project_root,
            resolved,
            column_key="solar_radiation_w_m2",
            periods=periods,
        )
        temperature_profile = _read_profile(
            project_root,
            resolved,
            column_key="temperature_c",
            periods=periods,
        )
        pv_profile = _pv_output_profile(solar_profile, temperature_profile, pv_capacity_kw)
        price = _float(
            resolved.get("prices", {})
            .get("electricity", {})
            .get("value")
        )
        return {
            "buses": [{"id": "electricity"}],
            "demand_sinks": [
                {
                    "id": "electricity_demand",
                    "input_carrier": "electricity",
                    "profile": load_profile,
                },
                {
                    "id": "electricity_spill",
                    "component_type": "Sink",
                    "input_carrier": "electricity",
                    "profile": None,
                },
            ],
            "components": [
                {
                    "id": "pv",
                    "component_type": "Source",
                    "output_carriers": ["electricity"],
                    "fixed_profile": pv_profile,
                    "capacity_variables": [
                        {"variable_name": "capacity_kw", "role": "primary_capacity"}
                    ],
                    "applied_capacities": {"capacity_kw": pv_capacity_kw},
                    "variable_costs": 0,
                },
                {
                    "id": "grid_electricity",
                    "component_type": "Source",
                    "output_carriers": ["electricity"],
                    "capacity_variables": [
                        {"variable_name": "capacity_kw", "role": "primary_capacity"}
                    ],
                    "applied_capacities": {"capacity_kw": max(load_profile) if load_profile else 0.0},
                    "variable_costs": price,
                },
            ],
        }

    @classmethod
    def build_grid_pv_storage_electric_spec(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        periods: int = 24,
        pv_capacity_kw: float = 0.0,
        storage_power_kw: float = 0.0,
        storage_capacity_kwh: float = 0.0,
    ) -> dict[str, Any]:
        spec = cls.build_grid_pv_electric_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity_kw,
        )
        # Use a variable spill sink in storage cases so PV surplus can be curtailed.
        spec["demand_sinks"] = [
            item for item in spec["demand_sinks"]
            if item.get("id") != "electricity_spill"
        ]
        spec["components"].append({
            "id": "electric_storage",
            "component_type": "GenericStorage",
            "input_carriers": ["electricity"],
            "output_carriers": ["electricity"],
            "capacity_variables": [
                {"variable_name": "power_kw", "role": "primary_capacity"},
                {"variable_name": "capacity_kwh", "role": "energy_capacity"},
            ],
            "applied_capacities": {
                "power_kw": storage_power_kw,
                "capacity_kwh": storage_capacity_kwh,
            },
            "charge_efficiency": _storage_parameter(resolved, "charge_efficiency", default=0.95),
            "discharge_efficiency": _storage_parameter(resolved, "discharge_efficiency", default=0.95),
            "loss_rate": _storage_parameter(resolved, "loss_rate", default=0.0),
        })
        spec["components"].append({
            "id": "electricity_spill",
            "component_type": "Sink",
            "input_carriers": ["electricity"],
            "capacity_variables": [
                {"variable_name": "capacity_kw", "role": "primary_capacity"}
            ],
            "applied_capacities": {"capacity_kw": _spill_capacity(spec)},
            "variable_costs": 0,
        })
        return spec

    @classmethod
    def build_grid_pv_storage_heat_cool_spec(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        periods: int = 24,
        pv_capacity_kw: float = 0.0,
        storage_power_kw: float = 0.0,
        storage_capacity_kwh: float = 0.0,
        heat_pump_capacity_kw: float = 0.0,
        electric_chiller_capacity_kw: float = 0.0,
    ) -> dict[str, Any]:
        spec = cls.build_grid_pv_storage_electric_spec(
            resolved,
            project_root=project_root,
            periods=periods,
            pv_capacity_kw=pv_capacity_kw,
            storage_power_kw=storage_power_kw,
            storage_capacity_kwh=storage_capacity_kwh,
        )
        project_root = Path(project_root)
        heat_profile = _read_profile(project_root, resolved, "heat_load_kw", periods)
        cool_profile = _read_profile(project_root, resolved, "cool_load_kw", periods)
        heat_cop = _device_parameter(resolved, "electric_heat_pump", "cop", default=4.0)
        cool_cop = _device_parameter(resolved, "electric_chiller", "cop", default=5.0)

        spec["buses"].extend([{"id": "heat"}, {"id": "cooling"}])
        spec["demand_sinks"].extend([
            {"id": "heat_demand", "input_carrier": "heat", "profile": heat_profile},
            {"id": "cooling_demand", "input_carrier": "cooling", "profile": cool_profile},
        ])
        spec["components"].extend([
            {
                "id": "electric_heat_pump",
                "component_type": "Transformer",
                "input_carriers": ["electricity"],
                "output_carriers": ["heat"],
                "capacity_variables": [
                    {"variable_name": "capacity_kw", "role": "primary_capacity"}
                ],
                "applied_capacities": {"capacity_kw": heat_pump_capacity_kw},
                "conversion_factor": heat_cop,
            },
            {
                "id": "electric_chiller",
                "component_type": "Transformer",
                "input_carriers": ["electricity"],
                "output_carriers": ["cooling"],
                "capacity_variables": [
                    {"variable_name": "capacity_kw", "role": "primary_capacity"}
                ],
                "applied_capacities": {"capacity_kw": electric_chiller_capacity_kw},
                "conversion_factor": cool_cop,
            },
        ])
        _resize_grid_for_ehc(spec, heat_profile, cool_profile, heat_cop, cool_cop)
        return spec


def _read_profile(
    project_root: Path,
    resolved: dict[str, Any],
    column_key: str,
    periods: int,
) -> list[float]:
    data = resolved.get("data", {}) or {}
    load_file = data.get("load_file")
    if not load_file:
        raise ValueError("data.load_file is required for generic dispatch input")
    path = project_root / str(load_file)
    column = (data.get("column_mapping", {}) or {}).get(column_key)
    if not column:
        raise ValueError(f"data.column_mapping.{column_key} is required")

    values: list[float] = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            raise ValueError(f"column '{column}' not found in {path}")
        for row in reader:
            values.append(_float(row.get(column)))
            if len(values) >= periods:
                break
    if len(values) < periods:
        raise ValueError(f"expected at least {periods} rows in {path}, got {len(values)}")
    return values


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pv_output_profile(
    solar_radiation_w_m2: list[float],
    temperature_c: list[float],
    capacity_kw: float,
) -> list[float]:
    return [
        max(0.0, capacity_kw * 0.9 * radiation / 1000 * (1 - 0.0035 * (temperature - 25)))
        for radiation, temperature in zip(solar_radiation_w_m2, temperature_c)
    ]


def _storage_parameter(resolved: dict[str, Any], name: str, default: float) -> float:
    return _device_parameter(resolved, "electric_storage", name, default)


def _device_parameter(resolved: dict[str, Any], device_id: str, name: str, default: float) -> float:
    device = (resolved.get("devices", {}) or {}).get(device_id, {}) or {}
    parameters = device.get("parameters", {}) or {}
    return _float(parameters.get(name, default))


def _spill_capacity(spec: dict[str, Any]) -> float:
    peak = 0.0
    for demand in spec.get("demand_sinks", []) or []:
        peak = max(peak, max(demand.get("profile", []) or [0.0]))
    for component in spec.get("components", []) or []:
        peak = max(peak, max(component.get("fixed_profile", []) or [0.0]))
    return peak


def _resize_grid_for_ehc(
    spec: dict[str, Any],
    heat_profile: list[float],
    cool_profile: list[float],
    heat_cop: float,
    cool_cop: float,
) -> None:
    electric_profile = []
    for demand in spec.get("demand_sinks", []) or []:
        if demand.get("id") == "electricity_demand":
            electric_profile = demand.get("profile", []) or []
            break
    combined_peak = 0.0
    for ele, heat, cool in zip(electric_profile, heat_profile, cool_profile):
        combined_peak = max(
            combined_peak,
            ele + heat / max(heat_cop, 1e-9) + cool / max(cool_cop, 1e-9),
        )
    for component in spec.get("components", []) or []:
        if component.get("id") == "grid_electricity":
            component.setdefault("applied_capacities", {})["capacity_kw"] = combined_peak
