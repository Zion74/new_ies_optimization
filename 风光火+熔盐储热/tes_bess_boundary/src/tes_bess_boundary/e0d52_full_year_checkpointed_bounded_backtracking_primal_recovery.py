"""E0-D-52 checkpointed bounded-backtracking BESS primal recovery.

The module promotes the D51 checkpoint mechanics into a separately guarded
full-year controller.  A rollback always discards the current Pyomo model,
rebuilds the original model through a caller-supplied clean builder, audits the
base identity, replays the accepted physical prefix, and reinstalls every
registered no-good cut in deterministic order.  Nothing in this module grants
formal execution permission; that gate belongs to :mod:`e0d52_monitored_executor`.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

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
    write_seed_csv_gz,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    FORMAL_THREADS,
    build_original_stage_model,
    constraint_identity,
)
from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
    exact_lift_fuel_encoding,
    static_fuel_lift_spec_audit,
)
from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
    BINARY_VALUE_TOLERANCE,
    COMMIT_HOURS,
    EXPECTED_FORMAL_HOURS,
    EXPECTED_FORMAL_LAST_BLOCK_HOURS,
    EXPECTED_FORMAL_STAGE_COUNT,
    INTEGER_LOOKAHEAD_HOURS,
    _objective_identity,
    apply_stage_domain_plan,
    commit_stage_snapshot,
    make_stage_domain_plan,
    prepare_d50_model,
    solve_d50_original_cost_repair,
    write_gate_a_build_audit as write_d50_gate_a_build_audit,
    write_physical_snapshot,
)
from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
    MAX_ATTEMPTS_PER_STAGE,
    MAX_ROLLBACK_DEPTH,
    NoGoodCutSpec,
    _atomic_publish,
    _canonical_json_bytes,
    _finite_model_values,
    _variable_boundary_identity,
    activate_feasibility_objective,
    add_registered_no_good_cut,
    capture_first_feasibility_incumbent,
    read_attempt_checkpoint,
    restore_original_economic_objective,
    write_attempt_checkpoint,
)
from tes_bess_boundary.model import Architecture


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d52_checkpointed_candidate.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d52_gate_a_build.v1"
DEMONSTRATION_SCHEMA_ID = "tes_bess_boundary.e0d52_gate_a_demonstration.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d52_original_cost_repair.v1"
ATTEMPT_FAILURE_SCHEMA_ID = "tes_bess_boundary.e0d52_attempt_failure.v1"

MAX_TOTAL_ROLLBACK_EVENTS = 8
MAX_SOLVER_ATTEMPTS = EXPECTED_FORMAL_STAGE_COUNT + 2 * MAX_TOTAL_ROLLBACK_EVENTS
STAGE_SOFT_TIME_LIMIT_SECONDS = 360.0
STAGE_HARD_WALL_SECONDS = 390.0
CLEAN_REBUILD_HARD_WALL_SECONDS = 390.0
CANDIDATE_TOTAL_HARD_WALL_SECONDS = 30_600.0
REPAIR_HARD_WALL_SECONDS = 1_500.0
TOTAL_HARD_WALL_SECONDS = 32_400.0
HEARTBEAT_INTERVAL_SECONDS = 30.0
PROCESS_TREE_RSS_WARNING_GIB = 35.0
AGGREGATE_RSS_STOP_GIB = 45.0
HOST_MEMORY_RESERVE_GIB = 30.0

D51_CORE_SHA256 = (
    "1b50ed42ebc31fb845dc5a1498abd5dcac38899eb09682ee809850504ea4d447"
)
D51_GATE0_MANIFEST_SHA256 = (
    "883d4c0bad9bb9e66011d769b5c7886bc09494f64fb68bcdf927ae65fb90d152"
)
D50_FORMAL_MANIFEST_SHA256 = (
    "3efdbba505ed2e34d14592e2384a67d074ae8ee08f35a32acdaa6b9639f10e91"
)
D52_CONTRACT_COMMIT = "5e6b58c791d74257c0d0e23269453c0f93af7295"


class CheckpointIntegrityError(RuntimeError):
    """A published checkpoint, cut chain, or clean replay failed identity audit."""


def _write_json_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_publish(path, _canonical_json_bytes(payload))


def _progress_append(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {"unix_time": __import__("time").time(), **payload},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery.py",
        "e0d52_monitored_executor.py",
        "e0d51_checkpointed_bounded_backtracking.py",
        "e0d50_full_year_coupled_physical_block_relax_and_fix.py",
        "e0d49_physics_first_fuel_projection_primal_recovery.py",
        "e0d48_hamming_primal_recovery.py",
        "e0d46_full_year_feasible_upper_bound_repair.py",
        "e0d41_strict_full_year_decomposition.py",
        "planning_model.py",
        "components/chp.py",
        "capacity_planning.py",
    )
    return {name: _sha256(package / name) for name in names}


def d51_core_identity_audit() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name(
        "e0d51_checkpointed_bounded_backtracking.py"
    )
    actual = _sha256(path)
    return {
        "path": path.name,
        "expected_sha256": D51_CORE_SHA256,
        "actual_sha256": actual,
        "unchanged": actual == D51_CORE_SHA256,
        "passed": actual == D51_CORE_SHA256,
    }


@dataclass(frozen=True)
class CleanModelBundle:
    """One independently constructed model and its immutable build evidence."""

    model: object
    inventory: BinaryInventory
    chp_units: tuple[object, ...]
    build_audit: Mapping[str, Any]


CleanModelBuilder = Callable[[], CleanModelBundle]
CaptureFunction = Callable[[object, int, int], dict[str, Any]]


@dataclass(frozen=True)
class CommittedStageRecord:
    stage_index: int
    attempt_index: int
    checkpoint_path: Path
    checkpoint_sha256: str
    current_block_values: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class BacktrackingTransition:
    event: str
    next_stage_index: int | None
    rejected_record: CommittedStageRecord | None = None
    terminal_status: str | None = None


@dataclass
class D52BoundedBacktrackingController:
    """Frozen one-block controller with an eight-event annual budget."""

    stage_count: int
    max_attempts_per_stage: int = MAX_ATTEMPTS_PER_STAGE
    max_total_rollback_events: int = MAX_TOTAL_ROLLBACK_EVENTS
    maximum_solver_attempts: int | None = None
    current_stage_index: int = 0
    rollback_anchor_stage_index: int | None = None
    total_rollback_events: int = 0
    solver_attempt_count: int = 0
    attempt_index_by_stage: dict[int, int] = field(default_factory=dict)
    committed_records: dict[int, CommittedStageRecord] = field(default_factory=dict)
    terminal_status: str | None = None

    def __post_init__(self) -> None:
        if self.stage_count <= 0:
            raise ValueError("D52 controller requires at least one stage")
        if self.max_attempts_per_stage != 3:
            raise ValueError("D52 attempt limit is frozen at three")
        if self.max_total_rollback_events != 8:
            raise ValueError("D52 rollback budget is frozen at eight")
        mechanical = self.stage_count + 2 * self.max_total_rollback_events
        if self.maximum_solver_attempts is None:
            self.maximum_solver_attempts = mechanical
        if self.maximum_solver_attempts != mechanical:
            raise ValueError("D52 solver-attempt budget does not match the contract")
        self.attempt_index_by_stage = {
            index: 0 for index in range(self.stage_count)
        }

    @property
    def current_attempt_index(self) -> int:
        return self.attempt_index_by_stage[self.current_stage_index]

    def record_attempt_started(self) -> int:
        if self.terminal_status is not None:
            raise ValueError("D52 controller is already terminal")
        self.solver_attempt_count += 1
        if self.solver_attempt_count > int(self.maximum_solver_attempts):
            raise RuntimeError("D52 solver-attempt budget exceeded")
        return self.solver_attempt_count

    def record_commit(self, record: CommittedStageRecord) -> BacktrackingTransition:
        if self.terminal_status is not None:
            raise ValueError("D52 controller is already terminal")
        if record.stage_index != self.current_stage_index:
            raise ValueError("D52 commit does not match the current stage")
        if record.attempt_index != self.current_attempt_index:
            raise ValueError("D52 commit does not match the current attempt")
        if not record.checkpoint_path.is_file():
            raise ValueError("D52 committed checkpoint is missing")
        if _sha256(record.checkpoint_path) != record.checkpoint_sha256:
            raise ValueError("D52 committed checkpoint hash mismatch")
        self.committed_records[record.stage_index] = record
        if (
            self.rollback_anchor_stage_index is not None
            and record.stage_index == self.rollback_anchor_stage_index - 1
        ):
            self.current_stage_index = self.rollback_anchor_stage_index
            return BacktrackingTransition(
                event="alternative_block_committed_retry_failed_frontier",
                next_stage_index=self.current_stage_index,
            )
        if self.rollback_anchor_stage_index == record.stage_index:
            self.rollback_anchor_stage_index = None
        self.current_stage_index = record.stage_index + 1
        if self.current_stage_index == self.stage_count:
            self.terminal_status = "checkpointed_path_complete"
            return BacktrackingTransition(
                event="path_complete",
                next_stage_index=None,
                terminal_status=self.terminal_status,
            )
        return BacktrackingTransition(
            event="advance",
            next_stage_index=self.current_stage_index,
        )

    def record_failure(self, stage_index: int) -> BacktrackingTransition:
        if self.terminal_status is not None:
            raise ValueError("D52 controller is already terminal")
        if stage_index != self.current_stage_index:
            raise ValueError("D52 failure does not match the current stage")
        if (
            self.rollback_anchor_stage_index is not None
            and stage_index == self.rollback_anchor_stage_index - 1
        ):
            return self._close("alternative_stage_itself_has_no_incumbent")
        if stage_index == 0:
            return self._close("stage_zero_has_no_incumbent")
        if self.total_rollback_events >= self.max_total_rollback_events:
            return self._close("total_rollback_budget_exhausted")
        target = stage_index - MAX_ROLLBACK_DEPTH
        rejected = self.committed_records.get(target)
        if rejected is None:
            return self._close("missing_rollback_checkpoint")
        next_attempt = self.attempt_index_by_stage[target] + 1
        if next_attempt >= self.max_attempts_per_stage:
            return self._close(
                "stage_attempt_budget_exhausted",
                rejected_record=rejected,
            )
        self.total_rollback_events += 1
        self.attempt_index_by_stage[target] = next_attempt
        self.rollback_anchor_stage_index = stage_index
        for index in tuple(self.committed_records):
            if index >= target:
                del self.committed_records[index]
        self.current_stage_index = target
        return BacktrackingTransition(
            event="rollback_one_block",
            next_stage_index=target,
            rejected_record=rejected,
        )

    def _close(
        self,
        reason: str,
        *,
        rejected_record: CommittedStageRecord | None = None,
    ) -> BacktrackingTransition:
        self.terminal_status = "closed_no_checkpointed_path"
        return BacktrackingTransition(
            event=reason,
            next_stage_index=None,
            rejected_record=rejected_record,
            terminal_status=self.terminal_status,
        )


def _current_block_values(
    committed: Mapping[str, int],
    prior: Mapping[str, int],
    *,
    global_names: Sequence[str],
) -> dict[str, int]:
    names = set(committed) - set(prior) - set(global_names)
    return {name: committed[name] for name in sorted(names)}


def _preparation_identity(preparation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "original_constraint_identity": preparation["original_constraint_identity"],
        "original_objective_identity": preparation["original_objective_identity"],
        "binary_partition_audit": preparation["binary_partition_audit"],
        "physical_time_layout_audit": preparation["physical_time_layout_audit"],
        "commit_block_coverage_audit": preparation["commit_block_coverage_audit"],
        "fuel_projection_dependency_audit": preparation[
            "fuel_projection_dependency_audit"
        ],
        "guide_identity_audit": preparation["guide_identity_audit"],
    }


def _attempt_failure_payload(
    *,
    stage_index: int,
    attempt_index: int,
    domain_audit: Mapping[str, Any],
    capture_audit: Mapping[str, Any],
    current_constraint_identity: Mapping[str, Any],
    objective_audit: Mapping[str, Any],
    no_good_specs: Sequence[NoGoodCutSpec],
    formal_year: bool,
) -> dict[str, Any]:
    capture = {key: value for key, value in capture_audit.items() if key != "variable_values"}
    return {
        "schema_id": ATTEMPT_FAILURE_SCHEMA_ID,
        "status": "stage_no_feasibility_incumbent",
        "stage_index": stage_index,
        "attempt_index": attempt_index,
        "domain_audit": dict(domain_audit),
        "capture_audit": capture,
        "current_constraint_identity": dict(current_constraint_identity),
        "objective_audit": dict(objective_audit),
        "registered_no_good_cuts": [item.payload() for item in no_good_specs],
        "formal_8784h_optimization_invoked": formal_year,
        "formal_upper_bound_eligible": False,
    }


def _read_parent_prefix(
    controller: D52BoundedBacktrackingController,
    target_stage: int,
) -> tuple[dict[str, int], dict[str, Any] | None, str | None]:
    if target_stage == 0:
        return {}, None, None
    parent = controller.committed_records.get(target_stage - 1)
    if parent is None:
        raise CheckpointIntegrityError(
            "D52 clean rebuild lacks the accepted parent checkpoint"
        )
    grandparent_hash = (
        controller.committed_records[target_stage - 2].checkpoint_sha256
        if target_stage > 1
        else None
    )
    try:
        payload, _ = read_attempt_checkpoint(
            parent.checkpoint_path,
            expected_parent_sha256=grandparent_hash,
        )
    except (OSError, ValueError) as error:
        raise CheckpointIntegrityError(
            "D52 clean rebuild parent checkpoint validation failed"
        ) from error
    if _sha256(parent.checkpoint_path) != parent.checkpoint_sha256:
        raise CheckpointIntegrityError(
            "D52 clean rebuild parent checkpoint hash drift"
        )
    if int(payload["stage_index"]) != target_stage - 1:
        raise CheckpointIntegrityError(
            "D52 clean rebuild parent checkpoint stage mismatch"
        )
    fixed = {
        str(name): int(value)
        for name, value in payload["fixed_physical_values_after_commit"].items()
    }
    return fixed, payload, parent.checkpoint_sha256


def solve_checkpointed_bounded_backtracking_candidate(
    builder: CleanModelBuilder,
    *,
    architecture: Architecture,
    guide_path: Path,
    checkpoint_dir: Path,
    attempt_result_dir: Path,
    progress_output_path: Path,
    physical_snapshot_output_path: Path,
    candidate_output_path: Path,
    commit_hours: int = COMMIT_HOURS,
    time_limit_seconds: float = STAGE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
    require_locked_guide_hash: bool = True,
    require_formal_counts: bool = True,
    capture_function: CaptureFunction | None = None,
) -> dict[str, Any]:
    """Run the D52 path; every rollback performs a clean model rebuild."""

    if architecture is not Architecture.BESS:
        raise ValueError("D52 formal recovery is frozen for BESS only")
    if commit_hours != COMMIT_HOURS and require_formal_counts:
        raise ValueError("D52 formal commit length is frozen at 168 hours")
    for path in (
        checkpoint_dir,
        attempt_result_dir,
        progress_output_path,
        physical_snapshot_output_path,
        candidate_output_path,
    ):
        if path.exists():
            raise FileExistsError(f"D52 refuses to overwrite {path}")
    if d51_core_identity_audit()["passed"] is not True:
        raise ValueError("D52 refuses a modified D51 checkpoint core")

    checkpoint_dir.mkdir(parents=True)
    attempt_result_dir.mkdir(parents=True)
    _progress_append(
        progress_output_path,
        {
            "event": "clean_rebuild_started",
            "target_stage_index": 0,
            "initial_clean_build": True,
            "rollback_source_checkpoint_sha256": None,
            "parent_checkpoint_sha256": None,
        },
    )
    bundle = builder()
    partition, layout, blocks, preparation = prepare_d50_model(
        bundle.model,
        bundle.inventory,
        architecture=architecture,
        guide_path=guide_path,
        commit_hours=commit_hours,
        require_locked_guide_hash=require_locked_guide_hash,
        require_formal_counts=require_formal_counts,
    )
    if preparation["passed"] is not True:
        raise ValueError("D52 initial model preparation failed")
    formal_year = len(layout.periods) == EXPECTED_FORMAL_HOURS
    if formal_year != require_formal_counts:
        raise PermissionError("D52 formal-year mode and horizon identity disagree")
    initial_preparation_identity = _preparation_identity(preparation)
    initial_boundary_identity = _variable_boundary_identity(bundle.model)
    objective_audit = activate_feasibility_objective(bundle.model)
    if objective_audit["passed"] is not True:
        raise ValueError("D52 feasibility objective audit failed")
    _progress_append(
        progress_output_path,
        {
            "event": "clean_rebuild_completed",
            "target_stage_index": 0,
            "initial_clean_build": True,
            "clean_rebuild_count": 0,
            "registered_cut_count": 0,
        },
    )

    controller = D52BoundedBacktrackingController(stage_count=len(blocks))
    fixed_snapshot: dict[str, int] = {}
    checkpoint_artifacts: list[dict[str, Any]] = []
    failure_artifacts: list[dict[str, Any]] = []
    clean_rebuild_audits: list[dict[str, Any]] = []
    no_good_specs: list[NoGoodCutSpec] = []
    installed_cut_hashes: set[str] = set()
    rollback_source_hash: str | None = None

    def default_capture(model: object, _stage: int, _attempt: int) -> dict[str, Any]:
        return capture_first_feasibility_incumbent(
            model,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )

    capture = capture_function or default_capture
    while controller.terminal_status is None:
        stage_index = controller.current_stage_index
        attempt_index = controller.current_attempt_index
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            stage_index,
        )
        domain_audit = apply_stage_domain_plan(
            bundle.model,
            bundle.inventory,
            plan,
            fixed_snapshot,
        )
        if domain_audit["passed"] is not True:
            raise ValueError("D52 stage domain audit failed")
        solver_attempt = controller.record_attempt_started()
        _progress_append(
            progress_output_path,
            {
                "event": "attempt_started",
                "stage_index": stage_index,
                "attempt_index": attempt_index,
                "solver_attempt_count": solver_attempt,
                "rollback_events": controller.total_rollback_events,
            },
        )
        captured = capture(bundle.model, stage_index, attempt_index)
        if captured.get("incumbent_captured") is not True:
            failure_path = attempt_result_dir / (
                f"stage_{stage_index:02d}_attempt_{attempt_index:02d}_failure.json"
            )
            _write_json_immutable(
                failure_path,
                _attempt_failure_payload(
                    stage_index=stage_index,
                    attempt_index=attempt_index,
                    domain_audit=domain_audit,
                    capture_audit=captured,
                    current_constraint_identity=constraint_identity(bundle.model),
                    objective_audit=objective_audit,
                    no_good_specs=no_good_specs,
                    formal_year=formal_year,
                ),
            )
            failure_artifacts.append(
                {"path": str(failure_path), "sha256": _sha256(failure_path)}
            )
            transition = controller.record_failure(stage_index)
            rejected = transition.rejected_record
            if rejected is not None:
                spec = NoGoodCutSpec(
                    stage_index=rejected.stage_index,
                    block_index=blocks[rejected.stage_index].index,
                    binary_values=rejected.current_block_values,
                )
                no_good_specs.append(spec)
                rollback_source_hash = rejected.checkpoint_sha256
            _progress_append(
                progress_output_path,
                {
                    "event": transition.event,
                    "stage_index": stage_index,
                    "attempt_index": attempt_index,
                    "next_stage_index": transition.next_stage_index,
                    "terminal_status": transition.terminal_status,
                },
            )
            if transition.terminal_status is not None:
                restored = restore_original_economic_objective(
                    bundle.model,
                    objective_audit,
                )
                return {
                    "schema_id": RESULT_SCHEMA_ID,
                    "status": "closed_no_checkpointed_path",
                    "closure_reason": transition.event,
                    "failed_stage_index": stage_index,
                    "stage_count": len(blocks),
                    "solver_attempt_count": controller.solver_attempt_count,
                    "maximum_solver_attempts": controller.maximum_solver_attempts,
                    "total_rollback_events": controller.total_rollback_events,
                    "checkpoint_artifacts": checkpoint_artifacts,
                    "attempt_failure_artifacts": failure_artifacts,
                    "clean_rebuild_audits": clean_rebuild_audits,
                    "registered_no_good_cuts": [item.payload() for item in no_good_specs],
                    "objective_restore_audit": restored,
                    "candidate_artifact": None,
                    "formal_8784h_optimization_invoked": formal_year,
                    "formal_upper_bound_eligible": False,
                }

            if rejected is None:
                raise AssertionError("D52 rollback lacks a rejected checkpoint")
            target = int(transition.next_stage_index)
            fixed_snapshot, parent_payload, parent_hash = _read_parent_prefix(
                controller,
                target,
            )
            _progress_append(
                progress_output_path,
                {
                    "event": "clean_rebuild_started",
                    "target_stage_index": target,
                    "rollback_source_checkpoint_sha256": rollback_source_hash,
                    "parent_checkpoint_sha256": parent_hash,
                },
            )
            rebuild_started = perf_counter()
            del bundle
            gc.collect()
            bundle = builder()
            partition, layout, blocks, rebuilt_preparation = prepare_d50_model(
                bundle.model,
                bundle.inventory,
                architecture=architecture,
                guide_path=guide_path,
                commit_hours=commit_hours,
                require_locked_guide_hash=require_locked_guide_hash,
                require_formal_counts=require_formal_counts,
            )
            preparation_match = (
                _preparation_identity(rebuilt_preparation)
                == initial_preparation_identity
            )
            boundary_match = (
                _variable_boundary_identity(bundle.model)
                == initial_boundary_identity
            )
            rebuilt_objective = activate_feasibility_objective(bundle.model)
            objective_match = rebuilt_objective == objective_audit
            installed_cut_hashes = set()
            try:
                for registered in no_good_specs:
                    add_registered_no_good_cut(
                        bundle.model,
                        registered,
                        existing_sha256=installed_cut_hashes,
                    )
            except (KeyError, TypeError, ValueError) as error:
                raise CheckpointIntegrityError(
                    "D52 registered no-good cut replay failed"
                ) from error
            fixed_names_match = set(fixed_snapshot) == set(
                make_stage_domain_plan(
                    layout,
                    blocks,
                    partition.projected_fuel_code_names,
                    target,
                ).fixed_physical_names
            )
            rebuild_audit = {
                "target_stage_index": target,
                "rollback_source_checkpoint_sha256": rollback_source_hash,
                "parent_checkpoint_sha256": parent_hash,
                "parent_checkpoint_stage_index": (
                    int(parent_payload["stage_index"])
                    if parent_payload is not None
                    else None
                ),
                "preparation_identity_reproduced": preparation_match,
                "variable_boundary_identity_reproduced": boundary_match,
                "objective_identity_reproduced": objective_match,
                "fixed_parent_prefix_replayed": fixed_names_match,
                "registered_cut_count_replayed": len(installed_cut_hashes),
                "registered_cut_order_sha256": hashlib.sha256(
                    "\n".join(
                        str(item.payload()["cut_sha256"]) for item in no_good_specs
                    ).encode("utf-8")
                ).hexdigest(),
                "runtime_seconds": perf_counter() - rebuild_started,
            }
            rebuild_audit["passed"] = all(
                (
                    preparation_match,
                    boundary_match,
                    objective_match,
                    fixed_names_match,
                    len(installed_cut_hashes) == len(no_good_specs),
                )
            )
            if rebuild_audit["passed"] is not True:
                raise CheckpointIntegrityError(
                    "D52 clean rollback replay identity mismatch"
                )
            clean_rebuild_audits.append(rebuild_audit)
            _progress_append(
                progress_output_path,
                {
                    "event": "clean_rebuild_completed",
                    "target_stage_index": target,
                    "clean_rebuild_count": len(clean_rebuild_audits),
                    "registered_cut_count": len(installed_cut_hashes),
                },
            )
            continue

        prior_snapshot = dict(fixed_snapshot)
        committed, commit_audit = commit_stage_snapshot(
            bundle.model,
            layout,
            plan,
            prior_snapshot,
        )
        if commit_audit["passed"] is not True:
            raise ValueError("D52 stage commit audit failed")
        block_values = _current_block_values(
            committed,
            prior_snapshot,
            global_names=layout.global_names,
        )
        parent_hash = (
            controller.committed_records[stage_index - 1].checkpoint_sha256
            if stage_index > 0
            else None
        )
        try:
            artifact = write_attempt_checkpoint(
                checkpoint_dir,
                architecture=architecture,
                stage_index=stage_index,
                attempt_index=attempt_index,
                parent_checkpoint_sha256=parent_hash,
                rollback_source_checkpoint_sha256=rollback_source_hash,
                fixed_snapshot_after_commit=committed,
                current_block_values=block_values,
                domain_audit=domain_audit,
                commit_audit=commit_audit,
                capture_audit=captured,
                original_constraint_identity=preparation[
                    "original_constraint_identity"
                ],
                current_constraint_identity=constraint_identity(bundle.model),
                objective_audit=objective_audit,
                no_good_specs=no_good_specs,
                model=bundle.model,
            )
        except (OSError, TypeError, ValueError) as error:
            raise CheckpointIntegrityError(
                "D52 atomic attempt checkpoint publication failed"
            ) from error
        checkpoint_artifacts.append(artifact)
        record = CommittedStageRecord(
            stage_index=stage_index,
            attempt_index=attempt_index,
            checkpoint_path=Path(str(artifact["manifest_path"])),
            checkpoint_sha256=str(artifact["manifest_sha256"]),
            current_block_values=tuple(sorted(block_values.items())),
        )
        try:
            transition = controller.record_commit(record)
        except ValueError as error:
            raise CheckpointIntegrityError(
                "D52 published checkpoint failed controller verification"
            ) from error
        fixed_snapshot = dict(committed)
        rollback_source_hash = None
        _progress_append(
            progress_output_path,
            {
                "event": "attempt_checkpointed",
                "stage_index": stage_index,
                "attempt_index": attempt_index,
                "checkpoint_sha256": artifact["manifest_sha256"],
                "next_event": transition.event,
                "next_stage_index": transition.next_stage_index,
            },
        )

    if controller.terminal_status != "checkpointed_path_complete":
        raise AssertionError("D52 controller reached an unknown terminal state")
    if set(fixed_snapshot) != set(partition.physical_binary_names):
        raise ValueError("D52 final physical snapshot is incomplete")
    physical_artifact = write_physical_snapshot(
        physical_snapshot_output_path,
        architecture=architecture,
        stage_index=len(blocks) - 1,
        stage_count=len(blocks),
        snapshot=fixed_snapshot,
    )
    objective_restore = restore_original_economic_objective(
        bundle.model,
        objective_audit,
    )
    try:
        lift_audit = exact_lift_fuel_encoding(bundle.model, bundle.chp_units)
        if lift_audit["passed"] is not True:
            raise ValueError("D52 exact fuel lift audit failed")
        restore_binary_domains(bundle.model, bundle.inventory)
        binary_snapshot = extract_binary_snapshot(
            bundle.model,
            bundle.inventory,
            tolerance=BINARY_VALUE_TOLERANCE,
        )
    except Exception as error:  # noqa: BLE001 - canonical terminal evidence
        return {
            "schema_id": RESULT_SCHEMA_ID,
            "status": "final_exact_lift_failed",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stage_count": len(blocks),
            "solver_attempt_count": controller.solver_attempt_count,
            "total_rollback_events": controller.total_rollback_events,
            "checkpoint_artifacts": checkpoint_artifacts,
            "attempt_failure_artifacts": failure_artifacts,
            "clean_rebuild_audits": clean_rebuild_audits,
            "physical_snapshot_artifact": physical_artifact,
            "objective_restore_audit": objective_restore,
            "candidate_artifact": None,
            "formal_8784h_optimization_invoked": formal_year,
            "formal_upper_bound_eligible": False,
        }
    feasibility = _bound_and_constraint_audit(bundle.model)
    service = _service_audit(bundle.model)
    passed = feasibility["passed"] and service["passed"]
    candidate_artifact = None
    status = "final_exact_lift_failed"
    if passed:
        candidate_artifact = write_seed_csv_gz(
            candidate_output_path,
            _finite_model_values(bundle.model),
            binary_snapshot,
        )
        status = "candidate_incumbent_captured_and_exactly_lifted"
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "status": status,
        "stage_count": len(blocks),
        "completed_stage_count": len(blocks),
        "solver_attempt_count": controller.solver_attempt_count,
        "maximum_solver_attempts": controller.maximum_solver_attempts,
        "total_rollback_events": controller.total_rollback_events,
        "checkpoint_count": len(checkpoint_artifacts),
        "checkpoint_artifacts": checkpoint_artifacts,
        "attempt_failure_artifacts": failure_artifacts,
        "clean_rebuild_audits": clean_rebuild_audits,
        "registered_no_good_cuts": [item.payload() for item in no_good_specs],
        "physical_snapshot_artifact": physical_artifact,
        "objective_restore_audit": objective_restore,
        "exact_fuel_lift_audit": lift_audit,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_service_audit": service,
        "candidate_audit_passed": passed,
        "binary_snapshot_variable_count": len(binary_snapshot),
        "binary_snapshot_names_sha256": _name_list_sha256(
            tuple(sorted(binary_snapshot))
        ),
        "candidate_artifact": candidate_artifact,
        "candidate_requires_original_cost_repair": True,
        "formal_8784h_optimization_invoked": formal_year,
        "formal_upper_bound_eligible": False,
    }


def solve_d52_original_cost_repair(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = solve_d50_original_cost_repair(*args, **kwargs)
    result["schema_id"] = REPAIR_SCHEMA_ID
    result["checkpointed_d52_candidate_required"] = True
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
        "stage": stage,
        "architecture": Architecture.BESS.value,
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
    checkpoint_dir: Path,
    attempt_result_dir: Path,
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
    build_count = 0

    def builder() -> CleanModelBundle:
        nonlocal build_count
        case, model, inventory, build_audit = build_original_stage_model(
            architecture=Architecture.BESS,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        build_count += 1
        return CleanModelBundle(
            model=model,
            inventory=inventory,
            chp_units=tuple(case.chp_units),
            build_audit=build_audit,
        )

    solver_invoked = False

    def capture(model: object, stage_index: int, attempt_index: int) -> dict[str, Any]:
        nonlocal solver_invoked
        solver_invoked = True
        return capture_first_feasibility_incumbent(
            model,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )

    try:
        result = solve_checkpointed_bounded_backtracking_candidate(
            builder,
            architecture=Architecture.BESS,
            guide_path=guide_path,
            checkpoint_dir=checkpoint_dir,
            attempt_result_dir=attempt_result_dir,
            progress_output_path=progress_output_path,
            physical_snapshot_output_path=physical_snapshot_output_path,
            candidate_output_path=candidate_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_locked_guide_hash=True,
            require_formal_counts=True,
            capture_function=capture,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "clean_model_build_count": build_count,
            **result,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        status = (
            "checkpoint_integrity_failure"
            if isinstance(error, CheckpointIntegrityError)
            else "no_primal_status_closure"
        )
        payload = {
            **base,
            "status": status,
            "solver_invoked": solver_invoked,
            "clean_model_build_count": build_count,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_8784h_optimization_invoked": solver_invoked,
            "formal_upper_bound_eligible": False,
        }
    _write_json_immutable(result_output_path, payload)
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
        repair = solve_d52_original_cost_repair(
            model,
            inventory,
            architecture=Architecture.BESS,
            candidate_path=candidate_path,
            solution_output_path=solution_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        payload = {**base, "solver_invoked": True, "build_audit": build_audit, **repair}
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "fixed_binary_repair_failed",
            "solver_invoked": solver_invoked,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    _write_json_immutable(result_output_path, payload)
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
    subordinate_d50_output_path: Path,
    result_output_path: Path,
) -> dict[str, Any]:
    """Prove formal structure and clean rollback rebuilding without optimize."""

    if subordinate_d50_output_path.exists() or result_output_path.exists():
        raise FileExistsError("D52 Gate A build outputs must be new")
    started = perf_counter()
    d50_build = write_d50_gate_a_build_audit(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        guide_path=guide_path,
        result_output_path=subordinate_d50_output_path,
    )
    if d50_build["audit"]["passed"] is not True:
        raise ValueError("D52 subordinate D50 build audit failed")
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
    base_constraint_identity = constraint_identity(model)
    base_objective_identity = _objective_identity(model)
    base_boundary_identity = _variable_boundary_identity(model)
    objective_audit = activate_feasibility_objective(model)
    plan = make_stage_domain_plan(
        layout,
        blocks,
        partition.projected_fuel_code_names,
        0,
    )
    domain = apply_stage_domain_plan(model, inventory, plan, {})
    cut_names = tuple(
        sorted(
            name
            for name in plan.active_physical_names
            if not name.endswith(".installed")
            and any(
                name in layout.hourly_names[position]
                for position in range(
                    plan.current_block.start_position,
                    plan.current_block.stop_position,
                )
            )
        )
    )
    synthetic = NoGoodCutSpec(
        stage_index=0,
        block_index=0,
        binary_values=tuple((name, 0) for name in cut_names),
    )
    synthetic_cut_hash = add_registered_no_good_cut(model, synthetic)
    cut_constraint_identity = constraint_identity(model)
    static_lift = static_fuel_lift_spec_audit(case.chp_units)
    model_size = _linearity_audit(model)
    d50_preparation = d50_build["d50_preparation_audit"]
    clean_rebuild = {
        "preparation_identity_reproduced": (
            _preparation_identity(preparation)
            == _preparation_identity(d50_preparation)
        ),
        "base_constraint_identity_reproduced": (
            base_constraint_identity == preparation["original_constraint_identity"]
        ),
        "base_objective_identity_reproduced": (
            base_objective_identity == preparation["original_objective_identity"]
        ),
        "variable_boundary_identity": base_boundary_identity,
        "zero_objective_installed": objective_audit["passed"],
        "stage_zero_domain_audit": domain,
        "synthetic_registered_cut_sha256": synthetic_cut_hash,
        "constraint_identity_changed_only_after_registered_cut": (
            cut_constraint_identity != base_constraint_identity
        ),
        "solver_invoked": False,
    }
    clean_rebuild["passed"] = all(
        (
            clean_rebuild["preparation_identity_reproduced"],
            clean_rebuild["base_constraint_identity_reproduced"],
            clean_rebuild["base_objective_identity_reproduced"],
            clean_rebuild["zero_objective_installed"],
            domain["passed"],
            clean_rebuild["constraint_identity_changed_only_after_registered_cut"],
        )
    )
    budget_audit = {
        "stage_count": len(blocks),
        "commit_hours": COMMIT_HOURS,
        "integer_lookahead_hours": INTEGER_LOOKAHEAD_HOURS,
        "last_block_hours": blocks[-1].hours,
        "maximum_rollback_events": MAX_TOTAL_ROLLBACK_EVENTS,
        "maximum_attempts_per_stage": MAX_ATTEMPTS_PER_STAGE,
        "maximum_solver_attempts": MAX_SOLVER_ATTEMPTS,
        "mechanical_identity": MAX_SOLVER_ATTEMPTS
        == EXPECTED_FORMAL_STAGE_COUNT + 2 * MAX_TOTAL_ROLLBACK_EVENTS,
    }
    budget_audit["passed"] = all(
        (
            budget_audit["stage_count"] == EXPECTED_FORMAL_STAGE_COUNT,
            budget_audit["last_block_hours"] == EXPECTED_FORMAL_LAST_BLOCK_HOURS,
            budget_audit["mechanical_identity"],
        )
    )
    core_identity = d51_core_identity_audit()
    passed = all(
        (
            d50_build["audit"]["passed"],
            build_audit["binary_inventory_audit"]["passed"],
            preparation["passed"],
            clean_rebuild["passed"],
            budget_audit["passed"],
            static_lift["passed"],
            core_identity["passed"],
            model_size["active_variable_count"]
            == EXPECTED_MODEL_SIZE[Architecture.BESS]["active_variable_count"],
            model_size["active_constraint_count"]
            == EXPECTED_MODEL_SIZE[Architecture.BESS]["active_constraint_count"] + 1,
            model_size["nonlinear_component_count"] == 0,
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
        "formal_8784h_optimization_invoked": False,
        "runtime_seconds": perf_counter() - started,
        "subordinate_d50_build_sha256": _sha256(subordinate_d50_output_path),
        "build_audit": build_audit,
        "preparation_audit": preparation,
        "clean_rebuild_replay_audit": clean_rebuild,
        "budget_audit": budget_audit,
        "static_fuel_lift_spec_audit": static_lift,
        "d51_core_identity_audit": core_identity,
        "post_synthetic_cut_model_size": model_size,
        "audit": {"passed": passed},
    }
    _write_json_immutable(result_output_path, payload)
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
    candidate.add_argument("--checkpoint-dir", type=Path, required=True)
    candidate.add_argument("--attempt-result-dir", type=Path, required=True)
    candidate.add_argument("--progress-output", type=Path, required=True)
    candidate.add_argument("--physical-snapshot-output", type=Path, required=True)
    candidate.add_argument("--candidate-output", type=Path, required=True)
    candidate.add_argument("--result-output", type=Path, required=True)
    candidate.add_argument("--threads", type=int, default=FORMAL_THREADS)
    candidate.add_argument(
        "--stage-time-limit",
        type=float,
        default=STAGE_SOFT_TIME_LIMIT_SECONDS,
    )
    repair = commands.add_parser("repair")
    _add_formal_inputs(repair)
    repair.add_argument("--candidate", type=Path, required=True)
    repair.add_argument("--solution-output", type=Path, required=True)
    repair.add_argument("--result-output", type=Path, required=True)
    repair.add_argument("--threads", type=int, default=FORMAL_THREADS)
    repair.add_argument("--time-limit", type=float, default=REPAIR_HARD_WALL_SECONDS)
    build = commands.add_parser("gate-a-build")
    _add_formal_inputs(build)
    build.add_argument("--guide", type=Path, required=True)
    build.add_argument("--subordinate-d50-output", type=Path, required=True)
    build.add_argument("--result-output", type=Path, required=True)
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
            checkpoint_dir=args.checkpoint_dir,
            attempt_result_dir=args.attempt_result_dir,
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
            subordinate_d50_output_path=args.subordinate_d50_output,
            result_output_path=args.result_output,
            **common,
        )
        return
    raise AssertionError(f"unhandled D52 command: {args.command}")


if __name__ == "__main__":
    main()
