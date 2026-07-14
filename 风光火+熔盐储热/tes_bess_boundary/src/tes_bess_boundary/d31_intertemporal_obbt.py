"""Intertemporal continuous-relaxation OBBT for the open global L1 problem.

E0-D-31 retains the complete single-architecture D19 dispatch model, including
CHP transition/ramp constraints, TES inventory dynamics, annual PCC service,
and the normalized cost/curtailment admissibility caps.  It then relaxes every
integer variable and solves a proven-optimal LP minimum and maximum for every
periodic PCC variable.  The resulting intervals contain the projection of all
D19-admissible integer dispatches and can safely replace the looser D30 static
intervals in the same six interval-aware sign inequalities.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    E0D22_TRACE_SHA256,
    DispatchAdmissibility,
    RedistributionDirection,
    _seed_joint_model,
    _solve_d19_selected_model,
    build_joint_redistribution_model,
    load_e0d23_source_rows,
)
from tes_bess_boundary.d26_numerical_certification import (
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
    IntegerScope,
    _build_cases,
    _fix_integer_pattern,
    _strict_solve,
    _window_mip_gap,
)
from tes_bess_boundary.d27_direction_generation import (
    _replace_big_m_with_disaggregated_sign_formulation,
    _seed_joint_from_joint,
)
from tes_bess_boundary.d29_export_linked_bound_tightening import (
    D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH,
    add_export_linked_sign_cuts,
)
from tes_bess_boundary.d30_certification_bundle import D30_BUNDLE_SCHEMA
from tes_bess_boundary.d30_physics_service_bound_tightening import (
    D30_SCREEN_SCHEMA,
    add_physics_service_sign_cuts,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.model import E0CCase, build_e0c_model
from tes_bess_boundary.solver import create_highs_solver


D31_SCREEN_SCHEMA = "tes_bess_boundary.e0d31_intertemporal_obbt_screen.v1"
D31_PROBE_SCHEMA = "tes_bess_boundary.e0d31_intertemporal_obbt_probe.v1"
D31_BOUND_SAFETY_MARGIN_MW = 1e-4
D31_RELAXATION_CONTRACT = (
    "full_single_architecture_d19_model_with_all_integer_domains_relaxed_"
    "and_intertemporal_service_admissibility_constraints_retained"
)


@dataclass(frozen=True)
class D30OBBTReference:
    window_id: str
    hours: int
    target_export_mwh: float
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    comparator_lower_mw: tuple[float, ...]
    comparator_upper_mw: tuple[float, ...]
    candidate_lower_mw: tuple[float, ...]
    candidate_upper_mw: tuple[float, ...]
    csv_sha256: str
    manifest_sha256: str
    screen_sha256: str


@dataclass(frozen=True)
class PeriodOBBTResult:
    period: int
    minimum_mw: float
    maximum_mw: float
    minimum_runtime_seconds: float
    maximum_runtime_seconds: float
    relaxed_integer_variable_count: int
    solver_retry_count: int = 0


@dataclass(frozen=True)
class ArchitectureOBBTBounds:
    architecture: str
    periods: int
    lower_mw: tuple[float, ...]
    upper_mw: tuple[float, ...]
    lp_solve_count: int
    optimal_lp_solve_count: int
    worker_count: int
    relaxed_integer_variable_count: int
    solver_runtime_seconds: float
    solver_retry_count: int
    safety_margin_mw: float = D31_BOUND_SAFETY_MARGIN_MW
    relaxation_contract: str = D31_RELAXATION_CONTRACT


@dataclass(frozen=True)
class D31BoundAudit:
    periods: int
    per_period_cut_count: int
    d30_mean_positive_sign_width_mw: float
    d30_mean_negative_sign_width_mw: float
    d31_mean_positive_sign_width_mw: float
    d31_mean_negative_sign_width_mw: float
    positive_width_reduction_vs_d30_fraction: float
    negative_width_reduction_vs_d30_fraction: float
    positive_width_reduction_vs_pcc_fraction: float
    negative_width_reduction_vs_pcc_fraction: float
    comparator_mean_width_d30_mw: float
    comparator_mean_width_d31_mw: float
    candidate_mean_width_d30_mw: float
    candidate_mean_width_d31_mw: float
    pcc_capacity_mw: float
    bound_safety_margin_mw: float
    intertemporal_constraints_retained: bool = True
    annual_service_and_admissibility_retained: bool = True
    all_integer_domains_relaxed: bool = True
    feasible_set_changed_for_integer_solutions: bool = False
    primary_integer_patterns_reopened: bool = True
    sign_binaries_reopened: bool = True


@dataclass(frozen=True)
class D31OBBTScreen:
    schema: str
    window_id: str
    hours: int
    workers: int
    comparator_workers: int
    candidate_workers: int
    target_export_mwh: float
    reference_d30_lower_bound_mwh: float
    reference_d30_upper_bound_mwh: float
    reference_d30_csv_sha256: str
    reference_d30_manifest_sha256: str
    reference_d30_screen_sha256: str
    comparator: ArchitectureOBBTBounds
    candidate: ArchitectureOBBTBounds
    bound_audit: D31BoundAudit
    known_d19_witness_within_bounds: bool
    wall_runtime_seconds: float
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


@dataclass(frozen=True)
class D31GlobalProbe:
    schema: str
    window_id: str
    hours: int
    threads: int
    time_limit_seconds: float
    reference_d30_lower_bound_mwh: float
    reference_d30_upper_bound_mwh: float
    reference_d30_csv_sha256: str
    reference_d30_manifest_sha256: str
    reference_d30_screen_sha256: str
    d31_screen_sha256: str
    selected_face_witness_mwh: float
    selected_face_termination: str
    selected_face_bound_certificate_complete: bool
    known_witness_within_bounds: bool
    bound_audit: dict[str, object]
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    recomputed_redistribution_mwh: float
    witness_reference_excess_mwh: float
    witness_clamped_to_reference: bool
    dual_bound_mwh: float | None
    dual_reference_deficit_mwh: float | None
    dual_clamped_to_reference_lower: bool
    relative_gap: float | None
    bound_certificate_complete: bool
    witness_dominance_passed: bool
    witness_dominance_tolerance_mwh: float
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    global_upper_bound_improvement_mwh: float
    global_upper_bound_improvement_fraction: float
    global_upper_bound_improved: bool
    exact_global_maximum: bool
    global_dual_is_valid_l1_upper_bound: bool
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: object, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _finite_vector(value: object, *, label: str, periods: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != periods:
        raise ValueError(f"{label} must contain {periods} values")
    return tuple(_finite(item, label=label) for item in value)


def load_d30_obbt_reference(
    source_dir: str | Path,
    *,
    window_id: str,
) -> D30OBBTReference:
    """Load one internally hash-verified D30 certificate and screen."""

    source = Path(source_dir)
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("D31 is missing the D30 manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != D30_BUNDLE_SCHEMA:
        raise ValueError("D31 D30 manifest schema mismatch")
    boundary = manifest.get("scientific_boundary")
    if not isinstance(boundary, dict) or boundary.get(
        "global_dual_is_valid_l1_upper_bound"
    ) is not True:
        raise ValueError("D31 D30 manifest lacks a valid global L1 upper bound")
    output = manifest.get("output")
    screens = manifest.get("screens")
    if not isinstance(output, dict) or not isinstance(screens, dict):
        raise ValueError("D31 D30 manifest is incomplete")
    csv_name = output.get("csv")
    csv_hash = output.get("csv_sha256")
    if not isinstance(csv_name, str) or not isinstance(csv_hash, str):
        raise ValueError("D31 D30 output contract is incomplete")
    csv_path = source / csv_name
    if not csv_path.is_file() or _sha256(csv_path) != csv_hash:
        raise ValueError("D31 D30 certificate hash mismatch")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        matches = tuple(
            row for row in csv.DictReader(handle) if row.get("window_id") == window_id
        )
    if len(matches) != 1:
        raise ValueError(f"D31 needs exactly one D30 row for {window_id}")
    row = matches[0]
    if row.get("global_dual_is_valid_l1_upper_bound") != "true":
        raise ValueError("D31 D30 reference has no valid global upper bound")
    hours = int(row["hours"])
    screen_name = f"screen_{hours}h.json"
    expected_screen_hash = screens.get(screen_name)
    screen_path = source / screen_name
    if not isinstance(expected_screen_hash, str) or not screen_path.is_file():
        raise ValueError("D31 D30 screen contract is incomplete")
    if _sha256(screen_path) != expected_screen_hash:
        raise ValueError("D31 D30 screen hash mismatch")
    screen = json.loads(screen_path.read_text(encoding="utf-8"))
    if (
        screen.get("schema") != D30_SCREEN_SCHEMA
        or screen.get("window_id") != window_id
        or int(screen.get("hours", 0)) != hours
    ):
        raise ValueError("D31 D30 screen identity mismatch")
    lower = _finite(row["strict_global_lower_bound_mwh"], label="D30 lower")
    upper = _finite(row["strict_global_upper_bound_mwh"], label="D30 upper")
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise ValueError("D31 D30 reference interval is reversed")
    return D30OBBTReference(
        window_id=window_id,
        hours=hours,
        target_export_mwh=_finite(
            screen.get("target_export_mwh"), label="D30 PCC target"
        ),
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        comparator_lower_mw=_finite_vector(
            screen.get("comparator_service_lower_mw"),
            label="D30 comparator lower",
            periods=hours,
        ),
        comparator_upper_mw=_finite_vector(
            screen.get("comparator_service_upper_mw"),
            label="D30 comparator upper",
            periods=hours,
        ),
        candidate_lower_mw=_finite_vector(
            screen.get("candidate_service_lower_mw"),
            label="D30 candidate lower",
            periods=hours,
        ),
        candidate_upper_mw=_finite_vector(
            screen.get("candidate_service_upper_mw"),
            label="D30 candidate upper",
            periods=hours,
        ),
        csv_sha256=csv_hash,
        manifest_sha256=_sha256(manifest_path),
        screen_sha256=expected_screen_hash,
    )


def build_intertemporal_obbt_relaxation(
    case: E0CCase,
    admissibility: DispatchAdmissibility,
    *,
    d30_lower_mw: Sequence[float],
    d30_upper_mw: Sequence[float],
) -> tuple[object, int]:
    """Build the full D19 single-architecture LP relaxation used for OBBT."""

    from pyomo.environ import Constraint, Objective, TransformationFactory, Var, minimize

    periods = case.timeseries.period_count
    lower = tuple(float(item) for item in d30_lower_mw)
    upper = tuple(float(item) for item in d30_upper_mw)
    if len(lower) != periods or len(upper) != periods:
        raise ValueError("D31 D30 bounds do not match the case horizon")
    if any(
        not math.isfinite(lo)
        or not math.isfinite(hi)
        or lo < 0.0
        or lo > hi
        or hi > case.pcc_export_capacity_mw + 1e-9
        for lo, hi in zip(lower, upper, strict=True)
    ):
        raise ValueError("D31 received an invalid D30 interval")
    model = build_e0c_model(case)
    model.validation_cost.deactivate()
    cost_scale = max(1.0, admissibility.primary_cost_upper_bound_cny)
    curtailment_scale = max(1.0, admissibility.curtailment_upper_bound_mwh)
    model.d31_primary_cost_cap = Constraint(
        expr=model.annual_total_cost_cny / cost_scale
        <= admissibility.primary_cost_upper_bound_cny / cost_scale
    )
    model.d31_curtailment_cap = Constraint(
        expr=model.annual_curtailment_mwh / curtailment_scale
        <= admissibility.curtailment_upper_bound_mwh / curtailment_scale
    )
    service = case.curtailment_service
    if service is not None and hasattr(model, "annual_curtailment_service"):
        model.annual_curtailment_service.deactivate()
        service_scale = max(1.0, service.maximum_curtailment_mwh)
        model.d31_service_curtailment_cap = Constraint(
            expr=model.annual_curtailment_mwh / service_scale
            <= service.maximum_curtailment_mwh / service_scale
        )
    for period in model.periods:
        model.pcc_export[period].setlb(lower[int(period)])
        model.pcc_export[period].setub(upper[int(period)])
    integer_count = sum(
        1
        for variable in model.component_data_objects(Var, active=True, descend_into=True)
        if variable.is_binary() or variable.is_integer()
    )
    if integer_count <= 0:
        raise RuntimeError("D31 found no integer domains to relax")
    TransformationFactory("core.relax_integer_vars").apply_to(model)
    if any(
        variable.is_binary() or variable.is_integer()
        for variable in model.component_data_objects(Var, active=True, descend_into=True)
    ):
        raise RuntimeError("D31 failed to relax every integer domain")
    model.d31_obbt_objective = Objective(expr=0.0, sense=minimize)
    return model, integer_count


_OBBT_MODEL: object | None = None
_OBBT_SOLVER: object | None = None
_OBBT_INTEGER_COUNT = 0
_OBBT_INIT_ARGS: tuple[
    E0CCase,
    DispatchAdmissibility,
    tuple[float, ...],
    tuple[float, ...],
] | None = None


def _initialize_obbt_worker(
    case: E0CCase,
    admissibility: DispatchAdmissibility,
    lower_mw: tuple[float, ...],
    upper_mw: tuple[float, ...],
) -> None:
    global _OBBT_MODEL, _OBBT_SOLVER, _OBBT_INTEGER_COUNT, _OBBT_INIT_ARGS
    model, integer_count = build_intertemporal_obbt_relaxation(
        case,
        admissibility,
        d30_lower_mw=lower_mw,
        d30_upper_mw=upper_mw,
    )
    solver = create_highs_solver(threads=1, random_seed=0, mip_rel_gap=0.0)
    solver.options["primal_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    solver.options["dual_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    _OBBT_MODEL = model
    _OBBT_SOLVER = solver
    _OBBT_INTEGER_COUNT = integer_count
    _OBBT_INIT_ARGS = (case, admissibility, lower_mw, upper_mw)


def _solve_obbt_period(period: int) -> PeriodOBBTResult:
    from pyomo.environ import maximize, minimize, value
    import highspy

    if _OBBT_MODEL is None or _OBBT_SOLVER is None:
        raise RuntimeError("D31 OBBT worker is not initialized")
    if period < 0 or period >= len(tuple(_OBBT_MODEL.periods)):
        raise ValueError("D31 period is outside the OBBT horizon")
    values: dict[str, float] = {}
    runtimes: dict[str, float] = {}
    retry_count = 0
    for label, sense in (("minimum", minimize), ("maximum", maximize)):
        for attempt in range(2):
            assert _OBBT_MODEL is not None
            assert _OBBT_SOLVER is not None
            model = _OBBT_MODEL
            solver = _OBBT_SOLVER
            model.d31_obbt_objective.set_value(model.pcc_export[period])
            model.d31_obbt_objective.sense = sense
            started = perf_counter()
            try:
                results = solver.solve(model, tee=False)
                runtime = perf_counter() - started
                termination = str(results.solver.termination_condition).lower()
                if termination != "optimal":
                    raise RuntimeError(f"termination={termination}")
            except RuntimeError as exc:
                runtime = perf_counter() - started
                if attempt == 1 or _OBBT_INIT_ARGS is None:
                    raise RuntimeError(
                        f"D31 OBBT {label} at period {period} failed after retry"
                    ) from exc
                retry_count += 1
                highspy.Highs.resetGlobalScheduler(True)
                _initialize_obbt_worker(*_OBBT_INIT_ARGS)
                continue
            runtimes[label] = runtime
            break
        values[label] = _finite(
            value(model.pcc_export[period]), label=f"D31 {label} PCC bound"
        )
    if values["minimum"] > values["maximum"] + D31_BOUND_SAFETY_MARGIN_MW:
        raise RuntimeError("D31 OBBT returned a reversed raw interval")
    return PeriodOBBTResult(
        period=period,
        minimum_mw=values["minimum"],
        maximum_mw=values["maximum"],
        minimum_runtime_seconds=runtimes["minimum"],
        maximum_runtime_seconds=runtimes["maximum"],
        relaxed_integer_variable_count=_OBBT_INTEGER_COUNT,
        solver_retry_count=retry_count,
    )


def _merge_architecture_bounds(
    architecture: str,
    results: Sequence[PeriodOBBTResult],
    *,
    d30_lower_mw: Sequence[float],
    d30_upper_mw: Sequence[float],
    worker_count: int,
) -> ArchitectureOBBTBounds:
    ordered = tuple(sorted(results, key=lambda item: item.period))
    periods = len(tuple(d30_lower_mw))
    if len(ordered) != periods or tuple(item.period for item in ordered) != tuple(
        range(periods)
    ):
        raise RuntimeError("D31 OBBT results do not cover the complete horizon")
    integer_counts = {item.relaxed_integer_variable_count for item in ordered}
    if len(integer_counts) != 1:
        raise RuntimeError("D31 workers disagree on the relaxed integer count")
    lower: list[float] = []
    upper: list[float] = []
    for item, d30_lower, d30_upper in zip(
        ordered, d30_lower_mw, d30_upper_mw, strict=True
    ):
        if item.minimum_mw < d30_lower - D31_BOUND_SAFETY_MARGIN_MW or (
            item.maximum_mw > d30_upper + D31_BOUND_SAFETY_MARGIN_MW
        ):
            raise RuntimeError("D31 OBBT optimum escapes the protected D30 interval")
        protected_lower = max(d30_lower, item.minimum_mw - D31_BOUND_SAFETY_MARGIN_MW)
        protected_upper = min(d30_upper, item.maximum_mw + D31_BOUND_SAFETY_MARGIN_MW)
        if protected_lower > protected_upper:
            raise RuntimeError("D31 protected interval is reversed")
        lower.append(protected_lower)
        upper.append(protected_upper)
    return ArchitectureOBBTBounds(
        architecture=architecture,
        periods=periods,
        lower_mw=tuple(lower),
        upper_mw=tuple(upper),
        lp_solve_count=2 * periods,
        optimal_lp_solve_count=2 * periods,
        worker_count=worker_count,
        relaxed_integer_variable_count=integer_counts.pop(),
        solver_runtime_seconds=math.fsum(
            item.minimum_runtime_seconds + item.maximum_runtime_seconds
            for item in ordered
        ),
        solver_retry_count=sum(item.solver_retry_count for item in ordered),
    )


def _worker_allocation(workers: int, periods: int) -> tuple[int, int]:
    if type(workers) is not int or workers <= 0:
        raise ValueError("D31 workers must be a positive integer")
    if workers == 1:
        return 1, 1
    usable = min(workers, 2 * periods)
    comparator_workers = max(1, round(usable / 7))
    candidate_workers = max(1, usable - comparator_workers)
    return min(periods, comparator_workers), min(periods, candidate_workers)


def _run_architecture_sequential(
    case: E0CCase,
    admissibility: DispatchAdmissibility,
    lower_mw: tuple[float, ...],
    upper_mw: tuple[float, ...],
) -> tuple[PeriodOBBTResult, ...]:
    import highspy

    try:
        _initialize_obbt_worker(case, admissibility, lower_mw, upper_mw)
        return tuple(_solve_obbt_period(period) for period in range(len(lower_mw)))
    finally:
        highspy.Highs.resetGlobalScheduler(True)


def _known_trace_within_bounds(
    d22_source_dir: str | Path,
    *,
    window_id: str,
    comparator_lower_mw: Sequence[float],
    comparator_upper_mw: Sequence[float],
    candidate_lower_mw: Sequence[float],
    candidate_upper_mw: Sequence[float],
) -> bool:
    trace_path = Path(d22_source_dir) / "e0d22_pcc_dispatch_trace.csv"
    if not trace_path.is_file() or _sha256(trace_path) != E0D22_TRACE_SHA256:
        raise ValueError("D31 D22 selected-trace hash mismatch")
    with trace_path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(
            row for row in csv.DictReader(handle) if row.get("window_id") == window_id
        )
    periods = len(tuple(comparator_lower_mw))
    if len(rows) != periods:
        raise ValueError("D31 D22 selected trace has the wrong horizon")
    for expected_period, row in enumerate(rows):
        if int(row["period_index"]) != expected_period:
            raise ValueError("D31 D22 selected trace is not period ordered")
        comparator = _finite(
            row["comparator_pcc_export_mw"], label="D22 comparator PCC"
        )
        candidate = _finite(
            row["candidate_pcc_export_mw"], label="D22 candidate PCC"
        )
        if not (
            comparator_lower_mw[expected_period] - D31_BOUND_SAFETY_MARGIN_MW
            <= comparator
            <= comparator_upper_mw[expected_period] + D31_BOUND_SAFETY_MARGIN_MW
            and candidate_lower_mw[expected_period] - D31_BOUND_SAFETY_MARGIN_MW
            <= candidate
            <= candidate_upper_mw[expected_period] + D31_BOUND_SAFETY_MARGIN_MW
        ):
            return False
    return True


def _mean_width(lower: Sequence[float], upper: Sequence[float]) -> float:
    return math.fsum(hi - lo for lo, hi in zip(lower, upper, strict=True)) / len(
        tuple(lower)
    )


def _sign_widths(
    comparator_lower: Sequence[float],
    comparator_upper: Sequence[float],
    candidate_lower: Sequence[float],
    candidate_upper: Sequence[float],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    positive = tuple(
        max(0.0, candidate_hi - comparator_lo)
        for comparator_lo, candidate_hi in zip(
            comparator_lower, candidate_upper, strict=True
        )
    )
    negative = tuple(
        max(0.0, comparator_hi - candidate_lo)
        for comparator_hi, candidate_lo in zip(
            comparator_upper, candidate_lower, strict=True
        )
    )
    return positive, negative


def _bound_audit(
    reference: D30OBBTReference,
    comparator: ArchitectureOBBTBounds,
    candidate: ArchitectureOBBTBounds,
    *,
    pcc_capacity_mw: float,
) -> D31BoundAudit:
    d30_positive, d30_negative = _sign_widths(
        reference.comparator_lower_mw,
        reference.comparator_upper_mw,
        reference.candidate_lower_mw,
        reference.candidate_upper_mw,
    )
    d31_positive, d31_negative = _sign_widths(
        comparator.lower_mw,
        comparator.upper_mw,
        candidate.lower_mw,
        candidate.upper_mw,
    )
    count = reference.hours
    means = {
        "d30_positive": math.fsum(d30_positive) / count,
        "d30_negative": math.fsum(d30_negative) / count,
        "d31_positive": math.fsum(d31_positive) / count,
        "d31_negative": math.fsum(d31_negative) / count,
    }
    return D31BoundAudit(
        periods=count,
        per_period_cut_count=6 * count,
        d30_mean_positive_sign_width_mw=means["d30_positive"],
        d30_mean_negative_sign_width_mw=means["d30_negative"],
        d31_mean_positive_sign_width_mw=means["d31_positive"],
        d31_mean_negative_sign_width_mw=means["d31_negative"],
        positive_width_reduction_vs_d30_fraction=(
            1.0 - means["d31_positive"] / means["d30_positive"]
            if means["d30_positive"] > 0.0
            else 0.0
        ),
        negative_width_reduction_vs_d30_fraction=(
            1.0 - means["d31_negative"] / means["d30_negative"]
            if means["d30_negative"] > 0.0
            else 0.0
        ),
        positive_width_reduction_vs_pcc_fraction=(
            1.0 - means["d31_positive"] / pcc_capacity_mw
        ),
        negative_width_reduction_vs_pcc_fraction=(
            1.0 - means["d31_negative"] / pcc_capacity_mw
        ),
        comparator_mean_width_d30_mw=_mean_width(
            reference.comparator_lower_mw, reference.comparator_upper_mw
        ),
        comparator_mean_width_d31_mw=_mean_width(
            comparator.lower_mw, comparator.upper_mw
        ),
        candidate_mean_width_d30_mw=_mean_width(
            reference.candidate_lower_mw, reference.candidate_upper_mw
        ),
        candidate_mean_width_d31_mw=_mean_width(candidate.lower_mw, candidate.upper_mw),
        pcc_capacity_mw=pcc_capacity_mw,
        bound_safety_margin_mw=D31_BOUND_SAFETY_MARGIN_MW,
    )


def run_intertemporal_obbt_screen(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d30_source_dir: str | Path,
    window: E0D17WindowSpec,
    workers: int,
) -> D31OBBTScreen:
    """Solve all four proven-optimal PCC OBBT LP families for one window."""

    reference = load_d30_obbt_reference(
        d30_source_dir,
        window_id=window.window_id,
    )
    if reference.hours != window.hours:
        raise ValueError("D31 D30 reference horizon mismatch")
    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator_case, candidate_case, comparator_cap, candidate_cap, service = (
        _build_cases(rows, d19_rows[window.window_id])
    )
    if not math.isclose(
        service.target_export_mwh,
        reference.target_export_mwh,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("D31 D19 and D30 PCC targets disagree")
    comparator_workers, candidate_workers = _worker_allocation(workers, window.hours)
    started = perf_counter()
    if workers == 1:
        comparator_results = _run_architecture_sequential(
            comparator_case,
            comparator_cap,
            reference.comparator_lower_mw,
            reference.comparator_upper_mw,
        )
        candidate_results = _run_architecture_sequential(
            candidate_case,
            candidate_cap,
            reference.candidate_lower_mw,
            reference.candidate_upper_mw,
        )
    else:
        with ProcessPoolExecutor(
            max_workers=comparator_workers,
            initializer=_initialize_obbt_worker,
            initargs=(
                comparator_case,
                comparator_cap,
                reference.comparator_lower_mw,
                reference.comparator_upper_mw,
            ),
        ) as comparator_pool, ProcessPoolExecutor(
            max_workers=candidate_workers,
            initializer=_initialize_obbt_worker,
            initargs=(
                candidate_case,
                candidate_cap,
                reference.candidate_lower_mw,
                reference.candidate_upper_mw,
            ),
        ) as candidate_pool:
            comparator_futures = tuple(
                comparator_pool.submit(_solve_obbt_period, period)
                for period in range(window.hours)
            )
            candidate_futures = tuple(
                candidate_pool.submit(_solve_obbt_period, period)
                for period in range(window.hours)
            )
            comparator_results = tuple(future.result() for future in comparator_futures)
            candidate_results = tuple(future.result() for future in candidate_futures)
    wall_runtime = perf_counter() - started
    comparator = _merge_architecture_bounds(
        comparator_case.architecture.value,
        comparator_results,
        d30_lower_mw=reference.comparator_lower_mw,
        d30_upper_mw=reference.comparator_upper_mw,
        worker_count=comparator_workers,
    )
    candidate = _merge_architecture_bounds(
        candidate_case.architecture.value,
        candidate_results,
        d30_lower_mw=reference.candidate_lower_mw,
        d30_upper_mw=reference.candidate_upper_mw,
        worker_count=candidate_workers,
    )
    witness_within = _known_trace_within_bounds(
        d22_source_dir,
        window_id=window.window_id,
        comparator_lower_mw=comparator.lower_mw,
        comparator_upper_mw=comparator.upper_mw,
        candidate_lower_mw=candidate.lower_mw,
        candidate_upper_mw=candidate.upper_mw,
    )
    if not witness_within:
        raise RuntimeError("D31 OBBT excludes the locked D19 selected witness")
    return D31OBBTScreen(
        schema=D31_SCREEN_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        workers=workers,
        comparator_workers=comparator_workers,
        candidate_workers=candidate_workers,
        target_export_mwh=service.target_export_mwh,
        reference_d30_lower_bound_mwh=(
            reference.strict_global_lower_bound_mwh
        ),
        reference_d30_upper_bound_mwh=(
            reference.strict_global_upper_bound_mwh
        ),
        reference_d30_csv_sha256=reference.csv_sha256,
        reference_d30_manifest_sha256=reference.manifest_sha256,
        reference_d30_screen_sha256=reference.screen_sha256,
        comparator=comparator,
        candidate=candidate,
        bound_audit=_bound_audit(
            reference,
            comparator,
            candidate,
            pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        ),
        known_d19_witness_within_bounds=True,
        wall_runtime_seconds=wall_runtime,
    )


def write_screen(screen: D31OBBTScreen, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(screen), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_d31_screen(
    screen_path: str | Path,
    *,
    window: E0D17WindowSpec,
    reference: D30OBBTReference,
) -> dict[str, object]:
    path = Path(screen_path)
    if not path.is_file():
        raise ValueError("D31 screen file is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != D31_SCREEN_SCHEMA
        or payload.get("window_id") != window.window_id
        or int(payload.get("hours", 0)) != window.hours
    ):
        raise ValueError("D31 screen identity mismatch")
    locks = (
        ("reference_d30_csv_sha256", reference.csv_sha256),
        ("reference_d30_manifest_sha256", reference.manifest_sha256),
        ("reference_d30_screen_sha256", reference.screen_sha256),
    )
    if any(payload.get(key) != expected for key, expected in locks):
        raise ValueError("D31 screen D30 source lock mismatch")
    if payload.get("known_d19_witness_within_bounds") is not True:
        raise ValueError("D31 screen excludes the known D19 witness")
    audit = payload.get("bound_audit")
    if not isinstance(audit, dict) or any(
        audit.get(key) is not expected
        for key, expected in (
            ("intertemporal_constraints_retained", True),
            ("annual_service_and_admissibility_retained", True),
            ("all_integer_domains_relaxed", True),
            ("feasible_set_changed_for_integer_solutions", False),
            ("primary_integer_patterns_reopened", True),
            ("sign_binaries_reopened", True),
        )
    ):
        raise ValueError("D31 screen audit contract mismatch")
    return payload


def _screen_bounds(
    screen: dict[str, object],
    architecture: str,
    *,
    hours: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    payload = screen.get(architecture)
    if not isinstance(payload, dict):
        raise ValueError(f"D31 screen has no {architecture} bounds")
    return (
        _finite_vector(payload.get("lower_mw"), label=f"{architecture} lower", periods=hours),
        _finite_vector(payload.get("upper_mw"), label=f"{architecture} upper", periods=hours),
    )


def _selected_models_within_bounds(
    comparator_selected: object,
    candidate_selected: object,
    *,
    comparator_lower: Sequence[float],
    comparator_upper: Sequence[float],
    candidate_lower: Sequence[float],
    candidate_upper: Sequence[float],
) -> bool:
    from pyomo.environ import value

    for period in comparator_selected.periods:
        index = int(period)
        comparator = float(value(comparator_selected.pcc_export[period]))
        candidate = float(value(candidate_selected.pcc_export[period]))
        if not (
            comparator_lower[index] - D31_BOUND_SAFETY_MARGIN_MW
            <= comparator
            <= comparator_upper[index] + D31_BOUND_SAFETY_MARGIN_MW
            and candidate_lower[index] - D31_BOUND_SAFETY_MARGIN_MW
            <= candidate
            <= candidate_upper[index] + D31_BOUND_SAFETY_MARGIN_MW
        ):
            return False
    return True


def run_intertemporal_obbt_probe(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d30_source_dir: str | Path,
    screen_path: str | Path,
    window: E0D17WindowSpec,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> D31GlobalProbe:
    """Reopen the global D30 maximum with the D31 OBBT intervals."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D31 time limit must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D31 threads must be a positive integer")
    reference = load_d30_obbt_reference(
        d30_source_dir,
        window_id=window.window_id,
    )
    screen = load_d31_screen(screen_path, window=window, reference=reference)
    comparator_lower, comparator_upper = _screen_bounds(
        screen, "comparator", hours=window.hours
    )
    candidate_lower, candidate_upper = _screen_bounds(
        screen, "candidate", hours=window.hours
    )
    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator_case, candidate_case, comparator_cap, candidate_cap, service = (
        _build_cases(rows, d19_rows[window.window_id])
    )
    warm_started = perf_counter()
    comparator_selected = _solve_d19_selected_model(
        comparator_case,
        primary_mip_gap=0.0,
        pcc_service_feasibility_warm_start=False,
    )
    candidate_selected = _solve_d19_selected_model(
        candidate_case,
        primary_mip_gap=_window_mip_gap(window),
        pcc_service_feasibility_warm_start=window.hours > 24,
    )
    warm_runtime = perf_counter() - warm_started
    known_witness_within_bounds = _selected_models_within_bounds(
        comparator_selected,
        candidate_selected,
        comparator_lower=comparator_lower,
        comparator_upper=comparator_upper,
        candidate_lower=candidate_lower,
        candidate_upper=candidate_upper,
    )
    if not known_witness_within_bounds:
        raise RuntimeError("D31 OBBT excludes the reproduced D19 selected witness")

    face_model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_model(face_model, comparator_selected, candidate_selected)
    fixed_count = _fix_integer_pattern(face_model.comparator, comparator_selected)
    fixed_count += _fix_integer_pattern(face_model.candidate, candidate_selected)
    face_result = _strict_solve(
        face_model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.D19_SELECTED_FACE,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=fixed_count,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=min(300.0, time_limit_seconds),
        threads=threads,
        tee=tee,
        allow_incumbent_only=True,
    )

    model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=RedistributionDirection.MAXIMUM,
    )
    _seed_joint_from_joint(face_model, model)
    _replace_big_m_with_disaggregated_sign_formulation(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
    )
    add_export_linked_sign_cuts(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        annual_weights=comparator_case.economics.horizon.period_weights,
        dt_hours=comparator_case.timeseries.dt_hours,
        target_export_mwh=service.target_export_mwh,
    )
    add_physics_service_sign_cuts(
        model,
        comparator_lower_mw=comparator_lower,
        comparator_upper_mw=comparator_upper,
        candidate_lower_mw=candidate_lower,
        candidate_upper_mw=candidate_upper,
    )
    result = _strict_solve(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=service,
        window=window,
        scope=IntegerScope.REOPENED,
        direction=RedistributionDirection.MAXIMUM,
        fixed_primary_integer_count=0,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        tee=tee,
        conditional_face_warm_start_mwh=face_result.auxiliary_objective_mwh,
        conditional_face_warm_start_runtime_seconds=face_result.runtime_seconds,
        conditional_face_warm_start_termination="d31_selected_face",
        conditional_face_fixed_primary_integer_count=fixed_count,
        allow_incumbent_only=True,
    )
    if result.maximum_positive_normalized_constraint_residual > STRICT_FEASIBILITY_TOLERANCE:
        raise RuntimeError("D31 global incumbent violates strict feasibility")
    if abs(result.auxiliary_objective_mismatch_mwh) > (
        D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
    ):
        raise RuntimeError("D31 global incumbent failed L1 recomputation")

    witness_reference_excess = (
        result.recomputed_redistribution_mwh
        - reference.strict_global_upper_bound_mwh
    )
    if witness_reference_excess > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
        raise RuntimeError("D31 witness exceeds the D30 upper bound beyond tolerance")
    witness_clamped = witness_reference_excess > 0.0
    lower = max(
        reference.strict_global_lower_bound_mwh,
        min(
            result.recomputed_redistribution_mwh,
            reference.strict_global_upper_bound_mwh,
        ),
    )
    upper = reference.strict_global_upper_bound_mwh
    dual_reference_deficit: float | None = None
    dual_clamped = False
    if result.dual_bound_mwh is not None:
        dual_reference_deficit = (
            reference.strict_global_lower_bound_mwh - result.dual_bound_mwh
        )
        if dual_reference_deficit > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
            raise RuntimeError("D31 dual falls below the D30 feasible lower bound")
        dual_clamped = dual_reference_deficit > 0.0
        upper = min(
            upper,
            max(
                result.dual_bound_mwh,
                reference.strict_global_lower_bound_mwh,
            ),
        )
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise RuntimeError("D31 strict interval is numerically reversed")
    improvement = reference.strict_global_upper_bound_mwh - upper
    exact = upper - lower <= KNOWN_WITNESS_TOLERANCE_MWH
    return D31GlobalProbe(
        schema=D31_PROBE_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        threads=threads,
        time_limit_seconds=time_limit_seconds,
        reference_d30_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        reference_d30_upper_bound_mwh=reference.strict_global_upper_bound_mwh,
        reference_d30_csv_sha256=reference.csv_sha256,
        reference_d30_manifest_sha256=reference.manifest_sha256,
        reference_d30_screen_sha256=reference.screen_sha256,
        d31_screen_sha256=_sha256(Path(screen_path)),
        selected_face_witness_mwh=face_result.auxiliary_objective_mwh,
        selected_face_termination=face_result.termination,
        selected_face_bound_certificate_complete=face_result.bound_certificate_complete,
        known_witness_within_bounds=True,
        bound_audit=dict(screen["bound_audit"]),
        termination=result.termination,
        runtime_seconds=result.runtime_seconds,
        primal_bound_mwh=result.primal_bound_mwh,
        recomputed_redistribution_mwh=result.recomputed_redistribution_mwh,
        witness_reference_excess_mwh=witness_reference_excess,
        witness_clamped_to_reference=witness_clamped,
        dual_bound_mwh=result.dual_bound_mwh,
        dual_reference_deficit_mwh=dual_reference_deficit,
        dual_clamped_to_reference_lower=dual_clamped,
        relative_gap=result.relative_gap,
        bound_certificate_complete=result.bound_certificate_complete,
        witness_dominance_passed=(
            result.recomputed_redistribution_mwh
            + D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
            >= face_result.auxiliary_objective_mwh
        ),
        witness_dominance_tolerance_mwh=(
            D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
        ),
        maximum_positive_normalized_constraint_residual=(
            result.maximum_positive_normalized_constraint_residual
        ),
        auxiliary_objective_mismatch_mwh=result.auxiliary_objective_mismatch_mwh,
        strict_global_lower_bound_mwh=lower,
        strict_global_upper_bound_mwh=upper,
        global_upper_bound_improvement_mwh=improvement,
        global_upper_bound_improvement_fraction=(
            improvement / reference.strict_global_upper_bound_mwh
        ),
        global_upper_bound_improved=improvement > KNOWN_WITNESS_TOLERANCE_MWH,
        exact_global_maximum=exact,
        global_dual_is_valid_l1_upper_bound=result.bound_certificate_complete,
    )


def write_probe(probe: D31GlobalProbe, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(probe), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _window(window_id: str) -> E0D17WindowSpec:
    return next(item for item in DEFAULT_WINDOWS if item.window_id == window_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run E0-D-31 intertemporal OBBT.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    screen_parser = subparsers.add_parser("screen")
    probe_parser = subparsers.add_parser("probe")
    for child in (screen_parser, probe_parser):
        child.add_argument("--heat", required=True, type=Path)
        child.add_argument("--vre", required=True, type=Path)
        child.add_argument("--d19-source-dir", required=True, type=Path)
        child.add_argument("--d22-source-dir", required=True, type=Path)
        child.add_argument("--d30-source-dir", required=True, type=Path)
        child.add_argument(
            "--window",
            required=True,
            choices=tuple(item.window_id for item in DEFAULT_WINDOWS),
        )
        child.add_argument("--output", required=True, type=Path)
    screen_parser.add_argument("--workers", required=True, type=int)
    probe_parser.add_argument("--screen", required=True, type=Path)
    probe_parser.add_argument("--time-limit", required=True, type=float)
    probe_parser.add_argument("--threads", required=True, type=int)
    probe_parser.add_argument("--tee", action="store_true")
    args = parser.parse_args(argv)
    window = _window(args.window)
    if args.command == "screen":
        result = run_intertemporal_obbt_screen(
            args.heat,
            args.vre,
            d19_source_dir=args.d19_source_dir,
            d22_source_dir=args.d22_source_dir,
            d30_source_dir=args.d30_source_dir,
            window=window,
            workers=args.workers,
        )
        print(write_screen(result, args.output))
    else:
        result = run_intertemporal_obbt_probe(
            args.heat,
            args.vre,
            d19_source_dir=args.d19_source_dir,
            d22_source_dir=args.d22_source_dir,
            d30_source_dir=args.d30_source_dir,
            screen_path=args.screen,
            window=window,
            time_limit_seconds=args.time_limit,
            threads=args.threads,
            tee=args.tee,
        )
        print(write_probe(result, args.output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
