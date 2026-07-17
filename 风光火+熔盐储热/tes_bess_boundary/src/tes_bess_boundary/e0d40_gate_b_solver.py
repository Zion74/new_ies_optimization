"""Monitored E0-D-40 Gate B full-year solves and evidence compilation.

Gate A remains immutable.  This module pins its service and manifest hashes,
spawns each solve in a clean child process, monitors the preregistered memory
limits, and keeps scientific result payloads separate from execution metadata.
"""

from __future__ import annotations

import argparse
import hashlib
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

from tes_bess_boundary.e0d17_exploration import COAL_PRICE_CNY_PER_TCE
from tes_bess_boundary.e0d38_prevalidation import (
    build_d38_case,
    load_full_year_input,
    planning_inputs_for_state,
    state_spec,
)
from tes_bess_boundary.e0d40_full_year_compute_gate import (
    ACTUAL_RENEWABLE_AVAILABLE_MWH,
    CLAIM_SCOPE,
    EPSILON_CURTAILMENT_CEILING_MWH,
    FORMAL_PROJECT_TAC_READY,
    FULL_YEAR_HOURS,
    GATE_A_SCHEMA_ID,
    PCC_EXPORT_TARGET_MWH,
    _code_hashes as _gate_a_code_hashes,
    _input_hashes,
    _linearity_audit,
    _service_specs,
    _sha256,
    _write_json,
    load_full_year_service,
)
from tes_bess_boundary.model import Architecture, ValidationObjectiveSpec
from tes_bess_boundary.planning_model import build_endogenous_capacity_model
from tes_bess_boundary.solver import create_highs_solver


CASE_SCHEMA_ID = "tes_bess_boundary.e0d40_gate_b_case.v1"
EXECUTION_SCHEMA_ID = f"{CASE_SCHEMA_ID}.execution"
SUMMARY_SCHEMA_ID = "tes_bess_boundary.e0d40_gate_b_manifest.v1"

SERVICE_SHA256 = (
    "1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95"
)
GATE_A_MANIFEST_SHA256 = (
    "23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577"
)

FORMAL_THREADS = 12
FORMAL_RANDOM_SEED = 0
FORMAL_TIME_LIMIT_SECONDS = 3_600.0
FORMAL_TARGET_RELATIVE_GAP = 0.001
BOUNDED_MAX_RELATIVE_GAP = 0.005
PREFLIGHT_TIME_LIMIT_SECONDS = 60.0
SOLVER_FEASIBILITY_TOLERANCE = 1e-7

SERVICE_TOLERANCE_MWH = 1e-3
BALANCE_TOLERANCE_MW = 1e-5
NORMALIZED_CONSTRAINT_TOLERANCE = 1e-6
OBJECTIVE_RELATIVE_TOLERANCE = 1e-8

PROCESS_RSS_LIMIT_GIB = 35.0
AGGREGATE_RSS_LIMIT_GIB = 75.0
HOST_MEMORY_RESERVE_GIB = 15.0
MONITOR_INTERVAL_SECONDS = 0.5

FORMAL_ARCHITECTURES = (
    Architecture.BESS,
    Architecture.TES,
    Architecture.HYBRID,
)
CLASSIFICATION_RANK = {
    "monolithic_not_viable": 0,
    "bounded_but_not_qualified": 1,
    "qualified_full_year": 2,
}


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _finite_or_none(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _termination_name(raw: object) -> str:
    return getattr(raw, "name", str(raw)).replace("_", "").lower()


def _relative_gap(lower_bound: float | None, upper_bound: float | None) -> float | None:
    if lower_bound is None or upper_bound is None or lower_bound > upper_bound:
        return None
    return max(0.0, upper_bound - lower_bound) / max(abs(upper_bound), 1e-12)


def classify_case(
    *,
    mode: str,
    termination: str,
    lower_bound: float | None,
    upper_bound: float | None,
    solution_loaded: bool,
    solution_audit_passed: bool,
) -> tuple[str, str, float | None, bool]:
    """Apply the preregistered D40 Gate B classification without tuning."""

    if mode not in {"formal", "preflight"}:
        raise ValueError("D40 Gate B mode must be formal or preflight")
    normalized_termination = termination.replace("_", "").lower()
    globally_infeasible = normalized_termination == "infeasible"
    gap = _relative_gap(lower_bound, upper_bound)
    if mode == "preflight":
        return "preflight_only", "preflight_is_not_formal_evidence", gap, globally_infeasible
    if globally_infeasible:
        return (
            "qualified_full_year",
            "highs_global_infeasibility_proof",
            gap,
            True,
        )
    if not solution_loaded or not solution_audit_passed:
        return (
            "monolithic_not_viable",
            "missing_or_invalid_incumbent",
            gap,
            False,
        )
    if gap is None:
        return "monolithic_not_viable", "missing_finite_dual_bound", None, False
    if gap <= FORMAL_TARGET_RELATIVE_GAP + 1e-12:
        return "qualified_full_year", "relative_gap_at_most_0.1_percent", gap, False
    if gap <= BOUNDED_MAX_RELATIVE_GAP + 1e-12:
        return (
            "bounded_but_not_qualified",
            "relative_gap_between_0.1_and_0.5_percent",
            gap,
            False,
        )
    return "monolithic_not_viable", "relative_gap_above_0.5_percent", gap, False


def _load_locked_gate_a(gate_a_manifest_path: Path, service_path: Path) -> dict[str, Any]:
    if _sha256(service_path) != SERVICE_SHA256:
        raise ValueError("D40 Gate B service hash mismatch")
    service = load_full_year_service(service_path)
    if _sha256(gate_a_manifest_path) != GATE_A_MANIFEST_SHA256:
        raise ValueError("D40 Gate B Gate A manifest hash mismatch")
    gate = json.loads(gate_a_manifest_path.read_text(encoding="utf-8"))
    if gate.get("schema_id") != GATE_A_SCHEMA_ID:
        raise ValueError("D40 Gate B Gate A schema mismatch")
    if gate.get("status") != "gate_a_passed":
        raise ValueError("D40 Gate B requires a passed Gate A")
    if gate.get("solver_invoked") is not False:
        raise ValueError("D40 Gate A unexpectedly invoked a solver")
    if gate.get("service_contract_sha256") != SERVICE_SHA256:
        raise ValueError("D40 Gate A service reference mismatch")
    if gate.get("audit", {}).get("passed") is not True:
        raise ValueError("D40 Gate A audit is not passed")
    if service.get("representative_period_input_used") is not False:
        raise ValueError("D40 Gate B cannot use representative periods")
    return gate


def _gate_b_code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    return {
        **_gate_a_code_hashes(),
        "e0d40_gate_b_solver.py": _sha256(package / "e0d40_gate_b_solver.py"),
    }


def _base_payload(
    *,
    architecture: Architecture,
    mode: str,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    time_limit = (
        FORMAL_TIME_LIMIT_SECONDS
        if mode == "formal"
        else PREFLIGHT_TIME_LIMIT_SECONDS
    )
    return {
        "schema_id": CASE_SCHEMA_ID,
        "mode": mode,
        "formal_gate_b_eligible": mode == "formal",
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "architecture": architecture.value,
        "service_contract_sha256": _sha256(service_path),
        "gate_a_manifest_sha256": _sha256(gate_a_manifest_path),
        "representative_period_input_used": False,
        "solver": {
            "name": "appsi_highs",
            "threads": FORMAL_THREADS,
            "random_seed": FORMAL_RANDOM_SEED,
            "time_limit_seconds": time_limit,
            "target_relative_mip_gap": FORMAL_TARGET_RELATIVE_GAP,
            "primal_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "dual_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "mip_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "warm_start_used": False,
        },
        "provenance": {
            **_input_hashes(heat_path, vre_path, price_basis_path),
            "code_sha256": _gate_b_code_hashes(),
        },
    }


def _build_gate_b_model(
    architecture: Architecture,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> tuple[object, object, dict[str, Any]]:
    if architecture not in FORMAL_ARCHITECTURES:
        raise ValueError("D40 Gate B only solves BESS, TES, or Hybrid")
    gate = _load_locked_gate_a(gate_a_manifest_path, service_path)
    service = load_full_year_service(service_path)
    state = state_spec("baseline")
    horizon_input = load_full_year_input(heat_path, vre_path, state)
    if horizon_input.timeseries.period_count != FULL_YEAR_HOURS:
        raise ValueError("D40 Gate B requires exactly 8784 actual hours")
    if len(horizon_input.horizon.dispatch_blocks) != 1:
        raise ValueError("D40 Gate B requires one full-year cyclic block")
    if not math.isclose(
        horizon_input.renewable_available_mwh,
        ACTUAL_RENEWABLE_AVAILABLE_MWH,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("D40 Gate B renewable availability mismatch")
    curtailment_service, pcc_service = _service_specs(service)
    case = build_d38_case(
        state=state,
        architecture=architecture,
        horizon_input=horizon_input,
        planning_inputs=planning_inputs_for_state(price_basis_path, state),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=COAL_PRICE_CNY_PER_TCE,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
        curtailment_service=curtailment_service,
        pcc_export_service=pcc_service,
    )
    model = build_endogenous_capacity_model(case)
    size = _linearity_audit(model)
    if size != gate["model_size"][architecture.value]:
        raise ValueError("D40 Gate B model size differs from Gate A")
    return case, model, size


def _component_value(component: object, name: str, *, nonnegative: bool = False) -> float:
    from pyomo.environ import value

    raw = float(value(component))
    if not math.isfinite(raw):
        raise ValueError(f"D40 Gate B {name} is not finite")
    if nonnegative and raw < -1e-7:
        raise ValueError(f"D40 Gate B {name} is negative")
    return max(0.0, raw) if nonnegative else raw


def _capacity_snapshot(model: object, architecture: Architecture, case: object) -> dict[str, Any]:
    bess: dict[str, float] | None = None
    tes: dict[str, float] | None = None
    if architecture in (Architecture.BESS, Architecture.HYBRID):
        bess = {
            "energy_capacity_mwh": _component_value(
                model.bess.energy_capacity_mwh, "BESS energy capacity", nonnegative=True
            ),
            "charge_power_capacity_mw": _component_value(
                model.bess.charge_power_capacity_mw,
                "BESS charge power capacity",
                nonnegative=True,
            ),
            "discharge_power_capacity_mw": _component_value(
                model.bess.discharge_power_capacity_mw,
                "BESS discharge power capacity",
                nonnegative=True,
            ),
            "common_pcs_power_capacity_mw": _component_value(
                model.bess.pcs_power_capacity_mw,
                "BESS common PCS capacity",
                nonnegative=True,
            ),
            "installation_binary": _component_value(
                model.bess.installed, "BESS installation binary", nonnegative=True
            ),
            "annual_ac_discharge_throughput_mwh": _component_value(
                model.planning_bess_ac_discharge_throughput_mwh,
                "BESS annual AC discharge throughput",
                nonnegative=True,
            ),
        }
    if architecture in (Architecture.TES, Architecture.HYBRID):
        names = (
            "salt_mass_t",
            "ht_tank_capacity_t",
            "mt_tank_capacity_t",
            "lt_tank_capacity_t",
            "ht_service_salt_mass_t",
            "mt_service_salt_mass_t",
            "electric_charge_input_capacity_mw",
            "steam_to_ht_input_capacity_mw",
            "steam_to_mt_input_capacity_mw",
            "electric_output_capacity_mw",
            "heat_output_capacity_mw",
        )
        tes = {
            name: _component_value(
                getattr(model.tes, name), f"TES {name}", nonnegative=True
            )
            for name in names
        }
        tes["annual_auxiliary_mwh"] = _component_value(
            case.timeseries.dt_hours
            * sum(
                model.annual_period_weight[period]
                * model.tes.auxiliary_power_mw[period]
                for period in model.periods
            ),
            "TES annual auxiliary energy",
            nonnegative=True,
        )
        tes["continuous_zero_capacity_allowed"] = not hasattr(model.tes, "installed")
    return {"bess": bess, "tes": tes}


def _max_equality_residual(component: object) -> float:
    from pyomo.environ import value

    worst = 0.0
    for index in component:
        constraint = component[index]
        body = float(value(constraint.body))
        lower = float(value(constraint.lower))
        upper = float(value(constraint.upper))
        if not math.isclose(lower, upper, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"D40 Gate B {constraint.name} is not an equality")
        worst = max(worst, abs(body - lower))
    return worst


def _constraint_residual_audit(model: object) -> dict[str, Any]:
    from pyomo.environ import Constraint, value

    worst_normalized = 0.0
    worst_absolute = 0.0
    worst_component: str | None = None
    evaluated = 0
    nonfinite = 0
    for constraint in model.component_data_objects(Constraint, active=True):
        evaluated += 1
        try:
            body = float(value(constraint.body))
            lower = None if constraint.lower is None else float(value(constraint.lower))
            upper = None if constraint.upper is None else float(value(constraint.upper))
        except (TypeError, ValueError):
            nonfinite += 1
            continue
        values = [body]
        if lower is not None:
            values.append(lower)
        if upper is not None:
            values.append(upper)
        if not all(math.isfinite(item) for item in values):
            nonfinite += 1
            continue
        violation = 0.0
        if lower is not None:
            violation = max(violation, lower - body)
        if upper is not None:
            violation = max(violation, body - upper)
        scale = max(1.0, *(abs(item) for item in values))
        normalized = violation / scale
        if normalized > worst_normalized:
            worst_normalized = normalized
            worst_absolute = violation
            worst_component = constraint.name
    return {
        "evaluated_constraint_count": evaluated,
        "nonfinite_constraint_count": nonfinite,
        "max_normalized_violation": worst_normalized,
        "max_absolute_violation": worst_absolute,
        "worst_constraint": worst_component,
        "tolerance": NORMALIZED_CONSTRAINT_TOLERANCE,
        "passed": (
            nonfinite == 0
            and worst_normalized <= NORMALIZED_CONSTRAINT_TOLERANCE
        ),
    }


def _solution_payload(
    model: object,
    case: object,
    architecture: Architecture,
    upper_bound: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    costs = {
        "annual_total_cost_cny": _component_value(
            model.planning_total_cost_cny, "annual total cost"
        ),
        "annual_operating_cost_cny": _component_value(
            model.annual_operating_cost_cny, "annual operating cost"
        ),
        "annual_storage_capacity_cost_cny": _component_value(
            model.planning_storage_capacity_cost_cny,
            "annual storage capacity cost",
            nonnegative=True,
        ),
        "annual_bess_cycle_cost_cny": _component_value(
            model.planning_bess_cycle_cost_cny,
            "annual BESS cycle cost",
            nonnegative=True,
        ),
        "annual_bess_variable_om_cost_cny": _component_value(
            model.planning_bess_variable_om_cost_cny,
            "annual BESS variable O&M cost",
            nonnegative=True,
        ),
    }
    annual_curtailment = _component_value(
        model.annual_curtailment_mwh, "annual curtailment", nonnegative=True
    )
    annual_pcc = _component_value(model.annual_pcc_export_mwh, "annual PCC export")
    annual_fuel = _component_value(
        model.annual_fuel_tce, "annual fuel", nonnegative=True
    )
    objective_relative_error = abs(
        costs["annual_total_cost_cny"] - upper_bound
    ) / max(abs(upper_bound), 1.0)
    service_audit = {
        "annual_curtailment_mwh": annual_curtailment,
        "curtailment_ceiling_mwh": EPSILON_CURTAILMENT_CEILING_MWH,
        "curtailment_ceiling_slack_mwh": (
            EPSILON_CURTAILMENT_CEILING_MWH - annual_curtailment
        ),
        "annual_pcc_export_mwh": annual_pcc,
        "pcc_export_target_mwh": PCC_EXPORT_TARGET_MWH,
        "pcc_export_residual_mwh": annual_pcc - PCC_EXPORT_TARGET_MWH,
        "service_tolerance_mwh": SERVICE_TOLERANCE_MWH,
    }
    balance_audit = {
        "max_planning_pcc_balance_residual_mw": _max_equality_residual(
            model.planning_pcc_balance
        ),
        "max_planning_heat_allocation_residual_mw": _max_equality_residual(
            model.planning_heat_allocation
        ),
        "max_planning_heat_balance_residual_mw": _max_equality_residual(
            model.planning_heat_balance
        ),
        "balance_tolerance_mw": BALANCE_TOLERANCE_MW,
    }
    balance_audit["passed"] = all(
        balance_audit[key] <= BALANCE_TOLERANCE_MW
        for key in (
            "max_planning_pcc_balance_residual_mw",
            "max_planning_heat_allocation_residual_mw",
            "max_planning_heat_balance_residual_mw",
        )
    )
    constraint_audit = _constraint_residual_audit(model)
    objective_audit = {
        "model_objective_cny": costs["annual_total_cost_cny"],
        "highs_incumbent_cny": upper_bound,
        "relative_error": objective_relative_error,
        "relative_tolerance": OBJECTIVE_RELATIVE_TOLERANCE,
        "passed": objective_relative_error <= OBJECTIVE_RELATIVE_TOLERANCE,
    }
    service_audit["passed"] = all(
        (
            abs(service_audit["pcc_export_residual_mwh"])
            <= SERVICE_TOLERANCE_MWH,
            service_audit["curtailment_ceiling_slack_mwh"]
            >= -SERVICE_TOLERANCE_MWH,
        )
    )
    audit = {
        "service": service_audit,
        "balances": balance_audit,
        "constraints": constraint_audit,
        "objective": objective_audit,
    }
    audit["passed"] = all(
        section["passed"]
        for section in (
            service_audit,
            balance_audit,
            constraint_audit,
            objective_audit,
        )
    )
    solution = {
        "costs": costs,
        "weighted_fuel_tce": annual_fuel,
        "weighted_curtailment_mwh": annual_curtailment,
        "weighted_pcc_export_mwh": annual_pcc,
        "capacity_snapshot": _capacity_snapshot(model, architecture, case),
    }
    return solution, audit


def solve_child(
    *,
    architecture: Architecture,
    mode: str,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Build and solve one child task; execution metadata belongs to the parent."""

    base = _base_payload(
        architecture=architecture,
        mode=mode,
        service_path=service_path,
        gate_a_manifest_path=gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    try:
        case, model, model_size = _build_gate_b_model(
            architecture,
            service_path,
            gate_a_manifest_path,
            heat_path,
            vre_path,
            price_basis_path,
        )
    except Exception as error:  # noqa: BLE001 - preserve a canonical failure record
        payload = {
            **base,
            "solver_invoked": False,
            "status": "build_failed",
            "classification": (
                "preflight_only" if mode == "preflight" else "monolithic_not_viable"
            ),
            "classification_reason": "build_or_provenance_failure",
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
        _write_json(output_path, payload)
        return payload

    time_limit = (
        FORMAL_TIME_LIMIT_SECONDS
        if mode == "formal"
        else PREFLIGHT_TIME_LIMIT_SECONDS
    )
    termination = "solver_error"
    lower_bound: float | None = None
    upper_bound: float | None = None
    solution_loaded = False
    solution: dict[str, Any] | None = None
    solution_audit: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    import highspy

    highspy.Highs.resetGlobalScheduler(True)
    try:
        solver = create_highs_solver(
            threads=FORMAL_THREADS,
            random_seed=FORMAL_RANDOM_SEED,
            mip_rel_gap=FORMAL_TARGET_RELATIVE_GAP,
        )
        solver.options["time_limit"] = time_limit
        solver.options["primal_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
        solver.options["dual_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
        solver.options["mip_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
        results = solver.solve(model, tee=True, load_solutions=False)
        termination = _termination_name(results.solver.termination_condition)
        lower_bound = _finite_or_none(getattr(results.problem, "lower_bound", None))
        upper_bound = _finite_or_none(getattr(results.problem, "upper_bound", None))
        if upper_bound is not None:
            try:
                if len(results.solution) > 0:
                    model.solutions.load_from(results)
                else:
                    solver.load_vars()
                solution_loaded = True
                solution, solution_audit = _solution_payload(
                    model, case, architecture, upper_bound
                )
            except Exception as error:  # noqa: BLE001 - classify an unloadable incumbent
                error_type = type(error).__name__
                error_message = str(error)
                solution_loaded = False
                solution = None
                solution_audit = None
    except Exception as error:  # noqa: BLE001 - solver failures are scientific evidence
        error_type = type(error).__name__
        error_message = str(error)
    finally:
        highspy.Highs.resetGlobalScheduler(True)

    classification, reason, gap, globally_infeasible = classify_case(
        mode=mode,
        termination=termination,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        solution_loaded=solution_loaded,
        solution_audit_passed=(
            solution_audit is not None and solution_audit.get("passed") is True
        ),
    )
    status = (
        "global_infeasibility_proven"
        if globally_infeasible
        else ("solution_available" if solution_loaded else "no_loadable_incumbent")
    )
    payload = {
        **base,
        "solver_invoked": True,
        "status": status,
        "termination_condition": termination,
        "objective_lower_bound_cny": lower_bound,
        "objective_upper_bound_cny": upper_bound,
        "actual_relative_mip_gap": gap,
        "global_infeasibility_proven": globally_infeasible,
        "solution_loaded": solution_loaded,
        "classification": classification,
        "classification_reason": reason,
        "model_size": model_size,
        "solution": solution,
        "solution_audit": solution_audit,
    }
    if error_type is not None:
        payload["error_type"] = error_type
        payload["error_message"] = error_message
    _write_json(output_path, payload)
    return payload


def _available_memory_gib() -> float | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return None
    for line in meminfo.read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024.0**2
    return None


def _process_rss_gib(pid: int) -> float | None:
    status = Path(f"/proc/{pid}/status")
    if not status.is_file():
        return None
    try:
        for line in status.read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0**2
    except (OSError, ValueError):
        return None
    return None


def _terminate_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait(timeout=10.0)


def _case_paths(
    output_dir: Path, architecture: Architecture, mode: str
) -> tuple[Path, Path, Path]:
    prefix = (
        f"gate_b_{architecture.value}"
        if mode == "formal"
        else f"preflight_{architecture.value}"
    )
    return (
        output_dir / f"{prefix}.json",
        output_dir / f"{prefix}_execution.json",
        output_dir / f"{prefix}.log",
    )


def run_monitored_case(
    *,
    architecture: Architecture,
    mode: str,
    service_path: Path,
    gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run one clean child process and enforce the D40 RSS/host reserve gates."""

    if mode == "preflight" and architecture is not Architecture.BESS:
        raise ValueError("D40 permits only the BESS preflight")
    if mode not in {"formal", "preflight"}:
        raise ValueError("D40 Gate B mode must be formal or preflight")
    _load_locked_gate_a(gate_a_manifest_path, service_path)
    _input_hashes(heat_path, vre_path, price_basis_path)
    result_path, execution_path, log_path = _case_paths(
        output_dir, architecture, mode
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (result_path, execution_path, log_path):
        if path.exists():
            raise FileExistsError(f"D40 Gate B refuses to overwrite {path}")
    available_before = _available_memory_gib()
    if available_before is None:
        raise RuntimeError("D40 Gate B formal monitor requires Linux /proc memory data")
    if available_before < HOST_MEMORY_RESERVE_GIB:
        raise RuntimeError("D40 Gate B host memory is below the preregistered reserve")
    started_execution = {
        "schema_id": EXECUTION_SCHEMA_ID,
        "mode": mode,
        "architecture": architecture.value,
        "status": "child_starting",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "available_memory_before_gib": available_before,
        "resource_thresholds": {
            "process_rss_limit_gib": PROCESS_RSS_LIMIT_GIB,
            "aggregate_rss_limit_gib": AGGREGATE_RSS_LIMIT_GIB,
            "host_memory_reserve_gib": HOST_MEMORY_RESERVE_GIB,
            "monitor_interval_seconds": MONITOR_INTERVAL_SECONDS,
        },
    }
    _write_json(execution_path, started_execution)
    command = [
        sys.executable,
        "-m",
        "tes_bess_boundary.e0d40_gate_b_solver",
        "_solve-child",
        "--architecture",
        architecture.value,
        "--mode",
        mode,
        "--service-file",
        str(service_path),
        "--gate-a-manifest",
        str(gate_a_manifest_path),
        "--heat-path",
        str(heat_path),
        "--vre-path",
        str(vre_path),
        "--price-basis-path",
        str(price_basis_path),
        "--output",
        str(result_path),
    ]
    peak_rss = 0.0
    peak_aggregate_rss = 0.0
    min_available = available_before
    rss_samples = 0
    memory_samples = 0
    resource_stop_reason: str | None = None
    started = perf_counter()
    with log_path.open("w", encoding="utf-8", newline="\n") as log_stream:
        process = subprocess.Popen(
            command,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        while process.poll() is None:
            rss = _process_rss_gib(process.pid)
            parent_rss = _process_rss_gib(os.getpid())
            available = _available_memory_gib()
            if rss is not None:
                peak_rss = max(peak_rss, rss)
                rss_samples += 1
            if rss is not None and parent_rss is not None:
                peak_aggregate_rss = max(
                    peak_aggregate_rss, rss + parent_rss
                )
            if available is not None:
                min_available = min(min_available, available)
                memory_samples += 1
            if rss is not None and rss >= PROCESS_RSS_LIMIT_GIB:
                resource_stop_reason = "process_rss_limit_reached"
                _terminate_process(process)
                break
            if peak_aggregate_rss >= AGGREGATE_RSS_LIMIT_GIB:
                resource_stop_reason = "aggregate_rss_limit_reached"
                _terminate_process(process)
                break
            if available is not None and available < HOST_MEMORY_RESERVE_GIB:
                resource_stop_reason = "host_memory_reserve_breached"
                _terminate_process(process)
                break
            time.sleep(MONITOR_INTERVAL_SECONDS)
        return_code = process.wait()
    runtime = perf_counter() - started
    result_hash = _sha256(result_path) if result_path.is_file() else None
    log_hash = _sha256(log_path)
    resource_gate_passed = (
        resource_stop_reason is None
        and rss_samples > 0
        and memory_samples > 0
        and peak_rss < PROCESS_RSS_LIMIT_GIB
        and peak_aggregate_rss < AGGREGATE_RSS_LIMIT_GIB
        and min_available >= HOST_MEMORY_RESERVE_GIB
    )
    result_payload: dict[str, Any] | None = None
    if result_path.is_file():
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    effective_classification = (
        result_payload.get("classification")
        if result_payload is not None
        else ("preflight_only" if mode == "preflight" else "monolithic_not_viable")
    )
    if mode == "formal" and (
        return_code != 0 or not resource_gate_passed or result_payload is None
    ):
        effective_classification = "monolithic_not_viable"
    execution = {
        **started_execution,
        "status": (
            "complete"
            if return_code == 0 and result_payload is not None and resource_gate_passed
            else "resource_or_process_failure"
        ),
        "return_code": return_code,
        "runtime_seconds": runtime,
        "peak_child_rss_gib": peak_rss,
        "peak_gate_b_process_tree_rss_gib": peak_aggregate_rss,
        "minimum_available_memory_gib": min_available,
        "rss_sample_count": rss_samples,
        "available_memory_sample_count": memory_samples,
        "resource_stop_reason": resource_stop_reason,
        "resource_gate_passed": resource_gate_passed,
        "result_sha256": result_hash,
        "log_sha256": log_hash,
        "effective_classification": effective_classification,
    }
    _write_json(execution_path, execution)
    return execution


def compile_gate_b_manifest(
    service_path: Path,
    gate_a_manifest_path: Path,
    result_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile three formal cases and apply the weakest-case decision rule."""

    _load_locked_gate_a(gate_a_manifest_path, service_path)
    results: dict[str, dict[str, Any]] = {}
    executions: dict[str, dict[str, Any]] = {}
    classifications: dict[str, str] = {}
    for architecture in FORMAL_ARCHITECTURES:
        name = architecture.value
        result_path, execution_path, _ = _case_paths(
            result_dir, architecture, "formal"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
        if result.get("schema_id") != CASE_SCHEMA_ID:
            raise ValueError(f"D40 Gate B {name} result schema mismatch")
        if result.get("mode") != "formal" or result.get("formal_gate_b_eligible") is not True:
            raise ValueError(f"D40 Gate B {name} is not a formal run")
        if result.get("architecture") != name:
            raise ValueError(f"D40 Gate B {name} architecture mismatch")
        if result.get("service_contract_sha256") != SERVICE_SHA256:
            raise ValueError(f"D40 Gate B {name} service mismatch")
        if result.get("gate_a_manifest_sha256") != GATE_A_MANIFEST_SHA256:
            raise ValueError(f"D40 Gate B {name} Gate A mismatch")
        if result.get("solver") != {
            "name": "appsi_highs",
            "threads": FORMAL_THREADS,
            "random_seed": FORMAL_RANDOM_SEED,
            "time_limit_seconds": FORMAL_TIME_LIMIT_SECONDS,
            "target_relative_mip_gap": FORMAL_TARGET_RELATIVE_GAP,
            "primal_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "dual_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "mip_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
            "warm_start_used": False,
        }:
            raise ValueError(f"D40 Gate B {name} solver contract mismatch")
        if execution.get("schema_id") != EXECUTION_SCHEMA_ID:
            raise ValueError(f"D40 Gate B {name} execution schema mismatch")
        if execution.get("mode") != "formal" or execution.get("architecture") != name:
            raise ValueError(f"D40 Gate B {name} execution identity mismatch")
        if execution.get("result_sha256") != _sha256(result_path):
            raise ValueError(f"D40 Gate B {name} result hash mismatch")
        classification = execution.get("effective_classification")
        if classification not in CLASSIFICATION_RANK:
            raise ValueError(f"D40 Gate B {name} classification mismatch")
        results[name] = result
        executions[name] = execution
        classifications[name] = classification
    total_classification = min(
        classifications.values(), key=lambda item: CLASSIFICATION_RANK[item]
    )
    status = {
        "qualified_full_year": "gate_b_passed",
        "bounded_but_not_qualified": "gate_b_bounded_not_qualified",
        "monolithic_not_viable": "gate_b_monolithic_not_viable",
    }[total_classification]
    manifest = {
        "schema_id": SUMMARY_SCHEMA_ID,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "status": status,
        "classification": total_classification,
        "service_contract_sha256": SERVICE_SHA256,
        "gate_a_manifest_sha256": GATE_A_MANIFEST_SHA256,
        "formal_sequence": [item.value for item in FORMAL_ARCHITECTURES],
        "case_classification": classifications,
        "case_result_sha256": {
            name: _sha256(result_dir / f"gate_b_{name}.json") for name in results
        },
        "case_execution_sha256": {
            name: _sha256(result_dir / f"gate_b_{name}_execution.json")
            for name in executions
        },
        "gate_b_passed": total_classification == "qualified_full_year",
        "e2_e4_authorized": total_classification == "qualified_full_year",
        "technical_winner_claim_authorized": False,
        "audit": {"evidence_complete": True},
    }
    execution_payload = {
        "schema_id": f"{SUMMARY_SCHEMA_ID}.execution",
        "case_execution": executions,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }
    return manifest, execution_payload


def write_gate_b_manifest(
    service_path: Path,
    gate_a_manifest_path: Path,
    result_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifest, execution = compile_gate_b_manifest(
        service_path, gate_a_manifest_path, result_dir
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _canonical_json_bytes(manifest)
    (output_dir / "gate_b_manifest.json").write_bytes(manifest_bytes)
    execution["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    _write_json(output_dir / "gate_b_execution.json", execution)
    return manifest


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--service-file", type=Path, required=True)
    parser.add_argument("--gate-a-manifest", type=Path, required=True)
    parser.add_argument("--heat-path", type=Path, required=True)
    parser.add_argument("--vre-path", type=Path, required=True)
    parser.add_argument("--price-basis-path", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run-case")
    run.add_argument(
        "--architecture",
        choices=tuple(item.value for item in FORMAL_ARCHITECTURES),
        required=True,
    )
    run.add_argument("--mode", choices=("formal", "preflight"), default="formal")
    _add_common_paths(run)
    run.add_argument("--output-dir", type=Path, required=True)

    child = commands.add_parser("_solve-child")
    child.add_argument(
        "--architecture",
        choices=tuple(item.value for item in FORMAL_ARCHITECTURES),
        required=True,
    )
    child.add_argument("--mode", choices=("formal", "preflight"), required=True)
    _add_common_paths(child)
    child.add_argument("--output", type=Path, required=True)

    audit = commands.add_parser("audit")
    audit.add_argument("--service-file", type=Path, required=True)
    audit.add_argument("--gate-a-manifest", type=Path, required=True)
    audit.add_argument("--result-dir", type=Path, required=True)
    audit.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run-case":
        payload = run_monitored_case(
            architecture=Architecture(args.architecture),
            mode=args.mode,
            service_path=args.service_file,
            gate_a_manifest_path=args.gate_a_manifest,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_dir=args.output_dir,
        )
    elif args.command == "_solve-child":
        payload = solve_child(
            architecture=Architecture(args.architecture),
            mode=args.mode,
            service_path=args.service_file,
            gate_a_manifest_path=args.gate_a_manifest,
            heat_path=args.heat_path,
            vre_path=args.vre_path,
            price_basis_path=args.price_basis_path,
            output_path=args.output,
        )
    else:
        payload = write_gate_b_manifest(
            args.service_file,
            args.gate_a_manifest,
            args.result_dir,
            args.output_dir,
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
