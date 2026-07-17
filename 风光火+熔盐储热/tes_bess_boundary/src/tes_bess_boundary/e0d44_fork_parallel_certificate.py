"""E0-D-44 fork-parallel 80-digit Lagrangian certificate recovery.

The formal path is read-only.  It validates the hash-locked D42 LP and dual
snapshots, partitions all columns deterministically, and evaluates the same
outward-rounded Lagrangian expression in Linux fork workers.  It never builds
or solves an optimization model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Sequence

from tes_bess_boundary import e0d43_offline_dual_certificate as d43_module
from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
from tes_bess_boundary.e0d42_gate_b_executor import (
    _atomic_write_json,
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _terminate_process_group,
    read_lp_archive,
)
from tes_bess_boundary.e0d42_native_highs_certificate import (
    _decimal,
    _product_interval,
    _residual_bound_interval,
    audit_highs_lp,
    fingerprint_highs_lp,
)


SCHEMA_ID = "tes_bess_boundary.e0d44_fork_parallel_certificate.v1"
CHUNK_SCHEMA_ID = f"{SCHEMA_ID}.chunk"
CERTIFICATE_SCHEMA_ID = f"{SCHEMA_ID}.certificate"
PHASE_RESULT_SCHEMA_ID = f"{SCHEMA_ID}.phase"
PHASE_EXECUTION_SCHEMA_ID = f"{PHASE_RESULT_SCHEMA_ID}.execution"
MANIFEST_SCHEMA_ID = f"{SCHEMA_ID}.manifest"
EXECUTION_SCHEMA_ID = f"{MANIFEST_SCHEMA_ID}.execution"
GATE_A_SCHEMA_ID = f"{SCHEMA_ID}.gate_a"

LOCKED_D43_SOURCE_SHA256 = (
    "684385d5a33a531a9034f52ad755b7655adc2e58690ca689ad4e2f08eb889791"
)
LOCKED_D43_MANIFEST_SHA256 = (
    "c7b7e42973c30778efb791e2369ec5dc60dd4c70c75db333bfb5d3e1ac8f4526"
)
FORMAL_DECIMAL_PRECISION = 80
FORMAL_CHUNK_COUNT = 24
FORMAL_WORKERS_PER_PHASE = 24
PHASE_HARD_WALL_SECONDS = 900.0
TOTAL_PARENT_HARD_WALL_SECONDS = 1_080.0
PHASE_RSS_LIMIT_GIB = 20.0
AGGREGATE_RSS_LIMIT_GIB = 45.0
HOST_MEMORY_RESERVE_GIB = 30.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class ColumnChunk:
    """One deterministic half-open range of LP columns."""

    chunk_id: int
    start_column: int
    end_column: int


def fixed_column_chunks(num_col: int, chunk_count: int) -> tuple[ColumnChunk, ...]:
    """Return the result-before frozen equal-column partition."""

    if num_col <= 0:
        raise ValueError("D44 requires at least one column")
    if chunk_count <= 0 or chunk_count > num_col:
        raise ValueError("D44 chunk_count must be in [1, num_col]")
    chunks = tuple(
        ColumnChunk(
            chunk_id=index,
            start_column=(index * num_col) // chunk_count,
            end_column=((index + 1) * num_col) // chunk_count,
        )
        for index in range(chunk_count)
    )
    validate_column_partition(chunks, num_col=num_col, chunk_count=chunk_count)
    return chunks


def validate_column_partition(
    chunks: Sequence[ColumnChunk], *, num_col: int, chunk_count: int
) -> None:
    """Reject missing, duplicate, overlapping, empty, or reordered chunks."""

    if len(chunks) != chunk_count:
        raise ValueError("D44 column partition has a missing or duplicate chunk")
    expected_start = 0
    for expected_id, chunk in enumerate(chunks):
        if chunk.chunk_id != expected_id:
            raise ValueError("D44 column partition chunk ids are not canonical")
        if chunk.start_column != expected_start:
            raise ValueError("D44 column partition has a gap or overlap")
        if chunk.end_column <= chunk.start_column:
            raise ValueError("D44 column partition contains an empty chunk")
        expected_start = chunk.end_column
    if expected_start != num_col:
        raise ValueError("D44 column partition does not cover all columns")


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def project_row_terms(
    lp: object,
    row_multipliers: Sequence[float],
    *,
    precision: int = FORMAL_DECIMAL_PRECISION,
) -> dict[str, Any]:
    """Apply the unchanged D42 row projection and row-bound accumulation."""

    audit = audit_highs_lp(lp)
    if precision < FORMAL_DECIMAL_PRECISION:
        raise ValueError("D44 requires decimal precision >= 80")
    if audit["objective_sense"] != "minimize":
        raise ValueError("D44 requires a minimization LP")
    if audit["noncontinuous_column_count"] != 0:
        raise ValueError("D44 requires a continuous LP")
    if len(row_multipliers) != audit["num_row"]:
        raise ValueError("D44 row multiplier length mismatch")
    multiplier_values = tuple(float(value) for value in row_multipliers)
    if not all(math.isfinite(value) for value in multiplier_values):
        raise ValueError("D44 row multipliers must all be finite")

    down = Context(prec=precision, rounding=ROUND_FLOOR)
    up = Context(prec=precision, rounding=ROUND_CEILING)
    total_lower = _decimal(float(lp.offset_))
    total_upper = total_lower
    projected: list[float] = []
    projected_count = 0
    for multiplier, raw_lower, raw_upper in zip(
        multiplier_values,
        lp.row_lower_,
        lp.row_upper_,
        strict=True,
    ):
        lower = float(raw_lower)
        upper = float(raw_upper)
        if lower > upper:
            raise ValueError("D44 row lower bound exceeds upper bound")
        lower_finite = math.isfinite(lower)
        upper_finite = math.isfinite(upper)
        repaired = multiplier
        if not lower_finite and not upper_finite:
            repaired = 0.0
        elif lower_finite and not upper_finite and repaired < 0.0:
            repaired = 0.0
        elif not lower_finite and upper_finite and repaired > 0.0:
            repaired = 0.0
        if repaired != multiplier:
            projected_count += 1
        projected.append(repaired)
        if repaired == 0.0:
            continue
        selected_bound = lower if repaired > 0.0 else upper
        if not math.isfinite(selected_bound):
            raise AssertionError("D44 row projection selected infinity")
        term_lower, term_upper = _product_interval(
            _decimal(repaired),
            _decimal(selected_bound),
            down,
            up,
        )
        total_lower = down.add(total_lower, term_lower)
        total_upper = up.add(total_upper, term_upper)
    return {
        "projected": tuple(_decimal(value) for value in projected),
        "row_total_lower": total_lower,
        "row_total_upper": total_upper,
        "projected_count": projected_count,
        "row_multiplier_count": len(multiplier_values),
        "audit": audit,
    }


def evaluate_column_chunk(
    lp: object,
    projected_multipliers: Sequence[Decimal],
    chunk: ColumnChunk,
    *,
    precision: int = FORMAL_DECIMAL_PRECISION,
) -> dict[str, Any]:
    """Evaluate one column block with the unchanged D42 interval kernel."""

    if precision < FORMAL_DECIMAL_PRECISION:
        raise ValueError("D44 requires decimal precision >= 80")
    num_col = int(lp.num_col_)
    if not (0 <= chunk.start_column < chunk.end_column <= num_col):
        raise ValueError("D44 chunk is outside the LP column range")
    if len(projected_multipliers) != int(lp.num_row_):
        raise ValueError("D44 projected multiplier length mismatch")
    down = Context(prec=precision, rounding=ROUND_FLOOR)
    up = Context(prec=precision, rounding=ROUND_CEILING)
    zero = Decimal(0)
    total_lower = zero
    total_upper = zero
    invalid_columns = 0
    starts = lp.a_matrix_.start_
    indices = lp.a_matrix_.index_
    matrix_values = lp.a_matrix_.value_

    for column in range(chunk.start_column, chunk.end_column):
        activity_lower = zero
        activity_upper = zero
        for position in range(int(starts[column]), int(starts[column + 1])):
            coefficient = _decimal(float(matrix_values[position]))
            multiplier = projected_multipliers[int(indices[position])]
            product_lower, product_upper = _product_interval(
                coefficient,
                multiplier,
                down,
                up,
            )
            activity_lower = down.add(activity_lower, product_lower)
            activity_upper = up.add(activity_upper, product_upper)
        cost = _decimal(float(lp.col_cost_[column]))
        residual_lower = down.subtract(cost, activity_upper)
        residual_upper = up.subtract(cost, activity_lower)
        lower = float(lp.col_lower_[column])
        upper = float(lp.col_upper_[column])
        if lower > upper:
            raise ValueError("D44 column lower bound exceeds upper bound")
        contribution = _residual_bound_interval(
            residual_lower=residual_lower,
            residual_upper=residual_upper,
            lower=lower,
            upper=upper,
            down=down,
            up=up,
        )
        if contribution is None:
            invalid_columns += 1
            continue
        total_lower = down.add(total_lower, contribution[0])
        total_upper = up.add(total_upper, contribution[1])

    payload = {
        "schema_id": CHUNK_SCHEMA_ID,
        **asdict(chunk),
        "nonzero_count": int(starts[chunk.end_column])
        - int(starts[chunk.start_column]),
        "lower_bound_decimal": str(total_lower),
        "upper_bound_decimal": str(total_upper),
        "invalid_column_endpoint_count": invalid_columns,
    }
    return {**payload, "content_sha256": _canonical_hash(payload)}


def assemble_partitioned_certificate(
    *,
    lp_sha256: str,
    precision: int,
    row_total_lower: Decimal,
    row_total_upper: Decimal,
    row_multiplier_count: int,
    projected_count: int,
    num_col: int,
    chunk_count: int,
    expected_chunk_nonzero_counts: Sequence[int],
    chunk_audits: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Validate every block and combine them in canonical chunk-id order."""

    expected = fixed_column_chunks(num_col, chunk_count)
    if len(expected_chunk_nonzero_counts) != chunk_count:
        raise ValueError("D44 expected nonzero-count vector length mismatch")
    if len(chunk_audits) != chunk_count:
        raise ValueError("D44 cannot assemble a partial chunk set")
    by_id: dict[int, dict[str, Any]] = {}
    for audit in chunk_audits:
        if audit.get("schema_id") != CHUNK_SCHEMA_ID:
            raise ValueError("D44 chunk schema mismatch")
        chunk_id = audit.get("chunk_id")
        if not isinstance(chunk_id, int) or chunk_id in by_id:
            raise ValueError("D44 chunk id is missing, duplicated, or invalid")
        payload = {key: value for key, value in audit.items() if key != "content_sha256"}
        if audit.get("content_sha256") != _canonical_hash(payload):
            raise ValueError("D44 chunk content hash mismatch")
        by_id[chunk_id] = audit

    down = Context(prec=precision, rounding=ROUND_FLOOR)
    up = Context(prec=precision, rounding=ROUND_CEILING)
    total_lower = row_total_lower
    total_upper = row_total_upper
    if (
        not total_lower.is_finite()
        or not total_upper.is_finite()
        or total_lower > total_upper
    ):
        raise ValueError("D44 row interval is invalid")
    invalid_columns = 0
    ordered: list[dict[str, Any]] = []
    for chunk in expected:
        audit = by_id.get(chunk.chunk_id)
        if audit is None:
            raise ValueError("D44 chunk set has a missing id")
        if audit.get("start_column") != chunk.start_column or audit.get(
            "end_column"
        ) != chunk.end_column:
            raise ValueError("D44 chunk range differs from the frozen partition")
        nonzero_count = audit.get("nonzero_count")
        if (
            not isinstance(nonzero_count, int)
            or nonzero_count < 0
            or nonzero_count != expected_chunk_nonzero_counts[chunk.chunk_id]
        ):
            raise ValueError("D44 chunk nonzero count differs from the frozen LP")
        lower = Decimal(str(audit["lower_bound_decimal"]))
        upper = Decimal(str(audit["upper_bound_decimal"]))
        if not lower.is_finite() or not upper.is_finite() or lower > upper:
            raise ValueError("D44 chunk interval is invalid")
        invalid = audit.get("invalid_column_endpoint_count")
        if not isinstance(invalid, int) or invalid < 0:
            raise ValueError("D44 chunk invalid-column count is invalid")
        invalid_columns += invalid
        total_lower = down.add(total_lower, lower)
        total_upper = up.add(total_upper, upper)
        ordered.append(audit)

    eligible = invalid_columns == 0 and total_lower.is_finite()
    lower_decimal = str(total_lower) if eligible else None
    upper_decimal = str(total_upper) if eligible else None
    lower_float = float(total_lower) if eligible else None
    if lower_float is not None and not math.isfinite(lower_float):
        raise ValueError("D44 lower bound is not representable as finite float")
    width = up.subtract(total_upper, total_lower) if eligible else None
    return {
        "schema_id": CERTIFICATE_SCHEMA_ID,
        "lp_sha256": lp_sha256,
        "precision": precision,
        "partition_rule": "floor(k*num_col/chunk_count):floor((k+1)*num_col/chunk_count)",
        "chunk_count": chunk_count,
        "row_multiplier_count": row_multiplier_count,
        "projected_row_multiplier_count": projected_count,
        "invalid_column_endpoint_count": invalid_columns,
        "lower_bound_decimal": lower_decimal,
        "upper_bound_decimal": upper_decimal,
        "lower_bound_float": lower_float,
        "interval_width_decimal": str(width) if width is not None else None,
        "formal_lower_bound_eligible": eligible,
        "status": (
            "certified_finite_lower_bound"
            if eligible
            else "nonfinite_required_column_endpoint"
        ),
        "chunks": ordered,
    }


_FORK_LP: object | None = None
_FORK_PROJECTED: Sequence[Decimal] | None = None
_FORK_PRECISION = FORMAL_DECIMAL_PRECISION


def _fork_chunk_worker(chunk: ColumnChunk) -> dict[str, Any]:
    if _FORK_LP is None or _FORK_PROJECTED is None:
        raise RuntimeError("D44 fork worker was not initialized")
    return evaluate_column_chunk(
        _FORK_LP,
        _FORK_PROJECTED,
        chunk,
        precision=_FORK_PRECISION,
    )


def _append_ndjson(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


def evaluate_chunks_fork(
    lp: object,
    projected_multipliers: Sequence[Decimal],
    chunks: Sequence[ColumnChunk],
    *,
    workers: int,
    precision: int,
    progress_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate chunks in Linux fork workers without serializing the LP."""

    if "fork" not in multiprocessing.get_all_start_methods():
        raise RuntimeError("D44 formal parallelism requires Linux fork")
    if workers <= 0 or workers > len(chunks):
        raise ValueError("D44 worker count must be in [1, chunk_count]")
    global _FORK_LP, _FORK_PRECISION, _FORK_PROJECTED
    _FORK_LP = lp
    _FORK_PROJECTED = projected_multipliers
    _FORK_PRECISION = precision
    context = multiprocessing.get_context("fork")
    pool = context.Pool(processes=workers)
    results: list[dict[str, Any]] = []
    started = perf_counter()
    try:
        for result in pool.imap_unordered(_fork_chunk_worker, chunks, chunksize=1):
            results.append(result)
            if progress_path is not None:
                _append_ndjson(
                    progress_path,
                    {
                        "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                        "completed_chunks": len(results),
                        "chunk_count": len(chunks),
                        "last_completed_chunk_id": result["chunk_id"],
                        "elapsed_seconds": perf_counter() - started,
                    },
                )
        pool.close()
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()
        _FORK_LP = None
        _FORK_PROJECTED = None
    return results


def certify_partitioned_lagrangian(
    lp: object,
    row_multipliers: Sequence[float],
    *,
    expected_lp_sha256: str | None = None,
    precision: int = FORMAL_DECIMAL_PRECISION,
    chunk_count: int = FORMAL_CHUNK_COUNT,
    fork_workers: int | None = None,
    progress_path: Path | None = None,
    chunk_executor: Callable[
        [object, Sequence[Decimal], Sequence[ColumnChunk]], Sequence[dict[str, Any]]
    ]
    | None = None,
) -> dict[str, Any]:
    """Create a rigorous partitioned certificate from one frozen row dual."""

    lp_sha256 = fingerprint_highs_lp(lp)
    if expected_lp_sha256 is not None and lp_sha256 != expected_lp_sha256:
        raise ValueError("D44 LP fingerprint differs from the locked identity")
    row = project_row_terms(lp, row_multipliers, precision=precision)
    num_col = int(row["audit"]["num_col"])
    chunks = fixed_column_chunks(num_col, chunk_count)
    starts = lp.a_matrix_.start_
    expected_chunk_nonzero_counts = tuple(
        int(starts[chunk.end_column]) - int(starts[chunk.start_column])
        for chunk in chunks
    )
    if chunk_executor is not None:
        chunk_audits = list(chunk_executor(lp, row["projected"], chunks))
    elif fork_workers is not None:
        chunk_audits = evaluate_chunks_fork(
            lp,
            row["projected"],
            chunks,
            workers=fork_workers,
            precision=precision,
            progress_path=progress_path,
        )
    else:
        chunk_audits = [
            evaluate_column_chunk(
                lp,
                row["projected"],
                chunk,
                precision=precision,
            )
            for chunk in chunks
        ]
    return assemble_partitioned_certificate(
        lp_sha256=lp_sha256,
        precision=precision,
        row_total_lower=row["row_total_lower"],
        row_total_upper=row["row_total_upper"],
        row_multiplier_count=row["row_multiplier_count"],
        projected_count=row["projected_count"],
        num_col=num_col,
        chunk_count=chunk_count,
        expected_chunk_nonzero_counts=expected_chunk_nonzero_counts,
        chunk_audits=chunk_audits,
    )


def _phase_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    return {
        "certificate": output_dir / f"{phase}_certificate.json",
        "chunks": output_dir / f"{phase}_chunks.json",
        "result": output_dir / f"{phase}_result.json",
        "execution": output_dir / f"{phase}_execution.json",
        "progress": output_dir / f"{phase}_progress.ndjson",
        "heartbeat": output_dir / f"{phase}_heartbeat.ndjson",
        "log": output_dir / f"{phase}_child.log",
    }


def certify_snapshot_child(
    *,
    lp_archive_path: Path,
    solution_path: Path,
    phase_execution_path: Path,
    output_dir: Path,
    spec: d43_module.SnapshotSpec,
    expected_lp_archive_sha256: str = d43_module.LOCKED_LP_ARCHIVE_SHA256,
    expected_lp_sha256: str = d43_module.LOCKED_LP_SHA256,
    expected_num_col: int = d43_module.FORMAL_NUM_COL,
    expected_num_row: int = d43_module.FORMAL_NUM_ROW,
    chunk_count: int = FORMAL_CHUNK_COUNT,
    fork_workers: int | None = FORMAL_WORKERS_PER_PHASE,
) -> dict[str, Any]:
    """Validate one snapshot and create its D44 certificate."""

    paths = _phase_paths(output_dir, spec.key)
    if any(paths[key].exists() for key in ("certificate", "chunks", "result")):
        raise FileExistsError("D44 refuses to overwrite phase artifacts")
    lp, lp_audit = read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    if lp_audit["archive_sha256"] != expected_lp_archive_sha256:
        raise ValueError("D44 LP archive hash mismatch")
    if lp_audit["audit"]["num_col"] != expected_num_col:
        raise ValueError("D44 LP column count mismatch")
    if lp_audit["audit"]["num_row"] != expected_num_row:
        raise ValueError("D44 LP row count mismatch")
    row_dual, snapshot_audit = d43_module.load_locked_snapshot(
        solution_path=solution_path,
        phase_execution_path=phase_execution_path,
        phase=spec.key,
        expected_solution_sha256=spec.solution_sha256,
        expected_phase_execution_sha256=spec.phase_execution_sha256,
        expected_lp_sha256=expected_lp_sha256,
        expected_num_col=expected_num_col,
        expected_num_row=expected_num_row,
    )
    certificate = certify_partitioned_lagrangian(
        lp,
        row_dual,
        expected_lp_sha256=expected_lp_sha256,
        precision=FORMAL_DECIMAL_PRECISION,
        chunk_count=chunk_count,
        fork_workers=fork_workers,
        progress_path=paths["progress"],
    )
    chunks_payload = {
        "schema_id": f"{SCHEMA_ID}.chunks",
        "phase": spec.key,
        "chunk_count": chunk_count,
        "chunks": certificate["chunks"],
    }
    _atomic_write_json(paths["chunks"], chunks_payload)
    _atomic_write_json(paths["certificate"], certificate)
    result = {
        "schema_id": PHASE_RESULT_SCHEMA_ID,
        "phase": spec.key,
        "status": certificate["status"],
        "lp_sha256": expected_lp_sha256,
        "snapshot_audit": snapshot_audit,
        "lp_archive_audit": lp_audit,
        "certificate_sha256": _sha256(paths["certificate"]),
        "chunks_sha256": _sha256(paths["chunks"]),
        "formal_lower_bound_eligible": certificate[
            "formal_lower_bound_eligible"
        ],
        "lower_bound_decimal": certificate["lower_bound_decimal"],
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(paths["result"], result)
    return result


def validate_structure_identity(structure_manifest: dict[str, Any]) -> None:
    identity = structure_manifest.get("tes_r0_r1_identity")
    if not isinstance(identity, dict):
        raise ValueError("D44 structure manifest has no TES identity audit")
    if identity.get("original_lp_fingerprint_equal") is not True:
        raise ValueError("D44 TES original LP identity is not proven")
    if identity.get("presolved_lp_fingerprint_equal") is not True:
        raise ValueError("D44 TES presolved LP identity is not proven")
    if identity.get("presolved_lp_sha256") != d43_module.LOCKED_LP_SHA256:
        raise ValueError("D44 structure manifest presolved LP mismatch")
    if structure_manifest.get("formal_gate_b_permitted") is not True:
        raise ValueError("D44 structure manifest does not permit Gate B")


def validate_gate_a_manifest(
    *, gate_a_manifest: Path, d44_test_path: Path
) -> dict[str, Any]:
    """Bind formal execution to a passed same-hash Linux Gate A audit."""

    if not gate_a_manifest.is_file():
        raise FileNotFoundError("D44 Gate A manifest is missing")
    if not d44_test_path.is_file():
        raise FileNotFoundError("D44 Gate A test source is missing")
    payload = json.loads(gate_a_manifest.read_text(encoding="utf-8"))
    if payload.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D44 Gate A manifest schema mismatch")
    if payload.get("status") != "gate_a_passed":
        raise ValueError("D44 Gate A did not pass")
    if payload.get("platform") != "linux" or payload.get("fork_available") is not True:
        raise ValueError("D44 Gate A did not verify Linux fork")
    if payload.get("four_worker_fork_smoke_passed") is not True:
        raise ValueError("D44 Gate A four-worker fork smoke did not pass")
    for claim in (
        "fraction_reference_passed",
        "chunk_count_equivalence_passed",
        "failure_injection_passed",
        "directed_regression_passed",
        "full_regression_passed",
    ):
        if payload.get(claim) is not True:
            raise ValueError(f"D44 Gate A required claim is false: {claim}")
    source_sha256 = _sha256(Path(__file__))
    test_sha256 = _sha256(d44_test_path)
    if payload.get("source_sha256") != source_sha256:
        raise ValueError("D44 Gate A production source SHA-256 mismatch")
    if payload.get("test_sha256") != test_sha256:
        raise ValueError("D44 Gate A test source SHA-256 mismatch")
    if payload.get("test_failed_count") != 0 or payload.get("test_skipped_count") != 0:
        raise ValueError("D44 Gate A contains failed or skipped tests")
    passed_count = payload.get("test_passed_count")
    if not isinstance(passed_count, int) or passed_count < 23:
        raise ValueError("D44 Gate A test pass count is incomplete")
    commit = payload.get("git_commit")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("D44 Gate A has no full lowercase Git commit identity")
    return {
        "manifest_sha256": _sha256(gate_a_manifest),
        "source_sha256": source_sha256,
        "test_sha256": test_sha256,
        "git_commit": commit,
        "test_passed_count": passed_count,
    }


def validate_formal_inputs(
    *,
    d42_dir: Path,
    structure_manifest: Path,
    d43_manifest: Path,
    gate_a_manifest: Path,
    d44_test_path: Path,
) -> dict[str, Any]:
    """Validate the complete D42/D43 chain before any formal D44 child starts."""

    d43_module._validate_formal_inputs(d42_dir, structure_manifest)
    if _sha256(Path(d43_module.__file__)) != LOCKED_D43_SOURCE_SHA256:
        raise ValueError("D44 D43 validator source SHA-256 mismatch")
    if not d43_manifest.is_file() or _sha256(d43_manifest) != LOCKED_D43_MANIFEST_SHA256:
        raise ValueError("D44 D43 formal manifest SHA-256 mismatch")
    d43_payload = json.loads(d43_manifest.read_text(encoding="utf-8"))
    if (
        d43_payload.get("status") != "no_strict_certificate"
        or d43_payload.get("formal_lower_bound_eligible") is not False
        or d43_payload.get("optimization_invoked") is not False
        or d43_payload.get("native_solver_invoked") is not False
    ):
        raise ValueError("D44 D43 terminal claim boundary mismatch")
    structure_payload = json.loads(structure_manifest.read_text(encoding="utf-8"))
    validate_structure_identity(structure_payload)
    return validate_gate_a_manifest(
        gate_a_manifest=gate_a_manifest,
        d44_test_path=d44_test_path,
    )


def monitor_stop_reason(
    *,
    phase_elapsed_seconds: dict[str, float],
    total_elapsed_seconds: float,
    phase_rss_gib: dict[str, float | None],
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    if total_elapsed_seconds >= TOTAL_PARENT_HARD_WALL_SECONDS:
        return "total_parent_hard_wall_reached"
    for spec in d43_module.SNAPSHOT_SPECS:
        if phase_elapsed_seconds.get(spec.key, 0.0) >= PHASE_HARD_WALL_SECONDS:
            return f"phase_hard_wall_reached:{spec.key}"
    for spec in d43_module.SNAPSHOT_SPECS:
        rss = phase_rss_gib.get(spec.key)
        if rss is not None and rss >= PHASE_RSS_LIMIT_GIB:
            return f"phase_rss_limit_reached:{spec.key}"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB:
        return "aggregate_rss_limit_reached"
    if (
        available_memory_gib is not None
        and available_memory_gib < HOST_MEMORY_RESERVE_GIB
    ):
        return "host_memory_reserve_breached"
    return None


def _completed_chunks(progress_path: Path) -> int:
    if not progress_path.is_file():
        return 0
    with progress_path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def assemble_manifest(
    *,
    phase_results: dict[str, dict[str, Any]],
    phase_artifacts: dict[str, dict[str, str | None]],
    source_sha256: dict[str, str],
    gate_a_audit: dict[str, Any],
) -> dict[str, Any]:
    eligible: list[tuple[Decimal, int, str]] = []
    for order, spec in enumerate(d43_module.SNAPSHOT_SPECS):
        result = phase_results[spec.key]
        if result.get("formal_lower_bound_eligible") is True:
            value = result.get("lower_bound_decimal")
            if not isinstance(value, str) or not Decimal(value).is_finite():
                raise ValueError("D44 eligible phase has no finite Decimal bound")
            eligible.append((Decimal(value), -order, spec.key))
    selected_phase = max(eligible)[2] if eligible else None
    selected_result = phase_results[selected_phase] if selected_phase else None
    recovered = selected_result is not None
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "status": "tes_lower_bound_recovered" if recovered else "no_strict_certificate",
        "architecture": "tes",
        "relaxation_mode": "r0_all_continuous",
        "claim_scope": "controlled_public_cost_sensitivity_not_formal_project_tac",
        "partition_rule": "floor(k*num_col/24):floor((k+1)*num_col/24)",
        "chunk_count_per_phase": FORMAL_CHUNK_COUNT,
        "workers_per_phase": FORMAL_WORKERS_PER_PHASE,
        "selected_phase": selected_phase,
        "formal_lower_bound_decimal": (
            selected_result["lower_bound_decimal"] if selected_result else None
        ),
        "formal_lower_bound_float": (
            float(selected_result["lower_bound_decimal"])
            if selected_result
            else None
        ),
        "formal_lower_bound_eligible": recovered,
        "tes_r0_certificate_covers_r1": recovered,
        "hybrid_lower_bound_contract_permitted": recovered,
        "formal_project_tac_ready": False,
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
        "input_sha256": {
            "case_manifest": d43_module.LOCKED_CASE_MANIFEST_SHA256,
            "case_execution": d43_module.LOCKED_CASE_EXECUTION_SHA256,
            "lp_manifest": d43_module.LOCKED_LP_MANIFEST_SHA256,
            "lp_execution": d43_module.LOCKED_LP_EXECUTION_SHA256,
            "lp_archive": d43_module.LOCKED_LP_ARCHIVE_SHA256,
            "structure_manifest": d43_module.LOCKED_STRUCTURE_MANIFEST_SHA256,
            "bess_reuse_result": d43_module.LOCKED_BESS_REUSE_RESULT_SHA256,
            "d43_manifest": LOCKED_D43_MANIFEST_SHA256,
            "d44_gate_a_manifest": gate_a_audit["manifest_sha256"],
            **{
                f"{spec.key}_solution": spec.solution_sha256
                for spec in d43_module.SNAPSHOT_SPECS
            },
            **{
                f"{spec.key}_phase_execution": spec.phase_execution_sha256
                for spec in d43_module.SNAPSHOT_SPECS
            },
        },
        "source_sha256": source_sha256,
        "gate_a_audit": gate_a_audit,
        "phase_audits": {
            spec.key: {
                "status": phase_results[spec.key].get("status"),
                "formal_lower_bound_eligible": phase_results[spec.key].get(
                    "formal_lower_bound_eligible"
                )
                is True,
                "lower_bound_decimal": phase_results[spec.key].get(
                    "lower_bound_decimal"
                ),
                **phase_artifacts[spec.key],
            }
            for spec in d43_module.SNAPSHOT_SPECS
        },
    }


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def render_readme(manifest: dict[str, Any], *, manifest_sha256: str) -> str:
    selected = manifest.get("selected_phase") or "none"
    lower = manifest.get("formal_lower_bound_decimal") or "none"
    return (
        "# E0-D-44 fork-parallel Lagrangian certificate\n\n"
        f"- Status: `{manifest['status']}`\n"
        f"- Selected frozen snapshot: `{selected}`\n"
        f"- TES R0 formal lower bound (CNY): `{lower}`\n"
        f"- Manifest SHA-256: `{manifest_sha256}`\n"
        "- Optimization/native solver invoked: `false`\n"
        "- Technical ranking permitted: `false`\n\n"
        "This result audits hash-locked D42 row duals with a deterministic "
        "24-chunk, 80-digit outward-rounded certificate. It is not a feasible "
        "upper bound, capacity plan, project TAC, or technology ranking.\n"
    )


def _child_command(d42_dir: Path, output_dir: Path, phase: str) -> list[str]:
    return [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d44_fork_parallel_certificate",
        "_child",
        "--d42-dir",
        str(d42_dir),
        "--output-dir",
        str(output_dir),
        "--phase",
        phase,
    ]


def run_formal_recovery(
    *,
    d42_dir: Path,
    structure_manifest: Path,
    d43_manifest: Path,
    gate_a_manifest: Path,
    d44_test_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the one-shot two-phase D44 formal recovery."""

    if output_dir.exists():
        raise FileExistsError("D44 formal output directory must not already exist")
    if "fork" not in multiprocessing.get_all_start_methods():
        raise RuntimeError("D44 formal recovery requires Linux fork")
    gate_a_audit = validate_formal_inputs(
        d42_dir=d42_dir,
        structure_manifest=structure_manifest,
        d43_manifest=d43_manifest,
        gate_a_manifest=gate_a_manifest,
        d44_test_path=d44_test_path,
    )
    available_before = _available_memory_gib()
    if available_before is None or available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D44 host memory is below the frozen reserve")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    processes: dict[str, subprocess.Popen[Any]] = {}
    logs: dict[str, Any] = {}
    phase_started: dict[str, float] = {}
    next_heartbeat = {spec.key: 0.0 for spec in d43_module.SNAPSHOT_SPECS}
    peak_phase = {spec.key: 0.0 for spec in d43_module.SNAPSHOT_SPECS}
    peak_aggregate = 0.0
    minimum_available = available_before
    stop_reason: str | None = None
    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
    for spec in d43_module.SNAPSHOT_SPECS:
        paths = _phase_paths(output_dir, spec.key)
        log_handle = paths["log"].open("wb")
        logs[spec.key] = log_handle
        process = subprocess.Popen(
            _child_command(d42_dir, output_dir, spec.key),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        processes[spec.key] = process
        phase_started[spec.key] = perf_counter()

    try:
        while any(process.poll() is None for process in processes.values()):
            now = perf_counter()
            total_elapsed = now - started
            phase_elapsed = {
                key: now - phase_started[key]
                for key, process in processes.items()
                if process.poll() is None
            }
            phase_rss = {
                key: (
                    _process_tree_rss_gib(process.pid)
                    if process.poll() is None
                    else None
                )
                for key, process in processes.items()
            }
            for key, rss in phase_rss.items():
                if rss is not None:
                    peak_phase[key] = max(peak_phase[key], rss)
            parent_rss = _process_rss_gib(os.getpid()) or 0.0
            aggregate = parent_rss + sum(rss or 0.0 for rss in phase_rss.values())
            peak_aggregate = max(peak_aggregate, aggregate)
            available = _available_memory_gib()
            if available is not None:
                minimum_available = min(minimum_available, available)
            for spec in d43_module.SNAPSHOT_SPECS:
                if total_elapsed >= next_heartbeat[spec.key]:
                    paths = _phase_paths(output_dir, spec.key)
                    _append_ndjson(
                        paths["heartbeat"],
                        {
                            "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                            "phase": spec.key,
                            "elapsed_seconds": phase_elapsed.get(spec.key),
                            "completed_chunks": _completed_chunks(paths["progress"]),
                            "chunk_count": FORMAL_CHUNK_COUNT,
                            "phase_tree_rss_gib": phase_rss.get(spec.key),
                            "aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                            "state": (
                                "running"
                                if processes[spec.key].poll() is None
                                else "exited"
                            ),
                        },
                    )
                    next_heartbeat[spec.key] = total_elapsed + HEARTBEAT_INTERVAL_SECONDS
            stop_reason = monitor_stop_reason(
                phase_elapsed_seconds=phase_elapsed,
                total_elapsed_seconds=total_elapsed,
                phase_rss_gib=phase_rss,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
            )
            if stop_reason is not None:
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        if stop_reason is not None:
            for process in processes.values():
                if process.poll() is None:
                    _terminate_process_group(process)
        for process in processes.values():
            try:
                process.wait(timeout=35.0)
            except subprocess.TimeoutExpired:
                _terminate_process_group(process)
                process.wait(timeout=5.0)
    finally:
        for handle in logs.values():
            handle.close()

    phase_results: dict[str, dict[str, Any]] = {}
    phase_artifacts: dict[str, dict[str, str | None]] = {}
    for spec in d43_module.SNAPSHOT_SPECS:
        paths = _phase_paths(output_dir, spec.key)
        if paths["result"].is_file():
            result = json.loads(paths["result"].read_text(encoding="utf-8"))
        else:
            result = {
                "schema_id": PHASE_RESULT_SCHEMA_ID,
                "phase": spec.key,
                "status": stop_reason or "phase_child_failed",
                "formal_lower_bound_eligible": False,
                "lower_bound_decimal": None,
                "optimization_invoked": False,
                "native_solver_invoked": False,
                "technical_ranking_permitted": False,
            }
        phase_results[spec.key] = result
        phase_artifacts[spec.key] = {
            "result_sha256": (
                _sha256(paths["result"]) if paths["result"].is_file() else None
            ),
            "certificate_sha256": (
                _sha256(paths["certificate"])
                if paths["certificate"].is_file()
                else None
            ),
            "chunks_sha256": (
                _sha256(paths["chunks"]) if paths["chunks"].is_file() else None
            ),
        }
        execution = {
            "schema_id": PHASE_EXECUTION_SCHEMA_ID,
            "phase": spec.key,
            "return_code": processes[spec.key].returncode,
            "stop_reason": stop_reason,
            "runtime_seconds": perf_counter() - phase_started[spec.key],
            "completed_chunks": _completed_chunks(paths["progress"]),
            "peak_phase_process_tree_rss_gib": peak_phase[spec.key],
            "peak_parent_child_aggregate_rss_gib": peak_aggregate,
            "minimum_available_memory_gib": minimum_available,
            "heartbeat_sha256": (
                _sha256(paths["heartbeat"])
                if paths["heartbeat"].is_file()
                else None
            ),
            "progress_sha256": (
                _sha256(paths["progress"]) if paths["progress"].is_file() else None
            ),
            "child_log_sha256": _sha256(paths["log"]),
            **phase_artifacts[spec.key],
            "formal_lower_bound_eligible": result.get(
                "formal_lower_bound_eligible"
            )
            is True,
            "technical_ranking_permitted": False,
        }
        _atomic_write_json(paths["execution"], execution)
        phase_artifacts[spec.key]["execution_sha256"] = _sha256(paths["execution"])

    source_sha256 = {
        "e0d42_native_highs_certificate.py": d43_module.LOCKED_D42_CERTIFICATE_SOURCE_SHA256,
        "e0d42_gate_b_executor.py": d43_module.LOCKED_D42_EXECUTOR_SOURCE_SHA256,
        "e0d43_offline_dual_certificate.py": LOCKED_D43_SOURCE_SHA256,
        "e0d44_fork_parallel_certificate.py": _sha256(Path(__file__)),
        "test_e0d44_fork_parallel_certificate.py": gate_a_audit["test_sha256"],
    }
    manifest = assemble_manifest(
        phase_results=phase_results,
        phase_artifacts=phase_artifacts,
        source_sha256=source_sha256,
        gate_a_audit=gate_a_audit,
    )
    manifest_path = output_dir / "manifest.json"
    _atomic_write_json(manifest_path, manifest)
    manifest_sha256 = _sha256(manifest_path)
    readme_path = output_dir / "README.md"
    _atomic_write_text(
        readme_path,
        render_readme(manifest, manifest_sha256=manifest_sha256),
    )
    total_execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": manifest["status"],
        "manifest_sha256": manifest_sha256,
        "readme_sha256": _sha256(readme_path),
        "runtime_seconds": perf_counter() - started,
        "stop_reason": stop_reason,
        "available_memory_before_gib": available_before,
        "minimum_available_memory_gib": minimum_available,
        "peak_parent_child_aggregate_rss_gib": peak_aggregate,
        "phase_execution_sha256": {
            spec.key: phase_artifacts[spec.key]["execution_sha256"]
            for spec in d43_module.SNAPSHOT_SPECS
        },
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(output_dir / "execution.json", total_execution)
    return manifest


def _run_child(args: argparse.Namespace) -> None:
    spec = d43_module.SNAPSHOT_BY_KEY[args.phase]
    result = certify_snapshot_child(
        lp_archive_path=args.d42_dir / "presolved_lp.bin.gz",
        solution_path=args.d42_dir / spec.solution_file,
        phase_execution_path=args.d42_dir / spec.phase_execution_file,
        output_dir=args.output_dir,
        spec=spec,
    )
    print(json.dumps(result, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    child = subparsers.add_parser("_child")
    child.add_argument("--d42-dir", type=Path, required=True)
    child.add_argument("--output-dir", type=Path, required=True)
    child.add_argument("--phase", choices=tuple(d43_module.SNAPSHOT_BY_KEY), required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--d42-dir", type=Path, required=True)
    run.add_argument("--structure-manifest", type=Path, required=True)
    run.add_argument("--d43-manifest", type=Path, required=True)
    run.add_argument("--gate-a-manifest", type=Path, required=True)
    run.add_argument("--d44-test-path", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "_child":
        _run_child(args)
        return
    manifest = run_formal_recovery(
        d42_dir=args.d42_dir,
        structure_manifest=args.structure_manifest,
        d43_manifest=args.d43_manifest,
        gate_a_manifest=args.gate_a_manifest,
        d44_test_path=args.d44_test_path,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
