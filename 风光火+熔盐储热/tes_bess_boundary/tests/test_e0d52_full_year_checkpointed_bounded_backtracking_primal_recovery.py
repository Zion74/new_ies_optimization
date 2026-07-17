from __future__ import annotations

import json
from pathlib import Path

import pytest


def _checkpoint(tmp_path: Path, digit: str) -> tuple[Path, str]:
    path = tmp_path / f"{digit}.json"
    path.write_text(digit, encoding="utf-8")
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        _sha256,
    )

    return path, _sha256(path)


def _record(
    tmp_path: Path,
    stage: int,
    attempt: int,
    digit: str,
    values: tuple[tuple[str, int], ...],
):
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        CommittedStageRecord,
    )

    path, digest = _checkpoint(tmp_path, digit)
    return CommittedStageRecord(
        stage_index=stage,
        attempt_index=attempt,
        checkpoint_path=path,
        checkpoint_sha256=digest,
        current_block_values=values,
    )


def test_frozen_annual_budget_and_block_identity() -> None:
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        build_commit_blocks,
        commit_block_coverage_audit,
    )
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        COMMIT_HOURS,
        EXPECTED_FORMAL_HOURS,
        MAX_SOLVER_ATTEMPTS,
        MAX_TOTAL_ROLLBACK_EVENTS,
    )

    blocks = build_commit_blocks(tuple(range(EXPECTED_FORMAL_HOURS)))
    audit = commit_block_coverage_audit(
        tuple(range(EXPECTED_FORMAL_HOURS)),
        blocks,
        require_formal_counts=True,
    )
    assert audit["passed"] is True
    assert len(blocks) == 53
    assert blocks[-1].hours == 48
    assert COMMIT_HOURS == 168
    assert MAX_TOTAL_ROLLBACK_EVENTS == 8
    assert MAX_SOLVER_ATTEMPTS == 53 + 2 * 8 == 69


def test_d51_core_hash_remains_frozen() -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D51_CORE_SHA256,
        d51_core_identity_audit,
    )

    audit = d51_core_identity_audit()
    assert audit["passed"] is True
    assert audit["actual_sha256"] == D51_CORE_SHA256


def test_controller_clean_path_with_one_rollback(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D52BoundedBacktrackingController,
    )

    controller = D52BoundedBacktrackingController(stage_count=3)
    assert controller.maximum_solver_attempts == 19
    controller.record_attempt_started()
    controller.record_commit(
        _record(tmp_path, 0, 0, "a", (("block0", 0),))
    )
    controller.record_attempt_started()
    controller.record_commit(
        _record(tmp_path, 1, 0, "b", (("block1", 0),))
    )
    controller.record_attempt_started()
    rollback = controller.record_failure(2)
    assert rollback.event == "rollback_one_block"
    assert rollback.next_stage_index == 1
    assert rollback.rejected_record is not None
    assert controller.current_attempt_index == 1
    controller.record_attempt_started()
    transition = controller.record_commit(
        _record(tmp_path, 1, 1, "c", (("block1", 1),))
    )
    assert transition.event == "alternative_block_committed_retry_failed_frontier"
    controller.record_attempt_started()
    completed = controller.record_commit(
        _record(tmp_path, 2, 0, "d", (("block2", 1),))
    )
    assert completed.terminal_status == "checkpointed_path_complete"
    assert controller.solver_attempt_count == 5
    assert controller.total_rollback_events == 1


def test_controller_closes_at_three_patterns(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D52BoundedBacktrackingController,
    )

    controller = D52BoundedBacktrackingController(stage_count=3)
    controller.record_attempt_started()
    controller.record_commit(_record(tmp_path, 0, 0, "a", (("b0", 0),)))
    controller.record_attempt_started()
    controller.record_commit(_record(tmp_path, 1, 0, "b", (("b1", 0),)))
    for attempt, digit in ((1, "c"), (2, "d")):
        controller.record_attempt_started()
        assert controller.record_failure(2).event == "rollback_one_block"
        controller.record_attempt_started()
        controller.record_commit(
            _record(tmp_path, 1, attempt, digit, (("b1", attempt % 2),))
        )
    controller.record_attempt_started()
    terminal = controller.record_failure(2)
    assert terminal.event == "stage_attempt_budget_exhausted"
    assert terminal.rejected_record is not None
    assert terminal.rejected_record.attempt_index == 2
    assert terminal.terminal_status == "closed_no_checkpointed_path"


def test_controller_closes_for_stage_zero_alternative_failure_and_total_budget(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D52BoundedBacktrackingController,
        MAX_TOTAL_ROLLBACK_EVENTS,
    )

    zero = D52BoundedBacktrackingController(stage_count=2)
    zero.record_attempt_started()
    assert zero.record_failure(0).event == "stage_zero_has_no_incumbent"

    alternative = D52BoundedBacktrackingController(stage_count=3)
    alternative.record_attempt_started()
    alternative.record_commit(_record(tmp_path, 0, 0, "a", (("b0", 0),)))
    alternative.record_attempt_started()
    alternative.record_commit(_record(tmp_path, 1, 0, "b", (("b1", 0),)))
    alternative.record_attempt_started()
    alternative.record_failure(2)
    alternative.record_attempt_started()
    terminal = alternative.record_failure(1)
    assert terminal.event == "alternative_stage_itself_has_no_incumbent"

    budget = D52BoundedBacktrackingController(stage_count=3)
    budget.record_attempt_started()
    budget.record_commit(_record(tmp_path, 0, 0, "c", (("b0", 0),)))
    budget.record_attempt_started()
    budget.record_commit(_record(tmp_path, 1, 0, "d", (("b1", 0),)))
    budget.total_rollback_events = MAX_TOTAL_ROLLBACK_EVENTS
    budget.record_attempt_started()
    exhausted = budget.record_failure(2)
    assert exhausted.event == "total_rollback_budget_exhausted"


def test_controller_rejects_result_after_budget_changes() -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D52BoundedBacktrackingController,
    )

    with pytest.raises(ValueError, match="attempt limit"):
        D52BoundedBacktrackingController(stage_count=53, max_attempts_per_stage=4)
    with pytest.raises(ValueError, match="rollback budget"):
        D52BoundedBacktrackingController(stage_count=53, max_total_rollback_events=9)
    with pytest.raises(ValueError, match="solver-attempt budget"):
        D52BoundedBacktrackingController(stage_count=53, maximum_solver_attempts=70)


def test_no_good_cut_rejects_capacity_and_global_topology() -> None:
    from pyomo.environ import Binary, ConcreteModel, Objective, Var

    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        NoGoodCutSpec,
        add_registered_no_good_cut,
    )

    model = ConcreteModel()
    model.x = Var(domain=Binary)
    model.capacity_mw = Var(bounds=(0.0, 10.0))
    model.installed = Var(domain=Binary)
    model.installed._name = "bess.installed"
    model.obj = Objective(expr=model.capacity_mw)
    with pytest.raises(ValueError, match="not binary"):
        add_registered_no_good_cut(
            model,
            NoGoodCutSpec(0, 0, (("capacity_mw", 0),)),
        )


def test_formal_candidate_requires_bess_and_new_paths(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        solve_checkpointed_bounded_backtracking_candidate,
    )
    from tes_bess_boundary.model import Architecture

    existing = tmp_path / "checkpoints"
    existing.mkdir()
    with pytest.raises(ValueError, match="BESS only"):
        solve_checkpointed_bounded_backtracking_candidate(
            lambda: None,  # type: ignore[arg-type,return-value]
            architecture=Architecture.TES,
            guide_path=tmp_path / "guide.gz",
            checkpoint_dir=existing,
            attempt_result_dir=tmp_path / "attempts",
            progress_output_path=tmp_path / "progress.jsonl",
            physical_snapshot_output_path=tmp_path / "physical.json",
            candidate_output_path=tmp_path / "candidate.gz",
        )


def test_initial_clean_build_is_visible_before_builder_runs(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        solve_checkpointed_bounded_backtracking_candidate,
    )
    from tes_bess_boundary.model import Architecture

    progress = tmp_path / "progress.jsonl"

    def failed_builder():
        raise RuntimeError("synthetic clean-build failure")

    with pytest.raises(RuntimeError, match="clean-build failure"):
        solve_checkpointed_bounded_backtracking_candidate(
            failed_builder,
            architecture=Architecture.BESS,
            guide_path=tmp_path / "guide.gz",
            checkpoint_dir=tmp_path / "checkpoints",
            attempt_result_dir=tmp_path / "attempts",
            progress_output_path=progress,
            physical_snapshot_output_path=tmp_path / "physical.json",
            candidate_output_path=tmp_path / "candidate.gz",
        )
    first = json.loads(progress.read_text(encoding="utf-8").splitlines()[0])
    assert first["event"] == "clean_rebuild_started"
    assert first["initial_clean_build"] is True
