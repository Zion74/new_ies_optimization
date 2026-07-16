"""Gate A compiler and BESS-only monitored executor for formal E0-D-50."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    FORMAL_HEAT_SHA256,
    LEGACY_VRE_SHA256,
    PRICE_BASIS_TREE_SHA256,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    GATE_A_MANIFEST_SHA256 as D40_GATE_A_MANIFEST_SHA256,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    SERVICE_SHA256 as D40_SERVICE_SHA256,
)

from tes_bess_boundary.e0d41_gate_b_lower_bound import (
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _terminate_process_group,
)
from tes_bess_boundary.e0d46_monitored_executor import (
    AGGREGATE_RSS_LIMIT_GIB,
    HOST_MEMORY_RESERVE_GIB,
    MONITOR_INTERVAL_SECONDS,
    PROCESS_TREE_RSS_LIMIT_GIB,
    _process_group_active,
    _terminate_residual_process_group,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    D41_GATE_A_MANIFEST_SHA256,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    D46_FORMAL_MANIFEST_SHA256,
    D46_POSTMORTEM_BUNDLE_SHA256,
)
from tes_bess_boundary.e0d48_monitored_executor import _parse_junit
from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
    BUILD_SCHEMA_ID,
    CANDIDATE_TOTAL_HARD_WALL_SECONDS,
    CLAIM_SCOPE,
    D50_BESS_R1_GUIDE_SHA256,
    EXPECTED_FORMAL_STAGE_COUNT,
    FORMAL_PROJECT_TAC_READY,
    FORMAL_THREADS,
    REPAIR_HARD_WALL_SECONDS,
    STAGE_HARD_WALL_SECONDS,
    STAGE_SOFT_TIME_LIMIT_SECONDS,
    TECHNICAL_RANKING_PERMITTED,
    TOTAL_HARD_WALL_SECONDS,
    _code_hashes,
    _sha256,
    _tree_sha256,
)
from tes_bess_boundary.model import Architecture


EXECUTION_SCHEMA_ID = "tes_bess_boundary.e0d50_stage_execution.v1"
ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d50_architecture_manifest.v1"
FORMAL_SCHEMA_ID = "tes_bess_boundary.e0d50_formal_manifest.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d50_gate_a_manifest.v1"

FORMAL_ARCHITECTURE = Architecture.BESS
HEARTBEAT_INTERVAL_SECONDS = 30.0
D48_R1_FORMAL_MANIFEST_SHA256 = (
    "ca0248805ce72d1b25dd69a0cf20c5c68dee8b60a5d0a2d575a192f3e8455165"
)
D49_FORMAL_MANIFEST_SHA256 = (
    "0d66f06defcc8ecabe247bc7eb38c3f9e7f457d41dac82927295f54b0ad62a14"
)


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


def _stage_paths(output_dir: Path, stage: str) -> dict[str, Path]:
    prefix = f"bess_{stage}"
    return {
        "result": output_dir / f"{prefix}.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solver_log": output_dir / f"{prefix}.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.jsonl",
        "progress": output_dir / f"{prefix}_progress.jsonl",
        "stage_dir": output_dir / "bess_candidate_stages",
        "physical_snapshot": output_dir / "bess_physical_snapshot.json",
        "candidate": output_dir / "bess_candidate.csv.gz",
        "solution": output_dir / "bess_solution.csv.gz",
    }


def _common_command(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> list[str]:
    return [
        "--service",
        str(service_path),
        "--d40-gate-a",
        str(d40_gate_a_manifest_path),
        "--d41-gate-a",
        str(d41_gate_a_manifest_path),
        "--heat",
        str(heat_path),
        "--vre",
        str(vre_path),
        "--price-basis",
        str(price_basis_path),
    ]


def build_stage_command(
    *,
    stage: str,
    output_dir: Path,
    guide_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> tuple[list[str], tuple[Path, ...]]:
    paths = _stage_paths(output_dir, stage)
    common = _common_command(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    base = [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix",
    ]
    if stage == "candidate":
        return (
            [
                *base,
                "candidate",
                *common,
                "--guide",
                str(guide_path),
                "--stage-output-dir",
                str(paths["stage_dir"]),
                "--progress-output",
                str(paths["progress"]),
                "--physical-snapshot-output",
                str(paths["physical_snapshot"]),
                "--candidate-output",
                str(paths["candidate"]),
                "--result-output",
                str(paths["result"]),
                "--threads",
                str(FORMAL_THREADS),
                "--stage-time-limit",
                str(STAGE_SOFT_TIME_LIMIT_SECONDS),
            ],
            (
                paths["result"],
                paths["progress"],
                paths["physical_snapshot"],
                paths["candidate"],
            ),
        )
    if stage == "repair":
        return (
            [
                *base,
                "repair",
                *common,
                "--candidate",
                str(paths["candidate"]),
                "--solution-output",
                str(paths["solution"]),
                "--result-output",
                str(paths["result"]),
                "--threads",
                str(FORMAL_THREADS),
                "--time-limit",
                str(REPAIR_HARD_WALL_SECONDS),
            ],
            (paths["result"], paths["solution"]),
        )
    raise ValueError(f"unknown D50 stage: {stage}")


def _latest_progress(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _candidate_stage_stop_reason(
    latest: Mapping[str, Any] | None,
    *,
    now_unix: float,
) -> str | None:
    if latest is None or latest.get("event") != "stage_started":
        return None
    started = latest.get("unix_time")
    if not isinstance(started, (int, float)) or not math.isfinite(float(started)):
        return "invalid_stage_progress_clock"
    if now_unix - float(started) >= STAGE_HARD_WALL_SECONDS:
        return "stage_hard_wall"
    return None


def _resource_stop_reason(
    *,
    elapsed_seconds: float,
    hard_wall_seconds: float,
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    """Apply the D50 35-GiB warning / 45-GiB stop interpretation."""

    if elapsed_seconds >= hard_wall_seconds:
        return "hard_wall"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB:
        return "aggregate_rss_stop"
    if (
        available_memory_gib is not None
        and available_memory_gib < HOST_MEMORY_RESERVE_GIB
    ):
        return "host_memory_reserve_stop"
    return None


def run_monitored_stage(
    *,
    stage: str,
    output_dir: Path,
    hard_wall_seconds: float,
    guide_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Run one candidate or repair child under total and per-stage gates."""

    if not math.isfinite(hard_wall_seconds) or hard_wall_seconds <= 0.0:
        raise ValueError("D50 stage hard wall must be finite and positive")
    paths = _stage_paths(output_dir, stage)
    command, declared_artifacts = build_stage_command(
        stage=stage,
        output_dir=output_dir,
        guide_path=guide_path,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        paths["execution"],
        paths["solver_log"],
        paths["heartbeat"],
        *declared_artifacts,
    ):
        if path.exists():
            raise FileExistsError(f"D50 refuses to overwrite {path}")
    if stage == "candidate" and paths["stage_dir"].exists():
        raise FileExistsError(f"D50 refuses to overwrite {paths['stage_dir']}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D50 formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D50 host memory is below the frozen reserve")

    started_payload = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": "child_starting",
        "architecture": FORMAL_ARCHITECTURE.value,
        "stage": stage,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "hard_wall_enforced_by_parent": True,
        "per_block_stage_hard_wall_enforced_by_parent": stage == "candidate",
        "resource_thresholds": {
            "hard_wall_seconds": hard_wall_seconds,
            "block_stage_hard_wall_seconds": (
                STAGE_HARD_WALL_SECONDS if stage == "candidate" else None
            ),
            "process_tree_rss_warning_gib": PROCESS_TREE_RSS_LIMIT_GIB,
            "aggregate_rss_stop_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        },
    }
    _write_json(paths["execution"], started_payload)
    environment = os.environ.copy()
    environment.update(
        {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    )
    peak_child_tree = 0.0
    peak_aggregate = 0.0
    minimum_available = available_before
    rss_samples = 0
    memory_samples = 0
    stop_reason: str | None = None
    termination_signal: str | None = None
    latest_progress: dict[str, Any] | None = None
    process_tree_warning_triggered = False
    started = perf_counter()
    last_heartbeat = -HEARTBEAT_INTERVAL_SECONDS
    with (
        paths["solver_log"].open("w", encoding="utf-8", newline="\n") as solver_log,
        paths["heartbeat"].open(
            "w", encoding="utf-8", newline="\n", buffering=1
        ) as heartbeat_log,
    ):
        process = subprocess.Popen(
            command,
            stdout=solver_log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
            env=environment,
        )
        while process.poll() is None:
            elapsed = perf_counter() - started
            child_tree = _process_tree_rss_gib(process.pid)
            parent_rss = _process_rss_gib(os.getpid())
            available = _available_memory_gib()
            aggregate = (
                child_tree + parent_rss
                if child_tree is not None and parent_rss is not None
                else None
            )
            if child_tree is not None:
                peak_child_tree = max(peak_child_tree, child_tree)
                process_tree_warning_triggered = (
                    process_tree_warning_triggered
                    or child_tree >= PROCESS_TREE_RSS_LIMIT_GIB
                )
                rss_samples += 1
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            if stage == "candidate":
                latest_progress = _latest_progress(paths["progress"])
            if elapsed - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                heartbeat_log.write(
                    json.dumps(
                        {
                            "architecture": FORMAL_ARCHITECTURE.value,
                            "stage": stage,
                            "pid": process.pid,
                            "elapsed_seconds": elapsed,
                            "child_process_tree_rss_gib": child_tree,
                            "parent_child_aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                            "block_progress": latest_progress,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                heartbeat_log.flush()
                last_heartbeat = elapsed
            stop_reason = _resource_stop_reason(
                elapsed_seconds=elapsed,
                hard_wall_seconds=hard_wall_seconds,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
            )
            if stop_reason is None and stage == "candidate":
                stop_reason = _candidate_stage_stop_reason(
                    latest_progress,
                    now_unix=time.time(),
                )
            if stop_reason is not None:
                termination_signal = _terminate_process_group(process)
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.wait()
    residual_termination_signal = _terminate_residual_process_group(process.pid)
    runtime = perf_counter() - started
    result_payload = (
        json.loads(paths["result"].read_text(encoding="utf-8"))
        if paths["result"].is_file()
        else None
    )
    residual_process_group_active = _process_group_active(process.pid)
    resource_gate_passed = all(
        (
            stop_reason is None,
            rss_samples > 0,
            memory_samples > 0,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
            not residual_process_group_active,
        )
    )
    complete = return_code == 0 and result_payload is not None and resource_gate_passed
    stage_artifacts = (
        {
            str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
            for path in sorted(paths["stage_dir"].rglob("*"))
            if path.is_file()
        }
        if paths["stage_dir"].is_dir()
        else {}
    )
    execution = {
        **started_payload,
        "status": "complete" if complete else "resource_or_process_failure",
        "return_code": return_code,
        "runtime_seconds": runtime,
        "peak_child_process_tree_rss_gib": peak_child_tree,
        "process_tree_rss_warning_triggered": process_tree_warning_triggered,
        "peak_parent_child_aggregate_rss_gib": peak_aggregate,
        "minimum_available_memory_gib": minimum_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "stop_reason": stop_reason,
        "termination_signal": termination_signal,
        "residual_termination_signal": residual_termination_signal,
        "resource_gate_passed": resource_gate_passed,
        "last_block_progress": latest_progress,
        "result_sha256": _sha256(paths["result"]) if paths["result"].is_file() else None,
        "solver_log_sha256": _sha256(paths["solver_log"]),
        "heartbeat_sha256": _sha256(paths["heartbeat"]),
        "declared_artifact_sha256": {
            path.name: _sha256(path) if path.is_file() else None
            for path in declared_artifacts
        },
        "block_stage_artifact_sha256": stage_artifacts,
        "active_residual_process_count": int(residual_process_group_active),
    }
    _write_json(paths["execution"], execution)
    return execution


def _load_completed_result(output_dir: Path, stage: str) -> dict[str, Any] | None:
    paths = _stage_paths(output_dir, stage)
    if not paths["result"].is_file() or not paths["execution"].is_file():
        return None
    execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
    if execution.get("status") != "complete":
        return None
    if execution.get("result_sha256") != _sha256(paths["result"]):
        raise ValueError(f"D50 BESS {stage} result hash mismatch")
    return json.loads(paths["result"].read_text(encoding="utf-8"))


def run_bess_method_gate(
    *,
    output_dir: Path,
    guide_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Run the one frozen 53-stage candidate child and optional clean repair."""

    started = perf_counter()
    executions: dict[str, Any] = {}
    executions["candidate"] = run_monitored_stage(
        stage="candidate",
        output_dir=output_dir,
        hard_wall_seconds=CANDIDATE_TOTAL_HARD_WALL_SECONDS,
        guide_path=guide_path,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    candidate = _load_completed_result(output_dir, "candidate")
    if candidate is not None and candidate.get("status") == (
        "candidate_incumbent_captured_and_exactly_lifted"
    ):
        executions["repair"] = run_monitored_stage(
            stage="repair",
            output_dir=output_dir,
            hard_wall_seconds=REPAIR_HARD_WALL_SECONDS,
            guide_path=guide_path,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
    repair = _load_completed_result(output_dir, "repair")
    candidate_execution = executions["candidate"]
    if repair is not None and repair.get("status") == (
        "audited_feasible_upper_bound_recovered"
    ):
        status = "audited_feasible_upper_bound_recovered"
    elif candidate is not None and candidate.get("status") == "final_exact_lift_failed":
        status = "final_exact_lift_failed"
    elif candidate is not None and candidate.get("status") == "block_path_no_incumbent":
        status = "block_path_no_incumbent"
    elif candidate is not None and candidate.get("status") != (
        "candidate_incumbent_captured_and_exactly_lifted"
    ):
        status = "no_primal_status_closure"
    elif candidate is not None:
        status = "fixed_binary_repair_failed"
    elif candidate_execution.get("stop_reason") == "stage_hard_wall":
        status = "block_path_no_incumbent"
    else:
        status = "no_primal_status_closure"
    payload = {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "status": status,
        "architecture": FORMAL_ARCHITECTURE.value,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "runtime_seconds": perf_counter() - started,
        "guide_sha256": _sha256(guide_path),
        "stage_execution": executions,
        "candidate_status": candidate.get("status") if candidate else None,
        "repair_status": repair.get("status") if repair else None,
        "failed_block_stage_index": (
            candidate.get("failed_stage_index")
            if candidate
            else candidate_execution.get("last_block_progress", {}).get("stage_index")
        ),
        "audited_feasible_upper_bound_cny": (
            repair.get("solution_audit", {}).get("audited_feasible_upper_bound_cny")
            if repair
            else None
        ),
    }
    _write_json(output_dir / "bess_manifest.json", payload)
    return payload


def _validate_d50_predecessors(
    d48_r1_formal_manifest_path: Path,
    d49_formal_manifest_path: Path,
) -> dict[str, str]:
    hashes = {
        "d48_r1_formal_manifest": _sha256(d48_r1_formal_manifest_path),
        "d49_formal_manifest": _sha256(d49_formal_manifest_path),
    }
    expected = {
        "d48_r1_formal_manifest": D48_R1_FORMAL_MANIFEST_SHA256,
        "d49_formal_manifest": D49_FORMAL_MANIFEST_SHA256,
    }
    if hashes != expected:
        raise ValueError("D50 predecessor manifest hash mismatch")
    return hashes


def _validate_d50_formal_inputs(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    """Validate the frozen D50 inputs, including the D41 BESS R1 guide."""

    expected = {
        "service": (service_path, D40_SERVICE_SHA256),
        "d40_gate_a": (d40_gate_a_manifest_path, D40_GATE_A_MANIFEST_SHA256),
        "d41_gate_a": (d41_gate_a_manifest_path, D41_GATE_A_MANIFEST_SHA256),
        "d46_formal_manifest": (d46_formal_manifest_path, D46_FORMAL_MANIFEST_SHA256),
        "d46_postmortem_bundle": (
            d46_postmortem_bundle_path,
            D46_POSTMORTEM_BUNDLE_SHA256,
        ),
        "d41_bess_r1_guide": (guide_path, D50_BESS_R1_GUIDE_SHA256),
        "heat": (heat_path, FORMAL_HEAT_SHA256),
        "vre": (vre_path, LEGACY_VRE_SHA256),
    }
    actual: dict[str, str] = {}
    for name, (path, expected_hash) in expected.items():
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"D50 formal {name} hash mismatch")
        actual[name] = actual_hash
    price_hash = _tree_sha256(price_basis_path)
    if price_hash != PRICE_BASIS_TREE_SHA256:
        raise ValueError("D50 formal price-basis tree hash mismatch")
    actual["price_basis_tree"] = price_hash
    return actual


def compile_gate_a_manifest(
    *,
    output_dir: Path,
    build_path: Path,
    targeted_junit_path: Path,
    compatibility_junit_path: Path,
    full_junit_path: Path,
    ruff_log_path: Path,
    pycompile_log_path: Path,
    git_commit: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    d48_r1_formal_manifest_path: Path,
    d49_formal_manifest_path: Path,
    guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Compile D50 Gate A evidence without invoking the formal-year optimizer."""

    if output_dir.exists():
        raise FileExistsError(f"D50 Gate A output already exists: {output_dir}")
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise ValueError("D50 Gate A requires a full lowercase Git commit")
    started = perf_counter()
    formal_inputs = _validate_d50_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_path=guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    predecessor_hashes = _validate_d50_predecessors(
        d48_r1_formal_manifest_path,
        d49_formal_manifest_path,
    )
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build.get("schema_id") != BUILD_SCHEMA_ID:
        raise ValueError("D50 Gate A build schema mismatch")
    if build.get("status") != "gate_a_build_passed":
        raise ValueError("D50 Gate A build failed")
    if build.get("solver_invoked") is not False:
        raise ValueError("D50 Gate A build invoked a solver")
    if build.get("formal_optimization_invoked") is not False:
        raise ValueError("D50 Gate A invoked formal optimize")
    if build.get("audit", {}).get("passed") is not True:
        raise ValueError("D50 Gate A build audit failed")
    preparation = build["d50_preparation_audit"]
    if preparation["commit_block_coverage_audit"]["stage_count"] != (
        EXPECTED_FORMAL_STAGE_COUNT
    ):
        raise ValueError("D50 Gate A did not prove all 53 stages")
    tests = {
        "d50_targeted": _parse_junit(targeted_junit_path, no_skips=True),
        "d40_d50_compatibility": _parse_junit(compatibility_junit_path, no_skips=True),
        "full_package": _parse_junit(full_junit_path, no_skips=True),
    }
    if not all(item["passed"] for item in tests.values()):
        raise ValueError("D50 Gate A test evidence failed")
    quality = {
        "ruff": {
            "sentinel_present": "D50_RUFF_PASSED"
            in ruff_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(ruff_log_path),
        },
        "pycompile": {
            "sentinel_present": "D50_PYCOMPILE_PASSED"
            in pycompile_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(pycompile_log_path),
        },
    }
    if not all(item["sentinel_present"] for item in quality.values()):
        raise ValueError("D50 Gate A quality sentinel is missing")
    package = Path(__file__).resolve().parent
    tests_dir = package.parent.parent / "tests"
    payload = {
        "schema_id": GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "formal_optimization_invoked": False,
        "formal_run_permitted": True,
        "formal_architecture_order": [FORMAL_ARCHITECTURE.value],
        "tes_or_hybrid_formal_run_permitted": False,
        "formal_input_sha256": formal_inputs,
        "predecessor_manifest_sha256": predecessor_hashes,
        "build_audit_sha256": _sha256(build_path),
        "commit_block_coverage_audit": preparation[
            "commit_block_coverage_audit"
        ],
        "selected_stage_domain_audit": build["selected_stage_domain_audit"],
        "test_evidence": tests,
        "quality_evidence": quality,
        "provenance": {
            "git_commit": git_commit,
            "code_sha256": _code_hashes(),
            "test_sha256": {
                name: _sha256(tests_dir / name)
                for name in (
                    "test_e0d50_full_year_coupled_physical_block_relax_and_fix.py",
                    "test_e0d50_monitored_executor.py",
                )
            },
        },
        "audit": {"passed": True},
    }
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "gate_a_manifest.json"
    _write_json(manifest_path, payload)
    _write_json(
        output_dir / "gate_a_execution.json",
        {
            "schema_id": f"{GATE_A_SCHEMA_ID}.execution",
            "status": "complete",
            "runtime_seconds": perf_counter() - started,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "manifest_sha256": _sha256(manifest_path),
        },
    )
    return payload


def _validate_gate_a(manifest_path: Path, execution_path: Path) -> dict[str, Any]:
    manifest_hash = _sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D50 Gate A schema mismatch")
    if manifest.get("status") != "gate_a_passed":
        raise ValueError("D50 formal run requires a passed Gate A")
    if manifest.get("formal_optimization_invoked") is not False:
        raise ValueError("D50 Gate A unexpectedly invoked formal optimization")
    if manifest.get("formal_architecture_order") != [FORMAL_ARCHITECTURE.value]:
        raise ValueError("D50 Gate A did not authorize BESS-only execution")
    if manifest.get("tes_or_hybrid_formal_run_permitted") is not False:
        raise ValueError("D50 Gate A improperly authorized TES/Hybrid")
    if manifest.get("formal_run_permitted") is not True:
        raise ValueError("D50 Gate A did not permit the formal run")
    if manifest.get("audit", {}).get("passed") is not True:
        raise ValueError("D50 Gate A audit is not passed")
    if execution.get("status") != "complete":
        raise ValueError("D50 Gate A execution is incomplete")
    if execution.get("manifest_sha256") != manifest_hash:
        raise ValueError("D50 Gate A execution hash mismatch")
    if manifest.get("provenance", {}).get("code_sha256") != _code_hashes():
        raise ValueError("D50 formal source differs from Gate A")
    return {
        "manifest_sha256": manifest_hash,
        "execution_sha256": _sha256(execution_path),
        "git_commit": manifest.get("provenance", {}).get("git_commit"),
        "passed": True,
    }


def run_formal_bess_gate(
    *,
    output_dir: Path,
    gate_a_manifest_path: Path,
    gate_a_execution_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    d48_r1_formal_manifest_path: Path,
    d49_formal_manifest_path: Path,
    guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Run the only pre-registered D50 formal gate: BESS once."""

    if output_dir.exists():
        raise FileExistsError(f"D50 formal output already exists: {output_dir}")
    gate_a = _validate_gate_a(gate_a_manifest_path, gate_a_execution_path)
    formal_inputs = _validate_d50_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_path=guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    predecessor_hashes = _validate_d50_predecessors(
        d48_r1_formal_manifest_path,
        d49_formal_manifest_path,
    )
    available = _available_memory_gib()
    if available is None or available < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D50 formal host does not satisfy the memory reserve")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    bess = run_bess_method_gate(
        output_dir=output_dir,
        guide_path=guide_path,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    artifact_hashes = {
        str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "formal_manifest.json"
    }
    payload = {
        "schema_id": FORMAL_SCHEMA_ID,
        "status": bess["status"],
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "architecture_order": [FORMAL_ARCHITECTURE.value],
        "successful_architecture_count": int(
            bess["status"] == "audited_feasible_upper_bound_recovered"
        ),
        "runtime_seconds": perf_counter() - started,
        "gate_a": gate_a,
        "formal_input_sha256": formal_inputs,
        "predecessor_manifest_sha256": predecessor_hashes,
        "architecture": {FORMAL_ARCHITECTURE.value: bess},
        "tes_or_hybrid_executed": False,
        "resource_contract": {
            "threads_per_stage": FORMAL_THREADS,
            "block_stage_count": EXPECTED_FORMAL_STAGE_COUNT,
            "block_stage_soft_time_limit_seconds": STAGE_SOFT_TIME_LIMIT_SECONDS,
            "block_stage_hard_wall_seconds": STAGE_HARD_WALL_SECONDS,
            "candidate_total_hard_wall_seconds": CANDIDATE_TOTAL_HARD_WALL_SECONDS,
            "repair_hard_wall_seconds": REPAIR_HARD_WALL_SECONDS,
            "total_hard_wall_seconds": TOTAL_HARD_WALL_SECONDS,
            "process_tree_rss_warning_gib": PROCESS_TREE_RSS_LIMIT_GIB,
            "aggregate_rss_stop_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        },
        "provenance": {"code_sha256": _code_hashes()},
        "artifact_sha256": artifact_hashes,
        "engineering_numerical_feasibility_only": True,
        "rational_exact_feasibility_certificate": False,
    }
    _write_json(output_dir / "formal_manifest.json", payload)
    return payload


def _add_shared_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--d46-formal-manifest", type=Path, required=True)
    parser.add_argument("--d46-postmortem-bundle", type=Path, required=True)
    parser.add_argument("--d48-r1-formal-manifest", type=Path, required=True)
    parser.add_argument("--d49-formal-manifest", type=Path, required=True)
    parser.add_argument("--bess-guide", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gate_a = commands.add_parser("gate-a-compile")
    gate_a.add_argument("--output-dir", type=Path, required=True)
    gate_a.add_argument("--build", type=Path, required=True)
    gate_a.add_argument("--targeted-junit", type=Path, required=True)
    gate_a.add_argument("--compatibility-junit", type=Path, required=True)
    gate_a.add_argument("--full-junit", type=Path, required=True)
    gate_a.add_argument("--ruff-log", type=Path, required=True)
    gate_a.add_argument("--pycompile-log", type=Path, required=True)
    gate_a.add_argument("--git-commit", required=True)
    _add_shared_inputs(gate_a)
    formal = commands.add_parser("formal-bess")
    formal.add_argument("--output-dir", type=Path, required=True)
    formal.add_argument("--gate-a-manifest", type=Path, required=True)
    formal.add_argument("--gate-a-execution", type=Path, required=True)
    _add_shared_inputs(formal)
    return parser


def _shared_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "service_path": args.service,
        "d40_gate_a_manifest_path": args.d40_gate_a,
        "d41_gate_a_manifest_path": args.d41_gate_a,
        "d46_formal_manifest_path": args.d46_formal_manifest,
        "d46_postmortem_bundle_path": args.d46_postmortem_bundle,
        "d48_r1_formal_manifest_path": args.d48_r1_formal_manifest,
        "d49_formal_manifest_path": args.d49_formal_manifest,
        "guide_path": args.bess_guide,
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "gate-a-compile":
        compile_gate_a_manifest(
            output_dir=args.output_dir,
            build_path=args.build,
            targeted_junit_path=args.targeted_junit,
            compatibility_junit_path=args.compatibility_junit,
            full_junit_path=args.full_junit,
            ruff_log_path=args.ruff_log,
            pycompile_log_path=args.pycompile_log,
            git_commit=args.git_commit,
            **_shared_kwargs(args),
        )
        return
    if args.command == "formal-bess":
        run_formal_bess_gate(
            output_dir=args.output_dir,
            gate_a_manifest_path=args.gate_a_manifest,
            gate_a_execution_path=args.gate_a_execution,
            **_shared_kwargs(args),
        )
        return
    raise AssertionError(f"unhandled D50 executor command: {args.command}")


if __name__ == "__main__":
    main()
