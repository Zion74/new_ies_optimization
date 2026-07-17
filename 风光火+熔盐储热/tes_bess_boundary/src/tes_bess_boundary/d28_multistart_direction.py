"""Deterministic multi-start support directions for the open 336 h L1 maximum.

E0-D-28 deliberately does not construct a global L1 upper bound.  It starts the
fixed-support iteration from sign vectors that differ from the D19-selected
trajectory.  Every returned dispatch is a globally feasible L1 witness, whereas
the solver dual bounds only the corresponding fixed support direction.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import Enum
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
    _fix_integer_pattern,
    _normalize_admissibility_constraints,
    _strict_solve,
    _window_mip_gap,
)
from tes_bess_boundary.d27_direction_generation import (
    D27DirectionIteration,
    _configure_support_objective,
    _encode_sign_pattern,
    _normalized_residual_audit,
    _seed_joint_from_joint,
    _sign_pattern_from_model,
    _validate_signs,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.model import AnnualPCCExportServiceSpec, E0CCase
from tes_bess_boundary.solver import create_highs_solver


D28_MULTISTART_SCHEMA = "tes_bess_boundary.e0d28_multistart_direction.probe.v1"


class SignSeedStrategy(str, Enum):
    NEGATED = "negated"
    CYCLIC_SHIFT = "cyclic_shift"
    ALTERNATING = "alternating"


@dataclass(frozen=True)
class D28MultiStartProbe:
    schema: str
    window_id: str
    hours: int
    seed_strategy: str
    shift_periods: int
    threads: int
    time_limit_seconds_per_iteration: float
    requested_iterations: int
    completed_iterations: int
    selected_face_l1_mwh: float
    base_sign_pattern: str
    seed_sign_pattern: str
    seed_positive_sign_count: int
    initial_seed_support_witness_mwh: float
    best_feasible_l1_redistribution_mwh: float
    improvement_over_selected_face_mwh: float
    final_sign_pattern: str
    fixed_point_reached: bool
    iterations: tuple[D27DirectionIteration, ...]
    support_dual_is_global_l1_upper_bound: bool = False
    global_l1_bound_generated: bool = False
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def transform_sign_seed(
    base_signs: Sequence[int],
    strategy: SignSeedStrategy | str,
    *,
    shift_periods: int = 0,
) -> tuple[int, ...]:
    """Create a deterministic sign seed distinct from trajectory following."""

    if len(base_signs) == 0:
        raise ValueError("D28 base sign pattern must not be empty")
    base = _validate_signs(base_signs, len(base_signs))
    try:
        selected = SignSeedStrategy(strategy)
    except ValueError as exc:
        raise ValueError(f"unsupported D28 sign strategy: {strategy}") from exc
    if type(shift_periods) is not int:
        raise ValueError("shift_periods must be an integer")
    if selected is SignSeedStrategy.NEGATED:
        return tuple(-sign for sign in base)
    if selected is SignSeedStrategy.CYCLIC_SHIFT:
        offset = shift_periods % len(base)
        if offset == 0:
            raise ValueError("cyclic shift must differ from the base sign pattern")
        return tuple(base[(index - offset) % len(base)] for index in range(len(base)))
    return tuple(
        1 if (index + shift_periods) % 2 == 0 else -1
        for index in range(len(base))
    )


def support_value_from_deltas(
    deltas_mw: Sequence[float],
    signs: Sequence[int],
    annual_weights: Sequence[float],
    *,
    dt_hours: float,
) -> float:
    """Evaluate one fixed support direction, allowing a negative witness."""

    period_count = len(deltas_mw)
    pattern = _validate_signs(signs, period_count)
    if len(annual_weights) != period_count:
        raise ValueError("support weights do not match the sign horizon")
    if not math.isfinite(dt_hours) or dt_hours <= 0.0:
        raise ValueError("support dt_hours must be finite and positive")
    values = tuple(float(delta) for delta in deltas_mw)
    weights = tuple(float(weight) for weight in annual_weights)
    if any(not math.isfinite(value) for value in (*values, *weights)):
        raise ValueError("support inputs must be finite")
    return 0.5 * dt_hours * sum(
        weight * sign * delta
        for weight, sign, delta in zip(weights, pattern, values)
    )


def _loaded_support_value(
    model: object,
    signs: Sequence[int],
    *,
    annual_weights: Sequence[float],
    dt_hours: float,
) -> float:
    from pyomo.environ import value

    periods = tuple(model.redistribution_periods)
    return support_value_from_deltas(
        tuple(float(value(model.delta_pcc_export_mw[period])) for period in periods),
        signs,
        tuple(annual_weights[period] for period in periods),
        dt_hours=dt_hours,
    )


def _solve_seed_support_direction(
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
    random_seed: int,
    time_limit_seconds: float,
    threads: int,
    tee: bool,
) -> D27DirectionIteration:
    from pyomo.environ import value
    import highspy

    if not math.isfinite(support_witness_mwh):
        raise ValueError("D28 support witness must be finite")
    highspy.Highs.resetGlobalScheduler(True)
    solver = create_highs_solver(
        threads=threads,
        random_seed=random_seed,
        mip_rel_gap=_window_mip_gap(
            next(
                window
                for window in DEFAULT_WINDOWS
                if window.hours == comparator_case.timeseries.period_count
            )
        ),
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
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
        termination = getattr(raw_termination, "name", str(raw_termination)).lower()
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
        weights[period] * abs(float(value(model.delta_pcc_export_mw[period])))
        for period in periods
    )
    scale = max(abs(primal), abs(loaded_support), 1.0)
    if abs(primal - loaded_support) > 1e-6 * scale:
        raise RuntimeError("D28 loaded support incumbent differs from primal")
    if loaded_support + KNOWN_WITNESS_TOLERANCE_MWH < support_witness_mwh:
        raise RuntimeError("D28 support solve is worse than its seed witness")
    if feasible_l1 + KNOWN_WITNESS_TOLERANCE_MWH < loaded_support:
        raise RuntimeError("D28 support objective exceeds recomputed feasible L1")
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
        raise RuntimeError("D28 support incumbent violates strict feasibility")
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


def run_multistart_direction(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    window: E0D17WindowSpec,
    seed_strategy: SignSeedStrategy | str,
    shift_periods: int,
    iterations: int,
    time_limit_seconds_per_iteration: float,
    threads: int,
    tee: bool = False,
) -> D28MultiStartProbe:
    """Run one transformed sign seed without producing a global L1 dual."""

    if type(iterations) is not int or iterations <= 0:
        raise ValueError("D28 iterations must be a positive integer")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D28 threads must be a positive integer")
    if (
        not math.isfinite(time_limit_seconds_per_iteration)
        or time_limit_seconds_per_iteration <= 0.0
    ):
        raise ValueError("D28 time limit must be finite and positive")
    selected_strategy = SignSeedStrategy(seed_strategy)

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    if window.window_id not in d19_rows:
        raise ValueError(f"D28 window is absent from D19: {window.window_id}")
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
    base_signs = _sign_pattern_from_model(face_model)
    signs = transform_sign_seed(
        base_signs,
        selected_strategy,
        shift_periods=shift_periods,
    )
    seed_signs = signs
    source_model = face_model
    selected_face_l1 = face_result.auxiliary_objective_mwh
    best_l1 = selected_face_l1
    records: list[D27DirectionIteration] = []
    initial_support_witness: float | None = None

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
        witness = _loaded_support_value(
            model,
            signs,
            annual_weights=comparator_case.economics.horizon.period_weights,
            dt_hours=comparator_case.timeseries.dt_hours,
        )
        if initial_support_witness is None:
            initial_support_witness = witness
        record = _solve_seed_support_direction(
            model,
            input_signs=signs,
            support_witness_mwh=witness,
            comparator_case=comparator_case,
            candidate_case=candidate_case,
            comparator_cap=comparator_cap,
            candidate_cap=candidate_cap,
            pcc_service=service,
            iteration=iteration,
            random_seed=(17 * list(SignSeedStrategy).index(selected_strategy) + iteration),
            time_limit_seconds=time_limit_seconds_per_iteration,
            threads=threads,
            tee=tee,
        )
        records.append(record)
        best_l1 = max(best_l1, record.feasible_l1_redistribution_mwh)
        signs = tuple(
            1 if char == "+" else -1 for char in record.output_sign_pattern
        )
        source_model = model
        if record.sign_pattern_stable:
            break

    assert initial_support_witness is not None
    return D28MultiStartProbe(
        schema=D28_MULTISTART_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        seed_strategy=selected_strategy.value,
        shift_periods=shift_periods,
        threads=threads,
        time_limit_seconds_per_iteration=time_limit_seconds_per_iteration,
        requested_iterations=iterations,
        completed_iterations=len(records),
        selected_face_l1_mwh=selected_face_l1,
        base_sign_pattern=_encode_sign_pattern(base_signs),
        seed_sign_pattern=_encode_sign_pattern(seed_signs),
        seed_positive_sign_count=sum(sign > 0 for sign in seed_signs),
        initial_seed_support_witness_mwh=initial_support_witness,
        best_feasible_l1_redistribution_mwh=best_l1,
        improvement_over_selected_face_mwh=best_l1 - selected_face_l1,
        final_sign_pattern=_encode_sign_pattern(signs),
        fixed_point_reached=bool(records and records[-1].sign_pattern_stable),
        iterations=tuple(records),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one E0-D-28 transformed support-direction seed."
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
    parser.add_argument(
        "--seed-strategy",
        required=True,
        choices=tuple(strategy.value for strategy in SignSeedStrategy),
    )
    parser.add_argument("--shift-periods", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--time-limit-seconds", type=float, default=1800.0)
    parser.add_argument("--threads", type=int, default=28)
    parser.add_argument("--tee", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    selected_window = next(
        window for window in DEFAULT_WINDOWS if window.window_id == args.window
    )
    result = run_multistart_direction(
        args.heat_path,
        args.vre_path,
        d19_source_dir=args.d19_source_dir,
        d22_source_dir=args.d22_source_dir,
        window=selected_window,
        seed_strategy=args.seed_strategy,
        shift_periods=args.shift_periods,
        iterations=args.iterations,
        time_limit_seconds_per_iteration=args.time_limit_seconds,
        threads=args.threads,
        tee=args.tee,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        asdict(result), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
