from __future__ import annotations

import json
from pathlib import Path

import pytest


def _command_kwargs(tmp_path: Path) -> dict[str, Path]:
    return {
        "output_dir": tmp_path / "out",
        "guide_path": tmp_path / "guide.csv.gz",
        "service_path": tmp_path / "service.json",
        "d40_gate_a_manifest_path": tmp_path / "d40.json",
        "d41_gate_a_manifest_path": tmp_path / "d41.json",
        "heat_path": tmp_path / "heat.csv",
        "vre_path": tmp_path / "vre.csv",
        "price_basis_path": tmp_path / "price",
    }


def test_stage_commands_use_one_d50_candidate_child_and_frozen_options(
    tmp_path: Path,
) -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    kwargs = _command_kwargs(tmp_path)
    candidate, candidate_artifacts = executor.build_stage_command(
        stage="candidate", **kwargs
    )
    repair, repair_artifacts = executor.build_stage_command(stage="repair", **kwargs)
    assert (
        "tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix"
        in candidate
    )
    assert "candidate" in candidate
    assert "--stage-output-dir" in candidate
    assert candidate[candidate.index("--threads") + 1] == str(executor.FORMAL_THREADS)
    assert candidate[candidate.index("--stage-time-limit") + 1] == str(
        executor.STAGE_SOFT_TIME_LIMIT_SECONDS
    )
    assert "--guide" in candidate
    assert "--candidate" in repair
    assert candidate_artifacts[-1].name == "bess_candidate.csv.gz"
    assert repair_artifacts[-1].name == "bess_solution.csv.gz"
    with pytest.raises(ValueError, match="unknown D50 stage"):
        executor.build_stage_command(stage="tes", **kwargs)


def test_candidate_stage_hard_wall_uses_child_progress_clock() -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    latest = {
        "event": "stage_started",
        "stage_index": 7,
        "unix_time": 1000.0,
    }
    assert (
        executor._candidate_stage_stop_reason(latest, now_unix=1389.9) is None
    )
    assert executor._candidate_stage_stop_reason(
        latest, now_unix=1390.0
    ) == "stage_hard_wall"
    latest["event"] = "stage_committed"
    assert executor._candidate_stage_stop_reason(latest, now_unix=2000.0) is None


def test_resource_gate_warns_at_35_but_stops_at_45_gib() -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    assert executor._resource_stop_reason(
        elapsed_seconds=1.0,
        hard_wall_seconds=100.0,
        aggregate_rss_gib=35.0,
        available_memory_gib=90.0,
    ) is None
    assert executor._resource_stop_reason(
        elapsed_seconds=1.0,
        hard_wall_seconds=100.0,
        aggregate_rss_gib=45.0,
        available_memory_gib=90.0,
    ) == "aggregate_rss_stop"


def test_bess_gate_repairs_only_a_complete_exactly_lifted_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    kwargs = _command_kwargs(tmp_path)
    kwargs["guide_path"].write_bytes(b"guide")
    stages: list[str] = []

    def fake_run_monitored_stage(**call):
        stages.append(call["stage"])
        return {"status": "complete", "last_block_progress": None}

    def fake_load(_output_dir: Path, stage: str):
        if stage == "candidate":
            return {"status": "candidate_incumbent_captured_and_exactly_lifted"}
        return {
            "status": "audited_feasible_upper_bound_recovered",
            "solution_audit": {"audited_feasible_upper_bound_cny": "123.0"},
        }

    monkeypatch.setattr(executor, "run_monitored_stage", fake_run_monitored_stage)
    monkeypatch.setattr(executor, "_load_completed_result", fake_load)
    result = executor.run_bess_method_gate(**kwargs)
    assert stages == ["candidate", "repair"]
    assert result["status"] == "audited_feasible_upper_bound_recovered"
    assert result["audited_feasible_upper_bound_cny"] == "123.0"


@pytest.mark.parametrize(
    ("candidate_status", "expected"),
    [
        ("block_path_no_incumbent", "block_path_no_incumbent"),
        ("final_exact_lift_failed", "final_exact_lift_failed"),
        ("no_primal_status_closure", "no_primal_status_closure"),
    ],
)
def test_bess_gate_never_repairs_an_ineligible_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate_status: str,
    expected: str,
) -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    kwargs = _command_kwargs(tmp_path)
    kwargs["guide_path"].write_bytes(b"guide")
    stages: list[str] = []

    def fake_run_monitored_stage(**call):
        stages.append(call["stage"])
        return {"status": "complete", "last_block_progress": None}

    monkeypatch.setattr(executor, "run_monitored_stage", fake_run_monitored_stage)
    monkeypatch.setattr(
        executor,
        "_load_completed_result",
        lambda _output_dir, stage: (
            {"status": candidate_status} if stage == "candidate" else None
        ),
    )
    result = executor.run_bess_method_gate(**kwargs)
    assert stages == ["candidate"]
    assert result["status"] == expected


def test_gate_a_validation_requires_bess_only_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    monkeypatch.setattr(executor, "_code_hashes", lambda: {"core": "hash"})
    manifest_path = tmp_path / "gate_a_manifest.json"
    execution_path = tmp_path / "gate_a_execution.json"
    manifest = {
        "schema_id": executor.GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "formal_optimization_invoked": False,
        "formal_run_permitted": True,
        "formal_architecture_order": ["bess"],
        "tes_or_hybrid_formal_run_permitted": False,
        "audit": {"passed": True},
        "provenance": {"git_commit": "a" * 40, "code_sha256": {"core": "hash"}},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    execution_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "manifest_sha256": executor._sha256(manifest_path),
            }
        ),
        encoding="utf-8",
    )
    assert executor._validate_gate_a(manifest_path, execution_path)["passed"] is True
    manifest["formal_architecture_order"] = ["bess", "tes"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    execution_path.write_text(
        json.dumps(
            {
                "status": "complete",
                "manifest_sha256": executor._sha256(manifest_path),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="BESS-only"):
        executor._validate_gate_a(manifest_path, execution_path)


def test_predecessor_manifest_hashes_are_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d50_monitored_executor as executor

    d48 = tmp_path / "d48.json"
    d49 = tmp_path / "d49.json"
    d48.write_bytes(b"d48")
    d49.write_bytes(b"d49")
    real_sha = executor._sha256
    expected = {
        d48: executor.D48_R1_FORMAL_MANIFEST_SHA256,
        d49: executor.D49_FORMAL_MANIFEST_SHA256,
    }
    monkeypatch.setattr(executor, "_sha256", lambda path: expected.get(path, real_sha(path)))
    hashes = executor._validate_d50_predecessors(d48, d49)
    assert hashes["d48_r1_formal_manifest"] == executor.D48_R1_FORMAL_MANIFEST_SHA256
    d49.write_bytes(b"corrupted")
    monkeypatch.setattr(executor, "_sha256", real_sha)
    with pytest.raises(ValueError, match="predecessor"):
        executor._validate_d50_predecessors(d48, d49)
