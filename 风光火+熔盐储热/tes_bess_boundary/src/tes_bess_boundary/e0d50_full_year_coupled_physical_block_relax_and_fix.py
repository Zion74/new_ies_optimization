"""E0-D-50 full-year coupled physical-binary relax-and-fix recovery.

The original 8784-hour BESS planning model, its economic objective, and every
constraint remain active throughout candidate construction.  CHP fuel-code
bits stay projected to ``[0, 1]``.  Physical binaries are made integral in a
336-hour moving band and committed in chronological 168-hour blocks.  Only a
complete final physical trajectory may be lifted with the frozen D49 fuel
encoding and passed to a clean original-cost repair.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

from tes_bess_boundary.e0d40_full_year_compute_gate import _linearity_audit
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    BinaryInventory,
    extract_binary_snapshot,
    restore_binary_domains,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    CLAIM_SCOPE,
    EXPECTED_MODEL_SIZE,
    FORMAL_PROJECT_TAC_READY,
    TECHNICAL_RANKING_PERMITTED,
    _bound_and_constraint_audit,
    _name_list_sha256,
    _service_audit,
    _sha256,
    _tree_sha256,
    _variable_map,
    write_seed_csv_gz,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    FORMAL_THREADS,
    REPAIR_HARD_WALL_SECONDS,
    _configure_hamming_solver,
    build_original_stage_model,
    constraint_identity,
    highs_option_roundtrip,
)
from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
    EXPECTED_PHYSICAL_BINARY_COUNT,
    exact_lift_fuel_encoding,
    fuel_projection_dependency_audit,
    partition_fuel_code_binaries,
    solve_d49_original_cost_repair,
    static_fuel_lift_spec_audit,
)
from tes_bess_boundary.model import Architecture


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d50_block_relax_and_fix.v1"
STAGE_SCHEMA_ID = "tes_bess_boundary.e0d50_block_stage.v1"
SNAPSHOT_SCHEMA_ID = "tes_bess_boundary.e0d50_physical_snapshot.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d50_gate_a_build.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d50_original_cost_repair.v1"

COMMIT_HOURS = 168
INTEGER_LOOKAHEAD_HOURS = 336
STAGE_SOFT_TIME_LIMIT_SECONDS = 360.0
STAGE_HARD_WALL_SECONDS = 390.0
CANDIDATE_TOTAL_HARD_WALL_SECONDS = 21_600.0
TOTAL_HARD_WALL_SECONDS = 23_400.0
EXPECTED_FORMAL_HOURS = 8_784
EXPECTED_FORMAL_STAGE_COUNT = 53
EXPECTED_FORMAL_LAST_BLOCK_HOURS = 48
BINARY_VALUE_TOLERANCE = 1e-7
D50_BESS_R1_GUIDE_SHA256 = (
    "2d03ab0ae229583bbf46e3ebdd84ab0924627d7ac20e2af68dad42ff11de4614"
)

CHP_ONLINE_COMPONENT = re.compile(r"^chp\[\d+\]\.online$")
ALLOWED_HOURLY_PHYSICAL_COMPONENTS = frozenset({"bess.charge_mode"})
ALLOWED_GLOBAL_PHYSICAL_COMPONENTS = frozenset({"bess.installed"})


@dataclass(frozen=True)
class PhysicalTimeLayout:
    """Map every D50 physical binary to a real period or global topology."""

    periods: tuple[object, ...]
    hourly_names: tuple[tuple[str, ...], ...]
    global_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.periods:
            raise ValueError("D50 physical layout requires at least one period")
        if len(self.periods) != len(self.hourly_names):
            raise ValueError("D50 period/name layout length mismatch")
        flattened = tuple(name for names in self.hourly_names for name in names)
        all_names = flattened + self.global_names
        if len(all_names) != len(set(all_names)):
            raise ValueError("D50 physical layout contains duplicate names")

    @property
    def all_names(self) -> tuple[str, ...]:
        return tuple(name for names in self.hourly_names for name in names) + (
            self.global_names
        )


@dataclass(frozen=True)
class CommitBlock:
    """One chronological physical-binary commit block."""

    index: int
    start_position: int
    stop_position: int
    periods: tuple[object, ...]

    @property
    def hours(self) -> int:
        return self.stop_position - self.start_position


@dataclass(frozen=True)
class StageDomainPlan:
    """Disjoint D50 variable partition for one solve stage."""

    stage_index: int
    current_block: CommitBlock
    lookahead_block: CommitBlock | None
    fixed_physical_names: tuple[str, ...]
    active_physical_names: tuple[str, ...]
    relaxed_physical_names: tuple[str, ...]
    projected_fuel_names: tuple[str, ...]


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


def _append_progress(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n", buffering=1) as handle:
        handle.write(
            json.dumps(
                {"unix_time": time.time(), **payload},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d50_full_year_coupled_physical_block_relax_and_fix.py",
        "e0d50_monitored_executor.py",
        "e0d49_physics_first_fuel_projection_primal_recovery.py",
        "e0d48_hamming_primal_recovery.py",
        "e0d46_full_year_feasible_upper_bound_repair.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
        "components/chp.py",
        "capacity_planning.py",
    )
    return {name: _sha256(package / name) for name in names}


def _objective_identity(model: object) -> dict[str, Any]:
    from pyomo.environ import Objective

    objectives = tuple(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    digest = hashlib.sha256()
    for objective in sorted(objectives, key=lambda item: item.name):
        digest.update(objective.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(objective.expr).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(objective.sense).encode("utf-8"))
        digest.update(b"\0")
    return {
        "active_objective_count": len(objectives),
        "active_objective_names": [item.name for item in objectives],
        "active_objective_expressions_sha256": digest.hexdigest(),
    }


def _period_index(variable: object) -> object:
    raw = variable.index()
    if isinstance(raw, tuple):
        if len(raw) != 1:
            raise ValueError(f"D50 physical variable has non-hourly index: {variable.name}")
        return raw[0]
    return raw


def audit_candidate_guide_identity(
    guide_path: Path,
    *,
    expected_variable_names: Sequence[str],
    expected_binary_names: Sequence[str],
) -> dict[str, Any]:
    """Validate D41/D46 guide rows without applying any value to the model."""

    expected_variables = tuple(sorted(expected_variable_names))
    expected_binaries = set(expected_binary_names)
    names: list[str] = []
    classified_binaries: set[str] = set()
    fractional_binary_value_count = 0
    with gzip.open(guide_path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["variable_name", "value", "variable_class"]:
            raise ValueError("D50 guide header mismatch")
        previous: str | None = None
        for row in reader:
            name = row["variable_name"]
            if not name or (previous is not None and name <= previous):
                raise ValueError("D50 guide names are missing, duplicated, or unsorted")
            previous = name
            variable_class = row["variable_class"]
            if variable_class not in {
                "topology_binary",
                "operational_binary",
                "original_binary",
                "continuous",
            }:
                raise ValueError(f"D50 guide class is invalid: {name}")
            try:
                number = float(row["value"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"D50 guide value is invalid: {name}") from error
            if not math.isfinite(number):
                raise ValueError(f"D50 guide value is not finite: {name}")
            is_binary_class = variable_class != "continuous"
            if is_binary_class:
                classified_binaries.add(name)
                if min(abs(number), abs(number - 1.0)) > BINARY_VALUE_TOLERANCE:
                    fractional_binary_value_count += 1
            names.append(name)
    names_tuple = tuple(names)
    variable_identity = names_tuple == expected_variables
    binary_identity = classified_binaries == expected_binaries
    passed = variable_identity and binary_identity
    return {
        "variable_count": len(names_tuple),
        "variable_names_sha256": _name_list_sha256(names_tuple),
        "binary_classified_count": len(classified_binaries),
        "binary_names_sha256": _name_list_sha256(tuple(sorted(classified_binaries))),
        "fractional_binary_value_count": fractional_binary_value_count,
        "variable_identity_passed": variable_identity,
        "binary_identity_passed": binary_identity,
        "values_applied_to_model": False,
        "binary_seed_applied": False,
        "continuous_partial_warmstart_applied": False,
        "passed": passed,
    }


def build_physical_time_layout(
    model: object,
    physical_names: Sequence[str],
    *,
    require_formal_counts: bool,
) -> tuple[PhysicalTimeLayout, dict[str, Any]]:
    """Classify only CHP-online, BESS-mode, and BESS-installation binaries."""

    variables = _variable_map(model)
    periods = tuple(model.periods)
    period_positions = {period: index for index, period in enumerate(periods)}
    if len(period_positions) != len(periods):
        raise ValueError("D50 model periods are not unique")
    hourly: list[list[str]] = [[] for _ in periods]
    global_names: list[str] = []
    component_counts: dict[str, int] = {}
    forbidden: list[str] = []
    for name in physical_names:
        variable = variables[name]
        component = variable.parent_component().name
        component_counts[component] = component_counts.get(component, 0) + 1
        if component in ALLOWED_GLOBAL_PHYSICAL_COMPONENTS:
            if variable.index() is not None:
                forbidden.append(name)
            else:
                global_names.append(name)
            continue
        if component in ALLOWED_HOURLY_PHYSICAL_COMPONENTS or CHP_ONLINE_COMPONENT.fullmatch(
            component
        ):
            period = _period_index(variable)
            if period not in period_positions:
                forbidden.append(name)
            else:
                hourly[period_positions[period]].append(name)
            continue
        forbidden.append(name)
    layout = PhysicalTimeLayout(
        periods=periods,
        hourly_names=tuple(tuple(sorted(names)) for names in hourly),
        global_names=tuple(sorted(global_names)),
    )
    complete = set(layout.all_names) == set(physical_names) and not forbidden
    names_per_period = tuple(len(names) for names in layout.hourly_names)
    constant_hourly_width = len(set(names_per_period)) == 1
    formal_counts_passed = all(
        (
            len(periods) == EXPECTED_FORMAL_HOURS,
            names_per_period == (3,) * EXPECTED_FORMAL_HOURS,
            layout.global_names == ("bess.installed",),
            len(layout.all_names) == EXPECTED_PHYSICAL_BINARY_COUNT[Architecture.BESS],
        )
    )
    passed = all(
        (
            complete,
            constant_hourly_width,
            bool(names_per_period and names_per_period[0] > 0),
            bool(layout.global_names),
            formal_counts_passed if require_formal_counts else True,
        )
    )
    return layout, {
        "period_count": len(periods),
        "physical_binary_count": len(physical_names),
        "hourly_physical_binary_count": sum(names_per_period),
        "global_physical_binary_count": len(layout.global_names),
        "hourly_binary_count_per_period": (
            names_per_period[0] if constant_hourly_width and names_per_period else None
        ),
        "global_physical_names": list(layout.global_names),
        "component_counts": dict(sorted(component_counts.items())),
        "forbidden_physical_name_count": len(forbidden),
        "forbidden_physical_names_sha256": _name_list_sha256(tuple(sorted(forbidden))),
        "layout_complete_and_disjoint": complete,
        "constant_hourly_width": constant_hourly_width,
        "formal_counts_required": require_formal_counts,
        "formal_counts_passed": formal_counts_passed,
        "physical_names_sha256": _name_list_sha256(tuple(sorted(layout.all_names))),
        "passed": passed,
    }


def build_commit_blocks(
    periods: Sequence[object], *, commit_hours: int = COMMIT_HOURS
) -> tuple[CommitBlock, ...]:
    """Partition the real ordered horizon without wraparound or padding."""

    ordered = tuple(periods)
    if not ordered:
        raise ValueError("D50 commit blocks require periods")
    if not isinstance(commit_hours, int) or commit_hours <= 0:
        raise ValueError("D50 commit hours must be a positive integer")
    blocks: list[CommitBlock] = []
    for index, start in enumerate(range(0, len(ordered), commit_hours)):
        stop = min(start + commit_hours, len(ordered))
        blocks.append(
            CommitBlock(
                index=index,
                start_position=start,
                stop_position=stop,
                periods=ordered[start:stop],
            )
        )
    return tuple(blocks)


def commit_block_coverage_audit(
    periods: Sequence[object],
    blocks: Sequence[CommitBlock],
    *,
    require_formal_counts: bool,
) -> dict[str, Any]:
    ordered = tuple(periods)
    flattened = tuple(period for block in blocks for period in block.periods)
    contiguous = all(
        block.index == index
        and block.start_position == (0 if index == 0 else blocks[index - 1].stop_position)
        and block.stop_position - block.start_position == len(block.periods)
        for index, block in enumerate(blocks)
    )
    exact = flattened == ordered and contiguous
    sizes = tuple(block.hours for block in blocks)
    formal_counts_passed = all(
        (
            len(ordered) == EXPECTED_FORMAL_HOURS,
            len(blocks) == EXPECTED_FORMAL_STAGE_COUNT,
            sizes[:-1] == (COMMIT_HOURS,) * 52,
            sizes[-1:] == (EXPECTED_FORMAL_LAST_BLOCK_HOURS,),
        )
    )
    return {
        "period_count": len(ordered),
        "stage_count": len(blocks),
        "block_hours": list(sizes),
        "exact_ordered_coverage_without_wraparound": exact,
        "formal_counts_required": require_formal_counts,
        "formal_counts_passed": formal_counts_passed,
        "passed": exact and (formal_counts_passed if require_formal_counts else True),
    }


def make_stage_domain_plan(
    layout: PhysicalTimeLayout,
    blocks: Sequence[CommitBlock],
    projected_fuel_names: Sequence[str],
    stage_index: int,
) -> StageDomainPlan:
    if stage_index < 0 or stage_index >= len(blocks):
        raise ValueError("D50 stage index is outside the frozen block sequence")
    current = blocks[stage_index]
    lookahead = blocks[stage_index + 1] if stage_index + 1 < len(blocks) else None

    def names_for(blocks_to_use: Sequence[CommitBlock]) -> tuple[str, ...]:
        return tuple(
            name
            for block in blocks_to_use
            for position in range(block.start_position, block.stop_position)
            for name in layout.hourly_names[position]
        )

    fixed = names_for(blocks[:stage_index])
    active = names_for(blocks[stage_index : min(stage_index + 2, len(blocks))])
    relaxed = names_for(blocks[min(stage_index + 2, len(blocks)) :])
    if stage_index == 0:
        active = tuple(sorted((*active, *layout.global_names)))
    else:
        fixed = tuple(sorted((*fixed, *layout.global_names)))
    return StageDomainPlan(
        stage_index=stage_index,
        current_block=current,
        lookahead_block=lookahead,
        fixed_physical_names=tuple(sorted(fixed)),
        active_physical_names=tuple(sorted(active)),
        relaxed_physical_names=tuple(sorted(relaxed)),
        projected_fuel_names=tuple(sorted(projected_fuel_names)),
    )


def apply_stage_domain_plan(
    model: object,
    inventory: BinaryInventory,
    plan: StageDomainPlan,
    fixed_snapshot: Mapping[str, int],
) -> dict[str, Any]:
    """Apply one exact fixed/integer/relaxed/projected partition."""

    from pyomo.environ import Binary, UnitInterval

    variables = _variable_map(model)
    fixed = set(plan.fixed_physical_names)
    active = set(plan.active_physical_names)
    relaxed = set(plan.relaxed_physical_names)
    projected = set(plan.projected_fuel_names)
    categories = (fixed, active, relaxed, projected)
    disjoint = all(
        not categories[left] & categories[right]
        for left in range(len(categories))
        for right in range(left + 1, len(categories))
    )
    complete = set().union(*categories) == set(inventory.all_names)
    if not disjoint or not complete:
        raise ValueError("D50 stage domain partition is incomplete or overlapping")
    if set(fixed_snapshot) != fixed:
        raise ValueError("D50 fixed snapshot does not exactly match the stage past")
    invalid_snapshot = sorted(
        name for name, value in fixed_snapshot.items() if value not in (0, 1)
    )
    if invalid_snapshot:
        raise ValueError(f"D50 fixed snapshot is not binary: {invalid_snapshot[:3]}")

    for name in plan.projected_fuel_names:
        variable = variables[name]
        variable.unfix()
        variable.domain = UnitInterval
        variable.setlb(0.0)
        variable.setub(1.0)
    for name in plan.relaxed_physical_names:
        variable = variables[name]
        variable.unfix()
        variable.domain = UnitInterval
        variable.setlb(0.0)
        variable.setub(1.0)

    cleared_fractional = 0
    retained_integer_initial = 0
    for name in plan.active_physical_names:
        variable = variables[name]
        variable.unfix()
        variable.domain = Binary
        variable.setlb(0.0)
        variable.setub(1.0)
        raw = variable.value
        if raw is None:
            continue
        number = float(raw)
        if min(abs(number), abs(number - 1.0)) <= BINARY_VALUE_TOLERANCE:
            retained_integer_initial += 1
        else:
            variable.set_value(None)
            cleared_fractional += 1
    for name in plan.fixed_physical_names:
        variable = variables[name]
        variable.domain = Binary
        variable.setlb(0.0)
        variable.setub(1.0)
        variable.fix(int(fixed_snapshot[name]))

    active_binary_names = tuple(
        sorted(name for name, variable in variables.items() if variable.is_binary())
    )
    expected_binary_names = tuple(sorted(fixed | active))
    fixed_values_match = all(
        variables[name].fixed
        and float(variables[name].value) == float(fixed_snapshot[name])
        for name in plan.fixed_physical_names
    )
    projected_valid = all(
        not variables[name].is_binary()
        and not variables[name].fixed
        and float(variables[name].lb) == 0.0
        and float(variables[name].ub) == 1.0
        for name in (*plan.projected_fuel_names, *plan.relaxed_physical_names)
    )
    passed = all(
        (
            disjoint,
            complete,
            active_binary_names == expected_binary_names,
            fixed_values_match,
            projected_valid,
        )
    )
    return {
        "stage_index": plan.stage_index,
        "current_block": {
            "index": plan.current_block.index,
            "start_position": plan.current_block.start_position,
            "stop_position": plan.current_block.stop_position,
            "hours": plan.current_block.hours,
        },
        "lookahead_block": (
            None
            if plan.lookahead_block is None
            else {
                "index": plan.lookahead_block.index,
                "start_position": plan.lookahead_block.start_position,
                "stop_position": plan.lookahead_block.stop_position,
                "hours": plan.lookahead_block.hours,
            }
        ),
        "fixed_physical_count": len(fixed),
        "active_physical_count": len(active),
        "relaxed_physical_count": len(relaxed),
        "projected_fuel_count": len(projected),
        "fixed_physical_names_sha256": _name_list_sha256(tuple(sorted(fixed))),
        "active_physical_names_sha256": _name_list_sha256(tuple(sorted(active))),
        "relaxed_physical_names_sha256": _name_list_sha256(tuple(sorted(relaxed))),
        "projected_fuel_names_sha256": _name_list_sha256(tuple(sorted(projected))),
        "active_binary_count_after_domain_update": len(active_binary_names),
        "active_binary_names_sha256_after_domain_update": _name_list_sha256(
            active_binary_names
        ),
        "newly_active_fractional_values_cleared_count": cleared_fractional,
        "legal_integer_initial_values_retained_count": retained_integer_initial,
        "warmstart_requested": False,
        "artificial_rounding_applied": False,
        "partition_complete_and_disjoint": disjoint and complete,
        "fixed_values_match_snapshot": fixed_values_match,
        "relaxed_domains_valid": projected_valid,
        "passed": passed,
    }


def prepare_d50_model(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    guide_path: Path,
    commit_hours: int = COMMIT_HOURS,
    require_locked_guide_hash: bool = True,
    require_formal_counts: bool = True,
) -> tuple[object, PhysicalTimeLayout, tuple[CommitBlock, ...], dict[str, Any]]:
    """Prove the D50 partition and validate—but never apply—the D41 guide."""

    if architecture is not Architecture.BESS:
        raise ValueError("D50 is frozen for BESS only")
    guide_hash = _sha256(guide_path)
    expected_hash = D50_BESS_R1_GUIDE_SHA256
    if require_locked_guide_hash and guide_hash != expected_hash:
        raise ValueError("D50 D41 guide hash mismatch")
    variable_names = tuple(sorted(_variable_map(model)))
    guide_identity_audit = audit_candidate_guide_identity(
        guide_path,
        expected_variable_names=variable_names,
        expected_binary_names=inventory.all_names,
    )
    guide_identity_audit = {
        **guide_identity_audit,
        "guide_sha256": guide_hash,
        "expected_guide_sha256": expected_hash,
        "guide_hash_required": require_locked_guide_hash,
    }
    partition, partition_audit = partition_fuel_code_binaries(
        model,
        inventory,
        architecture=architecture,
        require_formal_counts=require_formal_counts,
    )
    dependency_audit = fuel_projection_dependency_audit(model)
    layout, layout_audit = build_physical_time_layout(
        model,
        partition.physical_binary_names,
        require_formal_counts=require_formal_counts,
    )
    blocks = build_commit_blocks(layout.periods, commit_hours=commit_hours)
    coverage_audit = commit_block_coverage_audit(
        layout.periods,
        blocks,
        require_formal_counts=require_formal_counts,
    )
    constraints = constraint_identity(model)
    objective = _objective_identity(model)
    passed = all(
        (
            guide_identity_audit["passed"],
            partition_audit["passed"],
            dependency_audit["passed"],
            layout_audit["passed"],
            coverage_audit["passed"],
            objective["active_objective_count"] == 1,
        )
    )
    return partition, layout, blocks, {
        "guide_identity_audit": guide_identity_audit,
        "binary_partition_audit": partition_audit,
        "fuel_projection_dependency_audit": dependency_audit,
        "physical_time_layout_audit": layout_audit,
        "commit_block_coverage_audit": coverage_audit,
        "original_constraint_identity": constraints,
        "original_objective_identity": objective,
        "original_economic_objective_retained": True,
        "hamming_objective_added": False,
        "passed": passed,
    }


def capture_first_original_cost_incumbent(
    model: object,
    *,
    time_limit_seconds: float = STAGE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
) -> dict[str, Any]:
    """Capture and load the first complete incumbent without a MIP start."""

    import highspy

    solver = _configure_hamming_solver(
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    solver.config.warmstart = False
    solver.set_instance(model)
    expected_variable_names = set(_variable_map(model))
    mapped_variable_names = {
        solver._vars[variable_id][0].name
        for variable_id in solver._pyomo_var_to_solver_var_map
    }
    if mapped_variable_names != expected_variable_names:
        raise ValueError("D50 HiGHS/Pyomo variable map is incomplete")
    captured: dict[str, Any] = {}

    def _callback(event: object) -> None:
        if captured:
            return
        raw = tuple(float(item) for item in event.data_out.mip_solution)
        primal_bound = float(event.data_out.mip_primal_bound)
        if len(raw) != len(solver._pyomo_var_to_solver_var_map):
            return
        if not all(math.isfinite(item) for item in raw):
            return
        captured["column_values"] = raw
        captured["reported_original_cost_objective"] = (
            primal_bound if math.isfinite(primal_bound) else None
        )
        event.interrupt()

    solver._solver_model.cbMipSolution.subscribe(_callback)
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(
            model,
            tee=True,
            load_solutions=False,
            warmstart=False,
        )
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    termination = str(results.solver.termination_condition).lower()
    model_status = solver._solver_model.getModelStatus()
    model_status_text = solver._solver_model.modelStatusToString(model_status)
    info = solver._solver_model.getInfo()
    solution = solver._solver_model.getSolution()
    solver_status = {
        "termination_condition": termination,
        "highs_model_status": model_status_text,
        "mip_node_count": int(getattr(info, "mip_node_count", -1)),
        "primal_solution_status": int(getattr(info, "primal_solution_status", -1)),
        "solution_value_valid": bool(getattr(solution, "value_valid", False)),
    }
    if not captured:
        return {
            "status": "block_path_no_incumbent",
            "incumbent_captured": False,
            "runtime_seconds": runtime,
            "solver_status": solver_status,
            "warmstart_requested": False,
            "formal_upper_bound_eligible": False,
        }
    index_to_variable = {
        column: solver._vars[variable_id][0]
        for variable_id, column in solver._pyomo_var_to_solver_var_map.items()
    }
    if set(index_to_variable) != set(range(len(captured["column_values"]))):
        raise ValueError("D50 HiGHS/Pyomo column map is incomplete")
    values: dict[str, float] = {}
    for column, number in enumerate(captured["column_values"]):
        variable = index_to_variable[column]
        variable.set_value(number, skip_validation=True)
        values[variable.name] = number
    return {
        "status": "block_stage_incumbent_captured",
        "incumbent_captured": True,
        "runtime_seconds": runtime,
        "solver_status": solver_status,
        "reported_original_cost_objective": captured[
            "reported_original_cost_objective"
        ],
        "variable_values": values,
        "variable_count": len(values),
        "expected_variable_count": len(expected_variable_names),
        "complete_variable_mapping": True,
        "variable_names_sha256": _name_list_sha256(tuple(sorted(values))),
        "warmstart_requested": False,
        "formal_upper_bound_eligible": False,
    }


def commit_stage_snapshot(
    model: object,
    layout: PhysicalTimeLayout,
    plan: StageDomainPlan,
    prior_snapshot: Mapping[str, int],
) -> tuple[dict[str, int], dict[str, Any]]:
    """Commit only the current block and the stage-zero global topology."""

    variables = _variable_map(model)
    current_names = tuple(
        name
        for position in range(
            plan.current_block.start_position, plan.current_block.stop_position
        )
        for name in layout.hourly_names[position]
    )
    commit_names = tuple(
        sorted(
            (*current_names, *layout.global_names)
            if plan.stage_index == 0
            else current_names
        )
    )
    expected_prior = set(plan.fixed_physical_names)
    if set(prior_snapshot) != expected_prior:
        raise ValueError("D50 prior snapshot does not match the fixed stage prefix")
    committed = dict(prior_snapshot)
    invalid: list[str] = []
    maximum_integrality_residual = 0.0
    for name in commit_names:
        raw = variables[name].value
        if raw is None or not math.isfinite(float(raw)):
            invalid.append(name)
            continue
        number = float(raw)
        rounded = int(round(number))
        residual = abs(number - rounded)
        maximum_integrality_residual = max(maximum_integrality_residual, residual)
        if rounded not in (0, 1) or residual > BINARY_VALUE_TOLERANCE:
            invalid.append(name)
            continue
        committed[name] = rounded
    expected_after = expected_prior | set(commit_names)
    passed = not invalid and set(committed) == expected_after
    return committed, {
        "stage_index": plan.stage_index,
        "prior_fixed_count": len(prior_snapshot),
        "current_commit_count": len(commit_names),
        "fixed_count_after_commit": len(committed),
        "commit_names_sha256": _name_list_sha256(commit_names),
        "fixed_names_sha256_after_commit": _name_list_sha256(
            tuple(sorted(committed))
        ),
        "maximum_integrality_residual": maximum_integrality_residual,
        "binary_tolerance": BINARY_VALUE_TOLERANCE,
        "invalid_commit_name_count": len(invalid),
        "invalid_commit_names_sha256": _name_list_sha256(tuple(sorted(invalid))),
        "lookahead_block_committed": False,
        "artificial_rounding_applied": False,
        "passed": passed,
    }


def write_physical_snapshot(
    path: Path,
    *,
    architecture: Architecture,
    stage_index: int,
    stage_count: int,
    snapshot: Mapping[str, int],
) -> dict[str, Any]:
    payload = {
        "schema_id": SNAPSHOT_SCHEMA_ID,
        "architecture": architecture.value,
        "completed_stage_index": stage_index,
        "stage_count": stage_count,
        "fixed_physical_count": len(snapshot),
        "fixed_physical_names_sha256": _name_list_sha256(tuple(sorted(snapshot))),
        "fixed_physical_values": {name: snapshot[name] for name in sorted(snapshot)},
    }
    _write_json(path, payload)
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "fixed_physical_count": len(snapshot),
        "fixed_physical_names_sha256": payload["fixed_physical_names_sha256"],
    }


def solve_block_relax_and_fix_candidate(
    model: object,
    inventory: BinaryInventory,
    chp_units: Sequence[object],
    *,
    architecture: Architecture,
    guide_path: Path,
    stage_output_dir: Path,
    progress_output_path: Path,
    physical_snapshot_output_path: Path,
    candidate_output_path: Path,
    commit_hours: int = COMMIT_HOURS,
    time_limit_seconds: float = STAGE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
    require_locked_guide_hash: bool = True,
    require_formal_counts: bool = True,
) -> dict[str, Any]:
    """Run all chronological stages on one clean, persistent Pyomo model."""

    if stage_output_dir.exists():
        raise FileExistsError(f"D50 stage output already exists: {stage_output_dir}")
    if progress_output_path.exists():
        raise FileExistsError(f"D50 progress output already exists: {progress_output_path}")
    stage_output_dir.mkdir(parents=True)
    partition, layout, blocks, preparation = prepare_d50_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        commit_hours=commit_hours,
        require_locked_guide_hash=require_locked_guide_hash,
        require_formal_counts=require_formal_counts,
    )
    if preparation["passed"] is not True:
        raise ValueError("D50 preparation audit failed")
    original_constraints = preparation["original_constraint_identity"]
    original_objective = preparation["original_objective_identity"]
    fixed_snapshot: dict[str, int] = {}
    stage_hashes: dict[str, str] = {}
    total_solver_runtime = 0.0
    for stage_index in range(len(blocks)):
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            stage_index,
        )
        domain_audit = apply_stage_domain_plan(
            model,
            inventory,
            plan,
            fixed_snapshot,
        )
        constraints_after = constraint_identity(model)
        objective_after = _objective_identity(model)
        identity_preserved = (
            constraints_after == original_constraints
            and objective_after == original_objective
        )
        if not domain_audit["passed"] or not identity_preserved:
            raise ValueError(f"D50 stage {stage_index} domain/identity audit failed")
        _append_progress(
            progress_output_path,
            {
                "event": "stage_started",
                "stage_index": stage_index,
                "stage_count": len(blocks),
                "current_block": domain_audit["current_block"],
                "lookahead_block": domain_audit["lookahead_block"],
                "incumbent_captured": False,
            },
        )
        capture = capture_first_original_cost_incumbent(
            model,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )
        total_solver_runtime += float(capture["runtime_seconds"])
        capture.pop("variable_values", None)
        if capture["incumbent_captured"] is not True:
            stage_payload = {
                "schema_id": STAGE_SCHEMA_ID,
                "status": "block_path_no_incumbent",
                "stage_index": stage_index,
                "stage_count": len(blocks),
                "domain_audit": domain_audit,
                "constraint_and_objective_identity_preserved": identity_preserved,
                "capture": capture,
                "formal_upper_bound_eligible": False,
            }
            stage_path = stage_output_dir / f"stage_{stage_index:02d}.json"
            _write_json(stage_path, stage_payload)
            stage_hashes[stage_path.name] = _sha256(stage_path)
            _append_progress(
                progress_output_path,
                {
                    "event": "stage_failed",
                    "stage_index": stage_index,
                    "stage_count": len(blocks),
                    "incumbent_captured": False,
                    "stage_result": str(stage_path),
                },
            )
            return {
                "status": "block_path_no_incumbent",
                "failed_stage_index": stage_index,
                "completed_stage_count": stage_index,
                "stage_count": len(blocks),
                "preparation_audit": preparation,
                "stage_result_sha256": stage_hashes,
                "total_solver_runtime_seconds": total_solver_runtime,
                "candidate_artifact": None,
                "formal_upper_bound_eligible": False,
            }
        fixed_snapshot, commit_audit = commit_stage_snapshot(
            model,
            layout,
            plan,
            fixed_snapshot,
        )
        if commit_audit["passed"] is not True:
            raise ValueError(f"D50 stage {stage_index} commit audit failed")
        stage_payload = {
            "schema_id": STAGE_SCHEMA_ID,
            "status": "block_stage_incumbent_committed",
            "stage_index": stage_index,
            "stage_count": len(blocks),
            "domain_audit": domain_audit,
            "constraint_and_objective_identity_preserved": identity_preserved,
            "capture": capture,
            "commit_audit": commit_audit,
            "formal_upper_bound_eligible": False,
        }
        stage_path = stage_output_dir / f"stage_{stage_index:02d}.json"
        _write_json(stage_path, stage_payload)
        stage_hashes[stage_path.name] = _sha256(stage_path)
        _append_progress(
            progress_output_path,
            {
                "event": "stage_committed",
                "stage_index": stage_index,
                "stage_count": len(blocks),
                "incumbent_captured": True,
                "fixed_physical_count": len(fixed_snapshot),
                "stage_result": str(stage_path),
            },
        )

    expected_physical = set(partition.physical_binary_names)
    physical_complete = set(fixed_snapshot) == expected_physical
    if not physical_complete:
        raise ValueError("D50 final physical snapshot is incomplete")
    physical_artifact = write_physical_snapshot(
        physical_snapshot_output_path,
        architecture=architecture,
        stage_index=len(blocks) - 1,
        stage_count=len(blocks),
        snapshot=fixed_snapshot,
    )
    try:
        lift_audit = exact_lift_fuel_encoding(model, chp_units)
        if lift_audit["passed"] is not True:
            raise ValueError("D50 exact fuel lift changed an unregistered variable")
        restore_binary_domains(model, inventory)
        snapshot = extract_binary_snapshot(
            model,
            inventory,
            tolerance=BINARY_VALUE_TOLERANCE,
        )
    except Exception as error:  # noqa: BLE001 - canonical failed-lift evidence
        return {
            "status": "final_exact_lift_failed",
            "completed_stage_count": len(blocks),
            "stage_count": len(blocks),
            "preparation_audit": preparation,
            "stage_result_sha256": stage_hashes,
            "physical_snapshot_artifact": physical_artifact,
            "exact_fuel_lift_audit": locals().get("lift_audit"),
            "exact_lift_error_type": type(error).__name__,
            "exact_lift_error_message": str(error),
            "candidate_artifact": None,
            "formal_upper_bound_eligible": False,
        }
    feasibility = _bound_and_constraint_audit(model)
    service = _service_audit(model)
    candidate_passed = feasibility["passed"] and service["passed"]
    artifact = None
    status = "final_exact_lift_failed"
    if candidate_passed:
        values = {
            name: float(variable.value)
            for name, variable in sorted(_variable_map(model).items())
        }
        artifact = write_seed_csv_gz(candidate_output_path, values, snapshot)
        status = "candidate_incumbent_captured_and_exactly_lifted"
    _append_progress(
        progress_output_path,
        {
            "event": "candidate_complete",
            "stage_index": len(blocks) - 1,
            "stage_count": len(blocks),
            "incumbent_captured": True,
            "candidate_status": status,
            "candidate_artifact": str(candidate_output_path) if artifact else None,
        },
    )
    return {
        "status": status,
        "completed_stage_count": len(blocks),
        "stage_count": len(blocks),
        "preparation_audit": preparation,
        "stage_result_sha256": stage_hashes,
        "total_solver_runtime_seconds": total_solver_runtime,
        "physical_snapshot_complete": physical_complete,
        "physical_snapshot_artifact": physical_artifact,
        "exact_fuel_lift_audit": lift_audit,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_service_audit": service,
        "candidate_audit_passed": candidate_passed,
        "binary_snapshot_variable_count": len(snapshot),
        "binary_snapshot_names_sha256": _name_list_sha256(tuple(sorted(snapshot))),
        "candidate_artifact": artifact,
        "candidate_requires_original_cost_repair": True,
        "formal_upper_bound_eligible": False,
    }


def solve_d50_original_cost_repair(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = solve_d49_original_cost_repair(*args, **kwargs)
    result["schema_id"] = REPAIR_SCHEMA_ID
    result["candidate_complete_physical_block_path_required"] = True
    return result


def _formal_base_payload(
    *,
    stage: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "architecture": Architecture.BESS.value,
        "stage": stage,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "representative_period_input_used": False,
        "service_contract_sha256": _sha256(service_path),
        "d40_gate_a_manifest_sha256": _sha256(d40_gate_a_manifest_path),
        "d41_gate_a_manifest_sha256": _sha256(d41_gate_a_manifest_path),
        "input_sha256": {
            "heat": _sha256(heat_path),
            "vre": _sha256(vre_path),
            "price_basis_tree": _tree_sha256(price_basis_path),
        },
        "provenance": {"code_sha256": _code_hashes()},
    }


def solve_candidate_child(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    guide_path: Path,
    stage_output_dir: Path,
    progress_output_path: Path,
    physical_snapshot_output_path: Path,
    candidate_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = STAGE_SOFT_TIME_LIMIT_SECONDS,
) -> dict[str, Any]:
    base = _formal_base_payload(
        stage="candidate",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    solver_invoked = False
    try:
        case, model, inventory, build_audit = build_original_stage_model(
            architecture=Architecture.BESS,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        candidate = solve_block_relax_and_fix_candidate(
            model,
            inventory,
            case.chp_units,
            architecture=Architecture.BESS,
            guide_path=guide_path,
            stage_output_dir=stage_output_dir,
            progress_output_path=progress_output_path,
            physical_snapshot_output_path=physical_snapshot_output_path,
            candidate_output_path=candidate_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_locked_guide_hash=True,
            require_formal_counts=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "single_clean_candidate_model_build": True,
            "build_audit": build_audit,
            **candidate,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "no_primal_status_closure",
            "solver_invoked": solver_invoked,
            "single_clean_candidate_model_build": True,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_upper_bound_eligible": False,
        }
    _write_json(result_output_path, payload)
    return payload


def solve_repair_child(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    candidate_path: Path,
    solution_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = REPAIR_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    base = _formal_base_payload(
        stage="repair",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    solver_invoked = False
    try:
        _, model, inventory, build_audit = build_original_stage_model(
            architecture=Architecture.BESS,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        repair = solve_d50_original_cost_repair(
            model,
            inventory,
            architecture=Architecture.BESS,
            candidate_path=candidate_path,
            solution_output_path=solution_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **repair,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "fixed_binary_repair_failed",
            "solver_invoked": solver_invoked,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    _write_json(result_output_path, payload)
    return payload


def write_gate_a_build_audit(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    guide_path: Path,
    result_output_path: Path,
) -> dict[str, Any]:
    """Build and domain-audit the formal model without calling optimize."""

    started = perf_counter()
    case, model, inventory, build_audit = build_original_stage_model(
        architecture=Architecture.BESS,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    partition, layout, blocks, preparation = prepare_d50_model(
        model,
        inventory,
        architecture=Architecture.BESS,
        guide_path=guide_path,
        require_locked_guide_hash=True,
        require_formal_counts=True,
    )
    selected_indices = (0, len(blocks) // 2, len(blocks) - 2, len(blocks) - 1)
    domain_audits: dict[str, Any] = {}
    original_constraints = constraint_identity(model)
    original_objective = _objective_identity(model)
    for stage_index in selected_indices:
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            stage_index,
        )
        synthetic_snapshot = {name: 0 for name in plan.fixed_physical_names}
        audit = apply_stage_domain_plan(
            model,
            inventory,
            plan,
            synthetic_snapshot,
        )
        audit["synthetic_zero_snapshot_used_for_domain_audit_only"] = True
        audit["constraint_identity_preserved"] = (
            constraint_identity(model) == original_constraints
        )
        audit["objective_identity_preserved"] = (
            _objective_identity(model) == original_objective
        )
        audit["passed"] = all(
            (
                audit["passed"],
                audit["constraint_identity_preserved"],
                audit["objective_identity_preserved"],
            )
        )
        domain_audits[str(stage_index)] = audit
    post_size = _linearity_audit(model)
    size_passed = all(
        (
            post_size["active_variable_count"]
            == EXPECTED_MODEL_SIZE[Architecture.BESS]["active_variable_count"],
            post_size["active_constraint_count"]
            == EXPECTED_MODEL_SIZE[Architecture.BESS]["active_constraint_count"],
            post_size["nonlinear_component_count"] == 0,
        )
    )
    static_lift = static_fuel_lift_spec_audit(case.chp_units)
    option_audit = highs_option_roundtrip()
    passed = all(
        (
            build_audit["binary_inventory_audit"]["passed"],
            build_audit["original_capacity_boundary_audit"]["passed"],
            preparation["passed"],
            size_passed,
            static_lift["passed"],
            option_audit["passed"],
            all(item["passed"] for item in domain_audits.values()),
        )
    )
    payload = {
        **_formal_base_payload(
            stage="gate_a_build_only",
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        ),
        "schema_id": BUILD_SCHEMA_ID,
        "status": "gate_a_build_passed" if passed else "gate_a_build_failed",
        "solver_invoked": False,
        "formal_optimization_invoked": False,
        "runtime_seconds": perf_counter() - started,
        "build_audit": build_audit,
        "d50_preparation_audit": preparation,
        "selected_stage_domain_audit": domain_audits,
        "post_domain_model_size": post_size,
        "model_size_identity_passed": size_passed,
        "static_fuel_lift_spec_audit": static_lift,
        "highs_option_roundtrip": option_audit,
        "audit": {"passed": passed},
    }
    _write_json(result_output_path, payload)
    return payload


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("candidate")
    _add_formal_inputs(candidate)
    candidate.add_argument("--guide", type=Path, required=True)
    candidate.add_argument("--stage-output-dir", type=Path, required=True)
    candidate.add_argument("--progress-output", type=Path, required=True)
    candidate.add_argument("--physical-snapshot-output", type=Path, required=True)
    candidate.add_argument("--candidate-output", type=Path, required=True)
    candidate.add_argument("--result-output", type=Path, required=True)
    candidate.add_argument("--threads", type=int, default=FORMAL_THREADS)
    candidate.add_argument(
        "--stage-time-limit", type=float, default=STAGE_SOFT_TIME_LIMIT_SECONDS
    )
    repair = commands.add_parser("repair")
    _add_formal_inputs(repair)
    repair.add_argument("--candidate", type=Path, required=True)
    repair.add_argument("--solution-output", type=Path, required=True)
    repair.add_argument("--result-output", type=Path, required=True)
    repair.add_argument("--threads", type=int, default=FORMAL_THREADS)
    repair.add_argument("--time-limit", type=float, default=REPAIR_HARD_WALL_SECONDS)
    gate_a = commands.add_parser("gate-a-build")
    _add_formal_inputs(gate_a)
    gate_a.add_argument("--guide", type=Path, required=True)
    gate_a.add_argument("--result-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    common = {
        "service_path": args.service,
        "d40_gate_a_manifest_path": args.d40_gate_a,
        "d41_gate_a_manifest_path": args.d41_gate_a,
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
    }
    if args.command == "candidate":
        solve_candidate_child(
            guide_path=args.guide,
            stage_output_dir=args.stage_output_dir,
            progress_output_path=args.progress_output,
            physical_snapshot_output_path=args.physical_snapshot_output,
            candidate_output_path=args.candidate_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.stage_time_limit,
            **common,
        )
        return
    if args.command == "repair":
        solve_repair_child(
            candidate_path=args.candidate,
            solution_output_path=args.solution_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit,
            **common,
        )
        return
    if args.command == "gate-a-build":
        write_gate_a_build_audit(
            guide_path=args.guide,
            result_output_path=args.result_output,
            **common,
        )
        return
    raise AssertionError(f"unhandled D50 command: {args.command}")


if __name__ == "__main__":
    main()
