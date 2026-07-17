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


def test_stage_commands_are_bess_only_and_use_d49_module(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d49_monitored_executor import build_stage_command

    kwargs = _command_kwargs(tmp_path)
    candidate, candidate_artifacts = build_stage_command(stage="candidate", **kwargs)
    repair, repair_artifacts = build_stage_command(stage="repair", **kwargs)
    assert (
        "tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery"
        in candidate
    )
    assert candidate[candidate.index("--architecture") + 1] == "bess"
    assert repair[repair.index("--architecture") + 1] == "bess"
    assert "--guide" in candidate
    assert "--candidate" in repair
    assert candidate_artifacts[-1].name == "bess_candidate.csv.gz"
    assert repair_artifacts[-1].name == "bess_solution.csv.gz"
    with pytest.raises(ValueError, match="unknown D49 stage"):
        build_stage_command(stage="tes", **kwargs)


def test_bess_gate_does_not_repair_a_failed_exact_lift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d49_monitored_executor as executor

    kwargs = _command_kwargs(tmp_path)
    kwargs["guide_path"].write_bytes(b"guide")
    stages: list[str] = []

    def fake_run_monitored_stage(**call):
        stages.append(call["stage"])
        return {"status": "complete"}

    def fake_load(_output_dir: Path, stage: str):
        if stage == "candidate":
            return {"status": "candidate_found_but_exact_lift_failed"}
        return None

    monkeypatch.setattr(executor, "run_monitored_stage", fake_run_monitored_stage)
    monkeypatch.setattr(executor, "_load_completed_result", fake_load)
    result = executor.run_bess_method_gate(**kwargs)
    assert stages == ["candidate"]
    assert result["status"] == "candidate_found_but_exact_lift_failed"
    assert result["repair_status"] is None


def test_bess_gate_repairs_only_an_exactly_lifted_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d49_monitored_executor as executor

    kwargs = _command_kwargs(tmp_path)
    kwargs["guide_path"].write_bytes(b"guide")
    stages: list[str] = []

    def fake_run_monitored_stage(**call):
        stages.append(call["stage"])
        return {"status": "complete"}

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


def test_gate_a_validation_requires_bess_only_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d49_monitored_executor as executor

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


def test_formal_manifest_contains_only_bess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d49_monitored_executor as executor

    input_paths = {
        "gate_a_manifest_path": tmp_path / "gate_a.json",
        "gate_a_execution_path": tmp_path / "gate_a_execution.json",
        "service_path": tmp_path / "service.json",
        "d40_gate_a_manifest_path": tmp_path / "d40.json",
        "d41_gate_a_manifest_path": tmp_path / "d41.json",
        "d46_formal_manifest_path": tmp_path / "d46.json",
        "d46_postmortem_bundle_path": tmp_path / "postmortem.json",
        "heat_path": tmp_path / "heat.csv",
        "vre_path": tmp_path / "vre.csv",
        "price_basis_path": tmp_path / "price",
    }
    guide_paths = {
        executor.Architecture.BESS: tmp_path / "bess.csv.gz",
        executor.Architecture.TES: tmp_path / "tes.csv.gz",
        executor.Architecture.HYBRID: tmp_path / "hybrid.csv.gz",
    }
    for path in (*input_paths.values(), *guide_paths.values()):
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        else:
            path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        executor,
        "_validate_gate_a",
        lambda *_args, **_kwargs: {"passed": True},
    )
    monkeypatch.setattr(
        executor,
        "_validate_formal_inputs",
        lambda **_kwargs: {"inputs": "locked"},
    )
    monkeypatch.setattr(executor, "_available_memory_gib", lambda: 100.0)
    monkeypatch.setattr(
        executor,
        "run_bess_method_gate",
        lambda **_kwargs: {
            "status": "no_primal_status_closure",
            "architecture": "bess",
        },
    )
    monkeypatch.setattr(executor, "_code_hashes", lambda: {"core": "hash"})
    result = executor.run_formal_bess_gate(
        output_dir=tmp_path / "formal",
        guide_paths=guide_paths,
        **input_paths,
    )
    assert result["architecture_order"] == ["bess"]
    assert set(result["architecture"]) == {"bess"}
    assert result["tes_or_hybrid_executed"] is False
