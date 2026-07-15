from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def test_d46_resource_stop_priority_and_strict_thresholds() -> None:
    from tes_bess_boundary.e0d46_monitored_executor import monitor_stop_reason

    common = {
        "hard_wall_seconds": 100.0,
        "child_tree_rss_gib": 1.0,
        "aggregate_rss_gib": 2.0,
        "available_memory_gib": 80.0,
    }
    assert monitor_stop_reason(elapsed_seconds=99.0, **common) is None
    assert (
        monitor_stop_reason(elapsed_seconds=100.0, **common)
        == "hard_wall_clock_reached"
    )
    assert (
        monitor_stop_reason(
            elapsed_seconds=1.0,
            **{**common, "child_tree_rss_gib": 35.0},
        )
        == "process_tree_rss_limit_reached"
    )
    assert (
        monitor_stop_reason(
            elapsed_seconds=1.0,
            **{**common, "aggregate_rss_gib": 45.0},
        )
        == "aggregate_rss_limit_reached"
    )
    assert (
        monitor_stop_reason(
            elapsed_seconds=1.0,
            **{**common, "available_memory_gib": 29.999},
        )
        == "host_memory_reserve_breached"
    )


@pytest.mark.parametrize("stage", ["guide", "candidate", "repair_a", "repair_b"])
def test_stage_commands_are_highs_only_and_preregistered(
    tmp_path: Path,
    stage: str,
) -> None:
    from tes_bess_boundary.e0d46_monitored_executor import build_stage_command
    from tes_bess_boundary.model import Architecture

    command, artifacts = build_stage_command(
        architecture=Architecture.BESS,
        stage=stage,
        output_dir=tmp_path,
        service_path=tmp_path / "service.json",
        d40_gate_a_manifest_path=tmp_path / "d40.json",
        d41_gate_a_manifest_path=tmp_path / "d41.json",
        heat_path=tmp_path / "heat.xlsx",
        vre_path=tmp_path / "vre.csv",
        price_basis_path=tmp_path / "prices",
        d41_bess_guide_path=tmp_path / "d41_bess_guide.csv.gz",
    )
    rendered = " ".join(command).lower()

    assert "gurobi" not in rendered
    assert "e0d46_full_year_feasible_upper_bound_repair" in rendered
    assert "--threads 12" in rendered
    assert artifacts[0].name == f"bess_{stage}.json"
    if stage == "guide":
        assert "--time-limit-seconds 900.0" in rendered
    if stage == "candidate":
        assert "--time-limit-seconds 3600.0" in rendered
    if stage.startswith("repair"):
        assert "--time-limit-seconds 1500.0" in rendered


def test_d47_permission_requires_hashes_and_explicit_boolean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d46_monitored_executor as executor

    manifest = tmp_path / "manifest.json"
    execution = tmp_path / "execution.json"
    manifest.write_text(
        json.dumps({"d46_feasible_upper_bound_contract_permitted": True}),
        encoding="utf-8",
    )
    execution.write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    monkeypatch.setattr(
        executor,
        "D47_FORMAL_MANIFEST_SHA256",
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        executor,
        "D47_FORMAL_EXECUTION_SHA256",
        hashlib.sha256(execution.read_bytes()).hexdigest(),
    )

    audit = executor._validate_d47_permission(manifest, execution)
    assert audit["permission"] is True

    manifest.write_text(
        json.dumps({"d46_feasible_upper_bound_contract_permitted": False}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        executor,
        "D47_FORMAL_MANIFEST_SHA256",
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="did not permit"):
        executor._validate_d47_permission(manifest, execution)


def test_formal_batch_refuses_existing_output_before_any_run(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d46_monitored_executor import run_formal_batch

    output = tmp_path / "formal"
    output.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        run_formal_batch(
            output_dir=output,
            d47_manifest_path=tmp_path / "d47_manifest.json",
            d47_execution_path=tmp_path / "d47_execution.json",
            d46_gate_a_manifest_path=tmp_path / "d46_gate_a_manifest.json",
            d46_gate_a_execution_path=tmp_path / "d46_gate_a_execution.json",
            service_path=tmp_path / "service.json",
            d40_gate_a_manifest_path=tmp_path / "d40.json",
            d41_gate_a_manifest_path=tmp_path / "d41.json",
            heat_path=tmp_path / "heat.xlsx",
            vre_path=tmp_path / "vre.csv",
            price_basis_path=tmp_path / "prices",
            d41_bess_guide_path=tmp_path / "d41_bess_guide.csv.gz",
        )
