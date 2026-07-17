"""Direction-generation search for the open E0-D-26 336 h L1 envelope.

For a fixed sign vector ``s`` the support objective

    0.5 * sum_t w_t * dt * s_t * delta_t

is linear and no larger than the L1 redistribution at the same dispatch.
Solving this MILP with all primary integer patterns reopened therefore gives
a valid feasible L1 witness while removing the auxiliary sign binaries from
the optimization.  Its dual bounds only that fixed support direction; it is
never reported as a global upper bound on the L1 envelope.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    DispatchAdmissibility,
    RedistributionDirection,
    _seed_joint_model,
    _solve_d19_selected_model,
    build_joint_redistribution_model,
    legacy_primal_dual_bounds,
    load_e0d23_source_rows,
)
from tes_bess_boundary.d26_numerical_certification import (
    KNOWN_WITNESS_TOLERANCE_MWH,
    STRICT_FEASIBILITY_TOLERANCE,
    IntegerScope,
    _build_cases,
    _copy_joint_block_values,
    _fix_integer_pattern,
    _normalize_admissibility_constraints,
    _strict_solve,
    _window_mip_gap,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.model import AnnualPCCExportServiceSpec, E0CCase
from tes_bess_boundary.solver import create_highs_solver


D27_DIRECTION_SCHEMA = (
    "tes_bess_boundary.e0d27_direction_generation.probe.v1"
)
ZERO_SIGN_TOLERANCE_MW = 1e-9


@dataclass(frozen=True)
class D27DirectionIteration:
    iteration: int
    termination: str
    runtime_seconds: float
    input_positive_sign_count: int
    output_positive_sign_count: int
    sign_change_count: int
    sign_pattern_stable: bool
    support_witness_mwh: float
    support_primal_mwh: float
    support_dual_mwh: float | None
    support_relative_gap: float | None
    support_bound_certificate_complete: bool
    feasible_l1_redistribution_mwh: float
    l1_minus_support_mwh: float
    maximum_positive_normalized_constraint_residual: float
    comparator_pcc_service_residual_mwh: float
    candidate_pcc_service_residual_mwh: float
    common_pcc_difference_mwh: float
    output_sign_pattern: str


@dataclass(frozen=True)
class D27DisaggregatedGlobalResult:
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    dual_bound_mwh: float | None
    relative_gap: float | None
    bound_certificate_complete: bool
    warm_start_witness_mwh: float
    witness_dominance_passed: bool
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    primary_integer_patterns_reopened: bool
    sign_formulation: str
    dual_is_global_l1_upper_bound: bool


@dataclass(frozen=True)
class D27DirectionProbe:
    schema: str
    window_id: str
    hours: int
    threads: int
    time_limit_seconds_per_iteration: float
    requested_iterations: int
    completed_iterations: int
    selected_face_witness_mwh: float
    selected_face_termination: str
    selected_face_bound_certificate_complete: bool
    initial_sign_pattern: str
    best_feasible_l1_redistribution_mwh: float
    final_sign_pattern: str
    fixed_point_reached: bool
    iterations: tuple[D27DirectionIteration, ...]
    disaggregated_global: D27DisaggregatedGlobalResult | None
    support_dual_is_global_l1_upper_bound: bool = False
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _validate_signs(signs: Sequence[int], period_count: int) -> tuple[int, ...]:
    pattern = tuple(signs)
    if len(pattern) != period_count:
        raise ValueError("support sign pattern length does not match the horizon")
    if any(sign not in (-1, 1) for sign in pattern):
        raise ValueError("support signs must all be -1 or +1")
    return pattern


def _encode_sign_pattern(signs: Sequence[int]) -> str:
    return "".join("+" if sign > 0 else "-" for sign in signs)


def _sign_pattern_from_model(
    model: object,
    *,
    fallback: Sequence[int] | None = None,
    zero_tolerance_mw: float = ZERO_SIGN_TOLERANCE_MW,
) -> tuple[int, ...]:
    from pyomo.environ import value

    if not math.isfinite(zero_tolerance_mw) or zero_tolerance_mw < 0.0:
        raise ValueError("zero sign tolerance must be finite and non-negative")
    period_count = len(model.redistribution_periods)
    fallback_pattern = (
        None if fallback is None else _validate_signs(fallback, period_count)
    )
    signs: list[int] = []
    for offset, period in enumerate(model.redistribution_periods):
        delta = float(value(model.delta_pcc_export_mw[period]))
        if abs(delta) <= zero_tolerance_mw and fallback_pattern is not None:
            signs.append(fallback_pattern[offset])
        else:
            signs.append(1 if delta >= 0.0 else -1)
    return tuple(signs)


def _seed_joint_from_joint(source: object, target: object) -> None:
    from pyomo.environ import value

    _copy_joint_block_values(source.comparator, target.comparator)
    _copy_joint_block_values(source.candidate, target.candidate)
    for period in target.redistribution_periods:
        delta = float(value(target.delta_pcc_export_mw[period]))
        target.absolute_delta_pcc_export_mw[period].set_value(abs(delta))
        if hasattr(target, "delta_nonnegative"):
            target.delta_nonnegative[period].set_value(1 if delta >= 0.0 else 0)


def _configure_support_objective(
    model: object,
    signs: Sequence[int],
    *,
    annual_weights: Sequence[float],
    dt_hours: float,
) -> tuple[int, ...]:
    """Replace the exact L1 objective by one fixed linear support direction."""

    from pyomo.environ import Objective, Reals, maximize

    periods = tuple(model.redistribution_periods)
    pattern = _validate_signs(signs, len(periods))
    weights = tuple(float(weight) for weight in annual_weights)
    if len(weights) != len(periods):
        raise ValueError("support weights do not match the horizon")
    if any(not math.isfinite(weight) or weight <= 0.0 for weight in weights):
        raise ValueError("support weights must be finite and positive")
    if not math.isfinite(dt_hours) or dt_hours <= 0.0:
        raise ValueError("support dt_hours must be finite and positive")

    model.redistribution_objective.deactivate()
    model.absolute_delta_lower_positive.deactivate()
    model.absolute_delta_lower_negative.deactivate()
    if hasattr(model, "absolute_delta_upper_positive"):
        model.absolute_delta_upper_positive.deactivate()
        model.absolute_delta_upper_negative.deactivate()
    for period in periods:
        model.absolute_delta_pcc_export_mw[period].fix(0.0)
        if hasattr(model, "delta_nonnegative"):
            model.delta_nonnegative[period].fix(0.0)
            model.delta_nonnegative[period].domain = Reals
    model.d27_support_objective = Objective(
        expr=0.5
        * dt_hours
        * sum(
            weights[offset]
            * pattern[offset]
            * model.delta_pcc_export_mw[period]
            for offset, period in enumerate(periods)
        ),
        sense=maximize,
    )
    return pattern


def _replace_big_m_with_disaggregated_sign_formulation(
    model: object,
    *,
    pcc_capacity_mw: float,
) -> None:
    """Install an exact, tighter positive/negative L1 formulation.

    The D23 formulation is algebraically exact, but its two ``2M`` upper
    rows produced a small 24 h numerical contradiction between a claimed
    global upper bound and a separately feasible support-direction point.
    This disaggregation uses ``M`` once on each non-negative part and retains
    the same single sign binary per period.
    """

    from pyomo.environ import Constraint, NonNegativeReals, Var, value

    if not math.isfinite(pcc_capacity_mw) or pcc_capacity_mw <= 0.0:
        raise ValueError("PCC capacity must be finite and positive")
    if not hasattr(model, "delta_nonnegative"):
        raise ValueError("disaggregated maximum requires sign binaries")
    model.absolute_delta_lower_positive.deactivate()
    model.absolute_delta_lower_negative.deactivate()
    model.absolute_delta_upper_positive.deactivate()
    model.absolute_delta_upper_negative.deactivate()
    model.d27_delta_positive_mw = Var(
        model.redistribution_periods,
        domain=NonNegativeReals,
        bounds=(0.0, pcc_capacity_mw),
    )
    model.d27_delta_negative_mw = Var(
        model.redistribution_periods,
        domain=NonNegativeReals,
        bounds=(0.0, pcc_capacity_mw),
    )
    model.d27_delta_decomposition = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.delta_pcc_export_mw[period]
            == block.d27_delta_positive_mw[period]
            - block.d27_delta_negative_mw[period]
        ),
    )
    model.d27_absolute_delta_identity = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.absolute_delta_pcc_export_mw[period]
            == block.d27_delta_positive_mw[period]
            + block.d27_delta_negative_mw[period]
        ),
    )
    model.d27_positive_sign_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_positive_mw[period]
            <= pcc_capacity_mw * block.delta_nonnegative[period]
        ),
    )
    model.d27_negative_sign_limit = Constraint(
        model.redistribution_periods,
        rule=lambda block, period: (
            block.d27_delta_negative_mw[period]
            <= pcc_capacity_mw * (1.0 - block.delta_nonnegative[period])
        ),
    )
    for period in model.redistribution_periods:
        incumbent = value(
            model.delta_pcc_export_mw[period], exception=False
        )
        delta = 0.0 if incumbent is None else float(incumbent)
        model.d27_delta_positive_mw[period].set_value(max(delta, 0.0))
        model.d27_delta_negative_mw[period].set_value(max(-delta, 0.0))
        model.absolute_delta_pcc_export_mw[period].set_value(abs(delta))
        model.delta_nonnegative[period].set_value(1 if delta >= 0.0 else 0)


def _normalized_residual_audit(
    model: object,
    *,
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    comparator_cap: DispatchAdmissibility,
    candidate_cap: DispatchAdmissibility,
    pcc_service: AnnualPCCExportServiceSpec,
) -> tuple[float, float, float, float]:
    from pyomo.environ import value

    comparator_cost_residual = float(
        value(model.comparator.annual_total_cost_cny)
    ) - comparator_cap.primary_cost_upper_bound_cny
    candidate_cost_residual = float(
        value(model.candidate.annual_total_cost_cny)
    ) - candidate_cap.primary_cost_upper_bound_cny
    comparator_curtailment_residual = float(
        value(model.comparator.annual_curtailment_mwh)
    ) - comparator_cap.curtailment_upper_bound_mwh
    candidate_curtailment_residual = float(
        value(model.candidate.annual_curtailment_mwh)
    ) - candidate_cap.curtailment_upper_bound_mwh
    comparator_export = float(value(model.comparator.annual_pcc_export_mwh))
    candidate_export = float(value(model.candidate.annual_pcc_export_mwh))
    comparator_service_residual = (
        comparator_export - pcc_service.target_export_mwh
    )
    candidate_service_residual = candidate_export - pcc_service.target_export_mwh
    weighted_hours = comparator_case.timeseries.dt_hours * sum(
        comparator_case.economics.horizon.period_weights
    )
    if candidate_case.timeseries.period_count != (
        comparator_case.timeseries.period_count
    ):
        raise ValueError("D27 audit cases have different horizons")
    residuals = (
        comparator_cost_residual
        / max(1.0, comparator_cap.primary_cost_upper_bound_cny),
        candidate_cost_residual
        / max(1.0, candidate_cap.primary_cost_upper_bound_cny),
        comparator_curtailment_residual
        / max(1.0, comparator_cap.curtailment_upper_bound_mwh),
        candidate_curtailment_residual
        / max(1.0, candidate_cap.curtailment_upper_bound_mwh),
        abs(comparator_service_residual) / weighted_hours,
        abs(candidate_service_residual) / weighted_hours,
    )
    return (
        max(0.0, *residuals),
        comparator_service_residual,
        candidate_service_residual,
        candidate_export - comparator_export,
    )


def _solve_support_direction(
    model: object,
    *,
    input_signs: Sequence[int],
    support_witness_mwh: float,
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    comparator_cap: DispatchAdmissibility,
    candidate_cap: DispatchAdmissibility,
    pcc_service: AnnualPCCExportServiceSpec,
    iteration: int,
    time_limit_seconds: float,
    threads: int,
    tee: bool,
) -> D27DirectionIteration:
    from pyomo.environ import value
    import highspy

    if not math.isfinite(support_witness_mwh) or support_witness_mwh < 0.0:
        raise ValueError("support witness must be finite and non-negative")
    highspy.Highs.resetGlobalScheduler(True)
    solver = create_highs_solver(
        threads=threads,
        random_seed=iteration,
        mip_rel_gap=_window_mip_gap(
            next(
                window
                for window in DEFAULT_WINDOWS
                if window.hours == comparator_case.timeseries.period_count
            )
        ),
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = (
        STRICT_FEASIBILITY_TOLERANCE
    )
    solver.options["dual_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    solver.options["mip_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    started = perf_counter()
    try:
        results = solver.solve(
            model,
            tee=tee,
            load_solutions=False,
            warmstart=True,
        )
        runtime_seconds = perf_counter() - started
        raw_termination = results.solver.termination_condition
        termination = getattr(
            raw_termination, "name", str(raw_termination)
        ).lower()
        primal, dual = legacy_primal_dual_bounds(
            results, RedistributionDirection.MAXIMUM
        )
        if len(results.solution) > 0:
            model.solutions.load_from(results)
        else:
            solver.load_vars()
        loaded_support = float(value(model.d27_support_objective))
        if primal is None:
            primal = loaded_support
    finally:
        highspy.Highs.resetGlobalScheduler(True)

    periods = tuple(model.redistribution_periods)
    weights = comparator_case.economics.horizon.period_weights
    dt_hours = comparator_case.timeseries.dt_hours
    feasible_l1 = 0.5 * dt_hours * sum(
        weights[period]
        * abs(float(value(model.delta_pcc_export_mw[period])))
        for period in periods
    )
    scale = max(abs(primal), abs(loaded_support), 1.0)
    if abs(primal - loaded_support) > 1e-6 * scale:
        raise RuntimeError("D27 loaded support incumbent differs from primal")
    if loaded_support + KNOWN_WITNESS_TOLERANCE_MWH < support_witness_mwh:
        raise RuntimeError("D27 support solve is worse than its feasible witness")
    if feasible_l1 + KNOWN_WITNESS_TOLERANCE_MWH < loaded_support:
        raise RuntimeError("D27 support objective exceeds recomputed feasible L1")
    residual, comparator_service, candidate_service, common_difference = (
        _normalized_residual_audit(
            model,
            comparator_case=comparator_case,
            candidate_case=candidate_case,
            comparator_cap=comparator_cap,
            candidate_cap=candidate_cap,
            pcc_service=pcc_service,
        )
    )
    if residual > STRICT_FEASIBILITY_TOLERANCE:
        raise RuntimeError("D27 support incumbent violates strict feasibility")
    output_signs = _sign_pattern_from_model(model, fallback=input_signs)
    input_pattern = tuple(input_signs)
    sign_changes = sum(
        before != after for before, after in zip(input_pattern, output_signs)
    )
    relative_gap = (
        None
        if dual is None
        else abs(primal - dual) / max(abs(primal), 1e-12)
    )
    return D27DirectionIteration(
        iteration=iteration,
        termination=termination,
        runtime_seconds=runtime_seconds,
        input_positive_sign_count=sum(sign > 0 for sign in input_pattern),
        output_positive_sign_count=sum(sign > 0 for sign in output_signs),
        sign_change_count=sign_changes,
        sign_pattern_stable=sign_changes == 0,
        support_witness_mwh=support_witness_mwh,
        support_primal_mwh=primal,
        support_dual_mwh=dual,
        support_relative_gap=relative_gap,
        support_bound_certificate_complete=dual is not None,
        feasible_l1_redistribution_mwh=feasible_l1,
        l1_minus_support_mwh=feasible_l1 - loaded_support,
        maximum_positive_normalized_constraint_residual=residual,
        comparator_pcc_service_residual_mwh=comparator_service,
        candidate_pcc_service_residual_mwh=candidate_service,
        common_pcc_difference_mwh=common_difference,
        output_sign_pattern=_encode_sign_pattern(output_signs),
    )


def run_direction_generation(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    window: E0D17WindowSpec,
    iterations: int,
    time_limit_seconds_per_iteration: float,
    global_time_limit_seconds: float | None,
    threads: int,
    tee: bool = False,
) -> D27DirectionProbe:
    """Run fixed-support direction generation from the D19 selected face."""

    if type(iterations) is not int or iterations < 0:
        raise ValueError("iterations must be a non-negative integer")
    if type(threads) is not int or threads <= 0:
        raise ValueError("threads must be a positive integer")
    if (
        not math.isfinite(time_limit_seconds_per_iteration)
        or time_limit_seconds_per_iteration <= 0.0
    ):
        raise ValueError("iteration time limit must be finite and positive")
    if global_time_limit_seconds is not None and (
        not math.isfinite(global_time_limit_seconds)
        or global_time_limit_seconds <= 0.0
    ):
        raise ValueError("global time limit must be finite and positive")

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    if window.window_id not in d19_rows:
        raise ValueError(f"D27 window is absent from D19: {window.window_id}")
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
        time_limit_seconds=min(300.0, time_limit_seconds_per_iteration),
        threads=threads,
        tee=tee,
        allow_incumbent_only=True,
    )
    signs = _sign_pattern_from_model(face_model)
    initial_signs = signs
    witness = face_result.auxiliary_objective_mwh
    source_model = face_model
    records: list[D27DirectionIteration] = []
    best_l1 = witness
    best_model = face_model

    for iteration in range(1, iterations + 1):
        model = build_joint_redistribution_model(
            comparator_case,
            candidate_case,
            comparator_admissibility=comparator_cap,
            candidate_admissibility=candidate_cap,
            direction=RedistributionDirection.MAXIMUM,
        )
        _seed_joint_from_joint(source_model, model)
        _normalize_admissibility_constraints(
            model,
            comparator_case=comparator_case,
            candidate_case=candidate_case,
            comparator_cap=comparator_cap,
            candidate_cap=candidate_cap,
        )
        _configure_support_objective(
            model,
            signs,
            annual_weights=comparator_case.economics.horizon.period_weights,
            dt_hours=comparator_case.timeseries.dt_hours,
        )
        record = _solve_support_direction(
            model,
            input_signs=signs,
            support_witness_mwh=witness,
            comparator_case=comparator_case,
            candidate_case=candidate_case,
            comparator_cap=comparator_cap,
            candidate_cap=candidate_cap,
            pcc_service=service,
            iteration=iteration,
            time_limit_seconds=time_limit_seconds_per_iteration,
            threads=threads,
            tee=tee,
        )
        records.append(record)
        if (
            record.feasible_l1_redistribution_mwh
            >= best_l1 - KNOWN_WITNESS_TOLERANCE_MWH
        ):
            best_l1 = max(best_l1, record.feasible_l1_redistribution_mwh)
            best_model = model
        new_signs = tuple(1 if char == "+" else -1 for char in record.output_sign_pattern)
        source_model = model
        witness = record.feasible_l1_redistribution_mwh
        signs = new_signs
        if record.sign_pattern_stable:
            break

    global_certificate: D27DisaggregatedGlobalResult | None = None
    if global_time_limit_seconds is not None:
        global_witness = best_l1
        global_model = build_joint_redistribution_model(
            comparator_case,
            candidate_case,
            comparator_admissibility=comparator_cap,
            candidate_admissibility=candidate_cap,
            direction=RedistributionDirection.MAXIMUM,
        )
        _seed_joint_from_joint(best_model, global_model)
        _replace_big_m_with_disaggregated_sign_formulation(
            global_model,
            pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        )
        global_result = _strict_solve(
            global_model,
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
            time_limit_seconds=global_time_limit_seconds,
            threads=threads,
            tee=tee,
            conditional_face_warm_start_mwh=global_witness,
            conditional_face_warm_start_runtime_seconds=sum(
                record.runtime_seconds for record in records
            ),
            conditional_face_warm_start_termination="d27_support_direction",
            conditional_face_fixed_primary_integer_count=0,
            allow_incumbent_only=True,
        )
        if (
            global_result.maximum_positive_normalized_constraint_residual
            > STRICT_FEASIBILITY_TOLERANCE
        ):
            raise RuntimeError("D27 global incumbent violates strict feasibility")
        if abs(global_result.auxiliary_objective_mismatch_mwh) > 1e-6:
            raise RuntimeError("D27 global incumbent failed L1 recomputation")
        best_l1 = max(best_l1, global_result.primal_bound_mwh)
        global_certificate = D27DisaggregatedGlobalResult(
            termination=global_result.termination,
            runtime_seconds=global_result.runtime_seconds,
            primal_bound_mwh=global_result.primal_bound_mwh,
            dual_bound_mwh=global_result.dual_bound_mwh,
            relative_gap=global_result.relative_gap,
            bound_certificate_complete=(
                global_result.bound_certificate_complete
            ),
            warm_start_witness_mwh=global_witness,
            witness_dominance_passed=(
                global_result.primal_bound_mwh
                + KNOWN_WITNESS_TOLERANCE_MWH
                >= global_witness
            ),
            maximum_positive_normalized_constraint_residual=(
                global_result.maximum_positive_normalized_constraint_residual
            ),
            auxiliary_objective_mismatch_mwh=(
                global_result.auxiliary_objective_mismatch_mwh
            ),
            primary_integer_patterns_reopened=True,
            sign_formulation="positive_negative_disaggregation_single_binary",
            dual_is_global_l1_upper_bound=(
                global_result.bound_certificate_complete
            ),
        )

    return D27DirectionProbe(
        schema=D27_DIRECTION_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        threads=threads,
        time_limit_seconds_per_iteration=time_limit_seconds_per_iteration,
        requested_iterations=iterations,
        completed_iterations=len(records),
        selected_face_witness_mwh=face_result.auxiliary_objective_mwh,
        selected_face_termination=face_result.termination,
        selected_face_bound_certificate_complete=(
            face_result.bound_certificate_complete
        ),
        initial_sign_pattern=_encode_sign_pattern(initial_signs),
        best_feasible_l1_redistribution_mwh=best_l1,
        final_sign_pattern=_encode_sign_pattern(signs),
        fixed_point_reached=bool(records and records[-1].sign_pattern_stable),
        iterations=tuple(records),
        disaggregated_global=global_certificate,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run E0-D-27 fixed-support direction generation."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--d22-source-dir", required=True, type=Path)
    parser.add_argument(
        "--window",
        required=True,
        choices=tuple(window.window_id for window in DEFAULT_WINDOWS),
    )
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--time-limit-seconds", type=float, required=True)
    parser.add_argument("--global-time-limit-seconds", type=float)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--tee", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    window = next(
        item for item in DEFAULT_WINDOWS if item.window_id == args.window
    )
    result = run_direction_generation(
        args.heat_path,
        args.vre_path,
        d19_source_dir=args.d19_source_dir,
        d22_source_dir=args.d22_source_dir,
        window=window,
        iterations=args.iterations,
        time_limit_seconds_per_iteration=args.time_limit_seconds,
        global_time_limit_seconds=args.global_time_limit_seconds,
        threads=args.threads,
        tee=args.tee,
    )
    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8", newline="\n")
    print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
