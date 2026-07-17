"""Parent-side resource monitor and one-shot executor for formal E0-D-46."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping
from xml.etree import ElementTree

from tes_bess_boundary.e0d41_gate_b_lower_bound import (
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _terminate_process_group,
)
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
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    ARCHITECTURE_HARD_WALL_SECONDS,
    BATCH_HARD_WALL_SECONDS,
    CANDIDATE_HARD_WALL_SECONDS,
    CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    CLAIM_SCOPE,
    D47_FORMAL_EXECUTION_SHA256,
    D47_FORMAL_MANIFEST_SHA256,
    D41_BESS_R1_GUIDE_SHA256,
    D41_GATE_A_MANIFEST_SHA256,
    FORMAL_ARCHITECTURES,
    FORMAL_PROJECT_TAC_READY,
    FORMAL_THREADS,
    GUIDE_HARD_WALL_SECONDS,
    GUIDE_SOFT_TIME_LIMIT_SECONDS,
    REPAIR_A_HARD_WALL_SECONDS,
    REPAIR_B_HARD_WALL_SECONDS,
    TECHNICAL_RANKING_PERMITTED,
    _code_hashes,
    _sha256,
    _tree_sha256,
    select_preferred_repair,
)
from tes_bess_boundary.model import Architecture


EXECUTION_SCHEMA_ID = "tes_bess_boundary.e0d46_stage_execution.v1"
ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d46_architecture_manifest.v1"
FORMAL_SCHEMA_ID = "tes_bess_boundary.e0d46_formal_manifest.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d46_gate_a_manifest.v1"

PROCESS_TREE_RSS_LIMIT_GIB = 35.0
AGGREGATE_RSS_LIMIT_GIB = 45.0
HOST_MEMORY_RESERVE_GIB = 30.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


def monitor_stop_reason(
    *,
    elapsed_seconds: float,
    hard_wall_seconds: float,
    child_tree_rss_gib: float | None,
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    """Apply D46 hard-wall and memory stops in frozen priority order."""

    if elapsed_seconds >= hard_wall_seconds:
        return "hard_wall_clock_reached"
    if (
        child_tree_rss_gib is not None
        and child_tree_rss_gib >= PROCESS_TREE_RSS_LIMIT_GIB
    ):
        return "process_tree_rss_limit_reached"
    if (
        aggregate_rss_gib is not None
        and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB
    ):
        return "aggregate_rss_limit_reached"
    if (
        available_memory_gib is not None
        and available_memory_gib < HOST_MEMORY_RESERVE_GIB
    ):
        return "host_memory_reserve_breached"
    return None


def _process_group_active(process_group_id: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(process_group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_residual_process_group(process_group_id: int) -> str | None:
    if not _process_group_active(process_group_id):
        return None
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return None
    deadline = perf_counter() + 30.0
    while perf_counter() < deadline:
        if not _process_group_active(process_group_id):
            return "residual_sigterm"
        time.sleep(0.1)
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return "residual_sigterm"
    return "residual_sigkill"


def _stage_paths(
    output_dir: Path,
    architecture: Architecture,
    stage: str,
) -> dict[str, Path]:
    prefix = f"{architecture.value}_{stage}"
    return {
        "result": output_dir / f"{prefix}.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solver_log": output_dir / f"{prefix}.log",
        "heartbeat": output_dir / f"{prefix}_heartbeat.jsonl",
    }


def _common_command(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> list[str]:
    return [
        "--architecture",
        architecture.value,
        "--service-file",
        str(service_path),
        "--d40-gate-a-manifest",
        str(d40_gate_a_manifest_path),
        "--d41-gate-a-manifest",
        str(d41_gate_a_manifest_path),
        "--heat-path",
        str(heat_path),
        "--vre-path",
        str(vre_path),
        "--price-basis-path",
        str(price_basis_path),
    ]


def build_stage_command(
    *,
    architecture: Architecture,
    stage: str,
    output_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d41_bess_guide_path: Path | None = None,
) -> tuple[list[str], tuple[Path, ...]]:
    """Build the exact child command and declare its non-log artifacts."""

    paths = _stage_paths(output_dir, architecture, stage)
    common = _common_command(
        architecture=architecture,
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
        "tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair",
    ]
    if stage == "guide":
        seed = output_dir / f"{architecture.value}_guide.csv.gz"
        command = [
            *base,
            "_guide-child",
            *common,
            "--seed-output",
            str(seed),
            "--result-output",
            str(paths["result"]),
            "--threads",
            str(FORMAL_THREADS),
            "--time-limit-seconds",
            str(GUIDE_SOFT_TIME_LIMIT_SECONDS),
        ]
        return command, (paths["result"], seed)
    if stage == "candidate":
        seed = output_dir / f"{architecture.value}_guide.csv.gz"
        candidate = output_dir / f"{architecture.value}_candidate.csv.gz"
        fallback_seed = output_dir / "bess_d41_fallback_seed.csv.gz"
        command = [
            *base,
            "_candidate-child",
            *common,
            "--seed-path",
            str(seed),
            "--candidate-output",
            str(candidate),
            "--result-output",
            str(paths["result"]),
            "--threads",
            str(FORMAL_THREADS),
            "--time-limit-seconds",
            str(CANDIDATE_SOFT_TIME_LIMIT_SECONDS),
        ]
        artifacts: tuple[Path, ...] = (paths["result"], candidate)
        if architecture is Architecture.BESS:
            if d41_bess_guide_path is None:
                raise ValueError("D46 BESS candidate requires the locked D41 guide")
            command.extend(
                [
                    "--d41-bess-guide",
                    str(d41_bess_guide_path),
                    "--fallback-seed-output",
                    str(fallback_seed),
                ]
            )
            artifacts = (*artifacts, fallback_seed)
        return command, artifacts
    if stage in {"repair_a", "repair_b"}:
        repair = stage[-1].upper()
        candidate = output_dir / f"{architecture.value}_candidate.csv.gz"
        solution = output_dir / f"{architecture.value}_{stage}_solution.csv.gz"
        command = [
            *base,
            "_repair-child",
            *common,
            "--repair",
            repair,
            "--candidate-path",
            str(candidate),
            "--solution-output",
            str(solution),
            "--result-output",
            str(paths["result"]),
            "--threads",
            str(FORMAL_THREADS),
            "--time-limit-seconds",
            str(
                REPAIR_A_HARD_WALL_SECONDS
                if repair == "A"
                else REPAIR_B_HARD_WALL_SECONDS
            ),
        ]
        return command, (paths["result"], solution)
    raise ValueError(f"unknown D46 stage: {stage}")


def run_monitored_stage(
    *,
    architecture: Architecture,
    stage: str,
    output_dir: Path,
    hard_wall_seconds: float,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d41_bess_guide_path: Path | None = None,
) -> dict[str, Any]:
    """Run one stage in a clean process group under the D46 resource contract."""

    if not math.isfinite(hard_wall_seconds) or hard_wall_seconds <= 0.0:
        raise ValueError("D46 stage hard wall must be finite and positive")
    paths = _stage_paths(output_dir, architecture, stage)
    command, artifacts = build_stage_command(
        architecture=architecture,
        stage=stage,
        output_dir=output_dir,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        d41_bess_guide_path=d41_bess_guide_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (
        paths["execution"],
        paths["solver_log"],
        paths["heartbeat"],
        *artifacts,
    ):
        if path.exists():
            raise FileExistsError(f"D46 refuses to overwrite {path}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D46 formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D46 host memory is below the frozen reserve")

    started_payload = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": "child_starting",
        "architecture": architecture.value,
        "stage": stage,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "hard_wall_enforced_by_parent": True,
        "resource_thresholds": {
            "hard_wall_seconds": hard_wall_seconds,
            "process_tree_rss_limit_gib": PROCESS_TREE_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        },
    }
    _write_json(paths["execution"], started_payload)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
    peak_child_tree = 0.0
    peak_aggregate = 0.0
    minimum_available = available_before
    rss_samples = 0
    memory_samples = 0
    stop_reason: str | None = None
    termination_signal: str | None = None
    started = perf_counter()
    last_heartbeat = -HEARTBEAT_INTERVAL_SECONDS
    with paths["solver_log"].open(
        "w", encoding="utf-8", newline="\n"
    ) as solver_log, paths["heartbeat"].open(
        "w", encoding="utf-8", newline="\n", buffering=1
    ) as heartbeat_log:
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
                rss_samples += 1
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            if elapsed - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                heartbeat_log.write(
                    json.dumps(
                        {
                            "architecture": architecture.value,
                            "stage": stage,
                            "pid": process.pid,
                            "elapsed_seconds": elapsed,
                            "child_process_tree_rss_gib": child_tree,
                            "parent_child_aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                heartbeat_log.flush()
                last_heartbeat = elapsed
            stop_reason = monitor_stop_reason(
                elapsed_seconds=elapsed,
                hard_wall_seconds=hard_wall_seconds,
                child_tree_rss_gib=child_tree,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
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
            peak_child_tree < PROCESS_TREE_RSS_LIMIT_GIB,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
            not residual_process_group_active,
        )
    )
    complete = (
        return_code == 0
        and result_payload is not None
        and resource_gate_passed
    )
    execution = {
        **started_payload,
        "status": "complete" if complete else "resource_or_process_failure",
        "return_code": return_code,
        "runtime_seconds": runtime,
        "peak_child_process_tree_rss_gib": peak_child_tree,
        "peak_parent_child_aggregate_rss_gib": peak_aggregate,
        "minimum_available_memory_gib": minimum_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "stop_reason": stop_reason,
        "termination_signal": termination_signal,
        "residual_termination_signal": residual_termination_signal,
        "resource_gate_passed": resource_gate_passed,
        "result_sha256": (
            _sha256(paths["result"]) if paths["result"].is_file() else None
        ),
        "solver_log_sha256": _sha256(paths["solver_log"]),
        "heartbeat_sha256": _sha256(paths["heartbeat"]),
        "declared_artifact_sha256": {
            path.name: _sha256(path) if path.is_file() else None
            for path in artifacts
        },
        "active_residual_process_count": int(
            residual_process_group_active
        ),
    }
    _write_json(paths["execution"], execution)
    return execution


def _load_completed_result(
    output_dir: Path,
    architecture: Architecture,
    stage: str,
) -> dict[str, Any] | None:
    paths = _stage_paths(output_dir, architecture, stage)
    if not paths["result"].is_file() or not paths["execution"].is_file():
        return None
    execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
    if execution.get("status") != "complete":
        return None
    if execution.get("result_sha256") != _sha256(paths["result"]):
        raise ValueError(f"D46 {architecture.value} {stage} result hash mismatch")
    return json.loads(paths["result"].read_text(encoding="utf-8"))


def run_architecture(
    *,
    architecture: Architecture,
    output_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d41_bess_guide_path: Path | None = None,
    hard_wall_seconds: float = ARCHITECTURE_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    """Run the frozen guide/candidate/Repair A/B sequence for one architecture."""

    architecture_started = perf_counter()
    executions: dict[str, Any] = {}
    stage_limits = (
        ("guide", GUIDE_HARD_WALL_SECONDS),
        ("candidate", CANDIDATE_HARD_WALL_SECONDS),
        ("repair_a", REPAIR_A_HARD_WALL_SECONDS),
        ("repair_b", REPAIR_B_HARD_WALL_SECONDS),
    )
    for stage, stage_limit in stage_limits:
        if stage == "candidate":
            guide = _load_completed_result(output_dir, architecture, "guide")
            if guide is None or guide.get("status") != "continuous_guide_recovered":
                break
        if stage == "repair_a":
            candidate = _load_completed_result(
                output_dir, architecture, "candidate"
            )
            if (
                candidate is None
                or candidate.get("status") != "candidate_incumbent_captured"
            ):
                break
        if stage == "repair_b":
            repair_a = _load_completed_result(
                output_dir, architecture, "repair_a"
            )
            if (
                repair_a is None
                or repair_a.get("status")
                != "audited_feasible_upper_bound_recovered"
            ):
                break
        remaining = hard_wall_seconds - (
            perf_counter() - architecture_started
        )
        if remaining <= 0.0:
            executions[stage] = {"status": "architecture_hard_wall_exhausted"}
            break
        executions[stage] = run_monitored_stage(
            architecture=architecture,
            stage=stage,
            output_dir=output_dir,
            hard_wall_seconds=min(stage_limit, remaining),
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            d41_bess_guide_path=d41_bess_guide_path,
        )

    repair_a = _load_completed_result(output_dir, architecture, "repair_a")
    repair_b = _load_completed_result(output_dir, architecture, "repair_b")
    selection = None
    if (
        repair_a is not None
        and repair_a.get("status") == "audited_feasible_upper_bound_recovered"
    ):
        selection = select_preferred_repair(repair_a, repair_b)
    guide = _load_completed_result(output_dir, architecture, "guide")
    candidate = _load_completed_result(output_dir, architecture, "candidate")
    if selection is not None:
        status = "audited_feasible_upper_bound_recovered"
    elif guide is None or guide.get("status") != "continuous_guide_recovered":
        status = "no_continuous_guide"
    elif (
        candidate is None
        or candidate.get("status") != "candidate_incumbent_captured"
    ):
        status = "no_candidate_incumbent"
    else:
        status = "fixed_binary_repair_failed"
    payload = {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "status": status,
        "architecture": architecture.value,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "runtime_seconds": perf_counter() - architecture_started,
        "stage_execution": executions,
        "repair_selection": selection,
    }
    path = output_dir / f"{architecture.value}_manifest.json"
    _write_json(path, payload)
    return payload


def _validate_d47_permission(
    manifest_path: Path,
    execution_path: Path,
) -> dict[str, Any]:
    if _sha256(manifest_path) != D47_FORMAL_MANIFEST_SHA256:
        raise ValueError("D46 D47 formal manifest hash mismatch")
    if _sha256(execution_path) != D47_FORMAL_EXECUTION_SHA256:
        raise ValueError("D46 D47 formal execution hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if manifest.get("d46_feasible_upper_bound_contract_permitted") is not True:
        raise ValueError("D47 did not permit the D46 upper-bound contract")
    return {
        "manifest_sha256": _sha256(manifest_path),
        "execution_sha256": _sha256(execution_path),
        "permission": True,
        "d47_status": manifest.get("status"),
        "d47_execution_status": execution.get("status"),
    }


def _validate_formal_inputs(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d41_bess_guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    expected = {
        "service": (service_path, D40_SERVICE_SHA256),
        "d40_gate_a": (
            d40_gate_a_manifest_path,
            D40_GATE_A_MANIFEST_SHA256,
        ),
        "d41_gate_a": (
            d41_gate_a_manifest_path,
            D41_GATE_A_MANIFEST_SHA256,
        ),
        "d41_bess_guide": (
            d41_bess_guide_path,
            D41_BESS_R1_GUIDE_SHA256,
        ),
        "heat": (heat_path, FORMAL_HEAT_SHA256),
        "vre": (vre_path, LEGACY_VRE_SHA256),
    }
    actual: dict[str, str] = {}
    for name, (path, expected_hash) in expected.items():
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"D46 formal {name} hash mismatch")
        actual[name] = actual_hash
    price_hash = _tree_sha256(price_basis_path)
    if price_hash != PRICE_BASIS_TREE_SHA256:
        raise ValueError("D46 formal price-basis tree hash mismatch")
    actual["price_basis_tree"] = price_hash
    return actual


def _validate_d46_gate_a(
    manifest_path: Path,
    execution_path: Path,
) -> dict[str, Any]:
    manifest_hash = _sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if manifest.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D46 Gate A schema mismatch")
    if manifest.get("status") != "gate_a_passed":
        raise ValueError("D46 formal run requires a passed Gate A")
    if manifest.get("formal_optimization_invoked") is not False:
        raise ValueError("D46 Gate A unexpectedly invoked formal optimization")
    if manifest.get("formal_run_permitted") is not True:
        raise ValueError("D46 Gate A did not permit the formal run")
    if manifest.get("audit", {}).get("passed") is not True:
        raise ValueError("D46 Gate A audit is not passed")
    if execution.get("status") != "complete":
        raise ValueError("D46 Gate A execution is incomplete")
    if execution.get("manifest_sha256") != manifest_hash:
        raise ValueError("D46 Gate A execution hash mismatch")
    expected_code = manifest.get("provenance", {}).get("code_sha256")
    if expected_code != _code_hashes():
        raise ValueError("D46 formal source differs from Gate A")
    return {
        "manifest_sha256": manifest_hash,
        "execution_sha256": _sha256(execution_path),
        "git_commit": manifest.get("provenance", {}).get("git_commit"),
        "passed": True,
    }


def _parse_junit(path: Path) -> dict[str, Any]:
    root = ElementTree.parse(path).getroot()
    suites = (root,) if root.tag == "testsuite" else tuple(root.findall("testsuite"))
    if not suites:
        raise ValueError(f"D46 Gate A JUnit has no test suites: {path}")
    counts = {
        key: sum(int(float(suite.attrib.get(key, "0"))) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    counts["passed"] = (
        counts["tests"] > 0
        and counts["failures"] == 0
        and counts["errors"] == 0
        and counts["skipped"] == 0
    )
    counts["file_sha256"] = _sha256(path)
    return counts


def compile_gate_a_manifest(
    *,
    output_dir: Path,
    build_dir: Path,
    targeted_junit_path: Path,
    d40_d47_junit_path: Path,
    full_junit_path: Path,
    ruff_log_path: Path,
    pycompile_log_path: Path,
    git_commit: str,
    d47_manifest_path: Path,
    d47_execution_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d41_bess_guide_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Compile build, toy integration, regression, and lint evidence for Gate A."""

    if output_dir.exists():
        raise FileExistsError(f"D46 Gate A output already exists: {output_dir}")
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise ValueError("D46 Gate A requires a full lowercase Git commit")
    started = perf_counter()
    permission = _validate_d47_permission(d47_manifest_path, d47_execution_path)
    formal_inputs = _validate_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d41_bess_guide_path=d41_bess_guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    build_audits: dict[str, Any] = {}
    build_hashes: dict[str, str] = {}
    for architecture in FORMAL_ARCHITECTURES:
        path = build_dir / f"gate_a_build_{architecture.value}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "gate_a_build_passed":
            raise ValueError(f"D46 Gate A {architecture.value} build failed")
        if payload.get("solver_invoked") is not False:
            raise ValueError(f"D46 Gate A {architecture.value} invoked a solver")
        if payload.get("formal_optimization_invoked") is not False:
            raise ValueError(
                f"D46 Gate A {architecture.value} invoked formal optimization"
            )
        if payload.get("audit", {}).get("passed") is not True:
            raise ValueError(f"D46 Gate A {architecture.value} audit failed")
        build_audits[architecture.value] = payload
        build_hashes[architecture.value] = _sha256(path)

    tests = {
        "d46_targeted": _parse_junit(targeted_junit_path),
        "d40_d47": _parse_junit(d40_d47_junit_path),
        "full_package": _parse_junit(full_junit_path),
    }
    if not all(item["passed"] for item in tests.values()):
        raise ValueError("D46 Gate A requires zero test failures and zero skips")
    ruff_text = ruff_log_path.read_text(encoding="utf-8")
    pycompile_text = pycompile_log_path.read_text(encoding="utf-8")
    quality = {
        "ruff": {
            "sentinel_present": "D46_RUFF_PASSED" in ruff_text,
            "file_sha256": _sha256(ruff_log_path),
        },
        "pycompile": {
            "sentinel_present": "D46_PYCOMPILE_PASSED" in pycompile_text,
            "file_sha256": _sha256(pycompile_log_path),
        },
    }
    if not all(item["sentinel_present"] for item in quality.values()):
        raise ValueError("D46 Gate A quality sentinel is missing")

    package = Path(__file__).resolve().parent
    tests_dir = package.parent.parent / "tests"
    provenance = {
        "git_commit": git_commit,
        "code_sha256": _code_hashes(),
        "test_sha256": {
            name: _sha256(tests_dir / name)
            for name in (
                "test_e0d46_full_year_feasible_upper_bound_repair.py",
                "test_e0d46_monitored_executor.py",
            )
        },
    }
    payload = {
        "schema_id": GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "formal_optimization_invoked": False,
        "formal_run_permitted": True,
        "d47_permission": permission,
        "formal_input_sha256": formal_inputs,
        "build_audit_sha256": build_hashes,
        "build_model_size": {
            name: audit["build_audit"]["model_size"]
            for name, audit in build_audits.items()
        },
        "test_evidence": tests,
        "quality_evidence": quality,
        "provenance": provenance,
        "audit": {"passed": True},
    }
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "gate_a_manifest.json"
    _write_json(manifest_path, payload)
    execution = {
        "schema_id": f"{GATE_A_SCHEMA_ID}.execution",
        "status": "complete",
        "runtime_seconds": perf_counter() - started,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "manifest_sha256": _sha256(manifest_path),
    }
    _write_json(output_dir / "gate_a_execution.json", execution)
    return payload


def run_formal_batch(
    *,
    output_dir: Path,
    d47_manifest_path: Path,
    d47_execution_path: Path,
    d46_gate_a_manifest_path: Path,
    d46_gate_a_execution_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    d41_bess_guide_path: Path,
) -> dict[str, Any]:
    """Run the only permitted formal D46 batch in BESS/TES/Hybrid order."""

    if output_dir.exists():
        raise FileExistsError(f"D46 formal output already exists: {output_dir}")
    permission = _validate_d47_permission(
        d47_manifest_path,
        d47_execution_path,
    )
    d46_gate_a = _validate_d46_gate_a(
        d46_gate_a_manifest_path,
        d46_gate_a_execution_path,
    )
    formal_inputs = _validate_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d41_bess_guide_path=d41_bess_guide_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    available = _available_memory_gib()
    if available is None or available < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D46 formal host does not satisfy the memory reserve")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    architectures: dict[str, dict[str, Any]] = {}
    for architecture in FORMAL_ARCHITECTURES:
        elapsed = perf_counter() - started
        if elapsed >= BATCH_HARD_WALL_SECONDS:
            architectures[architecture.value] = {
                "status": "batch_hard_wall_exhausted"
            }
            continue
        remaining_batch = BATCH_HARD_WALL_SECONDS - elapsed
        architectures[architecture.value] = run_architecture(
            architecture=architecture,
            output_dir=output_dir,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            d41_bess_guide_path=d41_bess_guide_path,
            hard_wall_seconds=min(
                ARCHITECTURE_HARD_WALL_SECONDS,
                remaining_batch,
            ),
        )
    success_count = sum(
        payload.get("status") == "audited_feasible_upper_bound_recovered"
        for payload in architectures.values()
    )
    status = (
        "all_architecture_upper_bounds_recovered"
        if success_count == len(FORMAL_ARCHITECTURES)
        else "partial_or_no_upper_bound_recovery"
    )
    artifact_hashes = {
        str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "formal_manifest.json"
    }
    payload = {
        "schema_id": FORMAL_SCHEMA_ID,
        "status": status,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "architecture_order": [item.value for item in FORMAL_ARCHITECTURES],
        "successful_architecture_count": success_count,
        "runtime_seconds": perf_counter() - started,
        "d47_permission": permission,
        "d46_gate_a": d46_gate_a,
        "formal_input_sha256": formal_inputs,
        "architecture": architectures,
        "resource_contract": {
            "threads_per_stage": FORMAL_THREADS,
            "architecture_hard_wall_seconds": ARCHITECTURE_HARD_WALL_SECONDS,
            "batch_hard_wall_seconds": BATCH_HARD_WALL_SECONDS,
            "process_tree_rss_limit_gib": PROCESS_TREE_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
        },
        "provenance": {"code_sha256": _code_hashes()},
        "artifact_sha256": artifact_hashes,
        "engineering_numerical_feasibility_only": True,
        "rational_exact_feasibility_certificate": False,
    }
    _write_json(output_dir / "formal_manifest.json", payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    formal = commands.add_parser("formal-batch")
    formal.add_argument("--output-dir", type=Path, required=True)
    formal.add_argument("--d47-manifest", type=Path, required=True)
    formal.add_argument("--d47-execution", type=Path, required=True)
    formal.add_argument("--d46-gate-a-manifest", type=Path, required=True)
    formal.add_argument("--d46-gate-a-execution", type=Path, required=True)
    formal.add_argument("--service-file", type=Path, required=True)
    formal.add_argument("--d40-gate-a-manifest", type=Path, required=True)
    formal.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    formal.add_argument("--heat-path", type=Path, required=True)
    formal.add_argument("--vre-path", type=Path, required=True)
    formal.add_argument("--price-basis-path", type=Path, required=True)
    formal.add_argument("--d41-bess-guide", type=Path, required=True)
    gate_a = commands.add_parser("gate-a-compile")
    gate_a.add_argument("--output-dir", type=Path, required=True)
    gate_a.add_argument("--build-dir", type=Path, required=True)
    gate_a.add_argument("--targeted-junit", type=Path, required=True)
    gate_a.add_argument("--d40-d47-junit", type=Path, required=True)
    gate_a.add_argument("--full-junit", type=Path, required=True)
    gate_a.add_argument("--ruff-log", type=Path, required=True)
    gate_a.add_argument("--pycompile-log", type=Path, required=True)
    gate_a.add_argument("--git-commit", required=True)
    gate_a.add_argument("--d47-manifest", type=Path, required=True)
    gate_a.add_argument("--d47-execution", type=Path, required=True)
    gate_a.add_argument("--service-file", type=Path, required=True)
    gate_a.add_argument("--d40-gate-a-manifest", type=Path, required=True)
    gate_a.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    gate_a.add_argument("--d41-bess-guide", type=Path, required=True)
    gate_a.add_argument("--heat-path", type=Path, required=True)
    gate_a.add_argument("--vre-path", type=Path, required=True)
    gate_a.add_argument("--price-basis-path", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "formal-batch":
        run_formal_batch(
            output_dir=args.output_dir,
            d47_manifest_path=args.d47_manifest,
            d47_execution_path=args.d47_execution,
            d46_gate_a_manifest_path=args.d46_gate_a_manifest,
            d46_gate_a_execution_path=args.d46_gate_a_execution,
            service_path=args.service_file,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            d41_bess_guide_path=args.d41_bess_guide,
        )
        return
    if args.command == "gate-a-compile":
        compile_gate_a_manifest(
            output_dir=args.output_dir,
            build_dir=args.build_dir,
            targeted_junit_path=args.targeted_junit,
            d40_d47_junit_path=args.d40_d47_junit,
            full_junit_path=args.full_junit,
            ruff_log_path=args.ruff_log,
            pycompile_log_path=args.pycompile_log,
            git_commit=args.git_commit,
            d47_manifest_path=args.d47_manifest,
            d47_execution_path=args.d47_execution,
            service_path=args.service_file,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest,
            d41_bess_guide_path=args.d41_bess_guide,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
        )
        return
    raise AssertionError(f"unhandled D46 executor command: {args.command}")


if __name__ == "__main__":
    main()
