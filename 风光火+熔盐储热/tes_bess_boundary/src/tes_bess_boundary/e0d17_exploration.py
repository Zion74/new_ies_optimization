"""Reproducible E0-D-17 Yangling exploratory break-even windows.

The run combines the formal E0-B heat series with the previously assembled
2019 PVGIS/Renewables.ninja resource shapes mapped onto the 2024 calendar.  It
is therefore an exploratory bridge, not a formal Yangling renewable-data
baseline.  TES ownership prices are intentionally absent; the output is only a
fuel-scope whole-system EAC ceiling under the primary-cost incumbent-
conditional curtailment service of each window.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from tes_bess_boundary.components.chp import LowLoadFuelRule, yangling_chp_specs
from tes_bess_boundary.components.molten_salt import (
    MoltenSaltPhysics,
    SaltInventory,
)
from tes_bess_boundary.economics import (
    AnnualEconomicsSpec,
    AnnualHorizonSpec,
    FixedCapacityNonCellCost,
    InstalledAssetQuantity,
    LifecycleAssetClass,
    LifecycleCostSpec,
    ProjectFinance,
    build_lifecycle_cost_portfolio,
)
from tes_bess_boundary.formal_tes_costs import (
    build_e0d15_tes_formal_cost_readiness,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    Architecture,
    E0CCase,
    E0CTimeSeries,
    TESFixedSpec,
    TESPortCaps,
    ValidationObjectiveSpec,
    solve_e0c,
)
from tes_bess_boundary.solver import create_highs_solver
from tes_bess_boundary.tes_break_even_adapter import (
    E0CBreakEvenAdapterSpec,
    compare_e0c_annual_break_even,
)
from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis
from tes_bess_boundary.tes_loss_auxiliary import (
    LossCompensationMode,
    TESLossAuxiliarySpec,
    TESParameterIdentity,
)
from tes_bess_boundary.tes_loss_calibration import (
    E0D9BLossLevel,
    build_e0d9b_loss_scenarios,
    calibrate_loss_for_mt,
)
from tes_bess_boundary.tes_pump_calibration import (
    E0D9B2PumpLevel,
    build_e0d9b2_pump_pressure_scenarios,
    calibrate_pump_for_mt,
    hitec_sensible_energy_mwh_per_tonne,
)
from tes_bess_boundary.tes_temperature_scenarios import (
    build_e0d8_hitec_normalized_mt_scenarios,
)


FORMAL_HEAT_SHA256 = (
    "a89d3654600eac53768529ad9ef6d304b7d756783359fc1f1db95fd2bd4c709e"
)
LEGACY_VRE_SHA256 = (
    "515892a944dacf75c4bae3f41f008b01924f30dbd9b004d132afbdb7c0e25b6f"
)
SCHEMA_ID = "tes_bess_boundary.e0d17_exploration.v1"
CANONICAL_FLOAT_DECIMALS = 6
COAL_PRICE_CNY_PER_TCE = 800.86
WIND_CAPACITY_MW = 1_050.0
PV_CAPACITY_MW = 200.0
PCC_CAPACITY_MW = 700.0
TES_THERMAL_CAPACITY_MWH = 1_200.0
TES_PORT_CAPACITY_MW = 150.0
SOLVER_THREADS = 1
SOLVER_MIP_REL_GAP = 0.0


@dataclass(frozen=True)
class E0D17WindowSpec:
    window_id: str
    start: datetime
    hours: int

    def __post_init__(self) -> None:
        if not self.window_id.strip():
            raise ValueError("window_id must be non-empty")
        if isinstance(self.hours, bool) or not isinstance(self.hours, int) or (
            self.hours <= 0
        ):
            raise ValueError("window hours must be a positive integer")


DEFAULT_WINDOWS = (
    E0D17WindowSpec(
        window_id="winter_day_20240101",
        start=datetime(2024, 1, 1),
        hours=24,
    ),
    E0D17WindowSpec(
        window_id="winter_fortnight_20240101",
        start=datetime(2024, 1, 1),
        hours=14 * 24,
    ),
)


@dataclass(frozen=True)
class E0D17InputRow:
    timestamp: datetime
    heat_demand_mw: float
    wind_cf: float
    pv_cf: float
    ambient_temperature_c: float


@dataclass(frozen=True)
class E0D17ExplorationRecord:
    window_id: str
    window_start: str
    hours: int
    annual_weight_per_hour: float
    service_id: str
    service_curtailment_ceiling_mwh: float
    renewable_available_mwh: float
    comparator_curtailment_mwh: float
    candidate_curtailment_mwh: float
    curtailment_reduction_mwh: float
    comparator_fuel_tce: float
    candidate_fuel_tce: float
    fuel_saving_tce: float
    comparator_pcc_export_mwh: float
    candidate_pcc_export_mwh: float
    pcc_export_change_mwh: float
    tes_auxiliary_mwh_e: float
    maximum_tes_ownership_eac_cny_per_year: float
    system_eac_ceiling_cny_per_kwh_th_year: float
    system_eac_ceiling_cny_per_kw_e_charge_year: float
    system_eac_ceiling_cny_per_kw_th_output_year: float
    claim_scope: str
    formal_tes_portfolio_ready: bool
    non_tes_cost_scope_complete: bool
    comparator_termination: str
    candidate_termination: str
    comparator_mip_gap: float | None
    candidate_mip_gap: float | None
    scientific_status: str


@dataclass(frozen=True)
class E0D17ExecutionRecord:
    window_id: str
    natural_baseline_runtime_seconds: float
    comparator_runtime_seconds: float
    candidate_runtime_seconds: float


@dataclass(frozen=True)
class E0D17ExplorationRun:
    records: tuple[E0D17ExplorationRecord, ...]
    execution: tuple[E0D17ExecutionRecord, ...]
    heat_path: Path
    vre_path: Path


@dataclass(frozen=True)
class E0D17ExplorationExport:
    csv_path: Path
    manifest_path: Path
    execution_path: Path
    canonical_sha256: dict[str, str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: str, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def load_e0d17_inputs(
    heat_path: str | Path,
    vre_path: str | Path,
) -> tuple[E0D17InputRow, ...]:
    """Load the two hash-locked inputs and require exact timestamp alignment."""

    heat = Path(heat_path)
    vre = Path(vre_path)
    if _sha256(heat) != FORMAL_HEAT_SHA256:
        raise ValueError("formal E0-B heat input SHA-256 mismatch")
    if _sha256(vre) != LEGACY_VRE_SHA256:
        raise ValueError("legacy mapped VRE input SHA-256 mismatch")

    with heat.open("r", encoding="utf-8-sig", newline="") as handle:
        heat_rows = list(csv.DictReader(handle))
    with vre.open("r", encoding="utf-8-sig", newline="") as handle:
        vre_rows = list(csv.DictReader(handle))
    if len(heat_rows) != 8_784 or len(vre_rows) != 8_784:
        raise ValueError("E0-D-17 inputs must each contain 8784 hourly rows")

    combined: list[E0D17InputRow] = []
    for heat_row, vre_row in zip(heat_rows, vre_rows, strict=True):
        heat_timestamp = datetime.fromisoformat(heat_row["timestamp"])
        vre_timestamp = datetime.fromisoformat(vre_row["ts"])
        if heat_timestamp != vre_timestamp:
            raise ValueError("heat and VRE timestamps are not exactly aligned")
        heat_demand = max(0.0, _finite(heat_row["heat_net_mw"], "heat_net_mw"))
        wind_cf = _finite(vre_row["wind_cf_dingbian"], "wind_cf_dingbian")
        pv_cf = _finite(vre_row["pv_cf"], "pv_cf")
        if not 0.0 <= wind_cf <= 1.0 or not 0.0 <= pv_cf <= 1.0:
            raise ValueError("renewable capacity factors must lie in [0, 1]")
        combined.append(
            E0D17InputRow(
                timestamp=heat_timestamp,
                heat_demand_mw=heat_demand,
                wind_cf=wind_cf,
                pv_cf=pv_cf,
                ambient_temperature_c=_finite(vre_row["temp"], "temp"),
            )
        )
    return tuple(combined)


def build_e0d17_tes_spec() -> TESFixedSpec:
    """Build the disclosed 150 MW / 1200 MWhth cascade TES slice."""

    mt_point = build_e0d8_hitec_normalized_mt_scenarios().point("balanced_50")
    loss_scenario = next(
        scenario
        for scenario in build_e0d9b_loss_scenarios()
        if scenario.level is E0D9BLossLevel.BASE
    )
    pump_scenario = next(
        scenario
        for scenario in build_e0d9b2_pump_pressure_scenarios()
        if scenario.level is E0D9B2PumpLevel.BASE
    )
    loss = calibrate_loss_for_mt(loss_scenario, mt_point)
    pump = calibrate_pump_for_mt(pump_scenario, mt_point)
    evidence_ids = tuple(
        dict.fromkeys(
            (*loss_scenario.evidence_source_ids, *pump_scenario.evidence_source_ids)
        )
    )
    loss_auxiliary = TESLossAuxiliarySpec(
        ht_standing_loss_fraction_per_hour=loss.raw_hourly_downgrade_fraction,
        mt_standing_loss_fraction_per_hour=loss.raw_hourly_downgrade_fraction,
        ht_loss_compensation_fraction=loss_scenario.loss_compensation_fraction,
        mt_loss_compensation_fraction=loss_scenario.loss_compensation_fraction,
        tracing_heater_efficiency=0.95,
        pump=pump.pump,
        compensation_mode=LossCompensationMode.FIXED_FRACTION,
        parameter_identity=TESParameterIdentity.AUTHOR_SENSITIVITY,
        parameter_source_id="author:e0-d-17-base-loss-pump-composite-v1",
        evidence_source_ids=evidence_ids,
        reference_ambient_temperature_c=20.0,
    )
    full_energy_per_tonne = hitec_sensible_energy_mwh_per_tonne(
        mt_point.temperature_lt_c,
        mt_point.temperature_ht_c,
    )
    salt_mass_t = TES_THERMAL_CAPACITY_MWH / full_energy_per_tonne
    average_specific_heat = full_energy_per_tonne / (
        mt_point.temperature_ht_c - mt_point.temperature_lt_c
    )
    physics = MoltenSaltPhysics(
        salt_mass_t=salt_mass_t,
        ht_tank_capacity_t=salt_mass_t,
        mt_tank_capacity_t=salt_mass_t,
        lt_tank_capacity_t=salt_mass_t,
        specific_heat_mwh_per_tonne_k=average_specific_heat,
        temperature_ht=mt_point.temperature_ht_c,
        temperature_mt=mt_point.temperature_mt_c,
        temperature_lt=mt_point.temperature_lt_c,
        electric_heater_efficiency=0.95,
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.95,
        power_block_efficiency=0.40,
        heat_exchanger_efficiency=0.95,
    )
    return TESFixedSpec(
        physics=physics,
        initial_inventory=SaltInventory(0.0, 0.0, salt_mass_t),
        port_caps=TESPortCaps(
            electric_charge_input_mw=TES_PORT_CAPACITY_MW,
            steam_to_ht_reference_input_mw=0.0,
            steam_to_mt_reference_input_mw=0.0,
            electric_output_mw=TES_PORT_CAPACITY_MW,
            heat_output_mw=TES_PORT_CAPACITY_MW,
        ),
        cyclic=True,
        loss_auxiliary=loss_auxiliary,
    )


def _window_rows(
    inputs: tuple[E0D17InputRow, ...],
    window: E0D17WindowSpec,
) -> tuple[E0D17InputRow, ...]:
    index = {row.timestamp: offset for offset, row in enumerate(inputs)}
    if window.start not in index:
        raise ValueError(f"window start is absent: {window.start.isoformat()}")
    start = index[window.start]
    rows = inputs[start : start + window.hours]
    if len(rows) != window.hours:
        raise ValueError("window extends beyond the annual input")
    return rows


def _base_case(
    rows: tuple[E0D17InputRow, ...],
    *,
    architecture: Architecture,
    service: AnnualCurtailmentServiceSpec | None,
) -> E0CCase:
    weights = (8_784.0 / len(rows),) * len(rows)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    non_cell_cost = None
    if includes_tes:
        steam_generator_id = "e0d17_unpriced_salt_to_steam_classification"
        reuse_id = "e0d17_existing_turbine_reuse_classification"
        reuse_portfolio = build_lifecycle_cost_portfolio(
            (
                LifecycleCostSpec(
                    asset_id=steam_generator_id,
                    capacity_unit="kW_th",
                    currency="CNY",
                    price_base_year=2024,
                    initial_cost_per_unit=0.0,
                    replacement_cost_per_unit=0.0,
                    fixed_om_per_unit_year=0.0,
                    service_life_years=20.0,
                    asset_class=LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
                ),
                LifecycleCostSpec(
                    asset_id=reuse_id,
                    capacity_unit="kW_e",
                    currency="CNY",
                    price_base_year=2024,
                    initial_cost_per_unit=0.0,
                    replacement_cost_per_unit=0.0,
                    fixed_om_per_unit_year=0.0,
                    service_life_years=20.0,
                    asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                ),
            ),
            ProjectFinance(project_years=20, real_discount_rate=0.08),
        )
        non_cell_cost = FixedCapacityNonCellCost(
            portfolio=reuse_portfolio,
            quantities=(
                InstalledAssetQuantity(
                    steam_generator_id,
                    TES_PORT_CAPACITY_MW * 1_000.0,
                ),
                InstalledAssetQuantity(
                    reuse_id,
                    TES_PORT_CAPACITY_MW * 1_000.0,
                ),
            ),
        )
    economics = AnnualEconomicsSpec(
        horizon=AnnualHorizonSpec(weights),
        non_cell_cost=non_cell_cost,
    )
    return E0CCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=tuple(row.heat_demand_mw for row in rows),
            wind_available_mw=tuple(
                WIND_CAPACITY_MW * row.wind_cf for row in rows
            ),
            pv_available_mw=tuple(PV_CAPACITY_MW * row.pv_cf for row in rows),
            ambient_temperature_c=tuple(
                row.ambient_temperature_c for row in rows
            ),
        ),
        chp_units=yangling_chp_specs(
            low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
        ),
        chp_initial_online=(1, 1),
        chp_terminal_online=(1, 1),
        pcc_export_capacity_mw=PCC_CAPACITY_MW,
        tes=build_e0d17_tes_spec() if includes_tes else None,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
            cycle_event_cost_proxy_cny=None,
        ),
        economics=economics,
        curtailment_service=service,
    )


def _normalization_value(comparison, basis: TESCapacityBasis) -> float:
    return comparison.break_even.normalization(
        basis
    ).system_eac_ceiling_per_unit_year


def _exploration_solver():
    return create_highs_solver(
        threads=SOLVER_THREADS,
        random_seed=0,
        mip_rel_gap=SOLVER_MIP_REL_GAP,
    )


def run_e0d17_exploration(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    windows: tuple[E0D17WindowSpec, ...] = DEFAULT_WINDOWS,
) -> E0D17ExplorationRun:
    """Run the locked 24 h and two-week penalty-free exploratory comparisons."""

    inputs = load_e0d17_inputs(heat_path, vre_path)
    records: list[E0D17ExplorationRecord] = []
    execution: list[E0D17ExecutionRecord] = []
    readiness = build_e0d15_tes_formal_cost_readiness()
    for window in windows:
        rows = _window_rows(inputs, window)
        natural_case = _base_case(
            rows,
            architecture=Architecture.NO_STORAGE,
            service=None,
        )
        natural_result = solve_e0c(
            natural_case,
            solver=_exploration_solver(),
            lexicographic_minimize_curtailment=True,
        )
        assert natural_result.annual_economics is not None
        renewable_available = (
            natural_result.annual_economics.weighted_renewable_available_mwh
        )
        service_tolerance = max(1e-6, renewable_available * 1e-10)
        service = AnnualCurtailmentServiceSpec(
            service_id=(
                "primary_incumbent_conditional_no_storage_plus_tolerance:"
                f"{window.window_id}"
            ),
            maximum_curtailment_mwh=(
                natural_result.annual_economics.weighted_curtailment_mwh
                + service_tolerance
            ),
        )
        comparator_case = replace(natural_case, curtailment_service=service)
        candidate_case = _base_case(
            rows,
            architecture=Architecture.TES,
            service=service,
        )
        comparator_result = solve_e0c(
            comparator_case,
            solver=_exploration_solver(),
            lexicographic_minimize_curtailment=True,
        )
        candidate_result = solve_e0c(
            candidate_case,
            solver=_exploration_solver(),
            lexicographic_minimize_curtailment=True,
        )
        adapter_spec = E0CBreakEvenAdapterSpec(
            scenario_id="yangling_legacy_vre_mapped_2024_e0d17",
            horizon_id=window.window_id,
            known_cost_scope_id="fuel_only_2024_cny_exploratory",
            omitted_non_tes_cost_terms=(
                "chp_variable_om",
                "carbon",
                "electricity_settlement",
                "tes_variable_om",
            ),
        )
        comparison = compare_e0c_annual_break_even(
            comparator_case,
            comparator_result,
            candidate_case,
            candidate_result,
            spec=adapter_spec,
            tes_readiness=readiness,
        )
        comparator = comparison.comparator.outcome
        candidate = comparison.candidate.outcome
        delta = comparison.break_even.physical_delta
        records.append(
            E0D17ExplorationRecord(
                window_id=window.window_id,
                window_start=window.start.isoformat(timespec="seconds"),
                hours=window.hours,
                annual_weight_per_hour=8_784.0 / window.hours,
                service_id=service.service_id,
                service_curtailment_ceiling_mwh=service.maximum_curtailment_mwh,
                renewable_available_mwh=(
                    comparator.physical.renewable_available_mwh
                ),
                comparator_curtailment_mwh=comparator.physical.curtailment_mwh,
                candidate_curtailment_mwh=candidate.physical.curtailment_mwh,
                curtailment_reduction_mwh=delta.curtailment_reduction_mwh,
                comparator_fuel_tce=comparator.physical.fuel_tce,
                candidate_fuel_tce=candidate.physical.fuel_tce,
                fuel_saving_tce=delta.fuel_saving_tce,
                comparator_pcc_export_mwh=comparator.physical.pcc_export_mwh,
                candidate_pcc_export_mwh=candidate.physical.pcc_export_mwh,
                pcc_export_change_mwh=delta.pcc_export_change_mwh,
                tes_auxiliary_mwh_e=delta.tes_auxiliary_mwh_e,
                maximum_tes_ownership_eac_cny_per_year=(
                    comparison.break_even.maximum_tes_ownership_eac_cny_per_year
                ),
                system_eac_ceiling_cny_per_kwh_th_year=_normalization_value(
                    comparison,
                    TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
                ),
                system_eac_ceiling_cny_per_kw_e_charge_year=_normalization_value(
                    comparison,
                    TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
                ),
                system_eac_ceiling_cny_per_kw_th_output_year=_normalization_value(
                    comparison,
                    TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH,
                ),
                claim_scope=comparison.break_even.claim_scope.value,
                formal_tes_portfolio_ready=(
                    comparison.break_even.formal_tes_portfolio_ready
                ),
                non_tes_cost_scope_complete=(
                    comparison.break_even.non_tes_cost_scope_complete
                ),
                comparator_termination=comparator_result.termination,
                candidate_termination=candidate_result.termination,
                comparator_mip_gap=comparator_result.mip_gap,
                candidate_mip_gap=candidate_result.mip_gap,
                scientific_status=(
                    "exploratory_only_formal_heat_plus_legacy_2019_vre_shape_"
                    "fuel_scope_cascade_electric_plus_heat_tes_not_e1"
                ),
            )
        )
        execution.append(
            E0D17ExecutionRecord(
                window_id=window.window_id,
                natural_baseline_runtime_seconds=natural_result.runtime_seconds,
                comparator_runtime_seconds=comparator_result.runtime_seconds,
                candidate_runtime_seconds=candidate_result.runtime_seconds,
            )
        )
    return E0D17ExplorationRun(
        records=tuple(records),
        execution=tuple(execution),
        heat_path=Path(heat_path),
        vre_path=Path(vre_path),
    )


def _json_ready(value: object) -> object:
    if isinstance(value, float):
        rounded = round(value, 12)
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.{CANONICAL_FLOAT_DECIMALS}f}"
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_e0d17_exploration(
    run: E0D17ExplorationRun,
    output_dir: str | Path,
) -> E0D17ExplorationExport:
    """Write canonical records/manifest and a non-canonical runtime sidecar."""

    if not isinstance(run, E0D17ExplorationRun) or not run.records:
        raise ValueError("run must contain E0-D-17 exploration records")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "e0d17_tes_break_even.csv"
    manifest_path = directory / "manifest.json"
    execution_path = directory / "execution.json"
    fields = tuple(asdict(run.records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in run.records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )
    csv_hash = _sha256(csv_path)
    manifest = _json_ready(
        {
            "schema": SCHEMA_ID,
            "scientific_scope": (
                "exploratory_break_even_not_formal_tac_not_e1"
            ),
            "inputs": {
                "formal_heat": {
                    "file": run.heat_path.name,
                    "sha256": _sha256(run.heat_path),
                    "interpretation": "net_clipped=max(heat_net_mw,0)",
                },
                "renewable_shape": {
                    "source_id": "legacy_vre_shape_2019_mapped_2024",
                    "sha256": _sha256(run.vre_path),
                    "status": "legacy_2019_resource_year_mapped_to_2024_calendar",
                },
            },
            "case": {
                "wind_capacity_mw": WIND_CAPACITY_MW,
                "pv_capacity_mw": PV_CAPACITY_MW,
                "pcc_capacity_mw": PCC_CAPACITY_MW,
                "coal_price_cny_per_tce": COAL_PRICE_CNY_PER_TCE,
                "curtailment_penalty_cny_per_mwh": 0.0,
                "tes_thermal_capacity_mwh_th": TES_THERMAL_CAPACITY_MWH,
                "tes_electric_charge_mw": TES_PORT_CAPACITY_MW,
                "tes_electric_output_mw": TES_PORT_CAPACITY_MW,
                "tes_heat_output_mw_th": TES_PORT_CAPACITY_MW,
                "tes_cost_mode": (
                    "all_tes_ownership_costs_unpriced_with_zero_price_salt_to_"
                    "steam_and_existing_turbine_reuse_classifications"
                ),
                "known_cost_scope": "fuel_only_2024_cny_exploratory",
                "omitted_non_tes_cost_terms": [
                    "chp_variable_om",
                    "carbon",
                    "electricity_settlement",
                    "tes_variable_om",
                ],
                "solver": "appsi_highs",
                "solver_threads": SOLVER_THREADS,
                "solver_random_seed": 0,
                "solver_mip_rel_gap": SOLVER_MIP_REL_GAP,
                "dispatch_tie_break": (
                    "fix_primary_cost_incumbent_integers_then_minimize_"
                    "curtailment"
                ),
            },
            "windows": [
                {
                    "window_id": record.window_id,
                    "start": record.window_start,
                    "hours": record.hours,
                    "annual_weight_per_hour": record.annual_weight_per_hour,
                    "service_id": record.service_id,
                }
                for record in run.records
            ],
            "output": {
                "csv": csv_path.name,
                "rows": len(run.records),
                "float_decimals": CANONICAL_FLOAT_DECIMALS,
                "csv_sha256": csv_hash,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    canonical_hashes = {
        csv_path.name: csv_hash,
        manifest_path.name: _sha256(manifest_path),
    }

    import highspy

    execution = _json_ready(
        {
            "schema": f"{SCHEMA_ID}.execution",
            "canonical_sha256": canonical_hashes,
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "pyomo": version("pyomo"),
                "highspy": highspy.Highs().version(),
            },
            "solves": [asdict(record) for record in run.execution],
        }
    )
    execution_path.write_text(
        json.dumps(
            execution,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    return E0D17ExplorationExport(
        csv_path=csv_path,
        manifest_path=manifest_path,
        execution_path=execution_path,
        canonical_sha256=canonical_hashes,
    )


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat", required=True)
    parser.add_argument("--vre", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--window",
        action="append",
        choices=tuple(window.window_id for window in DEFAULT_WINDOWS),
        dest="window_ids",
        help=(
            "Run only the selected window; repeat for multiple windows. "
            "Omit to run the full locked set."
        ),
    )
    args = parser.parse_args(argv)
    selected_windows = DEFAULT_WINDOWS
    if args.window_ids:
        requested = set(args.window_ids)
        selected_windows = tuple(
            window for window in DEFAULT_WINDOWS if window.window_id in requested
        )
    run = run_e0d17_exploration(
        args.heat,
        args.vre,
        windows=selected_windows,
    )
    export = write_e0d17_exploration(run, args.output)
    print(json.dumps(export.canonical_sha256, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
