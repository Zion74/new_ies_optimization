from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_junit(path: Path, count: int = 2, *, skipped: bool = False) -> None:
    cases = []
    for index in range(count):
        marker = "<skipped/>" if skipped and index == 0 else ""
        cases.append(f'<testcase classname="d52" name="case_{index}">{marker}</testcase>')
    path.write_text(
        f'<testsuite tests="{count}">{"".join(cases)}</testsuite>',
        encoding="utf-8",
    )


def test_candidate_progress_hard_walls_are_event_specific() -> None:
    from tes_bess_boundary.e0d52_monitored_executor import (
        CLEAN_REBUILD_HARD_WALL_SECONDS,
        STAGE_HARD_WALL_SECONDS,
        _candidate_local_stop_reason,
    )

    now = 1_000.0
    assert _candidate_local_stop_reason(
        {"event": "attempt_started", "unix_time": now - STAGE_HARD_WALL_SECONDS},
        now_unix=now,
    ) == "attempt_hard_wall"
    assert _candidate_local_stop_reason(
        {
            "event": "clean_rebuild_started",
            "unix_time": now - CLEAN_REBUILD_HARD_WALL_SECONDS,
        },
        now_unix=now,
    ) == "clean_rebuild_hard_wall"
    assert _candidate_local_stop_reason(
        {"event": "attempt_checkpointed", "unix_time": 0.0},
        now_unix=now,
    ) is None


def test_formal_stage_command_has_frozen_parameters(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_monitored_executor import build_stage_command

    common = {
        "output_dir": tmp_path,
        "guide_path": tmp_path / "guide.gz",
        "service_path": tmp_path / "service.json",
        "d40_gate_a_manifest_path": tmp_path / "d40.json",
        "d41_gate_a_manifest_path": tmp_path / "d41.json",
        "heat_path": tmp_path / "heat.csv",
        "vre_path": tmp_path / "vre.csv",
        "price_basis_path": tmp_path / "prices",
    }
    command, _ = build_stage_command(stage="candidate", **common)
    joined = " ".join(command)
    assert "e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery" in joined
    assert "--threads 12" in joined
    assert "--stage-time-limit 360.0" in joined
    assert "--checkpoint-dir" in command
    repair, _ = build_stage_command(stage="repair", **common)
    assert "--time-limit 1500.0" in " ".join(repair)


def test_candidate_child_reports_no_solver_when_clean_build_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery as core

    files = {}
    for name in ("service", "d40", "d41", "heat", "vre"):
        path = tmp_path / f"{name}.txt"
        path.write_text(name, encoding="utf-8")
        files[name] = path
    prices = tmp_path / "prices"
    prices.mkdir()
    (prices / "basis.txt").write_text("price", encoding="utf-8")

    def failed_build(**_: object):
        raise RuntimeError("synthetic build failure")

    monkeypatch.setattr(core, "build_original_stage_model", failed_build)
    result = core.solve_candidate_child(
        service_path=files["service"],
        d40_gate_a_manifest_path=files["d40"],
        d41_gate_a_manifest_path=files["d41"],
        heat_path=files["heat"],
        vre_path=files["vre"],
        price_basis_path=prices,
        guide_path=tmp_path / "guide.gz",
        checkpoint_dir=tmp_path / "checkpoints",
        attempt_result_dir=tmp_path / "attempts",
        progress_output_path=tmp_path / "progress.jsonl",
        physical_snapshot_output_path=tmp_path / "physical.json",
        candidate_output_path=tmp_path / "candidate.gz",
        result_output_path=tmp_path / "result.json",
    )
    assert result["status"] == "no_primal_status_closure"
    assert result["solver_invoked"] is False
    assert result["formal_8784h_optimization_invoked"] is False


@pytest.mark.solver
@pytest.mark.integration
def test_gate_a_24h_demonstration_forces_clean_recovery(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_monitored_executor import (
        run_gate_a_24h_demonstration,
    )

    result = run_gate_a_24h_demonstration(
        output_dir=tmp_path / "demonstration",
        time_limit_seconds=30.0,
        threads=1,
    )
    assert result["status"] == "gate_a_demonstration_passed"
    assert result["fault_injected_frontier_failure"] is True
    assert result["total_rollback_events"] == 1
    assert result["solver_attempt_count"] == 5
    assert result["clean_model_build_count"] == 2
    assert len(result["checkpoint_replay_audit"]) == 4
    assert result["formal_8784h_optimization_invoked"] is False
    assert result["formal_run_permitted"] is False


def _gate_a_fixture(tmp_path: Path) -> dict[str, Path | str]:
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        BUILD_SCHEMA_ID,
        DEMONSTRATION_SCHEMA_ID,
        _code_hashes,
    )

    code_hashes = _code_hashes()
    build = tmp_path / "build.json"
    demo = tmp_path / "demo.json"
    _write_json(
        build,
        {
            "schema_id": BUILD_SCHEMA_ID,
            "status": "gate_a_build_passed",
            "solver_invoked": False,
            "formal_8784h_optimization_invoked": False,
            "provenance": {"code_sha256": code_hashes},
            "audit": {"passed": True},
        },
    )
    _write_json(
        demo,
        {
            "schema_id": DEMONSTRATION_SCHEMA_ID,
            "status": "gate_a_demonstration_passed",
            "formal_8784h_optimization_invoked": False,
            "fault_injected_frontier_failure": True,
            "total_rollback_events": 1,
            "solver_attempt_count": 5,
            "clean_model_build_count": 2,
            "candidate_status": "candidate_incumbent_captured_and_exactly_lifted",
            "repair_status": "audited_feasible_upper_bound_recovered",
            "checkpoint_replay_audit": [
                {"replay_audit": {"passed": True}} for _ in range(4)
            ],
            "provenance": {"code_sha256": code_hashes},
            "audit": {"passed": True},
        },
    )
    junit = []
    for name in ("targeted", "compatibility", "full"):
        path = tmp_path / f"{name}.xml"
        _write_junit(path)
        junit.append(path)
    ruff = tmp_path / "ruff.log"
    pycompile = tmp_path / "pycompile.log"
    ruff.write_text("D52_RUFF_PASSED\n", encoding="utf-8")
    pycompile.write_text("D52_PYCOMPILE_PASSED\n", encoding="utf-8")
    return {
        "output_dir": tmp_path / "gate_a",
        "build_path": build,
        "demonstration_path": demo,
        "targeted_junit_path": junit[0],
        "compatibility_junit_path": junit[1],
        "full_junit_path": junit[2],
        "ruff_log_path": ruff,
        "pycompile_log_path": pycompile,
        "implementation_git_commit": "a" * 40,
        "contract_git_commit": "5e6b58c791d74257c0d0e23269453c0f93af7295",
        "service_path": tmp_path / "service.json",
        "d40_gate_a_manifest_path": tmp_path / "d40.json",
        "d41_gate_a_manifest_path": tmp_path / "d41.json",
        "d46_formal_manifest_path": tmp_path / "d46.json",
        "d46_postmortem_bundle_path": tmp_path / "postmortem.json",
        "guide_path": tmp_path / "guide.gz",
        "heat_path": tmp_path / "heat.csv",
        "vre_path": tmp_path / "vre.csv",
        "price_basis_path": tmp_path / "prices",
        "d50_formal_manifest_path": tmp_path / "d50.json",
        "d51_gate0_manifest_path": tmp_path / "d51.json",
    }


def test_gate_a_compiler_closes_formal_optimization_and_binds_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d52_monitored_executor as executor

    kwargs = _gate_a_fixture(tmp_path)
    monkeypatch.setattr(executor, "_validate_frozen_inputs", lambda **_: {"frozen": "hash"})
    monkeypatch.setattr(executor, "_git_head", lambda: "a" * 40)
    result = executor.compile_gate_a_manifest(**kwargs)  # type: ignore[arg-type]
    assert result["status"] == "gate_a_passed"
    assert result["formal_8784h_optimization_invoked"] is False
    assert result["formal_run_permitted"] is True
    assert result["formal_architecture_order"] == ["bess"]
    assert result["tes_or_hybrid_formal_run_permitted"] is False
    assert result["frozen_method"]["maximum_solver_attempts"] == 69
    assert result["provenance"]["contract_git_commit"] == kwargs["contract_git_commit"]


def test_gate_a_compiler_rejects_skips_and_contract_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d52_monitored_executor as executor

    kwargs = _gate_a_fixture(tmp_path)
    monkeypatch.setattr(executor, "_validate_frozen_inputs", lambda **_: {"frozen": "hash"})
    monkeypatch.setattr(executor, "_git_head", lambda: "a" * 40)
    _write_junit(Path(kwargs["targeted_junit_path"]), skipped=True)
    with pytest.raises(ValueError, match="skips"):
        executor.compile_gate_a_manifest(**kwargs)  # type: ignore[arg-type]

    kwargs = _gate_a_fixture(tmp_path / "contract")
    kwargs["contract_git_commit"] = "b" * 40
    with pytest.raises(ValueError, match="contract commit"):
        executor.compile_gate_a_manifest(**kwargs)  # type: ignore[arg-type]


def test_gate_a_validator_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        _sha256,
    )
    from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
        D52_CONTRACT_COMMIT,
        _code_hashes,
    )
    import tes_bess_boundary.e0d52_monitored_executor as executor

    monkeypatch.setattr(executor, "_git_head", lambda: "a" * 40)

    manifest = tmp_path / "manifest.json"
    execution = tmp_path / "execution.json"
    payload = {
        "schema_id": executor.GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "formal_8784h_optimization_invoked": False,
        "formal_run_permitted": True,
        "formal_architecture_order": ["bess"],
        "tes_or_hybrid_formal_run_permitted": False,
        "audit": {"passed": True},
        "provenance": {
            "contract_git_commit": D52_CONTRACT_COMMIT,
            "implementation_git_commit": "a" * 40,
            "code_sha256": _code_hashes(),
        },
    }
    _write_json(manifest, payload)
    _write_json(execution, {"status": "complete", "manifest_sha256": _sha256(manifest)})
    assert executor._validate_gate_a(manifest, execution)["passed"] is True
    payload["provenance"]["code_sha256"] = {"drift": "1"}  # type: ignore[index]
    _write_json(manifest, payload)
    _write_json(execution, {"status": "complete", "manifest_sha256": _sha256(manifest)})
    with pytest.raises(ValueError, match="source differs"):
        executor._validate_gate_a(manifest, execution)


def test_formal_entry_rejects_existing_output_before_any_run(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d52_monitored_executor import run_formal_bess_gate

    output = tmp_path / "formal"
    output.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        run_formal_bess_gate(
            output_dir=output,
            host_formal_lock_path=tmp_path / "lock",
            gate_a_manifest_path=tmp_path / "gate.json",
            gate_a_execution_path=tmp_path / "execution.json",
            service_path=tmp_path / "service.json",
            d40_gate_a_manifest_path=tmp_path / "d40.json",
            d41_gate_a_manifest_path=tmp_path / "d41.json",
            d46_formal_manifest_path=tmp_path / "d46.json",
            d46_postmortem_bundle_path=tmp_path / "postmortem.json",
            guide_path=tmp_path / "guide.gz",
            heat_path=tmp_path / "heat.csv",
            vre_path=tmp_path / "vre.csv",
            price_basis_path=tmp_path / "prices",
            d50_formal_manifest_path=tmp_path / "d50.json",
            d51_gate0_manifest_path=tmp_path / "d51.json",
        )
