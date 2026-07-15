from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _bounded_lp(size: int = 4):
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


def _locked_fixture(
    tmp_path: Path,
    *,
    phase: str = "ipx",
    dual_valid: bool = True,
    row_dual: list[float] | None = None,
    col_count_delta: int = 0,
):
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import (
        _atomic_write_json,
        _write_solution_archive,
        write_lp_archive,
    )
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        fingerprint_highs_lp,
    )
    from tes_bess_boundary.e0d43_offline_dual_certificate import SnapshotSpec

    lp = _bounded_lp()
    lp_sha256 = fingerprint_highs_lp(lp)
    lp_path = tmp_path / "lp.bin.gz"
    lp_archive = write_lp_archive(lp, lp_path)
    solution_path = tmp_path / f"phase_{phase}_solution.bin.gz"
    num_col = int(lp.num_col_)
    num_row = int(lp.num_row_)
    solution = SimpleNamespace(
        value_valid=True,
        dual_valid=dual_valid,
        col_value=[0.0] * (num_col + col_count_delta),
        col_dual=[0.0] * num_col,
        row_value=[0.0] * num_row,
        row_dual=[0.0] * num_row if row_dual is None else row_dual,
    )
    solution_audit = _write_solution_archive(
        solution_path,
        solution=solution,
        lp_sha256=lp_sha256,
        phase_key=phase,
        model_status="Interrupted by user",
    )
    execution_path = tmp_path / f"phase_{phase}_execution.json"
    _atomic_write_json(
        execution_path,
        {
            "lp_sha256": lp_sha256,
            "artifact_sha256": {"solution": solution_audit["archive_sha256"]},
        },
    )
    spec = SnapshotSpec(
        key=phase,
        solution_file=solution_path.name,
        solution_sha256=_sha256(solution_path),
        phase_execution_file=execution_path.name,
        phase_execution_sha256=_sha256(execution_path),
    )
    return {
        "lp": lp,
        "lp_path": lp_path,
        "lp_archive": lp_archive,
        "lp_sha256": lp_sha256,
        "solution_path": solution_path,
        "execution_path": execution_path,
        "spec": spec,
        "num_col": num_col,
        "num_row": num_row,
    }


def test_snapshot_child_recovers_finite_bound_without_optimizer(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import (
        certify_snapshot_child,
    )

    fixture = _locked_fixture(tmp_path)
    output = tmp_path / "out"
    result = certify_snapshot_child(
        lp_archive_path=fixture["lp_path"],
        solution_path=fixture["solution_path"],
        phase_execution_path=fixture["execution_path"],
        output_dir=output,
        spec=fixture["spec"],
        expected_lp_archive_sha256=fixture["lp_archive"]["archive_sha256"],
        expected_lp_sha256=fixture["lp_sha256"],
        expected_num_col=fixture["num_col"],
        expected_num_row=fixture["num_row"],
    )

    assert result["formal_lower_bound_eligible"] is True
    assert result["certificate"]["lower_bound_float"] == pytest.approx(3.25)
    assert result["optimization_invoked"] is False
    assert result["native_solver_invoked"] is False
    assert result["snapshot_audit"]["finite_row_dual_count"] == 1
    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        certify_snapshot_child(
            lp_archive_path=fixture["lp_path"],
            solution_path=fixture["solution_path"],
            phase_execution_path=fixture["execution_path"],
            output_dir=output,
            spec=fixture["spec"],
            expected_lp_archive_sha256=fixture["lp_archive"]["archive_sha256"],
            expected_lp_sha256=fixture["lp_sha256"],
            expected_num_col=fixture["num_col"],
            expected_num_row=fixture["num_row"],
        )


@pytest.mark.parametrize(
    ("fixture_kwargs", "message"),
    [
        ({"dual_valid": False}, "dual_valid=true"),
        ({"row_dual": [float("nan")]}, "non-finite"),
        ({"col_count_delta": 1}, "array length mismatch"),
    ],
)
def test_snapshot_gate_rejects_invalid_archives(
    tmp_path: Path,
    fixture_kwargs: dict[str, object],
    message: str,
) -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import (
        load_locked_snapshot,
    )

    fixture = _locked_fixture(tmp_path, **fixture_kwargs)
    with pytest.raises(ValueError, match=message):
        load_locked_snapshot(
            solution_path=fixture["solution_path"],
            phase_execution_path=fixture["execution_path"],
            phase="ipx",
            expected_solution_sha256=fixture["spec"].solution_sha256,
            expected_phase_execution_sha256=(fixture["spec"].phase_execution_sha256),
            expected_lp_sha256=fixture["lp_sha256"],
            expected_num_col=fixture["num_col"],
            expected_num_row=fixture["num_row"],
        )


def test_snapshot_gate_rejects_hash_and_execution_seam_tampering(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import _atomic_write_json
    from tes_bess_boundary.e0d43_offline_dual_certificate import (
        load_locked_snapshot,
    )

    fixture = _locked_fixture(tmp_path)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_locked_snapshot(
            solution_path=fixture["solution_path"],
            phase_execution_path=fixture["execution_path"],
            phase="ipx",
            expected_solution_sha256="0" * 64,
            expected_phase_execution_sha256=(fixture["spec"].phase_execution_sha256),
            expected_lp_sha256=fixture["lp_sha256"],
            expected_num_col=fixture["num_col"],
            expected_num_row=fixture["num_row"],
        )

    _atomic_write_json(
        fixture["execution_path"],
        {
            "lp_sha256": fixture["lp_sha256"],
            "artifact_sha256": {"solution": "f" * 64},
        },
    )
    with pytest.raises(ValueError, match="does not bind"):
        load_locked_snapshot(
            solution_path=fixture["solution_path"],
            phase_execution_path=fixture["execution_path"],
            phase="ipx",
            expected_solution_sha256=fixture["spec"].solution_sha256,
            expected_phase_execution_sha256=_sha256(fixture["execution_path"]),
            expected_lp_sha256=fixture["lp_sha256"],
            expected_num_col=fixture["num_col"],
            expected_num_row=fixture["num_row"],
        )


def test_d42_metadata_chain_binds_bess_lp_and_both_snapshots() -> None:
    import tes_bess_boundary.e0d43_offline_dual_certificate as d43

    phase_executions = {
        spec.key: {
            "lp_sha256": d43.LOCKED_LP_SHA256,
            "lp_archive_sha256": d43.LOCKED_LP_ARCHIVE_SHA256,
            "artifact_sha256": {"solution": spec.solution_sha256},
        }
        for spec in d43.SNAPSHOT_SPECS
    }
    case_manifest = {
        "architecture": "tes",
        "relaxation_mode": "r0_all_continuous",
        "bess_reuse_result_sha256": d43.LOCKED_BESS_REUSE_RESULT_SHA256,
        "structure_manifest_sha256": d43.LOCKED_STRUCTURE_MANIFEST_SHA256,
        "lp_manifest_sha256": d43.LOCKED_LP_MANIFEST_SHA256,
        "lp_execution_sha256": d43.LOCKED_LP_EXECUTION_SHA256,
        "lp_sha256": d43.LOCKED_LP_SHA256,
    }
    case_execution = {"case_manifest_sha256": d43.LOCKED_CASE_MANIFEST_SHA256}
    lp_execution = {
        "manifest_sha256": d43.LOCKED_LP_MANIFEST_SHA256,
        "lp_sha256": d43.LOCKED_LP_SHA256,
        "phase_executions": phase_executions,
    }

    d43.validate_d42_metadata_chain(
        case_manifest=case_manifest,
        case_execution=case_execution,
        lp_execution=lp_execution,
        phase_executions=phase_executions,
    )

    tampered_ipx = {
        **phase_executions["ipx"],
        "artifact_sha256": {"solution": "f" * 64},
    }
    with pytest.raises(ValueError, match="phase execution ipx"):
        d43.validate_d42_metadata_chain(
            case_manifest=case_manifest,
            case_execution=case_execution,
            lp_execution={
                **lp_execution,
                "phase_executions": {
                    **phase_executions,
                    "ipx": tampered_ipx,
                },
            },
            phase_executions=phase_executions,
        )


def _phase_result(phase: str, lower: str | None) -> dict[str, object]:
    eligible = lower is not None
    return {
        "phase": phase,
        "status": (
            "certified_finite_lower_bound" if eligible else "snapshot_ineligible"
        ),
        "formal_lower_bound_eligible": eligible,
        "certificate": (
            {
                "lower_bound_decimal": lower,
                "lower_bound_float": None if lower is None else float(lower),
                "interval_width_decimal": "0.0001",
                "invalid_column_endpoint_count": 0,
            }
            if eligible
            else None
        ),
        "technical_ranking_permitted": False,
    }


def _artifacts() -> dict[str, dict[str, str | None]]:
    return {
        "ipx": {
            "result_sha256": "1" * 64,
            "certificate_sha256": "2" * 64,
            "execution_sha256": "3" * 64,
        },
        "simplex_1": {
            "result_sha256": "4" * 64,
            "certificate_sha256": "5" * 64,
            "execution_sha256": "6" * 64,
        },
    }


def test_manifest_uses_strongest_decimal_bound_and_tie_order() -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import assemble_manifest

    stronger_simplex = assemble_manifest(
        phase_results={
            "ipx": _phase_result("ipx", "10.0000000000000000001"),
            "simplex_1": _phase_result("simplex_1", "10.0000000000000000002"),
        },
        phase_artifact_sha256=_artifacts(),
        input_sha256={},
        source_sha256={},
    )
    tie = assemble_manifest(
        phase_results={
            "ipx": _phase_result("ipx", "11"),
            "simplex_1": _phase_result("simplex_1", "11.0"),
        },
        phase_artifact_sha256=_artifacts(),
        input_sha256={},
        source_sha256={},
    )

    assert stronger_simplex["status"] == "tes_lower_bound_recovered"
    assert stronger_simplex["selected_phase"] == "simplex_1"
    assert stronger_simplex["hybrid_lower_bound_contract_permitted"] is True
    assert stronger_simplex["technical_ranking_permitted"] is False
    assert tie["selected_phase"] == "ipx"


def test_manifest_accepts_one_snapshot_and_stops_when_both_fail() -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import assemble_manifest

    one = assemble_manifest(
        phase_results={
            "ipx": _phase_result("ipx", None),
            "simplex_1": _phase_result("simplex_1", "9.5"),
        },
        phase_artifact_sha256=_artifacts(),
        input_sha256={},
        source_sha256={},
    )
    none = assemble_manifest(
        phase_results={
            "ipx": _phase_result("ipx", None),
            "simplex_1": _phase_result("simplex_1", None),
        },
        phase_artifact_sha256=_artifacts(),
        input_sha256={},
        source_sha256={},
    )

    assert one["selected_phase"] == "simplex_1"
    assert one["tes_r0_certificate_covers_r1"] is True
    assert none["status"] == "no_strict_certificate"
    assert none["hybrid_lower_bound_contract_permitted"] is False


def test_readme_preserves_claim_boundary() -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import (
        assemble_manifest,
        render_readme,
    )

    manifest = assemble_manifest(
        phase_results={
            "ipx": _phase_result("ipx", "9.5"),
            "simplex_1": _phase_result("simplex_1", None),
        },
        phase_artifact_sha256=_artifacts(),
        input_sha256={},
        source_sha256={},
    )
    readme = render_readme(manifest, manifest_sha256="a" * 64)

    assert "TES R0 formal lower bound (CNY): `9.5`" in readme
    assert "Optimization/native solver invoked: `false`" in readme
    assert "not a feasible upper bound" in readme
    assert "not a feasible upper bound, capacity plan, project TAC" in readme


def test_manifest_rejects_bad_decimal_width_and_phase_order() -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import assemble_manifest

    invalid = _phase_result("ipx", "10")
    invalid["certificate"]["interval_width_decimal"] = "-0.1"
    with pytest.raises(ValueError, match="not admissible"):
        assemble_manifest(
            phase_results={
                "ipx": invalid,
                "simplex_1": _phase_result("simplex_1", None),
            },
            phase_artifact_sha256=_artifacts(),
            input_sha256={},
            source_sha256={},
        )
    with pytest.raises(ValueError, match="phase order"):
        assemble_manifest(
            phase_results={
                "simplex_1": _phase_result("simplex_1", None),
                "ipx": _phase_result("ipx", None),
            },
            phase_artifact_sha256=_artifacts(),
            input_sha256={},
            source_sha256={},
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"total_elapsed_seconds": 2100.0}, "total_parent_hard_wall_reached"),
        (
            {"child_elapsed_seconds": {"ipx": 1800.0}},
            "child_hard_wall_reached:ipx",
        ),
        (
            {"child_rss_gib": {"simplex_1": 8.0}},
            "child_rss_limit_reached:simplex_1",
        ),
        ({"aggregate_rss_gib": 20.0}, "aggregate_rss_limit_reached"),
        ({"available_memory_gib": 19.99}, "host_memory_reserve_breached"),
    ],
)
def test_monitor_stop_priority(overrides: dict[str, object], expected: str) -> None:
    from tes_bess_boundary.e0d43_offline_dual_certificate import (
        monitor_stop_reason,
    )

    values = {
        "child_elapsed_seconds": {"ipx": 0.0, "simplex_1": 0.0},
        "total_elapsed_seconds": 0.0,
        "child_rss_gib": {"ipx": 0.0, "simplex_1": 0.0},
        "aggregate_rss_gib": 0.0,
        "available_memory_gib": 100.0,
    }
    values.update(overrides)
    assert monitor_stop_reason(**values) == expected
