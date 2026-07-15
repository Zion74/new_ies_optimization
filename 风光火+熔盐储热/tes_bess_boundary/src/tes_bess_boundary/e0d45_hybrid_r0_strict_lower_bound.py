"""E0-D-45 Hybrid R0 native snapshots and strict lower-bound recovery.

The formal workflow prepares the locked Hybrid R0 LP once, runs IPX and the
first dual-simplex phase concurrently, persists their native solution snapshots
before any Decimal work, and then applies the unchanged D44 24-chunk fork
certificate kernel.  It never treats a native objective as a strict bound and
never creates a feasible MILP solution, capacity decision, TAC, or ranking.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import platform
import signal
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

from tes_bess_boundary import e0d42_gate_b_executor as d42_executor
from tes_bess_boundary import e0d42_gate_b_formal as d42_formal
from tes_bess_boundary import e0d43_offline_dual_certificate as d43_module
from tes_bess_boundary import e0d44_fork_parallel_certificate as d44_module
from tes_bess_boundary.e0d40_full_year_compute_gate import _sha256


SCHEMA_ID = "tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound.v1"
SOLVER_RESULT_SCHEMA_ID = f"{SCHEMA_ID}.solver_snapshot"
SOLVER_EXECUTION_SCHEMA_ID = f"{SOLVER_RESULT_SCHEMA_ID}.execution"
CERTIFICATE_RESULT_SCHEMA_ID = f"{SCHEMA_ID}.certificate_phase"
CERTIFICATE_EXECUTION_SCHEMA_ID = f"{CERTIFICATE_RESULT_SCHEMA_ID}.execution"
MANIFEST_SCHEMA_ID = f"{SCHEMA_ID}.manifest"
EXECUTION_SCHEMA_ID = f"{MANIFEST_SCHEMA_ID}.execution"
GATE_A_SCHEMA_ID = f"{SCHEMA_ID}.gate_a"

D42_STRUCTURE_MANIFEST_SHA256 = (
    "2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1"
)
D42_HYBRID_R0_CASE_SHA256 = (
    "0923ae65d123e29691ff794828dfa9f2228ea81fbc93608bde0ccd914c23315b"
)
D44_FORMAL_MANIFEST_SHA256 = (
    "d6fe2f34a354e5986ad4775034135f090df2e74492e0c7abc8f95861cb89739f"
)
D44_FORMAL_EXECUTION_SHA256 = (
    "673f4442d1f53d714f5eabd0c450c33373457cbd214a5ce0a85956d60f89946e"
)
LOCKED_SOURCE_SHA256 = {
    "planning_model.py": (
        "fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2"
    ),
    "e0d42_gate_b_formal.py": (
        "a2ba832e51a227b3ad9e3c3484ffe958ca1df39442555dfd397a4330666ca53e"
    ),
    "e0d42_gate_b_executor.py": (
        "c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51"
    ),
    "e0d42_native_highs_certificate.py": (
        "3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298"
    ),
    "e0d44_fork_parallel_certificate.py": (
        "16786dd98757851dc2829b335d12ddb8dfeab38fd9bc03fcf3ac840e9df41c4c"
    ),
}

FORMAL_ORIGINAL_LP = {
    "num_row": 667_662,
    "num_col": 685_194,
    "num_nz": 2_688_087,
    "lp_sha256": "3534a0c91e1f47bbd32b7125216c70bdfc06df91984b15136b5d8b5cd68e35c8",
}
FORMAL_PRESOLVED_LP = {
    "num_row": 495_630,
    "num_col": 539_546,
    "num_nz": 1_985_956,
    "presolved_lp_sha256": (
        "756014eca3a93581a09f0abf99b42fd52e73a94694d532798d60290d7ddf740a"
    ),
}
FORMAL_ORIGINAL_BINARY_COUNT = 96_625
FORMAL_REMAINING_BINARY_COUNT = 0
FORMAL_THREADS = 12
FORMAL_DECIMAL_PRECISION = 80
FORMAL_CHUNK_COUNT = 24
FORMAL_WORKERS_PER_PHASE = 24

PREPARE_HARD_WALL_SECONDS = 420.0
PREPARE_TREE_RSS_LIMIT_GIB = 12.0
PREPARE_AGGREGATE_RSS_LIMIT_GIB = 15.0
SOLVER_STAGE_HARD_WALL_SECONDS = 1_080.0
CERTIFICATE_STAGE_HARD_WALL_SECONDS = 1_080.0
CERTIFICATE_PHASE_HARD_WALL_SECONDS = 900.0
PHASE_TREE_RSS_LIMIT_GIB = 20.0
STAGE_AGGREGATE_RSS_LIMIT_GIB = 45.0
HOST_MEMORY_RESERVE_GIB = 30.0
TOTAL_HARD_WALL_SECONDS = 2_700.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0
TERMINATION_GRACE_SECONDS = 30.0

BESS_STRICT_LOWER_BOUND_CNY = "1144950604.8368804"
TES_STRICT_LOWER_BOUND_CNY = (
    "254860566.61931588889075258309724606578637338890918249419801438224278086471875331"
)


@dataclass(frozen=True)
class SnapshotPhase:
    key: str
    solver_name: str
    soft_wall_seconds: float
    parent_hard_wall_seconds: float


SNAPSHOT_PHASES = (
    SnapshotPhase("ipx", "ipx", 900.0, 1_020.0),
    SnapshotPhase("simplex_1", "simplex", 600.0, 720.0),
)
SNAPSHOT_BY_KEY = {phase.key: phase for phase in SNAPSHOT_PHASES}


@dataclass(frozen=True)
class StageProcess:
    key: str
    command: tuple[str, ...]
    paths: dict[str, Path]
    hard_wall_seconds: float
    lp_sha256: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _solver_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    if phase not in SNAPSHOT_BY_KEY:
        raise ValueError(f"unknown D45 solver phase: {phase}")
    prefix = f"solver_{phase}"
    return {
        "result": output_dir / f"{prefix}_result.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solution": output_dir / f"{prefix}_solution.bin.gz",
        "progress": output_dir / f"{prefix}_progress.json",
        "log": output_dir / f"{prefix}.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.ndjson",
    }


def _certificate_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    if phase not in SNAPSHOT_BY_KEY:
        raise ValueError(f"unknown D45 certificate phase: {phase}")
    prefix = f"certificate_{phase}"
    return {
        "result": output_dir / f"{prefix}_result.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "certificate": output_dir / f"{prefix}.json",
        "chunks": output_dir / f"{prefix}_chunks.json",
        "progress": output_dir / f"{prefix}_progress.ndjson",
        "log": output_dir / f"{prefix}.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.ndjson",
    }


def _prepare_paths(output_dir: Path) -> dict[str, Path]:
    paths = d42_formal._prepare_paths(output_dir)
    return {**paths, "execution": output_dir / "prepare_execution.json"}


def _set_numeric_thread_environment() -> None:
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = "1"


def validate_locked_source_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    actual = {name: _sha256(package / name) for name in LOCKED_SOURCE_SHA256}
    if actual != LOCKED_SOURCE_SHA256:
        changed = sorted(name for name in actual if actual[name] != LOCKED_SOURCE_SHA256[name])
        raise ValueError(f"D45 locked dependency source changed: {changed}")
    return actual


def validate_hybrid_prepare_identity(
    prepare_result: dict[str, Any],
    structure_case: dict[str, Any],
) -> dict[str, Any]:
    """Reject any formal prepare result outside the frozen Hybrid R0 identity."""

    expected_case = structure_case["lp_identity_audit"]
    checks = {
        "schema": prepare_result.get("schema_id") == d42_formal.PREPARE_SCHEMA_ID,
        "status": prepare_result.get("status") == "formal_lp_prepared",
        "case": prepare_result.get("case_key") == "hybrid_r0",
        "architecture": prepare_result.get("architecture") == "hybrid",
        "relaxation": prepare_result.get("relaxation_mode") == "r0_all_continuous",
        "topology": prepare_result.get("topology_value") is None,
        "structure_manifest": prepare_result.get("structure_manifest_sha256")
        == D42_STRUCTURE_MANIFEST_SHA256,
        "structure_case": prepare_result.get("structure_case_sha256")
        == D42_HYBRID_R0_CASE_SHA256,
        "optimization_not_invoked": prepare_result.get("optimization_invoked") is False,
        "single_build": prepare_result.get("single_original_model_build") is True,
        "single_presolve": prepare_result.get("single_explicit_presolve") is True,
        "audit": prepare_result.get("audit", {}).get("passed") is True,
    }
    relaxation = prepare_result.get("relaxation", {})
    checks["binary_count"] = (
        relaxation.get("relaxed_binary_variable_count") == FORMAL_ORIGINAL_BINARY_COUNT
        and relaxation.get("remaining_binary_variable_count")
        == FORMAL_REMAINING_BINARY_COUNT
    )
    original = prepare_result.get("original_lp", {})
    presolved = prepare_result.get("presolved_lp", {})
    checks["original_lp"] = all(
        original.get(key) == value for key, value in FORMAL_ORIGINAL_LP.items()
    )
    checks["presolved_lp"] = all(
        presolved.get(key) == value for key, value in FORMAL_PRESOLVED_LP.items()
    )
    checks["structure_original_equal"] = original == expected_case["original_lp"]
    checks["structure_presolved_equal"] = presolved == expected_case["presolved_lp"]
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise ValueError(f"D45 Hybrid R0 prepare identity mismatch: {failed}")
    return {"passed": True, "checks": checks}


def validate_solver_snapshot(
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
    """Validate a new D45 snapshot through the unchanged D43 archive gate."""

    row_dual, audit = d43_module.load_locked_snapshot(
        solution_path=solution_path,
        phase_execution_path=phase_execution_path,
        phase=phase,
        expected_solution_sha256=expected_solution_sha256,
        expected_phase_execution_sha256=expected_phase_execution_sha256,
        expected_lp_sha256=expected_lp_sha256,
        expected_num_col=expected_num_col,
        expected_num_row=expected_num_row,
    )
    execution = _load_json(phase_execution_path)
    if not all(
        (
            execution.get("schema_id") == SOLVER_EXECUTION_SCHEMA_ID,
            execution.get("status") == "complete",
            execution.get("return_code") == 0,
            execution.get("resource_gate_passed") is True,
            execution.get("stop_reason") is None,
            execution.get("phase") == phase,
            execution.get("hard_wall_enforced_by_parent") is True,
        )
    ):
        raise ValueError("D45 solver execution sidecar is ineligible")
    return row_dual, {**audit, "d45_execution_gate_passed": True}


def run_solver_snapshot_child(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    expected_lp_archive_sha256: str,
    phase: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Run one native HiGHS phase and stop after persisting its snapshot."""

    import highspy

    if phase not in SNAPSHOT_BY_KEY:
        raise ValueError(f"unknown D45 solver phase: {phase}")
    _set_numeric_thread_environment()
    paths = _solver_paths(output_dir, phase)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("result", "solution"):
        if paths[key].exists():
            raise FileExistsError(f"D45 refuses to overwrite {paths[key]}")
    lp, lp_audit = d42_executor.read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    if lp_audit["archive_sha256"] != expected_lp_archive_sha256:
        raise ValueError("D45 LP archive SHA-256 mismatch")
    d42_spec = d42_executor.PHASE_BY_KEY[phase]
    frozen = SNAPSHOT_BY_KEY[phase]
    if (
        d42_spec.solver_name != frozen.solver_name
        or d42_spec.soft_wall_seconds != frozen.soft_wall_seconds
        or d42_spec.parent_hard_wall_seconds != frozen.parent_hard_wall_seconds
        or d42_executor.FORMAL_THREADS != FORMAL_THREADS
    ):
        raise ValueError("D45 solver phase differs from the locked D42 phase")

    highspy.Highs.resetGlobalScheduler(True)
    owner = highspy.Highs()
    options = d42_executor._set_locked_options(owner, d42_spec)
    if owner.passModel(lp) != highspy.HighsStatus.kOk:
        raise RuntimeError("D45 HiGHS passModel failed")
    started = perf_counter()
    callback_count = 0
    soft_interrupt_requested = False
    last_progress = -HEARTBEAT_INTERVAL_SECONDS
    latest_iterations = {"ipm": 0, "simplex": 0}

    def write_progress(state: str) -> None:
        d42_executor._atomic_write_json(
            paths["progress"],
            {
                "schema_id": SOLVER_EXECUTION_SCHEMA_ID,
                "phase": phase,
                "pid": os.getpid(),
                "state": state,
                "elapsed_seconds": perf_counter() - started,
                "ipm_iteration_count": latest_iterations["ipm"],
                "simplex_iteration_count": latest_iterations["simplex"],
                "callback_count": callback_count,
                "soft_interrupt_requested": soft_interrupt_requested,
            },
        )

    def interrupt(event: object) -> None:
        nonlocal callback_count, last_progress, soft_interrupt_requested
        callback_count += 1
        latest_iterations["ipm"] = int(event.data_out.ipm_iteration_count)
        latest_iterations["simplex"] = int(event.data_out.simplex_iteration_count)
        elapsed = perf_counter() - started
        if elapsed - last_progress >= HEARTBEAT_INTERVAL_SECONDS:
            write_progress("native_solve_running")
            last_progress = elapsed
        if elapsed >= frozen.soft_wall_seconds:
            soft_interrupt_requested = True
            write_progress("soft_interrupt_requested")
            event.interrupt()

    write_progress("native_solve_starting")
    if frozen.solver_name == "ipx":
        owner.cbIpmInterrupt += interrupt
    else:
        owner.cbSimplexInterrupt += interrupt
    run_status = owner.run()
    if run_status == highspy.HighsStatus.kError:
        raise RuntimeError("HiGHS failed without an auditable D45 native state")

    info = owner.getInfo()
    solution = owner.getSolution()
    model_status = owner.modelStatusToString(owner.getModelStatus())
    latest_iterations["ipm"] = int(info.ipm_iteration_count)
    latest_iterations["simplex"] = int(info.simplex_iteration_count)
    write_progress("native_returned_writing_snapshot")
    solution_audit = d42_executor._write_solution_archive(
        paths["solution"],
        solution=solution,
        lp_sha256=expected_lp_sha256,
        phase_key=phase,
        model_status=model_status,
    )
    expected_lengths = {
        "col_value": int(lp.num_col_),
        "col_dual": int(lp.num_col_),
        "row_value": int(lp.num_row_),
        "row_dual": int(lp.num_row_),
    }
    actual_lengths = {
        "col_value": len(solution.col_value),
        "col_dual": len(solution.col_dual),
        "row_value": len(solution.row_value),
        "row_dual": len(solution.row_dual),
    }
    finite_row_dual = all(math.isfinite(float(value)) for value in solution.row_dual)
    snapshot_eligible = all(
        (
            bool(solution.dual_valid),
            actual_lengths == expected_lengths,
            finite_row_dual,
        )
    )
    result = {
        "schema_id": SOLVER_RESULT_SCHEMA_ID,
        "status": "snapshot_ready" if snapshot_eligible else "snapshot_ineligible",
        "phase": phase,
        "solver_name": frozen.solver_name,
        "lp_sha256": expected_lp_sha256,
        "lp_archive_sha256": expected_lp_archive_sha256,
        "highs_version": owner.version(),
        "run_status": str(run_status),
        "model_status": model_status,
        "callback_count": callback_count,
        "soft_interrupt_requested": soft_interrupt_requested,
        "runtime_seconds": perf_counter() - started,
        "phase_spec": asdict(frozen),
        "locked_options": options,
        "native_info": d42_executor._info_audit(owner, info),
        "native_solution": solution_audit,
        "solution_sha256": _sha256(paths["solution"]),
        "array_lengths": actual_lengths,
        "finite_row_dual_count": len(solution.row_dual) if finite_row_dual else None,
        "snapshot_eligible_for_certificate": snapshot_eligible,
        "strict_certificate_pending": snapshot_eligible,
        "formal_lower_bound_eligible": False,
        "optimization_invoked": True,
        "native_solver_invoked": True,
        "technical_ranking_permitted": False,
    }
    d42_executor._atomic_write_json(paths["result"], result)
    write_progress("snapshot_artifacts_complete")
    highspy.Highs.resetGlobalScheduler(True)
    return result


def run_certificate_child(
    *,
    lp_archive_path: Path,
    expected_lp_sha256: str,
    expected_lp_archive_sha256: str,
    solution_path: Path,
    solver_execution_path: Path,
    expected_solution_sha256: str,
    expected_solver_execution_sha256: str,
    phase: str,
    output_dir: Path,
    expected_num_col: int = FORMAL_PRESOLVED_LP["num_col"],
    expected_num_row: int = FORMAL_PRESOLVED_LP["num_row"],
    chunk_count: int = FORMAL_CHUNK_COUNT,
    fork_workers: int | None = FORMAL_WORKERS_PER_PHASE,
) -> dict[str, Any]:
    """Apply the unchanged D44 kernel to one fully audited D45 snapshot."""

    paths = _certificate_paths(output_dir, phase)
    for key in ("result", "certificate", "chunks"):
        if paths[key].exists():
            raise FileExistsError(f"D45 refuses to overwrite {paths[key]}")
    lp, lp_audit = d42_executor.read_lp_archive(
        lp_archive_path,
        expected_lp_sha256=expected_lp_sha256,
    )
    if lp_audit["archive_sha256"] != expected_lp_archive_sha256:
        raise ValueError("D45 certificate LP archive SHA-256 mismatch")
    if (
        lp_audit["audit"]["num_col"] != expected_num_col
        or lp_audit["audit"]["num_row"] != expected_num_row
    ):
        raise ValueError("D45 certificate LP dimensions changed")
    row_dual, snapshot_audit = validate_solver_snapshot(
        solution_path=solution_path,
        phase_execution_path=solver_execution_path,
        phase=phase,
        expected_solution_sha256=expected_solution_sha256,
        expected_phase_execution_sha256=expected_solver_execution_sha256,
        expected_lp_sha256=expected_lp_sha256,
        expected_num_col=expected_num_col,
        expected_num_row=expected_num_row,
    )
    certificate = d44_module.certify_partitioned_lagrangian(
        lp,
        row_dual,
        expected_lp_sha256=expected_lp_sha256,
        precision=FORMAL_DECIMAL_PRECISION,
        chunk_count=chunk_count,
        fork_workers=fork_workers,
        progress_path=paths["progress"],
    )
    chunks = {
        "schema_id": f"{SCHEMA_ID}.chunks",
        "phase": phase,
        "chunk_count": chunk_count,
        "chunks": certificate["chunks"],
    }
    d42_executor._atomic_write_json(paths["chunks"], chunks)
    d42_executor._atomic_write_json(paths["certificate"], certificate)
    result = {
        "schema_id": CERTIFICATE_RESULT_SCHEMA_ID,
        "phase": phase,
        "status": certificate["status"],
        "lp_sha256": expected_lp_sha256,
        "lp_archive_sha256": expected_lp_archive_sha256,
        "solution_sha256": expected_solution_sha256,
        "solver_execution_sha256": expected_solver_execution_sha256,
        "snapshot_audit": snapshot_audit,
        "certificate_sha256": _sha256(paths["certificate"]),
        "chunks_sha256": _sha256(paths["chunks"]),
        "formal_lower_bound_eligible": certificate["formal_lower_bound_eligible"],
        "lower_bound_decimal": certificate["lower_bound_decimal"],
        "upper_bound_decimal": certificate["upper_bound_decimal"],
        "optimization_invoked": False,
        "native_solver_invoked": False,
        "technical_ranking_permitted": False,
    }
    d42_executor._atomic_write_json(paths["result"], result)
    return result


def monitor_stage_stop_reason(
    *,
    phase_elapsed_seconds: dict[str, float],
    phase_hard_walls: dict[str, float],
    stage_elapsed_seconds: float,
    stage_hard_wall_seconds: float,
    phase_rss_gib: dict[str, float | None],
    phase_rss_limit_gib: float,
    aggregate_rss_gib: float | None,
    aggregate_rss_limit_gib: float,
    available_memory_gib: float | None,
) -> str | None:
    if stage_elapsed_seconds >= stage_hard_wall_seconds:
        return "stage_hard_wall_reached"
    for key in phase_hard_walls:
        if phase_elapsed_seconds.get(key, 0.0) >= phase_hard_walls[key]:
            return f"phase_hard_wall_reached:{key}"
    for key in phase_hard_walls:
        rss = phase_rss_gib.get(key)
        if rss is not None and rss >= phase_rss_limit_gib:
            return f"phase_rss_limit_reached:{key}"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= aggregate_rss_limit_gib:
        return "aggregate_rss_limit_reached"
    if (
        available_memory_gib is not None
        and available_memory_gib < HOST_MEMORY_RESERVE_GIB
    ):
        return "host_memory_reserve_breached"
    return None


def _process_group_exists(process_group_id: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _cleanup_residual_process_group(process_group_id: int) -> bool:
    """Remove an escaped child group and report that a residual was detected."""

    if not _process_group_exists(process_group_id):
        return False
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = perf_counter() + TERMINATION_GRACE_SECONDS
    while perf_counter() < deadline and _process_group_exists(process_group_id):
        time.sleep(0.1)
    if _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return True


def validate_execution_artifacts(
    execution: dict[str, Any], paths: dict[str, Path]
) -> dict[str, str | None]:
    expected = execution.get("artifact_sha256")
    actual = {
        key: _sha256(path) if path.is_file() else None
        for key, path in paths.items()
        if key != "execution"
    }
    if not isinstance(expected, dict) or expected != actual:
        raise ValueError("D45 execution artifact hash map mismatch")
    return actual


def _run_parallel_stage(
    *,
    processes: Sequence[StageProcess],
    execution_schema_id: str,
    stage_name: str,
    stage_hard_wall_seconds: float,
    phase_rss_limit_gib: float,
    aggregate_rss_limit_gib: float,
    total_run_started: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Run independent process groups with a shared resource monitor."""

    if not processes:
        return {}
    available_before = d42_executor._available_memory_gib()
    if available_before is None:
        raise RuntimeError("D45 formal stages require Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D45 host memory is below the frozen reserve")
    for item in processes:
        for key in ("result", "execution", "log", "heartbeat"):
            if item.paths[key].exists():
                raise FileExistsError(f"D45 refuses to overwrite {item.paths[key]}")
        item.paths["result"].parent.mkdir(parents=True, exist_ok=True)

    stage_started = perf_counter()
    children: dict[str, subprocess.Popen[Any]] = {}
    phase_started: dict[str, float] = {}
    peak_phase = {item.key: 0.0 for item in processes}
    sample_count = {item.key: 0 for item in processes}
    peak_aggregate = 0.0
    minimum_available = available_before
    memory_samples = 0
    last_heartbeat = {item.key: -HEARTBEAT_INTERVAL_SECONDS for item in processes}
    phase_stop: dict[str, str | None] = {item.key: None for item in processes}
    termination_signal: dict[str, str | None] = {item.key: None for item in processes}
    residual_process_group = {item.key: False for item in processes}
    stage_stop: str | None = None
    by_key = {item.key: item for item in processes}

    with ExitStack() as stack:
        logs = {
            item.key: stack.enter_context(
                item.paths["log"].open("w", encoding="utf-8", newline="\n")
            )
            for item in processes
        }
        heartbeats = {
            item.key: stack.enter_context(
                item.paths["heartbeat"].open(
                    "w", encoding="utf-8", newline="\n", buffering=1
                )
            )
            for item in processes
        }
        for item in processes:
            d42_executor._atomic_write_json(
                item.paths["execution"],
                {
                    "schema_id": execution_schema_id,
                    "status": "child_starting",
                    "stage": stage_name,
                    "phase": item.key,
                    "lp_sha256": item.lp_sha256,
                    "hard_wall_enforced_by_parent": True,
                    "available_memory_before_gib": available_before,
                },
            )
            children[item.key] = subprocess.Popen(
                list(item.command),
                stdout=logs[item.key],
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
            )
            phase_started[item.key] = perf_counter()

        while any(process.poll() is None for process in children.values()):
            now = perf_counter()
            stage_elapsed = now - stage_started
            active = {key for key, process in children.items() if process.poll() is None}
            phase_elapsed = {key: now - phase_started[key] for key in active}
            phase_rss = {
                key: d42_executor._process_tree_rss_gib(children[key].pid)
                for key in active
            }
            for key, rss in phase_rss.items():
                if rss is not None:
                    peak_phase[key] = max(peak_phase[key], rss)
                    sample_count[key] += 1
            parent_rss = d42_executor._process_rss_gib(os.getpid())
            aggregate = (
                parent_rss + sum(rss or 0.0 for rss in phase_rss.values())
                if parent_rss is not None
                else None
            )
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            available = d42_executor._available_memory_gib()
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            for key in active:
                elapsed = phase_elapsed[key]
                if elapsed - last_heartbeat[key] >= HEARTBEAT_INTERVAL_SECONDS:
                    progress = None
                    if by_key[key].paths["progress"].is_file():
                        try:
                            progress = _load_json(by_key[key].paths["progress"])
                        except (json.JSONDecodeError, OSError):
                            progress = {"state": "progress_read_incomplete"}
                    heartbeats[key].write(
                        json.dumps(
                            {
                                "stage": stage_name,
                                "phase": key,
                                "pid": children[key].pid,
                                "phase_elapsed_seconds": elapsed,
                                "stage_elapsed_seconds": stage_elapsed,
                                "phase_tree_rss_gib": phase_rss.get(key),
                                "aggregate_rss_gib": aggregate,
                                "available_memory_gib": available,
                                "progress": progress,
                            },
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    heartbeats[key].flush()
                    last_heartbeat[key] = elapsed

            if (
                total_run_started is not None
                and now - total_run_started >= TOTAL_HARD_WALL_SECONDS
            ):
                reason = "total_parent_hard_wall_reached"
            else:
                reason = monitor_stage_stop_reason(
                    phase_elapsed_seconds=phase_elapsed,
                    phase_hard_walls={
                        key: by_key[key].hard_wall_seconds for key in active
                    },
                    stage_elapsed_seconds=stage_elapsed,
                    stage_hard_wall_seconds=stage_hard_wall_seconds,
                    phase_rss_gib=phase_rss,
                    phase_rss_limit_gib=phase_rss_limit_gib,
                    aggregate_rss_gib=aggregate,
                    aggregate_rss_limit_gib=aggregate_rss_limit_gib,
                    available_memory_gib=available,
                )
            if reason is not None:
                if reason.startswith("phase_"):
                    key = reason.rsplit(":", 1)[-1]
                    phase_stop[key] = reason
                    termination_signal[key] = d42_executor._terminate_process_group(
                        children[key]
                    )
                else:
                    stage_stop = reason
                    for key in active:
                        phase_stop[key] = reason
                        termination_signal[key] = d42_executor._terminate_process_group(
                            children[key]
                        )
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_codes = {key: process.wait() for key, process in children.items()}
        residual_process_group = {
            key: _cleanup_residual_process_group(process.pid)
            for key, process in children.items()
        }

    executions: dict[str, dict[str, Any]] = {}
    for key, item in by_key.items():
        hashes = {
            artifact: _sha256(path) if path.is_file() else None
            for artifact, path in item.paths.items()
            if artifact != "execution"
        }
        result = _load_json(item.paths["result"]) if item.paths["result"].is_file() else None
        resource_gate_passed = all(
            (
                phase_stop[key] is None,
                stage_stop is None,
                residual_process_group[key] is False,
                sample_count[key] > 0,
                memory_samples > 0,
                peak_phase[key] < phase_rss_limit_gib,
                peak_aggregate < aggregate_rss_limit_gib,
                minimum_available >= HOST_MEMORY_RESERVE_GIB,
            )
        )
        complete = return_codes[key] == 0 and result is not None and resource_gate_passed
        execution = {
            "schema_id": execution_schema_id,
            "status": "complete" if complete else "interrupted_or_failed",
            "stage": stage_name,
            "phase": key,
            "lp_sha256": item.lp_sha256,
            "return_code": return_codes[key],
            "phase_runtime_seconds": perf_counter() - phase_started[key],
            "stage_runtime_seconds": perf_counter() - stage_started,
            "hard_wall_enforced_by_parent": True,
            "stop_reason": phase_stop[key] or stage_stop,
            "termination_signal": termination_signal[key],
            "residual_process_group_detected": residual_process_group[key],
            "resource_gate_passed": resource_gate_passed,
            "peak_phase_process_tree_rss_gib": peak_phase[key],
            "peak_stage_aggregate_rss_gib": peak_aggregate,
            "minimum_available_memory_gib": minimum_available,
            "rss_sample_count": sample_count[key],
            "available_memory_sample_count": memory_samples,
            "artifact_sha256": hashes,
            "technical_ranking_permitted": False,
        }
        d42_executor._atomic_write_json(item.paths["execution"], execution)
        executions[key] = execution
    return executions


def assemble_manifest(
    *,
    phase_results: dict[str, dict[str, Any]],
    phase_artifacts: dict[str, dict[str, str | None]],
    input_sha256: dict[str, str],
    source_sha256: dict[str, str],
    gate_a_audit: dict[str, Any],
) -> dict[str, Any]:
    """Select the greatest eligible Decimal bound, preferring IPX on a tie."""

    eligible: list[tuple[Decimal, int, str]] = []
    for phase in SNAPSHOT_PHASES:
        result = phase_results[phase.key]
        if result.get("formal_lower_bound_eligible") is True:
            value = result.get("lower_bound_decimal")
            if not isinstance(value, str) or not Decimal(value).is_finite():
                raise ValueError("D45 eligible phase has no finite Decimal bound")
            tie_priority = 1 if phase.key == "ipx" else 0
            eligible.append((Decimal(value), tie_priority, phase.key))
    selected_phase = max(eligible)[2] if eligible else None
    selected = phase_results[selected_phase] if selected_phase else None
    recovered = selected is not None
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "status": "hybrid_r0_lower_bound_recovered" if recovered else "no_strict_certificate",
        "architecture": "hybrid",
        "relaxation_mode": "r0_all_continuous",
        "claim_scope": "controlled_public_cost_sensitivity_not_formal_project_tac",
        "partition_rule": "floor(k*num_col/24):floor((k+1)*num_col/24)",
        "chunk_count_per_phase": FORMAL_CHUNK_COUNT,
        "workers_per_phase": FORMAL_WORKERS_PER_PHASE,
        "selected_phase": selected_phase,
        "formal_lower_bound_decimal": selected.get("lower_bound_decimal") if selected else None,
        "formal_lower_bound_float": (
            float(Decimal(selected["lower_bound_decimal"])) if selected else None
        ),
        "formal_lower_bound_eligible": recovered,
        "hybrid_r0_certificate_covers_r1_and_original_milp": recovered,
        "d46_feasible_upper_bound_contract_permitted": recovered,
        "bess_strict_lower_bound_cny": BESS_STRICT_LOWER_BOUND_CNY,
        "tes_strict_lower_bound_cny": TES_STRICT_LOWER_BOUND_CNY,
        "formal_project_tac_ready": False,
        "optimization_invoked": True,
        "native_solver_invoked": True,
        "technical_ranking_permitted": False,
        "input_sha256": input_sha256,
        "source_sha256": source_sha256,
        "gate_a_audit": gate_a_audit,
        "phase_audits": {
            phase.key: {
                "status": phase_results[phase.key].get("status"),
                "formal_lower_bound_eligible": phase_results[phase.key].get(
                    "formal_lower_bound_eligible"
                )
                is True,
                "lower_bound_decimal": phase_results[phase.key].get(
                    "lower_bound_decimal"
                ),
                **phase_artifacts[phase.key],
            }
            for phase in SNAPSHOT_PHASES
        },
    }


def validate_gate_a_manifest(
    *, gate_a_manifest: Path, d45_test_path: Path
) -> dict[str, Any]:
    if not gate_a_manifest.is_file() or not d45_test_path.is_file():
        raise FileNotFoundError("D45 Gate A manifest or test source is missing")
    payload = _load_json(gate_a_manifest)
    if payload.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D45 Gate A manifest schema mismatch")
    if payload.get("status") != "gate_a_passed":
        raise ValueError("D45 Gate A did not pass")
    required = (
        "fork_available",
        "four_worker_fork_smoke_passed",
        "snapshot_archive_passed",
        "tamper_rejection_passed",
        "partition_equivalence_passed",
        "selection_passed",
        "identity_gate_passed",
        "process_tree_cleanup_passed",
        "directed_regression_passed",
        "full_regression_passed",
    )
    if payload.get("platform") != "linux" or any(
        payload.get(key) is not True for key in required
    ):
        raise ValueError("D45 Gate A required Linux claim is missing")
    source_sha256 = _sha256(Path(__file__))
    test_sha256 = _sha256(d45_test_path)
    if payload.get("source_sha256") != source_sha256:
        raise ValueError("D45 Gate A source SHA-256 mismatch")
    if payload.get("test_sha256") != test_sha256:
        raise ValueError("D45 Gate A test SHA-256 mismatch")
    if payload.get("test_failed_count") != 0 or payload.get("test_skipped_count") != 0:
        raise ValueError("D45 Gate A contains failed or skipped tests")
    passed = payload.get("test_passed_count")
    if not isinstance(passed, int) or passed < 16:
        raise ValueError("D45 Gate A test count is incomplete")
    commit = payload.get("git_commit")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise ValueError("D45 Gate A Git commit identity is invalid")
    return {
        "manifest_sha256": _sha256(gate_a_manifest),
        "source_sha256": source_sha256,
        "test_sha256": test_sha256,
        "git_commit": commit,
        "test_passed_count": passed,
    }


def validate_formal_prerequisites(
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d44_formal_manifest_path: Path,
    gate_a_manifest_path: Path,
    d45_test_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, Any]]:
    source_hashes = validate_locked_source_hashes()
    structure_manifest, structure_case = d42_formal.load_locked_structure_case(
        structure_dir, "hybrid_r0"
    )
    if _sha256(structure_dir / "structure_hybrid_r0.json") != D42_HYBRID_R0_CASE_SHA256:
        raise ValueError("D45 Hybrid R0 structure case SHA-256 mismatch")
    d42_formal._validate_current_inputs(
        structure_manifest=structure_manifest,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    if _sha256(d44_formal_manifest_path) != D44_FORMAL_MANIFEST_SHA256:
        raise ValueError("D45 D44 formal manifest SHA-256 mismatch")
    d44 = _load_json(d44_formal_manifest_path)
    d44_execution_path = d44_formal_manifest_path.with_name("execution.json")
    if not d44_execution_path.is_file() or _sha256(d44_execution_path) != D44_FORMAL_EXECUTION_SHA256:
        raise ValueError("D45 D44 formal execution SHA-256 mismatch")
    if not all(
        (
            d44.get("status") == "tes_lower_bound_recovered",
            d44.get("formal_lower_bound_eligible") is True,
            d44.get("selected_phase") == "ipx",
            d44.get("technical_ranking_permitted") is False,
        )
    ):
        raise ValueError("D45 D44 prerequisite claim boundary mismatch")
    gate_a = validate_gate_a_manifest(
        gate_a_manifest=gate_a_manifest_path,
        d45_test_path=d45_test_path,
    )
    return structure_manifest, structure_case, source_hashes, gate_a


def _formal_input_arguments(
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> list[str]:
    return [
        "--structure-dir",
        str(structure_dir),
        "--service-path",
        str(service_path),
        "--d40-gate-a-manifest-path",
        str(d40_gate_a_manifest_path),
        "--d41-gate-a-manifest-path",
        str(d41_gate_a_manifest_path),
        "--heat-path",
        str(heat_path),
        "--vre-path",
        str(vre_path),
        "--price-basis-path",
        str(price_basis_path),
        "--output-dir",
        str(output_dir),
    ]


def render_readme(manifest: dict[str, Any], *, manifest_sha256: str) -> str:
    return (
        "# E0-D-45 Hybrid R0 strict lower bound\n\n"
        f"- Status: `{manifest['status']}`\n"
        f"- Selected phase: `{manifest.get('selected_phase') or 'none'}`\n"
        f"- Strict lower bound: `{manifest.get('formal_lower_bound_decimal')}` CNY\n"
        f"- Manifest SHA-256: `{manifest_sha256}`\n\n"
        "The result is an outward-rounded lower bound for the locked Hybrid R0 "
        "continuous relaxation. By feasible-set containment it also bounds Hybrid "
        "R1 and the original MILP from below. It is not a feasible plan, capacity, "
        "project TAC, optimality gap, Hybrid synergy value, or technology ranking.\n"
    )


def run_formal(
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d44_formal_manifest_path: Path,
    gate_a_manifest_path: Path,
    d45_test_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute the single formal D45 run after every frozen prerequisite passes."""

    if platform.system().lower() != "linux" or "fork" not in multiprocessing.get_all_start_methods():
        raise RuntimeError("D45 formal execution requires Linux fork")
    if output_dir.exists():
        raise FileExistsError("D45 formal output directory must not already exist")
    structure_manifest, structure_case, locked_sources, gate_a = (
        validate_formal_prerequisites(
            structure_dir=structure_dir,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            d44_formal_manifest_path=d44_formal_manifest_path,
            gate_a_manifest_path=gate_a_manifest_path,
            d45_test_path=d45_test_path,
        )
    )
    output_dir.mkdir(parents=True)
    total_started = perf_counter()
    prepare_paths = _prepare_paths(output_dir)
    prepare_command = (
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound",
        "_prepare-child",
        *_formal_input_arguments(
            structure_dir=structure_dir,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            output_dir=output_dir,
        ),
    )
    prepare_execution = _run_parallel_stage(
        processes=(
            StageProcess("prepare", prepare_command, prepare_paths, PREPARE_HARD_WALL_SECONDS),
        ),
        execution_schema_id=f"{SCHEMA_ID}.prepare.execution",
        stage_name="prepare",
        stage_hard_wall_seconds=PREPARE_HARD_WALL_SECONDS,
        phase_rss_limit_gib=PREPARE_TREE_RSS_LIMIT_GIB,
        aggregate_rss_limit_gib=PREPARE_AGGREGATE_RSS_LIMIT_GIB,
        total_run_started=total_started,
    )["prepare"]
    if prepare_execution.get("status") != "complete":
        raise RuntimeError("D45 Hybrid R0 preparation did not complete")
    validate_execution_artifacts(prepare_execution, prepare_paths)
    prepare_result = _load_json(prepare_paths["result"])
    prepare_audit = validate_hybrid_prepare_identity(prepare_result, structure_case)
    expected_lp_sha256 = FORMAL_PRESOLVED_LP["presolved_lp_sha256"]
    _lp, archive_audit = d42_executor.read_lp_archive(
        prepare_paths["archive"], expected_lp_sha256=expected_lp_sha256
    )
    del _lp
    expected_lp_archive_sha256 = archive_audit["archive_sha256"]
    if expected_lp_archive_sha256 != prepare_result["lp_archive"]["archive_sha256"]:
        raise ValueError("D45 prepare LP archive hash chain mismatch")

    solver_processes = []
    for phase in SNAPSHOT_PHASES:
        paths = _solver_paths(output_dir, phase.key)
        command = (
            sys.executable,
            "-u",
            "-m",
            "tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound",
            "_solver-child",
            "--lp-archive",
            str(prepare_paths["archive"]),
            "--expected-lp-sha256",
            expected_lp_sha256,
            "--expected-lp-archive-sha256",
            expected_lp_archive_sha256,
            "--phase",
            phase.key,
            "--output-dir",
            str(output_dir),
        )
        solver_processes.append(
            StageProcess(
                phase.key,
                command,
                paths,
                phase.parent_hard_wall_seconds,
                expected_lp_sha256,
            )
        )
    solver_executions = _run_parallel_stage(
        processes=solver_processes,
        execution_schema_id=SOLVER_EXECUTION_SCHEMA_ID,
        stage_name="solver",
        stage_hard_wall_seconds=SOLVER_STAGE_HARD_WALL_SECONDS,
        phase_rss_limit_gib=PHASE_TREE_RSS_LIMIT_GIB,
        aggregate_rss_limit_gib=STAGE_AGGREGATE_RSS_LIMIT_GIB,
        total_run_started=total_started,
    )

    eligible_snapshots: dict[str, dict[str, str]] = {}
    for phase in SNAPSHOT_PHASES:
        paths = _solver_paths(output_dir, phase.key)
        execution = solver_executions[phase.key]
        if execution.get("status") != "complete" or not paths["result"].is_file():
            continue
        validate_execution_artifacts(execution, paths)
        result = _load_json(paths["result"])
        if result.get("snapshot_eligible_for_certificate") is not True:
            continue
        solution_sha256 = _sha256(paths["solution"])
        execution_sha256 = _sha256(paths["execution"])
        validate_solver_snapshot(
            solution_path=paths["solution"],
            phase_execution_path=paths["execution"],
            phase=phase.key,
            expected_solution_sha256=solution_sha256,
            expected_phase_execution_sha256=execution_sha256,
            expected_lp_sha256=expected_lp_sha256,
            expected_num_col=FORMAL_PRESOLVED_LP["num_col"],
            expected_num_row=FORMAL_PRESOLVED_LP["num_row"],
        )
        eligible_snapshots[phase.key] = {
            "solution_sha256": solution_sha256,
            "solver_execution_sha256": execution_sha256,
        }

    certificate_processes = []
    for phase in SNAPSHOT_PHASES:
        if phase.key not in eligible_snapshots:
            continue
        solver_paths = _solver_paths(output_dir, phase.key)
        certificate_paths = _certificate_paths(output_dir, phase.key)
        snapshot = eligible_snapshots[phase.key]
        command = (
            sys.executable,
            "-u",
            "-m",
            "tes_bess_boundary.e0d45_hybrid_r0_strict_lower_bound",
            "_certificate-child",
            "--lp-archive",
            str(prepare_paths["archive"]),
            "--expected-lp-sha256",
            expected_lp_sha256,
            "--expected-lp-archive-sha256",
            expected_lp_archive_sha256,
            "--solution",
            str(solver_paths["solution"]),
            "--solver-execution",
            str(solver_paths["execution"]),
            "--expected-solution-sha256",
            snapshot["solution_sha256"],
            "--expected-solver-execution-sha256",
            snapshot["solver_execution_sha256"],
            "--phase",
            phase.key,
            "--output-dir",
            str(output_dir),
        )
        certificate_processes.append(
            StageProcess(
                phase.key,
                command,
                certificate_paths,
                CERTIFICATE_PHASE_HARD_WALL_SECONDS,
                expected_lp_sha256,
            )
        )
    certificate_executions = _run_parallel_stage(
        processes=certificate_processes,
        execution_schema_id=CERTIFICATE_EXECUTION_SCHEMA_ID,
        stage_name="certificate",
        stage_hard_wall_seconds=CERTIFICATE_STAGE_HARD_WALL_SECONDS,
        phase_rss_limit_gib=PHASE_TREE_RSS_LIMIT_GIB,
        aggregate_rss_limit_gib=STAGE_AGGREGATE_RSS_LIMIT_GIB,
        total_run_started=total_started,
    )

    phase_results: dict[str, dict[str, Any]] = {}
    phase_artifacts: dict[str, dict[str, str | None]] = {}
    for phase in SNAPSHOT_PHASES:
        solver_paths = _solver_paths(output_dir, phase.key)
        certificate_paths = _certificate_paths(output_dir, phase.key)
        certificate_execution = certificate_executions.get(phase.key)
        if (
            certificate_execution is not None
            and certificate_execution.get("status") == "complete"
            and certificate_paths["result"].is_file()
        ):
            validate_execution_artifacts(certificate_execution, certificate_paths)
            result = _load_json(certificate_paths["result"])
        else:
            result = {
                "schema_id": CERTIFICATE_RESULT_SCHEMA_ID,
                "phase": phase.key,
                "status": (
                    "snapshot_ineligible"
                    if phase.key not in eligible_snapshots
                    else "certificate_child_failed"
                ),
                "formal_lower_bound_eligible": False,
                "lower_bound_decimal": None,
            }
        phase_results[phase.key] = result
        phase_artifacts[phase.key] = {
            "solver_result_sha256": (
                _sha256(solver_paths["result"])
                if solver_paths["result"].is_file()
                else None
            ),
            "solver_execution_sha256": (
                _sha256(solver_paths["execution"])
                if solver_paths["execution"].is_file()
                else None
            ),
            "solution_sha256": (
                _sha256(solver_paths["solution"])
                if solver_paths["solution"].is_file()
                else None
            ),
            "certificate_result_sha256": (
                _sha256(certificate_paths["result"])
                if certificate_paths["result"].is_file()
                else None
            ),
            "certificate_execution_sha256": (
                _sha256(certificate_paths["execution"])
                if certificate_paths["execution"].is_file()
                else None
            ),
            "certificate_sha256": (
                _sha256(certificate_paths["certificate"])
                if certificate_paths["certificate"].is_file()
                else None
            ),
            "chunks_sha256": (
                _sha256(certificate_paths["chunks"])
                if certificate_paths["chunks"].is_file()
                else None
            ),
        }

    if perf_counter() - total_started >= TOTAL_HARD_WALL_SECONDS:
        raise RuntimeError("D45 total parent hard wall reached before manifest assembly")
    input_sha256 = {
        "structure_manifest": D42_STRUCTURE_MANIFEST_SHA256,
        "hybrid_r0_structure_case": D42_HYBRID_R0_CASE_SHA256,
        "d44_formal_manifest": D44_FORMAL_MANIFEST_SHA256,
        "d44_formal_execution": D44_FORMAL_EXECUTION_SHA256,
        "d45_gate_a_manifest": gate_a["manifest_sha256"],
        "prepare_result": _sha256(prepare_paths["result"]),
        "prepare_execution": _sha256(prepare_paths["execution"]),
        "lp_archive": expected_lp_archive_sha256,
        **structure_manifest["input_sha256"],
    }
    source_sha256 = {
        **locked_sources,
        Path(__file__).name: _sha256(Path(__file__)),
        d45_test_path.name: _sha256(d45_test_path),
    }
    manifest = assemble_manifest(
        phase_results=phase_results,
        phase_artifacts=phase_artifacts,
        input_sha256=input_sha256,
        source_sha256=source_sha256,
        gate_a_audit=gate_a,
    )
    manifest["prepare_identity_audit"] = prepare_audit
    manifest_path = output_dir / "manifest.json"
    d42_executor._atomic_write_json(manifest_path, manifest)
    execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": manifest["status"],
        "manifest_sha256": _sha256(manifest_path),
        "runtime_seconds": perf_counter() - total_started,
        "total_hard_wall_seconds": TOTAL_HARD_WALL_SECONDS,
        "prepare_execution_sha256": _sha256(prepare_paths["execution"]),
        "solver_phase_execution_sha256": {
            phase.key: _sha256(_solver_paths(output_dir, phase.key)["execution"])
            for phase in SNAPSHOT_PHASES
        },
        "certificate_phase_execution_sha256": {
            phase.key: (
                _sha256(_certificate_paths(output_dir, phase.key)["execution"])
                if _certificate_paths(output_dir, phase.key)["execution"].is_file()
                else None
            )
            for phase in SNAPSHOT_PHASES
        },
        "optimization_invoked": True,
        "native_solver_invoked": True,
        "technical_ranking_permitted": False,
    }
    execution_path = output_dir / "execution.json"
    d42_executor._atomic_write_json(execution_path, execution)
    _atomic_write_text(
        output_dir / "README.md",
        render_readme(manifest, manifest_sha256=_sha256(manifest_path)),
    )
    return {"manifest": manifest, "execution": execution}


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--structure-dir", type=Path, required=True)
    parser.add_argument("--service-path", type=Path, required=True)
    parser.add_argument("--d40-gate-a-manifest-path", type=Path, required=True)
    parser.add_argument("--d41-gate-a-manifest-path", type=Path, required=True)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("_prepare-child")
    _add_formal_inputs(prepare)
    solver = commands.add_parser("_solver-child")
    solver.add_argument("--lp-archive", type=Path, required=True)
    solver.add_argument("--expected-lp-sha256", required=True)
    solver.add_argument("--expected-lp-archive-sha256", required=True)
    solver.add_argument("--phase", choices=tuple(SNAPSHOT_BY_KEY), required=True)
    solver.add_argument("--output-dir", type=Path, required=True)
    certificate = commands.add_parser("_certificate-child")
    certificate.add_argument("--lp-archive", type=Path, required=True)
    certificate.add_argument("--expected-lp-sha256", required=True)
    certificate.add_argument("--expected-lp-archive-sha256", required=True)
    certificate.add_argument("--solution", type=Path, required=True)
    certificate.add_argument("--solver-execution", type=Path, required=True)
    certificate.add_argument("--expected-solution-sha256", required=True)
    certificate.add_argument("--expected-solver-execution-sha256", required=True)
    certificate.add_argument("--phase", choices=tuple(SNAPSHOT_BY_KEY), required=True)
    certificate.add_argument("--output-dir", type=Path, required=True)
    formal = commands.add_parser("formal")
    _add_formal_inputs(formal)
    formal.add_argument("--d44-formal-manifest-path", type=Path, required=True)
    formal.add_argument("--gate-a-manifest-path", type=Path, required=True)
    formal.add_argument("--d45-test-path", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "_prepare-child":
        d42_formal.prepare_formal_case_child(
            "hybrid_r0",
            structure_dir=args.structure_dir,
            service_path=args.service_path,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest_path,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_dir=args.output_dir,
        )
    elif args.command == "_solver-child":
        run_solver_snapshot_child(
            lp_archive_path=args.lp_archive,
            expected_lp_sha256=args.expected_lp_sha256,
            expected_lp_archive_sha256=args.expected_lp_archive_sha256,
            phase=args.phase,
            output_dir=args.output_dir,
        )
    elif args.command == "_certificate-child":
        run_certificate_child(
            lp_archive_path=args.lp_archive,
            expected_lp_sha256=args.expected_lp_sha256,
            expected_lp_archive_sha256=args.expected_lp_archive_sha256,
            solution_path=args.solution,
            solver_execution_path=args.solver_execution,
            expected_solution_sha256=args.expected_solution_sha256,
            expected_solver_execution_sha256=args.expected_solver_execution_sha256,
            phase=args.phase,
            output_dir=args.output_dir,
        )
    else:
        run_formal(
            structure_dir=args.structure_dir,
            service_path=args.service_path,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest_path,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            d44_formal_manifest_path=args.d44_formal_manifest_path,
            gate_a_manifest_path=args.gate_a_manifest_path,
            d45_test_path=args.d45_test_path,
            output_dir=args.output_dir,
        )


if __name__ == "__main__":
    main()
