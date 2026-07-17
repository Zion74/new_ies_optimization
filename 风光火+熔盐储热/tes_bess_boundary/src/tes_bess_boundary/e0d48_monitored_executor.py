"""Parent-side Gate A compiler and one-shot executor for formal E0-D-48."""

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
from xml.etree import ElementTree

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
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    D41_GATE_A_MANIFEST_SHA256,
)
from tes_bess_boundary.e0d46_monitored_executor import (
    AGGREGATE_RSS_LIMIT_GIB,
    HEARTBEAT_INTERVAL_SECONDS,
    HOST_MEMORY_RESERVE_GIB,
    MONITOR_INTERVAL_SECONDS,
    PROCESS_TREE_RSS_LIMIT_GIB,
    _process_group_active,
    _terminate_residual_process_group,
    monitor_stop_reason,
)
from tes_bess_boundary.e0d48_hamming_primal_recovery import (
    ARCHITECTURE_HARD_WALL_SECONDS,
    BATCH_HARD_WALL_SECONDS,
    BUILD_SCHEMA_ID,
    CANDIDATE_HARD_WALL_SECONDS,
    CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    CLAIM_SCOPE,
    D46_FORMAL_MANIFEST_SHA256,
    D46_GUIDE_SHA256,
    D46_POSTMORTEM_BUNDLE_SHA256,
    FORMAL_ARCHITECTURES,
    FORMAL_PROJECT_TAC_READY,
    FORMAL_THREADS,
    REPAIR_HARD_WALL_SECONDS,
    TECHNICAL_RANKING_PERMITTED,
    _code_hashes,
    _sha256,
    _tree_sha256,
)
from tes_bess_boundary.model import Architecture


EXECUTION_SCHEMA_ID = "tes_bess_boundary.e0d48_stage_execution.v1"
ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d48_architecture_manifest.v1"
FORMAL_SCHEMA_ID = "tes_bess_boundary.e0d48_formal_manifest.v1"
GATE_A_SCHEMA_ID = "tes_bess_boundary.e0d48_gate_a_manifest.v1"


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


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
    architecture: Architecture,
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
    """Build one exact HiGHS-only child command and declare its artifacts."""

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
        "tes_bess_boundary.e0d48_hamming_primal_recovery",
    ]
    if stage == "candidate":
        candidate = output_dir / f"{architecture.value}_candidate.csv.gz"
        command = [
            *base,
            "candidate",
            *common,
            "--guide",
            str(guide_path),
            "--candidate-output",
            str(candidate),
            "--result-output",
            str(paths["result"]),
            "--threads",
            str(FORMAL_THREADS),
            "--time-limit",
            str(CANDIDATE_SOFT_TIME_LIMIT_SECONDS),
        ]
        return command, (paths["result"], candidate)
    if stage == "repair":
        candidate = output_dir / f"{architecture.value}_candidate.csv.gz"
        solution = output_dir / f"{architecture.value}_solution.csv.gz"
        command = [
            *base,
            "repair",
            *common,
            "--candidate",
            str(candidate),
            "--solution-output",
            str(solution),
            "--result-output",
            str(paths["result"]),
            "--threads",
            str(FORMAL_THREADS),
            "--time-limit",
            str(REPAIR_HARD_WALL_SECONDS),
        ]
        return command, (paths["result"], solution)
    raise ValueError(f"unknown D48 stage: {stage}")


def run_monitored_stage(
    *,
    architecture: Architecture,
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
    """Run one child in a clean process group under the frozen resource gate."""

    if not math.isfinite(hard_wall_seconds) or hard_wall_seconds <= 0.0:
        raise ValueError("D48 stage hard wall must be finite and positive")
    paths = _stage_paths(output_dir, architecture, stage)
    command, artifacts = build_stage_command(
        architecture=architecture,
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
        *artifacts,
    ):
        if path.exists():
            raise FileExistsError(f"D48 refuses to overwrite {path}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D48 formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D48 host memory is below the frozen reserve")

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
    complete = return_code == 0 and result_payload is not None and resource_gate_passed
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
        "result_sha256": _sha256(paths["result"])
        if paths["result"].is_file()
        else None,
        "solver_log_sha256": _sha256(paths["solver_log"]),
        "heartbeat_sha256": _sha256(paths["heartbeat"]),
        "declared_artifact_sha256": {
            path.name: _sha256(path) if path.is_file() else None for path in artifacts
        },
        "active_residual_process_count": int(residual_process_group_active),
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
        raise ValueError(f"D48 {architecture.value} {stage} result hash mismatch")
    return json.loads(paths["result"].read_text(encoding="utf-8"))


def run_architecture(
    *,
    architecture: Architecture,
    output_dir: Path,
    guide_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    hard_wall_seconds: float = ARCHITECTURE_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    """Run the single candidate/repair route for one architecture."""

    architecture_started = perf_counter()
    executions: dict[str, Any] = {}
    executions["candidate"] = run_monitored_stage(
        architecture=architecture,
        stage="candidate",
        output_dir=output_dir,
        hard_wall_seconds=min(CANDIDATE_HARD_WALL_SECONDS, hard_wall_seconds),
        guide_path=guide_path,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    candidate = _load_completed_result(output_dir, architecture, "candidate")
    if (
        candidate is not None
        and candidate.get("status") == "candidate_incumbent_captured"
    ):
        remaining = hard_wall_seconds - (perf_counter() - architecture_started)
        if remaining > 0.0:
            executions["repair"] = run_monitored_stage(
                architecture=architecture,
                stage="repair",
                output_dir=output_dir,
                hard_wall_seconds=min(REPAIR_HARD_WALL_SECONDS, remaining),
                guide_path=guide_path,
                service_path=service_path,
                d40_gate_a_manifest_path=d40_gate_a_manifest_path,
                d41_gate_a_manifest_path=d41_gate_a_manifest_path,
                heat_path=heat_path,
                vre_path=vre_path,
                price_basis_path=price_basis_path,
            )
        else:
            executions["repair"] = {"status": "architecture_hard_wall_exhausted"}
    repair = _load_completed_result(output_dir, architecture, "repair")
    if (
        repair is not None
        and repair.get("status") == "audited_feasible_upper_bound_recovered"
    ):
        status = "audited_feasible_upper_bound_recovered"
    elif candidate is None:
        status = "candidate_process_or_resource_failure"
    elif candidate.get("status") == "engineering_mip_infeasible_under_original_bounds":
        status = "engineering_mip_infeasible_under_original_bounds"
    elif candidate.get("status") != "candidate_incumbent_captured":
        status = "no_primal_status_closure"
    else:
        status = "candidate_found_but_repair_failed"
    payload = {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "status": status,
        "architecture": architecture.value,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "runtime_seconds": perf_counter() - architecture_started,
        "guide_sha256": _sha256(guide_path),
        "stage_execution": executions,
        "candidate_status": candidate.get("status") if candidate else None,
        "repair_status": repair.get("status") if repair else None,
        "audited_feasible_upper_bound_cny": (
            repair.get("solution_audit", {}).get("audited_feasible_upper_bound_cny")
            if repair
            else None
        ),
    }
    _write_json(output_dir / f"{architecture.value}_manifest.json", payload)
    return payload


def _guide_mapping(
    *,
    bess_guide_path: Path,
    tes_guide_path: Path,
    hybrid_guide_path: Path,
) -> dict[Architecture, Path]:
    return {
        Architecture.BESS: bess_guide_path,
        Architecture.TES: tes_guide_path,
        Architecture.HYBRID: hybrid_guide_path,
    }


def _validate_formal_inputs(
    *,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_paths: Mapping[Architecture, Path],
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    expected = {
        "service": (service_path, D40_SERVICE_SHA256),
        "d40_gate_a": (d40_gate_a_manifest_path, D40_GATE_A_MANIFEST_SHA256),
        "d41_gate_a": (d41_gate_a_manifest_path, D41_GATE_A_MANIFEST_SHA256),
        "d46_formal_manifest": (d46_formal_manifest_path, D46_FORMAL_MANIFEST_SHA256),
        "d46_postmortem_bundle": (
            d46_postmortem_bundle_path,
            D46_POSTMORTEM_BUNDLE_SHA256,
        ),
        "heat": (heat_path, FORMAL_HEAT_SHA256),
        "vre": (vre_path, LEGACY_VRE_SHA256),
    }
    actual: dict[str, str] = {}
    for name, (path, expected_hash) in expected.items():
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise ValueError(f"D48 formal {name} hash mismatch")
        actual[name] = actual_hash
    for architecture, path in guide_paths.items():
        actual_hash = _sha256(path)
        if actual_hash != D46_GUIDE_SHA256[architecture]:
            raise ValueError(f"D48 formal {architecture.value} guide hash mismatch")
        actual[f"{architecture.value}_guide"] = actual_hash
    price_hash = _tree_sha256(price_basis_path)
    if price_hash != PRICE_BASIS_TREE_SHA256:
        raise ValueError("D48 formal price-basis tree hash mismatch")
    actual["price_basis_tree"] = price_hash
    return actual


def _parse_junit(path: Path, *, no_skips: bool) -> dict[str, Any]:
    root = ElementTree.parse(path).getroot()
    suites = (root,) if root.tag == "testsuite" else tuple(root.findall("testsuite"))
    if not suites:
        raise ValueError(f"D48 Gate A JUnit has no test suites: {path}")
    counts = {
        key: sum(int(float(suite.attrib.get(key, "0"))) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    counts["passed"] = (
        counts["tests"] > 0
        and counts["failures"] == 0
        and counts["errors"] == 0
        and (not no_skips or counts["skipped"] == 0)
    )
    counts["file_sha256"] = _sha256(path)
    return counts


def compile_gate_a_manifest(
    *,
    output_dir: Path,
    build_dir: Path,
    targeted_junit_path: Path,
    full_junit_path: Path,
    ruff_log_path: Path,
    pycompile_log_path: Path,
    git_commit: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_paths: Mapping[Architecture, Path],
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Compile no-solver builds, tests, quality, hashes, and provenance."""

    if output_dir.exists():
        raise FileExistsError(f"D48 Gate A output already exists: {output_dir}")
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise ValueError("D48 Gate A requires a full lowercase Git commit")
    started = perf_counter()
    formal_inputs = _validate_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_paths=guide_paths,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    build_hashes: dict[str, str] = {}
    build_sizes: dict[str, Any] = {}
    for architecture in FORMAL_ARCHITECTURES:
        path = build_dir / f"gate_a_build_{architecture.value}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_id") != BUILD_SCHEMA_ID:
            raise ValueError(f"D48 Gate A {architecture.value} build schema mismatch")
        if payload.get("status") != "gate_a_build_passed":
            raise ValueError(f"D48 Gate A {architecture.value} build failed")
        if payload.get("solver_invoked") is not False:
            raise ValueError(f"D48 Gate A {architecture.value} invoked a solver")
        if payload.get("formal_optimization_invoked") is not False:
            raise ValueError(
                f"D48 Gate A {architecture.value} invoked formal optimization"
            )
        if payload.get("audit", {}).get("passed") is not True:
            raise ValueError(f"D48 Gate A {architecture.value} audit failed")
        build_hashes[architecture.value] = _sha256(path)
        build_sizes[architecture.value] = payload["post_hamming_model_size"]
    tests = {
        "d48_targeted": _parse_junit(targeted_junit_path, no_skips=True),
        "full_package": _parse_junit(full_junit_path, no_skips=False),
    }
    if not all(item["passed"] for item in tests.values()):
        raise ValueError("D48 Gate A test evidence failed")
    quality = {
        "ruff": {
            "sentinel_present": "D48_RUFF_PASSED"
            in ruff_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(ruff_log_path),
        },
        "pycompile": {
            "sentinel_present": "D48_PYCOMPILE_PASSED"
            in pycompile_log_path.read_text(encoding="utf-8"),
            "file_sha256": _sha256(pycompile_log_path),
        },
    }
    if not all(item["sentinel_present"] for item in quality.values()):
        raise ValueError("D48 Gate A quality sentinel is missing")
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
        "formal_input_sha256": formal_inputs,
        "build_audit_sha256": build_hashes,
        "build_model_size": build_sizes,
        "test_evidence": tests,
        "quality_evidence": quality,
        "provenance": {
            "git_commit": git_commit,
            "code_sha256": _code_hashes(),
            "test_sha256": {
                name: _sha256(tests_dir / name)
                for name in (
                    "test_e0d48_hamming_primal_recovery.py",
                    "test_e0d48_monitored_executor.py",
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
        raise ValueError("D48 Gate A schema mismatch")
    if manifest.get("status") != "gate_a_passed":
        raise ValueError("D48 formal run requires a passed Gate A")
    if manifest.get("formal_optimization_invoked") is not False:
        raise ValueError("D48 Gate A unexpectedly invoked formal optimization")
    if manifest.get("formal_run_permitted") is not True:
        raise ValueError("D48 Gate A did not permit the formal run")
    if manifest.get("audit", {}).get("passed") is not True:
        raise ValueError("D48 Gate A audit is not passed")
    if execution.get("status") != "complete":
        raise ValueError("D48 Gate A execution is incomplete")
    if execution.get("manifest_sha256") != manifest_hash:
        raise ValueError("D48 Gate A execution hash mismatch")
    if manifest.get("provenance", {}).get("code_sha256") != _code_hashes():
        raise ValueError("D48 formal source differs from Gate A")
    return {
        "manifest_sha256": manifest_hash,
        "execution_sha256": _sha256(execution_path),
        "git_commit": manifest.get("provenance", {}).get("git_commit"),
        "passed": True,
    }


def run_formal_batch(
    *,
    output_dir: Path,
    gate_a_manifest_path: Path,
    gate_a_execution_path: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d46_formal_manifest_path: Path,
    d46_postmortem_bundle_path: Path,
    guide_paths: Mapping[Architecture, Path],
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    """Run the only permitted D48 batch in BESS/TES/Hybrid order."""

    if output_dir.exists():
        raise FileExistsError(f"D48 formal output already exists: {output_dir}")
    gate_a = _validate_gate_a(gate_a_manifest_path, gate_a_execution_path)
    formal_inputs = _validate_formal_inputs(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        d46_formal_manifest_path=d46_formal_manifest_path,
        d46_postmortem_bundle_path=d46_postmortem_bundle_path,
        guide_paths=guide_paths,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    available = _available_memory_gib()
    if available is None or available < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D48 formal host does not satisfy the memory reserve")
    output_dir.mkdir(parents=True)
    started = perf_counter()
    architectures: dict[str, dict[str, Any]] = {}
    for architecture in FORMAL_ARCHITECTURES:
        elapsed = perf_counter() - started
        if elapsed >= BATCH_HARD_WALL_SECONDS:
            architectures[architecture.value] = {"status": "batch_hard_wall_exhausted"}
            continue
        architectures[architecture.value] = run_architecture(
            architecture=architecture,
            output_dir=output_dir,
            guide_path=guide_paths[architecture],
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            hard_wall_seconds=min(
                ARCHITECTURE_HARD_WALL_SECONDS, BATCH_HARD_WALL_SECONDS - elapsed
            ),
        )
    success_count = sum(
        item.get("status") == "audited_feasible_upper_bound_recovered"
        for item in architectures.values()
    )
    artifact_hashes = {
        str(path.relative_to(output_dir)).replace("\\", "/"): _sha256(path)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != "formal_manifest.json"
    }
    payload = {
        "schema_id": FORMAL_SCHEMA_ID,
        "status": (
            "all_architecture_upper_bounds_recovered"
            if success_count == len(FORMAL_ARCHITECTURES)
            else "partial_or_no_upper_bound_recovery"
        ),
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "architecture_order": [item.value for item in FORMAL_ARCHITECTURES],
        "successful_architecture_count": success_count,
        "runtime_seconds": perf_counter() - started,
        "gate_a": gate_a,
        "formal_input_sha256": formal_inputs,
        "architecture": architectures,
        "resource_contract": {
            "threads_per_stage": FORMAL_THREADS,
            "candidate_soft_time_limit_seconds": CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
            "candidate_hard_wall_seconds": CANDIDATE_HARD_WALL_SECONDS,
            "repair_hard_wall_seconds": REPAIR_HARD_WALL_SECONDS,
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


def _add_shared_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--d46-formal-manifest", type=Path, required=True)
    parser.add_argument("--d46-postmortem-bundle", type=Path, required=True)
    parser.add_argument("--bess-guide", type=Path, required=True)
    parser.add_argument("--tes-guide", type=Path, required=True)
    parser.add_argument("--hybrid-guide", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gate_a = commands.add_parser("gate-a-compile")
    gate_a.add_argument("--output-dir", type=Path, required=True)
    gate_a.add_argument("--build-dir", type=Path, required=True)
    gate_a.add_argument("--targeted-junit", type=Path, required=True)
    gate_a.add_argument("--full-junit", type=Path, required=True)
    gate_a.add_argument("--ruff-log", type=Path, required=True)
    gate_a.add_argument("--pycompile-log", type=Path, required=True)
    gate_a.add_argument("--git-commit", required=True)
    _add_shared_inputs(gate_a)
    formal = commands.add_parser("formal-batch")
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
        "guide_paths": _guide_mapping(
            bess_guide_path=args.bess_guide,
            tes_guide_path=args.tes_guide,
            hybrid_guide_path=args.hybrid_guide,
        ),
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "gate-a-compile":
        compile_gate_a_manifest(
            output_dir=args.output_dir,
            build_dir=args.build_dir,
            targeted_junit_path=args.targeted_junit,
            full_junit_path=args.full_junit,
            ruff_log_path=args.ruff_log,
            pycompile_log_path=args.pycompile_log,
            git_commit=args.git_commit,
            **_shared_kwargs(args),
        )
        return
    if args.command == "formal-batch":
        run_formal_batch(
            output_dir=args.output_dir,
            gate_a_manifest_path=args.gate_a_manifest,
            gate_a_execution_path=args.gate_a_execution,
            **_shared_kwargs(args),
        )
        return
    raise AssertionError(f"unhandled D48 executor command: {args.command}")


if __name__ == "__main__":
    main()
