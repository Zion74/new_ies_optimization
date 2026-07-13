"""E0-D-18 exact-formulation tightening and two-window TES screening.

The 24 h window remains an exact-gap regression.  The 336 h TES candidate uses
a disclosed 0.5% primary MIP-gap limit and reports a break-even interval from
the primal and dual cost bounds.  No curtailment penalty is introduced.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path

from tes_bess_boundary.components.chp import (
    CommitmentTransitionFormulation,
    FuelSegmentFormulation,
)
from tes_bess_boundary.e0d17_exploration import (
    CANONICAL_FLOAT_DECIMALS,
    COAL_PRICE_CNY_PER_TCE,
    DEFAULT_WINDOWS,
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    PCC_CAPACITY_MW,
    PV_CAPACITY_MW,
    SOLVER_THREADS,
    TES_PORT_CAPACITY_MW,
    TES_THERMAL_CAPACITY_MWH,
    WIND_CAPACITY_MW,
    E0D17WindowSpec,
    _base_case,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.formal_tes_costs import build_e0d15_tes_formal_cost_readiness
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    Architecture,
    E0CCase,
    build_e0c_model,
    solve_e0c,
)
from tes_bess_boundary.solver import create_highs_solver
from tes_bess_boundary.tes_break_even_adapter import (
    E0CBreakEvenAdapterSpec,
    compare_e0c_annual_break_even,
)


SCHEMA_ID = "tes_bess_boundary.e0d18_performance.v1"
PRIMARY_SOLVE_TIME_LIMIT_SECONDS = 900.0
EXACT_PRIMARY_MIP_GAP = 0.0
FORTNIGHT_PRIMARY_MIP_GAP = 0.005


@dataclass(frozen=True)
class E0D18Record:
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
    comparator_primary_cost_cny: float
    candidate_primary_primal_bound_cny: float
    candidate_primary_dual_bound_cny: float
    candidate_primary_mip_gap: float
    secondary_curtailment_mip_gap: float
    tes_ownership_eac_lower_bound_cny_per_year: float
    tes_ownership_eac_upper_bound_cny_per_year: float
    tes_ownership_eac_interval_width_cny_per_year: float
    eac_lower_cny_per_kwh_th_year: float
    eac_upper_cny_per_kwh_th_year: float
    eac_lower_cny_per_kw_port_year: float
    eac_upper_cny_per_kw_port_year: float
    claim_scope: str
    formal_tes_portfolio_ready: bool
    non_tes_cost_scope_complete: bool
    scientific_status: str


@dataclass(frozen=True)
class E0D18ExecutionRecord:
    window_id: str
    natural_runtime_seconds: float
    comparator_runtime_seconds: float
    candidate_runtime_seconds: float


@dataclass(frozen=True)
class E0D18Run:
    records: tuple[E0D18Record, ...]
    execution: tuple[E0D18ExecutionRecord, ...]
    heat_path: Path
    vre_path: Path
    formulation_audit: dict[str, float | int]


@dataclass(frozen=True)
class E0D18Export:
    csv_path: Path
    manifest_path: Path
    execution_path: Path
    canonical_sha256: dict[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _solver(primary_mip_gap: float) -> object:
    solver = create_highs_solver(
        threads=SOLVER_THREADS,
        random_seed=0,
        mip_rel_gap=primary_mip_gap,
    )
    solver.options["time_limit"] = PRIMARY_SOLVE_TIME_LIMIT_SECONDS
    return solver


def _tight_case(case: E0CCase) -> E0CCase:
    return replace(
        case,
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
        chp_transition_formulation=(
            CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE
        ),
    )


def _candidate_gap(window: E0D17WindowSpec) -> float:
    if window.hours == 24:
        return EXACT_PRIMARY_MIP_GAP
    if window.hours == 14 * 24:
        return FORTNIGHT_PRIMARY_MIP_GAP
    raise ValueError(f"no E0-D-18 gap policy is registered for {window.window_id}")


def _count_formulation(case: E0CCase) -> tuple[int, int, int]:
    from pyomo.environ import Constraint, Var

    model = build_e0c_model(case)
    variables = tuple(model.component_data_objects(Var, active=True))
    unfixed_binary = sum(var.is_binary() and not var.fixed for var in variables)
    fixed_binary = sum(var.is_binary() and var.fixed for var in variables)
    constraints = sum(1 for _ in model.component_data_objects(Constraint, active=True))
    return unfixed_binary, fixed_binary, constraints


def _formulation_audit(rows: tuple[object, ...]) -> dict[str, float | int]:
    service = AnnualCurtailmentServiceSpec("e0d18_formulation_audit", 1e12)
    base = _base_case(rows, architecture=Architecture.TES, service=service)
    one_hot = replace(
        base,
        chp_fuel_segment_formulation=FuelSegmentFormulation.ONE_HOT,
    )
    logarithmic = _tight_case(base)
    one_hot_binary, one_hot_fixed, one_hot_constraints = _count_formulation(one_hot)
    log_binary, log_fixed, log_constraints = _count_formulation(logarithmic)
    tes = logarithmic.tes
    assert tes is not None
    physics = tes.physics
    caps = tes.port_caps
    return {
        "legacy_unfixed_binary_count": one_hot_binary,
        "tightened_unfixed_binary_count": log_binary,
        "unfixed_binary_reduction_count": one_hot_binary - log_binary,
        "unfixed_binary_reduction_fraction": (
            (one_hot_binary - log_binary) / one_hot_binary
        ),
        "legacy_fixed_binary_count": one_hot_fixed,
        "tightened_fixed_binary_count": log_fixed,
        "legacy_constraint_count": one_hot_constraints,
        "tightened_constraint_count": log_constraints,
        "legacy_inventory_flow_big_m_tph": physics.salt_mass_t,
        "tight_ht_receiving_big_m_tph": (
            caps.electric_charge_input_mw
            * physics.electric_heater_efficiency
            / (
                physics.specific_heat_mwh_per_tonne_k
                * (physics.temperature_ht - physics.temperature_lt)
            )
        ),
        "tight_ht_sending_big_m_tph": (
            caps.electric_output_mw
            / (
                physics.power_block_efficiency
                * physics.specific_heat_mwh_per_tonne_k
                * physics.delta_ht_mt
            )
        ),
        "tight_mt_direct_charge_big_m_tph": 0.0,
        "tight_mt_heat_discharge_big_m_tph": (
            caps.heat_output_mw
            / (
                physics.heat_exchanger_efficiency
                * physics.specific_heat_mwh_per_tonne_k
                * physics.delta_mt_lt
            )
        ),
    }


def run_e0d18(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    windows: tuple[E0D17WindowSpec, ...] = DEFAULT_WINDOWS,
) -> E0D18Run:
    """Run exact 24 h and bounded-gap 336 h exploratory TES comparisons."""

    inputs = load_e0d17_inputs(heat_path, vre_path)
    records: list[E0D18Record] = []
    execution: list[E0D18ExecutionRecord] = []
    readiness = build_e0d15_tes_formal_cost_readiness()
    for window in windows:
        rows = _window_rows(inputs, window)
        natural_case = _tight_case(
            _base_case(rows, architecture=Architecture.NO_STORAGE, service=None)
        )
        natural_result = solve_e0c(
            natural_case,
            solver=_solver(EXACT_PRIMARY_MIP_GAP),
            lexicographic_minimize_curtailment=True,
        )
        natural_audit = natural_result.annual_economics
        assert natural_audit is not None
        service_tolerance = max(
            1e-6,
            natural_audit.weighted_renewable_available_mwh * 1e-10,
        )
        service = AnnualCurtailmentServiceSpec(
            service_id=f"e0d18_primary_incumbent_no_storage:{window.window_id}",
            maximum_curtailment_mwh=(
                natural_audit.weighted_curtailment_mwh + service_tolerance
            ),
        )
        comparator_case = replace(natural_case, curtailment_service=service)
        candidate_case = _tight_case(
            _base_case(rows, architecture=Architecture.TES, service=service)
        )
        comparator_result = solve_e0c(
            comparator_case,
            solver=_solver(EXACT_PRIMARY_MIP_GAP),
            lexicographic_minimize_curtailment=True,
        )
        candidate_result = solve_e0c(
            candidate_case,
            solver=_solver(_candidate_gap(window)),
            lexicographic_minimize_curtailment=True,
        )
        comparison = compare_e0c_annual_break_even(
            comparator_case,
            comparator_result,
            candidate_case,
            candidate_result,
            spec=E0CBreakEvenAdapterSpec(
                scenario_id="yangling_legacy_vre_mapped_2024_e0d18",
                horizon_id=window.window_id,
                known_cost_scope_id="fuel_only_2024_cny_exploratory",
                omitted_non_tes_cost_terms=(
                    "chp_variable_om",
                    "carbon",
                    "electricity_settlement",
                    "tes_variable_om",
                ),
            ),
            tes_readiness=readiness,
        )
        comparator = comparison.comparator.outcome
        candidate = comparison.candidate.outcome
        delta = comparison.break_even.physical_delta
        candidate_primal = candidate_result.primary_objective_upper_bound
        candidate_dual = candidate_result.primary_objective_lower_bound
        candidate_gap = candidate_result.primary_cost_mip_gap
        secondary_gap = candidate_result.secondary_curtailment_mip_gap
        if None in (candidate_primal, candidate_dual, candidate_gap, secondary_gap):
            raise RuntimeError("E0-D-18 requires complete primary and secondary bounds")
        assert candidate_primal is not None
        assert candidate_dual is not None
        assert candidate_gap is not None
        assert secondary_gap is not None
        comparator_cost = comparator.known_cost.known_total_cost_cny
        eac_lower = comparison.break_even.maximum_tes_ownership_eac_cny_per_year
        eac_upper = (
            eac_lower
            if candidate_gap <= 1e-12
            else max(eac_lower, comparator_cost - candidate_dual)
        )
        tes_operation = candidate_result.tes_operation
        if tes_operation is None:
            raise RuntimeError("TES candidate must expose annual TES operation")
        records.append(
            E0D18Record(
                window_id=window.window_id,
                window_start=window.start.isoformat(timespec="seconds"),
                hours=window.hours,
                annual_weight_per_hour=8_784.0 / window.hours,
                service_id=service.service_id,
                service_curtailment_ceiling_mwh=service.maximum_curtailment_mwh,
                renewable_available_mwh=comparator.physical.renewable_available_mwh,
                comparator_curtailment_mwh=comparator.physical.curtailment_mwh,
                candidate_curtailment_mwh=candidate.physical.curtailment_mwh,
                curtailment_reduction_mwh=delta.curtailment_reduction_mwh,
                comparator_fuel_tce=comparator.physical.fuel_tce,
                candidate_fuel_tce=candidate.physical.fuel_tce,
                fuel_saving_tce=delta.fuel_saving_tce,
                comparator_pcc_export_mwh=comparator.physical.pcc_export_mwh,
                candidate_pcc_export_mwh=candidate.physical.pcc_export_mwh,
                pcc_export_change_mwh=delta.pcc_export_change_mwh,
                tes_auxiliary_mwh_e=tes_operation.total_auxiliary_mwh_e,
                comparator_primary_cost_cny=comparator_cost,
                candidate_primary_primal_bound_cny=candidate_primal,
                candidate_primary_dual_bound_cny=candidate_dual,
                candidate_primary_mip_gap=candidate_gap,
                secondary_curtailment_mip_gap=secondary_gap,
                tes_ownership_eac_lower_bound_cny_per_year=eac_lower,
                tes_ownership_eac_upper_bound_cny_per_year=eac_upper,
                tes_ownership_eac_interval_width_cny_per_year=eac_upper - eac_lower,
                eac_lower_cny_per_kwh_th_year=(
                    eac_lower / (TES_THERMAL_CAPACITY_MWH * 1_000.0)
                ),
                eac_upper_cny_per_kwh_th_year=(
                    eac_upper / (TES_THERMAL_CAPACITY_MWH * 1_000.0)
                ),
                eac_lower_cny_per_kw_port_year=(
                    eac_lower / (TES_PORT_CAPACITY_MW * 1_000.0)
                ),
                eac_upper_cny_per_kw_port_year=(
                    eac_upper / (TES_PORT_CAPACITY_MW * 1_000.0)
                ),
                claim_scope=comparison.break_even.claim_scope.value,
                formal_tes_portfolio_ready=(
                    comparison.break_even.formal_tes_portfolio_ready
                ),
                non_tes_cost_scope_complete=(
                    comparison.break_even.non_tes_cost_scope_complete
                ),
                scientific_status=(
                    "exact_24h_formulation_regression"
                    if window.hours == 24 and candidate_gap <= 1e-12
                    else "bounded_gap_336h_exploratory_interval_not_formal_tac"
                ),
            )
        )
        execution.append(
            E0D18ExecutionRecord(
                window_id=window.window_id,
                natural_runtime_seconds=natural_result.runtime_seconds,
                comparator_runtime_seconds=comparator_result.runtime_seconds,
                candidate_runtime_seconds=candidate_result.runtime_seconds,
            )
        )
    longest_rows = _window_rows(inputs, max(windows, key=lambda item: item.hours))
    return E0D18Run(
        records=tuple(records),
        execution=tuple(execution),
        heat_path=Path(heat_path),
        vre_path=Path(vre_path),
        formulation_audit=_formulation_audit(longest_rows),
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


def write_e0d18(run: E0D18Run, output_dir: str | Path) -> E0D18Export:
    """Write canonical interval results and a non-canonical runtime sidecar."""

    if not isinstance(run, E0D18Run) or not run.records:
        raise ValueError("run must contain E0-D-18 records")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "e0d18_tes_break_even_interval.csv"
    manifest_path = directory / "manifest.json"
    execution_path = directory / "execution.json"
    field_names = tuple(asdict(run.records[0]))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names, lineterminator="\n")
        writer.writeheader()
        for record in run.records:
            writer.writerow(
                {key: _csv_value(value) for key, value in asdict(record).items()}
            )
    csv_hash = _sha256(csv_path)
    source_dir = Path(__file__).resolve().parent
    source_names = (
        "e0d18_performance.py",
        "model.py",
        "tes_break_even_adapter.py",
        "components/chp.py",
        "components/molten_salt.py",
    )
    manifest = _json_ready(
        {
            "schema": SCHEMA_ID,
            "scientific_scope": "exploratory_interval_not_formal_tac_not_e1",
            "inputs": {
                "formal_heat": {
                    "file": run.heat_path.name,
                    "sha256": _sha256(run.heat_path),
                    "locked_sha256": FORMAL_HEAT_SHA256,
                },
                "renewable_shape": {
                    "file": run.vre_path.name,
                    "sha256": _sha256(run.vre_path),
                    "locked_sha256": LEGACY_VRE_SHA256,
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
                "tes_port_capacity_mw": TES_PORT_CAPACITY_MW,
                "known_cost_scope": "fuel_only_2024_cny_exploratory",
                "omitted_non_tes_cost_terms": [
                    "chp_variable_om",
                    "carbon",
                    "electricity_settlement",
                    "tes_variable_om",
                ],
            },
            "solver_contract": {
                "solver": "appsi_highs",
                "threads": SOLVER_THREADS,
                "random_seed": 0,
                "time_limit_seconds_per_solve": PRIMARY_SOLVE_TIME_LIMIT_SECONDS,
                "comparator_primary_mip_gap": EXACT_PRIMARY_MIP_GAP,
                "candidate_primary_mip_gap_by_hours": {
                    "24": EXACT_PRIMARY_MIP_GAP,
                    "336": FORTNIGHT_PRIMARY_MIP_GAP,
                },
                "secondary_tie_break": (
                    "fix_primary_incumbent_integers_then_minimize_curtailment"
                ),
                "interval_definition": (
                    "lower=comparator_exact_cost-candidate_primal_bound;"
                    "upper=comparator_exact_cost-candidate_dual_bound"
                ),
            },
            "formulation_audit": run.formulation_audit,
            "sources": {
                name: _sha256(source_dir / name) for name in source_names
            },
            "windows": [
                {
                    "window_id": record.window_id,
                    "start": record.window_start,
                    "hours": record.hours,
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
    return E0D18Export(
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
        help="repeat to select windows; omission runs both",
    )
    args = parser.parse_args(argv)
    selected = (
        DEFAULT_WINDOWS
        if not args.window
        else tuple(
            window for window in DEFAULT_WINDOWS if window.window_id in args.window
        )
    )
    export = write_e0d18(
        run_e0d18(args.heat, args.vre, windows=selected),
        args.output,
    )
    print(json.dumps(export.canonical_sha256, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
