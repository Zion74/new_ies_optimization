"""Gate A compiler and BESS-only monitored executor for formal E0-D-52."""

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
from xml.etree import ElementTree
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d41_gate_b_lower_bound import (
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _terminate_process_group,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    TECHNICAL_RANKING_PERMITTED,
    _sha256,
    fix_engineering_capacity_anchor,
    solve_continuous_guide,
)
from tes_bess_boundary.e0d46_monitored_executor import (
    MONITOR_INTERVAL_SECONDS,
    _process_group_active,
    _terminate_residual_process_group,
)
from tes_bess_boundary.e0d48_monitored_executor import _parse_junit
from tes_bess_boundary.e0d50_monitored_executor import (
    _validate_d50_formal_inputs,
)
from tes_bess_boundary.e0d51_checkpointed_bounded_backtracking import (
    capture_first_feasibility_incumbent,
    read_attempt_checkpoint,
    replay_attempt_checkpoint,
)
from tes_bess_boundary.e0d51_gate0_evidence import build_gate0_24h_case
from tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery import (
    AGGREGATE_RSS_STOP_GIB,
    BUILD_SCHEMA_ID,
    CANDIDATE_TOTAL_HARD_WALL_SECONDS,
    CLEAN_REBUILD_HARD_WALL_SECONDS,
    COMMIT_HOURS,
    D50_FORMAL_MANIFEST_SHA256,
    D51_GATE0_MANIFEST_SHA256,
    D52_CONTRACT_COMMIT,
    DEMONSTRATION_SCHEMA_ID,
    HEARTBEAT_INTERVAL_SECONDS,
    HOST_MEMORY_RESERVE_GIB,
    MAX_ATTEMPTS_PER_STAGE,
    MAX_SOLVER_ATTEMPTS,
    MAX_TOTAL_ROLLBACK_EVENTS,
    PROCESS_TREE_RSS_WARNING_GIB,
    REPAIR_HARD_WALL_SECONDS,
    STAGE_HARD_WALL_SECONDS,
    STAGE_SOFT_TIME_LIMIT_SECONDS,
    TOTAL_HARD_WALL_SECONDS,
    CleanModelBundle,
    _code_hashes,
    d51_core_identity_audit,
    solve_checkpointed_bounded_backtracking_candidate,
    solve_d52_original_cost_repair,
)
from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
    EXPECTED_FORMAL_STAGE_COUNT,
    FORMAL_THREADS,
    make_stage_domain_plan,
    prepare_d50_model,
)
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.planning_model import build_endogenous_capacity_model


EXECUTION_SCHEMA_ID = "tes_bess_boundary.e0d52_stage_execution.v1"
ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d52_architecture_manifest.v1"
FORMAL_SCHEMA_ID = "tes_bess_boundary.e0d52_formal_manifest.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d52_gate_a_manifest.v1"
FORMAL_ARCHITECTURE = Architecture.BESS
GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FORMAL_PROCESS_PATTERN = re.compile(r"tes_bess_boundary\.e0d(?:4\d|5[0-2])")


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _git_head() -> str:
    package_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        ["git", "-C", str(package_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError("D52 could not resolve a full lowercase Git commit")
    return commit


def _parse_gate_a_junit(path: Path) -> dict[str, Any]:
    """Parse JUnit evidence and independently reject every skipped testcase."""

    result = _parse_junit(path, no_skips=True)
    root = ElementTree.parse(path).getroot()
    explicit_skips = len(root.findall(".//skipped"))
    if explicit_skips > result["skipped"]:
        result["skipped"] = explicit_skips
        result["passed"] = False
    return result


def _write_json(path: Path, payload: Mapping[str, Any], *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"D52 refuses to overwrite {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(_canonical_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stage_paths(output_dir: Path, stage: str) -> dict[str, Path]:
    prefix = f"bess_{stage}"
    return {
        "result": output_dir / f"{prefix}.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solver_log": output_dir / f"{prefix}.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.jsonl",
        "progress": output_dir / "bess_candidate_progress.jsonl",
        "checkpoint_dir": output_dir / "bess_candidate_checkpoints",
        "attempt_result_dir": output_dir / "bess_candidate_attempt_results",
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
        "tes_bess_boundary.e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery",
    ]
    if stage == "candidate":
        return (
            [
                *base,
                "candidate",
                *common,
                "--guide",
                str(guide_path),
                "--checkpoint-dir",
                str(paths["checkpoint_dir"]),
                "--attempt-result-dir",
                str(paths["attempt_result_dir"]),
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
    raise ValueError(f"unknown D52 stage: {stage}")


def _latest_progress(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _candidate_local_stop_reason(
    latest: Mapping[str, Any] | None,
    *,
    now_unix: float,
) -> str | None:
    if latest is None:
        return None
    event = latest.get("event")
    started = latest.get("unix_time")
    if event not in {"attempt_started", "clean_rebuild_started"}:
        return None
    if not isinstance(started, (int, float)) or not math.isfinite(float(started)):
        return "invalid_progress_clock"
    limit = (
        STAGE_HARD_WALL_SECONDS
        if event == "attempt_started"
        else CLEAN_REBUILD_HARD_WALL_SECONDS
    )
    if now_unix - float(started) >= limit:
        return "attempt_hard_wall" if event == "attempt_started" else "clean_rebuild_hard_wall"
    return None


def _resource_stop_reason(
    *,
    elapsed_seconds: float,
    hard_wall_seconds: float,
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    if elapsed_seconds >= hard_wall_seconds:
        return "hard_wall"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_STOP_GIB:
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
    """Run a candidate or repair child with frozen resource and local gates."""

    if not math.isfinite(hard_wall_seconds) or hard_wall_seconds <= 0.0:
        raise ValueError("D52 stage hard wall must be finite and positive")
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
            raise FileExistsError(f"D52 refuses to overwrite {path}")
    if stage == "candidate" and (
        paths["checkpoint_dir"].exists() or paths["attempt_result_dir"].exists()
    ):
        raise FileExistsError("D52 candidate artifact directories already exist")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D52 formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D52 host memory is below the frozen reserve")
    started_payload = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": "child_starting",
        "architecture": FORMAL_ARCHITECTURE.value,
        "stage": stage,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "hard_wall_enforced_by_parent": True,
        "resource_thresholds": {
            "hard_wall_seconds": hard_wall_seconds,
            "attempt_hard_wall_seconds": (
                STAGE_HARD_WALL_SECONDS if stage == "candidate" else None
            ),
            "clean_rebuild_hard_wall_seconds": (
                CLEAN_REBUILD_HARD_WALL_SECONDS if stage == "candidate" else None
            ),
            "process_tree_rss_warning_gib": PROCESS_TREE_RSS_WARNING_GIB,
            "aggregate_rss_stop_gib": AGGREGATE_RSS_STOP_GIB,
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
        paths["heartbeat"].open("w", encoding="utf-8", newline="\n", buffering=1)
        as heartbeat_log,
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
                    or child_tree >= PROCESS_TREE_RSS_WARNING_GIB
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
                            "progress": latest_progress,
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
                stop_reason = _candidate_local_stop_reason(
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
    residual_active = _process_group_active(process.pid)
    resource_gate_passed = all(
        (
            stop_reason is None,
            rss_samples > 0,
            memory_samples > 0,
            peak_aggregate < AGGREGATE_RSS_STOP_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
            not residual_active,
        )
    )
    complete = return_code == 0 and result_payload is not None and resource_gate_passed
    recursive_artifacts: dict[str, str] = {}
    for directory in (paths["checkpoint_dir"], paths["attempt_result_dir"]):
        if directory.is_dir():
            recursive_artifacts.update(
                {
                    str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
                    for path in sorted(directory.rglob("*"))
                    if path.is_file()
                }
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
        "last_progress": latest_progress,
        "result_sha256": _sha256(paths["result"]) if paths["result"].is_file() else None,
        "solver_log_sha256": _sha256(paths["solver_log"]),
        "heartbeat_sha256": _sha256(paths["heartbeat"]),
        "declared_artifact_sha256": {
            path.name: _sha256(path) if path.is_file() else None
            for path in declared_artifacts
        },
        "recursive_attempt_artifact_sha256": recursive_artifacts,
        "active_residual_process_count": int(residual_active),
    }
    _write_json(paths["execution"], execution, overwrite=True)
    return execution


def _load_completed_result(output_dir: Path, stage: str) -> dict[str, Any] | None:
    paths = _stage_paths(output_dir, stage)
    if not paths["result"].is_file() or not paths["execution"].is_file():
        return None
    execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
    if execution.get("status") != "complete":
        return None
    if execution.get("result_sha256") != _sha256(paths["result"]):
        raise ValueError(f"D52 BESS {stage} result hash mismatch")
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
    if repair is not None and repair.get("status") == "audited_feasible_upper_bound_recovered":
        status = "audited_feasible_upper_bound_recovered"
    elif candidate is not None and candidate.get("status") == "closed_no_checkpointed_path":
        status = "closed_no_checkpointed_path"
    elif candidate is not None and candidate.get("status") == "final_exact_lift_failed":
        status = "final_exact_lift_failed"
    elif candidate is not None and candidate.get("status") == (
        "checkpoint_integrity_failure"
    ):
        status = "checkpoint_integrity_failure"
    elif candidate is not None and candidate.get("status") == (
        "candidate_incumbent_captured_and_exactly_lifted"
    ):
        status = "fixed_binary_repair_failed"
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
        "stage_execution": executions,
        "candidate_status": candidate.get("status") if candidate else None,
        "repair_status": repair.get("status") if repair else None,
        "solver_attempt_count": candidate.get("solver_attempt_count") if candidate else None,
        "total_rollback_events": candidate.get("total_rollback_events") if candidate else None,
        "audited_feasible_upper_bound_cny": (
            repair.get("solution_audit", {}).get("audited_feasible_upper_bound_cny")
            if repair
            else None
        ),
    }
    _write_json(output_dir / "bess_manifest.json", payload)
    return payload


def run_gate_a_24h_demonstration(
    *,
    output_dir: Path,
    time_limit_seconds: float = 30.0,
    threads: int = 1,
) -> dict[str, Any]:
    """Exercise one forced frontier failure and clean one-block recovery."""

    if output_dir.exists():
        raise FileExistsError(f"D52 Gate A demonstration already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    case = build_gate0_24h_case()
    guide_model = build_endogenous_capacity_model(case)
    guide_inventory = collect_binary_inventory(guide_model)
    anchor = fix_engineering_capacity_anchor(guide_model, Architecture.BESS)
    relaxation = apply_relaxation(guide_model, guide_inventory, RelaxationMode.R0)
    if anchor["passed"] is not True or relaxation["passed"] is not True:
        raise ValueError("D52 Gate A guide preparation failed")
    guide_path = output_dir / "guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=guide_path,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    if guide["status"] != "continuous_guide_recovered":
        raise ValueError("D52 Gate A continuous guide was not recovered")
    clean_build_count = 0

    def builder() -> CleanModelBundle:
        nonlocal clean_build_count
        model = build_endogenous_capacity_model(case)
        clean_build_count += 1
        return CleanModelBundle(
            model=model,
            inventory=collect_binary_inventory(model),
            chp_units=tuple(case.chp_units),
            build_audit={"gate_a_shortened_horizon": True},
        )

    forced_failure_used = False

    def capture(model: object, stage_index: int, attempt_index: int) -> dict[str, Any]:
        nonlocal forced_failure_used
        if stage_index == 2 and attempt_index == 0 and not forced_failure_used:
            forced_failure_used = True
            return {
                "status": "fault_injected_frontier_no_incumbent",
                "incumbent_captured": False,
                "runtime_seconds": 0.0,
                "gate_a_fault_injection": True,
                "formal_upper_bound_eligible": False,
            }
        return capture_first_feasibility_incumbent(
            model,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
        )

    candidate_path = output_dir / "candidate.csv.gz"
    candidate = solve_checkpointed_bounded_backtracking_candidate(
        builder,
        architecture=Architecture.BESS,
        guide_path=guide_path,
        checkpoint_dir=output_dir / "checkpoints",
        attempt_result_dir=output_dir / "attempt_results",
        progress_output_path=output_dir / "progress.jsonl",
        physical_snapshot_output_path=output_dir / "physical_snapshot.json",
        candidate_output_path=candidate_path,
        commit_hours=8,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
        require_locked_guide_hash=False,
        require_formal_counts=False,
        capture_function=capture,
    )
    _write_json(output_dir / "candidate_result.json", candidate)

    checkpoint_paths = sorted((output_dir / "checkpoints").glob("stage_*.json"))
    checkpoint_hash_to_path = {_sha256(path): path for path in checkpoint_paths}
    replay_audits: list[dict[str, Any]] = []
    for checkpoint_path in checkpoint_paths:
        raw = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        parent_hash = raw.get("parent_checkpoint_sha256")
        rollback_hash = raw.get("rollback_source_checkpoint_sha256")
        if parent_hash is not None and parent_hash not in checkpoint_hash_to_path:
            raise ValueError("D52 demonstration checkpoint parent is absent")
        if rollback_hash is not None and rollback_hash not in checkpoint_hash_to_path:
            raise ValueError("D52 demonstration rollback source is absent")
        payload, _ = read_attempt_checkpoint(
            checkpoint_path,
            expected_parent_sha256=parent_hash,
        )
        replay_model = build_endogenous_capacity_model(case)
        replay_inventory = collect_binary_inventory(replay_model)
        partition, layout, blocks, _ = prepare_d50_model(
            replay_model,
            replay_inventory,
            architecture=Architecture.BESS,
            guide_path=guide_path,
            commit_hours=8,
            require_locked_guide_hash=False,
            require_formal_counts=False,
        )
        plan = make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            int(payload["stage_index"]),
        )
        replay = replay_attempt_checkpoint(
            replay_model,
            checkpoint_path,
            expected_parent_sha256=parent_hash,
            inventory=replay_inventory,
            domain_plan=plan,
        )
        replay_audits.append(
            {
                "checkpoint": checkpoint_path.name,
                "checkpoint_sha256": _sha256(checkpoint_path),
                "parent_checkpoint_sha256": parent_hash,
                "rollback_source_checkpoint_sha256": rollback_hash,
                "replay_audit": replay,
            }
        )

    repair = None
    if candidate["status"] == "candidate_incumbent_captured_and_exactly_lifted":
        repair_model = build_endogenous_capacity_model(case)
        repair_inventory = collect_binary_inventory(repair_model)
        repair = solve_d52_original_cost_repair(
            repair_model,
            repair_inventory,
            architecture=Architecture.BESS,
            candidate_path=candidate_path,
            solution_output_path=output_dir / "repaired_solution.csv.gz",
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        _write_json(output_dir / "repair_result.json", repair)
    passed = all(
        (
            forced_failure_used,
            candidate["status"] == "candidate_incumbent_captured_and_exactly_lifted",
            candidate["total_rollback_events"] == 1,
            candidate["solver_attempt_count"] == 5,
            len(candidate["clean_rebuild_audits"]) == 1,
            candidate["clean_rebuild_audits"][0]["passed"] is True,
            candidate["checkpoint_count"] == 4,
            len(replay_audits) == 4,
            all(item["replay_audit"]["passed"] for item in replay_audits),
            repair is not None,
            repair is not None and repair["status"] == "audited_feasible_upper_bound_recovered",
        )
    )
    payload = {
        "schema_id": DEMONSTRATION_SCHEMA_ID,
        "status": "gate_a_demonstration_passed" if passed else "gate_a_demonstration_failed",
        "architecture": Architecture.BESS.value,
        "period_count": 24,
        "commit_hours": 8,
        "stage_count": 3,
        "fault_injected_frontier_failure": forced_failure_used,
        "clean_model_build_count": clean_build_count,
        "candidate_status": candidate["status"],
        "candidate_result_sha256": _sha256(output_dir / "candidate_result.json"),
        "solver_attempt_count": candidate.get("solver_attempt_count"),
        "total_rollback_events": candidate.get("total_rollback_events"),
        "checkpoint_replay_audit": replay_audits,
        "repair_status": repair["status"] if repair else None,
        "repair_result_sha256": _sha256(output_dir / "repair_result.json") if repair else None,
        "runtime_seconds": perf_counter() - started,
        "formal_8784h_optimization_invoked": False,
        "formal_run_permitted": False,
        "formal_upper_bound_eligible": False,
        "provenance": {"code_sha256": _code_hashes()},
        "audit": {"passed": passed},
    }
    _write_json(output_dir / "demonstration_result.json", payload)
    return payload


def _validate_frozen_inputs(
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
    d50_formal_manifest_path: Path,
    d51_gate0_manifest_path: Path,
) -> dict[str, str]:
    inputs = _validate_d50_formal_inputs(
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
    predecessor = {
        "d50_formal_manifest": _sha256(d50_formal_manifest_path),
        "d51_gate0_manifest": _sha256(d51_gate0_manifest_path),
    }
    expected = {
        "d50_formal_manifest": D50_FORMAL_MANIFEST_SHA256,
        "d51_gate0_manifest": D51_GATE0_MANIFEST_SHA256,
    }
    if predecessor != expected:
        raise ValueError("D52 predecessor manifest hash mismatch")
    return {**inputs, **predecessor}


def compile_gate_a_manifest(
    *,
    output_dir: Path,
    build_path: Path,
    demonstration_path: Path,
    targeted_junit_path: Path,
    compatibility_junit_path: Path,
    full_junit_path: Path,
    ruff_log_path: Path,
    pycompile_log_path: Path,
    implementation_git_commit: str,
    contract_git_commit: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d50_formal_manifest_path: Path,
    d51_gate0_manifest_path: Path,
) -> dict[str, Any]:
    """Compile Gate A without invoking the 8784-hour optimizer."""

    if output_dir.exists():
        raise FileExistsError(f"D52 Gate A output already exists: {output_dir}")
    if GIT_COMMIT_PATTERN.fullmatch(implementation_git_commit) is None:
        raise ValueError("D52 Gate A requires the full implementation commit")
    if implementation_git_commit != _git_head():
        raise ValueError("D52 Gate A implementation commit differs from HEAD")
    if contract_git_commit != D52_CONTRACT_COMMIT:
        raise ValueError("D52 contract commit mismatch")
    frozen_inputs = _validate_frozen_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_path=guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        d50_formal_manifest_path=d50_formal_manifest_path,
        d51_gate0_manifest_path=d51_gate0_manifest_path,
    )
    build = json.loads(build_path.read_text(encoding="utf-8"))
    demonstration = json.loads(demonstration_path.read_text(encoding="utf-8"))
    if build.get("schema_id") != BUILD_SCHEMA_ID or build.get("status") != "gate_a_build_passed":
        raise ValueError("D52 Gate A build did not pass")
    if build.get("solver_invoked") is not False or build.get("formal_8784h_optimization_invoked") is not False:
        raise ValueError("D52 Gate A build invoked formal optimization")
    if build.get("audit", {}).get("passed") is not True:
        raise ValueError("D52 Gate A build audit failed")
    expected_code_hashes = _code_hashes()
    if build.get("provenance", {}).get("code_sha256") != expected_code_hashes:
        raise ValueError("D52 Gate A build source hash mismatch")
    if demonstration.get("schema_id") != DEMONSTRATION_SCHEMA_ID:
        raise ValueError("D52 Gate A demonstration schema mismatch")
    if demonstration.get("status") != "gate_a_demonstration_passed":
        raise ValueError("D52 Gate A demonstration failed")
    if demonstration.get("formal_8784h_optimization_invoked") is not False:
        raise ValueError("D52 Gate A demonstration invoked formal optimization")
    replay_audits = demonstration.get("checkpoint_replay_audit", [])
    demonstration_identity = all(
        (
            demonstration.get("audit", {}).get("passed") is True,
            demonstration.get("fault_injected_frontier_failure") is True,
            demonstration.get("total_rollback_events") == 1,
            demonstration.get("solver_attempt_count") == 5,
            demonstration.get("clean_model_build_count") == 2,
            demonstration.get("candidate_status")
            == "candidate_incumbent_captured_and_exactly_lifted",
            demonstration.get("repair_status")
            == "audited_feasible_upper_bound_recovered",
            isinstance(replay_audits, list),
            len(replay_audits) == 4,
            demonstration.get("provenance", {}).get("code_sha256")
            == expected_code_hashes,
        )
    )
    if not demonstration_identity:
        raise ValueError("D52 Gate A demonstration identity mismatch")
    if not all(
        item.get("replay_audit", {}).get("passed") is True
        for item in replay_audits
    ):
        raise ValueError("D52 Gate A checkpoint replay failed")
    tests = {
        "d52_targeted": _parse_gate_a_junit(targeted_junit_path),
        "d40_d52_compatibility": _parse_gate_a_junit(compatibility_junit_path),
        "full_package": _parse_gate_a_junit(full_junit_path),
    }
    if any(item["skipped"] for item in tests.values()):
        raise ValueError("D52 Gate A test evidence contains skips")
    if not all(item["passed"] for item in tests.values()):
        raise ValueError("D52 Gate A test evidence failed")
    quality = {
        "ruff": {
            "sentinel_present": "D52_RUFF_PASSED" in ruff_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(ruff_log_path),
        },
        "pycompile": {
            "sentinel_present": "D52_PYCOMPILE_PASSED" in pycompile_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(pycompile_log_path),
        },
    }
    if not all(item["sentinel_present"] for item in quality.values()):
        raise ValueError("D52 Gate A quality sentinel is missing")
    core_identity = d51_core_identity_audit()
    if core_identity["passed"] is not True:
        raise ValueError("D52 Gate A detected D51 core drift")
    tests_dir = Path(__file__).resolve().parents[2] / "tests"
    payload = {
        "schema_id": GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "formal_8784h_optimization_invoked": False,
        "formal_run_permitted": True,
        "formal_architecture_order": [FORMAL_ARCHITECTURE.value],
        "tes_or_hybrid_formal_run_permitted": False,
        "formal_input_sha256": frozen_inputs,
        "build_audit_sha256": _sha256(build_path),
        "demonstration_sha256": _sha256(demonstration_path),
        "test_evidence": tests,
        "quality_evidence": quality,
        "d51_core_identity_audit": core_identity,
        "frozen_method": {
            "stage_count": EXPECTED_FORMAL_STAGE_COUNT,
            "commit_hours": COMMIT_HOURS,
            "integer_lookahead_hours": 336,
            "maximum_attempts_per_stage": MAX_ATTEMPTS_PER_STAGE,
            "maximum_total_rollback_events": MAX_TOTAL_ROLLBACK_EVENTS,
            "maximum_solver_attempts": MAX_SOLVER_ATTEMPTS,
            "candidate_objective": "constant_zero",
            "warmstart_requested": False,
        },
        "provenance": {
            "contract_git_commit": contract_git_commit,
            "implementation_git_commit": implementation_git_commit,
            "code_sha256": _code_hashes(),
            "test_sha256": {
                name: _sha256(tests_dir / name)
                for name in (
                    "test_e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery.py",
                    "test_e0d52_monitored_executor.py",
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
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "manifest_sha256": _sha256(manifest_path),
            "implementation_git_commit": implementation_git_commit,
            "formal_8784h_optimization_invoked": False,
        },
    )
    return payload


def _validate_gate_a(manifest_path: Path, execution_path: Path) -> dict[str, Any]:
    manifest_hash = _sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D52 Gate A schema mismatch")
    if manifest.get("status") != "gate_a_passed":
        raise ValueError("D52 formal run requires a passed Gate A")
    if manifest.get("formal_8784h_optimization_invoked") is not False:
        raise ValueError("D52 Gate A unexpectedly invoked formal optimization")
    if manifest.get("formal_run_permitted") is not True:
        raise ValueError("D52 Gate A did not permit the formal run")
    if manifest.get("formal_architecture_order") != [Architecture.BESS.value]:
        raise ValueError("D52 Gate A did not authorize BESS-only execution")
    if manifest.get("tes_or_hybrid_formal_run_permitted") is not False:
        raise ValueError("D52 Gate A improperly authorized TES/Hybrid")
    if manifest.get("audit", {}).get("passed") is not True:
        raise ValueError("D52 Gate A audit is not passed")
    if execution.get("status") != "complete" or execution.get("manifest_sha256") != manifest_hash:
        raise ValueError("D52 Gate A execution hash mismatch")
    if manifest.get("provenance", {}).get("code_sha256") != _code_hashes():
        raise ValueError("D52 formal source differs from Gate A")
    if manifest.get("provenance", {}).get("contract_git_commit") != D52_CONTRACT_COMMIT:
        raise ValueError("D52 formal contract commit differs from Gate A")
    implementation_commit = manifest.get("provenance", {}).get(
        "implementation_git_commit"
    )
    if implementation_commit != _git_head():
        raise ValueError("D52 formal implementation commit differs from Gate A")
    return {
        "manifest_sha256": manifest_hash,
        "execution_sha256": _sha256(execution_path),
        "implementation_git_commit": implementation_commit,
        "passed": True,
    }


def _ancestor_pids(pid: int) -> set[int]:
    ancestors: set[int] = set()
    current = pid
    while current > 1:
        try:
            stat = (Path("/proc") / str(current) / "stat").read_text(
                encoding="utf-8"
            )
            fields = stat[stat.rfind(")") + 2 :].split()
            parent = int(fields[1])
        except (OSError, ValueError, IndexError):
            break
        if parent <= 1 or parent in ancestors:
            break
        ancestors.add(parent)
        current = parent
    return ancestors


def _active_formal_processes() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    proc = Path("/proc")
    if not proc.is_dir():
        raise RuntimeError("D52 formal process audit requires Linux /proc")
    excluded_pids = _ancestor_pids(os.getpid()) | {os.getpid()}
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) in excluded_pids:
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if FORMAL_PROCESS_PATTERN.search(command) and any(
            marker in command for marker in ("formal", "candidate", "gate-b")
        ):
            active.append({"pid": int(entry.name), "command_sha256": __import__("hashlib").sha256(command.encode()).hexdigest()})
    return sorted(active, key=lambda item: item["pid"])


def run_formal_bess_gate(
    *,
    output_dir: Path,
    host_formal_lock_path: Path,
    gate_a_manifest_path: Path,
    gate_a_execution_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d50_formal_manifest_path: Path,
    d51_gate0_manifest_path: Path,
) -> dict[str, Any]:
    """Run the unique formal D52 BESS directory after all immutable gates."""

    if output_dir.exists():
        raise FileExistsError(f"D52 formal output already exists: {output_dir}")
    gate_a = _validate_gate_a(gate_a_manifest_path, gate_a_execution_path)
    formal_inputs = _validate_frozen_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_path=guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        d50_formal_manifest_path=d50_formal_manifest_path,
        d51_gate0_manifest_path=d51_gate0_manifest_path,
    )
    active = _active_formal_processes()
    if active:
        raise RuntimeError("D52 refuses to overlap another formal large process")
    available = _available_memory_gib()
    if available is None or available < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D52 formal host does not satisfy the memory reserve")
    host_formal_lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            host_formal_lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise RuntimeError("D52 formal host lock already exists") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"pid": os.getpid(), "output_dir": str(output_dir)}, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    output_dir.mkdir(parents=True)
    started = perf_counter()
    try:
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
        runtime = perf_counter() - started
        if runtime > TOTAL_HARD_WALL_SECONDS:
            raise RuntimeError("D52 total hard wall exceeded")
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
            "architecture_order": [Architecture.BESS.value],
            "successful_architecture_count": int(bess["status"] == "audited_feasible_upper_bound_recovered"),
            "runtime_seconds": runtime,
            "gate_a": gate_a,
            "formal_input_sha256": formal_inputs,
            "architecture": {Architecture.BESS.value: bess},
            "tes_or_hybrid_executed": False,
            "resource_contract": {
                "threads_per_attempt": FORMAL_THREADS,
                "stage_count": EXPECTED_FORMAL_STAGE_COUNT,
                "maximum_solver_attempts": MAX_SOLVER_ATTEMPTS,
                "maximum_rollback_events": MAX_TOTAL_ROLLBACK_EVENTS,
                "attempt_soft_time_limit_seconds": STAGE_SOFT_TIME_LIMIT_SECONDS,
                "attempt_hard_wall_seconds": STAGE_HARD_WALL_SECONDS,
                "clean_rebuild_hard_wall_seconds": CLEAN_REBUILD_HARD_WALL_SECONDS,
                "candidate_total_hard_wall_seconds": CANDIDATE_TOTAL_HARD_WALL_SECONDS,
                "repair_hard_wall_seconds": REPAIR_HARD_WALL_SECONDS,
                "total_hard_wall_seconds": TOTAL_HARD_WALL_SECONDS,
                "process_tree_rss_warning_gib": PROCESS_TREE_RSS_WARNING_GIB,
                "aggregate_rss_stop_gib": AGGREGATE_RSS_STOP_GIB,
                "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
                "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            },
            "provenance": {"code_sha256": _code_hashes()},
            "artifact_sha256": artifact_hashes,
            "engineering_numerical_feasibility_only": True,
            "rational_exact_feasibility_certificate": False,
            "restart_or_resume_permitted": False,
        }
        _write_json(output_dir / "formal_manifest.json", payload)
        return payload
    finally:
        host_formal_lock_path.unlink(missing_ok=True)


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--d46-formal", type=Path, required=True)
    parser.add_argument("--d46-postmortem", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)
    parser.add_argument("--d50-formal", type=Path, required=True)
    parser.add_argument("--d51-gate0", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demonstration = commands.add_parser("demonstration-24h")
    demonstration.add_argument("--output-dir", type=Path, required=True)
    demonstration.add_argument("--time-limit", type=float, default=30.0)
    demonstration.add_argument("--threads", type=int, default=1)
    compile_gate = commands.add_parser("compile-gate-a")
    compile_gate.add_argument("--output-dir", type=Path, required=True)
    compile_gate.add_argument("--build", type=Path, required=True)
    compile_gate.add_argument("--demonstration", type=Path, required=True)
    compile_gate.add_argument("--targeted-junit", type=Path, required=True)
    compile_gate.add_argument("--compatibility-junit", type=Path, required=True)
    compile_gate.add_argument("--full-junit", type=Path, required=True)
    compile_gate.add_argument("--ruff-log", type=Path, required=True)
    compile_gate.add_argument("--pycompile-log", type=Path, required=True)
    compile_gate.add_argument("--implementation-git-commit", required=True)
    compile_gate.add_argument("--contract-git-commit", required=True)
    _add_formal_inputs(compile_gate)
    formal = commands.add_parser("formal-bess")
    formal.add_argument("--output-dir", type=Path, required=True)
    formal.add_argument("--host-formal-lock", type=Path, required=True)
    formal.add_argument("--gate-a-manifest", type=Path, required=True)
    formal.add_argument("--gate-a-execution", type=Path, required=True)
    _add_formal_inputs(formal)
    return parser


def _formal_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "service_path": args.service,
        "d40_gate_a_manifest_path": args.d40_gate_a,
        "d41_gate_a_manifest_path": args.d41_gate_a,
        "d46_formal_manifest_path": args.d46_formal,
        "d46_postmortem_bundle_path": args.d46_postmortem,
        "guide_path": args.guide,
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
        "d50_formal_manifest_path": args.d50_formal,
        "d51_gate0_manifest_path": args.d51_gate0,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "demonstration-24h":
        run_gate_a_24h_demonstration(
            output_dir=args.output_dir,
            time_limit_seconds=args.time_limit,
            threads=args.threads,
        )
        return
    if args.command == "compile-gate-a":
        compile_gate_a_manifest(
            output_dir=args.output_dir,
            build_path=args.build,
            demonstration_path=args.demonstration,
            targeted_junit_path=args.targeted_junit,
            compatibility_junit_path=args.compatibility_junit,
            full_junit_path=args.full_junit,
            ruff_log_path=args.ruff_log,
            pycompile_log_path=args.pycompile_log,
            implementation_git_commit=args.implementation_git_commit,
            contract_git_commit=args.contract_git_commit,
            **_formal_kwargs(args),
        )
        return
    if args.command == "formal-bess":
        run_formal_bess_gate(
            output_dir=args.output_dir,
            host_formal_lock_path=args.host_formal_lock,
            gate_a_manifest_path=args.gate_a_manifest,
            gate_a_execution_path=args.gate_a_execution,
            **_formal_kwargs(args),
        )
        return
    raise AssertionError(f"unhandled D52 executor command: {args.command}")


if __name__ == "__main__":
    main()
