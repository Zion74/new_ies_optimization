"""E0-D-47 weighted persistent certificate recovery for Hybrid R0.

The workflow is read-only with respect to the D45 presolved LP and solution
snapshots.  It never calls a solver.  It balances contiguous column blocks by
their fixed per-column work plus sparse nonzeros, persists every completed
block atomically, and accepts a lower bound only after a complete outward-
rounded certificate has been assembled.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Sequence

from tes_bess_boundary import e0d42_gate_b_executor as d42_executor
from tes_bess_boundary import e0d43_offline_dual_certificate as d43_module
from tes_bess_boundary import e0d44_fork_parallel_certificate as d44_module
from tes_bess_boundary import e0d45_hybrid_r0_strict_lower_bound as d45_module
from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
from tes_bess_boundary.e0d42_native_highs_certificate import fingerprint_highs_lp


SCHEMA_ID = "tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate.v1"
PARTITION_SCHEMA_ID = f"{SCHEMA_ID}.partition"
CHUNK_SCHEMA_ID = f"{SCHEMA_ID}.chunk"
CERTIFICATE_SCHEMA_ID = f"{SCHEMA_ID}.certificate"
PHASE_RESULT_SCHEMA_ID = f"{SCHEMA_ID}.phase"
PHASE_EXECUTION_SCHEMA_ID = f"{PHASE_RESULT_SCHEMA_ID}.execution"
MANIFEST_SCHEMA_ID = f"{SCHEMA_ID}.manifest"
EXECUTION_SCHEMA_ID = f"{MANIFEST_SCHEMA_ID}.execution"
GATE_A_SCHEMA_ID = f"{SCHEMA_ID}.gate_a"

D45_FORMAL_MANIFEST_SHA256 = (
    "668fb0ea4c9293f789781298ca54f56da2bdcb55a3a7806d5bf8171d6e24cc55"
)
D45_FORMAL_EXECUTION_SHA256 = (
    "60af4ee5b16f9aed6ec1a048b87cd57cbaf58b9b90141001ad667bdc71dcbca0"
)
D45_ARTIFACT_LIST_SHA256 = (
    "ef53178bcfdab3cad719d94994c41f8e35906b1593ee95e55e679182303058e9"
)
LOCKED_LP_ARCHIVE_SHA256 = (
    "e84eb73544153e0fa1381d753ae154404eed82a661a8397719a0973b0dd43b12"
)
LOCKED_LP_SHA256 = "756014eca3a93581a09f0abf99b42fd52e73a94694d532798d60290d7ddf740a"
LOCKED_D44_SOURCE_SHA256 = (
    "16786dd98757851dc2829b335d12ddb8dfeab38fd9bc03fcf3ac840e9df41c4c"
)
LOCKED_D45_SOURCE_SHA256 = (
    "cf977561f6471fd99fb9c4d3eed4dc04b65277f7b8a10f3013d10bd5e4a0866d"
)
FORMAL_NUM_ROW = 495_630
FORMAL_NUM_COL = 539_546
FORMAL_NUM_NZ = 1_985_956
FORMAL_TOTAL_WORK_WEIGHT = 2_525_502
FORMAL_CHUNK_COUNT = 56
FORMAL_WORKERS = 56
FORMAL_DECIMAL_PRECISION = 80
PHASE_HARD_WALL_SECONDS = 1_800.0
STAGE_HARD_WALL_SECONDS = 1_830.0
TOTAL_HARD_WALL_SECONDS = 3_900.0
PHASE_TREE_RSS_LIMIT_GIB = 30.0
AGGREGATE_RSS_LIMIT_GIB = 40.0
HOST_MEMORY_RESERVE_GIB = 30.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0

BESS_STRICT_LOWER_BOUND_CNY = "1144950604.8368804"
TES_STRICT_LOWER_BOUND_CNY = (
    "254860566.61931588889075258309724606578637338890918249419801438224278086471875331"
)


@dataclass(frozen=True)
class FrozenPhase:
    key: str
    solution_name: str
    solution_sha256: str
    solver_execution_name: str
    solver_execution_sha256: str


PHASES = (
    FrozenPhase(
        "ipx",
        "solver_ipx_solution.bin.gz",
        "eed2b064d13f31f6718dd7292374f545607709445705bdb9f54210c5688d4a80",
        "solver_ipx_execution.json",
        "39b547a06bea1fdbd7924651e8e57b8be06322a2b6da7d205640fabfa2eed6f1",
    ),
    FrozenPhase(
        "simplex_1",
        "solver_simplex_1_solution.bin.gz",
        "6f4d0276ae62a58ee8053f0be60373068c883782b113c15455fdf2ade3a5c25c",
        "solver_simplex_1_execution.json",
        "8bf887665d6271d27963e8d90aa53822cc90eb037d8c0b56ddc539feeb0f1167",
    ),
)
PHASE_BY_KEY = {phase.key: phase for phase in PHASES}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _append_ndjson(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


def _tree_sha256(root: Path) -> str | None:
    if not root.is_dir():
        return None
    hasher = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(len(relative).to_bytes(8, "little"))
        hasher.update(relative)
        digest = bytes.fromhex(_sha256(path))
        hasher.update(digest)
    return hasher.hexdigest()


def _work_prefix(lp: object) -> tuple[list[int], int]:
    num_col = int(lp.num_col_)
    starts = lp.a_matrix_.start_
    if len(starts) != num_col + 1:
        raise ValueError("D47 CSC start length mismatch")
    prefix = [0]
    for column in range(num_col):
        nonzeros = int(starts[column + 1]) - int(starts[column])
        if nonzeros < 0:
            raise ValueError("D47 CSC starts are not monotone")
        prefix.append(prefix[-1] + 1 + nonzeros)
    return prefix, prefix[-1]


def weighted_column_chunks(
    lp: object, chunk_count: int = FORMAL_CHUNK_COUNT
) -> tuple[d44_module.ColumnChunk, ...]:
    """Return the frozen cumulative-work contiguous partition."""

    num_col = int(lp.num_col_)
    if num_col <= 0:
        raise ValueError("D47 requires at least one column")
    if chunk_count <= 0 or chunk_count > num_col:
        raise ValueError("D47 chunk_count must be in [1, num_col]")
    prefix, total_work = _work_prefix(lp)
    boundaries = [0]
    for chunk_id in range(1, chunk_count):
        target = (chunk_id * total_work + chunk_count - 1) // chunk_count
        candidate = bisect.bisect_left(prefix, target)
        lower = boundaries[-1] + 1
        upper = num_col - (chunk_count - chunk_id)
        boundaries.append(min(max(candidate, lower), upper))
    boundaries.append(num_col)
    chunks = tuple(
        d44_module.ColumnChunk(chunk_id, start, end)
        for chunk_id, (start, end) in enumerate(
            zip(boundaries[:-1], boundaries[1:], strict=True)
        )
    )
    validate_weighted_partition(lp, chunks, chunk_count=chunk_count)
    return chunks


def validate_weighted_partition(
    lp: object,
    chunks: Sequence[d44_module.ColumnChunk],
    *,
    chunk_count: int,
) -> None:
    """Reject any partition that differs from the deterministic formula."""

    if len(chunks) != chunk_count:
        raise ValueError("D47 partition has a missing or duplicate chunk")
    num_col = int(lp.num_col_)
    expected_start = 0
    for chunk_id, chunk in enumerate(chunks):
        if chunk.chunk_id != chunk_id:
            raise ValueError("D47 chunk ids are not canonical")
        if chunk.start_column != expected_start:
            raise ValueError("D47 partition has a gap or overlap")
        if chunk.end_column <= chunk.start_column:
            raise ValueError("D47 partition contains an empty chunk")
        expected_start = chunk.end_column
    if expected_start != num_col:
        raise ValueError("D47 partition does not cover all columns")
    prefix, total_work = _work_prefix(lp)
    boundaries = [0]
    for chunk_id in range(1, chunk_count):
        target = (chunk_id * total_work + chunk_count - 1) // chunk_count
        candidate = bisect.bisect_left(prefix, target)
        lower = boundaries[-1] + 1
        upper = num_col - (chunk_count - chunk_id)
        boundaries.append(min(max(candidate, lower), upper))
    boundaries.append(num_col)
    actual = [chunks[0].start_column] + [chunk.end_column for chunk in chunks]
    if actual != boundaries:
        raise ValueError("D47 partition differs from the frozen weighted formula")


def build_partition_manifest(
    lp: object,
    *,
    lp_sha256: str,
    chunks: Sequence[d44_module.ColumnChunk],
) -> dict[str, Any]:
    validate_weighted_partition(lp, chunks, chunk_count=len(chunks))
    starts = lp.a_matrix_.start_
    prefix, total_work = _work_prefix(lp)
    records = []
    for chunk in chunks:
        record = {
            **asdict(chunk),
            "column_count": chunk.end_column - chunk.start_column,
            "nonzero_count": int(starts[chunk.end_column])
            - int(starts[chunk.start_column]),
            "work_weight": prefix[chunk.end_column] - prefix[chunk.start_column],
        }
        records.append({**record, "content_sha256": _canonical_hash(record)})
    weights = [record["work_weight"] for record in records]
    payload = {
        "schema_id": PARTITION_SCHEMA_ID,
        "lp_sha256": lp_sha256,
        "partition_rule": "cumulative_sum(1+column_nnz),ceil(k*W/K),clamped_nonempty",
        "chunk_count": len(chunks),
        "total_work_weight": total_work,
        "minimum_chunk_work_weight": min(weights),
        "maximum_chunk_work_weight": max(weights),
        "work_weight_ratio": max(weights) / min(weights),
        "chunks": records,
    }
    return {**payload, "content_sha256": _canonical_hash(payload)}


def validate_partition_manifest(
    lp: object, partition: dict[str, Any], *, expected_lp_sha256: str
) -> tuple[d44_module.ColumnChunk, ...]:
    if partition.get("schema_id") != PARTITION_SCHEMA_ID:
        raise ValueError("D47 partition schema mismatch")
    payload = {
        key: value for key, value in partition.items() if key != "content_sha256"
    }
    if partition.get("content_sha256") != _canonical_hash(payload):
        raise ValueError("D47 partition content hash mismatch")
    if partition.get("lp_sha256") != expected_lp_sha256:
        raise ValueError("D47 partition LP fingerprint mismatch")
    records = partition.get("chunks")
    if not isinstance(records, list):
        raise ValueError("D47 partition chunks are missing")
    if not records or any(not isinstance(record, dict) for record in records):
        raise ValueError("D47 partition chunks are invalid")
    chunks = tuple(
        d44_module.ColumnChunk(
            int(record["chunk_id"]),
            int(record["start_column"]),
            int(record["end_column"]),
        )
        for record in records
    )
    expected = weighted_column_chunks(lp, len(chunks))
    if chunks != expected:
        raise ValueError("D47 partition ranges differ from the frozen formula")
    starts = lp.a_matrix_.start_
    prefix, total_work = _work_prefix(lp)
    for chunk, record in zip(chunks, records, strict=True):
        base = {key: value for key, value in record.items() if key != "content_sha256"}
        if record.get("content_sha256") != _canonical_hash(base):
            raise ValueError("D47 partition chunk content hash mismatch")
        expected_values = {
            "column_count": chunk.end_column - chunk.start_column,
            "nonzero_count": int(starts[chunk.end_column])
            - int(starts[chunk.start_column]),
            "work_weight": prefix[chunk.end_column] - prefix[chunk.start_column],
        }
        if any(record.get(key) != value for key, value in expected_values.items()):
            raise ValueError("D47 partition chunk statistic mismatch")
    if partition.get("total_work_weight") != total_work:
        raise ValueError("D47 partition total work mismatch")
    return chunks


def _wrap_chunk_audit(
    raw: dict[str, Any],
    *,
    phase: str,
    lp_sha256: str,
    solution_sha256: str,
    partition_sha256: str,
    partition_record: dict[str, Any],
) -> dict[str, Any]:
    raw_payload = {key: value for key, value in raw.items() if key != "content_sha256"}
    if raw.get("content_sha256") != d44_module._canonical_hash(raw_payload):
        raise ValueError("D47 received a tampered D44 chunk")
    for key in ("chunk_id", "start_column", "end_column", "nonzero_count"):
        if raw.get(key) != partition_record.get(key):
            raise ValueError("D47 chunk differs from the weighted partition")
    payload = {
        "schema_id": CHUNK_SCHEMA_ID,
        "phase": phase,
        "lp_sha256": lp_sha256,
        "solution_sha256": solution_sha256,
        "partition_sha256": partition_sha256,
        "chunk_id": raw["chunk_id"],
        "start_column": raw["start_column"],
        "end_column": raw["end_column"],
        "column_count": partition_record["column_count"],
        "nonzero_count": raw["nonzero_count"],
        "work_weight": partition_record["work_weight"],
        "lower_bound_decimal": raw["lower_bound_decimal"],
        "upper_bound_decimal": raw["upper_bound_decimal"],
        "invalid_column_endpoint_count": raw["invalid_column_endpoint_count"],
    }
    return {**payload, "content_sha256": _canonical_hash(payload)}


def assemble_weighted_certificate(
    *,
    lp: object,
    phase: str,
    lp_sha256: str,
    solution_sha256: str,
    precision: int,
    row_total_lower: Decimal,
    row_total_upper: Decimal,
    row_multiplier_count: int,
    projected_count: int,
    partition: dict[str, Any],
    chunk_audits: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    chunks = validate_partition_manifest(lp, partition, expected_lp_sha256=lp_sha256)
    if len(chunk_audits) != len(chunks):
        raise ValueError("D47 cannot assemble a partial chunk set")
    partition_sha256 = partition["content_sha256"]
    by_id: dict[int, dict[str, Any]] = {}
    for audit in chunk_audits:
        if audit.get("schema_id") != CHUNK_SCHEMA_ID:
            raise ValueError("D47 chunk schema mismatch")
        chunk_id = audit.get("chunk_id")
        if not isinstance(chunk_id, int) or chunk_id in by_id:
            raise ValueError("D47 chunk id is missing, duplicated, or invalid")
        payload = {
            key: value for key, value in audit.items() if key != "content_sha256"
        }
        if audit.get("content_sha256") != _canonical_hash(payload):
            raise ValueError("D47 chunk content hash mismatch")
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
        raise ValueError("D47 row interval is invalid")
    invalid_columns = 0
    ordered = []
    records = partition["chunks"]
    for chunk, record in zip(chunks, records, strict=True):
        audit = by_id.get(chunk.chunk_id)
        if audit is None:
            raise ValueError("D47 chunk set has a missing id")
        expected = {
            "phase": phase,
            "lp_sha256": lp_sha256,
            "solution_sha256": solution_sha256,
            "partition_sha256": partition_sha256,
            "start_column": chunk.start_column,
            "end_column": chunk.end_column,
            "column_count": record["column_count"],
            "nonzero_count": record["nonzero_count"],
            "work_weight": record["work_weight"],
        }
        if any(audit.get(key) != value for key, value in expected.items()):
            raise ValueError("D47 chunk identity or statistic mismatch")
        lower = Decimal(str(audit["lower_bound_decimal"]))
        upper = Decimal(str(audit["upper_bound_decimal"]))
        if not lower.is_finite() or not upper.is_finite() or lower > upper:
            raise ValueError("D47 chunk interval is invalid")
        invalid = audit.get("invalid_column_endpoint_count")
        if not isinstance(invalid, int) or invalid < 0:
            raise ValueError("D47 invalid endpoint count is invalid")
        invalid_columns += invalid
        total_lower = down.add(total_lower, lower)
        total_upper = up.add(total_upper, upper)
        ordered.append(audit)
    eligible = invalid_columns == 0 and total_lower.is_finite()
    lower = str(total_lower) if eligible else None
    upper = str(total_upper) if eligible else None
    lower_float = float(total_lower) if eligible else None
    if lower_float is not None and not math.isfinite(lower_float):
        raise ValueError("D47 lower bound is not representable as a finite float")
    width = up.subtract(total_upper, total_lower) if eligible else None
    return {
        "schema_id": CERTIFICATE_SCHEMA_ID,
        "phase": phase,
        "lp_sha256": lp_sha256,
        "solution_sha256": solution_sha256,
        "partition_sha256": partition_sha256,
        "precision": precision,
        "chunk_count": len(chunks),
        "row_multiplier_count": row_multiplier_count,
        "projected_row_multiplier_count": projected_count,
        "invalid_column_endpoint_count": invalid_columns,
        "lower_bound_decimal": lower,
        "upper_bound_decimal": upper,
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


ChunkExecutor = Callable[
    [object, Sequence[Decimal], Sequence[d44_module.ColumnChunk]],
    Sequence[dict[str, Any]],
]


def certify_weighted_lagrangian(
    lp: object,
    row_multipliers: Sequence[float],
    *,
    phase: str,
    solution_sha256: str,
    expected_lp_sha256: str | None = None,
    precision: int = FORMAL_DECIMAL_PRECISION,
    chunk_count: int = FORMAL_CHUNK_COUNT,
    chunk_executor: ChunkExecutor | None = None,
) -> dict[str, Any]:
    """Create a rigorous certificate with a supplied test or serial executor."""

    lp_sha256 = fingerprint_highs_lp(lp)
    if expected_lp_sha256 is not None and lp_sha256 != expected_lp_sha256:
        raise ValueError("D47 LP fingerprint differs from the locked identity")
    row = d44_module.project_row_terms(lp, row_multipliers, precision=precision)
    chunks = weighted_column_chunks(lp, chunk_count)
    partition = build_partition_manifest(lp, lp_sha256=lp_sha256, chunks=chunks)
    if chunk_executor is None:
        raw = [
            d44_module.evaluate_column_chunk(
                lp, row["projected"], chunk, precision=precision
            )
            for chunk in chunks
        ]
    else:
        raw = list(chunk_executor(lp, row["projected"], chunks))
    records = partition["chunks"]
    wrapped = []
    for audit in raw:
        chunk_id = audit.get("chunk_id")
        if not isinstance(chunk_id, int) or not 0 <= chunk_id < len(records):
            raise ValueError("D47 received an invalid chunk id")
        wrapped.append(
            _wrap_chunk_audit(
                audit,
                phase=phase,
                lp_sha256=lp_sha256,
                solution_sha256=solution_sha256,
                partition_sha256=partition["content_sha256"],
                partition_record=records[chunk_id],
            )
        )
    return assemble_weighted_certificate(
        lp=lp,
        phase=phase,
        lp_sha256=lp_sha256,
        solution_sha256=solution_sha256,
        precision=precision,
        row_total_lower=row["row_total_lower"],
        row_total_upper=row["row_total_upper"],
        row_multiplier_count=row["row_multiplier_count"],
        projected_count=row["projected_count"],
        partition=partition,
        chunk_audits=wrapped,
    )


_FORK_LP: object | None = None
_FORK_PROJECTED: Sequence[Decimal] | None = None
_FORK_PRECISION = FORMAL_DECIMAL_PRECISION


def _fork_chunk_worker(chunk: d44_module.ColumnChunk) -> dict[str, Any]:
    if _FORK_LP is None or _FORK_PROJECTED is None:
        raise RuntimeError("D47 fork worker was not initialized")
    return d44_module.evaluate_column_chunk(
        _FORK_LP,
        _FORK_PROJECTED,
        chunk,
        precision=_FORK_PRECISION,
    )


def evaluate_chunks_fork_persistent(
    lp: object,
    projected_multipliers: Sequence[Decimal],
    chunks: Sequence[d44_module.ColumnChunk],
    *,
    workers: int,
    precision: int,
    phase: str,
    lp_sha256: str,
    solution_sha256: str,
    partition: dict[str, Any],
    chunk_dir: Path,
    progress_path: Path,
    completion_path: Path,
) -> list[dict[str, Any]]:
    """Evaluate weighted chunks with Linux fork and persist each completion."""

    if "fork" not in multiprocessing.get_all_start_methods():
        raise RuntimeError("D47 formal parallelism requires Linux fork")
    if workers <= 0 or workers > len(chunks):
        raise ValueError("D47 workers must be in [1, chunk_count]")
    for path in (chunk_dir, progress_path, completion_path):
        if path.exists():
            raise FileExistsError(f"D47 refuses to overwrite {path}")
    chunk_dir.mkdir(parents=True)
    records = partition["chunks"]
    global _FORK_LP, _FORK_PRECISION, _FORK_PROJECTED
    _FORK_LP = lp
    _FORK_PROJECTED = projected_multipliers
    _FORK_PRECISION = precision
    context = multiprocessing.get_context("fork")
    pool = context.Pool(processes=workers)
    results: list[dict[str, Any]] = []
    started = perf_counter()
    try:
        for raw in pool.imap_unordered(_fork_chunk_worker, chunks, chunksize=1):
            chunk_id = int(raw["chunk_id"])
            result = _wrap_chunk_audit(
                raw,
                phase=phase,
                lp_sha256=lp_sha256,
                solution_sha256=solution_sha256,
                partition_sha256=partition["content_sha256"],
                partition_record=records[chunk_id],
            )
            chunk_path = chunk_dir / f"chunk_{chunk_id:03d}.json"
            d42_executor._atomic_write_json(chunk_path, result)
            results.append(result)
            progress = {
                "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                "phase": phase,
                "completed_chunks": len(results),
                "chunk_count": len(chunks),
                "last_completed_chunk_id": chunk_id,
                "elapsed_seconds": perf_counter() - started,
            }
            d42_executor._atomic_write_json(progress_path, progress)
            _append_ndjson(completion_path, progress)
        pool.close()
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()
        _FORK_LP = None
        _FORK_PROJECTED = None
    return results


def _phase_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    if phase not in PHASE_BY_KEY:
        raise ValueError(f"unknown D47 phase: {phase}")
    root = output_dir / phase
    return {
        "root": root,
        "result": root / "result.json",
        "certificate": root / "certificate.json",
        "partition": root / "partition.json",
        "chunks_manifest": root / "chunks_manifest.json",
        "chunks": root / "chunks",
        "progress": root / "progress.json",
        "completion": root / "completion.ndjson",
        "log": root / "phase.log",
        "heartbeat": root / "heartbeat.ndjson",
        "execution": root / "execution.json",
    }


def validate_locked_dependencies() -> dict[str, str]:
    actual = {
        "e0d44_fork_parallel_certificate.py": _sha256(Path(d44_module.__file__)),
        "e0d45_hybrid_r0_strict_lower_bound.py": _sha256(Path(d45_module.__file__)),
    }
    expected = {
        "e0d44_fork_parallel_certificate.py": LOCKED_D44_SOURCE_SHA256,
        "e0d45_hybrid_r0_strict_lower_bound.py": LOCKED_D45_SOURCE_SHA256,
    }
    if actual != expected:
        raise ValueError("D47 locked dependency source SHA-256 mismatch")
    return actual


def validate_d45_formal_inputs(d45_formal_dir: Path) -> dict[str, Any]:
    required = {
        "manifest": ("manifest.json", D45_FORMAL_MANIFEST_SHA256),
        "execution": ("execution.json", D45_FORMAL_EXECUTION_SHA256),
        "artifact_list": ("artifact_sha256.txt", D45_ARTIFACT_LIST_SHA256),
        "lp_archive": ("presolved_lp.bin.gz", LOCKED_LP_ARCHIVE_SHA256),
    }
    hashes = {}
    for key, (name, expected) in required.items():
        path = d45_formal_dir / name
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"D47 D45 {key} SHA-256 mismatch")
        hashes[key] = expected
    manifest = _load_json(d45_formal_dir / "manifest.json")
    if not all(
        (
            manifest.get("status") == "no_strict_certificate",
            manifest.get("formal_lower_bound_eligible") is False,
            manifest.get("formal_lower_bound_decimal") is None,
            manifest.get("selected_phase") is None,
            manifest.get("d46_feasible_upper_bound_contract_permitted") is False,
            manifest.get("technical_ranking_permitted") is False,
        )
    ):
        raise ValueError("D47 D45 claim boundary mismatch")
    execution = _load_json(d45_formal_dir / "execution.json")
    if execution.get("status") != "no_strict_certificate":
        raise ValueError("D47 D45 execution status mismatch")
    phase_hashes = {}
    for phase in PHASES:
        for label, name, expected in (
            ("solution", phase.solution_name, phase.solution_sha256),
            (
                "solver_execution",
                phase.solver_execution_name,
                phase.solver_execution_sha256,
            ),
        ):
            path = d45_formal_dir / name
            if not path.is_file() or _sha256(path) != expected:
                raise ValueError(f"D47 {phase.key} {label} SHA-256 mismatch")
            phase_hashes[f"{phase.key}_{label}"] = expected
    return {
        "manifest": manifest,
        "input_sha256": {**hashes, **phase_hashes},
    }


def validate_gate_a_manifest(
    *, gate_a_manifest_path: Path, d47_test_path: Path
) -> dict[str, Any]:
    if not gate_a_manifest_path.is_file() or not d47_test_path.is_file():
        raise FileNotFoundError("D47 Gate A manifest or test source is missing")
    payload = _load_json(gate_a_manifest_path)
    if payload.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D47 Gate A schema mismatch")
    if payload.get("status") != "gate_a_passed" or payload.get("platform") != "linux":
        raise ValueError("D47 Gate A did not pass on Linux")
    required = (
        "fork_available",
        "four_worker_persistence_smoke_passed",
        "weighted_partition_passed",
        "fraction_direction_passed",
        "tamper_rejection_passed",
        "phase_fallback_passed",
        "identity_gate_passed",
        "process_tree_cleanup_passed",
        "directed_regression_passed",
        "full_regression_passed",
    )
    if any(payload.get(key) is not True for key in required):
        raise ValueError("D47 Gate A required claim is missing")
    source_sha256 = _sha256(Path(__file__))
    test_sha256 = _sha256(d47_test_path)
    if payload.get("source_sha256") != source_sha256:
        raise ValueError("D47 Gate A source SHA-256 mismatch")
    if payload.get("test_sha256") != test_sha256:
        raise ValueError("D47 Gate A test SHA-256 mismatch")
    if payload.get("test_failed_count") != 0 or payload.get("test_skipped_count") != 0:
        raise ValueError("D47 Gate A contains failed or skipped tests")
    passed = payload.get("test_passed_count")
    if not isinstance(passed, int) or passed < 14:
        raise ValueError("D47 Gate A test count is incomplete")
    if payload.get("optimization_invoked") is not False:
        raise ValueError("D47 Gate A must not invoke optimization")
    if payload.get("partition_chunk_count") != FORMAL_CHUNK_COUNT:
        raise ValueError("D47 Gate A partition count mismatch")
    commit = payload.get("git_commit")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("D47 Gate A Git commit identity is invalid")
    return {
        "manifest_sha256": _sha256(gate_a_manifest_path),
        "source_sha256": source_sha256,
        "test_sha256": test_sha256,
        "git_commit": commit,
        "test_passed_count": passed,
    }


def run_phase_child(*, d45_formal_dir: Path, phase: str, output_dir: Path) -> None:
    inputs = validate_d45_formal_inputs(d45_formal_dir)
    validate_locked_dependencies()
    spec = PHASE_BY_KEY[phase]
    paths = _phase_paths(output_dir, phase)
    for key in ("result", "certificate", "partition", "chunks_manifest", "chunks"):
        if paths[key].exists():
            raise FileExistsError(f"D47 phase output already exists: {paths[key]}")
    lp, lp_meta = d42_executor.read_lp_archive(
        d45_formal_dir / "presolved_lp.bin.gz",
        expected_lp_sha256=LOCKED_LP_SHA256,
    )
    if lp_meta.get("archive_sha256") != LOCKED_LP_ARCHIVE_SHA256:
        raise ValueError("D47 formal LP archive SHA-256 changed after input gate")
    audit = lp_meta["audit"]
    if (
        audit.get("num_row"),
        audit.get("num_col"),
        audit.get("num_nz"),
    ) != (FORMAL_NUM_ROW, FORMAL_NUM_COL, FORMAL_NUM_NZ):
        raise ValueError("D47 formal LP dimensions changed")
    row_dual, snapshot_audit = d43_module.load_locked_snapshot(
        solution_path=d45_formal_dir / spec.solution_name,
        phase_execution_path=d45_formal_dir / spec.solver_execution_name,
        phase=phase,
        expected_solution_sha256=spec.solution_sha256,
        expected_phase_execution_sha256=spec.solver_execution_sha256,
        expected_lp_sha256=LOCKED_LP_SHA256,
        expected_num_col=FORMAL_NUM_COL,
        expected_num_row=FORMAL_NUM_ROW,
    )
    row = d44_module.project_row_terms(lp, row_dual, precision=FORMAL_DECIMAL_PRECISION)
    chunks = weighted_column_chunks(lp)
    partition = build_partition_manifest(lp, lp_sha256=LOCKED_LP_SHA256, chunks=chunks)
    if partition["total_work_weight"] != FORMAL_TOTAL_WORK_WEIGHT:
        raise ValueError("D47 formal total work weight changed")
    d42_executor._atomic_write_json(paths["partition"], partition)
    audits = evaluate_chunks_fork_persistent(
        lp,
        row["projected"],
        chunks,
        workers=FORMAL_WORKERS,
        precision=FORMAL_DECIMAL_PRECISION,
        phase=phase,
        lp_sha256=LOCKED_LP_SHA256,
        solution_sha256=spec.solution_sha256,
        partition=partition,
        chunk_dir=paths["chunks"],
        progress_path=paths["progress"],
        completion_path=paths["completion"],
    )
    certificate = assemble_weighted_certificate(
        lp=lp,
        phase=phase,
        lp_sha256=LOCKED_LP_SHA256,
        solution_sha256=spec.solution_sha256,
        precision=FORMAL_DECIMAL_PRECISION,
        row_total_lower=row["row_total_lower"],
        row_total_upper=row["row_total_upper"],
        row_multiplier_count=row["row_multiplier_count"],
        projected_count=row["projected_count"],
        partition=partition,
        chunk_audits=audits,
    )
    d42_executor._atomic_write_json(paths["certificate"], certificate)
    chunk_files = sorted(paths["chunks"].glob("chunk_*.json"))
    chunks_manifest = {
        "schema_id": f"{SCHEMA_ID}.chunks_manifest",
        "phase": phase,
        "chunk_count": len(chunk_files),
        "partition_sha256": partition["content_sha256"],
        "files": [{"name": path.name, "sha256": _sha256(path)} for path in chunk_files],
        "tree_sha256": _tree_sha256(paths["chunks"]),
    }
    d42_executor._atomic_write_json(paths["chunks_manifest"], chunks_manifest)
    result = {
        "schema_id": PHASE_RESULT_SCHEMA_ID,
        "status": certificate["status"],
        "phase": phase,
        "lp_sha256": LOCKED_LP_SHA256,
        "solution_sha256": spec.solution_sha256,
        "snapshot_audit": snapshot_audit,
        "partition_sha256": partition["content_sha256"],
        "partition_file_sha256": _sha256(paths["partition"]),
        "certificate_sha256": _sha256(paths["certificate"]),
        "chunks_manifest_sha256": _sha256(paths["chunks_manifest"]),
        "chunks_tree_sha256": chunks_manifest["tree_sha256"],
        "formal_lower_bound_eligible": certificate["formal_lower_bound_eligible"],
        "lower_bound_decimal": certificate["lower_bound_decimal"],
        "upper_bound_decimal": certificate["upper_bound_decimal"],
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
        "d45_manifest_sha256": inputs["input_sha256"]["manifest"],
    }
    d42_executor._atomic_write_json(paths["result"], result)


def _phase_command(d45_formal_dir: Path, output_dir: Path, phase: str) -> list[str]:
    return [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d47_hybrid_weighted_persistent_certificate",
        "_phase-child",
        "--d45-formal-dir",
        str(d45_formal_dir),
        "--phase",
        phase,
        "--output-dir",
        str(output_dir),
    ]


def _phase_artifact_hashes(paths: dict[str, Path]) -> dict[str, str | None]:
    hashes = {
        key: _sha256(path) if path.is_file() else None
        for key, path in paths.items()
        if key not in ("root", "chunks", "execution")
    }
    hashes["chunks_tree"] = _tree_sha256(paths["chunks"])
    return hashes


def validate_phase_execution(
    execution: dict[str, Any], paths: dict[str, Path]
) -> dict[str, str | None]:
    actual = _phase_artifact_hashes(paths)
    if execution.get("artifact_sha256") != actual:
        raise ValueError("D47 phase execution artifact hash map mismatch")
    return actual


def _process_group_members(process_group_id: int) -> dict[int, str]:
    """Return Linux process-group members and their kernel state codes."""

    if os.name == "nt":
        return {}
    members: dict[int, str] = {}
    proc = Path("/proc")
    if not proc.is_dir():
        return members
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="ascii")
            right = stat.rfind(")")
            fields = stat[right + 2 :].split()
            state = fields[0]
            process_group = int(fields[2])
            if process_group == process_group_id:
                members[int(entry.name)] = state
        except (FileNotFoundError, IndexError, OSError, ValueError):
            continue
    return members


def _cleanup_process_group(process_group_id: int) -> dict[str, Any]:
    """Terminate active group members and distinguish inert zombie entries."""

    before = _process_group_members(process_group_id)
    active_before = sorted(pid for pid, state in before.items() if state != "Z")
    signal_sequence: list[str] = []
    if active_before:
        try:
            os.killpg(process_group_id, signal.SIGTERM)
            signal_sequence.append("SIGTERM")
        except ProcessLookupError:
            pass
    deadline = perf_counter() + d45_module.TERMINATION_GRACE_SECONDS
    active_after = active_before
    while active_after and perf_counter() < deadline:
        time.sleep(0.1)
        current = _process_group_members(process_group_id)
        active_after = sorted(pid for pid, state in current.items() if state != "Z")
    if active_after:
        try:
            os.killpg(process_group_id, signal.SIGKILL)
            signal_sequence.append("SIGKILL")
        except ProcessLookupError:
            pass
        deadline = perf_counter() + d45_module.TERMINATION_GRACE_SECONDS
        while active_after and perf_counter() < deadline:
            time.sleep(0.1)
            current = _process_group_members(process_group_id)
            active_after = sorted(pid for pid, state in current.items() if state != "Z")
    after = _process_group_members(process_group_id)
    active_after = sorted(pid for pid, state in after.items() if state != "Z")
    zombies_after = sorted(pid for pid, state in after.items() if state == "Z")
    return {
        "process_group_id": process_group_id,
        "members_before_cleanup": {str(pid): state for pid, state in before.items()},
        "active_members_before_cleanup": active_before,
        "signal_sequence": signal_sequence,
        "members_after_cleanup": {str(pid): state for pid, state in after.items()},
        "active_members_after_cleanup": active_after,
        "zombie_members_after_cleanup": zombies_after,
        "active_residual_detected": bool(active_after),
    }


def run_monitored_phase(
    *,
    d45_formal_dir: Path,
    output_dir: Path,
    phase: str,
    total_run_started: float,
) -> dict[str, Any]:
    paths = _phase_paths(output_dir, phase)
    if paths["root"].exists():
        raise FileExistsError(f"D47 refuses to overwrite phase directory: {phase}")
    paths["root"].mkdir(parents=True)
    available_before = d42_executor._available_memory_gib()
    if available_before is None:
        raise RuntimeError("D47 formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D47 host memory is below the frozen reserve")
    started = perf_counter()
    peak_tree = 0.0
    peak_aggregate = 0.0
    minimum_available = available_before
    rss_samples = 0
    memory_samples = 0
    stop_reason = None
    termination_signal = None
    d42_executor._atomic_write_json(
        paths["execution"],
        {
            "schema_id": PHASE_EXECUTION_SCHEMA_ID,
            "status": "child_starting",
            "phase": phase,
            "lp_sha256": LOCKED_LP_SHA256,
            "hard_wall_enforced_by_parent": True,
        },
    )
    with (
        paths["log"].open("w", encoding="utf-8", newline="\n") as log,
        paths["heartbeat"].open(
            "w", encoding="utf-8", newline="\n", buffering=1
        ) as heartbeat,
    ):
        child = subprocess.Popen(
            _phase_command(d45_formal_dir, output_dir, phase),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        last_heartbeat = -HEARTBEAT_INTERVAL_SECONDS
        while child.poll() is None:
            now = perf_counter()
            elapsed = now - started
            tree_rss = d42_executor._process_tree_rss_gib(child.pid)
            parent_rss = d42_executor._process_rss_gib(os.getpid())
            aggregate = (
                parent_rss + (tree_rss or 0.0) if parent_rss is not None else None
            )
            available = d42_executor._available_memory_gib()
            if tree_rss is not None:
                peak_tree = max(peak_tree, tree_rss)
                rss_samples += 1
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            if elapsed - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                progress = None
                if paths["progress"].is_file():
                    try:
                        progress = _load_json(paths["progress"])
                    except (json.JSONDecodeError, OSError):
                        progress = {"state": "progress_read_incomplete"}
                heartbeat.write(
                    json.dumps(
                        {
                            "phase": phase,
                            "pid": child.pid,
                            "phase_elapsed_seconds": elapsed,
                            "total_elapsed_seconds": now - total_run_started,
                            "phase_tree_rss_gib": tree_rss,
                            "aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                            "progress": progress,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                heartbeat.flush()
                last_heartbeat = elapsed
            if now - total_run_started >= TOTAL_HARD_WALL_SECONDS:
                stop_reason = "total_parent_hard_wall_reached"
            elif elapsed >= PHASE_HARD_WALL_SECONDS:
                stop_reason = f"phase_hard_wall_reached:{phase}"
            elif elapsed >= STAGE_HARD_WALL_SECONDS:
                stop_reason = "stage_hard_wall_reached"
            elif tree_rss is not None and tree_rss >= PHASE_TREE_RSS_LIMIT_GIB:
                stop_reason = f"phase_rss_limit_reached:{phase}"
            elif aggregate is not None and aggregate >= AGGREGATE_RSS_LIMIT_GIB:
                stop_reason = "aggregate_rss_limit_reached"
            elif available is not None and available < HOST_MEMORY_RESERVE_GIB:
                stop_reason = "host_memory_reserve_breached"
            if stop_reason is not None and termination_signal is None:
                termination_signal = d42_executor._terminate_process_group(child)
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = child.wait()
        cleanup_audit = _cleanup_process_group(child.pid)
        residual = cleanup_audit["active_residual_detected"]
    result = _load_json(paths["result"]) if paths["result"].is_file() else None
    resource_gate_passed = all(
        (
            stop_reason is None,
            residual is False,
            rss_samples > 0,
            memory_samples > 0,
            peak_tree < PHASE_TREE_RSS_LIMIT_GIB,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
        )
    )
    complete = return_code == 0 and result is not None and resource_gate_passed
    execution = {
        "schema_id": PHASE_EXECUTION_SCHEMA_ID,
        "status": "complete" if complete else "interrupted_or_failed",
        "phase": phase,
        "lp_sha256": LOCKED_LP_SHA256,
        "return_code": return_code,
        "phase_runtime_seconds": perf_counter() - started,
        "hard_wall_enforced_by_parent": True,
        "stop_reason": stop_reason,
        "termination_signal": termination_signal,
        "residual_process_group_detected": residual,
        "process_group_cleanup_audit": cleanup_audit,
        "resource_gate_passed": resource_gate_passed,
        "peak_phase_process_tree_rss_gib": peak_tree,
        "peak_aggregate_rss_gib": peak_aggregate,
        "minimum_available_memory_gib": minimum_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "artifact_sha256": _phase_artifact_hashes(paths),
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    d42_executor._atomic_write_json(paths["execution"], execution)
    return execution


def assemble_manifest(
    *,
    input_audit: dict[str, Any],
    dependency_hashes: dict[str, str],
    gate_a_audit: dict[str, Any],
    phase_audits: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = None
    lower = None
    upper = None
    for phase in PHASES:
        audit = phase_audits.get(phase.key, {})
        if audit.get("formal_lower_bound_eligible") is True:
            selected = phase.key
            lower = audit.get("lower_bound_decimal")
            upper = audit.get("upper_bound_decimal")
            break
    recovered = selected is not None
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "status": (
            "hybrid_r0_lower_bound_recovered" if recovered else "no_strict_certificate"
        ),
        "architecture": "hybrid",
        "relaxation_mode": "r0_all_continuous",
        "selected_phase": selected,
        "formal_lower_bound_eligible": recovered,
        "formal_lower_bound_decimal": lower,
        "formal_upper_interval_decimal": upper,
        "hybrid_r0_certificate_covers_r1_and_original_milp": recovered,
        "d46_feasible_upper_bound_contract_permitted": recovered,
        "formal_project_tac_ready": False,
        "technical_ranking_permitted": False,
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "chunk_count": FORMAL_CHUNK_COUNT,
        "workers": FORMAL_WORKERS,
        "phase_order": [phase.key for phase in PHASES],
        "phase_audits": phase_audits,
        "input_sha256": input_audit["input_sha256"],
        "dependency_source_sha256": dependency_hashes,
        "gate_a_audit": gate_a_audit,
        "bess_strict_lower_bound_cny": BESS_STRICT_LOWER_BOUND_CNY,
        "tes_strict_lower_bound_cny": TES_STRICT_LOWER_BOUND_CNY,
        "claim_scope": "controlled_public_cost_sensitivity_not_formal_project_tac",
    }


def render_readme(manifest: dict[str, Any], *, manifest_sha256: str) -> str:
    recovered = manifest["formal_lower_bound_eligible"] is True
    if recovered:
        explanation = (
            "The value is an outward-rounded lower bound for the locked Hybrid R0 "
            "continuous relaxation. It is not a feasible plan, capacity, project "
            "TAC, optimality gap, synergy value, or technology ranking."
        )
    else:
        explanation = (
            "No complete eligible strict certificate was produced. Partial chunks "
            "are diagnostic only and do not form a lower bound, feasible plan, "
            "capacity, project TAC, gap, synergy value, or technology ranking."
        )
    return (
        "# E0-D-47 Hybrid weighted persistent certificate\n\n"
        f"- Status: `{manifest['status']}`\n"
        f"- Selected phase: `{manifest.get('selected_phase') or 'none'}`\n"
        f"- Strict lower bound: `{manifest.get('formal_lower_bound_decimal')}` CNY\n"
        f"- Manifest SHA-256: `{manifest_sha256}`\n\n"
        f"{explanation}\n"
    )


def run_formal(
    *,
    d45_formal_dir: Path,
    gate_a_manifest_path: Path,
    d47_test_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"D47 formal output already exists: {output_dir}")
    input_audit = validate_d45_formal_inputs(d45_formal_dir)
    dependency_hashes = validate_locked_dependencies()
    gate_a_audit = validate_gate_a_manifest(
        gate_a_manifest_path=gate_a_manifest_path,
        d47_test_path=d47_test_path,
    )
    output_dir.mkdir(parents=True)
    run_started = perf_counter()
    phase_audits: dict[str, dict[str, Any]] = {}
    execution_hashes: dict[str, str] = {}
    for phase in PHASES:
        execution = run_monitored_phase(
            d45_formal_dir=d45_formal_dir,
            output_dir=output_dir,
            phase=phase.key,
            total_run_started=run_started,
        )
        paths = _phase_paths(output_dir, phase.key)
        execution_hashes[phase.key] = _sha256(paths["execution"])
        result = None
        if execution.get("status") == "complete" and paths["result"].is_file():
            validate_phase_execution(execution, paths)
            result = _load_json(paths["result"])
        phase_audits[phase.key] = {
            "status": (result.get("status") if result is not None else "phase_failed"),
            "formal_lower_bound_eligible": (
                result.get("formal_lower_bound_eligible") is True
                if result is not None
                else False
            ),
            "lower_bound_decimal": (
                result.get("lower_bound_decimal") if result is not None else None
            ),
            "upper_bound_decimal": (
                result.get("upper_bound_decimal") if result is not None else None
            ),
            "result_sha256": _sha256(paths["result"])
            if paths["result"].is_file()
            else None,
            "certificate_sha256": _sha256(paths["certificate"])
            if paths["certificate"].is_file()
            else None,
            "partition_sha256": _sha256(paths["partition"])
            if paths["partition"].is_file()
            else None,
            "chunks_tree_sha256": _tree_sha256(paths["chunks"]),
            "execution_sha256": execution_hashes[phase.key],
        }
        if result is not None and result.get("formal_lower_bound_eligible") is True:
            break
    manifest = assemble_manifest(
        input_audit=input_audit,
        dependency_hashes=dependency_hashes,
        gate_a_audit=gate_a_audit,
        phase_audits=phase_audits,
    )
    manifest_path = output_dir / "manifest.json"
    d42_executor._atomic_write_json(manifest_path, manifest)
    manifest_sha256 = _sha256(manifest_path)
    execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": manifest["status"],
        "runtime_seconds": perf_counter() - run_started,
        "total_hard_wall_seconds": TOTAL_HARD_WALL_SECONDS,
        "phase_execution_sha256": execution_hashes,
        "manifest_sha256": manifest_sha256,
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    d42_executor._atomic_write_json(output_dir / "execution.json", execution)
    _atomic_write_text(
        output_dir / "README.md",
        render_readme(manifest, manifest_sha256=manifest_sha256),
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    child = commands.add_parser("_phase-child")
    child.add_argument("--d45-formal-dir", type=Path, required=True)
    child.add_argument("--phase", choices=tuple(PHASE_BY_KEY), required=True)
    child.add_argument("--output-dir", type=Path, required=True)
    formal = commands.add_parser("formal")
    formal.add_argument("--d45-formal-dir", type=Path, required=True)
    formal.add_argument("--gate-a-manifest-path", type=Path, required=True)
    formal.add_argument("--d47-test-path", type=Path, required=True)
    formal.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "_phase-child":
        run_phase_child(
            d45_formal_dir=args.d45_formal_dir,
            phase=args.phase,
            output_dir=args.output_dir,
        )
    else:
        run_formal(
            d45_formal_dir=args.d45_formal_dir,
            gate_a_manifest_path=args.gate_a_manifest_path,
            d47_test_path=args.d47_test_path,
            output_dir=args.output_dir,
        )


if __name__ == "__main__":
    main()
