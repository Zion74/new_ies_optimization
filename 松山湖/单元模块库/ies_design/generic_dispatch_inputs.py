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
