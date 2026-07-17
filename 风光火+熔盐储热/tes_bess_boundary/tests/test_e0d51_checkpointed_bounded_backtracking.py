from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


def _small_checkpoint_model():
    from pyomo.environ import Binary, ConcreteModel, Constraint, Objective, Var

    model = ConcreteModel()
    model.x = Var((0, 1), domain=Binary)
    model.capacity_mw = Var(bounds=(0.0, 10.0))
    model.balance = Constraint(expr=model.capacity_mw >= model.x[0] + model.x[1])
    model.economic_objective = Objective(expr=2.0 * model.capacity_mw + model.x[0])
    model.x[0].set_value(1)
    model.x[1].set_value(0)
    model.capacity_mw.set_value(1.0)
    return model


def _record(stage: int, attempt: int, digit: str, values: tuple[tuple[str, int], ...]):
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        CommittedStageRecord,
    )

    return CommittedStageRecord(
        stage_index=stage,
        attempt_index=attempt,
        checkpoint_sha256=digit * 64,
        current_block_values=values,
    )


def test_state_machine_recovers_one_forced_dead_end() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        BoundedBacktrackingController,
        NO_GOOD_COMPONENT,
        NoGoodCutSpec,
        add_registered_no_good_cut,
    )

    controller = BoundedBacktrackingController(stage_count=3)
    assert controller.record_commit(_record(0, 0, "a", (("b0", 0),))).event == (
        "advance"
    )
    rejected_pattern = (("x[0]", 0), ("x[1]", 0))
    assert controller.record_commit(_record(1, 0, "b", rejected_pattern)).event == (
        "advance"
    )
    rollback = controller.record_failure(2)
    assert rollback.event == "rollback_one_block"
    assert rollback.next_stage_index == 1
    assert rollback.rejected_record == _record(1, 0, "b", rejected_pattern)
    assert controller.current_attempt_index == 1

    model = _small_checkpoint_model()
    spec = NoGoodCutSpec(
        stage_index=1,
        block_index=1,
        binary_values=rollback.rejected_record.current_block_values,
    )
    add_registered_no_good_cut(model, spec)
    cut = getattr(model, NO_GOOD_COMPONENT)[1]
    model.x[0].set_value(0)
    model.x[1].set_value(0)
    assert value(cut.body) == pytest.approx(0.0)
    model.x[0].set_value(1)
    assert value(cut.body) == pytest.approx(1.0)

    retried = controller.record_commit(
        _record(1, 1, "c", (("x[0]", 1), ("x[1]", 0)))
    )
    assert retried.event == "alternative_block_committed_retry_failed_frontier"
    assert controller.current_stage_index == 2
    completed = controller.record_commit(_record(2, 0, "d", (("b2", 1),)))
    assert completed.event == "path_complete"
    assert completed.terminal_status == "checkpointed_path_complete"
    assert controller.total_rollback_events == 1


def test_state_machine_closes_at_frozen_attempt_limit() -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        BoundedBacktrackingController,
    )

    controller = BoundedBacktrackingController(stage_count=3)
    controller.record_commit(_record(0, 0, "a", (("b0", 0),)))
    controller.record_commit(_record(1, 0, "b", (("b1", 0),)))

    first = controller.record_failure(2)
    assert first.event == "rollback_one_block"
    controller.record_commit(_record(1, 1, "c", (("b1", 1),)))
    second = controller.record_failure(2)
    assert second.event == "rollback_one_block"
    controller.record_commit(_record(1, 2, "d", (("b1", 0),)))
    terminal = controller.record_failure(2)
    assert terminal.event == "stage_attempt_budget_exhausted"
    assert terminal.terminal_status == "closed_no_checkpointed_path"


def test_state_machine_rejects_stage_zero_and_cascaded_rollback() -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        BoundedBacktrackingController,
    )

    zero = BoundedBacktrackingController(stage_count=2)
    assert zero.record_failure(0).event == "stage_zero_has_no_incumbent"

    controller = BoundedBacktrackingController(stage_count=3)
    controller.record_commit(_record(0, 0, "a", (("b0", 0),)))
    controller.record_commit(_record(1, 0, "b", (("b1", 0),)))
    controller.record_failure(2)
    terminal = controller.record_failure(1)
    assert terminal.event == "alternative_stage_itself_has_no_incumbent"
    assert terminal.terminal_status == "closed_no_checkpointed_path"


def test_state_machine_closes_when_total_rollback_budget_is_exhausted() -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        BoundedBacktrackingController,
        MAX_TOTAL_ROLLBACK_EVENTS,
    )

    controller = BoundedBacktrackingController(stage_count=3)
    controller.record_commit(_record(0, 0, "a", (("b0", 0),)))
    controller.record_commit(_record(1, 0, "b", (("b1", 0),)))
    controller.total_rollback_events = MAX_TOTAL_ROLLBACK_EVENTS
    terminal = controller.record_failure(2)
    assert terminal.event == "total_rollback_budget_exhausted"


def test_no_good_cut_excludes_only_the_registered_pattern() -> None:
    from pyomo.environ import Binary, Block, Var, value

    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        NO_GOOD_COMPONENT,
        NoGoodCutSpec,
        add_registered_no_good_cut,
    )

    model = _small_checkpoint_model()
    spec = NoGoodCutSpec(
        stage_index=0,
        block_index=0,
        binary_values=(("x[0]", 0), ("x[1]", 0)),
    )
    hashes: set[str] = set()
    add_registered_no_good_cut(model, spec, existing_sha256=hashes)
    constraint = getattr(model, NO_GOOD_COMPONENT)[1]

    model.x[0].set_value(0)
    model.x[1].set_value(0)
    assert value(constraint.body) == pytest.approx(0.0)
    assert value(constraint.lower) == pytest.approx(1.0)
    model.x[0].set_value(1)
    assert value(constraint.body) == pytest.approx(1.0)

    with pytest.raises(ValueError, match="duplicate"):
        add_registered_no_good_cut(model, spec, existing_sha256=hashes)

    nonbinary = NoGoodCutSpec(
        stage_index=0,
        block_index=0,
        binary_values=(("capacity_mw", 0),),
    )
    with pytest.raises(ValueError, match="not binary"):
        add_registered_no_good_cut(model, nonbinary)

    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    global_topology = NoGoodCutSpec(
        stage_index=0,
        block_index=0,
        binary_values=(("bess.installed", 0),),
    )
    with pytest.raises(ValueError, match="global topology"):
        add_registered_no_good_cut(model, global_topology)


def _write_small_checkpoint(tmp_path: Path, *, fixed_value: float = 1.0):
    from tes_bess_boundary.e0d48_hamming_primal_recovery import constraint_identity
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        NoGoodCutSpec,
        activate_feasibility_objective,
        add_registered_no_good_cut,
        write_attempt_checkpoint,
    )
    from tes_bess_boundary.model import Architecture

    model = _small_checkpoint_model()
    original_constraints = constraint_identity(model)
    objective = activate_feasibility_objective(model)
    spec = NoGoodCutSpec(
        stage_index=0,
        block_index=0,
        binary_values=(("x[0]", 0), ("x[1]", 0)),
    )
    add_registered_no_good_cut(model, spec)
    artifact = write_attempt_checkpoint(
        tmp_path / "checkpoints",
        architecture=Architecture.BESS,
        stage_index=0,
        attempt_index=0,
        parent_checkpoint_sha256=None,
        rollback_source_checkpoint_sha256=None,
        fixed_snapshot_after_commit={"x[0]": fixed_value},
        current_block_values={"x[0]": fixed_value},
        domain_audit={"passed": True},
        commit_audit={"passed": True},
        capture_audit={
            "incumbent_captured": True,
            "variable_values": {"must": "not be serialized"},
        },
        original_constraint_identity=original_constraints,
        current_constraint_identity=constraint_identity(model),
        objective_audit=objective,
        no_good_specs=(spec,),
        model=model,
    )
    return artifact


def test_atomic_checkpoint_round_trip_and_clean_replay(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        read_attempt_checkpoint,
        replay_attempt_checkpoint,
    )

    artifact = _write_small_checkpoint(tmp_path)
    manifest_path = Path(artifact["manifest_path"])
    payload, values = read_attempt_checkpoint(
        manifest_path,
        expected_parent_sha256=None,
    )
    assert set(values) == {"x[0]", "x[1]", "capacity_mw"}
    assert payload["capacity_variable_values"] == {"capacity_mw": 1.0}
    assert payload["capture_audit"] == {"incumbent_captured": True}
    assert payload["registered_no_good_cut_count"] == 1

    replay = replay_attempt_checkpoint(
        _small_checkpoint_model(),
        manifest_path,
        expected_parent_sha256=None,
    )
    assert replay["passed"] is True
    assert replay["variable_count"] == 3
    assert replay["fixed_physical_count"] == 1
    assert replay["registered_no_good_cut_count"] == 1


def test_checkpoint_rejects_hash_tampering_and_overwrite(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        read_attempt_checkpoint,
    )

    artifact = _write_small_checkpoint(tmp_path)
    manifest_path = Path(artifact["manifest_path"])
    values_path = Path(artifact["values_path"])
    values_path.write_bytes(values_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_attempt_checkpoint(manifest_path, expected_parent_sha256=None)

    with pytest.raises(FileExistsError, match="already exists"):
        _write_small_checkpoint(tmp_path)


def test_checkpoint_rejects_wrong_parent_and_corrupt_cut_hash(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        read_attempt_checkpoint,
    )

    artifact = _write_small_checkpoint(tmp_path)
    manifest_path = Path(artifact["manifest_path"])
    with pytest.raises(ValueError, match="parent hash"):
        read_attempt_checkpoint(
            manifest_path,
            expected_parent_sha256="f" * 64,
        )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["registered_no_good_cuts"][0]["cut_sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cut payload hash"):
        read_attempt_checkpoint(manifest_path, expected_parent_sha256=None)


def test_checkpoint_rejects_fractional_snapshot_and_replay_variable_drift(
    tmp_path: Path,
) -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        replay_attempt_checkpoint,
    )

    with pytest.raises(ValueError, match="fractional"):
        _write_small_checkpoint(tmp_path / "fractional", fixed_value=0.5)

    artifact = _write_small_checkpoint(tmp_path / "identity")
    drifted = _small_checkpoint_model()
    drifted.unregistered_variable = Var(bounds=(0.0, 1.0))
    with pytest.raises(ValueError, match="variable identity"):
        replay_attempt_checkpoint(
            drifted,
            Path(artifact["manifest_path"]),
            expected_parent_sha256=None,
        )


def test_feasibility_objective_restores_exact_original_identity() -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        activate_feasibility_objective,
        restore_original_economic_objective,
    )

    model = _small_checkpoint_model()
    audit = activate_feasibility_objective(model)
    assert audit["constant_zero_objective"] is True
    restored = restore_original_economic_objective(model, audit)
    assert restored["passed"] is True
    assert restored["restored_objective_identity"] == audit[
        "original_objective_identity"
    ]


def test_gate0_horizon_guard_forbids_formal_year() -> None:
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        gate0_period_count_audit,
    )

    assert gate0_period_count_audit(840)["passed"] is True
    forbidden = gate0_period_count_audit(8784)
    assert forbidden["passed"] is False
    assert forbidden["formal_8784h_optimization_invoked"] is False


def _write_junit(path: Path, names: tuple[str, ...], *, skipped: bool = False) -> None:
    cases = []
    for index, name in enumerate(names):
        marker = "<skipped/>" if skipped and index == 0 else ""
        cases.append(f'<testcase classname="d51" name="{name}">{marker}</testcase>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<testsuite tests="{len(names)}">{"".join(cases)}</testsuite>',
        encoding="utf-8",
    )


def test_gate0_manifest_compiler_keeps_formal_run_closed(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d51_gate0_evidence import (
        DEMONSTRATION_SCHEMA_ID,
        compile_gate0_manifest,
    )

    output = tmp_path / "bundle"
    output.mkdir()
    demonstration = output / "demonstration_result.json"
    demonstration.write_text(
        json.dumps(
            {
                "schema_id": DEMONSTRATION_SCHEMA_ID,
                "status": "gate0_24h_demonstration_passed",
                "formal_8784h_optimization_invoked": False,
            }
        ),
        encoding="utf-8",
    )
    required = (
        "test_state_machine_recovers_one_forced_dead_end",
        "test_atomic_checkpoint_round_trip_and_clean_replay",
        "test_24h_checkpointed_path_lifts_and_repairs_original_cost",
    )
    targeted = output / "targeted.xml"
    compatibility = output / "compatibility.xml"
    full = output / "full.xml"
    _write_junit(targeted, required)
    _write_junit(compatibility, ("compatibility",))
    _write_junit(full, ("full",))
    ruff = output / "ruff.log"
    pycompile = output / "pycompile.log"
    ruff.write_text("D51_RUFF_PASSED\n", encoding="utf-8")
    pycompile.write_text("D51_PYCOMPILE_PASSED\n", encoding="utf-8")
    manifest = compile_gate0_manifest(
        output_dir=output,
        demonstration_result_path=demonstration,
        targeted_junit_path=targeted,
        compatibility_junit_path=compatibility,
        full_junit_path=full,
        ruff_log_path=ruff,
        pycompile_log_path=pycompile,
        git_commit="a" * 40,
    )
    assert manifest["status"] == "gate0_controller_validated"
    assert manifest["formal_8784h_optimization_invoked"] is False
    assert manifest["formal_run_permitted"] is False
    assert manifest["formal_capacity_or_upper_bound_available"] is False


def test_gate0_manifest_compiler_rejects_linux_skip(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d51_gate0_evidence import (
        DEMONSTRATION_SCHEMA_ID,
        compile_gate0_manifest,
    )

    output = tmp_path / "bundle"
    output.mkdir()
    demonstration = output / "demonstration_result.json"
    demonstration.write_text(
        json.dumps(
            {
                "schema_id": DEMONSTRATION_SCHEMA_ID,
                "status": "gate0_24h_demonstration_passed",
                "formal_8784h_optimization_invoked": False,
            }
        ),
        encoding="utf-8",
    )
    required = (
        "test_state_machine_recovers_one_forced_dead_end",
        "test_atomic_checkpoint_round_trip_and_clean_replay",
        "test_24h_checkpointed_path_lifts_and_repairs_original_cost",
    )
    targeted = output / "targeted.xml"
    compatibility = output / "compatibility.xml"
    full = output / "full.xml"
    _write_junit(targeted, required, skipped=True)
    _write_junit(compatibility, ("compatibility",))
    _write_junit(full, ("full",))
    ruff = output / "ruff.log"
    pycompile = output / "pycompile.log"
    ruff.write_text("D51_RUFF_PASSED\n", encoding="utf-8")
    pycompile.write_text("D51_PYCOMPILE_PASSED\n", encoding="utf-8")
    with pytest.raises(ValueError, match="test evidence failed"):
        compile_gate0_manifest(
            output_dir=output,
            demonstration_result_path=demonstration,
            targeted_junit_path=targeted,
            compatibility_junit_path=compatibility,
            full_junit_path=full,
            ruff_log_path=ruff,
            pycompile_log_path=pycompile,
            git_commit="a" * 40,
        )


@pytest.mark.solver
@pytest.mark.integration
def test_gate0_24h_demonstration_persists_and_replays_every_checkpoint(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d51_gate0_evidence import (
        run_gate0_24h_demonstration,
    )

    output = tmp_path / "demonstration"
    result = run_gate0_24h_demonstration(
        output_dir=output,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert result["status"] == "gate0_24h_demonstration_passed"
    assert result["formal_8784h_optimization_invoked"] is False
    assert result["formal_run_permitted"] is False
    assert len(result["checkpoint_replay_audit"]) == 3
    assert all(
        item["replay_audit"]["stage_domain_replayed"]
        for item in result["checkpoint_replay_audit"]
    )
    assert (output / "demonstration_result.json").is_file()
    assert len(list((output / "checkpoints").glob("stage_*.json"))) == 3


@pytest.mark.solver
@pytest.mark.integration
def test_24h_checkpointed_path_lifts_and_repairs_original_cost(tmp_path: Path) -> None:
    from test_e0d50_full_year_coupled_physical_block_relax_and_fix import (
        _toy_case_and_model,
    )

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        fix_engineering_capacity_anchor,
        solve_continuous_guide,
    )
    from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
        make_stage_domain_plan,
        prepare_d50_model,
        read_attempt_checkpoint,
        replay_attempt_checkpoint,
        solve_d51_original_cost_repair,
        solve_gate0_checkpointed_candidate,
    )
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture, case, guide_model = _toy_case_and_model()
    guide_inventory = collect_binary_inventory(guide_model)
    assert fix_engineering_capacity_anchor(guide_model, architecture)["passed"]
    assert apply_relaxation(
        guide_model,
        guide_inventory,
        RelaxationMode.R0,
    )["passed"]
    guide_path = tmp_path / "guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=guide_path,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert guide["status"] == "continuous_guide_recovered"

    candidate_model = build_endogenous_capacity_model(case)
    candidate_inventory = collect_binary_inventory(candidate_model)
    candidate_path = tmp_path / "candidate.csv.gz"
    candidate = solve_gate0_checkpointed_candidate(
        candidate_model,
        candidate_inventory,
        case.chp_units,
        architecture=architecture,
        guide_path=guide_path,
        checkpoint_dir=tmp_path / "checkpoints",
        progress_output_path=tmp_path / "progress.jsonl",
        physical_snapshot_output_path=tmp_path / "physical.json",
        candidate_output_path=candidate_path,
        commit_hours=8,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert candidate["status"] == "gate0_checkpointed_candidate_exactly_lifted"
    assert candidate["controller_terminal_status"] == "checkpointed_path_complete"
    assert candidate["stage_count"] == 3
    assert candidate["checkpoint_count"] == 3
    assert candidate["total_rollback_events"] == 0
    assert candidate["candidate_audit_passed"] is True
    assert candidate["formal_8784h_optimization_invoked"] is False

    parent = None
    checkpoint_paths = sorted((tmp_path / "checkpoints").glob("stage_*.json"))
    for index, path in enumerate(checkpoint_paths):
        payload, values = read_attempt_checkpoint(
            path,
            expected_parent_sha256=parent,
        )
        assert payload["stage_index"] == index
        assert payload["attempt_index"] == 0
        assert payload["capacity_variable_values"]
        assert len(values) == payload["values_artifact"]["variable_count"]
        parent = candidate["checkpoint_manifest_sha256"][path.name]

    replay_model = build_endogenous_capacity_model(case)
    replay_inventory = collect_binary_inventory(replay_model)
    replay_partition, replay_layout, replay_blocks, _ = prepare_d50_model(
        replay_model,
        replay_inventory,
        architecture=architecture,
        guide_path=guide_path,
        commit_hours=8,
        require_locked_guide_hash=False,
        require_formal_counts=False,
    )
    replay_plan = make_stage_domain_plan(
        replay_layout,
        replay_blocks,
        replay_partition.projected_fuel_code_names,
        0,
    )
    replay = replay_attempt_checkpoint(
        replay_model,
        checkpoint_paths[0],
        expected_parent_sha256=None,
        inventory=replay_inventory,
        domain_plan=replay_plan,
    )
    assert replay["passed"] is True
    assert replay["stage_domain_replayed"] is True
    assert replay["stage_domain_replay_audit"]["passed"] is True

    repair_model = build_endogenous_capacity_model(case)
    repair_inventory = collect_binary_inventory(repair_model)
    repaired = solve_d51_original_cost_repair(
        repair_model,
        repair_inventory,
        architecture=architecture,
        candidate_path=candidate_path,
        solution_output_path=tmp_path / "solution.csv.gz",
        time_limit_seconds=30.0,
        threads=1,
        require_named_constraint_groups=True,
    )
    assert repaired["status"] == "audited_feasible_upper_bound_recovered"
    assert repaired["schema_id"].endswith("e0d51_original_cost_repair.v1")
    assert repaired["gate0_shortened_horizon_only"] is True
    upper = repaired["solution_audit"]["audited_feasible_upper_bound_cny"]
    assert upper is not None and math.isfinite(float(upper))
