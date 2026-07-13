"""Real-CHP E0-C diagnostics for the formal E0-B heat-demand adapter."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from tes_bess_boundary.components.chp import (
    HeatBasis,
    LowLoadFuelRule,
    yangling_chp_specs,
)
from tes_bess_boundary.heat_adapter import (
    HeatDemandAdapterSpec,
    HeatDemandInterpretation,
    HourlyWindow,
    adapt_e0b_heat_demand,
    write_adapted_heat_demand,
)
from tes_bess_boundary.model import (
    Architecture,
    E0CCase,
    E0CTimeSeries,
    ValidationObjectiveSpec,
    solve_e0c,
)
from tes_bess_boundary.solver import create_highs_solver


@dataclass(frozen=True)
class HeatBridgeWindow:
    window_id: str
    window_role: str
    window: HourlyWindow


DEFAULT_HEAT_BRIDGE_WINDOWS = (
    HeatBridgeWindow(
        window_id="negative_hour_20240527",
        window_role="negative_hour_contract",
        window=HourlyWindow(start=datetime(2024, 5, 27), hours=24),
    ),
    HeatBridgeWindow(
        window_id="zero_segment_core_20241011",
        window_role="zero_segment_contract",
        window=HourlyWindow(start=datetime(2024, 10, 11), hours=24),
    ),
)


@dataclass(frozen=True)
class HeatBridgeDiagnosticRecord:
    window_id: str
    window_role: str
    window_start: datetime
    window_end_exclusive: datetime
    interpretation: str
    source_column: str
    formula: str
    scientific_status: str
    heat_energy_mwh: float
    heat_peak_mw: float
    heat_peak_timestamp: datetime
    period_count: int
    full_source_modification_count: int
    window_modification_count: int
    architecture: str
    chp_contract: str
    heat_basis: str
    low_load_fuel_rule: str
    chp_initial_online: tuple[int, ...]
    chp_terminal_online: tuple[int, ...] | None
    pcc_export_capacity_mw: float
    wind_available_mwh: float
    pv_available_mwh: float
    coal_price_cny_per_tce: float
    curtailment_penalty_cny_per_mwh: float
    transition_proxy_mode: str
    transition_proxy_charged_cny: float
    solver_name: str
    termination: str
    mip_gap: float | None
    objective_value: float
    fuel_tce: float
    curtailment_mwh: float
    wind_curtailed_mwh: float
    pv_curtailed_mwh: float
    pcc_export_mwh: float
    max_pcc_balance_residual_mw: float
    max_heat_balance_residual_mw: float
    bess_cyclic_residual_mwh: float | None
    tes_cyclic_residual_t: float | None
    source_hourly_csv: str
    source_hourly_csv_sha256: str
    source_manifest: str
    source_manifest_sha256: str
    adapter_csv: str
    adapter_csv_sha256: str
    adapter_manifest: str
    adapter_manifest_sha256: str
    runtime_seconds: float


@dataclass(frozen=True)
class HeatBridgeDiagnosticRun:
    year: int
    records: tuple[HeatBridgeDiagnosticRecord, ...]
    adapter_output_dir: Path


@dataclass(frozen=True)
class HeatBridgeExport:
    csv_path: Path
    manifest_path: Path
    execution_metadata_path: Path
    canonical_output_sha256: dict[str, str]
    execution_metadata_sha256: str


def run_e0c_heat_bridge_diagnostics(
    hourly_csv: str | Path,
    *,
    source_manifest: str | Path,
    adapter_output_dir: str | Path,
) -> HeatBridgeDiagnosticRun:
    """Solve the six locked no-storage adapter/CHP bridge diagnostics."""

    units = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )
    adapter_directory = Path(adapter_output_dir)
    records: list[HeatBridgeDiagnosticRecord] = []
    for registered_window in DEFAULT_HEAT_BRIDGE_WINDOWS:
        for interpretation in HeatDemandInterpretation:
            adapted = adapt_e0b_heat_demand(
                hourly_csv,
                spec=HeatDemandAdapterSpec(
                    interpretation=interpretation,
                    year=registered_window.window.start.year,
                    window=registered_window.window,
                ),
                source_manifest=source_manifest,
            )
            adapter_export = write_adapted_heat_demand(
                adapted, adapter_directory
            )
            period_count = len(adapted.values_mw)
            case = E0CCase(
                architecture=Architecture.NO_STORAGE,
                timeseries=E0CTimeSeries(
                    heat_demand_mw=adapted.values_mw,
                    wind_available_mw=(0.0,) * period_count,
                    pv_available_mw=(0.0,) * period_count,
                ),
                chp_units=units,
                chp_initial_online=(0, 0),
                pcc_export_capacity_mw=700.0,
                objective=ValidationObjectiveSpec(
                    coal_price_cny_per_tce=1.0,
                    curtailment_penalty_cny_per_mwh=0.0,
                    cycle_event_cost_proxy_cny=None,
                ),
            )
            result = solve_e0c(
                case,
                solver=create_highs_solver(
                    threads=1, random_seed=0, mip_rel_gap=0.0
                ),
            )
            peak_index = max(
                range(period_count), key=lambda index: adapted.values_mw[index]
            )
            records.append(
                HeatBridgeDiagnosticRecord(
                    window_id=registered_window.window_id,
                    window_role=registered_window.window_role,
                    window_start=registered_window.window.start,
                    window_end_exclusive=(
                        registered_window.window.end_exclusive
                    ),
                    interpretation=interpretation.value,
                    source_column=adapted.source_column,
                    formula=adapted.formula,
                    scientific_status=adapted.scientific_status,
                    heat_energy_mwh=math.fsum(adapted.values_mw),
                    heat_peak_mw=adapted.values_mw[peak_index],
                    heat_peak_timestamp=adapted.timestamps[peak_index],
                    period_count=period_count,
                    full_source_modification_count=len(
                        adapted.full_source_modifications
                    ),
                    window_modification_count=len(adapted.window_modifications),
                    architecture=case.architecture.value,
                    chp_contract="yangling_2x350mw_table_vertex",
                    heat_basis=HeatBasis.USEFUL.value,
                    low_load_fuel_rule=(
                        LowLoadFuelRule.CLAMP_30_PERCENT_RATE.value
                    ),
                    chp_initial_online=case.chp_initial_online,
                    chp_terminal_online=case.chp_terminal_online,
                    pcc_export_capacity_mw=case.pcc_export_capacity_mw,
                    wind_available_mwh=0.0,
                    pv_available_mwh=0.0,
                    coal_price_cny_per_tce=(
                        case.objective.coal_price_cny_per_tce
                    ),
                    curtailment_penalty_cny_per_mwh=(
                        case.objective.curtailment_penalty_cny_per_mwh
                    ),
                    transition_proxy_mode="omitted",
                    transition_proxy_charged_cny=0.0,
                    solver_name=result.solver_name,
                    termination=result.termination,
                    mip_gap=result.mip_gap,
                    objective_value=result.objective_value,
                    fuel_tce=result.fuel_tce,
                    curtailment_mwh=result.curtailment_mwh,
                    wind_curtailed_mwh=result.wind_curtailed_mwh,
                    pv_curtailed_mwh=result.pv_curtailed_mwh,
                    pcc_export_mwh=result.pcc_export_mwh,
                    max_pcc_balance_residual_mw=(
                        result.max_pcc_balance_residual_mw
                    ),
                    max_heat_balance_residual_mw=(
                        result.max_heat_balance_residual_mw
                    ),
                    bess_cyclic_residual_mwh=(
                        result.bess_cyclic_residual_mwh
                    ),
                    tes_cyclic_residual_t=result.tes_cyclic_residual_t,
                    source_hourly_csv=adapted.source_csv_name,
                    source_hourly_csv_sha256=adapted.source_csv_sha256,
                    source_manifest=adapted.source_manifest_name or "",
                    source_manifest_sha256=(
                        adapted.source_manifest_sha256 or ""
                    ),
                    adapter_csv=adapter_export.csv_path.name,
                    adapter_csv_sha256=adapter_export.output_sha256[
                        adapter_export.csv_path.name
                    ],
                    adapter_manifest=adapter_export.manifest_path.name,
                    adapter_manifest_sha256=adapter_export.output_sha256[
                        adapter_export.manifest_path.name
                    ],
                    runtime_seconds=result.runtime_seconds,
                )
            )
    return HeatBridgeDiagnosticRun(
        year=DEFAULT_HEAT_BRIDGE_WINDOWS[0].window.start.year,
        records=tuple(records),
        adapter_output_dir=adapter_directory,
    )


def _number(value: float) -> str:
    if abs(value) < 0.5e-12:
        value = 0.0
    return f"{value:.12f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _round_json_numbers(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _round_json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_json_numbers(item) for item in value]
    return value


_CSV_FIELDS = (
    "window_id",
    "window_role",
    "window_start",
    "window_end_exclusive",
    "interpretation",
    "source_column",
    "formula",
    "scientific_status",
    "heat_energy_mwh",
    "heat_peak_mw",
    "heat_peak_timestamp",
    "period_count",
    "full_source_modification_count",
    "window_modification_count",
    "architecture",
    "chp_contract",
    "heat_basis",
    "low_load_fuel_rule",
    "chp_initial_online",
    "chp_terminal_online",
    "pcc_export_capacity_mw",
    "wind_available_mwh",
    "pv_available_mwh",
    "coal_price_cny_per_tce",
    "curtailment_penalty_cny_per_mwh",
    "transition_proxy_mode",
    "transition_proxy_charged_cny",
    "solver_name",
    "termination",
    "mip_gap",
    "objective_value",
    "fuel_tce",
    "curtailment_mwh",
    "wind_curtailed_mwh",
    "pv_curtailed_mwh",
    "pcc_export_mwh",
    "max_pcc_balance_residual_mw",
    "max_heat_balance_residual_mw",
    "bess_cyclic_residual_mwh",
    "tes_cyclic_residual_t",
    "source_hourly_csv",
    "source_hourly_csv_sha256",
    "source_manifest",
    "source_manifest_sha256",
    "adapter_csv",
    "adapter_csv_sha256",
    "adapter_manifest",
    "adapter_manifest_sha256",
)


def _adapter_reference(prefix: str, name: str) -> str:
    return name if prefix == "." else f"{prefix}/{name}"


def _record_row(
    record: HeatBridgeDiagnosticRecord, *, adapter_prefix: str
) -> dict[str, str | int]:
    numeric_fields = (
        "heat_energy_mwh",
        "heat_peak_mw",
        "pcc_export_capacity_mw",
        "wind_available_mwh",
        "pv_available_mwh",
        "coal_price_cny_per_tce",
        "curtailment_penalty_cny_per_mwh",
        "transition_proxy_charged_cny",
        "objective_value",
        "fuel_tce",
        "curtailment_mwh",
        "wind_curtailed_mwh",
        "pv_curtailed_mwh",
        "pcc_export_mwh",
        "max_pcc_balance_residual_mw",
        "max_heat_balance_residual_mw",
    )
    row: dict[str, str | int] = {
        field: getattr(record, field)
        for field in _CSV_FIELDS
        if field not in numeric_fields
        and field
        not in {
            "window_start",
            "window_end_exclusive",
            "heat_peak_timestamp",
            "chp_initial_online",
            "chp_terminal_online",
            "mip_gap",
            "bess_cyclic_residual_mwh",
            "tes_cyclic_residual_t",
        }
    }
    row.update({field: _number(getattr(record, field)) for field in numeric_fields})
    row.update(
        {
            "window_start": _timestamp(record.window_start),
            "window_end_exclusive": _timestamp(record.window_end_exclusive),
            "heat_peak_timestamp": _timestamp(record.heat_peak_timestamp),
            "chp_initial_online": ";".join(
                str(value) for value in record.chp_initial_online
            ),
            "chp_terminal_online": (
                ""
                if record.chp_terminal_online is None
                else ";".join(str(value) for value in record.chp_terminal_online)
            ),
            "mip_gap": _optional_number(record.mip_gap),
            "bess_cyclic_residual_mwh": _optional_number(
                record.bess_cyclic_residual_mwh
            ),
            "tes_cyclic_residual_t": _optional_number(
                record.tes_cyclic_residual_t
            ),
            "adapter_csv": _adapter_reference(
                adapter_prefix, record.adapter_csv
            ),
            "adapter_manifest": _adapter_reference(
                adapter_prefix, record.adapter_manifest
            ),
        }
    )
    return row


def write_e0c_heat_bridge_diagnostics(
    run: HeatBridgeDiagnosticRun, output_dir: str | Path
) -> HeatBridgeExport:
    """Write canonical bridge results and a non-canonical runtime sidecar."""

    if not isinstance(run, HeatBridgeDiagnosticRun) or not run.records:
        raise ValueError("run must contain heat-bridge diagnostic records")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"e0c_heat_bridge_diagnostics_{run.year}"
    csv_path = directory / f"{stem}.csv"
    manifest_path = directory / f"{stem}.manifest.json"
    execution_path = directory / f"{stem}.execution.json"
    try:
        adapter_prefix = Path(
            os.path.relpath(run.adapter_output_dir, directory)
        ).as_posix()
    except ValueError as error:
        raise ValueError(
            "adapter outputs and diagnostics must be on the same filesystem"
        ) from error

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in run.records:
            writer.writerow(_record_row(record, adapter_prefix=adapter_prefix))
    csv_sha256 = _sha256(csv_path)

    first = run.records[0]
    manifest = {
        "schema": "tes_bess_boundary.e0c_heat_bridge.v1",
        "scientific_scope": (
            "orthogonal_input_and_physical_bridge_diagnostic_not_e1"
        ),
        "year": run.year,
        "source": {
            "hourly_csv": first.source_hourly_csv,
            "hourly_csv_sha256": first.source_hourly_csv_sha256,
            "manifest": first.source_manifest,
            "manifest_sha256": first.source_manifest_sha256,
        },
        "case_contract": {
            "architecture": Architecture.NO_STORAGE.value,
            "chp_contract": "yangling_2x350mw_table_vertex",
            "heat_basis": HeatBasis.USEFUL.value,
            "low_load_fuel_rule": (
                LowLoadFuelRule.CLAMP_30_PERCENT_RATE.value
            ),
            "chp_initial_online": [0, 0],
            "chp_terminal_online": None,
            "pcc_export_capacity_mw": 700.0,
            "wind_available_mw": 0.0,
            "pv_available_mw": 0.0,
            "coal_price_cny_per_tce": 1.0,
            "curtailment_penalty_cny_per_mwh": 0.0,
            "transition_proxy_mode": "omitted",
            "transition_proxy_charged_cny": 0.0,
            "solver": {
                "name": "appsi_highs",
                "threads": 1,
                "random_seed": 0,
                "mip_rel_gap": 0.0,
            },
        },
        "windows": [
            {
                "window_id": registered.window_id,
                "window_role": registered.window_role,
                "start": _timestamp(registered.window.start),
                "end_exclusive": _timestamp(
                    registered.window.end_exclusive
                ),
                "hours": registered.window.hours,
            }
            for registered in DEFAULT_HEAT_BRIDGE_WINDOWS
        ],
        "adapter_outputs": [
            {
                "window_id": record.window_id,
                "interpretation": record.interpretation,
                "csv": _adapter_reference(adapter_prefix, record.adapter_csv),
                "csv_sha256": record.adapter_csv_sha256,
                "manifest": _adapter_reference(
                    adapter_prefix, record.adapter_manifest
                ),
                "manifest_sha256": record.adapter_manifest_sha256,
            }
            for record in run.records
        ],
        "output": {
            "csv": csv_path.name,
            "rows": len(run.records),
            "csv_sha256": csv_sha256,
        },
        "units": {
            "heat_power": "MWth",
            "heat_energy": "MWhth",
            "fuel": "tce",
            "electric_energy": "MWh",
        },
    }
    manifest = _round_json_numbers(manifest)
    manifest_text = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(manifest_text)
    canonical_hashes = {
        csv_path.name: csv_sha256,
        manifest_path.name: _sha256(manifest_path),
    }

    import highspy

    execution = {
        "schema": "tes_bess_boundary.e0c_heat_bridge_execution.v1",
        "canonical_output_sha256": canonical_hashes,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pyomo": version("pyomo"),
            "highspy": highspy.Highs().version(),
        },
        "solves": [
            {
                "window_id": record.window_id,
                "interpretation": record.interpretation,
                "runtime_seconds": record.runtime_seconds,
            }
            for record in run.records
        ],
    }
    execution = _round_json_numbers(execution)
    execution_text = (
        json.dumps(
            execution,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    with execution_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(execution_text)
    return HeatBridgeExport(
        csv_path=csv_path,
        manifest_path=manifest_path,
        execution_metadata_path=execution_path,
        canonical_output_sha256=canonical_hashes,
        execution_metadata_sha256=_sha256(execution_path),
    )
