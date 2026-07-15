"""Diagnose the actual weeks behind an E0-D-38 feasibility reversal.

The diagnostic repeats the zero-fuel, minimum-curtailment no-storage problem on
the actual 8784 h horizon and on the frozen D36 horizon.  It then compares each
actual week with its frozen representative-week assignment.  This is a
post-failure diagnostic only; it does not change D36 weights or the D38 gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pyomo.environ import value

from tes_bess_boundary.e0d38_prevalidation import (
    CURTAILMENT_FRACTION,
    FORMAL_MIP_REL_GAP,
    build_d38_case,
    load_full_year_input,
    load_representative_input,
    planning_inputs_for_state,
    state_spec,
)
from tes_bess_boundary.model import Architecture, ValidationObjectiveSpec
from tes_bess_boundary.planning_model import (
    build_endogenous_capacity_model,
    relax_zero_cost_fuel_segment_binaries,
)
from tes_bess_boundary.solver import create_highs_solver


SCHEMA_ID = "tes_bess_boundary.e0d38_weekly_failure_diagnostic.v1"
FULL_WEEK_HOURS = 168
FULL_WEEK_COUNT = 52
FULL_WEEK_SCORING_HOURS = FULL_WEEK_HOURS * FULL_WEEK_COUNT


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _minimum_curtailment_case(
    *,
    state: object,
    horizon_input: object,
    planning_inputs: object,
) -> object:
    return build_d38_case(
        state=state,
        architecture=Architecture.NO_STORAGE,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=1.0,
        ),
        curtailment_service=None,
        pcc_export_service=None,
    )


def _solve_hourly_curtailment(
    case: object,
    *,
    solver_threads: int,
    mip_rel_gap: float,
    time_limit_seconds: float | None,
) -> tuple[list[float], dict[str, Any]]:
    model = build_endogenous_capacity_model(case)
    relaxed_binary_count = relax_zero_cost_fuel_segment_binaries(model, case)
    solver = create_highs_solver(
        threads=solver_threads,
        random_seed=0,
        mip_rel_gap=mip_rel_gap,
    )
    if time_limit_seconds is not None:
        solver.options["time_limit"] = time_limit_seconds
    started = perf_counter()
    solved = solver.solve(model)
    runtime_seconds = perf_counter() - started
    termination = str(solved.solver.termination_condition).lower()
    lower_bound = float(solved.problem.lower_bound)
    upper_bound = float(solved.problem.upper_bound)
    gap = abs(upper_bound - lower_bound) / max(abs(upper_bound), 1e-12)
    if "optimal" not in termination and not (
        math.isfinite(lower_bound)
        and math.isfinite(upper_bound)
        and gap <= mip_rel_gap
    ):
        raise RuntimeError(
            "weekly diagnostic solve did not converge within the accepted gap: "
            f"termination={termination}, relative_gap={gap}"
        )
    dt_hours = case.timeseries.dt_hours
    hourly = [
        float(
            value(
                dt_hours
                * (model.wind_curtailed[period] + model.pv_curtailed[period])
            )
        )
        for period in model.periods
    ]
    weighted_total = float(value(model.annual_curtailment_mwh))
    return hourly, {
        "termination_condition": termination,
        "objective_lower_bound_mwh": lower_bound,
        "objective_upper_bound_mwh": upper_bound,
        "relative_mip_gap": gap,
        "runtime_seconds": runtime_seconds,
        "relaxed_fuel_segment_binary_count": relaxed_binary_count,
        "weighted_minimum_curtailment_mwh": weighted_total,
    }


def group_actual_weeks(
    hourly_curtailment_mwh: list[float],
    hourly_renewable_available_mwh: list[float],
) -> tuple[dict[int, dict[str, float]], dict[str, float]]:
    """Group 2024 hourly values into 52 Monday weeks and the 48 h tail."""

    if len(hourly_curtailment_mwh) != len(hourly_renewable_available_mwh):
        raise ValueError("actual curtailment and renewable series must align")
    if len(hourly_curtailment_mwh) != 8_784:
        raise ValueError("D38 actual weekly diagnostic requires 8784 hours")
    weeks: dict[int, dict[str, float]] = {}
    for week in range(1, FULL_WEEK_COUNT + 1):
        start = (week - 1) * FULL_WEEK_HOURS
        stop = start + FULL_WEEK_HOURS
        curtailed = sum(hourly_curtailment_mwh[start:stop])
        available = sum(hourly_renewable_available_mwh[start:stop])
        weeks[week] = {
            "curtailment_mwh": curtailed,
            "renewable_available_mwh": available,
            "curtailment_rate": curtailed / available if available > 0.0 else 0.0,
        }
    tail_curtailment = sum(hourly_curtailment_mwh[FULL_WEEK_SCORING_HOURS:])
    tail_available = sum(hourly_renewable_available_mwh[FULL_WEEK_SCORING_HOURS:])
    return weeks, {
        "curtailment_mwh": tail_curtailment,
        "renewable_available_mwh": tail_available,
        "curtailment_rate": (
            tail_curtailment / tail_available if tail_available > 0.0 else 0.0
        ),
    }


def group_representative_weeks(
    hourly_curtailment_mwh: list[float],
    hourly_renewable_available_mwh: list[float],
    period_rows: list[dict[str, str]],
) -> tuple[dict[int, dict[str, float]], dict[str, float]]:
    """Recover unweighted representative weeks and the scored year-end tail."""

    if not (
        len(hourly_curtailment_mwh)
        == len(hourly_renewable_available_mwh)
        == len(period_rows)
    ):
        raise ValueError("representative diagnostic series must align")
    weeks: dict[int, dict[str, float]] = defaultdict(
        lambda: {"curtailment_mwh": 0.0, "renewable_available_mwh": 0.0}
    )
    tail = {"curtailment_mwh": 0.0, "renewable_available_mwh": 0.0}
    for curtailed, available, row in zip(
        hourly_curtailment_mwh,
        hourly_renewable_available_mwh,
        period_rows,
        strict=True,
    ):
        role = row["source_role"]
        if role == "representative_scored":
            week = int(row["source_week_index"])
            weeks[week]["curtailment_mwh"] += curtailed
            weeks[week]["renewable_available_mwh"] += available
        elif role == "tail_scored":
            tail["curtailment_mwh"] += curtailed
            tail["renewable_available_mwh"] += available
    for metrics in (*weeks.values(), tail):
        available = metrics["renewable_available_mwh"]
        metrics["curtailment_rate"] = (
            metrics["curtailment_mwh"] / available if available > 0.0 else 0.0
        )
    return dict(weeks), tail


def summarize_assignment_error(
    actual_weeks: dict[int, dict[str, float]],
    representative_weeks: dict[int, dict[str, float]],
    assignments: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compare actual weeks with their frozen D36 representative assignment."""

    weekly: list[dict[str, Any]] = []
    clusters: dict[int, dict[str, Any]] = {}
    for row in assignments:
        week = int(row["original_week_index"])
        representative = int(row["assigned_representative_week_index"])
        actual = actual_weeks[week]
        proxy = representative_weeks[representative]
        underrepresentation = actual["curtailment_mwh"] - proxy["curtailment_mwh"]
        weekly.append(
            {
                "original_week_index": week,
                "week_start": row["week_start"],
                "week_end": row["week_end"],
                "assigned_representative_week_index": representative,
                "actual_minimum_curtailment_mwh": actual["curtailment_mwh"],
                "representative_week_minimum_curtailment_mwh": proxy[
                    "curtailment_mwh"
                ],
                "curtailment_underrepresentation_mwh": underrepresentation,
                "actual_curtailment_rate": actual["curtailment_rate"],
                "representative_week_curtailment_rate": proxy[
                    "curtailment_rate"
                ],
            }
        )
        cluster = clusters.setdefault(
            representative,
            {
                "representative_week_index": representative,
                "assigned_actual_week_count": 0,
                "actual_minimum_curtailment_mwh": 0.0,
                "representative_projected_curtailment_mwh": 0.0,
            },
        )
        cluster["assigned_actual_week_count"] += 1
        cluster["actual_minimum_curtailment_mwh"] += actual["curtailment_mwh"]
        cluster["representative_projected_curtailment_mwh"] += proxy[
            "curtailment_mwh"
        ]
    for cluster in clusters.values():
        cluster["curtailment_underrepresentation_mwh"] = (
            cluster["actual_minimum_curtailment_mwh"]
            - cluster["representative_projected_curtailment_mwh"]
        )
    weekly.sort(key=lambda item: item["curtailment_underrepresentation_mwh"], reverse=True)
    cluster_rows = sorted(
        clusters.values(),
        key=lambda item: item["curtailment_underrepresentation_mwh"],
        reverse=True,
    )
    return weekly, cluster_rows


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    state = state_spec(args.state)
    planning_inputs = planning_inputs_for_state(args.price_basis_path, state)
    actual_input = load_full_year_input(args.heat_path, args.vre_path, state)
    representative_input = load_representative_input(args.periods_path, state)
    actual_case = _minimum_curtailment_case(
        state=state,
        horizon_input=actual_input,
        planning_inputs=planning_inputs,
    )
    representative_case = _minimum_curtailment_case(
        state=state,
        horizon_input=representative_input,
        planning_inputs=planning_inputs,
    )
    actual_curtailment, actual_solve = _solve_hourly_curtailment(
        actual_case,
        solver_threads=args.solver_threads,
        mip_rel_gap=args.mip_rel_gap,
        time_limit_seconds=args.time_limit_seconds,
    )
    representative_curtailment, representative_solve = _solve_hourly_curtailment(
        representative_case,
        solver_threads=args.solver_threads,
        mip_rel_gap=args.mip_rel_gap,
        time_limit_seconds=args.time_limit_seconds,
    )
    actual_renewable = [
        actual_case.timeseries.dt_hours * (wind + pv)
        for wind, pv in zip(
            actual_case.timeseries.wind_available_mw,
            actual_case.timeseries.pv_available_mw,
            strict=True,
        )
    ]
    representative_renewable = [
        representative_case.timeseries.dt_hours * (wind + pv)
        for wind, pv in zip(
            representative_case.timeseries.wind_available_mw,
            representative_case.timeseries.pv_available_mw,
            strict=True,
        )
    ]
    period_rows = _read_csv(args.periods_path)
    assignments = _read_csv(args.assignments_path)
    actual_weeks, actual_tail = group_actual_weeks(
        actual_curtailment,
        actual_renewable,
    )
    representative_weeks, representative_tail = group_representative_weeks(
        representative_curtailment,
        representative_renewable,
        period_rows,
    )
    weekly, clusters = summarize_assignment_error(
        actual_weeks,
        representative_weeks,
        assignments,
    )
    actual_total = actual_solve["weighted_minimum_curtailment_mwh"]
    representative_total = representative_solve[
        "weighted_minimum_curtailment_mwh"
    ]
    epsilon_ceiling = CURTAILMENT_FRACTION * actual_input.renewable_available_mwh
    return {
        "schema_id": SCHEMA_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": "complete",
        "claim_scope": "post_failure_week_diagnostic_not_formal_project_tac",
        "formal_project_tac_ready": False,
        "state": {
            "state_id": state.state_id,
            "heat_scale": state.heat_scale,
            "pcc_export_capacity_mw": state.pcc_export_capacity_mw,
        },
        "method": {
            "actual_horizon": "single_8784h_cyclic_block",
            "representative_horizon": "frozen_d36_seven_cyclic_blocks",
            "objective": "zero_fuel_minimum_renewable_curtailment",
            "fuel_segment_code": "continuous_exact_zero_fuel_objective_projection",
            "assignments": "frozen_d36_week_assignments",
        },
        "solver": {
            "name": "appsi_highs",
            "threads": args.solver_threads,
            "random_seed": 0,
            "mip_rel_gap": args.mip_rel_gap,
            "time_limit_seconds": args.time_limit_seconds,
        },
        "actual_solve": actual_solve,
        "representative_solve": representative_solve,
        "actual_renewable_available_mwh": actual_input.renewable_available_mwh,
        "epsilon_10_percent_ceiling_mwh": epsilon_ceiling,
        "actual_minimum_curtailment_mwh": actual_total,
        "representative_weighted_minimum_curtailment_mwh": representative_total,
        "aggregate_curtailment_underrepresentation_mwh": (
            actual_total - representative_total
        ),
        "actual_service_deficit_above_epsilon_mwh": actual_total - epsilon_ceiling,
        "representative_service_margin_below_epsilon_mwh": (
            epsilon_ceiling - representative_total
        ),
        "largest_underrepresented_actual_week": weekly[0],
        "top_10_underrepresented_actual_weeks": weekly[:10],
        "cluster_assignment_diagnostics": clusters,
        "year_end_tail": {
            "actual": actual_tail,
            "representative": representative_tail,
            "curtailment_underrepresentation_mwh": (
                actual_tail["curtailment_mwh"]
                - representative_tail["curtailment_mwh"]
            ),
        },
        "weekly_diagnostics": sorted(
            weekly,
            key=lambda item: item["original_week_index"],
        ),
        "provenance": {
            "heat_file_sha256": _sha256(args.heat_path),
            "vre_file_sha256": _sha256(args.vre_path),
            "representative_periods_sha256": _sha256(args.periods_path),
            "week_assignments_sha256": _sha256(args.assignments_path),
            "diagnostic_code_sha256": _sha256(Path(__file__)),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        choices=("baseline", "high_heat_tight_pcc_r1"),
        default="baseline",
    )
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--periods-path", type=Path, required=True)
    parser.add_argument("--assignments-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver-threads", type=int, default=4)
    parser.add_argument("--mip-rel-gap", type=float, default=FORMAL_MIP_REL_GAP)
    parser.add_argument("--time-limit-seconds", type=float)
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.solver_threads < 1:
        raise ValueError("solver threads must be at least one")
    if not 0.0 <= args.mip_rel_gap <= FORMAL_MIP_REL_GAP:
        raise ValueError("mip-rel-gap must lie in [0, 0.001]")
    if args.time_limit_seconds is not None and args.time_limit_seconds <= 0.0:
        raise ValueError("time limit must be positive")


def main() -> None:
    args = build_parser().parse_args()
    _validate_args(args)
    payload = run_diagnostic(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
