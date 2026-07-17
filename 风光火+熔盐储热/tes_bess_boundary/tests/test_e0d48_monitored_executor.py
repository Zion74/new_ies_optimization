from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.parametrize("stage", ["candidate", "repair"])
def test_stage_commands_are_highs_only_and_preregistered(
    tmp_path: Path,
    stage: str,
) -> None:
    from tes_bess_boundary.e0d48_monitored_executor import build_stage_command
    from tes_bess_boundary.model import Architecture

    command, artifacts = build_stage_command(
        architecture=Architecture.BESS,
        stage=stage,
        output_dir=tmp_path,
        guide_path=tmp_path / "guide.csv.gz",
        service_path=tmp_path / "service.json",
        d40_gate_a_manifest_path=tmp_path / "d40.json",
        d41_gate_a_manifest_path=tmp_path / "d41.json",
        heat_path=tmp_path / "heat.xlsx",
        vre_path=tmp_path / "vre.csv",
        price_basis_path=tmp_path / "prices",
    )
    rendered = " ".join(command).lower()

    assert "gurobi" not in rendered
    assert "e0d48_hamming_primal_recovery" in rendered
    assert "--threads 12" in rendered
    assert artifacts[0].name == f"bess_{stage}.json"
    if stage == "candidate":
        assert "--time-limit 3600.0" in rendered
        assert artifacts[1].name == "bess_candidate.csv.gz"
    else:
        assert "--time-limit 1500.0" in rendered
        assert artifacts[1].name == "bess_solution.csv.gz"


@pytest.mark.parametrize(
    ("candidate_status", "expected_status", "expected_stages"),
    [
        (
            "candidate_incumbent_captured",
            "audited_feasible_upper_bound_recovered",
            ["candidate", "repair"],
        ),
        (
            "engineering_mip_infeasible_under_original_bounds",
            "engineering_mip_infeasible_under_original_bounds",
            ["candidate"],
        ),
        ("no_primal_status_closure", "no_primal_status_closure", ["candidate"]),
    ],
)
def test_architecture_route_has_no_fallback_or_second_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate_status: str,
    expected_status: str,
    expected_stages: list[str],
) -> None:
    import tes_bess_boundary.e0d48_monitored_executor as executor
    from tes_bess_boundary.model import Architecture

    guide = tmp_path / "guide.csv.gz"
    guide.write_bytes(b"locked-guide")
    stages: list[str] = []

    def fake_stage(**kwargs: object) -> dict[str, object]:
        stage = str(kwargs["stage"])
        architecture = kwargs["architecture"]
        output_dir = Path(kwargs["output_dir"])
        assert architecture is Architecture.BESS
        stages.append(stage)
        paths = executor._stage_paths(output_dir, architecture, stage)
        result = (
            {"status": candidate_status}
            if stage == "candidate"
            else {
                "status": "audited_feasible_upper_bound_recovered",
                "solution_audit": {
                    "audited_feasible_upper_bound_cny": 123.0,
                },
            }
        )
        executor._write_json(paths["result"], result)
        execution = {
            "status": "complete",
            "result_sha256": executor._sha256(paths["result"]),
        }
        executor._write_json(paths["execution"], execution)
        return execution

    monkeypatch.setattr(executor, "run_monitored_stage", fake_stage)
    result = executor.run_architecture(
        architecture=Architecture.BESS,
        output_dir=tmp_path,
        guide_path=guide,
        service_path=tmp_path / "service.json",
        d40_gate_a_manifest_path=tmp_path / "d40.json",
        d41_gate_a_manifest_path=tmp_path / "d41.json",
        heat_path=tmp_path / "heat.xlsx",
        vre_path=tmp_path / "vre.csv",
        price_basis_path=tmp_path / "prices",
    )

    assert stages == expected_stages
    assert result["status"] == expected_status
    assert "repair_b" not in json.dumps(result)


def test_formal_batch_refuses_existing_output_before_validation(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d48_monitored_executor import run_formal_batch
    from tes_bess_boundary.model import Architecture

    output = tmp_path / "formal"
    output.mkdir()
    paths = {
        architecture: tmp_path / f"{architecture.value}.csv.gz"
        for architecture in Architecture
    }
    with pytest.raises(FileExistsError, match="already exists"):
        run_formal_batch(
            output_dir=output,
            gate_a_manifest_path=tmp_path / "gate.json",
            gate_a_execution_path=tmp_path / "gate_execution.json",
            service_path=tmp_path / "service.json",
            d40_gate_a_manifest_path=tmp_path / "d40.json",
            d41_gate_a_manifest_path=tmp_path / "d41.json",
            d46_formal_manifest_path=tmp_path / "d46.json",
            d46_postmortem_bundle_path=tmp_path / "diagnostic.json",
            guide_paths=paths,
            heat_path=tmp_path / "heat.xlsx",
            vre_path=tmp_path / "vre.csv",
            price_basis_path=tmp_path / "prices",
        )
