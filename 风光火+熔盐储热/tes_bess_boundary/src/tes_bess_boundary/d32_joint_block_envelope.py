"""Joint multi-period block envelopes for the open global PCC L1 problem.

E0-D-32 keeps both complete D19 architecture paths over the full horizon,
relaxes only their primary integer domains, and retains exact sign binaries
for one contiguous block at a time.  A finite maximization dual is therefore a
valid upper bound on that block's contribution for every original integer
dispatch.  Summing a partition of such bounds gives a valid global L1 upper
bound, while each block bound can also be added as a valid inequality to the
reopened global MILP.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict, dataclass, replace
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
    _replace_big_m_with_disaggregated_sign_formulation,
    _seed_joint_from_joint,
)
from tes_bess_boundary.d29_export_linked_bound_tightening import (
    D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH,
    add_export_linked_sign_cuts,
)
from tes_bess_boundary.d30_physics_service_bound_tightening import (
    add_physics_service_sign_cuts,
)
from tes_bess_boundary.d31_intertemporal_obbt import (
    _screen_bounds,
    load_d30_obbt_reference,
    load_d31_screen,
)
from tes_bess_boundary.e0d17_exploration import (
    DEFAULT_WINDOWS,
    E0D17WindowSpec,
    _window_rows,
    load_e0d17_inputs,
)
from tes_bess_boundary.model import E0CCase
from tes_bess_boundary.solver import create_highs_solver


D32_SCREEN_SCHEMA = "tes_bess_boundary.e0d32_joint_block_envelope_screen.v1"
D32_PROBE_SCHEMA = "tes_bess_boundary.e0d32_joint_block_envelope_probe.v1"
D32_BLOCK_HOURS = 24
D32_BLOCK_TIME_LIMIT_SECONDS = 300.0
D32_MATERIALITY_THRESHOLD_FRACTION = 0.01
D32_BOUND_SAFETY_MARGIN_MWH = 1e-3
D32_RELAXATION_CONTRACT = (
    "full_joint_d19_paths_with_primary_integer_domains_relaxed_"
    "and_exact_sign_binaries_retained_only_inside_each_24h_block"
)


@dataclass(frozen=True)
class BlockDefinition:
    block_index: int
    start_period: int
    stop_period: int

    @property
    def hours(self) -> int:
        return self.stop_period - self.start_period


@dataclass(frozen=True)
class BlockEnvelopeResult:
    block_index: int
    start_period: int
    stop_period: int
    hours: int
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float | None
    dual_bound_mwh: float
    protected_dual_bound_mwh: float
    relative_gap: float | None
    relaxed_primary_integer_variable_count: int
    active_sign_binary_count: int
    bound_certificate_complete: bool
    known_witness_block_l1_mwh: float = 0.0
    known_witness_within_bound: bool = False
    solver_threads: int = 1
    time_limit_seconds: float = D32_BLOCK_TIME_LIMIT_SECONDS
    bound_safety_margin_mwh: float = D32_BOUND_SAFETY_MARGIN_MWH
    relaxation_contract: str = D32_RELAXATION_CONTRACT


@dataclass(frozen=True)
class D32BlockEnvelopeScreen:
    schema: str
    window_id: str
    hours: int
    block_hours: int
    block_count: int
    workers: int
    per_block_time_limit_seconds: float
    reference_d30_lower_bound_mwh: float
    reference_d30_upper_bound_mwh: float
    reference_d30_csv_sha256: str
    reference_d30_manifest_sha256: str
    reference_d31_screen_sha256: str
    block_results: tuple[BlockEnvelopeResult, ...]
    summed_protected_block_upper_bound_mwh: float
    strict_partition_lower_bound_mwh: float
    strict_partition_upper_bound_mwh: float
    upper_bound_improvement_mwh: float
    upper_bound_improvement_fraction: float
    materiality_threshold_fraction: float
    materiality_gate_passed: bool
    global_probe_recommended: bool
    all_block_duals_finite: bool
    all_known_witness_blocks_within_bounds: bool
    intertemporal_constraints_retained: bool = True
    annual_service_and_admissibility_retained: bool = True
    primary_integer_domains_relaxed: bool = True
    block_sign_binaries_retained: bool = True
    feasible_set_changed_for_integer_solutions: bool = False
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


@dataclass(frozen=True)
class D32GlobalProbe:
    schema: str
    window_id: str
    hours: int
    threads: int
    time_limit_seconds: float
    reference_d30_lower_bound_mwh: float
    reference_d30_upper_bound_mwh: float
    reference_d30_csv_sha256: str
    reference_d30_manifest_sha256: str
    reference_d31_screen_sha256: str
    d32_screen_sha256: str
    block_count: int
    block_cut_count: int
    summed_protected_block_upper_bound_mwh: float
    partition_upper_bound_mwh: float
    selected_face_witness_mwh: float
    selected_face_termination: str
    selected_face_bound_certificate_complete: bool
    termination: str
    runtime_seconds: float
    primal_bound_mwh: float
    recomputed_redistribution_mwh: float
    dual_bound_mwh: float | None
    relative_gap: float | None
    bound_certificate_complete: bool
    witness_dominance_passed: bool
    all_known_witness_blocks_within_bounds: bool
    maximum_positive_normalized_constraint_residual: float
    auxiliary_objective_mismatch_mwh: float
    strict_global_lower_bound_mwh: float
    strict_global_upper_bound_mwh: float
    global_upper_bound_improvement_mwh: float
    global_upper_bound_improvement_fraction: float
    global_upper_bound_improved: bool
    exact_global_maximum: bool
    global_dual_is_valid_l1_upper_bound: bool
    primary_integer_patterns_reopened: bool = True
    sign_binaries_reopened: bool = True
    feasible_set_changed_for_integer_solutions: bool = False
    actual_price_path_assigned: bool = False
    formal_tac: bool = False
    e1_ready: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def partition_horizon(periods: int, block_hours: int = D32_BLOCK_HOURS) -> tuple[BlockDefinition, ...]:
    if type(periods) is not int or periods <= 0:
        raise ValueError("D32 periods must be a positive integer")
    if type(block_hours) is not int or block_hours <= 0:
        raise ValueError("D32 block hours must be a positive integer")
    return tuple(
        BlockDefinition(index, start, min(start + block_hours, periods))
        for index, start in enumerate(range(0, periods, block_hours))
    )


def _relax_primary_integer_domains(model: object) -> int:
    from pyomo.environ import TransformationFactory, Var

    count = 0
    for architecture in (model.comparator, model.candidate):
        count += sum(
            1
            for variable in architecture.component_data_objects(
                Var, active=True, descend_into=True
            )
            if variable.is_binary() or variable.is_integer()
        )
        TransformationFactory("core.relax_integer_vars").apply_to(architecture)
        if any(
            variable.is_binary() or variable.is_integer()
            for variable in architecture.component_data_objects(
                Var, active=True, descend_into=True
            )
        ):
            raise RuntimeError("D32 failed to relax a primary integer domain")
    if count <= 0:
        raise RuntimeError("D32 found no primary integer domains to relax")
    return count


def build_joint_block_relaxation(
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    *,
    comparator_admissibility: DispatchAdmissibility,
    candidate_admissibility: DispatchAdmissibility,
    comparator_lower_mw: Sequence[float],
    comparator_upper_mw: Sequence[float],
    candidate_lower_mw: Sequence[float],
    candidate_upper_mw: Sequence[float],
    block: BlockDefinition,
) -> tuple[object, int, int]:
    """Build one full-path relaxation with exact signs only in ``block``."""

    from pyomo.environ import Var

    periods = comparator_case.timeseries.period_count
    if candidate_case.timeseries.period_count != periods:
        raise ValueError("D32 joint cases have different horizons")
    if block.start_period < 0 or block.stop_period > periods or block.hours <= 0:
        raise ValueError("D32 block is outside the joint horizon")
    model = build_joint_redistribution_model(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_admissibility,
        candidate_admissibility=candidate_admissibility,
        direction=RedistributionDirection.MAXIMUM,
    )
    _replace_big_m_with_disaggregated_sign_formulation(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
    )
    add_export_linked_sign_cuts(
        model,
        pcc_capacity_mw=comparator_case.pcc_export_capacity_mw,
        annual_weights=comparator_case.economics.horizon.period_weights,
        dt_hours=comparator_case.timeseries.dt_hours,
        target_export_mwh=comparator_case.pcc_export_service.target_export_mwh,
    )
    # The annual signed-mass identity is valid for the complete L1 partition,
    # not for an individual block.  Full annual PCC service remains active in
    # both architecture blocks and is the correct cross-block coupling here.
    for name in (
        "d29_signed_mass_balance",
        "d29_positive_export_mass_cap",
        "d29_negative_export_mass_cap",
        "d29_positive_headroom_mass_cap",
        "d29_negative_headroom_mass_cap",
    ):
        getattr(model, name).deactivate()
    add_physics_service_sign_cuts(
        model,
        comparator_lower_mw=comparator_lower_mw,
        comparator_upper_mw=comparator_upper_mw,
        candidate_lower_mw=candidate_lower_mw,
        candidate_upper_mw=candidate_upper_mw,
    )
    _normalize_admissibility_constraints(
        model,
        comparator_case=comparator_case,
        candidate_case=candidate_case,
        comparator_cap=comparator_admissibility,
        candidate_cap=candidate_admissibility,
    )
    relaxed_primary_count = _relax_primary_integer_domains(model)
    active = set(range(block.start_period, block.stop_period))
    for period in model.redistribution_periods:
        if int(period) in active:
            continue
        model.d27_delta_decomposition[period].deactivate()
        model.d27_absolute_delta_identity[period].deactivate()
        model.d27_delta_positive_mw[period].fix(0.0)
        model.d27_delta_negative_mw[period].fix(0.0)
        model.absolute_delta_pcc_export_mw[period].fix(0.0)
        model.delta_nonnegative[period].fix(0)
    weights = comparator_case.economics.horizon.period_weights
    dt_hours = comparator_case.timeseries.dt_hours
    model.redistribution_objective.set_value(
        0.5
        * dt_hours
        * sum(
            weights[period] * model.absolute_delta_pcc_export_mw[period]
            for period in range(block.start_period, block.stop_period)
        )
    )
    active_sign_count = sum(
        1
        for variable in model.component_data_objects(
            Var, active=True, descend_into=True
        )
        if (variable.is_binary() or variable.is_integer()) and not variable.fixed
    )
    if active_sign_count != block.hours:
        raise RuntimeError(
            "D32 active integer count does not equal the block sign count"
        )
    return model, relaxed_primary_count, active_sign_count


def solve_joint_block_envelope(
    comparator_case: E0CCase,
    candidate_case: E0CCase,
    *,
    comparator_admissibility: DispatchAdmissibility,
    candidate_admissibility: DispatchAdmissibility,
    comparator_lower_mw: Sequence[float],
    comparator_upper_mw: Sequence[float],
    candidate_lower_mw: Sequence[float],
    candidate_upper_mw: Sequence[float],
    block: BlockDefinition,
    time_limit_seconds: float = D32_BLOCK_TIME_LIMIT_SECONDS,
    threads: int = 1,
    tee: bool = False,
) -> BlockEnvelopeResult:
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D32 block time limit must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D32 block threads must be a positive integer")
    import highspy

    model, relaxed_primary_count, sign_count = build_joint_block_relaxation(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_admissibility,
        candidate_admissibility=candidate_admissibility,
        comparator_lower_mw=comparator_lower_mw,
        comparator_upper_mw=comparator_upper_mw,
        candidate_lower_mw=candidate_lower_mw,
        candidate_upper_mw=candidate_upper_mw,
        block=block,
    )
    highspy.Highs.resetGlobalScheduler(True)
    solver = create_highs_solver(threads=threads, random_seed=0, mip_rel_gap=0.0)
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    solver.options["dual_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    solver.options["mip_feasibility_tolerance"] = STRICT_FEASIBILITY_TOLERANCE
    started = perf_counter()
    try:
        results = solver.solve(model, tee=tee, load_solutions=False)
        runtime = perf_counter() - started
        termination_raw = results.solver.termination_condition
        termination = getattr(termination_raw, "name", str(termination_raw)).lower()
        primal, dual = legacy_primal_dual_bounds(
            results, RedistributionDirection.MAXIMUM
        )
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    if dual is None or not math.isfinite(dual):
        raise RuntimeError(
            f"D32 block {block.block_index} returned no finite dual: {termination}"
        )
    if primal is not None and not math.isfinite(primal):
        primal = None
    if primal is not None and dual + KNOWN_WITNESS_TOLERANCE_MWH < primal:
        raise RuntimeError("D32 block dual is below its feasible primal")
    protected = dual + D32_BOUND_SAFETY_MARGIN_MWH
    relative_gap = (
        None
        if primal is None
        else abs(dual - primal) / max(abs(primal), 1e-12)
    )
    return BlockEnvelopeResult(
        block_index=block.block_index,
        start_period=block.start_period,
        stop_period=block.stop_period,
        hours=block.hours,
        termination=termination,
        runtime_seconds=runtime,
        primal_bound_mwh=primal,
        dual_bound_mwh=dual,
        protected_dual_bound_mwh=protected,
        relative_gap=relative_gap,
        relaxed_primary_integer_variable_count=relaxed_primary_count,
        active_sign_binary_count=sign_count,
        bound_certificate_complete=True,
        solver_threads=threads,
        time_limit_seconds=time_limit_seconds,
    )


def _load_known_trace_blocks(
    d22_source_dir: str | Path,
    *,
    window_id: str,
    blocks: Sequence[BlockDefinition],
) -> tuple[float, ...]:
    trace_path = Path(d22_source_dir) / "e0d22_pcc_dispatch_trace.csv"
    if not trace_path.is_file() or _sha256(trace_path) != E0D22_TRACE_SHA256:
        raise ValueError("D32 D22 trace is missing or hash-mismatched")
    with trace_path.open("r", encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["window_id"] == window_id]
    rows.sort(key=lambda row: int(row["period_index"]))
    if len(rows) != sum(block.hours for block in blocks):
        raise ValueError("D32 D22 trace horizon mismatch")
    result: list[float] = []
    for block in blocks:
        value = 0.5 * math.fsum(
            abs(float(rows[period]["annualized_delta_export_energy_mwh"]))
            for period in range(block.start_period, block.stop_period)
        )
        result.append(value)
    return tuple(result)


def _solve_block_worker(args: tuple[object, ...]) -> BlockEnvelopeResult:
    (
        comparator_case,
        candidate_case,
        comparator_cap,
        candidate_cap,
        comparator_lower,
        comparator_upper,
        candidate_lower,
        candidate_upper,
        block,
        time_limit_seconds,
    ) = args
    return solve_joint_block_envelope(
        comparator_case,
        candidate_case,
        comparator_admissibility=comparator_cap,
        candidate_admissibility=candidate_cap,
        comparator_lower_mw=comparator_lower,
        comparator_upper_mw=comparator_upper,
        candidate_lower_mw=candidate_lower,
        candidate_upper_mw=candidate_upper,
        block=block,
        time_limit_seconds=time_limit_seconds,
        threads=1,
    )


def run_joint_block_envelope_screen(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d30_source_dir: str | Path,
    d31_screen_path: str | Path,
    window: E0D17WindowSpec,
    block_hours: int = D32_BLOCK_HOURS,
    workers: int = 1,
    per_block_time_limit_seconds: float = D32_BLOCK_TIME_LIMIT_SECONDS,
) -> D32BlockEnvelopeScreen:
    if block_hours != D32_BLOCK_HOURS:
        raise ValueError("D32 preregistration fixes the block length at 24 h")
    if type(workers) is not int or workers <= 0:
        raise ValueError("D32 workers must be a positive integer")
    reference = load_d30_obbt_reference(d30_source_dir, window_id=window.window_id)
    d31_screen = load_d31_screen(
        d31_screen_path, window=window, reference=reference
    )
    comparator_lower, comparator_upper = _screen_bounds(
        d31_screen, "comparator", hours=window.hours
    )
    candidate_lower, candidate_upper = _screen_bounds(
        d31_screen, "candidate", hours=window.hours
    )
    d19_rows, _ = load_e0d23_source_rows(d19_source_dir, d22_source_dir)
    inputs = load_e0d17_inputs(heat_path, vre_path)
    rows = _window_rows(inputs, window)
    comparator_case, candidate_case, comparator_cap, candidate_cap, _service = (
        _build_cases(rows, d19_rows[window.window_id])
    )
    blocks = partition_horizon(window.hours, block_hours)
    witness_blocks = _load_known_trace_blocks(
        d22_source_dir, window_id=window.window_id, blocks=blocks
    )
    args = tuple(
        (
            comparator_case,
            candidate_case,
            comparator_cap,
            candidate_cap,
            comparator_lower,
            comparator_upper,
            candidate_lower,
            candidate_upper,
            block,
            per_block_time_limit_seconds,
        )
        for block in blocks
    )
    active_workers = min(workers, len(blocks))
    if active_workers == 1:
        raw_results = tuple(_solve_block_worker(item) for item in args)
    else:
        with ProcessPoolExecutor(max_workers=active_workers) as pool:
            raw_results = tuple(pool.map(_solve_block_worker, args))
    results: list[BlockEnvelopeResult] = []
    for raw, witness in zip(raw_results, witness_blocks, strict=True):
        within = witness <= raw.protected_dual_bound_mwh + KNOWN_WITNESS_TOLERANCE_MWH
        if not within:
            raise RuntimeError(
                f"D32 block {raw.block_index} excludes the locked D22 witness"
            )
        results.append(
            replace(
                raw,
                known_witness_block_l1_mwh=witness,
                known_witness_within_bound=True,
            )
        )
    summed_upper = math.fsum(item.protected_dual_bound_mwh for item in results)
    strict_upper = min(reference.strict_global_upper_bound_mwh, summed_upper)
    improvement = max(0.0, reference.strict_global_upper_bound_mwh - strict_upper)
    fraction = improvement / max(reference.strict_global_upper_bound_mwh, 1e-12)
    gate = fraction >= D32_MATERIALITY_THRESHOLD_FRACTION
    return D32BlockEnvelopeScreen(
        schema=D32_SCREEN_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        block_hours=block_hours,
        block_count=len(blocks),
        workers=active_workers,
        per_block_time_limit_seconds=per_block_time_limit_seconds,
        reference_d30_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        reference_d30_upper_bound_mwh=reference.strict_global_upper_bound_mwh,
        reference_d30_csv_sha256=reference.csv_sha256,
        reference_d30_manifest_sha256=reference.manifest_sha256,
        reference_d31_screen_sha256=_sha256(Path(d31_screen_path)),
        block_results=tuple(results),
        summed_protected_block_upper_bound_mwh=summed_upper,
        strict_partition_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        strict_partition_upper_bound_mwh=strict_upper,
        upper_bound_improvement_mwh=improvement,
        upper_bound_improvement_fraction=fraction,
        materiality_threshold_fraction=D32_MATERIALITY_THRESHOLD_FRACTION,
        materiality_gate_passed=gate,
        global_probe_recommended=gate,
        all_block_duals_finite=True,
        all_known_witness_blocks_within_bounds=True,
    )


def write_screen(screen: D32BlockEnvelopeScreen, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(screen), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_d32_screen(
    screen_path: str | Path,
    *,
    window: E0D17WindowSpec,
    reference: object,
    d31_screen_path: str | Path,
) -> dict[str, object]:
    path = Path(screen_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != D32_SCREEN_SCHEMA
        or payload.get("window_id") != window.window_id
        or int(payload.get("hours", 0)) != window.hours
        or int(payload.get("block_hours", 0)) != D32_BLOCK_HOURS
    ):
        raise ValueError("D32 screen identity mismatch")
    if payload.get("reference_d30_csv_sha256") != reference.csv_sha256:
        raise ValueError("D32 screen D30 CSV lock mismatch")
    if payload.get("reference_d30_manifest_sha256") != reference.manifest_sha256:
        raise ValueError("D32 screen D30 manifest lock mismatch")
    if payload.get("reference_d31_screen_sha256") != _sha256(Path(d31_screen_path)):
        raise ValueError("D32 screen D31 lock mismatch")
    if any(
        payload.get(key) is not False
        for key in (
            "feasible_set_changed_for_integer_solutions",
            "actual_price_path_assigned",
            "formal_tac",
            "e1_ready",
        )
    ):
        raise ValueError("D32 screen crosses its scientific boundary")
    if (
        payload.get("all_block_duals_finite") is not True
        or payload.get("all_known_witness_blocks_within_bounds") is not True
        or payload.get("intertemporal_constraints_retained") is not True
        or payload.get("annual_service_and_admissibility_retained") is not True
        or payload.get("primary_integer_domains_relaxed") is not True
        or payload.get("block_sign_binaries_retained") is not True
    ):
        raise ValueError("D32 screen has no valid block-bound certificate")
    blocks = payload.get("block_results")
    if not isinstance(blocks, list) or len(blocks) != int(payload.get("block_count", 0)):
        raise ValueError("D32 screen block list is incomplete")
    expected_start = 0
    protected_sum = 0.0
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError("D32 screen contains a malformed block")
        start = int(block.get("start_period", -1))
        stop = int(block.get("stop_period", -1))
        protected = float(block.get("protected_dual_bound_mwh", math.nan))
        if (
            int(block.get("block_index", -1)) != index
            or start != expected_start
            or stop <= start
            or stop > window.hours
            or not math.isfinite(protected)
            or block.get("bound_certificate_complete") is not True
            or block.get("known_witness_within_bound") is not True
            or int(block.get("active_sign_binary_count", 0)) != stop - start
        ):
            raise ValueError("D32 screen block audit failed")
        expected_start = stop
        protected_sum += protected
    if expected_start != window.hours:
        raise ValueError("D32 screen blocks do not partition the horizon")
    reported_sum = float(payload.get("summed_protected_block_upper_bound_mwh", math.nan))
    if not math.isclose(protected_sum, reported_sum, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("D32 screen block sum mismatch")
    return payload


def add_joint_block_envelope_cuts(
    model: object,
    *,
    screen: dict[str, object],
    annual_weights: Sequence[float],
    dt_hours: float,
) -> int:
    """Add every certified block L1 upper bound to the exact global model."""

    from pyomo.environ import ConstraintList

    if hasattr(model, "d32_block_l1_upper"):
        raise ValueError("D32 block cuts are already installed")
    periods = tuple(model.redistribution_periods)
    weights = tuple(float(item) for item in annual_weights)
    if len(weights) != len(periods):
        raise ValueError("D32 block-cut weights do not match the horizon")
    blocks = screen.get("block_results")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("D32 block cuts require a non-empty screen")
    model.d32_block_l1_upper = ConstraintList()
    for block in blocks:
        assert isinstance(block, dict)
        start = int(block["start_period"])
        stop = int(block["stop_period"])
        upper = float(block["protected_dual_bound_mwh"])
        model.d32_block_l1_upper.add(
            0.5
            * dt_hours
            * sum(
                weights[period] * model.absolute_delta_pcc_export_mw[period]
                for period in range(start, stop)
            )
            <= upper
        )
    return len(blocks)


def run_joint_block_envelope_probe(
    heat_path: str | Path,
    vre_path: str | Path,
    *,
    d19_source_dir: str | Path,
    d22_source_dir: str | Path,
    d30_source_dir: str | Path,
    d31_screen_path: str | Path,
    d32_screen_path: str | Path,
    window: E0D17WindowSpec,
    time_limit_seconds: float,
    threads: int,
    tee: bool = False,
) -> D32GlobalProbe:
    """Reopen the exact global MILP with all certified D32 block cuts."""

    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D32 global time limit must be finite and positive")
    if type(threads) is not int or threads <= 0:
        raise ValueError("D32 global threads must be a positive integer")
    reference = load_d30_obbt_reference(d30_source_dir, window_id=window.window_id)
    d31_screen = load_d31_screen(
        d31_screen_path, window=window, reference=reference
    )
    screen = load_d32_screen(
        d32_screen_path,
        window=window,
        reference=reference,
        d31_screen_path=d31_screen_path,
    )
    comparator_lower, comparator_upper = _screen_bounds(
        d31_screen, "comparator", hours=window.hours
    )
    candidate_lower, candidate_upper = _screen_bounds(
        d31_screen, "candidate", hours=window.hours
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
        model, pcc_capacity_mw=comparator_case.pcc_export_capacity_mw
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
    block_cut_count = add_joint_block_envelope_cuts(
        model,
        screen=screen,
        annual_weights=comparator_case.economics.horizon.period_weights,
        dt_hours=comparator_case.timeseries.dt_hours,
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
        conditional_face_warm_start_termination="d32_selected_face",
        conditional_face_fixed_primary_integer_count=fixed_count,
        allow_incumbent_only=True,
    )
    if result.maximum_positive_normalized_constraint_residual > STRICT_FEASIBILITY_TOLERANCE:
        raise RuntimeError("D32 global incumbent violates strict feasibility")
    if abs(result.auxiliary_objective_mismatch_mwh) > D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH:
        raise RuntimeError("D32 global incumbent failed L1 recomputation")
    lower = max(
        reference.strict_global_lower_bound_mwh,
        min(
            result.recomputed_redistribution_mwh,
            reference.strict_global_upper_bound_mwh,
        ),
    )
    partition_upper = float(screen["strict_partition_upper_bound_mwh"])
    upper = min(reference.strict_global_upper_bound_mwh, partition_upper)
    if result.dual_bound_mwh is not None:
        if (
            result.dual_bound_mwh + D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
            < reference.strict_global_lower_bound_mwh
        ):
            raise RuntimeError("D32 global dual falls below the known feasible lower bound")
        upper = min(
            upper,
            max(result.dual_bound_mwh, reference.strict_global_lower_bound_mwh),
        )
    if upper + KNOWN_WITNESS_TOLERANCE_MWH < lower:
        raise RuntimeError("D32 strict interval is numerically reversed")
    improvement = reference.strict_global_upper_bound_mwh - upper
    exact = upper - lower <= KNOWN_WITNESS_TOLERANCE_MWH
    return D32GlobalProbe(
        schema=D32_PROBE_SCHEMA,
        window_id=window.window_id,
        hours=window.hours,
        threads=threads,
        time_limit_seconds=time_limit_seconds,
        reference_d30_lower_bound_mwh=reference.strict_global_lower_bound_mwh,
        reference_d30_upper_bound_mwh=reference.strict_global_upper_bound_mwh,
        reference_d30_csv_sha256=reference.csv_sha256,
        reference_d30_manifest_sha256=reference.manifest_sha256,
        reference_d31_screen_sha256=_sha256(Path(d31_screen_path)),
        d32_screen_sha256=_sha256(Path(d32_screen_path)),
        block_count=int(screen["block_count"]),
        block_cut_count=block_cut_count,
        summed_protected_block_upper_bound_mwh=float(
            screen["summed_protected_block_upper_bound_mwh"]
        ),
        partition_upper_bound_mwh=partition_upper,
        selected_face_witness_mwh=face_result.auxiliary_objective_mwh,
        selected_face_termination=face_result.termination,
        selected_face_bound_certificate_complete=face_result.bound_certificate_complete,
        termination=result.termination,
        runtime_seconds=result.runtime_seconds,
        primal_bound_mwh=result.primal_bound_mwh,
        recomputed_redistribution_mwh=result.recomputed_redistribution_mwh,
        dual_bound_mwh=result.dual_bound_mwh,
        relative_gap=result.relative_gap,
        bound_certificate_complete=result.bound_certificate_complete,
        witness_dominance_passed=(
            result.recomputed_redistribution_mwh
            + D29_OBJECTIVE_RECOMPUTATION_TOLERANCE_MWH
            >= face_result.auxiliary_objective_mwh
        ),
        all_known_witness_blocks_within_bounds=True,
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
        global_dual_is_valid_l1_upper_bound=(
            result.bound_certificate_complete or partition_upper < math.inf
        ),
    )


def write_probe(probe: D32GlobalProbe, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(probe), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _window(window_id: str) -> E0D17WindowSpec:
    try:
        return next(item for item in DEFAULT_WINDOWS if item.window_id == window_id)
    except StopIteration as exc:
        raise ValueError(f"unknown D32 window: {window_id}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heat", required=True)
    parser.add_argument("--vre", required=True)
    parser.add_argument("--d19-source-dir", required=True)
    parser.add_argument("--d22-source-dir", required=True)
    parser.add_argument("--d30-source-dir", required=True)
    parser.add_argument("--d31-screen", required=True)
    parser.add_argument("--d32-screen")
    parser.add_argument("--mode", choices=("screen", "probe"), default="screen")
    parser.add_argument(
        "--window",
        choices=tuple(item.window_id for item in DEFAULT_WINDOWS),
        required=True,
    )
    parser.add_argument("--block-hours", type=int, default=D32_BLOCK_HOURS)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--per-block-time-limit-seconds",
        type=float,
        default=D32_BLOCK_TIME_LIMIT_SECONDS,
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--time-limit-seconds", type=float, default=300.0)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args(argv)
    if args.mode == "probe":
        if not args.d32_screen:
            parser.error("--d32-screen is required in probe mode")
        probe = run_joint_block_envelope_probe(
            args.heat,
            args.vre,
            d19_source_dir=args.d19_source_dir,
            d22_source_dir=args.d22_source_dir,
            d30_source_dir=args.d30_source_dir,
            d31_screen_path=args.d31_screen,
            d32_screen_path=args.d32_screen,
            window=_window(args.window),
            time_limit_seconds=args.time_limit_seconds,
            threads=args.threads,
        )
        write_probe(probe, args.output)
        print(json.dumps(asdict(probe), ensure_ascii=False, sort_keys=True))
        return 0
    screen = run_joint_block_envelope_screen(
        args.heat,
        args.vre,
        d19_source_dir=args.d19_source_dir,
        d22_source_dir=args.d22_source_dir,
        d30_source_dir=args.d30_source_dir,
        d31_screen_path=args.d31_screen,
        window=_window(args.window),
        block_hours=args.block_hours,
        workers=args.workers,
        per_block_time_limit_seconds=args.per_block_time_limit_seconds,
    )
    write_screen(screen, args.output)
    print(json.dumps(asdict(screen), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
