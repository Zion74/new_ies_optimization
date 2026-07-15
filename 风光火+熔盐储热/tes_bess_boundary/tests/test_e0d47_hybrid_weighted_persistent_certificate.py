from __future__ import annotations

import json
import math
import multiprocessing
import platform
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import pytest


def _synthetic_lp(size: int = 112):
    import highspy

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    for column in range(size):
        cost = 0.1 + (column - 7) * 0.125
        lower = -1.0 - 0.1 * (column % 3)
        upper = 2.0 + 0.2 * (column % 5)
        highs.addCol(cost, lower, upper, 0, [], [])
    rows = (
        (-0.5, 1.25, list(range(size)), lambda column: 0.2 + 0.05 * (column % 4)),
        (
            2.0,
            highspy.kHighsInf,
            list(range(0, size, 2)),
            lambda column: (-1.0) ** column * 0.3,
        ),
        (
            -highspy.kHighsInf,
            3.0,
            list(range(0, size, 3)),
            lambda column: 0.15 * ((column % 5) - 2),
        ),
        (
            -highspy.kHighsInf,
            highspy.kHighsInf,
            list(range(0, size, 5)),
            lambda column: 0.07 * ((column % 7) - 3),
        ),
        (
            -highspy.kHighsInf,
            4.0,
            list(range(1, size, 7)),
            lambda column: 0.11 * ((column % 6) - 2),
        ),
    )
    for lower, upper, columns, coefficient in rows:
        highs.addRow(
            lower,
            upper,
            len(columns),
            columns,
            [coefficient(column) for column in columns],
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
            activity += (
                _fraction(float(values[position])) * projected[int(indices[position])]
            )
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


def _assembly_fixture(chunk_count: int = 8):
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d42_native_highs_certificate import fingerprint_highs_lp

    lp, dual = _synthetic_lp(32)
    lp_sha256 = fingerprint_highs_lp(lp)
    solution_sha256 = "a" * 64
    row = d44.project_row_terms(lp, dual)
    chunks = d47.weighted_column_chunks(lp, chunk_count)
    partition = d47.build_partition_manifest(
        lp,
        lp_sha256=lp_sha256,
        chunks=chunks,
    )
    raw = _inline_executor(lp, row["projected"], chunks)
    wrapped = [
        d47._wrap_chunk_audit(
            audit,
            phase="ipx",
            lp_sha256=lp_sha256,
            solution_sha256=solution_sha256,
            partition_sha256=partition["content_sha256"],
            partition_record=partition["chunks"][audit["chunk_id"]],
        )
        for audit in raw
    ]
    return lp, lp_sha256, solution_sha256, row, partition, wrapped


def test_phase_and_resource_contract_is_frozen() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    assert [phase.key for phase in d47.PHASES] == ["ipx", "simplex_1"]
    assert d47.FORMAL_CHUNK_COUNT == d47.FORMAL_WORKERS == 56
    assert d47.FORMAL_DECIMAL_PRECISION == 80
    assert d47.PHASE_HARD_WALL_SECONDS == 1_800.0
    assert d47.TOTAL_HARD_WALL_SECONDS == 3_900.0
    assert d47.PHASE_TREE_RSS_LIMIT_GIB == 30.0
    assert d47.AGGREGATE_RSS_LIMIT_GIB == 40.0
    assert d47.HOST_MEMORY_RESERVE_GIB == 30.0


@pytest.mark.parametrize("chunk_count", [1, 2, 3, 24, 56])
def test_weighted_partition_is_deterministic_contiguous_and_complete(
    chunk_count: int,
) -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, _ = _synthetic_lp()
    first = d47.weighted_column_chunks(lp, chunk_count)
    second = d47.weighted_column_chunks(lp, chunk_count)

    assert first == second
    assert len(first) == chunk_count
    assert first[0].start_column == 0
    assert first[-1].end_column == int(lp.num_col_)
    assert all(
        left.end_column == right.start_column for left, right in zip(first, first[1:])
    )
    assert all(chunk.end_column > chunk.start_column for chunk in first)


def test_partition_manifest_binds_weight_nonzeros_and_ranges() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d42_native_highs_certificate import fingerprint_highs_lp

    lp, _ = _synthetic_lp()
    lp_sha256 = fingerprint_highs_lp(lp)
    chunks = d47.weighted_column_chunks(lp)
    partition = d47.build_partition_manifest(
        lp,
        lp_sha256=lp_sha256,
        chunks=chunks,
    )

    assert partition["chunk_count"] == 56
    assert partition["total_work_weight"] == int(lp.num_col_) + len(lp.a_matrix_.value_)
    assert (
        sum(record["work_weight"] for record in partition["chunks"])
        == partition["total_work_weight"]
    )
    assert (
        d47.validate_partition_manifest(
            lp,
            partition,
            expected_lp_sha256=lp_sha256,
        )
        == chunks
    )


@pytest.mark.parametrize("fault", ["gap", "id", "empty", "formula"])
def test_weighted_partition_rejects_noncanonical_ranges(fault: str) -> None:
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, _ = _synthetic_lp(32)
    chunks = list(d47.weighted_column_chunks(lp, 4))
    if fault == "gap":
        chunks[1] = d44.ColumnChunk(1, chunks[1].start_column + 1, chunks[1].end_column)
    elif fault == "id":
        chunks[1] = d44.ColumnChunk(0, chunks[1].start_column, chunks[1].end_column)
    elif fault == "empty":
        chunks[1] = d44.ColumnChunk(1, chunks[1].start_column, chunks[1].start_column)
    else:
        boundary = chunks[0].end_column + 1
        chunks[0] = d44.ColumnChunk(0, 0, boundary)
        chunks[1] = d44.ColumnChunk(1, boundary, chunks[1].end_column)
    with pytest.raises(ValueError):
        d47.validate_weighted_partition(lp, chunks, chunk_count=4)


def test_partition_manifest_rejects_hash_and_statistic_tampering() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, lp_sha256, _, _, partition, _ = _assembly_fixture()
    changed = json.loads(json.dumps(partition))
    changed["chunks"][0]["work_weight"] += 1
    with pytest.raises(ValueError, match="content hash"):
        d47.validate_partition_manifest(
            lp,
            changed,
            expected_lp_sha256=lp_sha256,
        )


def test_fraction_reference_is_contained_for_all_gate_a_chunk_counts() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, dual = _synthetic_lp(56)
    exact = _exact_lagrangian_value(lp, dual)
    intervals = []
    for chunk_count in (1, 2, 3, 24, 56):
        certificate = d47.certify_weighted_lagrangian(
            lp,
            dual,
            phase="ipx",
            solution_sha256="a" * 64,
            chunk_count=chunk_count,
        )
        assert certificate["formal_lower_bound_eligible"] is True
        interval = _interval(certificate)
        assert interval[0] <= exact <= interval[1]
        intervals.append(interval)
    assert max(lower for lower, _ in intervals) <= min(upper for _, upper in intervals)


def test_d44_and_d47_agree_for_bounded_and_invalid_endpoints() -> None:
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, dual = _synthetic_lp(24)
    old = d44.certify_partitioned_lagrangian(lp, dual, chunk_count=3)
    new = d47.certify_weighted_lagrangian(
        lp,
        dual,
        phase="ipx",
        solution_sha256="a" * 64,
        chunk_count=3,
    )
    assert (
        old["formal_lower_bound_eligible"] is new["formal_lower_bound_eligible"] is True
    )
    assert max(_interval(old)[0], _interval(new)[0]) <= min(
        _interval(old)[1], _interval(new)[1]
    )

    invalid_lp = _invalid_free_column_lp()
    invalid_old = d44.certify_partitioned_lagrangian(invalid_lp, [], chunk_count=1)
    invalid_new = d47.certify_weighted_lagrangian(
        invalid_lp,
        [],
        phase="ipx",
        solution_sha256="a" * 64,
        chunk_count=1,
    )
    assert invalid_old["formal_lower_bound_eligible"] is False
    assert invalid_new["formal_lower_bound_eligible"] is False
    assert invalid_new["invalid_column_endpoint_count"] == 1


def test_completion_order_cannot_change_certificate() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, dual = _synthetic_lp(32)
    canonical = d47.certify_weighted_lagrangian(
        lp,
        dual,
        phase="ipx",
        solution_sha256="a" * 64,
        chunk_count=8,
        chunk_executor=_inline_executor,
    )

    def reversed_executor(lp, projected, chunks):
        return list(reversed(_inline_executor(lp, projected, chunks)))

    reversed_result = d47.certify_weighted_lagrangian(
        lp,
        dual,
        phase="ipx",
        solution_sha256="a" * 64,
        chunk_count=8,
        chunk_executor=reversed_executor,
    )
    assert reversed_result == canonical


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "out_of_range", "range", "hash", "nonzeros"],
)
def test_partial_duplicate_and_tampered_raw_chunks_are_rejected(fault: str) -> None:
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, dual = _synthetic_lp(32)

    def faulty_executor(lp, projected, chunks):
        audits = _inline_executor(lp, projected, chunks)
        if fault == "missing":
            return audits[:-1]
        if fault == "duplicate":
            return [*audits[:-1], audits[0]]
        altered = dict(audits[-1])
        if fault == "out_of_range":
            altered["chunk_id"] = len(chunks)
        elif fault == "range":
            altered["start_column"] -= 1
        elif fault == "hash":
            altered["lower_bound_decimal"] = "123"
            audits[-1] = altered
            return audits
        else:
            altered["nonzero_count"] += 1
        payload = {
            key: value for key, value in altered.items() if key != "content_sha256"
        }
        altered["content_sha256"] = d44._canonical_hash(payload)
        audits[-1] = altered
        return audits

    with pytest.raises(ValueError):
        d47.certify_weighted_lagrangian(
            lp,
            dual,
            phase="ipx",
            solution_sha256="a" * 64,
            chunk_count=8,
            chunk_executor=faulty_executor,
        )


@pytest.mark.parametrize(
    "axis",
    ["phase", "lp", "solution", "partition", "work", "nonzeros", "hash"],
)
def test_assembly_rejects_every_chunk_identity_axis(axis: str) -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, lp_sha256, solution_sha256, row, partition, wrapped = _assembly_fixture()
    changed = [dict(audit) for audit in wrapped]
    if axis == "phase":
        changed[0]["phase"] = "simplex_1"
    elif axis == "lp":
        changed[0]["lp_sha256"] = "b" * 64
    elif axis == "solution":
        changed[0]["solution_sha256"] = "b" * 64
    elif axis == "partition":
        changed[0]["partition_sha256"] = "b" * 64
    elif axis == "work":
        changed[0]["work_weight"] += 1
    elif axis == "nonzeros":
        changed[0]["nonzero_count"] += 1
    else:
        changed[0]["lower_bound_decimal"] = "123"
    if axis != "hash":
        payload = {
            key: value for key, value in changed[0].items() if key != "content_sha256"
        }
        changed[0]["content_sha256"] = d47._canonical_hash(payload)
    with pytest.raises(ValueError):
        d47.assemble_weighted_certificate(
            lp=lp,
            phase="ipx",
            lp_sha256=lp_sha256,
            solution_sha256=solution_sha256,
            precision=80,
            row_total_lower=row["row_total_lower"],
            row_total_upper=row["row_total_upper"],
            row_multiplier_count=row["row_multiplier_count"],
            projected_count=row["projected_count"],
            partition=partition,
            chunk_audits=changed,
        )


def test_certificate_path_never_invokes_highs_solver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import highspy
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    lp, dual = _synthetic_lp(24)

    def forbidden(_self):
        raise AssertionError("D47 certificate invoked a native solver")

    monkeypatch.setattr(highspy.Highs, "run", forbidden)
    result = d47.certify_weighted_lagrangian(
        lp,
        dual,
        phase="ipx",
        solution_sha256="a" * 64,
        chunk_count=4,
    )
    assert result["formal_lower_bound_eligible"] is True


def test_d45_input_gate_binds_all_required_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256

    manifest = {
        "status": "no_strict_certificate",
        "formal_lower_bound_eligible": False,
        "formal_lower_bound_decimal": None,
        "selected_phase": None,
        "d46_feasible_upper_bound_contract_permitted": False,
        "technical_ranking_permitted": False,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "execution.json").write_text(
        json.dumps({"status": "no_strict_certificate"}), encoding="utf-8"
    )
    (tmp_path / "artifact_sha256.txt").write_text("locked\n", encoding="utf-8")
    (tmp_path / "presolved_lp.bin.gz").write_bytes(b"locked-lp")
    phases = []
    for key in ("ipx", "simplex_1"):
        solution_name = f"{key}.solution"
        execution_name = f"{key}.execution"
        (tmp_path / solution_name).write_bytes(f"solution-{key}".encode())
        (tmp_path / execution_name).write_bytes(f"execution-{key}".encode())
        phases.append(
            d47.FrozenPhase(
                key,
                solution_name,
                _sha256(tmp_path / solution_name),
                execution_name,
                _sha256(tmp_path / execution_name),
            )
        )
    monkeypatch.setattr(d47, "PHASES", tuple(phases))
    monkeypatch.setattr(
        d47, "D45_FORMAL_MANIFEST_SHA256", _sha256(tmp_path / "manifest.json")
    )
    monkeypatch.setattr(
        d47, "D45_FORMAL_EXECUTION_SHA256", _sha256(tmp_path / "execution.json")
    )
    monkeypatch.setattr(
        d47, "D45_ARTIFACT_LIST_SHA256", _sha256(tmp_path / "artifact_sha256.txt")
    )
    monkeypatch.setattr(
        d47, "LOCKED_LP_ARCHIVE_SHA256", _sha256(tmp_path / "presolved_lp.bin.gz")
    )

    audit = d47.validate_d45_formal_inputs(tmp_path)
    assert audit["manifest"] == manifest
    (tmp_path / phases[0].solution_name).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="solution SHA-256 mismatch"):
        d47.validate_d45_formal_inputs(tmp_path)


def _gate_a_payload(source: Path, test: Path) -> dict[str, object]:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256

    return {
        "schema_id": d47.GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "platform": "linux",
        "fork_available": True,
        "four_worker_persistence_smoke_passed": True,
        "weighted_partition_passed": True,
        "fraction_direction_passed": True,
        "tamper_rejection_passed": True,
        "phase_fallback_passed": True,
        "identity_gate_passed": True,
        "process_tree_cleanup_passed": True,
        "directed_regression_passed": True,
        "full_regression_passed": True,
        "source_sha256": _sha256(source),
        "test_sha256": _sha256(test),
        "test_failed_count": 0,
        "test_skipped_count": 0,
        "test_passed_count": 20,
        "optimization_invoked": False,
        "partition_chunk_count": 56,
        "git_commit": "a" * 40,
    }


def test_gate_a_manifest_binds_source_test_commit_and_zero_skips(
    tmp_path: Path,
) -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d42_gate_b_executor import _atomic_write_json

    source = Path(d47.__file__)
    test = Path(__file__)
    manifest = tmp_path / "gate_a_manifest.json"
    payload = _gate_a_payload(source, test)
    _atomic_write_json(manifest, payload)
    audit = d47.validate_gate_a_manifest(
        gate_a_manifest_path=manifest,
        d47_test_path=test,
    )
    assert audit["git_commit"] == "a" * 40
    _atomic_write_json(manifest, {**payload, "test_skipped_count": 1})
    with pytest.raises(ValueError, match="failed or skipped"):
        d47.validate_gate_a_manifest(
            gate_a_manifest_path=manifest,
            d47_test_path=test,
        )


def _phase_audit(*, eligible: bool, lower: str | None = None) -> dict[str, object]:
    return {
        "status": "certified_finite_lower_bound" if eligible else "phase_failed",
        "formal_lower_bound_eligible": eligible,
        "lower_bound_decimal": lower,
        "upper_bound_decimal": lower,
    }


def test_manifest_stops_at_eligible_ipx() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    manifest = d47.assemble_manifest(
        input_audit={"input_sha256": {}},
        dependency_hashes={},
        gate_a_audit={},
        phase_audits={
            "ipx": _phase_audit(eligible=True, lower="10"),
            "simplex_1": _phase_audit(eligible=True, lower="11"),
        },
    )
    assert manifest["selected_phase"] == "ipx"
    assert manifest["d46_feasible_upper_bound_contract_permitted"] is True


def test_manifest_falls_back_to_simplex_only_after_ipx_failure() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    manifest = d47.assemble_manifest(
        input_audit={"input_sha256": {}},
        dependency_hashes={},
        gate_a_audit={},
        phase_audits={
            "ipx": _phase_audit(eligible=False),
            "simplex_1": _phase_audit(eligible=True, lower="11"),
        },
    )
    assert manifest["selected_phase"] == "simplex_1"
    assert manifest["formal_lower_bound_decimal"] == "11"


def test_manifest_and_readme_reject_partial_chunks_as_a_bound() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    manifest = d47.assemble_manifest(
        input_audit={"input_sha256": {}},
        dependency_hashes={},
        gate_a_audit={},
        phase_audits={
            "ipx": _phase_audit(eligible=False),
            "simplex_1": _phase_audit(eligible=False),
        },
    )
    assert manifest["status"] == "no_strict_certificate"
    assert manifest["formal_lower_bound_decimal"] is None
    assert manifest["d46_feasible_upper_bound_contract_permitted"] is False
    readme = d47.render_readme(manifest, manifest_sha256="a" * 64)
    assert "Partial chunks are diagnostic only" in readme
    assert "do not form a lower bound" in readme


def test_parser_exposes_only_ipx_and_simplex_one() -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    parser = d47.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "_phase-child",
                "--d45-formal-dir",
                "x",
                "--phase",
                "simplex_2",
                "--output-dir",
                "y",
            ]
        )


@pytest.mark.skipif(
    platform.system().lower() != "linux"
    or "fork" not in multiprocessing.get_all_start_methods(),
    reason="D47 persistence smoke requires Linux fork",
)
def test_linux_four_worker_atomic_persistence_smoke(tmp_path: Path) -> None:
    import tes_bess_boundary.e0d44_fork_parallel_certificate as d44
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47
    from tes_bess_boundary.e0d42_native_highs_certificate import fingerprint_highs_lp

    lp, dual = _synthetic_lp(24)
    lp_sha256 = fingerprint_highs_lp(lp)
    solution_sha256 = "a" * 64
    row = d44.project_row_terms(lp, dual)
    chunks = d47.weighted_column_chunks(lp, 4)
    partition = d47.build_partition_manifest(
        lp,
        lp_sha256=lp_sha256,
        chunks=chunks,
    )
    audits = d47.evaluate_chunks_fork_persistent(
        lp,
        row["projected"],
        chunks,
        workers=4,
        precision=80,
        phase="ipx",
        lp_sha256=lp_sha256,
        solution_sha256=solution_sha256,
        partition=partition,
        chunk_dir=tmp_path / "chunks",
        progress_path=tmp_path / "progress.json",
        completion_path=tmp_path / "completion.ndjson",
    )
    certificate = d47.assemble_weighted_certificate(
        lp=lp,
        phase="ipx",
        lp_sha256=lp_sha256,
        solution_sha256=solution_sha256,
        precision=80,
        row_total_lower=row["row_total_lower"],
        row_total_upper=row["row_total_upper"],
        row_multiplier_count=row["row_multiplier_count"],
        projected_count=row["projected_count"],
        partition=partition,
        chunk_audits=audits,
    )
    assert certificate["formal_lower_bound_eligible"] is True
    assert len(list((tmp_path / "chunks").glob("chunk_*.json"))) == 4
    assert len((tmp_path / "completion.ndjson").read_text().splitlines()) == 4
    assert json.loads((tmp_path / "progress.json").read_text())["completed_chunks"] == 4


@pytest.mark.skipif(
    platform.system().lower() != "linux",
    reason="D47 process-group cleanup requires Linux /proc",
)
def test_linux_phase_hard_wall_cleans_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate as d47

    command = [
        sys.executable,
        "-c",
        (
            "import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
            "time.sleep(30)"
        ),
    ]
    monkeypatch.setattr(d47, "_phase_command", lambda *_args, **_kwargs: command)
    monkeypatch.setattr(d47, "PHASE_HARD_WALL_SECONDS", 0.05)
    monkeypatch.setattr(d47, "STAGE_HARD_WALL_SECONDS", 2.0)
    monkeypatch.setattr(d47, "TOTAL_HARD_WALL_SECONDS", 3.0)
    monkeypatch.setattr(d47, "MONITOR_INTERVAL_SECONDS", 0.01)
    execution = d47.run_monitored_phase(
        d45_formal_dir=tmp_path / "unused",
        output_dir=tmp_path / "out",
        phase="ipx",
        total_run_started=perf_counter(),
    )
    assert execution["status"] == "interrupted_or_failed"
    assert execution["stop_reason"] == "phase_hard_wall_reached:ipx"
    assert execution["residual_process_group_detected"] is False
    assert (
        execution["process_group_cleanup_audit"]["active_members_after_cleanup"] == []
    )
