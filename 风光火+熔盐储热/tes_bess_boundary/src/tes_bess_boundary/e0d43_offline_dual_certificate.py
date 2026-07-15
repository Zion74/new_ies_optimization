"""E0-D-43 read-only recovery of certificates from frozen D42 snapshots.

The formal path never builds or solves an optimization model.  It validates
the hash-locked D42 presolved LP and solution archives, then sends the saved
row-dual vectors to the unchanged D42 outward-rounded certificate routine.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

import tes_bess_boundary.e0d42_gate_b_executor as d42_executor_module
import tes_bess_boundary.e0d42_native_highs_certificate as d42_certificate_module
from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256
from tes_bess_boundary.e0d42_gate_b_executor import (
    SOLUTION_ARCHIVE_MAGIC,
    SOLUTION_ARCHIVE_SCHEMA_ID,
    _atomic_write_json,
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _read_binary_archive,
    _terminate_process_group,
    read_lp_archive,
)
from tes_bess_boundary.e0d42_native_highs_certificate import (
    certify_lagrangian_lower_bound,
)


SCHEMA_ID = "tes_bess_boundary.e0d43_offline_dual_certificate.v1"
PHASE_RESULT_SCHEMA_ID = f"{SCHEMA_ID}.phase"
PHASE_EXECUTION_SCHEMA_ID = f"{PHASE_RESULT_SCHEMA_ID}.execution"
MANIFEST_SCHEMA_ID = f"{SCHEMA_ID}.manifest"
EXECUTION_SCHEMA_ID = f"{MANIFEST_SCHEMA_ID}.execution"

LOCKED_LP_SHA256 = "c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5"
LOCKED_LP_ARCHIVE_SHA256 = (
    "dd362f179fd00052ecbca4c25d5d8d285811fbdd5700fa2d4adb49a2f7626776"
)
LOCKED_CASE_MANIFEST_SHA256 = (
    "cacd6cc2e32e2b8849398db4b75afa835a4796310e404e3301099c3942261944"
)
LOCKED_CASE_EXECUTION_SHA256 = (
    "49e2e21445c67a233ed2bc205a8266351ae800b566d0f89cbfa7883a059efc51"
)
LOCKED_LP_MANIFEST_SHA256 = (
    "23b10bd00abde649924f8f80901292188c60bf3a54d5dd2547ed60a44209fd84"
)
LOCKED_LP_EXECUTION_SHA256 = (
    "621bc909b9fe6d7af759c96e4e83ea92c4a4f67ffd6a4255825ea8ace08c2fe7"
)
LOCKED_STRUCTURE_MANIFEST_SHA256 = (
    "2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1"
)
LOCKED_BESS_REUSE_RESULT_SHA256 = (
    "ae30997a4dcf4fb3ed599ff17b9f5bb1238d66ad4eda677312e91a69bd4f5d36"
)
LOCKED_D42_CERTIFICATE_SOURCE_SHA256 = (
    "3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298"
)
LOCKED_D42_EXECUTOR_SOURCE_SHA256 = (
    "c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51"
)

FORMAL_DECIMAL_PRECISION = 80
FORMAL_NUM_COL = 509_289
FORMAL_NUM_ROW = 439_018
CHILD_HARD_WALL_SECONDS = 1_800.0
TOTAL_PARENT_HARD_WALL_SECONDS = 2_100.0
CHILD_RSS_LIMIT_GIB = 8.0
AGGREGATE_RSS_LIMIT_GIB = 20.0
HOST_MEMORY_RESERVE_GIB = 20.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class SnapshotSpec:
    key: str
    solution_file: str
    solution_sha256: str
    phase_execution_file: str
    phase_execution_sha256: str


SNAPSHOT_SPECS = (
    SnapshotSpec(
        key="ipx",
        solution_file="phase_ipx_solution.bin.gz",
        solution_sha256=(
            "d56109dabfc599ff996771924bc78f11b85c90f1dec001fd90edc9766fa5bfc6"
        ),
        phase_execution_file="phase_ipx_execution.json",
        phase_execution_sha256=(
            "43bd8bb93120b917cf4a62433b2ab99ea349df7dfe5664c54ca9822febd4a206"
        ),
    ),
    SnapshotSpec(
        key="simplex_1",
        solution_file="phase_simplex_1_solution.bin.gz",
        solution_sha256=(
            "bec595dfbc6b878659f588ed100d08c7368e55e4d89f91bafa22e49a9163b58b"
        ),
        phase_execution_file="phase_simplex_1_execution.json",
        phase_execution_sha256=(
            "c872fbd63a72fc0f6b733220b86a57a9e2f75fbfe4e46204ef8586899317a7c1"
        ),
    ),
)
SNAPSHOT_BY_KEY = {spec.key: spec for spec in SNAPSHOT_SPECS}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return payload


def _require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if _sha256(path) != expected:
        raise ValueError(f"D43 {label} SHA-256 mismatch")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _phase_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    return {
        "certificate": output_dir / f"{phase}_certificate.json",
        "result": output_dir / f"{phase}_result.json",
        "execution": output_dir / f"{phase}_execution.json",
        "heartbeat": output_dir / f"{phase}_heartbeat.ndjson",
        "log": output_dir / f"{phase}_child.log",
    }


def load_locked_snapshot(
    *,
    solution_path: Path,
    phase_execution_path: Path,
    phase: str,
    expected_solution_sha256: str,
    expected_phase_execution_sha256: str,
    expected_lp_sha256: str,
    expected_num_col: int,
    expected_num_row: int,
) -> tuple[Sequence[float], dict[str, Any]]:
    """Validate one solution archive and return its unmodified row dual."""

    _require_hash(solution_path, expected_solution_sha256, "solution archive")
    _require_hash(
        phase_execution_path,
        expected_phase_execution_sha256,
        "phase execution",
    )
    execution = _read_json(phase_execution_path)
    artifact_sha = execution.get("artifact_sha256")
    if not isinstance(artifact_sha, dict):
        raise ValueError("D43 phase execution has no artifact hash map")
    if artifact_sha.get("solution") != expected_solution_sha256:
        raise ValueError("D43 phase execution does not bind the solution archive")
    if execution.get("lp_sha256") != expected_lp_sha256:
        raise ValueError("D43 phase execution LP fingerprint mismatch")

    header, arrays = _read_binary_archive(
        solution_path,
        expected_magic=SOLUTION_ARCHIVE_MAGIC,
    )
    if header.get("schema_id") != SOLUTION_ARCHIVE_SCHEMA_ID:
        raise ValueError("D43 solution archive schema mismatch")
    if header.get("phase") != phase:
        raise ValueError("D43 solution archive phase mismatch")
    if header.get("lp_sha256") != expected_lp_sha256:
        raise ValueError("D43 solution archive LP fingerprint mismatch")
    if header.get("dual_valid") is not True:
        raise ValueError("D43 requires dual_valid=true")
    expected_arrays = {"col_value", "col_dual", "row_value", "row_dual"}
    if set(arrays) != expected_arrays:
        raise ValueError("D43 solution archive array set mismatch")
    expected_lengths = {
        "col_value": expected_num_col,
        "col_dual": expected_num_col,
        "row_value": expected_num_row,
        "row_dual": expected_num_row,
    }
    actual_lengths = {name: len(values) for name, values in arrays.items()}
    if actual_lengths != expected_lengths:
        raise ValueError("D43 solution archive array length mismatch")
    row_dual = arrays["row_dual"]
    if not all(math.isfinite(float(value)) for value in row_dual):
        raise ValueError("D43 row dual contains a non-finite value")
    audit = {
        "schema_id": f"{SCHEMA_ID}.snapshot_audit",
        "phase": phase,
        "solution_sha256": expected_solution_sha256,
        "phase_execution_sha256": expected_phase_execution_sha256,
        "lp_sha256": expected_lp_sha256,
        "array_lengths": actual_lengths,
        "value_valid": header.get("value_valid") is True,
        "dual_valid": True,
        "finite_row_dual_count": expected_num_row,
        "passed": True,
    }
    return row_dual, audit


def certify_snapshot_child(
    *,
    lp_archive_path: Path,
    solution_path: Path,
    phase_execution_path: Path,
    output_dir: Path,
    spec: SnapshotSpec,
    expected_lp_archive_sha256: str = LOCKED_LP_ARCHIVE_SHA256,
    expected_lp_sha256: str = LOCKED_LP_SHA256,
    expected_num_col: int = FORMAL_NUM_COL,
    expected_num_row: int = FORMAL_NUM_ROW,
) -> dict[str, Any]:
    """Create one formal certificate without invoking a native optimizer."""

    paths = _phase_paths(output_dir, spec.key)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("certificate", "result"):
        if paths[key].exists():
            raise FileExistsError(f"D43 refuses to overwrite {paths[key]}")
    _require_hash(lp_archive_path, expected_lp_archive_sha256, "LP archive")
    lp, lp_audit = read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    if lp_audit["archive_sha256"] != expected_lp_archive_sha256:
        raise ValueError("D43 LP archive audit hash mismatch")
    if lp_audit["audit"]["num_col"] != expected_num_col:
        raise ValueError("D43 LP column count mismatch")
    if lp_audit["audit"]["num_row"] != expected_num_row:
        raise ValueError("D43 LP row count mismatch")
    row_dual, snapshot_audit = load_locked_snapshot(
        solution_path=solution_path,
        phase_execution_path=phase_execution_path,
        phase=spec.key,
        expected_solution_sha256=spec.solution_sha256,
        expected_phase_execution_sha256=spec.phase_execution_sha256,
        expected_lp_sha256=expected_lp_sha256,
        expected_num_col=expected_num_col,
        expected_num_row=expected_num_row,
    )
    certificate = certify_lagrangian_lower_bound(
        lp,
        row_dual,
        expected_lp_sha256=expected_lp_sha256,
        precision=FORMAL_DECIMAL_PRECISION,
    ).to_audit()
    _atomic_write_json(paths["certificate"], certificate)
    eligible = certificate.get("formal_lower_bound_eligible") is True
    result = {
        "schema_id": PHASE_RESULT_SCHEMA_ID,
        "status": (
            "certified_finite_lower_bound"
            if eligible
            else str(certificate.get("status", "no_strict_certificate"))
        ),
        "phase": spec.key,
        "lp_sha256": expected_lp_sha256,
        "lp_archive_sha256": expected_lp_archive_sha256,
        "snapshot_audit": snapshot_audit,
        "certificate": certificate,
        "certificate_sha256": _sha256(paths["certificate"]),
        "formal_lower_bound_eligible": eligible,
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(paths["result"], result)
    return result


def _eligible_decimal(result: dict[str, Any]) -> Decimal | None:
    if result.get("formal_lower_bound_eligible") is not True:
        return None
    certificate = result.get("certificate")
    if not isinstance(certificate, dict):
        raise ValueError("D43 eligible result lacks a certificate")
    try:
        lower = Decimal(str(certificate["lower_bound_decimal"]))
        width = Decimal(str(certificate["interval_width_decimal"]))
    except (InvalidOperation, KeyError) as exc:
        raise ValueError("D43 certificate has invalid Decimal fields") from exc
    if not lower.is_finite() or not width.is_finite() or width < 0:
        raise ValueError("D43 certificate Decimal fields are not admissible")
    if certificate.get("invalid_column_endpoint_count") != 0:
        raise ValueError("D43 eligible certificate has invalid column endpoints")
    return lower


def assemble_manifest(
    *,
    phase_results: dict[str, dict[str, Any]],
    phase_artifact_sha256: dict[str, dict[str, str | None]],
    input_sha256: dict[str, str],
    source_sha256: dict[str, str],
) -> dict[str, Any]:
    """Select the strongest eligible Decimal bound in frozen phase order."""

    if tuple(phase_results) != tuple(spec.key for spec in SNAPSHOT_SPECS):
        raise ValueError("D43 phase order or set differs from the frozen contract")
    eligible: list[tuple[Decimal, int, str, dict[str, Any]]] = []
    phase_audit: dict[str, Any] = {}
    for index, spec in enumerate(SNAPSHOT_SPECS):
        result = phase_results[spec.key]
        if result.get("phase") != spec.key:
            raise ValueError("D43 result phase mismatch")
        if result.get("technical_ranking_permitted") is not False:
            raise ValueError("D43 result improperly permits technical ranking")
        lower = _eligible_decimal(result)
        phase_audit[spec.key] = {
            "status": result.get("status"),
            "formal_lower_bound_eligible": lower is not None,
            "lower_bound_decimal": None if lower is None else str(lower),
            **phase_artifact_sha256[spec.key],
        }
        if lower is not None:
            eligible.append((lower, -index, spec.key, result))
    selected = max(eligible, default=None, key=lambda item: (item[0], item[1]))
    recovered = selected is not None
    selected_phase = None if selected is None else selected[2]
    selected_certificate = None if selected is None else selected[3]["certificate"]
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "status": (
            "tes_lower_bound_recovered" if recovered else "no_strict_certificate"
        ),
        "architecture": "tes",
        "relaxation_mode": "r0_all_continuous",
        "claim_scope": "controlled_public_cost_sensitivity_not_formal_project_tac",
        "input_sha256": input_sha256,
        "source_sha256": source_sha256,
        "phase_audits": phase_audit,
        "selected_phase": selected_phase,
        "formal_lower_bound_decimal": (
            None
            if selected_certificate is None
            else selected_certificate["lower_bound_decimal"]
        ),
        "formal_lower_bound_float": (
            None
            if selected_certificate is None
            else selected_certificate["lower_bound_float"]
        ),
        "formal_lower_bound_eligible": recovered,
        "tes_r0_certificate_covers_r1": recovered,
        "hybrid_lower_bound_contract_permitted": recovered,
        "formal_project_tac_ready": False,
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }


def monitor_stop_reason(
    *,
    child_elapsed_seconds: dict[str, float],
    total_elapsed_seconds: float,
    child_rss_gib: dict[str, float | None],
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    if total_elapsed_seconds >= TOTAL_PARENT_HARD_WALL_SECONDS:
        return "total_parent_hard_wall_reached"
    for spec in SNAPSHOT_SPECS:
        if child_elapsed_seconds.get(spec.key, 0.0) >= CHILD_HARD_WALL_SECONDS:
            return f"child_hard_wall_reached:{spec.key}"
    for spec in SNAPSHOT_SPECS:
        rss = child_rss_gib.get(spec.key)
        if rss is not None and rss >= CHILD_RSS_LIMIT_GIB:
            return f"child_rss_limit_reached:{spec.key}"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB:
        return "aggregate_rss_limit_reached"
    if (
        available_memory_gib is not None
        and available_memory_gib < HOST_MEMORY_RESERVE_GIB
    ):
        return "host_memory_reserve_breached"
    return None


def validate_d42_metadata_chain(
    *,
    case_manifest: dict[str, Any],
    case_execution: dict[str, Any],
    lp_execution: dict[str, Any],
    phase_executions: dict[str, dict[str, Any]],
) -> None:
    """Verify that the locked D42 metadata binds every formal D43 input."""

    expected_case_links = {
        "bess_reuse_result_sha256": LOCKED_BESS_REUSE_RESULT_SHA256,
        "structure_manifest_sha256": LOCKED_STRUCTURE_MANIFEST_SHA256,
        "lp_manifest_sha256": LOCKED_LP_MANIFEST_SHA256,
        "lp_execution_sha256": LOCKED_LP_EXECUTION_SHA256,
        "lp_sha256": LOCKED_LP_SHA256,
    }
    for key, expected in expected_case_links.items():
        if case_manifest.get(key) != expected:
            raise ValueError(f"D43 case manifest does not bind {key}")
    if case_manifest.get("architecture") != "tes":
        raise ValueError("D43 case manifest architecture mismatch")
    if case_manifest.get("relaxation_mode") != "r0_all_continuous":
        raise ValueError("D43 case manifest relaxation mismatch")
    if case_execution.get("case_manifest_sha256") != LOCKED_CASE_MANIFEST_SHA256:
        raise ValueError("D43 case execution does not bind the case manifest")
    if lp_execution.get("manifest_sha256") != LOCKED_LP_MANIFEST_SHA256:
        raise ValueError("D43 LP execution does not bind the LP manifest")
    if lp_execution.get("lp_sha256") != LOCKED_LP_SHA256:
        raise ValueError("D43 LP execution fingerprint mismatch")
    embedded_phases = lp_execution.get("phase_executions")
    if not isinstance(embedded_phases, dict):
        raise ValueError("D43 LP execution has no phase hash chain")
    for spec in SNAPSHOT_SPECS:
        phase_execution = phase_executions.get(spec.key)
        embedded = embedded_phases.get(spec.key)
        if not isinstance(phase_execution, dict) or embedded != phase_execution:
            raise ValueError(
                f"D43 LP execution does not bind phase execution {spec.key}"
            )
        artifact_sha = embedded.get("artifact_sha256")
        if not isinstance(artifact_sha, dict):
            raise ValueError(f"D43 embedded phase {spec.key} has no artifact hash map")
        if artifact_sha.get("solution") != spec.solution_sha256:
            raise ValueError(
                f"D43 LP execution does not bind solution archive {spec.key}"
            )
        if embedded.get("lp_sha256") != LOCKED_LP_SHA256:
            raise ValueError(f"D43 embedded phase {spec.key} LP fingerprint mismatch")
        if embedded.get("lp_archive_sha256") != LOCKED_LP_ARCHIVE_SHA256:
            raise ValueError(f"D43 embedded phase {spec.key} LP archive mismatch")


def _validate_formal_inputs(d42_dir: Path, structure_manifest: Path) -> None:
    _require_hash(
        Path(d42_certificate_module.__file__),
        LOCKED_D42_CERTIFICATE_SOURCE_SHA256,
        "D42 certificate source",
    )
    _require_hash(
        Path(d42_executor_module.__file__),
        LOCKED_D42_EXECUTOR_SOURCE_SHA256,
        "D42 executor source",
    )
    locked = {
        "case_manifest.json": LOCKED_CASE_MANIFEST_SHA256,
        "case_execution.json": LOCKED_CASE_EXECUTION_SHA256,
        "lp_manifest.json": LOCKED_LP_MANIFEST_SHA256,
        "lp_execution.json": LOCKED_LP_EXECUTION_SHA256,
        "presolved_lp.bin.gz": LOCKED_LP_ARCHIVE_SHA256,
    }
    for name, expected in locked.items():
        _require_hash(d42_dir / name, expected, name)
    for spec in SNAPSHOT_SPECS:
        _require_hash(
            d42_dir / spec.solution_file,
            spec.solution_sha256,
            spec.solution_file,
        )
        _require_hash(
            d42_dir / spec.phase_execution_file,
            spec.phase_execution_sha256,
            spec.phase_execution_file,
        )
    bess_reuse_result = d42_dir.parent / "gate_b_bess_reuse" / "bess_reuse_result.json"
    _require_hash(
        bess_reuse_result,
        LOCKED_BESS_REUSE_RESULT_SHA256,
        "D42 BESS reuse result",
    )
    _require_hash(
        structure_manifest,
        LOCKED_STRUCTURE_MANIFEST_SHA256,
        "D42 structure manifest",
    )
    validate_d42_metadata_chain(
        case_manifest=_read_json(d42_dir / "case_manifest.json"),
        case_execution=_read_json(d42_dir / "case_execution.json"),
        lp_execution=_read_json(d42_dir / "lp_execution.json"),
        phase_executions={
            spec.key: _read_json(d42_dir / spec.phase_execution_file)
            for spec in SNAPSHOT_SPECS
        },
    )


def render_readme(manifest: dict[str, Any], *, manifest_sha256: str) -> str:
    selected_phase = manifest.get("selected_phase") or "none"
    lower_bound = manifest.get("formal_lower_bound_decimal") or "none"
    return (
        "# E0-D-43 offline dual certificate recovery\n\n"
        f"- Status: `{manifest['status']}`\n"
        f"- Selected frozen snapshot: `{selected_phase}`\n"
        f"- TES R0 formal lower bound (CNY): `{lower_bound}`\n"
        f"- Manifest SHA-256: `{manifest_sha256}`\n"
        "- Optimization/native solver invoked: `false`\n"
        "- Technical ranking permitted: `false`\n\n"
        "This result only audits hash-locked D42 row-dual snapshots against "
        "the unchanged 80-digit outward-rounded Lagrangian certificate. It is "
        "not a feasible upper bound, capacity plan, project TAC, or technology "
        "ranking.\n"
    )


def _child_command(d42_dir: Path, output_dir: Path, spec: SnapshotSpec) -> list[str]:
    return [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d43_offline_dual_certificate",
        "_child",
        "--d42-dir",
        str(d42_dir),
        "--output-dir",
        str(output_dir),
        "--phase",
        spec.key,
    ]


def _append_heartbeat(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def run_formal_recovery(
    *,
    d42_dir: Path,
    structure_manifest: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the two frozen offline certificates under parent resource gates."""

    if os.name == "nt" or not Path("/proc").is_dir():
        raise RuntimeError("D43 formal recovery requires Linux /proc")
    _validate_formal_inputs(d42_dir, structure_manifest)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("D43 refuses to overwrite a non-empty output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    available_before = _available_memory_gib()
    if available_before is None or available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D43 host memory is below the frozen reserve")

    started = perf_counter()
    processes: dict[str, subprocess.Popen[Any]] = {}
    logs: dict[str, Any] = {}
    phase_started: dict[str, float] = {}
    next_heartbeat: dict[str, float] = {}
    peak_child = {spec.key: 0.0 for spec in SNAPSHOT_SPECS}
    minimum_available = available_before
    peak_aggregate = 0.0
    stop_reason: str | None = None
    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
    for spec in SNAPSHOT_SPECS:
        paths = _phase_paths(output_dir, spec.key)
        log_handle = paths["log"].open("wb")
        logs[spec.key] = log_handle
        process = subprocess.Popen(
            _child_command(d42_dir, output_dir, spec),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        processes[spec.key] = process
        phase_started[spec.key] = perf_counter()
        next_heartbeat[spec.key] = 0.0

    try:
        while any(process.poll() is None for process in processes.values()):
            now = perf_counter()
            total_elapsed = now - started
            child_elapsed = {
                key: now - phase_started[key]
                for key, process in processes.items()
                if process.poll() is None
            }
            child_rss = {
                key: (
                    _process_tree_rss_gib(process.pid)
                    if process.poll() is None
                    else None
                )
                for key, process in processes.items()
            }
            for key, rss in child_rss.items():
                if rss is not None:
                    peak_child[key] = max(peak_child[key], rss)
            parent_rss = _process_rss_gib(os.getpid()) or 0.0
            aggregate = parent_rss + sum(rss or 0.0 for rss in child_rss.values())
            peak_aggregate = max(peak_aggregate, aggregate)
            available = _available_memory_gib()
            if available is not None:
                minimum_available = min(minimum_available, available)
            for spec in SNAPSHOT_SPECS:
                if total_elapsed >= next_heartbeat[spec.key]:
                    _append_heartbeat(
                        _phase_paths(output_dir, spec.key)["heartbeat"],
                        {
                            "schema_id": PHASE_EXECUTION_SCHEMA_ID,
                            "phase": spec.key,
                            "elapsed_seconds": child_elapsed.get(spec.key),
                            "child_tree_rss_gib": child_rss.get(spec.key),
                            "aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                            "state": (
                                "running"
                                if processes[spec.key].poll() is None
                                else "exited"
                            ),
                        },
                    )
                    next_heartbeat[spec.key] += HEARTBEAT_INTERVAL_SECONDS
            stop_reason = monitor_stop_reason(
                child_elapsed_seconds=child_elapsed,
                total_elapsed_seconds=total_elapsed,
                child_rss_gib=child_rss,
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
        else:
            for process in processes.values():
                process.wait()
    finally:
        for handle in logs.values():
            handle.close()

    phase_results: dict[str, dict[str, Any]] = {}
    phase_artifacts: dict[str, dict[str, str | None]] = {}
    for spec in SNAPSHOT_SPECS:
        process = processes[spec.key]
        paths = _phase_paths(output_dir, spec.key)
        successful = (
            process.returncode == 0
            and paths["result"].is_file()
            and paths["certificate"].is_file()
        )
        result = (
            _read_json(paths["result"])
            if successful
            else {
                "schema_id": PHASE_RESULT_SCHEMA_ID,
                "phase": spec.key,
                "status": stop_reason or "child_failed",
                "formal_lower_bound_eligible": False,
                "certificate": None,
                "technical_ranking_permitted": False,
            }
        )
        phase_results[spec.key] = result
        phase_artifacts[spec.key] = {
            "result_sha256": _sha256(paths["result"])
            if paths["result"].is_file()
            else None,
            "certificate_sha256": (
                _sha256(paths["certificate"])
                if paths["certificate"].is_file()
                else None
            ),
        }
        execution = {
            "schema_id": PHASE_EXECUTION_SCHEMA_ID,
            "phase": spec.key,
            "return_code": process.returncode,
            "stop_reason": stop_reason,
            "runtime_seconds": perf_counter() - phase_started[spec.key],
            "peak_child_process_tree_rss_gib": peak_child[spec.key],
            "peak_parent_child_aggregate_rss_gib": peak_aggregate,
            "minimum_available_memory_gib": minimum_available,
            "heartbeat_sha256": (
                _sha256(paths["heartbeat"]) if paths["heartbeat"].is_file() else None
            ),
            "child_log_sha256": _sha256(paths["log"]),
            **phase_artifacts[spec.key],
            "formal_lower_bound_eligible": (
                result.get("formal_lower_bound_eligible") is True
            ),
            "technical_ranking_permitted": False,
        }
        _atomic_write_json(paths["execution"], execution)
        phase_artifacts[spec.key]["execution_sha256"] = _sha256(paths["execution"])

    input_sha256 = {
        "case_manifest": LOCKED_CASE_MANIFEST_SHA256,
        "case_execution": LOCKED_CASE_EXECUTION_SHA256,
        "lp_manifest": LOCKED_LP_MANIFEST_SHA256,
        "lp_execution": LOCKED_LP_EXECUTION_SHA256,
        "lp_archive": LOCKED_LP_ARCHIVE_SHA256,
        "structure_manifest": LOCKED_STRUCTURE_MANIFEST_SHA256,
        "bess_reuse_result": LOCKED_BESS_REUSE_RESULT_SHA256,
        **{f"{spec.key}_solution": spec.solution_sha256 for spec in SNAPSHOT_SPECS},
        **{
            f"{spec.key}_phase_execution": spec.phase_execution_sha256
            for spec in SNAPSHOT_SPECS
        },
    }
    source_sha256 = {
        "e0d42_native_highs_certificate.py": LOCKED_D42_CERTIFICATE_SOURCE_SHA256,
        "e0d42_gate_b_executor.py": LOCKED_D42_EXECUTOR_SOURCE_SHA256,
        "e0d43_offline_dual_certificate.py": _sha256(Path(__file__)),
    }
    manifest = assemble_manifest(
        phase_results=phase_results,
        phase_artifact_sha256=phase_artifacts,
        input_sha256=input_sha256,
        source_sha256=source_sha256,
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
            for spec in SNAPSHOT_SPECS
        },
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(output_dir / "execution.json", total_execution)
    return manifest


def _run_child_from_args(args: argparse.Namespace) -> None:
    spec = SNAPSHOT_BY_KEY[args.phase]
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
    child.add_argument("--phase", choices=tuple(SNAPSHOT_BY_KEY), required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--d42-dir", type=Path, required=True)
    run.add_argument("--structure-manifest", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "_child":
        _run_child_from_args(args)
        return
    manifest = run_formal_recovery(
        d42_dir=args.d42_dir,
        structure_manifest=args.structure_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
