"""E0-D-19 same-PCC-service diagnostic before monetary settlement closure.

The E0-D-18 fuel-only screen allowed architectures to deliver different annual
electricity at the PCC.  This module first derives the no-storage annual PCC
delivery and then fixes that same service for the no-storage comparator and TES
candidate.  A constant flat export price therefore cancels exactly.  The
result remains exploratory because CHP VOM, ETS-compliance accounting, TES VOM,
and time-varying electricity settlement are not yet closed.
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
from importlib.metadata import version
from pathlib import Path

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
from tes_bess_boundary.e0d18_performance import (
    EXACT_PRIMARY_MIP_GAP,
    FORTNIGHT_PRIMARY_MIP_GAP,
    PRIMARY_SOLVE_TIME_LIMIT_SECONDS,
    _candidate_gap,
    _solver,
    _tight_case,
)
from tes_bess_boundary.formal_tes_costs import build_e0d15_tes_formal_cost_readiness
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    E0CCase,
    E0CResult,
    solve_e0c,
)
from tes_bess_boundary.tes_break_even_adapter import (
    E0CBreakEvenAdapterSpec,
    compare_e0c_annual_break_even,
)


SCHEMA_ID = "tes_bess_boundary.e0d19_same_pcc_service.v2"
_SERVICE_ABS_TOL_MWH = 1e-5


@dataclass(frozen=True)
class E0D19Record:
    window_id: str
    window_start: str
    hours: int
    annual_weight_per_hour: float
    curtailment_service_id: str
    service_curtailment_ceiling_mwh: float
    pcc_export_service_id: str
    pcc_export_target_mwh: float
    comparator_pcc_export_mwh: float
    candidate_pcc_export_mwh: float
    pcc_export_difference_mwh: float
    flat_price_settlement_difference_cny_per_year: float
    comparator_curtailment_mwh: float
    candidate_curtailment_mwh: float
    curtailment_reduction_mwh: float
    comparator_fuel_tce: float
    candidate_fuel_tce: float
    fuel_saving_tce: float
    tes_auxiliary_mwh_e: float
    comparator_primary_cost_cny: float
    candidate_audited_cost_cny: float
    candidate_primary_primal_bound_cny: float
    candidate_primary_dual_bound_cny: float
    candidate_primary_mip_gap: float
    candidate_primary_cost_tolerance_cny: float
    secondary_curtailment_mip_gap: float
    candidate_service_feasibility_warm_start: bool
    candidate_service_feasibility_deviation_mw: float | None
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
class E0D19ExecutionRecord:
    window_id: str
    natural_runtime_seconds: float
    comparator_runtime_seconds: float
    candidate_runtime_seconds: float
    candidate_service_feasibility_runtime_seconds: float | None


@dataclass(frozen=True)
class E0D19Run:
    records: tuple[E0D19Record, ...]
    execution: tuple[E0D19ExecutionRecord, ...]
    heat_path: Path
    vre_path: Path


@dataclass(frozen=True)
class E0D19Export:
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


def _same_pcc_audit(
    case: E0CCase,
    result: E0CResult,
    *,
    tolerance_mwh: float = _SERVICE_ABS_TOL_MWH,
) -> float:
    """Validate the public service identity and return delivered annual MWh."""

    if case.pcc_export_service is None or result.annual_economics is None:
        raise ValueError("same-PCC audit requires an annual PCC service and audit")
    annual = result.annual_economics
    service = case.pcc_export_service
    if annual.pcc_export_service_id != service.service_id:
        raise ValueError("result lost the annual PCC service identity")
    if annual.pcc_export_target_mwh is None or not math.isclose(
        annual.pcc_export_target_mwh,
        service.target_export_mwh,
        rel_tol=0.0,
        abs_tol=tolerance_mwh,
    ):
        raise ValueError("result lost the annual PCC export target")
    if not math.isclose(
        annual.weighted_pcc_export_mwh,
        service.target_export_mwh,
        rel_tol=0.0,
        abs_tol=tolerance_mwh,
    ):
        raise ValueError("annual PCC export does not satisfy the common service")
    return annual.weighted_pcc_export_mwh


def run_e0d19(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    windows: tuple[E0D17WindowSpec, ...] = DEFAULT_WINDOWS,
) -> E0D19Run:
    """Run same-curtailment and same-PCC no-storage/TES comparisons."""

    inputs = load_e0d17_inputs(heat_path, vre_path)
    readiness = build_e0d15_tes_formal_cost_readiness()
    records: list[E0D19Record] = []
    execution: list[E0D19ExecutionRecord] = []
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
        natural = natural_result.annual_economics
        assert natural is not None
        service_tolerance = max(
            1e-6,
            natural.weighted_renewable_available_mwh * 1e-10,
        )
        curtailment_service = AnnualCurtailmentServiceSpec(
            service_id=f"e0d19_primary_incumbent_no_storage:{window.window_id}",
            maximum_curtailment_mwh=(
                natural.weighted_curtailment_mwh + service_tolerance
            ),
        )
        pcc_service = AnnualPCCExportServiceSpec(
            service_id=f"e0d19_flat_price_common_delivery:{window.window_id}",
            target_export_mwh=natural.weighted_pcc_export_mwh,
        )
        comparator_case = replace(
            natural_case,
            curtailment_service=curtailment_service,
            pcc_export_service=pcc_service,
        )
        candidate_case = replace(
            _tight_case(
                _base_case(
                    rows,
                    architecture=Architecture.TES,
                    service=curtailment_service,
                )
            ),
            pcc_export_service=pcc_service,
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
            pcc_service_feasibility_warm_start=(window.hours > 24),
        )
        comparator_export = _same_pcc_audit(comparator_case, comparator_result)
        candidate_export = _same_pcc_audit(candidate_case, candidate_result)
        comparison = compare_e0c_annual_break_even(
            comparator_case,
            comparator_result,
            candidate_case,
            candidate_result,
            spec=E0CBreakEvenAdapterSpec(
                scenario_id="yangling_legacy_vre_mapped_2024_e0d19_same_pcc",
                horizon_id=window.window_id,
                known_cost_scope_id=(
                    "fuel_only_same_annual_pcc_service_2024_cny_exploratory"
                ),
                omitted_non_tes_cost_terms=(
                    "chp_variable_om",
                    "carbon_compliance_allowance",
                    "time_varying_electricity_settlement",
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
        primary_cost_tolerance = candidate_result.primary_cost_tolerance_cny
        if None in (
            candidate_primal,
            candidate_dual,
            candidate_gap,
            secondary_gap,
            primary_cost_tolerance,
        ):
            raise RuntimeError("E0-D-19 requires complete primary and secondary bounds")
        assert candidate_primal is not None
        assert candidate_dual is not None
        assert candidate_gap is not None
        assert secondary_gap is not None
        assert primary_cost_tolerance is not None
        comparator_cost = comparator.known_cost.known_total_cost_cny
        candidate_audited_cost = candidate.known_cost.known_total_cost_cny
        eac_lower = comparison.break_even.maximum_tes_ownership_eac_cny_per_year
        eac_upper = (
            eac_lower
            if candidate_gap <= 1e-12
            else max(eac_lower, comparator_cost - candidate_dual)
        )
        tes_operation = candidate_result.tes_operation
        if tes_operation is None:
            raise RuntimeError("TES candidate must expose annual TES operation")
        export_difference = candidate_export - comparator_export
        records.append(
            E0D19Record(
                window_id=window.window_id,
                window_start=window.start.isoformat(timespec="seconds"),
                hours=window.hours,
                annual_weight_per_hour=8_784.0 / window.hours,
                curtailment_service_id=curtailment_service.service_id,
                service_curtailment_ceiling_mwh=(
                    curtailment_service.maximum_curtailment_mwh
                ),
                pcc_export_service_id=pcc_service.service_id,
                pcc_export_target_mwh=pcc_service.target_export_mwh,
                comparator_pcc_export_mwh=comparator_export,
                candidate_pcc_export_mwh=candidate_export,
                pcc_export_difference_mwh=export_difference,
                flat_price_settlement_difference_cny_per_year=0.0,
                comparator_curtailment_mwh=comparator.physical.curtailment_mwh,
                candidate_curtailment_mwh=candidate.physical.curtailment_mwh,
                curtailment_reduction_mwh=delta.curtailment_reduction_mwh,
                comparator_fuel_tce=comparator.physical.fuel_tce,
                candidate_fuel_tce=candidate.physical.fuel_tce,
                fuel_saving_tce=delta.fuel_saving_tce,
                tes_auxiliary_mwh_e=tes_operation.total_auxiliary_mwh_e,
                comparator_primary_cost_cny=comparator_cost,
                candidate_audited_cost_cny=candidate_audited_cost,
                candidate_primary_primal_bound_cny=candidate_primal,
                candidate_primary_dual_bound_cny=candidate_dual,
                candidate_primary_mip_gap=candidate_gap,
                candidate_primary_cost_tolerance_cny=primary_cost_tolerance,
                secondary_curtailment_mip_gap=secondary_gap,
                candidate_service_feasibility_warm_start=(
                    candidate_result.pcc_service_feasibility_warm_start
                ),
                candidate_service_feasibility_deviation_mw=(
                    candidate_result.pcc_service_feasibility_deviation_mw
                ),
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
                    "exact_24h_same_pcc_service_diagnostic"
                    if window.hours == 24 and candidate_gap <= 1e-12
                    else "bounded_gap_336h_same_pcc_service_interval_not_formal_tac"
                ),
            )
        )
        execution.append(
            E0D19ExecutionRecord(
                window_id=window.window_id,
                natural_runtime_seconds=natural_result.runtime_seconds,
                comparator_runtime_seconds=comparator_result.runtime_seconds,
                candidate_runtime_seconds=candidate_result.runtime_seconds,
                candidate_service_feasibility_runtime_seconds=(
                    candidate_result.pcc_service_feasibility_runtime_seconds
                ),
            )
        )
    return E0D19Run(
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


def write_e0d19(run: E0D19Run, output_dir: str | Path) -> E0D19Export:
    """Write canonical same-service results and a runtime sidecar."""

    if not isinstance(run, E0D19Run) or not run.records:
        raise ValueError("run must contain E0-D-19 records")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "e0d19_same_pcc_service.csv"
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
        "e0d19_same_pcc_service.py",
        "e0d18_performance.py",
        "model.py",
        "tes_break_even_adapter.py",
        "components/chp.py",
        "components/molten_salt.py",
    )
    manifest = _json_ready(
        {
            "schema": SCHEMA_ID,
            "scientific_scope": (
                "same_annual_pcc_service_screen_not_formal_tac_not_e1"
            ),
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
                "known_cost_scope": (
                    "fuel_only_same_annual_pcc_service_2024_cny_exploratory"
                ),
                "omitted_non_tes_cost_terms": [
                    "chp_variable_om",
                    "carbon_compliance_allowance",
                    "time_varying_electricity_settlement",
                    "tes_variable_om",
                ],
            },
            "settlement_boundary": {
                "ownership": "single_system_owner_at_common_PCC",
                "baseline": "same_annual_PCC_delivery",
                "flat_price_identity": (
                    "pi_flat*(candidate_export-comparator_export)=0"
                ),
                "flat_price_settlement_complete": True,
                "time_varying_settlement_complete": False,
                "legacy_tou_status": (
                    "generated_scenario_without_registered_primary_source;excluded"
                ),
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
                "pcc_service_feasibility_warm_start": {
                    "24": False,
                    "336": True,
                    "phase_1": (
                        "minimize_average_PCC_delivery_absolute_deviation"
                    ),
                    "acceptance": "deviation_mw<=1e-9",
                    "phase_2": (
                        "restore_exact_PCC_equality_and_primary_cost_objective"
                    ),
                },
                "interval_definition": (
                    "lower=comparator_exact_cost-candidate_secondary_audited_cost;"
                    "upper=comparator_exact_cost-candidate_primary_dual_bound"
                ),
                "secondary_audited_cost_contract": (
                    "fixed_primary_integers;cost<=primary_incumbent+reported_tolerance"
                ),
            },
            "sources": {name: _sha256(source_dir / name) for name in source_names},
            "windows": [
                {
                    "window_id": record.window_id,
                    "start": record.window_start,
                    "hours": record.hours,
                    "curtailment_service_id": record.curtailment_service_id,
                    "pcc_export_service_id": record.pcc_export_service_id,
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
    return E0D19Export(
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
    export = write_e0d19(
        run_e0d19(args.heat, args.vre, windows=selected),
        args.output,
    )
    print(json.dumps(export.canonical_sha256, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
