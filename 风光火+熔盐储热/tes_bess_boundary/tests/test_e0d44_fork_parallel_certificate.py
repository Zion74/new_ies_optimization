from __future__ import annotations

import json
import math
import multiprocessing
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest


def _synthetic_lp(size: int = 24):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    for column in range(size):
        cost = 0.1 + (column - 7) * 0.125
        lower = -1.0 - 0.1 * (column % 3)
        upper = 2.0 + 0.2 * (column % 5)
        highs.addCol(cost, lower, upper, 0, [], [])
    all_columns = list(range(size))
    highs.addRow(
        -0.5,
        1.25,
        size,
        all_columns,
        [0.2 + 0.05 * (column % 4) for column in all_columns],
    )
    highs.addRow(
        2.0,
        highspy.kHighsInf,
        size,
        all_columns,
        [(-1.0) ** column * 0.3 for column in all_columns],
    )
    highs.addRow(
        -highspy.kHighsInf,
        3.0,
        size,
        all_columns,
        [0.15 * ((column % 5) - 2) for column in all_columns],
    )
    highs.addRow(
        -highspy.kHighsInf,
        highspy.kHighsInf,
        size,
        all_columns,
        [0.07 * ((column % 7) - 3) for column in all_columns],
    )
    highs.addRow(
        -highspy.kHighsInf,
        4.0,
        size,
        all_columns,
        [0.11 * ((column % 6) - 2) for column in all_columns],
    )
    highs.changeObjectiveOffset(0.15)
    highs.ensureColwise()
    return highs.getLp(), [0.3, -0.7, 0.9, 1.1, -0.4]


def _invalid_free_column_lp():
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    highs.addCol(1.0, -highspy.kHighsInf, highspy.kHighsInf, 0, [], [])
    highs.ensureColwise()
    return highs.getLp()


def _fraction(value: float) -> Fraction:
    return Fraction.from_float(float(value))


def _exact_lagrangian_value(lp: object, row_dual: list[float]) -> Fraction:
    projected: list[Fraction] = []
    result = _fraction(float(lp.offset_))
    for multiplier, raw_lower, raw_upper in zip(
        row_dual,
        lp.row_lower_,
        lp.row_upper_,
        strict=True,
    ):
        lower = float(raw_lower)
        upper = float(raw_upper)
        repaired = float(multiplier)
        if not math.isfinite(lower) and not math.isfinite(upper):
            repaired = 0.0
        elif math.isfinite(lower) and not math.isfinite(upper) and repaired < 0.0:
            repaired = 0.0
        elif not math.isfinite(lower) and math.isfinite(upper) and repaired > 0.0:
            repaired = 0.0
        repaired_fraction = _fraction(repaired)
        projected.append(repaired_fraction)
        if repaired > 0.0:
            result += repaired_fraction * _fraction(lower)
        elif repaired < 0.0:
            result += repaired_fraction * _fraction(upper)

    starts = lp.a_matrix_.start_
    indices = lp.a_matrix_.index_
    values = lp.a_matrix_.value_
    for column in range(int(lp.num_col_)):
        activity = Fraction(0)
        for position in range(int(starts[column]), int(starts[column + 1])):
            activity += _fraction(float(values[position])) * projected[
                int(indices[position])
            ]
        residual = _fraction(float(lp.col_cost_[column])) - activity
        if residual > 0:
            endpoint = float(lp.col_lower_[column])
        elif residual < 0:
            endpoint = float(lp.col_upper_[column])
        else:
            continue
        if not math.isfinite(endpoint):
            raise ValueError("exact synthetic reference is unbounded")
        result += residual * _fraction(endpoint)
    return result


def _interval(certificate: dict[str, object]) -> tuple[Fraction, Fraction]:
    lower = certificate["lower_bound_decimal"]
    upper = certificate["upper_bound_decimal"]
    assert isinstance(lower, str)
    assert isinstance(upper, str)
    return Fraction(Decimal(lower)), Fraction(Decimal(upper))


def _inline_executor(lp, projected, chunks):
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        evaluate_column_chunk,
    )

    return [evaluate_column_chunk(lp, projected, chunk) for chunk in chunks]


def _locked_fixture(tmp_path: Path):
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

    lp, dual = _synthetic_lp(size=8)
    lp_sha256 = fingerprint_highs_lp(lp)
    lp_path = tmp_path / "presolved_lp.bin.gz"
    lp_archive = write_lp_archive(lp, lp_path)
    solution_path = tmp_path / "phase_ipx_solution.bin.gz"
    solution = SimpleNamespace(
        value_valid=True,
        dual_valid=True,
        col_value=[0.0] * int(lp.num_col_),
        col_dual=[0.0] * int(lp.num_col_),
        row_value=[0.0] * int(lp.num_row_),
        row_dual=dual,
    )
    solution_audit = _write_solution_archive(
        solution_path,
        solution=solution,
        lp_sha256=lp_sha256,
        phase_key="ipx",
        model_status="Interrupted by user",
    )
    execution_path = tmp_path / "phase_ipx_execution.json"
    _atomic_write_json(
        execution_path,
        {
            "lp_sha256": lp_sha256,
            "artifact_sha256": {"solution": solution_audit["archive_sha256"]},
        },
    )
    spec = SnapshotSpec(
        key="ipx",
        solution_file=solution_path.name,
        solution_sha256=_sha256(solution_path),
        phase_execution_file=execution_path.name,
        phase_execution_sha256=_sha256(execution_path),
    )
    return {
        "lp_path": lp_path,
        "lp_archive": lp_archive,
        "lp_sha256": lp_sha256,
        "solution_path": solution_path,
        "execution_path": execution_path,
        "spec": spec,
        "num_col": int(lp.num_col_),
        "num_row": int(lp.num_row_),
    }


def test_fixed_partition_exactly_covers_formal_columns() -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        fixed_column_chunks,
    )

    chunks = fixed_column_chunks(509_289, 24)

    assert len(chunks) == 24
    assert chunks[0].start_column == 0
    assert chunks[-1].end_column == 509_289
    assert all(
        left.end_column == right.start_column
        for left, right in zip(chunks, chunks[1:])
    )
    assert sum(chunk.end_column - chunk.start_column for chunk in chunks) == 509_289


@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        ([(0, 0, 2), (1, 3, 4)], "gap or overlap"),
        ([(0, 0, 2), (0, 2, 4)], "ids are not canonical"),
        ([(0, 0, 0), (1, 0, 4)], "empty chunk"),
    ],
)
def test_partition_validator_rejects_noncanonical_ranges(
    chunks: list[tuple[int, int, int]], message: str
) -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        ColumnChunk,
        validate_column_partition,
    )

    with pytest.raises(ValueError, match=message):
        validate_column_partition(
            [ColumnChunk(*values) for values in chunks],
            num_col=4,
            chunk_count=2,
        )


def test_fraction_reference_is_contained_for_all_gate_a_chunk_counts() -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )

    lp, dual = _synthetic_lp()
    exact = _exact_lagrangian_value(lp, dual)
    intervals: list[tuple[Fraction, Fraction]] = []
    for chunk_count in (1, 2, 3, 24):
        certificate = certify_partitioned_lagrangian(
            lp,
            dual,
            chunk_count=chunk_count,
        )
        assert certificate["formal_lower_bound_eligible"] is True
        interval = _interval(certificate)
        assert interval[0] <= exact <= interval[1]
        intervals.append(interval)

    assert max(lower for lower, _ in intervals) <= min(
        upper for _, upper in intervals
    )


def test_d42_and_d44_classification_agree_for_bounded_and_invalid_lp() -> None:
    from tes_bess_boundary.e0d42_native_highs_certificate import (
        certify_lagrangian_lower_bound,
    )
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )

    bounded_lp, dual = _synthetic_lp()
    serial = certify_lagrangian_lower_bound(bounded_lp, dual)
    partitioned = certify_partitioned_lagrangian(bounded_lp, dual)
    assert serial.eligible is partitioned["formal_lower_bound_eligible"] is True
    serial_interval = (
        Fraction(Decimal(serial.lower_bound_decimal)),
        Fraction(Decimal(serial.upper_bound_decimal)),
    )
    partitioned_interval = _interval(partitioned)
    assert max(serial_interval[0], partitioned_interval[0]) <= min(
        serial_interval[1], partitioned_interval[1]
    )

    invalid_lp = _invalid_free_column_lp()
    invalid_serial = certify_lagrangian_lower_bound(invalid_lp, [])
    invalid_partitioned = certify_partitioned_lagrangian(
        invalid_lp,
        [],
        chunk_count=1,
    )
    assert invalid_serial.eligible is False
    assert invalid_partitioned["formal_lower_bound_eligible"] is False
    assert invalid_partitioned["invalid_column_endpoint_count"] == 1


def test_row_projection_matches_frozen_free_and_one_sided_rules() -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import project_row_terms

    lp, dual = _synthetic_lp()
    row = project_row_terms(lp, dual)

    assert row["projected_count"] == 3
    assert row["projected"] == tuple(
        Decimal.from_float(value) for value in [0.3, 0.0, 0.0, 0.0, -0.4]
    )


def test_completion_order_cannot_change_canonical_certificate() -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )

    lp, dual = _synthetic_lp()
    canonical = certify_partitioned_lagrangian(
        lp,
        dual,
        chunk_executor=_inline_executor,
    )

    def reversed_executor(lp, projected, chunks):
        return list(reversed(_inline_executor(lp, projected, chunks)))

    reversed_result = certify_partitioned_lagrangian(
        lp,
        dual,
        chunk_executor=reversed_executor,
    )
    assert reversed_result == canonical


@pytest.mark.parametrize("fault", ["missing", "duplicate", "range", "hash", "nnz"])
def test_partial_duplicate_and_tampered_chunk_sets_are_rejected(fault: str) -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        _canonical_hash,
        certify_partitioned_lagrangian,
    )

    lp, dual = _synthetic_lp()

    def faulty_executor(lp, projected, chunks):
        audits = _inline_executor(lp, projected, chunks)
        if fault == "missing":
            return audits[:-1]
        if fault == "duplicate":
            return [*audits[:-1], audits[0]]
        altered = dict(audits[-1])
        if fault == "range":
            altered["start_column"] -= 1
        elif fault == "hash":
            altered["lower_bound_decimal"] = "123"
            audits[-1] = altered
            return audits
        else:
            altered["nonzero_count"] += 1
        payload = {key: value for key, value in altered.items() if key != "content_sha256"}
        altered["content_sha256"] = _canonical_hash(payload)
        audits[-1] = altered
        return audits

    with pytest.raises(ValueError):
        certify_partitioned_lagrangian(
            lp,
            dual,
            chunk_executor=faulty_executor,
        )


def test_worker_exception_and_nonfinite_dual_are_rejected() -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )

    lp, dual = _synthetic_lp()

    def failed_executor(lp, projected, chunks):
        raise RuntimeError("injected worker failure")

    with pytest.raises(RuntimeError, match="injected worker failure"):
        certify_partitioned_lagrangian(
            lp,
            dual,
            chunk_executor=failed_executor,
        )
    with pytest.raises(ValueError, match="finite"):
        certify_partitioned_lagrangian(lp, [*dual[:-1], float("nan")])


def test_snapshot_child_writes_bound_hash_chain_without_solver(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
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
        chunk_count=4,
        fork_workers=None,
    )

    assert result["formal_lower_bound_eligible"] is True
    assert result["optimization_invoked"] is False
    assert result["native_solver_invoked"] is False
    assert result["certificate_sha256"] == _sha256(output / "ipx_certificate.json")
    assert result["chunks_sha256"] == _sha256(output / "ipx_chunks.json")
    chunks = json.loads((output / "ipx_chunks.json").read_text(encoding="utf-8"))
    assert chunks["chunk_count"] == 4
    assert len(chunks["chunks"]) == 4
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
            chunk_count=4,
            fork_workers=None,
        )


def test_manifest_selects_max_decimal_and_ipx_on_tie() -> None:
    import tes_bess_boundary.e0d43_offline_dual_certificate as d43
    from tes_bess_boundary.e0d44_fork_parallel_certificate import assemble_manifest

    artifacts = {spec.key: {} for spec in d43.SNAPSHOT_SPECS}
    source = {"d44": "a" * 64}
    gate_a = {
        "manifest_sha256": "b" * 64,
        "source_sha256": "c" * 64,
        "test_sha256": "d" * 64,
        "git_commit": "e" * 40,
        "test_passed_count": 23,
    }
    better_simplex = assemble_manifest(
        phase_results={
            "ipx": {"formal_lower_bound_eligible": True, "lower_bound_decimal": "1"},
            "simplex_1": {
                "formal_lower_bound_eligible": True,
                "lower_bound_decimal": "2",
            },
        },
        phase_artifacts=artifacts,
        source_sha256=source,
        gate_a_audit=gate_a,
    )
    assert better_simplex["selected_phase"] == "simplex_1"

    tied = assemble_manifest(
        phase_results={
            spec.key: {
                "formal_lower_bound_eligible": True,
                "lower_bound_decimal": "2.000",
            }
            for spec in d43.SNAPSHOT_SPECS
        },
        phase_artifacts=artifacts,
        source_sha256=source,
        gate_a_audit=gate_a,
    )
    assert tied["selected_phase"] == "ipx"
    assert tied["technical_ranking_permitted"] is False


def test_gate_a_manifest_binds_linux_fork_source_test_and_commit(
    tmp_path: Path,
) -> None:
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
    from tes_bess_boundary.e0d42_gate_b_executor import _atomic_write_json

    test_path = Path(__file__)
    manifest_path = tmp_path / "gate_a_manifest.json"
    payload = {
        "schema_id": d44.GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "platform": "linux",
        "fork_available": True,
        "four_worker_fork_smoke_passed": True,
        "fraction_reference_passed": True,
        "chunk_count_equivalence_passed": True,
        "failure_injection_passed": True,
        "directed_regression_passed": True,
        "full_regression_passed": True,
        "source_sha256": _sha256(Path(d44.__file__)),
        "test_sha256": _sha256(test_path),
        "test_passed_count": 23,
        "test_failed_count": 0,
        "test_skipped_count": 0,
        "git_commit": "a" * 40,
    }
    _atomic_write_json(manifest_path, payload)

    audit = d44.validate_gate_a_manifest(
        gate_a_manifest=manifest_path,
        d44_test_path=test_path,
    )

    assert audit["manifest_sha256"] == _sha256(manifest_path)
    assert audit["git_commit"] == "a" * 40
    _atomic_write_json(manifest_path, {**payload, "source_sha256": "f" * 64})
    with pytest.raises(ValueError, match="production source SHA-256 mismatch"):
        d44.validate_gate_a_manifest(
            gate_a_manifest=manifest_path,
            d44_test_path=test_path,
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"total_elapsed_seconds": 1080.0}, "total_parent_hard_wall_reached"),
        ({"phase_elapsed_seconds": {"ipx": 900.0}}, "phase_hard_wall_reached:ipx"),
        ({"phase_rss_gib": {"ipx": 20.0}}, "phase_rss_limit_reached:ipx"),
        ({"aggregate_rss_gib": 45.0}, "aggregate_rss_limit_reached"),
        ({"available_memory_gib": 29.9}, "host_memory_reserve_breached"),
    ],
)
def test_resource_stops_are_deterministic(
    overrides: dict[str, object], expected: str
) -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import monitor_stop_reason

    arguments = {
        "phase_elapsed_seconds": {"ipx": 1.0, "simplex_1": 1.0},
        "total_elapsed_seconds": 1.0,
        "phase_rss_gib": {"ipx": 1.0, "simplex_1": 1.0},
        "aggregate_rss_gib": 2.0,
        "available_memory_gib": 90.0,
    }
    arguments.update(overrides)
    assert monitor_stop_reason(**arguments) == expected


def test_structure_identity_and_claim_boundary() -> None:
    import tes_bess_boundary.e0d43_offline_dual_certificate as d43
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        render_readme,
        validate_structure_identity,
    )

    valid = {
        "tes_r0_r1_identity": {
            "original_lp_fingerprint_equal": True,
            "presolved_lp_fingerprint_equal": True,
            "presolved_lp_sha256": d43.LOCKED_LP_SHA256,
        },
        "formal_gate_b_permitted": True,
    }
    validate_structure_identity(valid)
    with pytest.raises(ValueError, match="presolved LP identity"):
        validate_structure_identity(
            {
                **valid,
                "tes_r0_r1_identity": {
                    **valid["tes_r0_r1_identity"],
                    "presolved_lp_fingerprint_equal": False,
                },
            }
        )

    readme = render_readme(
        {
            "status": "tes_lower_bound_recovered",
            "selected_phase": "ipx",
            "formal_lower_bound_decimal": "123",
        },
        manifest_sha256="a" * 64,
    )
    assert "not a feasible upper bound" in readme
    assert "technology ranking" in readme
    assert "Optimization/native solver invoked: `false`" in readme


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="formal fork integration is OpenBayes/Linux-only",
)
def test_linux_four_worker_fork_smoke_and_progress(tmp_path: Path) -> None:
    from tes_bess_boundary.e0d44_fork_parallel_certificate import (
        certify_partitioned_lagrangian,
    )

    lp, dual = _synthetic_lp()
    progress = tmp_path / "progress.ndjson"
    certificate = certify_partitioned_lagrangian(
        lp,
        dual,
        chunk_count=4,
        fork_workers=4,
        progress_path=progress,
    )

    assert certificate["formal_lower_bound_eligible"] is True
    records = [
        json.loads(line)
        for line in progress.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(records) == 4
    assert records[-1]["completed_chunks"] == 4
