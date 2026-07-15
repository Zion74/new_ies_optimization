"""E0-D-41 Gate B strict full-year lower-bound execution.

The only admissible numerical lower bounds are HiGHS dual bounds from the
locked 8784-hour R0/R1 relaxations.  Every solve runs in a clean child process;
the parent independently enforces the hard wall clock and resource gates.
R1 primal values are retained only as a candidate guide for Gate C.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from time import perf_counter
from typing import Any

from tes_bess_boundary.e0d40_full_year_compute_gate import (
    CLAIM_SCOPE,
    FORMAL_PROJECT_TAC_READY,
    FULL_YEAR_HOURS,
    _input_hashes,
    _linearity_audit,
    _sha256,
    _write_json,
)
from tes_bess_boundary.e0d40_gate_b_solver import (
    FORMAL_ARCHITECTURES,
    GATE_A_MANIFEST_SHA256 as D40_GATE_A_MANIFEST_SHA256,
    SERVICE_SHA256,
    _build_gate_b_model,
    _finite_or_none,
    _termination_name,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    GATE_A_SCHEMA_ID as D41_GATE_A_SCHEMA_ID,
    BinaryInventory,
    RelaxationMode,
    apply_relaxation,
    collect_binary_inventory,
)
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.solver import create_highs_solver


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d41_gate_b_lower_bound.v1"
EXECUTION_SCHEMA_ID = f"{RESULT_SCHEMA_ID}.execution"
ARCHITECTURE_SCHEMA_ID = "tes_bess_boundary.e0d41_gate_b_architecture.v1"
GUIDE_SCHEMA_ID = "tes_bess_boundary.e0d41_r1_candidate_guide.v1"

D41_GATE_A_MANIFEST_SHA256 = (
    "50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937"
)

FORMAL_THREADS = 12
FORMAL_RANDOM_SEED = 0
SOLVER_FEASIBILITY_TOLERANCE = 1e-7
R0_SOFT_TIME_LIMIT_SECONDS = 600.0
R0_HARD_WALL_SECONDS = 720.0
R1_SOFT_TIME_LIMIT_SECONDS = 1_200.0
R1_HARD_WALL_SECONDS = 1_320.0
ARCHITECTURE_HARD_WALL_SECONDS = 7_200.0

PROCESS_RSS_LIMIT_GIB = 35.0
AGGREGATE_RSS_LIMIT_GIB = 75.0
HOST_MEMORY_RESERVE_GIB = 15.0
MONITOR_INTERVAL_SECONDS = 0.5
HEARTBEAT_INTERVAL_SECONDS = 5.0
TERMINATION_GRACE_SECONDS = 30.0
OBJECTIVE_RELATIVE_TOLERANCE = 1e-8

RELAXATION_ORDER = (RelaxationMode.R0, RelaxationMode.R1)


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _mode_token(mode: RelaxationMode) -> str:
    if not isinstance(mode, RelaxationMode):
        raise ValueError("D41 Gate B mode must be RelaxationMode.R0 or R1")
    return "r0" if mode is RelaxationMode.R0 else "r1"


def _time_limits(mode: RelaxationMode) -> tuple[float, float]:
    if mode is RelaxationMode.R0:
        return R0_SOFT_TIME_LIMIT_SECONDS, R0_HARD_WALL_SECONDS
    if mode is RelaxationMode.R1:
        return R1_SOFT_TIME_LIMIT_SECONDS, R1_HARD_WALL_SECONDS
    raise ValueError("unknown D41 relaxation mode")


def _load_locked_d41_gate_a(path: Path) -> dict[str, Any]:
    if _sha256(path) != D41_GATE_A_MANIFEST_SHA256:
        raise ValueError("D41 Gate B Gate A manifest hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != D41_GATE_A_SCHEMA_ID:
        raise ValueError("D41 Gate B Gate A schema mismatch")
    if payload.get("status") != "gate_a_passed":
        raise ValueError("D41 Gate B requires passed Gate A evidence")
    if payload.get("solver_invoked") is not False:
        raise ValueError("D41 Gate A unexpectedly invoked a solver")
    if payload.get("audit", {}).get("passed") is not True:
        raise ValueError("D41 Gate A audit is not passed")
    if payload.get("representative_period_input_used") is not False:
        raise ValueError("D41 Gate B cannot use representative periods")
    if payload.get("service_contract_sha256") != SERVICE_SHA256:
        raise ValueError("D41 Gate A service hash mismatch")
    if payload.get("d40_gate_a_manifest_sha256") != D40_GATE_A_MANIFEST_SHA256:
        raise ValueError("D41 Gate A D40 manifest reference mismatch")
    if payload.get("relaxation_containment") != {
        "candidate_blocks_provide_formal_bound": False,
        "full_year_repair_required_for_upper_bound": True,
        "r0_contains_original_milp": True,
        "r1_contains_original_milp": True,
    }:
        raise ValueError("D41 Gate A relaxation containment record mismatch")
    return payload


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d41_gate_b_lower_bound.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
    )
    return {name: _sha256(package / name) for name in names}


def _inventory_lock_audit(
    inventory: BinaryInventory,
    architecture: Architecture,
    gate_a: dict[str, Any],
) -> dict[str, Any]:
    actual = inventory.to_audit()
    expected = gate_a["binary_inventory"][architecture.value]
    keys = (
        "all_binary_variable_count",
        "topology_binary_variable_count",
        "operational_binary_variable_count",
        "classification_complete",
        "all_binary_names_sha256",
        "topology_binary_names_sha256",
        "operational_binary_names_sha256",
        "component_counts",
        "topology_component_allowlist",
    )
    mismatches = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in keys
        if actual.get(key) != expected.get(key)
    }
    return {
        "expected": expected,
        "actual": actual,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def _objective_metadata(model: object) -> tuple[object, dict[str, Any]]:
    from pyomo.environ import Objective, minimize

    objectives = list(
        model.component_data_objects(Objective, active=True, descend_into=True)
    )
    if len(objectives) != 1:
        raise ValueError(
            f"D41 Gate B requires exactly one active objective, got {len(objectives)}"
        )
    objective = objectives[0]
    audit = {
        "active_objective_count": 1,
        "objective_name": objective.name,
        "objective_sense": "minimize" if objective.sense == minimize else "maximize",
        "expected_objective_name": "planning_cost",
        "expected_objective_sense": "minimize",
    }
    audit["passed"] = (
        audit["objective_name"] == audit["expected_objective_name"]
        and audit["objective_sense"] == audit["expected_objective_sense"]
    )
    return objective, audit


def audit_dual_bound(
    *,
    lower_bound: float | None,
    upper_bound: float | None,
    objective_audit_passed: bool,
    domain_audit_passed: bool,
    service_audit_passed: bool,
    linearity_audit_passed: bool,
    objective_value: float | None = None,
) -> dict[str, Any]:
    """Determine whether a reported minimization dual is formal evidence."""

    finite_lower = lower_bound is not None and math.isfinite(lower_bound)
    finite_upper = upper_bound is not None and math.isfinite(upper_bound)
    direction_correct = finite_lower and (
        not finite_upper or lower_bound <= upper_bound + 1e-7
    )
    objective_match: bool | None = None
    if objective_value is not None and finite_upper:
        objective_match = math.isclose(
            objective_value,
            upper_bound,
            rel_tol=OBJECTIVE_RELATIVE_TOLERANCE,
            abs_tol=1e-4,
        )
    scale_consistent = objective_match is not False
    passed = all(
        (
            finite_lower,
            direction_correct,
            objective_audit_passed,
            domain_audit_passed,
            service_audit_passed,
            linearity_audit_passed,
            scale_consistent,
        )
    )
    return {
        "finite_lower_bound": finite_lower,
        "finite_upper_bound": finite_upper,
        "minimization_bound_direction_correct": direction_correct,
        "loaded_objective_matches_upper_bound": objective_match,
        "objective_scale_consistent": scale_consistent,
        "passed": passed,
    }


def _service_audit(model: object, case: object) -> dict[str, Any]:
    from pyomo.environ import value

    weighted_hours = float(value(model.annual_weighted_hours))
    audit = {
        "period_count": case.timeseries.period_count,
        "weighted_annual_hours": weighted_hours,
        "single_full_year_dispatch_block": len(case.horizon.dispatch_blocks) == 1,
        "curtailment_constraint_active": bool(
            model.annual_curtailment_service.active
        ),
        "pcc_export_constraint_active": bool(
            model.annual_pcc_export_service.active
        ),
        "representative_period_input_used": False,
    }
    audit["passed"] = all(
        (
            audit["period_count"] == FULL_YEAR_HOURS,
            math.isclose(weighted_hours, FULL_YEAR_HOURS, abs_tol=1e-9),
            audit["single_full_year_dispatch_block"],
            audit["curtailment_constraint_active"],
            audit["pcc_export_constraint_active"],
        )
    )
    return audit


def _guide_path(result_path: Path) -> Path:
    return result_path.with_name(f"{result_path.stem}_guide.csv.gz")


def write_candidate_guide(
    model: object,
    inventory: BinaryInventory,
    output_path: Path,
) -> dict[str, Any]:
    """Persist a deterministic, compressed R1 solution for candidate generation."""

    from pyomo.environ import Var, value

    variables = sorted(
        model.component_data_objects(Var, active=True, descend_into=True),
        key=lambda item: item.name,
    )
    values: list[tuple[str, float, str]] = []
    topology = set(inventory.topology_names)
    operational = set(inventory.operational_names)
    for variable in variables:
        raw = _finite_or_none(value(variable, exception=False))
        if raw is None:
            raise ValueError(f"candidate guide variable is not finite: {variable.name}")
        variable_class = (
            "topology_binary"
            if variable.name in topology
            else (
                "operational_binary"
                if variable.name in operational
                else "continuous"
            )
        )
        values.append((variable.name, raw, variable_class))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw_stream:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_stream,
            mtime=0,
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(("variable_name", "value", "variable_class"))
                for name, number, variable_class in values:
                    writer.writerow((name, format(number, ".17g"), variable_class))
    return {
        "schema_id": GUIDE_SCHEMA_ID,
        "candidate_only": True,
        "formal_bound_eligible": False,
        "file_name": output_path.name,
        "file_sha256": _sha256(output_path),
        "variable_row_count": len(values),
        "all_values_finite": True,
        "all_original_binary_values_included": (
            len(topology) + len(operational) == len(inventory.all_names)
        ),
    }


def _solve_relaxed_model(
    *,
    model: object,
    objective: object,
    mode: RelaxationMode,
    inventory: BinaryInventory,
    guide_path: Path,
    soft_time_limit_seconds: float,
) -> dict[str, Any]:
    """Invoke HiGHS and return raw bounds plus a candidate-only R1 guide."""

    from pyomo.environ import value

    import highspy

    termination = "solver_error"
    lower_bound: float | None = None
    upper_bound: float | None = None
    objective_value: float | None = None
    solution_loaded = False
    guide: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        solver = create_highs_solver(
            threads=FORMAL_THREADS,
            random_seed=FORMAL_RANDOM_SEED,
            mip_rel_gap=0.0,
        )
        solver.options["time_limit"] = soft_time_limit_seconds
        solver.options["primal_feasibility_tolerance"] = (
            SOLVER_FEASIBILITY_TOLERANCE
        )
        solver.options["dual_feasibility_tolerance"] = (
            SOLVER_FEASIBILITY_TOLERANCE
        )
        solver.options["mip_feasibility_tolerance"] = (
            SOLVER_FEASIBILITY_TOLERANCE
        )
        results = solver.solve(model, tee=True, load_solutions=False)
        termination = _termination_name(results.solver.termination_condition)
        lower_bound = _finite_or_none(getattr(results.problem, "lower_bound", None))
        upper_bound = _finite_or_none(getattr(results.problem, "upper_bound", None))
        if upper_bound is not None:
            if len(results.solution) > 0:
                model.solutions.load_from(results)
            else:
                solver.load_vars()
            solution_loaded = True
            objective_value = _finite_or_none(value(objective, exception=False))
            if mode is RelaxationMode.R1:
                guide = write_candidate_guide(model, inventory, guide_path)
    except Exception as error:  # noqa: BLE001 - preserve solver evidence
        error_type = type(error).__name__
        error_message = str(error)
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    payload = {
        "termination_condition": termination,
        "objective_lower_bound_cny": lower_bound,
        "objective_upper_bound_cny": upper_bound,
        "loaded_objective_value_cny": objective_value,
        "solution_loaded": solution_loaded,
        "candidate_guide": guide,
        "solver_runtime_seconds": perf_counter() - started,
    }
    if error_type is not None:
        payload["error_type"] = error_type
        payload["error_message"] = error_message
    return payload


def solve_child(
    *,
    architecture: Architecture,
    mode: RelaxationMode,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Build and solve one formal lower-bound relaxation in a child process."""

    if architecture not in FORMAL_ARCHITECTURES:
        raise ValueError("D41 Gate B requires BESS, TES, or Hybrid")
    gate_a = _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    soft_limit, hard_limit = _time_limits(mode)
    base = {
        "schema_id": RESULT_SCHEMA_ID,
        "status": "build_pending",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "formal_lower_bound_eligible": False,
        "candidate_only": False,
        "architecture": architecture.value,
        "relaxation_mode": mode.value,
        "service_contract_sha256": _sha256(service_path),
        "d40_gate_a_manifest_sha256": _sha256(d40_gate_a_manifest_path),
        "d41_gate_a_manifest_sha256": _sha256(d41_gate_a_manifest_path),
        "representative_period_input_used": False,
        "solver": {
            "name": "appsi_highs",
            "threads": FORMAL_THREADS,
            "random_seed": FORMAL_RANDOM_SEED,
            "soft_time_limit_seconds": soft_limit,
            "parent_hard_wall_seconds": hard_limit,
            "primal_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "dual_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "mip_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "warm_start_used": False,
        },
        "provenance": {
            **_input_hashes(heat_path, vre_path, price_basis_path),
            "code_sha256": _code_hashes(),
        },
    }
    build_started = perf_counter()
    try:
        case, model, original_model_size = _build_gate_b_model(
            architecture,
            service_path,
            d40_gate_a_manifest_path,
            heat_path,
            vre_path,
            price_basis_path,
        )
        if original_model_size != gate_a["model_size"][architecture.value]:
            raise ValueError("D41 Gate B model size differs from locked Gate A")
        inventory = collect_binary_inventory(model)
        inventory_audit = _inventory_lock_audit(inventory, architecture, gate_a)
        relaxation_audit = apply_relaxation(model, inventory, mode)
        relaxed_model_size = _linearity_audit(model)
        objective, objective_audit = _objective_metadata(model)
        service_audit = _service_audit(model, case)
    except Exception as error:  # noqa: BLE001 - canonical build failure evidence
        payload = {
            **base,
            "status": "build_failed",
            "solver_invoked": False,
            "build_runtime_seconds": perf_counter() - build_started,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        _write_json(output_path, payload)
        return payload

    build_runtime = perf_counter() - build_started
    solver_result = _solve_relaxed_model(
        model=model,
        objective=objective,
        mode=mode,
        inventory=inventory,
        guide_path=_guide_path(output_path),
        soft_time_limit_seconds=soft_limit,
    )
    termination = solver_result["termination_condition"]
    globally_infeasible = (
        mode is RelaxationMode.R0
        and termination.replace("_", "").lower() == "infeasible"
    )
    linearity_passed = (
        relaxed_model_size["nonlinear_component_count"] == 0
        and relaxed_model_size["active_binary_variable_count"]
        == relaxation_audit["remaining_binary_variable_count"]
    )
    bound_audit = audit_dual_bound(
        lower_bound=solver_result["objective_lower_bound_cny"],
        upper_bound=solver_result["objective_upper_bound_cny"],
        objective_audit_passed=objective_audit["passed"],
        domain_audit_passed=(
            inventory_audit["passed"] and relaxation_audit["passed"]
        ),
        service_audit_passed=service_audit["passed"],
        linearity_audit_passed=linearity_passed,
        objective_value=solver_result["loaded_objective_value_cny"],
    )
    eligible = bound_audit["passed"]
    status = (
        "r0_global_infeasibility_proven"
        if globally_infeasible
        else ("finite_strict_lower_bound" if eligible else "no_valid_lower_bound")
    )
    payload = {
        **base,
        "status": status,
        "solver_invoked": True,
        "formal_lower_bound_eligible": eligible,
        "global_original_milp_infeasibility_proven": globally_infeasible,
        "build_runtime_seconds": build_runtime,
        "original_model_size": original_model_size,
        "relaxed_model_size": relaxed_model_size,
        "binary_inventory_audit": inventory_audit,
        "relaxation_domain_audit": relaxation_audit,
        "objective_audit": objective_audit,
        "service_audit": service_audit,
        "linearity_audit_passed": linearity_passed,
        "dual_bound_audit": bound_audit,
        **solver_result,
    }
    _write_json(output_path, payload)
    return payload


def _available_memory_gib() -> float | None:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024.0**2
    return None


def _process_table() -> dict[int, tuple[int, float]]:
    table: dict[int, tuple[int, float]] = {}
    proc = Path("/proc")
    if not proc.is_dir():
        return table
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="ascii")
            ppid = 0
            rss_kib = 0.0
            for line in status.splitlines():
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                elif line.startswith("VmRSS:"):
                    rss_kib = float(line.split()[1])
            table[int(entry.name)] = (ppid, rss_kib / 1024.0**2)
        except (OSError, ValueError):
            continue
    return table


def _process_tree_rss_gib(root_pid: int) -> float | None:
    table = _process_table()
    if root_pid not in table:
        return None
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _rss) in table.items():
            if ppid in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return sum(table[pid][1] for pid in selected if pid in table)


def _process_rss_gib(pid: int) -> float | None:
    entry = _process_table().get(pid)
    return None if entry is None else entry[1]


def monitor_stop_reason(
    *,
    elapsed_seconds: float,
    hard_wall_seconds: float,
    child_tree_rss_gib: float | None,
    aggregate_rss_gib: float | None,
    available_memory_gib: float | None,
) -> str | None:
    """Apply hard-wall and memory stops in their frozen priority order."""

    if elapsed_seconds >= hard_wall_seconds:
        return "hard_wall_clock_reached"
    if child_tree_rss_gib is not None and child_tree_rss_gib >= PROCESS_RSS_LIMIT_GIB:
        return "process_tree_rss_limit_reached"
    if aggregate_rss_gib is not None and aggregate_rss_gib >= AGGREGATE_RSS_LIMIT_GIB:
        return "aggregate_rss_limit_reached"
    if available_memory_gib is not None and available_memory_gib < HOST_MEMORY_RESERVE_GIB:
        return "host_memory_reserve_breached"
    return None


def _terminate_process_group(process: subprocess.Popen[Any]) -> str:
    if process.poll() is not None:
        return "already_exited"
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return "sigterm"
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        return "sigkill"


def _paths(
    output_dir: Path,
    architecture: Architecture,
    mode: RelaxationMode,
) -> dict[str, Path]:
    prefix = f"gate_b_{architecture.value}_{_mode_token(mode)}"
    return {
        "result": output_dir / f"{prefix}.json",
        "execution": output_dir / f"{prefix}_execution.json",
        "solver_log": output_dir / f"{prefix}.log",
        "parent_log": output_dir / f"{prefix}_parent.log",
        "guide": output_dir / f"{prefix}_guide.csv.gz",
    }


def run_monitored_relaxation(
    *,
    architecture: Architecture,
    mode: RelaxationMode,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run one clean child with independent hard-wall and resource monitoring."""

    _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    _input_hashes(heat_path, vre_path, price_basis_path)
    paths = _paths(output_dir, architecture, mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in ("result", "execution", "solver_log", "parent_log", "guide"):
        if paths[key].exists():
            raise FileExistsError(f"D41 Gate B refuses to overwrite {paths[key]}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D41 Gate B formal execution requires Linux /proc")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D41 Gate B host memory is below the frozen reserve")
    soft_limit, hard_limit = _time_limits(mode)
    started_payload = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "status": "child_starting",
        "architecture": architecture.value,
        "relaxation_mode": mode.value,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "hard_wall_enforced_by_parent": True,
        "resource_thresholds": {
            "soft_time_limit_seconds": soft_limit,
            "hard_wall_seconds": hard_limit,
            "process_tree_rss_limit_gib": PROCESS_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
            "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
        },
    }
    _write_json(paths["execution"], started_payload)
    command = [
        sys.executable,
        "-u",
        "-m",
        "tes_bess_boundary.e0d41_gate_b_lower_bound",
        "_solve-child",
        "--architecture",
        architecture.value,
        "--relaxation",
        _mode_token(mode),
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
        "--output",
        str(paths["result"]),
    ]
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
    ) as solver_log, paths["parent_log"].open(
        "w", encoding="utf-8", newline="\n", buffering=1
    ) as parent_log:
        process = subprocess.Popen(
            command,
            stdout=solver_log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
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
                heartbeat = {
                    "phase": "solve",
                    "pid": process.pid,
                    "elapsed_seconds": elapsed,
                    "child_process_tree_rss_gib": child_tree,
                    "parent_child_aggregate_rss_gib": aggregate,
                    "available_memory_gib": available,
                    "last_heartbeat_monotonic_seconds": elapsed,
                }
                parent_log.write(json.dumps(heartbeat, sort_keys=True) + "\n")
                parent_log.flush()
                last_heartbeat = elapsed
            stop_reason = monitor_stop_reason(
                elapsed_seconds=elapsed,
                hard_wall_seconds=hard_limit,
                child_tree_rss_gib=child_tree,
                aggregate_rss_gib=aggregate,
                available_memory_gib=available,
            )
            if stop_reason is not None:
                termination_signal = _terminate_process_group(process)
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.wait()
    runtime = perf_counter() - started
    result_payload = (
        json.loads(paths["result"].read_text(encoding="utf-8"))
        if paths["result"].is_file()
        else None
    )
    resource_gate_passed = all(
        (
            stop_reason is None,
            rss_samples > 0,
            memory_samples > 0,
            peak_child_tree < PROCESS_RSS_LIMIT_GIB,
            peak_aggregate < AGGREGATE_RSS_LIMIT_GIB,
            minimum_available >= HOST_MEMORY_RESERVE_GIB,
        )
    )
    complete = return_code == 0 and result_payload is not None and resource_gate_passed
    effective_lower_bound_eligible = bool(
        complete and result_payload.get("formal_lower_bound_eligible") is True
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
        "resource_gate_passed": resource_gate_passed,
        "result_sha256": _sha256(paths["result"]) if paths["result"].is_file() else None,
        "solver_log_sha256": _sha256(paths["solver_log"]),
        "parent_log_sha256": _sha256(paths["parent_log"]),
        "candidate_guide_sha256": (
            _sha256(paths["guide"]) if paths["guide"].is_file() else None
        ),
        "effective_lower_bound_eligible": effective_lower_bound_eligible,
    }
    _write_json(paths["execution"], execution)
    return execution


def compile_architecture_manifest(
    *,
    architecture: Architecture,
    d41_gate_a_manifest_path: Path,
    result_dir: Path,
) -> dict[str, Any]:
    """Select the strongest audited R0/R1 lower bound without ranking technologies."""

    _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    stages: dict[str, Any] = {}
    valid_bounds: list[tuple[float, str]] = []
    r0_infeasible_proof = False
    for mode in RELAXATION_ORDER:
        token = _mode_token(mode)
        paths = _paths(result_dir, architecture, mode)
        if not paths["result"].is_file() or not paths["execution"].is_file():
            stages[token] = {"status": "missing"}
            continue
        result = json.loads(paths["result"].read_text(encoding="utf-8"))
        execution = json.loads(paths["execution"].read_text(encoding="utf-8"))
        hash_ok = execution.get("result_sha256") == _sha256(paths["result"])
        identity_ok = all(
            (
                result.get("schema_id") == RESULT_SCHEMA_ID,
                execution.get("schema_id") == EXECUTION_SCHEMA_ID,
                result.get("architecture") == architecture.value,
                execution.get("architecture") == architecture.value,
                result.get("relaxation_mode") == mode.value,
                execution.get("relaxation_mode") == mode.value,
                result.get("d41_gate_a_manifest_sha256")
                == D41_GATE_A_MANIFEST_SHA256,
            )
        )
        execution_ok = all(
            (
                execution.get("status") == "complete",
                execution.get("resource_gate_passed") is True,
                execution.get("stop_reason") is None,
                execution.get("return_code") == 0,
                execution.get("hard_wall_enforced_by_parent") is True,
            )
        )
        eligible = all(
            (
                hash_ok,
                identity_ok,
                execution_ok,
                result.get("formal_lower_bound_eligible") is True,
                result.get("dual_bound_audit", {}).get("passed") is True,
            )
        )
        bound = _finite_or_none(result.get("objective_lower_bound_cny"))
        if eligible and bound is not None:
            valid_bounds.append((bound, token))
        if token == "r0":
            r0_infeasible_proof = all(
                (
                    hash_ok,
                    identity_ok,
                    execution_ok,
                    result.get("status") == "r0_global_infeasibility_proven",
                    result.get("global_original_milp_infeasibility_proven") is True,
                )
            )
        stages[token] = {
            "status": "audited" if eligible else "invalid_or_incomplete",
            "result_sha256": _sha256(paths["result"]),
            "execution_sha256": _sha256(paths["execution"]),
            "lower_bound_cny": bound,
            "eligible": eligible,
            "candidate_guide_sha256": execution.get("candidate_guide_sha256"),
        }

    both_numeric_stages_passed = all(
        stages.get(token, {}).get("eligible") is True for token in ("r0", "r1")
    )
    if r0_infeasible_proof:
        status = "original_milp_globally_infeasible"
        gate_b_passed = True
        strict_lower_bound = None
        selected_relaxation = "r0_infeasibility_proof"
    elif both_numeric_stages_passed:
        strict_lower_bound, selected_relaxation = max(valid_bounds)
        status = "gate_b_passed"
        gate_b_passed = True
    else:
        strict_lower_bound = None
        selected_relaxation = None
        status = "gate_b_failed"
        gate_b_passed = False
    return {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "status": status,
        "gate_b_passed": gate_b_passed,
        "architecture": architecture.value,
        "d41_gate_a_manifest_sha256": D41_GATE_A_MANIFEST_SHA256,
        "representative_period_input_used": False,
        "global_original_milp_infeasibility_proven": r0_infeasible_proof,
        "strict_lower_bound_cny": strict_lower_bound,
        "selected_relaxation": selected_relaxation,
        "candidate_only": False,
        "technical_ranking_permitted": False,
        "stages": stages,
    }


def write_architecture_manifest(
    *,
    architecture: Architecture,
    d41_gate_a_manifest_path: Path,
    result_dir: Path,
) -> dict[str, Any]:
    payload = compile_architecture_manifest(
        architecture=architecture,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        result_dir=result_dir,
    )
    _write_json(result_dir / f"gate_b_{architecture.value}_manifest.json", payload)
    return payload


def run_architecture(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute R0 then R1 serially under the architecture-level wall clock."""

    started = perf_counter()
    executions: dict[str, Any] = {}
    for mode in RELAXATION_ORDER:
        if perf_counter() - started >= ARCHITECTURE_HARD_WALL_SECONDS:
            executions[_mode_token(mode)] = {
                "status": "not_started",
                "reason": "architecture_hard_wall_reached",
            }
            break
        execution = run_monitored_relaxation(
            architecture=architecture,
            mode=mode,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
            output_dir=output_dir,
        )
        executions[_mode_token(mode)] = execution
        if execution.get("status") != "complete":
            break
        result_path = _paths(output_dir, architecture, mode)["result"]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("global_original_milp_infeasibility_proven") is True:
            break
        if result.get("formal_lower_bound_eligible") is not True:
            break
    manifest = write_architecture_manifest(
        architecture=architecture,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        result_dir=output_dir,
    )
    summary = {
        "architecture": architecture.value,
        "runtime_seconds": perf_counter() - started,
        "architecture_hard_wall_seconds": ARCHITECTURE_HARD_WALL_SECONDS,
        "executions": executions,
        "manifest": manifest,
    }
    _write_json(output_dir / f"gate_b_{architecture.value}_execution.json", summary)
    return summary


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service-file", type=Path, required=True)
    parser.add_argument("--d40-gate-a-manifest", type=Path, required=True)
    parser.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)


def _parse_mode(token: str) -> RelaxationMode:
    return RelaxationMode.R0 if token == "r0" else RelaxationMode.R1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-architecture")
    run.add_argument(
        "--architecture",
        choices=tuple(item.value for item in FORMAL_ARCHITECTURES),
        required=True,
    )
    _add_inputs(run)
    run.add_argument("--output-dir", type=Path, required=True)

    child = commands.add_parser("_solve-child")
    child.add_argument(
        "--architecture",
        choices=tuple(item.value for item in FORMAL_ARCHITECTURES),
        required=True,
    )
    child.add_argument("--relaxation", choices=("r0", "r1"), required=True)
    _add_inputs(child)
    child.add_argument("--output", type=Path, required=True)

    audit = commands.add_parser("audit-architecture")
    audit.add_argument(
        "--architecture",
        choices=tuple(item.value for item in FORMAL_ARCHITECTURES),
        required=True,
    )
    audit.add_argument("--d41-gate-a-manifest", type=Path, required=True)
    audit.add_argument("--result-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    architecture = Architecture(args.architecture)
    if args.command == "run-architecture":
        payload = run_architecture(
            architecture=architecture,
            service_path=args.service_file,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_dir=args.output_dir,
        )
    elif args.command == "_solve-child":
        payload = solve_child(
            architecture=architecture,
            mode=_parse_mode(args.relaxation),
            service_path=args.service_file,
            d40_gate_a_manifest_path=args.d40_gate_a_manifest,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_path=args.output,
        )
    else:
        payload = write_architecture_manifest(
            architecture=architecture,
            d41_gate_a_manifest_path=args.d41_gate_a_manifest,
            result_dir=args.result_dir,
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
