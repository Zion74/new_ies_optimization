from __future__ import annotations

import json
import multiprocessing
import platform
import sys
from copy import deepcopy
from pathlib import Path

import pytest


def _bounded_lp(size: int = 24):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    for column in range(size):
        highs.addCol(float(column + 1), 0.0, 1.0, 0, [], [])
    highs.addRow(
        float(size // 2),
        highspy.kHighsInf,
        size,
        list(range(size)),
        [1.0] * size,
    )
    highs.changeObjectiveOffset(3.25)
    highs.ensureColwise()
    return highs.getLp()


def _prepare_fixture():
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    original = {**d45.FORMAL_ORIGINAL_LP, "highs_version": "1.15.1"}
    presolved = {**d45.FORMAL_PRESOLVED_LP, "highs_version": "1.15.1"}
    prepare = {
        "schema_id": d45.d42_formal.PREPARE_SCHEMA_ID,
        "status": "formal_lp_prepared",
        "case_key": "hybrid_r0",
        "architecture": "hybrid",
        "relaxation_mode": "r0_all_continuous",
        "topology_value": None,
        "structure_manifest_sha256": d45.D42_STRUCTURE_MANIFEST_SHA256,
        "structure_case_sha256": d45.D42_HYBRID_R0_CASE_SHA256,
        "optimization_invoked": False,
        "single_original_model_build": True,
        "single_explicit_presolve": True,
        "audit": {"passed": True},
        "relaxation": {
            "relaxed_binary_variable_count": d45.FORMAL_ORIGINAL_BINARY_COUNT,
            "remaining_binary_variable_count": d45.FORMAL_REMAINING_BINARY_COUNT,
        },
        "original_lp": original,
        "presolved_lp": presolved,
    }
    structure = {
        "lp_identity_audit": {
            "original_lp": deepcopy(original),
            "presolved_lp": deepcopy(presolved),
        }
    }
    return prepare, structure


def _snapshot_fixture(tmp_path: Path, phase: str = "ipx"):
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import (
        _atomic_write_json,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    lp = _bounded_lp()
    lp_sha256 = fingerprint_highs_lp(lp)
    archive_path = tmp_path / "locked_lp.bin.gz"
    archive = write_lp_archive(lp, archive_path)
    result = d45.run_solver_snapshot_child(
        lp_archive_path=archive_path,
        expected_lp_sha256=lp_sha256,
        expected_lp_archive_sha256=archive["archive_sha256"],
        phase=phase,
        output_dir=tmp_path,
    )
    paths = d45._solver_paths(tmp_path, phase)
    execution = {
        "schema_id": d45.SOLVER_EXECUTION_SCHEMA_ID,
        "status": "complete",
        "phase": phase,
        "return_code": 0,
        "resource_gate_passed": True,
        "stop_reason": None,
        "hard_wall_enforced_by_parent": True,
        "lp_sha256": lp_sha256,
        "artifact_sha256": {"solution": _sha256(paths["solution"])},
    }
    _atomic_write_json(paths["execution"], execution)
    return {
        "lp": lp,
        "lp_sha256": lp_sha256,
        "archive_path": archive_path,
        "archive": archive,
        "result": result,
        "paths": paths,
    }


def _gate_a_payload(source: Path, test: Path) -> dict[str, object]:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    return {
        "schema_id": d45.GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "platform": "linux",
        "fork_available": True,
        "four_worker_fork_smoke_passed": True,
        "snapshot_archive_passed": True,
        "tamper_rejection_passed": True,
        "partition_equivalence_passed": True,
        "selection_passed": True,
        "identity_gate_passed": True,
        "process_tree_cleanup_passed": True,
        "directed_regression_passed": True,
        "full_regression_passed": True,
        "source_sha256": _sha256(source),
        "test_sha256": _sha256(test),
        "test_failed_count": 0,
        "test_skipped_count": 0,
        "test_passed_count": 20,
        "git_commit": "a" * 40,
    }


def test_phase_plan_locks_only_hybrid_r0_ipx_and_simplex_one() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    assert [phase.key for phase in d45.SNAPSHOT_PHASES] == ["ipx", "simplex_1"]
    assert [phase.solver_name for phase in d45.SNAPSHOT_PHASES] == ["ipx", "simplex"]
    assert [phase.soft_wall_seconds for phase in d45.SNAPSHOT_PHASES] == [900.0, 600.0]
    assert [phase.parent_hard_wall_seconds for phase in d45.SNAPSHOT_PHASES] == [
        1020.0,
        720.0,
    ]
    assert d45.FORMAL_THREADS == 12
    assert d45.FORMAL_CHUNK_COUNT == 24


def test_locked_dependency_hashes_match_frozen_contract() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    assert d45.validate_locked_source_hashes() == d45.LOCKED_SOURCE_SHA256


def test_prepare_identity_accepts_exact_hybrid_r0() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    prepare, structure = _prepare_fixture()
    assert d45.validate_hybrid_prepare_identity(prepare, structure)["passed"] is True


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        (("architecture",), "tes"),
        (("relaxation_mode",), "r1_topology_only"),
        (("optimization_invoked",), True),
        (("relaxation", "remaining_binary_variable_count"), 1),
        (("original_lp", "num_row"), 1),
        (("presolved_lp", "presolved_lp_sha256"), "0" * 64),
    ],
)
def test_prepare_identity_rejects_every_frozen_axis(
    mutation: tuple[str, ...], value: object
) -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    prepare, structure = _prepare_fixture()
    target = prepare
    for key in mutation[:-1]:
        target = target[key]
    target[mutation[-1]] = value
    with pytest.raises(ValueError, match="prepare identity mismatch"):
        d45.validate_hybrid_prepare_identity(prepare, structure)


@pytest.mark.parametrize("phase", ["ipx", "simplex_1"])
def test_solver_child_writes_snapshot_without_decimal_certificate(
    tmp_path: Path, phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d42_gate_b_executor as d42

    def forbidden(*_args, **_kwargs):
        raise AssertionError("D45 solver child invoked a Decimal certificate")

    monkeypatch.setattr(d42, "certify_lagrangian_lower_bound", forbidden)
    fixture = _snapshot_fixture(tmp_path, phase)
    result = fixture["result"]

    assert result["status"] == "snapshot_ready"
    assert result["snapshot_eligible_for_certificate"] is True
    assert result["formal_lower_bound_eligible"] is False
    assert result["optimization_invoked"] is True
    assert fixture["paths"]["solution"].is_file()
    assert not fixture["paths"].get("certificate", Path("missing")).exists()


def test_snapshot_validator_accepts_complete_hash_chain(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    fixture = _snapshot_fixture(tmp_path)
    row_dual, audit = d45.validate_solver_snapshot(
        solution_path=fixture["paths"]["solution"],
        phase_execution_path=fixture["paths"]["execution"],
        phase="ipx",
        expected_solution_sha256=_sha256(fixture["paths"]["solution"]),
        expected_phase_execution_sha256=_sha256(fixture["paths"]["execution"]),
        expected_lp_sha256=fixture["lp_sha256"],
        expected_num_col=int(fixture["lp"].num_col_),
        expected_num_row=int(fixture["lp"].num_row_),
    )

    assert len(row_dual) == int(fixture["lp"].num_row_)
    assert audit["d45_execution_gate_passed"] is True


def test_snapshot_validator_rejects_execution_tampering(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import _atomic_write_json
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    fixture = _snapshot_fixture(tmp_path)
    execution = json.loads(fixture["paths"]["execution"].read_text(encoding="utf-8"))
    execution["artifact_sha256"]["solution"] = "0" * 64
    _atomic_write_json(fixture["paths"]["execution"], execution)
    with pytest.raises(ValueError, match="bind the solution"):
        d45.validate_solver_snapshot(
            solution_path=fixture["paths"]["solution"],
            phase_execution_path=fixture["paths"]["execution"],
            phase="ipx",
            expected_solution_sha256=_sha256(fixture["paths"]["solution"]),
            expected_phase_execution_sha256=_sha256(fixture["paths"]["execution"]),
            expected_lp_sha256=fixture["lp_sha256"],
            expected_num_col=int(fixture["lp"].num_col_),
            expected_num_row=int(fixture["lp"].num_row_),
        )


def test_execution_artifact_map_rejects_any_changed_file(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    result = tmp_path / "result.json"
    log = tmp_path / "log.txt"
    execution_path = tmp_path / "execution.json"
    result.write_text("{}\n", encoding="utf-8")
    log.write_text("first\n", encoding="utf-8")
    paths = {"result": result, "log": log, "execution": execution_path}
    execution = {
        "artifact_sha256": {"result": _sha256(result), "log": _sha256(log)}
    }
    assert d45.validate_execution_artifacts(execution, paths) == execution[
        "artifact_sha256"
    ]
    log.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash map"):
        d45.validate_execution_artifacts(execution, paths)


def test_certificate_child_reuses_d44_kernel_without_native_solver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45
    import highspy

    fixture = _snapshot_fixture(tmp_path)

    def forbidden(_self):
        raise AssertionError("certificate child invoked a native solver")

    monkeypatch.setattr(highspy.Highs, "run", forbidden)
    result = d45.run_certificate_child(
        lp_archive_path=fixture["archive_path"],
        expected_lp_sha256=fixture["lp_sha256"],
        expected_lp_archive_sha256=fixture["archive"]["archive_sha256"],
        solution_path=fixture["paths"]["solution"],
        solver_execution_path=fixture["paths"]["execution"],
        expected_solution_sha256=_sha256(fixture["paths"]["solution"]),
        expected_solver_execution_sha256=_sha256(fixture["paths"]["execution"]),
        phase="ipx",
        output_dir=tmp_path,
        expected_num_col=int(fixture["lp"].num_col_),
        expected_num_row=int(fixture["lp"].num_row_),
        chunk_count=3,
        fork_workers=None,
    )

    assert result["formal_lower_bound_eligible"] is True
    assert result["optimization_invoked"] is False
    assert result["native_solver_invoked"] is False
    assert len(json.loads((tmp_path / "certificate_ipx_chunks.json").read_text())["chunks"]) == 3


def _manifest_inputs():
    phases = {
        "ipx": {
            "status": "certified_finite_lower_bound",
            "formal_lower_bound_eligible": True,
            "lower_bound_decimal": "10.0",
        },
        "simplex_1": {
            "status": "certified_finite_lower_bound",
            "formal_lower_bound_eligible": True,
            "lower_bound_decimal": "11.0",
        },
    }
    artifacts = {key: {} for key in phases}
    return phases, artifacts


def test_manifest_selects_greater_decimal_bound() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    phases, artifacts = _manifest_inputs()
    manifest = d45.assemble_manifest(
        phase_results=phases,
        phase_artifacts=artifacts,
        input_sha256={},
        source_sha256={},
        gate_a_audit={},
    )
    assert manifest["selected_phase"] == "simplex_1"
    assert manifest["status"] == "hybrid_r0_lower_bound_recovered"
    assert manifest["hybrid_r0_certificate_covers_r1_and_original_milp"] is True


def test_manifest_prefers_ipx_on_exact_decimal_tie() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    phases, artifacts = _manifest_inputs()
    phases["simplex_1"]["lower_bound_decimal"] = "10.00"
    manifest = d45.assemble_manifest(
        phase_results=phases,
        phase_artifacts=artifacts,
        input_sha256={},
        source_sha256={},
        gate_a_audit={},
    )
    assert manifest["selected_phase"] == "ipx"


def test_manifest_accepts_one_snapshot_and_rejects_partial_dual_as_bound() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    phases, artifacts = _manifest_inputs()
    phases["ipx"] = {
        "status": "snapshot_ineligible",
        "formal_lower_bound_eligible": False,
        "lower_bound_decimal": "999999",
    }
    manifest = d45.assemble_manifest(
        phase_results=phases,
        phase_artifacts=artifacts,
        input_sha256={},
        source_sha256={},
        gate_a_audit={},
    )
    assert manifest["selected_phase"] == "simplex_1"
    phases["simplex_1"]["formal_lower_bound_eligible"] = False
    failed = d45.assemble_manifest(
        phase_results=phases,
        phase_artifacts=artifacts,
        input_sha256={},
        source_sha256={},
        gate_a_audit={},
    )
    assert failed["status"] == "no_strict_certificate"
    assert failed["formal_lower_bound_decimal"] is None


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"stage_elapsed_seconds": 1080.0}, "stage_hard_wall_reached"),
        (
            {"phase_elapsed_seconds": {"ipx": 1020.0}},
            "phase_hard_wall_reached:ipx",
        ),
        ({"phase_rss_gib": {"ipx": 20.0}}, "phase_rss_limit_reached:ipx"),
        ({"aggregate_rss_gib": 45.0}, "aggregate_rss_limit_reached"),
        ({"available_memory_gib": 29.9}, "host_memory_reserve_breached"),
    ],
)
def test_stage_stop_rules_are_frozen(
    override: dict[str, object], expected: str
) -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    inputs = {
        "phase_elapsed_seconds": {"ipx": 1.0, "simplex_1": 1.0},
        "phase_hard_walls": {"ipx": 1020.0, "simplex_1": 720.0},
        "stage_elapsed_seconds": 1.0,
        "stage_hard_wall_seconds": 1080.0,
        "phase_rss_gib": {"ipx": 1.0, "simplex_1": 1.0},
        "phase_rss_limit_gib": 20.0,
        "aggregate_rss_gib": 2.0,
        "aggregate_rss_limit_gib": 45.0,
        "available_memory_gib": 90.0,
    }
    assert d45.monitor_stage_stop_reason(**{**inputs, **override}) == expected


def test_gate_a_manifest_binds_source_test_commit_and_zero_skips(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d42_gate_b_executor import _atomic_write_json
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    source = Path(d45.__file__)
    test = Path(__file__)
    manifest = tmp_path / "gate_a_manifest.json"
    _atomic_write_json(manifest, _gate_a_payload(source, test))
    audit = d45.validate_gate_a_manifest(
        gate_a_manifest=manifest,
        d45_test_path=test,
    )
    assert audit["source_sha256"] == _gate_a_payload(source, test)["source_sha256"]
    payload = _gate_a_payload(source, test)
    payload["test_skipped_count"] = 1
    _atomic_write_json(tmp_path / "bad.json", payload)
    with pytest.raises(ValueError, match="failed or skipped"):
        d45.validate_gate_a_manifest(
            gate_a_manifest=tmp_path / "bad.json",
            d45_test_path=test,
        )


def test_parser_exposes_only_frozen_snapshot_phases() -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    parser = d45.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "_solver-child",
                "--lp-archive",
                "x",
                "--expected-lp-sha256",
                "a",
                "--expected-lp-archive-sha256",
                "b",
                "--phase",
                "simplex_2",
                "--output-dir",
                "y",
            ]
        )


@pytest.mark.skipif(
    platform.system().lower() != "linux" or "fork" not in multiprocessing.get_all_start_methods(),
    reason="formal process-group cleanup requires Linux fork and /proc",
)
def test_linux_parent_hard_wall_terminates_process_group(tmp_path: Path) -> None:
    import tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound as d45

    paths = {
        "result": tmp_path / "result.json",
        "execution": tmp_path / "execution.json",
        "progress": tmp_path / "progress.json",
        "log": tmp_path / "child.log",
        "heartbeat": tmp_path / "heartbeat.ndjson",
    }
    executions = d45._run_parallel_stage(
        processes=(
            d45.StageProcess(
                "probe",
                (sys.executable, "-c", "import time; time.sleep(30)"),
                paths,
                0.05,
                "f" * 64,
            ),
        ),
        execution_schema_id="test.execution",
        stage_name="probe",
        stage_hard_wall_seconds=2.0,
        phase_rss_limit_gib=20.0,
        aggregate_rss_limit_gib=45.0,
    )
    assert executions["probe"]["status"] == "interrupted_or_failed"
    assert executions["probe"]["stop_reason"] == "phase_hard_wall_reached:probe"
    assert executions["probe"]["lp_sha256"] == "f" * 64
    assert executions["probe"]["residual_process_group_detected"] is False


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="D45 formal fork smoke requires Linux fork",
)
def test_linux_four_worker_d44_fork_smoke(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import fingerprint_highs_lp

    lp = _bounded_lp(24)
    certificate = certify_partitioned_lagrangian(
        lp,
        [0.0],
        expected_lp_sha256=fingerprint_highs_lp(lp),
        chunk_count=4,
        fork_workers=4,
        progress_path=tmp_path / "progress.ndjson",
    )
    assert certificate["formal_lower_bound_eligible"] is True
    assert len(certificate["chunks"]) == 4
    assert len((tmp_path / "progress.ndjson").read_text().splitlines()) == 4
