from __future__ import annotations

import json
from pathlib import Path

import pytest


def _bounded_lp(size: int = 20):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    for column in range(size):
        highs.addCol(float(column + 1), 0.0, 1.0, 0, [], [])
    indices = list(range(size))
    values = [1.0] * size
    highs.addRow(float(size // 2), highspy.kHighsInf, size, indices, values)
    highs.changeObjectiveOffset(3.25)
    highs.ensureColwise()
    return highs.getLp()


def test_formal_phase_plan_exactly_locks_ipx_and_four_simplex_segments() -> None:
    from tes_bess_boundary.e0d42_gate_b_executor import formal_phase_plan

    plan = formal_phase_plan()

    assert [phase["key"] for phase in plan] == [
        "ipx",
        "simplex_1",
        "simplex_2",
        "simplex_3",
        "simplex_4",
    ]
    assert [phase["soft_wall_seconds"] for phase in plan] == [
        900.0,
        600.0,
        600.0,
        600.0,
        600.0,
    ]
    assert [phase["parent_hard_wall_seconds"] for phase in plan] == [
        1020.0,
        720.0,
        720.0,
        720.0,
        720.0,
    ]
    assert plan[1]["prior_simplex_basis_required"] is False
    assert all(
        phase["prior_simplex_basis_required"] is True for phase in plan[2:]
    )


def test_lp_archive_is_deterministic_and_preserves_complete_fingerprint(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import (
        read_lp_archive,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )

    lp = _bounded_lp()
    first_path = tmp_path / "first.lpbin.gz"
    second_path = tmp_path / "second.lpbin.gz"
    first = write_lp_archive(lp, first_path)
    second = write_lp_archive(lp, second_path)
    restored, audit = read_lp_archive(
        first_path,
        expected_lp_sha256=fingerprint_highs_lp(lp),
    )

    assert first["archive_sha256"] == second["archive_sha256"]
    assert _sha256(first_path) == _sha256(second_path)
    assert fingerprint_highs_lp(restored) == fingerprint_highs_lp(lp)
    assert audit["roundtrip_fingerprint_passed"] is True
    with pytest.raises(ValueError, match="locked identity"):
        read_lp_archive(first_path, expected_lp_sha256="0" * 64)


def test_phase_child_saves_hashed_solution_certificate_and_resumable_basis(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import (
        SOLUTION_ARCHIVE_MAGIC,
        _phase_paths,
        _read_binary_archive,
        run_phase_child,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )

    lp = _bounded_lp(30)
    identity = fingerprint_highs_lp(lp)
    archive = tmp_path / "locked.lpbin.gz"
    write_lp_archive(lp, archive)

    ipx = run_phase_child(
        lp_archive_path=archive,
        expected_lp_sha256=identity,
        phase_key="ipx",
        output_dir=tmp_path,
    )
    ipx_paths = _phase_paths(tmp_path, "ipx")
    solution_header, solution_arrays = _read_binary_archive(
        ipx_paths["solution"],
        expected_magic=SOLUTION_ARCHIVE_MAGIC,
    )

    assert ipx["status"] == "certified_optimal_relaxation"
    assert ipx["formal_lower_bound_eligible"] is True
    assert ipx["acceptance_audit"]["kkt_passed"] is True
    assert ipx["certificate"]["formal_lower_bound_eligible"] is True
    assert ipx["certificate_sha256"] == _sha256(ipx_paths["certificate"])
    assert ipx["solution_sha256"] == _sha256(ipx_paths["solution"])
    assert ipx["basis"]["basis_valid"] is True
    assert solution_header["lp_sha256"] == identity
    assert len(solution_arrays["col_value"]) == 30
    assert len(solution_arrays["row_dual"]) == 1

    simplex = run_phase_child(
        lp_archive_path=archive,
        expected_lp_sha256=identity,
        phase_key="simplex_1",
        output_dir=tmp_path,
        input_basis_path=ipx_paths["basis"],
        input_basis_meta_path=ipx_paths["basis_meta"],
    )
    simplex_paths = _phase_paths(tmp_path, "simplex_1")
    resumed = run_phase_child(
        lp_archive_path=archive,
        expected_lp_sha256=identity,
        phase_key="simplex_2",
        output_dir=tmp_path,
        input_basis_path=simplex_paths["basis"],
        input_basis_meta_path=simplex_paths["basis_meta"],
    )

    assert simplex["input_basis"]["loaded"] is True
    assert resumed["input_basis"]["source_phase"] == "simplex_1"
    assert resumed["status"] == "certified_optimal_relaxation"


def test_later_simplex_requires_immediately_preceding_valid_same_lp_basis(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d42_gate_b_executor import (
        _phase_paths,
        run_phase_child,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )

    lp = _bounded_lp()
    identity = fingerprint_highs_lp(lp)
    archive = tmp_path / "locked.lpbin.gz"
    write_lp_archive(lp, archive)

    with pytest.raises(ValueError, match="preceding simplex basis"):
        run_phase_child(
            lp_archive_path=archive,
            expected_lp_sha256=identity,
            phase_key="simplex_2",
            output_dir=tmp_path,
        )

    first = run_phase_child(
        lp_archive_path=archive,
        expected_lp_sha256=identity,
        phase_key="simplex_1",
        output_dir=tmp_path,
    )
    assert first["basis"]["basis_valid"] is True
    paths = _phase_paths(tmp_path, "simplex_1")
    tampered_meta = tmp_path / "tampered_basis.json"
    payload = json.loads(paths["basis_meta"].read_text(encoding="utf-8"))
    payload["lp_sha256"] = "f" * 64
    tampered_meta.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        run_phase_child(
            lp_archive_path=archive,
            expected_lp_sha256=identity,
            phase_key="simplex_2",
            output_dir=tmp_path,
            input_basis_path=paths["basis"],
            input_basis_meta_path=tampered_meta,
        )


def test_monitor_stop_reason_enforces_total_wall_before_phase_and_memory() -> None:
    from tes_bess_boundary.e0d42_gate_b_executor import monitor_stop_reason

    common = {
        "phase_elapsed_seconds": 0.0,
        "phase_hard_wall_seconds": 720.0,
        "total_elapsed_seconds": 0.0,
        "child_tree_rss_gib": 1.0,
        "aggregate_rss_gib": 2.0,
        "available_memory_gib": 90.0,
    }
    assert monitor_stop_reason(**common) is None
    assert (
        monitor_stop_reason(
            **{
                **common,
                "phase_elapsed_seconds": 900.0,
                "total_elapsed_seconds": 4_600.0,
                "child_tree_rss_gib": 40.0,
                "available_memory_gib": 1.0,
            }
        )
        == "total_lp_parent_wall_reached"
    )
    assert (
        monitor_stop_reason(**{**common, "phase_elapsed_seconds": 720.0})
        == "phase_parent_hard_wall_reached"
    )
    assert (
        monitor_stop_reason(**{**common, "child_tree_rss_gib": 35.0})
        == "process_tree_rss_limit_reached"
    )
    assert (
        monitor_stop_reason(**{**common, "aggregate_rss_gib": 75.0})
        == "aggregate_rss_limit_reached"
    )
    assert (
        monitor_stop_reason(**{**common, "available_memory_gib": 14.9})
        == "host_memory_reserve_breached"
    )


def test_lp_manifest_reaudits_parent_hash_chain_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import (
        PHASE_EXECUTION_SCHEMA_ID,
        _phase_paths,
        compile_lp_manifest,
        run_phase_child,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )

    lp = _bounded_lp()
    identity = fingerprint_highs_lp(lp)
    archive = tmp_path / "locked.lpbin.gz"
    write_lp_archive(lp, archive)
    run_phase_child(
        lp_archive_path=archive,
        expected_lp_sha256=identity,
        phase_key="ipx",
        output_dir=tmp_path,
    )
    paths = _phase_paths(tmp_path, "ipx")
    paths["solver_log"].write_text("test log\n", encoding="utf-8")
    paths["heartbeat"].write_text("{}\n", encoding="utf-8")
    artifact_hashes = {
        key: _sha256(paths[key]) if paths[key].is_file() else None
        for key in (
            "result",
            "solver_log",
            "heartbeat",
            "progress",
            "solution",
            "certificate",
            "basis",
            "basis_meta",
        )
    }
    paths["execution"].write_text(
        json.dumps(
            {
                "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                "status": "complete",
                "phase": "ipx",
                "lp_sha256": identity,
                "return_code": 0,
                "resource_gate_passed": True,
                "stop_reason": None,
                "hard_wall_enforced_by_parent": True,
                "artifact_sha256": artifact_hashes,
            }
        ),
        encoding="utf-8",
    )

    manifest = compile_lp_manifest(
        output_dir=tmp_path,
        expected_lp_sha256=identity,
    )
    assert manifest["status"] == "certified_optimal_relaxation"
    assert manifest["formal_lower_bound_eligible"] is True
    assert manifest["selected_phase"] == "ipx"

    certificate = json.loads(paths["certificate"].read_text(encoding="utf-8"))
    certificate["lower_bound_decimal"] = "999999"
    paths["certificate"].write_text(json.dumps(certificate), encoding="utf-8")
    rejected = compile_lp_manifest(
        output_dir=tmp_path,
        expected_lp_sha256=identity,
    )
    assert rejected["status"] == "native_state_without_certificate"
    assert rejected["formal_lower_bound_eligible"] is False
