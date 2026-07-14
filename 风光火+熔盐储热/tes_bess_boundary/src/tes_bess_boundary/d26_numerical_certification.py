"""Strict-tolerance D26 probe for the D23 PCC exposure envelope.

This module separates two sources of alternate-dispatch uncertainty:

* the complete D23 admissible set with all primary integer patterns reopened;
* the continuous dispatch face conditional on the D19-selected integer pattern.

It is intentionally price agnostic and cannot certify formal TAC or E1.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Sequence

from tes_bess_boundary.alternative_dispatch_envelope import (
    DispatchAdmissibility,
    RedistributionDirection,
    _d19_admissibility,
    _float_field,
    _seed_joint_model,
    _solve_d19_selected_model,
    build_joint_redistribution_model,
    legacy_primal_dual_bounds,
    load_e0d23_source_rows,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _base_case,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.e0d18_performance import (
    EXACT_PRIMARY_MIP_GAP,
    FORTNIGHT_PRIMARY_MIP_GAP,
    _tight_case,
)
from tes_bess_boundary.model import (
    AnnualCurtailmentServiceSpec,
    AnnualPCCExportServiceSpec,
    Architecture,
    E0CCase,
)
from tes_bess_boundary.solver import create_highs_solver


D26_PROBE_SCHEMA = "tes_bess_boundary.e0d26_numerical_certification.probe.v1"
STRICT_FEASIBILITY_TOLERANCE = 1e-9
KNOWN_WITNESS_TOLERANCE_MWH = 1e-6


class IntegerScope(str, Enum):
    """Integer-pattern scope of one numerical certification solve."""

    REOPENED = "reopened"
    D19_SELECTED_FACE = "d19_selected_face"


@dataclass(frozen=True)
class D26ProbeResult:
    schema: str
    window_id: str
    hours: int
    scope: IntegerScope
    direction: RedistributionDirection
    termination: str
    runtime_seconds: float
    warm_start_runtime_seconds: float
    conditional_face_warm_start_mwh: float | None
    conditional_face_warm_start_runtime_seconds: float
    conditional_face_warm_start_termination: str | None
    conditional_face_fixed_primary_integer_count: int
    threads: int
    time_limit_seconds: float
    strict_feasibility_tolerance: float
    normalized_admissibility_constraints: bool
    fixed_primary_integrality_removed: bool
    maximum_positive_normalized_constraint_residual: float
    fixed_primary_integer_count: int
    auxiliary_objective_mwh: float
    recomputed_redistribution_mwh: float
    auxiliary_objective_mismatch_mwh: float
    bound_certificate_complete: bool
    primal_bound_mwh: float
    dual_bound_mwh: float | None
    relative_gap: float | None
    comparator_cost_residual_cny: float
    candidate_cost_residual_cny: float
    comparator_curtailment_residual_mwh: float
    candidate_curtailment_residual_mwh: float
    comparator_pcc_service_residual_mwh: float
    candidate_pcc_service_residual_mwh: float
    common_pcc_difference_mwh: float
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _window_mip_gap(window: E0D17WindowSpec) -> float:
    if window.hours == 24:
        return EXACT_PRIMARY_MIP_GAP
    if window.hours == 14 * 24:
        return FORTNIGHT_PRIMARY_MIP_GAP
    raise ValueError(f"no D26 gap policy is registered for {window.window_id}")


def _build_cases(
    rows: tuple[dict[str, object], ...],
    d19_row: dict[str, str],
) -> tuple[
    E0CCase,
    E0CCase,
    DispatchAdmissibility,
    DispatchAdmissibility,
    AnnualPCCExportServiceSpec,
]:
    curtailment_service = AnnualCurtailmentServiceSpec(
        service_id=d19_row["curtailment_service_id"],
        maximum_curtailment_mwh=_float_field(
            d19_row, "service_curtailment_ceiling_mwh"
        ),
    )
    pcc_service = AnnualPCCExportServiceSpec(
        service_id=d19_row["pcc_export_service_id"],
        target_export_mwh=_float_field(d19_row, "pcc_export_target_mwh"),
    )
    comparator = replace(
        _tight_case(
            _base_case(
                rows,
                architecture=Architecture.NO_STORAGE,
                service=curtailment_service,
            )
        ),
        pcc_export_service=pcc_service,
    )
    candidate = replace(
        _tight_case(
            _base_case(
                rows,
                architecture=Architecture.TES,
                service=curtailment_service,
            )
        ),
        pcc_export_service=pcc_service,
    )
    comparator_cap, candidate_cap = _d19_admissibility(d19_row)
    return comparator, candidate, comparator_cap, candidate_cap, pcc_service


def _fix_integer_pattern(target: object, source: object) -> int:
    from pyomo.environ import Reals, Var, value

    fixed = 0
    for source_component in source.component_objects(Var, active=True):
        target_component = target.find_component(source_component.name)
        if target_component is None:
            continue
        for index in source_component:
            source_variable = source_component[index]
            if not (
                source_variable.is_binary() or source_variable.is_integer()
            ):
                continue
            incumbent = value(source_variable, exception=False)
            if incumbent is None:
                raise RuntimeError("D19 selected integer pattern contains no value")
            target_variable = target_component[index]
            target_variable.fix(round(float(incumbent)))
            # Once fixed, the integer domain contributes no remaining
            # decision.  Present it to HiGHS as a fixed continuous column to
            # avoid a 336 h presolve pathology that reports infinite bounds
            # after first recovering the correct fixed-face LP optimum.
            target_variable.domain = Reals
            fixed += 1
    if fixed == 0:
        raise RuntimeError("D26 did not find a primary integer pattern to fix")
    return fixed


def _copy_joint_block_values(source: object, target: object) -> int:
    """Copy a solved joint-model Block into its peer using relative names."""

    from pyomo.environ import Var, value

    prefix = f"{source.name}."
    copied = 0
    for source_component in source.component_objects(Var, active=True):
        if not source_component.name.startswith(prefix):
            continue
        relative_name = source_component.name[len(prefix) :]
        target_component = target.find_component(relative_name)
        if target_component is None:
            continue
        for index in source_component:
            incumbent = value(source_component[index], exception=False)
            if incumbent is None:
                continue
            target_component[index].set_value(
                float(incumbent), skip_validation=True
            )
            copied += 1
    if copied == 0:
        raise RuntimeError("D26 failed to transfer a conditional-face state")
    return copied


def _seed_from_conditional_face(target: object, source: object) -> None:
    from pyomo.environ import value

    _copy_joint_block_values(source.comparator, target.comparator)
    _copy_joint_block_values(source.candidate, target.candidate)
    for period in target.redistribution_periods:
        delta = float(value(target.delta_pcc_export_mw[period]))
        target.absolute_delta_pcc_export_mw[period].set_value(abs(delta))
        if hasattr(target, "delta_nonnegative"):
            target.delta_nonnegative[period].set_value(
                1 if delta >= 0.0 else 0
            )


def _normalize_admissibility_constraints(
    model: object,
    *,
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    comparator_cap: DispatchAdmissibility,
    candidate_cap: DispatchAdmissibility,
) -> None:
    """Replace large annual cap rows by algebraically equivalent ratios.

    The locked E0 annual cost caps are O(1e8) CNY.  An absolute HiGHS
    feasibility tolerance of 1e-9 is below the floating-point resolution of
    an unscaled row at that magnitude.  Dividing each annual admissibility
    row by a fixed positive scale preserves the feasible set while making the
    strict D26 tolerance meaningful.
    """

    from pyomo.environ import Constraint

    model.comparator_primary_cost_cap.deactivate()
    model.candidate_primary_cost_cap.deactivate()
    model.comparator_curtailment_cap.deactivate()
    model.candidate_curtailment_cap.deactivate()

    comparator_cost_scale = max(
        1.0, comparator_cap.primary_cost_upper_bound_cny
    )
    candidate_cost_scale = max(1.0, candidate_cap.primary_cost_upper_bound_cny)
    comparator_curtailment_scale = max(
        1.0, comparator_cap.curtailment_upper_bound_mwh
    )
    candidate_curtailment_scale = max(
        1.0, candidate_cap.curtailment_upper_bound_mwh
    )
    model.d26_comparator_primary_cost_cap = Constraint(
        expr=(
            model.comparator.annual_total_cost_cny / comparator_cost_scale
            <= comparator_cap.primary_cost_upper_bound_cny
            / comparator_cost_scale
        )
    )
    model.d26_candidate_primary_cost_cap = Constraint(
        expr=(
            model.candidate.annual_total_cost_cny / candidate_cost_scale
            <= candidate_cap.primary_cost_upper_bound_cny / candidate_cost_scale
        )
    )
    model.d26_comparator_curtailment_cap = Constraint(
        expr=(
            model.comparator.annual_curtailment_mwh
            / comparator_curtailment_scale
            <= comparator_cap.curtailment_upper_bound_mwh
            / comparator_curtailment_scale
        )
    )
    model.d26_candidate_curtailment_cap = Constraint(
        expr=(
            model.candidate.annual_curtailment_mwh / candidate_curtailment_scale
            <= candidate_cap.curtailment_upper_bound_mwh
            / candidate_curtailment_scale
        )
    )

    for label, block, case in (
        ("comparator", model.comparator, comparator_case),
        ("candidate", model.candidate, candidate_case),
    ):
        service = case.curtailment_service
        if service is None or not hasattr(block, "annual_curtailment_service"):
            continue
        block.annual_curtailment_service.deactivate()
        service_scale = max(1.0, service.maximum_curtailment_mwh)
        setattr(
            model,
            f"d26_{label}_service_curtailment_cap",
            Constraint(
                expr=(
                    block.annual_curtailment_mwh / service_scale
                    <= service.maximum_curtailment_mwh / service_scale
                )
            ),
        )


def _strict_solve(
    model: object,
    *,
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    comparator_cap: DispatchAdmissibility,
    candidate_cap: DispatchAdmissibility,
    pcc_service: AnnualPCCExportServiceSpec,
    window: E0D17WindowSpec,
    scope: IntegerScope,
    direction: RedistributionDirection,
    fixed_primary_integer_count: int,
    warm_start_runtime_seconds: float,
    time_limit_seconds: float,
    threads: int,
    tee: bool,
    conditional_face_warm_start_mwh: float | None = None,
    conditional_face_warm_start_runtime_seconds: float = 0.0,
    conditional_face_warm_start_termination: str | None = None,
    conditional_face_fixed_primary_integer_count: int = 0,
    allow_incumbent_only: bool = False,
) -> D26ProbeResult:
    from pyomo.environ import value
    import highspy

    _normalize_admissibility_constraints(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
    )

    # D19 reproduction initializes the process-wide HiGHS scheduler at one
    # thread. Reset it before the independently configured D26 extreme solve;
    # otherwise requesting more threads can return ``unknown`` without an
    # incumbent even for the 24 h smoke case.
    highspy.Highs.resetGlobalScheduler(True)
    solver = create_highs_solver(
        threads=threads,
        random_seed=0,
        mip_rel_gap=_window_mip_gap(window),
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = (
        STRICT_FEASIBILITY_TOLERANCE
    )
    solver.options["dual_feasibility_tolerance"] = (
        STRICT_FEASIBILITY_TOLERANCE
    )
    solver.options["mip_feasibility_tolerance"] = (
        STRICT_FEASIBILITY_TOLERANCE
    )
    started = perf_counter()
    try:
        results = solver.solve(
            model,
            tee=tee,
            load_solutions=False,
            warmstart=True,
        )
        runtime_seconds = perf_counter() - started
        termination_raw = results.solver.termination_condition
        termination = getattr(
            termination_raw, "name", str(termination_raw)
        ).lower()
        primal, dual = legacy_primal_dual_bounds(results, direction)
        if len(results.solution) > 0:
            model.solutions.load_from(results)
        else:
            try:
                solver.load_vars()
            except RuntimeError as exc:
                raise RuntimeError(
                    "D26 strict probe did not return a loadable incumbent: "
                    f"{termination}"
                ) from exc
        if primal is None:
            primal = float(value(model.redistribution_objective))
        if dual is None and not allow_incumbent_only:
            raise RuntimeError(
                "D26 strict probe did not return a finite dual bound: "
                f"{termination}"
            )
    finally:
        # HiGHS owns a process-wide scheduler.  Leaving the D26 thread count
        # installed makes later solves that request a different count return
        # ``unknown``.  The solve is complete, so release it for the caller.
        highspy.Highs.resetGlobalScheduler(True)

    if conditional_face_warm_start_mwh is not None:
        if direction is RedistributionDirection.MINIMUM:
            witness_dominated = (
                primal
                <= conditional_face_warm_start_mwh
                + KNOWN_WITNESS_TOLERANCE_MWH
            )
        else:
            witness_dominated = (
                primal
                >= conditional_face_warm_start_mwh
                - KNOWN_WITNESS_TOLERANCE_MWH
            )
        if not witness_dominated:
            raise RuntimeError(
                "D26 reopened solve is worse than its conditional-face "
                f"feasible witness: primal={primal}, "
                f"witness={conditional_face_warm_start_mwh}"
            )

    auxiliary = float(value(model.redistribution_objective))
    weights = comparator_case.economics.horizon.period_weights
    dt_hours = comparator_case.timeseries.dt_hours
    recomputed = 0.5 * dt_hours * sum(
        weights[period]
        * abs(float(value(model.delta_pcc_export_mw[period])))
        for period in model.redistribution_periods
    )
    comparator_cost = float(value(model.comparator.annual_total_cost_cny))
    candidate_cost = float(value(model.candidate.annual_total_cost_cny))
    comparator_curtailment = float(
        value(model.comparator.annual_curtailment_mwh)
    )
    candidate_curtailment = float(
        value(model.candidate.annual_curtailment_mwh)
    )
    comparator_export = float(value(model.comparator.annual_pcc_export_mwh))
    candidate_export = float(value(model.candidate.annual_pcc_export_mwh))
    comparator_cost_residual = (
        comparator_cost - comparator_cap.primary_cost_upper_bound_cny
    )
    candidate_cost_residual = (
        candidate_cost - candidate_cap.primary_cost_upper_bound_cny
    )
    comparator_curtailment_residual = (
        comparator_curtailment
        - comparator_cap.curtailment_upper_bound_mwh
    )
    candidate_curtailment_residual = (
        candidate_curtailment - candidate_cap.curtailment_upper_bound_mwh
    )
    comparator_service_residual = (
        comparator_export - pcc_service.target_export_mwh
    )
    candidate_service_residual = (
        candidate_export - pcc_service.target_export_mwh
    )
    weighted_hours = dt_hours * sum(weights)
    normalized_residuals = (
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
    maximum_positive_normalized_residual = max(
        0.0, *normalized_residuals
    )
    relative_gap = (
        None
        if dual is None
        else abs(primal - dual) / max(abs(primal), 1e-12)
    )
    return D26ProbeResult(
        schema=D26_PROBE_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        scope=scope,
        direction=direction,
        termination=termination,
        runtime_seconds=runtime_seconds,
        warm_start_runtime_seconds=warm_start_runtime_seconds,
        conditional_face_warm_start_mwh=conditional_face_warm_start_mwh,
        conditional_face_warm_start_runtime_seconds=(
            conditional_face_warm_start_runtime_seconds
        ),
        conditional_face_warm_start_termination=(
            conditional_face_warm_start_termination
        ),
        conditional_face_fixed_primary_integer_count=(
            conditional_face_fixed_primary_integer_count
        ),
        threads=threads,
        time_limit_seconds=time_limit_seconds,
        strict_feasibility_tolerance=STRICT_FEASIBILITY_TOLERANCE,
        normalized_admissibility_constraints=True,
        fixed_primary_integrality_removed=(
            scope is IntegerScope.D19_SELECTED_FACE
            and fixed_primary_integer_count > 0
        ),
        maximum_positive_normalized_constraint_residual=(
            maximum_positive_normalized_residual
        ),
        fixed_primary_integer_count=fixed_primary_integer_count,
        auxiliary_objective_mwh=auxiliary,
        recomputed_redistribution_mwh=recomputed,
        auxiliary_objective_mismatch_mwh=recomputed - auxiliary,
        bound_certificate_complete=dual is not None,
        primal_bound_mwh=primal,
        dual_bound_mwh=dual,
        relative_gap=relative_gap,
        comparator_cost_residual_cny=comparator_cost_residual,
        candidate_cost_residual_cny=candidate_cost_residual,
        comparator_curtailment_residual_mwh=comparator_curtailment_residual,
        candidate_curtailment_residual_mwh=candidate_curtailment_residual,
        comparator_pcc_service_residual_mwh=comparator_service_residual,
        candidate_pcc_service_residual_mwh=candidate_service_residual,
        common_pcc_difference_mwh=candidate_export - comparator_export,
    )


def run_probe(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    window: E0D17WindowSpec,
    scope: IntegerScope,
    direction: RedistributionDirection,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> D26ProbeResult:
    """Run one strict-tolerance D26 scope/direction probe."""

    if not isinstance(scope, IntegerScope):
        raise ValueError("scope must be an IntegerScope")
    if not isinstance(direction, RedistributionDirection):
        raise ValueError("direction must be a RedistributionDirection")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("time_limit_seconds must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("threads must be a positive integer")

    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    if window.window_id not in d19_rows:
        raise ValueError(f"D26 window is absent from D19: {window.window_id}")
    d19_row = d19_rows[window.window_id]
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    (
        comparator_case,
        candidate_case,
        comparator_cap,
        candidate_cap,
        pcc_service,
    ) = _build_cases(rows, d19_row)

    warm_started = perf_counter()
    comparator_selected = _solve_d19_selected_model(
        comparator_case,
        primary_mip_gap=EXACT_PRIMARY_MIP_GAP,
        pcc_service_feasibility_warm_start=False,
    )
    candidate_selected = _solve_d19_selected_model(
        candidate_case,
        primary_mip_gap=_window_mip_gap(window),
        pcc_service_feasibility_warm_start=window.hours > 24,
    )
    warm_runtime = perf_counter() - warm_started

    model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        direction=direction,
    )
    _seed_joint_model(model, comparator_selected, candidate_selected)
    fixed = 0
    if scope is IntegerScope.D19_SELECTED_FACE:
        fixed += _fix_integer_pattern(model.comparator, comparator_selected)
        fixed += _fix_integer_pattern(model.candidate, candidate_selected)

    conditional_face_result: D26ProbeResult | None = None
    if scope is IntegerScope.REOPENED:
        face_model = model.clone()
        face_fixed = _fix_integer_pattern(
            face_model.comparator, comparator_selected
        )
        face_fixed += _fix_integer_pattern(
            face_model.candidate, candidate_selected
        )
        conditional_face_result = _strict_solve(
            face_model,
            comparator_case=comparator_case,
            candidate_case=candidate_case,
            comparator_cap=comparator_cap,
            candidate_cap=candidate_cap,
            pcc_service=pcc_service,
            window=window,
            scope=IntegerScope.D19_SELECTED_FACE,
            direction=direction,
            fixed_primary_integer_count=face_fixed,
            warm_start_runtime_seconds=warm_runtime,
            time_limit_seconds=min(300.0, time_limit_seconds),
            threads=threads,
            tee=tee,
            allow_incumbent_only=True,
        )
        _seed_from_conditional_face(model, face_model)

    return _strict_solve(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_cap,
        candidate_cap=candidate_cap,
        pcc_service=pcc_service,
        window=window,
        scope=scope,
        direction=direction,
        fixed_primary_integer_count=fixed,
        warm_start_runtime_seconds=warm_runtime,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        tee=tee,
        conditional_face_warm_start_mwh=(
            None
            if conditional_face_result is None
            else conditional_face_result.auxiliary_objective_mwh
        ),
        conditional_face_warm_start_runtime_seconds=(
            0.0
            if conditional_face_result is None
            else conditional_face_result.runtime_seconds
        ),
        conditional_face_warm_start_termination=(
            None
            if conditional_face_result is None
            else conditional_face_result.termination
        ),
        conditional_face_fixed_primary_integer_count=(
            0
            if conditional_face_result is None
            else conditional_face_result.fixed_primary_integer_count
        ),
        allow_incumbent_only=(
            scope is IntegerScope.D19_SELECTED_FACE
            and direction is RedistributionDirection.MAXIMUM
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one strict-tolerance E0-D-26 numerical probe."
    )
    parser.add_argument("--heat-path", required=True, type=Path)
    parser.add_argument("--vre-path", required=True, type=Path)
    parser.add_argument("--d19-source-dir", required=True, type=Path)
    parser.add_argument("--d22-source-dir", required=True, type=Path)
    parser.add_argument(
        "--window",
        required=True,
        choices=tuple(item.window_id for item in DEFAULT_WINDOWS),
    )
    parser.add_argument(
        "--scope", required=True, choices=tuple(item.value for item in IntegerScope)
    )
    parser.add_argument(
        "--direction",
        required=True,
        choices=tuple(item.value for item in RedistributionDirection),
    )
    parser.add_argument("--time-limit-seconds", type=float, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--tee",
        action="store_true",
        help="stream the native HiGHS log for numerical diagnostics",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    window = next(item for item in DEFAULT_WINDOWS if item.window_id == args.window)
    result = run_probe(
        args.heat_path,
        args.vre_path,
        d19_source_dir=args.d19_source_dir,
        d22_source_dir=args.d22_source_dir,
        window=window,
        scope=IntegerScope(args.scope),
        direction=RedistributionDirection(args.direction),
        time_limit_seconds=args.time_limit_seconds,
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
