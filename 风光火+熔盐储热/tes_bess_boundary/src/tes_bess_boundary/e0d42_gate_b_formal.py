"""E0-D-42 formal full-year preparation and architecture-order driver.

The formal driver binds the model-agnostic parent executor to the locked
D40/D41 8784-hour planning models and the passed D42 structure manifest.  It
rebuilds each requested LP once, runs exactly one explicit presolve, verifies
both native fingerprints, stores one compressed presolved LP, and only then
allows the preregistered B1/B2 execution plan.

The module also rebuilds BESS R0 without optimization before reusing the D41
strict lower bound.  It never converts a lower bound into a capacity, feasible
upper bound, project TAC, or technology ranking.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    _linearity_audit,
    _sha256,
    _write_json,
)
from tes_bess_boundary.e0d40_gate_b_solver import _build_gate_b_model
from tes_bess_boundary.e0d41_gate_b_lower_bound import (
    _load_locked_d41_gate_a,
    compile_architecture_manifest,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
)
from tes_bess_boundary.e0d42_full_year_structure_gate import (
    CASE_FILE_TEMPLATE,
    CASE_SCHEMA_ID,
    HYBRID_TOPOLOGY_NAME,
    MANIFEST_NAME as STRUCTURE_MANIFEST_NAME,
    MANIFEST_SCHEMA_ID as STRUCTURE_MANIFEST_SCHEMA_ID,
    STRUCTURE_CASES,
    _input_hashes,
)
from tes_bess_boundary.e0d42_gate_b_executor import (
    AGGREGATE_RSS_LIMIT_GIB,
    HEARTBEAT_INTERVAL_SECONDS,
    HOST_MEMORY_RESERVE_GIB,
    MONITOR_INTERVAL_SECONDS,
    PROCESS_RSS_LIMIT_GIB,
    TERMINATION_GRACE_SECONDS,
    TOTAL_LP_PARENT_WALL_SECONDS,
    _atomic_write_json,
    _available_memory_gib,
    _process_rss_gib,
    _process_tree_rss_gib,
    _terminate_process_group,
    monitor_stop_reason,
    read_lp_archive,
    run_frozen_lp_plan,
    write_lp_archive,
)
from tes_bess_boundary.e0d42_native_highs_certificate import (
    SUPPORTED_HIGHS_VERSION,
    explicit_presolve,
    translate_pyomo_model,
)
from tes_bess_boundary.model import Architecture


PREPARE_SCHEMA_ID = "tes_bess_boundary.e0d42_formal_lp_prepare.v1"
PREPARE_EXECUTION_SCHEMA_ID = f"{PREPARE_SCHEMA_ID}.execution"
BESS_REUSE_SCHEMA_ID = "tes_bess_boundary.e0d42_bess_reuse.v1"
BESS_REUSE_EXECUTION_SCHEMA_ID = f"{BESS_REUSE_SCHEMA_ID}.execution"
CASE_MANIFEST_SCHEMA_ID = "tes_bess_boundary.e0d42_formal_case_manifest.v1"
CASE_EXECUTION_SCHEMA_ID = f"{CASE_MANIFEST_SCHEMA_ID}.execution"
HYBRID_MANIFEST_SCHEMA_ID = "tes_bess_boundary.e0d42_hybrid_manifest.v1"

D42_STRUCTURE_MANIFEST_SHA256 = (
    "2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1"
)
D41_BESS_STRICT_LOWER_BOUND_CNY = 1_144_950_604.8368804
D41_BESS_MANIFEST_NAME = "gate_b_bess_manifest.json"


@dataclass(frozen=True)
class FormalCase:
    key: str
    architecture: Architecture
    mode: RelaxationMode
    topology_value: int | None


FORMAL_LP_CASES = tuple(
    FormalCase(case.key, case.architecture, case.mode, case.topology_value)
    for case in STRUCTURE_CASES
    if case.key != "tes_r1"
)
FORMAL_CASE_BY_KEY = {case.key: case for case in FORMAL_LP_CASES}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d42_gate_b_formal.py",
        "e0d42_gate_b_executor.py",
        "e0d42_native_highs_certificate.py",
        "e0d42_full_year_structure_gate.py",
        "e0d41_gate_b_lower_bound.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "planning_model.py",
    )
    return {name: _sha256(package / name) for name in names}


def load_locked_structure_case(
    structure_dir: Path,
    case_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one passed Gate A case through the immutable structure manifest."""

    if case_key not in FORMAL_CASE_BY_KEY:
        raise ValueError(f"unknown D42 formal LP case: {case_key}")
    manifest_path = structure_dir / STRUCTURE_MANIFEST_NAME
    if _sha256(manifest_path) != D42_STRUCTURE_MANIFEST_SHA256:
        raise ValueError("D42 formal structure manifest hash mismatch")
    manifest = _load_json(manifest_path)
    if manifest.get("schema_id") != STRUCTURE_MANIFEST_SCHEMA_ID:
        raise ValueError("D42 formal structure manifest schema mismatch")
    if manifest.get("status") != "gate_a_structure_passed":
        raise ValueError("D42 formal Gate A structure did not pass")
    if manifest.get("formal_gate_b_permitted") is not True:
        raise ValueError("D42 formal structure manifest does not permit Gate B")
    if manifest.get("technical_ranking_permitted") is not False:
        raise ValueError("D42 structure manifest unexpectedly permits ranking")
    case_path = structure_dir / CASE_FILE_TEMPLATE.format(case_key=case_key)
    expected_hash = manifest.get("case_sha256", {}).get(case_key)
    if expected_hash is None or _sha256(case_path) != expected_hash:
        raise ValueError("D42 formal structure case hash mismatch")
    payload = _load_json(case_path)
    spec = FORMAL_CASE_BY_KEY[case_key]
    if not all(
        (
            payload.get("schema_id") == CASE_SCHEMA_ID,
            payload.get("status") == "structure_case_passed",
            payload.get("case_key") == case_key,
            payload.get("architecture") == spec.architecture.value,
            payload.get("relaxation_mode") == spec.mode.value,
            payload.get("topology_value") == spec.topology_value,
            payload.get("optimization_invoked") is False,
            payload.get("audit", {}).get("passed") is True,
        )
    ):
        raise ValueError("D42 formal structure case identity mismatch")
    return manifest, payload


def _validate_current_inputs(
    *,
    structure_manifest: dict[str, Any],
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, str]:
    actual = _input_hashes(
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    if actual != structure_manifest.get("input_sha256"):
        raise ValueError("D42 formal inputs differ from the passed structure gate")
    return actual


def _apply_locked_case_relaxation(
    model: object,
    spec: FormalCase,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from pyomo.environ import UnitInterval

    inventory = collect_binary_inventory(model)
    relaxation = apply_relaxation(model, inventory, spec.mode)
    if spec.mode is RelaxationMode.R0:
        if spec.topology_value is not None:
            raise ValueError("D42 R0 cannot carry a topology branch")
        if relaxation["remaining_binary_variable_count"] != 0:
            raise ValueError("D42 R0 did not relax every binary")
    else:
        if inventory.topology_names != (HYBRID_TOPOLOGY_NAME,):
            raise ValueError("D42 Hybrid R1 topology lock changed")
        if spec.topology_value not in {0, 1}:
            raise ValueError("D42 Hybrid R1 branch must be 0 or 1")
        variable = model.find_component(HYBRID_TOPOLOGY_NAME)
        if variable is None:
            raise ValueError("D42 Hybrid topology variable is missing")
        variable.fix(spec.topology_value)
        variable.domain = UnitInterval
    return inventory.to_audit(), relaxation


def _prepare_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "result": output_dir / "prepare_result.json",
        "execution": output_dir / "prepare_execution.json",
        "progress": output_dir / "prepare_progress.json",
        "log": output_dir / "prepare.log",
        "heartbeat": output_dir / "prepare_heartbeat.ndjson",
        "archive": output_dir / "presolved_lp.bin.gz",
    }


def prepare_formal_case_child(
    case_key: str,
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Build, presolve and archive one locked formal LP without optimizing it."""

    spec = FORMAL_CASE_BY_KEY[case_key]
    paths = _prepare_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("result", "archive"):
        if paths[key].exists():
            raise FileExistsError(f"D42 refuses to overwrite {paths[key]}")

    started = perf_counter()

    def progress(state: str, **extra: Any) -> None:
        _atomic_write_json(
            paths["progress"],
            {
                "schema_id": PREPARE_EXECUTION_SCHEMA_ID,
                "case_key": case_key,
                "pid": os.getpid(),
                "state": state,
                "elapsed_seconds": perf_counter() - started,
                **extra,
            },
        )

    progress("loading_locked_evidence")
    structure_manifest, structure_case = load_locked_structure_case(
        structure_dir,
        case_key,
    )
    input_hashes = _validate_current_inputs(
        structure_manifest=structure_manifest,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    d41_gate_a = _load_locked_d41_gate_a(d41_gate_a_manifest_path)

    progress("building_original_full_year_model")
    build_started = perf_counter()
    _case, model, model_size = _build_gate_b_model(
        spec.architecture,
        service_path,
        d40_gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    build_seconds = perf_counter() - build_started
    expected_model_size = d41_gate_a["model_size"][spec.architecture.value]
    if model_size != expected_model_size:
        raise ValueError("D42 formal model size differs from D41 Gate A")
    current_inventory, relaxation = _apply_locked_case_relaxation(model, spec)
    expected_inventory = d41_gate_a["binary_inventory"][spec.architecture.value]
    if current_inventory != expected_inventory:
        raise ValueError("D42 formal binary inventory differs from D41 Gate A")
    linearity = _linearity_audit(model)
    if linearity["nonlinear_component_count"] != 0:
        raise ValueError("D42 formal case is nonlinear")
    if linearity["active_binary_variable_count"] != 0:
        raise ValueError("D42 formal case is not a continuous LP")

    progress("translating_original_lp")
    translate_started = perf_counter()
    translation = translate_pyomo_model(model)
    translate_seconds = perf_counter() - translate_started
    expected_original = structure_case["lp_identity_audit"]["original_lp"]
    if translation.audit["lp_sha256"] != expected_original["lp_sha256"]:
        raise ValueError("D42 formal original LP fingerprint changed")
    if translation.audit["highs_version"] != SUPPORTED_HIGHS_VERSION:
        raise ValueError("D42 formal translation HiGHS version changed")

    progress("explicit_presolve_once")
    presolve_started = perf_counter()
    presolved = explicit_presolve(translation.lp)
    presolve_seconds = perf_counter() - presolve_started
    expected_presolved = structure_case["lp_identity_audit"]["presolved_lp"]
    if (
        presolved.audit["presolved_lp_sha256"]
        != expected_presolved["presolved_lp_sha256"]
    ):
        raise ValueError("D42 formal presolved LP fingerprint changed")

    progress("writing_single_presolved_lp_archive")
    archive = write_lp_archive(presolved.lp, paths["archive"])
    restored, roundtrip = read_lp_archive(
        paths["archive"],
        expected_lp_sha256=presolved.audit["presolved_lp_sha256"],
    )
    del restored
    result = {
        "schema_id": PREPARE_SCHEMA_ID,
        "status": "formal_lp_prepared",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "case_key": case_key,
        "architecture": spec.architecture.value,
        "relaxation_mode": spec.mode.value,
        "topology_value": spec.topology_value,
        "structure_manifest_sha256": D42_STRUCTURE_MANIFEST_SHA256,
        "structure_case_sha256": structure_manifest["case_sha256"][case_key],
        "input_sha256": input_hashes,
        "model_size": model_size,
        "binary_inventory_matches": current_inventory == expected_inventory,
        "relaxation": relaxation,
        "linearity": linearity,
        "original_lp": translation.audit,
        "presolved_lp": presolved.audit,
        "lp_archive": archive,
        "lp_archive_roundtrip": roundtrip,
        "single_original_model_build": True,
        "single_explicit_presolve": True,
        "optimization_invoked": False,
        "timing_seconds": {
            "model_build": build_seconds,
            "translate": translate_seconds,
            "presolve": presolve_seconds,
            "total": perf_counter() - started,
        },
        "provenance": {"code_sha256": _code_hashes()},
        "technical_ranking_permitted": False,
        "audit": {"passed": True},
    }
    _atomic_write_json(paths["result"], result)
    progress("formal_lp_archive_complete", result_sha256=_sha256(paths["result"]))
    return result


def _bess_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "result": output_dir / "bess_reuse_result.json",
        "execution": output_dir / "bess_reuse_execution.json",
        "progress": output_dir / "bess_reuse_progress.json",
        "log": output_dir / "bess_reuse.log",
        "heartbeat": output_dir / "bess_reuse_heartbeat.ndjson",
    }


def build_bess_reuse_child(
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d41_result_dir: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Rebuild BESS R0 and re-audit the exact D41 lower bound without solving."""

    paths = _bess_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if paths["result"].exists():
        raise FileExistsError(f"D42 refuses to overwrite {paths['result']}")
    started = perf_counter()

    def progress(state: str) -> None:
        _atomic_write_json(
            paths["progress"],
            {
                "schema_id": BESS_REUSE_EXECUTION_SCHEMA_ID,
                "pid": os.getpid(),
                "state": state,
                "elapsed_seconds": perf_counter() - started,
            },
        )

    progress("loading_gate_a_and_d41_evidence")
    structure_path = structure_dir / STRUCTURE_MANIFEST_NAME
    if _sha256(structure_path) != D42_STRUCTURE_MANIFEST_SHA256:
        raise ValueError("D42 BESS reuse structure manifest hash mismatch")
    structure_manifest = _load_json(structure_path)
    input_hashes = _validate_current_inputs(
        structure_manifest=structure_manifest,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    d41_gate_a = _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    recomputed_d41 = compile_architecture_manifest(
        architecture=Architecture.BESS,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        result_dir=d41_result_dir,
    )
    existing_manifest_path = d41_result_dir / D41_BESS_MANIFEST_NAME
    existing_manifest = _load_json(existing_manifest_path)
    if existing_manifest != recomputed_d41:
        raise ValueError("D41 BESS manifest differs from independent recompilation")
    reused_bound = recomputed_d41.get("strict_lower_bound_cny")
    if not math.isclose(
        float(reused_bound),
        D41_BESS_STRICT_LOWER_BOUND_CNY,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("D41 BESS strict lower bound changed")

    progress("rebuilding_bess_r0")
    _case, model, model_size = _build_gate_b_model(
        Architecture.BESS,
        service_path,
        d40_gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    if model_size != d41_gate_a["model_size"][Architecture.BESS.value]:
        raise ValueError("D42 BESS model size differs from D41 Gate A")
    inventory = collect_binary_inventory(model)
    inventory_audit = inventory.to_audit()
    if inventory_audit != d41_gate_a["binary_inventory"][Architecture.BESS.value]:
        raise ValueError("D42 BESS binary inventory differs from D41 Gate A")
    relaxation = apply_relaxation(model, inventory, RelaxationMode.R0)
    linearity = _linearity_audit(model)
    if linearity["nonlinear_component_count"] != 0:
        raise ValueError("D42 BESS R0 is nonlinear")
    if linearity["active_binary_variable_count"] != 0:
        raise ValueError("D42 BESS R0 retained a binary variable")

    progress("fingerprinting_bess_r0")
    translation = translate_pyomo_model(model)
    presolved = explicit_presolve(translation.lp)
    result = {
        "schema_id": BESS_REUSE_SCHEMA_ID,
        "status": "bess_d41_bound_reuse_passed",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "architecture": Architecture.BESS.value,
        "relaxation_mode": RelaxationMode.R0.value,
        "structure_manifest_sha256": D42_STRUCTURE_MANIFEST_SHA256,
        "input_sha256": input_hashes,
        "model_size": model_size,
        "binary_inventory": inventory_audit,
        "relaxation": relaxation,
        "linearity": linearity,
        "original_lp": translation.audit,
        "presolved_lp": presolved.audit,
        "d41_bess_manifest_sha256": _sha256(existing_manifest_path),
        "d41_bess_manifest_recompiled_equal": True,
        "reused_strict_lower_bound_cny": reused_bound,
        "formal_lower_bound_eligible": True,
        "optimization_invoked": False,
        "technical_ranking_permitted": False,
        "runtime_seconds": perf_counter() - started,
        "provenance": {"code_sha256": _code_hashes()},
        "audit": {"passed": True},
    }
    _atomic_write_json(paths["result"], result)
    progress("bess_reuse_complete")
    return result


def _run_monitored_build_child(
    *,
    command: list[str],
    schema_id: str,
    stage: str,
    paths: dict[str, Path],
    total_run_started: float,
) -> dict[str, Any]:
    paths["result"].parent.mkdir(parents=True, exist_ok=True)
    for key in ("result", "execution", "log", "heartbeat"):
        if paths[key].exists():
            raise FileExistsError(f"D42 refuses to overwrite {paths[key]}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D42 formal preparation requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D42 host memory is below the frozen reserve")
    started_payload = {
        "schema_id": schema_id,
        "status": "child_starting",
        "stage": stage,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "hard_wall_enforced_by_parent": True,
        "available_memory_before_gib": available_before,
        "resource_thresholds": {
            "total_lp_parent_wall_seconds": TOTAL_LP_PARENT_WALL_SECONDS,
            "process_tree_rss_limit_gib": PROCESS_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
        },
    }
    _atomic_write_json(paths["execution"], started_payload)
    peak_child = 0.0
    peak_aggregate = 0.0
    minimum_available = available_before
    rss_samples = 0
    memory_samples = 0
    stop_reason = None
    termination_signal = None
    stage_started = perf_counter()
    last_heartbeat = -HEARTBEAT_INTERVAL_SECONDS
    with (
        paths["log"].open(
            "w", encoding="utf-8", newline="\n"
        ) as child_log,
        paths["heartbeat"].open(
            "w", encoding="utf-8", newline="\n", buffering=1
        ) as heartbeat_log,
    ):
        process = subprocess.Popen(
            command,
            stdout=child_log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        while process.poll() is None:
            stage_elapsed = perf_counter() - stage_started
            total_elapsed = perf_counter() - total_run_started
            child_tree = _process_tree_rss_gib(process.pid)
            parent_rss = _process_rss_gib(os.getpid())
            available = _available_memory_gib()
            aggregate = (
                child_tree + parent_rss
                if child_tree is not None and parent_rss is not None
                else None
            )
            if child_tree is not None:
                peak_child = max(peak_child, child_tree)
                rss_samples += 1
            if aggregate is not None:
                peak_aggregate = max(peak_aggregate, aggregate)
            if available is not None:
                minimum_available = min(minimum_available, available)
                memory_samples += 1
            if stage_elapsed - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                progress = None
                if paths["progress"].is_file():
                    try:
                        progress = _load_json(paths["progress"])
                    except (json.JSONDecodeError, OSError):
                        progress = {"state": "progress_read_incomplete"}
                heartbeat_log.write(
                    json.dumps(
                        {
                            "stage": stage,
                            "pid": process.pid,
                            "stage_elapsed_seconds": stage_elapsed,
                            "total_elapsed_seconds": total_elapsed,
                            "child_process_tree_rss_gib": child_tree,
                            "parent_child_aggregate_rss_gib": aggregate,
                            "available_memory_gib": available,
                            "child_progress": progress,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                heartbeat_log.flush()
                last_heartbeat = stage_elapsed
            stop_reason = monitor_stop_reason(
                phase_elapsed_seconds=stage_elapsed,
                phase_hard_wall_seconds=TOTAL_LP_PARENT_WALL_SECONDS,
                total_elapsed_seconds=total_elapsed,
                child_tree_rss_gib=child_tree,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
            )
            if stop_reason is not None:
                termination_signal = _terminate_process_group(process)
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.wait()
    result = _load_json(paths["result"]) if paths["result"].is_file() else None
    resource_gate_passed = all(
        (
            stop_reason is None,
            rss_samples > 0,
            memory_samples > 0,
            peak_child < PROCESS_RSS_LIMIT_GIB,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
        )
    )
    complete = return_code == 0 and result is not None and resource_gate_passed
    execution = {
        **started_payload,
        "status": "complete" if complete else "interrupted_or_failed",
        "return_code": return_code,
        "runtime_seconds": perf_counter() - stage_started,
        "total_elapsed_seconds_after": perf_counter() - total_run_started,
        "peak_child_process_tree_rss_gib": peak_child,
        "peak_parent_child_aggregate_rss_gib": peak_aggregate,
        "minimum_available_memory_gib": minimum_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "stop_reason": stop_reason,
        "termination_signal": termination_signal,
        "resource_gate_passed": resource_gate_passed,
        "result_sha256": _sha256(paths["result"]) if paths["result"].is_file() else None,
        "log_sha256": _sha256(paths["log"]),
        "heartbeat_sha256": _sha256(paths["heartbeat"]),
        "progress_sha256": (
            _sha256(paths["progress"]) if paths["progress"].is_file() else None
        ),
    }
    _atomic_write_json(paths["execution"], execution)
    return execution


def _formal_inputs_command(
    command: list[str],
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
        *command,
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


def _load_bess_prerequisite(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not all(
        (
            payload.get("schema_id") == BESS_REUSE_SCHEMA_ID,
            payload.get("status") == "bess_d41_bound_reuse_passed",
            payload.get("formal_lower_bound_eligible") is True,
            payload.get("optimization_invoked") is False,
            payload.get("audit", {}).get("passed") is True,
        )
    ):
        raise ValueError("D42 BESS reuse prerequisite is not eligible")
    execution_path = path.with_name("bess_reuse_execution.json")
    execution = _load_json(execution_path)
    if not all(
        (
            execution.get("schema_id") == BESS_REUSE_EXECUTION_SCHEMA_ID,
            execution.get("status") == "complete",
            execution.get("return_code") == 0,
            execution.get("resource_gate_passed") is True,
            execution.get("stop_reason") is None,
            execution.get("hard_wall_enforced_by_parent") is True,
            execution.get("result_sha256") == _sha256(path),
        )
    ):
        raise ValueError("D42 BESS reuse parent execution is not eligible")
    return payload


def _load_tes_prerequisite(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_id") != CASE_MANIFEST_SCHEMA_ID:
        raise ValueError("D42 TES prerequisite schema mismatch")
    if payload.get("case_key") != "tes_r0":
        raise ValueError("D42 Hybrid requires the TES R0 case manifest")
    if payload.get("formal_lower_bound_eligible") is not True:
        raise ValueError("D42 Hybrid requires a finite TES lower bound")
    execution_path = path.with_name("case_execution.json")
    execution = _load_json(execution_path)
    if not all(
        (
            execution.get("schema_id") == CASE_EXECUTION_SCHEMA_ID,
            execution.get("status") == payload.get("status"),
            execution.get("case_key") == "tes_r0",
            execution.get("case_manifest_sha256") == _sha256(path),
        )
    ):
        raise ValueError("D42 TES parent execution evidence is invalid")
    return payload


def run_formal_case(
    case_key: str,
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    bess_reuse_result_path: Path,
    tes_case_manifest_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    """Prepare and execute one formal LP after enforcing architecture order."""

    spec = FORMAL_CASE_BY_KEY[case_key]
    _load_bess_prerequisite(bess_reuse_result_path)
    tes_prerequisite_sha = None
    if spec.architecture is Architecture.HYBRID:
        if tes_case_manifest_path is None:
            raise ValueError("D42 Hybrid requires a TES case manifest")
        _load_tes_prerequisite(tes_case_manifest_path)
        tes_prerequisite_sha = _sha256(tes_case_manifest_path)
    elif tes_case_manifest_path is not None:
        raise ValueError("D42 TES does not accept a TES prerequisite")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"D42 formal case directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    total_started = perf_counter()
    prepare_paths = _prepare_paths(output_dir)
    command = _formal_inputs_command(
        [
            sys.executable,
            "-u",
            "-m",
            "tes_bess_boundary.e0d42_gate_b_formal",
            "_prepare-child",
            "--case-key",
            case_key,
        ],
        structure_dir=structure_dir,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        output_dir=output_dir,
    )
    prepare_execution = _run_monitored_build_child(
        command=command,
        schema_id=PREPARE_EXECUTION_SCHEMA_ID,
        stage=f"prepare_{case_key}",
        paths=prepare_paths,
        total_run_started=total_started,
    )
    if prepare_execution.get("status") != "complete":
        raise RuntimeError("D42 formal LP preparation did not complete")
    prepare_result = _load_json(prepare_paths["result"])
    if not all(
        (
            prepare_result.get("schema_id") == PREPARE_SCHEMA_ID,
            prepare_result.get("status") == "formal_lp_prepared",
            prepare_result.get("case_key") == case_key,
            prepare_result.get("audit", {}).get("passed") is True,
            prepare_result.get("optimization_invoked") is False,
            prepare_execution.get("result_sha256") == _sha256(prepare_paths["result"]),
        )
    ):
        raise ValueError("D42 formal LP preparation evidence is invalid")
    lp_sha256 = prepare_result["presolved_lp"]["presolved_lp_sha256"]
    _lp, archive_audit = read_lp_archive(
        prepare_paths["archive"],
        expected_lp_sha256=lp_sha256,
    )
    del _lp
    if archive_audit["archive_sha256"] != prepare_result["lp_archive"][
        "archive_sha256"
    ]:
        raise ValueError("D42 formal LP archive hash changed after preparation")

    plan = run_frozen_lp_plan(
        lp_archive_path=prepare_paths["archive"],
        expected_lp_sha256=lp_sha256,
        output_dir=output_dir,
        total_run_started=total_started,
    )
    lp_manifest_path = output_dir / "lp_manifest.json"
    lp_execution_path = output_dir / "lp_execution.json"
    lp_manifest = plan["manifest"]
    case_manifest = {
        "schema_id": CASE_MANIFEST_SCHEMA_ID,
        "status": lp_manifest["status"],
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "case_key": case_key,
        "architecture": spec.architecture.value,
        "relaxation_mode": spec.mode.value,
        "topology_value": spec.topology_value,
        "structure_manifest_sha256": D42_STRUCTURE_MANIFEST_SHA256,
        "bess_reuse_result_sha256": _sha256(bess_reuse_result_path),
        "bess_reuse_execution_sha256": _sha256(
            bess_reuse_result_path.with_name("bess_reuse_execution.json")
        ),
        "tes_case_manifest_sha256": tes_prerequisite_sha,
        "tes_case_execution_sha256": (
            _sha256(tes_case_manifest_path.with_name("case_execution.json"))
            if tes_case_manifest_path is not None
            else None
        ),
        "prepare_result_sha256": _sha256(prepare_paths["result"]),
        "prepare_execution_sha256": _sha256(prepare_paths["execution"]),
        "lp_manifest_sha256": _sha256(lp_manifest_path),
        "lp_execution_sha256": _sha256(lp_execution_path),
        "lp_sha256": lp_sha256,
        "formal_lower_bound_eligible": lp_manifest[
            "formal_lower_bound_eligible"
        ],
        "formal_lower_bound_decimal": lp_manifest[
            "formal_lower_bound_decimal"
        ],
        "formal_lower_bound_float": lp_manifest["formal_lower_bound_float"],
        "tes_r0_certificate_covers_r1": case_key == "tes_r0",
        "technical_ranking_permitted": False,
    }
    case_manifest_path = output_dir / "case_manifest.json"
    _atomic_write_json(case_manifest_path, case_manifest)
    case_execution = {
        "schema_id": CASE_EXECUTION_SCHEMA_ID,
        "status": case_manifest["status"],
        "case_key": case_key,
        "case_manifest_sha256": _sha256(case_manifest_path),
        "runtime_seconds": perf_counter() - total_started,
        "total_parent_wall_seconds": TOTAL_LP_PARENT_WALL_SECONDS,
        "technical_ranking_permitted": False,
    }
    _atomic_write_json(output_dir / "case_execution.json", case_execution)
    return {"manifest": case_manifest, "execution": case_execution}


def run_bess_reuse(
    *,
    structure_dir: Path,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    d41_result_dir: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"D42 BESS reuse directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _bess_paths(output_dir)
    started = perf_counter()
    command = _formal_inputs_command(
        [
            sys.executable,
            "-u",
            "-m",
            "tes_bess_boundary.e0d42_gate_b_formal",
            "_bess-reuse-child",
            "--d41-result-dir",
            str(d41_result_dir),
        ],
        structure_dir=structure_dir,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
        output_dir=output_dir,
    )
    execution = _run_monitored_build_child(
        command=command,
        schema_id=BESS_REUSE_EXECUTION_SCHEMA_ID,
        stage="bess_reuse_build_only",
        paths=paths,
        total_run_started=started,
    )
    if execution.get("status") != "complete":
        raise RuntimeError("D42 BESS reuse audit did not complete")
    result = _load_bess_prerequisite(paths["result"])
    if execution.get("result_sha256") != _sha256(paths["result"]):
        raise ValueError("D42 BESS reuse result hash mismatch")
    return {"result": result, "execution": execution}


def _load_case_manifest(path: Path, case_key: str) -> dict[str, Any]:
    payload = _load_json(path)
    if payload.get("schema_id") != CASE_MANIFEST_SCHEMA_ID:
        raise ValueError(f"D42 case manifest schema mismatch: {case_key}")
    if payload.get("case_key") != case_key:
        raise ValueError(f"D42 case manifest identity mismatch: {case_key}")
    if payload.get("formal_lower_bound_eligible") is not True:
        raise ValueError(f"D42 case lacks a finite lower bound: {case_key}")
    if payload.get("status") not in {
        "certified_optimal_relaxation",
        "certified_finite_lower_bound",
    }:
        raise ValueError(f"D42 case classification is ineligible: {case_key}")
    return payload


def compile_hybrid_manifest(
    *,
    hybrid_r0_path: Path,
    hybrid_r1_bess0_path: Path,
    hybrid_r1_bess1_path: Path,
) -> dict[str, Any]:
    """Apply the frozen min-over-branches then max-over-relaxations rule."""

    r0 = _load_case_manifest(hybrid_r0_path, "hybrid_r0")
    branch0 = _load_case_manifest(hybrid_r1_bess0_path, "hybrid_r1_bess0")
    branch1 = _load_case_manifest(hybrid_r1_bess1_path, "hybrid_r1_bess1")
    r0_bound = Decimal(r0["formal_lower_bound_decimal"])
    branch_bounds = (
        Decimal(branch0["formal_lower_bound_decimal"]),
        Decimal(branch1["formal_lower_bound_decimal"]),
    )
    r1_bound = min(branch_bounds)
    final_bound = max(r0_bound, r1_bound)
    classifications = {r0["status"], branch0["status"], branch1["status"]}
    status = (
        "certified_optimal_relaxation"
        if classifications == {"certified_optimal_relaxation"}
        else "certified_finite_lower_bound"
    )
    return {
        "schema_id": HYBRID_MANIFEST_SCHEMA_ID,
        "status": status,
        "architecture": Architecture.HYBRID.value,
        "hybrid_r0_lower_bound_decimal": str(r0_bound),
        "hybrid_r1_branch_lower_bounds_decimal": [
            str(value) for value in branch_bounds
        ],
        "hybrid_r1_lower_bound_decimal": str(r1_bound),
        "formal_lower_bound_decimal": str(final_bound),
        "formal_lower_bound_float": float(final_bound),
        "r1_aggregation": "minimum_across_complete_topology_branches",
        "final_aggregation": "maximum_of_r0_and_eligible_r1",
        "case_manifest_sha256": {
            "hybrid_r0": _sha256(hybrid_r0_path),
            "hybrid_r1_bess0": _sha256(hybrid_r1_bess0_path),
            "hybrid_r1_bess1": _sha256(hybrid_r1_bess1_path),
        },
        "formal_lower_bound_eligible": True,
        "technical_ranking_permitted": False,
    }


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
    bess = commands.add_parser("run-bess-reuse")
    _add_formal_inputs(bess)
    bess.add_argument("--d41-result-dir", type=Path, required=True)

    bess_child = commands.add_parser("_bess-reuse-child")
    _add_formal_inputs(bess_child)
    bess_child.add_argument("--d41-result-dir", type=Path, required=True)

    run_case = commands.add_parser("run-case")
    _add_formal_inputs(run_case)
    run_case.add_argument("--case-key", choices=tuple(FORMAL_CASE_BY_KEY), required=True)
    run_case.add_argument("--bess-reuse-result", type=Path, required=True)
    run_case.add_argument("--tes-case-manifest", type=Path)

    prepare = commands.add_parser("_prepare-child")
    _add_formal_inputs(prepare)
    prepare.add_argument("--case-key", choices=tuple(FORMAL_CASE_BY_KEY), required=True)

    hybrid = commands.add_parser("compile-hybrid")
    hybrid.add_argument("--hybrid-r0", type=Path, required=True)
    hybrid.add_argument("--hybrid-r1-bess0", type=Path, required=True)
    hybrid.add_argument("--hybrid-r1-bess1", type=Path, required=True)
    hybrid.add_argument("--output", type=Path, required=True)
    return parser


def _formal_kwargs(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "structure_dir": args.structure_dir,
        "service_path": args.service_path,
        "d40_gate_a_manifest_path": args.d40_gate_a_manifest_path,
        "d41_gate_a_manifest_path": args.d41_gate_a_manifest_path,
        "heat_path": args.heat_path,
        "vre_path": args.vre_path,
        "price_basis_path": args.price_basis_path,
        "output_dir": args.output_dir,
    }


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run-bess-reuse":
        payload = run_bess_reuse(
            **_formal_kwargs(args),
            d41_result_dir=args.d41_result_dir,
        )
    elif args.command == "_bess-reuse-child":
        payload = build_bess_reuse_child(
            **_formal_kwargs(args),
            d41_result_dir=args.d41_result_dir,
        )
    elif args.command == "run-case":
        payload = run_formal_case(
            args.case_key,
            **_formal_kwargs(args),
            bess_reuse_result_path=args.bess_reuse_result,
            tes_case_manifest_path=args.tes_case_manifest,
        )
    elif args.command == "_prepare-child":
        payload = prepare_formal_case_child(
            args.case_key,
            **_formal_kwargs(args),
        )
    elif args.command == "compile-hybrid":
        payload = compile_hybrid_manifest(
            hybrid_r0_path=args.hybrid_r0,
            hybrid_r1_bess0_path=args.hybrid_r1_bess0,
            hybrid_r1_bess1_path=args.hybrid_r1_bess1,
        )
        _write_json(args.output, payload)
    else:
        raise AssertionError(f"unhandled command: {args.command}")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
