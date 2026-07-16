"""E0-D-48 Hamming feasibility search and original-cost primal repair.

D48 deliberately keeps the original planning MILP feasible set.  Candidate
search only replaces the economic objective with an equal-weight Hamming
distance over the complete D41 binary inventory.  If HiGHS returns a complete
incumbent, a clean original model is rebuilt, every binary is fixed, and the
original economic objective is solved with all continuous capacities free
inside their original bounds.

Neither a Hamming objective nor an unaudited callback solution is an upper
bound.  Only :func:`audit_original_cost_repair` can grant the D48 engineering
numerical upper-bound field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from tes_bess_boundary.e0d40_full_year_compute_gate import _linearity_audit
from tes_bess_boundary.e0d40_gate_b_solver import (
    FORMAL_ARCHITECTURES,
    _build_gate_b_model,
)
from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
    BinaryInventory,
    collect_binary_inventory,
    extract_binary_snapshot,
    fix_binary_snapshot,
)
from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
    CLAIM_SCOPE,
    EXPECTED_MODEL_SIZE,
    FORMAL_PROJECT_TAC_READY,
    INDEPENDENT_ABSOLUTE_TOLERANCE,
    OBJECTIVE_ABSOLUTE_TOLERANCE_CNY,
    OBJECTIVE_RELATIVE_TOLERANCE,
    SOLVER_FEASIBILITY_TOLERANCE,
    TECHNICAL_RANKING_PERMITTED,
    _bound_and_constraint_audit,
    _ceil_upper_bound,
    _constraint_group_audits,
    _continuous_capacity_variables,
    _fixed_binary_audit,
    _inventory_lock_audit,
    _load_locked_d41_gate_a,
    _name_list_sha256,
    _objective_audit,
    _service_audit,
    _sha256,
    _solver_primal_audit,
    _tree_sha256,
    _variable_map,
    apply_complete_seed,
    read_seed_csv_gz,
    write_seed_csv_gz,
)
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.solver import create_highs_solver


RESULT_SCHEMA_ID = "tes_bess_boundary.e0d48_primal_recovery.v1"
REPAIR_SCHEMA_ID = "tes_bess_boundary.e0d48_original_cost_repair.v1"
BUILD_SCHEMA_ID = "tes_bess_boundary.e0d48_gate_a_build.v1"

D46_FORMAL_MANIFEST_SHA256 = (
    "8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9"
)
D46_POSTMORTEM_BUNDLE_SHA256 = (
    "c74a6943570690ace8573a0dee2f65aa763d0371854e01625337a46244a35b58"
)
D46_GUIDE_SHA256 = {
    Architecture.BESS: (
        "b69f4035deb5aa5f83a504e1e40347a23fa352b4104087bc017da6940c828b1f"
    ),
    Architecture.TES: (
        "d38004e6c3607cc2095c93def187de6d5300f5b9d9e97928872aaf6ce176e8e9"
    ),
    Architecture.HYBRID: (
        "9def0298195dbbebe477d9ff3b91f3b475082325eeea01dfc80c49930d532655"
    ),
}

FORMAL_THREADS = 12
FORMAL_RANDOM_SEED = 0
MIP_HEURISTIC_EFFORT = 0.20
CANDIDATE_SOFT_TIME_LIMIT_SECONDS = 3_600.0
CANDIDATE_HARD_WALL_SECONDS = 3_720.0
REPAIR_HARD_WALL_SECONDS = 1_500.0
ARCHITECTURE_HARD_WALL_SECONDS = 5_400.0
BATCH_HARD_WALL_SECONDS = 16_200.0

HIGHS_FEASIBILITY_OPTIONS: dict[str, object] = {
    "mip_heuristic_effort": MIP_HEURISTIC_EFFORT,
    "mip_heuristic_run_feasibility_jump": True,
    "mip_heuristic_run_rens": True,
    "mip_heuristic_run_rins": True,
    "mip_heuristic_run_root_reduced_cost": True,
    "mip_heuristic_run_shifting": True,
    "mip_heuristic_run_zi_round": True,
    "mip_detect_symmetry": True,
    "presolve": "choose",
}


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(payload))


def _code_hashes() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = (
        "e0d48_hamming_primal_recovery.py",
        "e0d48_monitored_executor.py",
        "e0d46_monitored_executor.py",
        "e0d41_strict_full_year_decomposition.py",
        "e0d46_full_year_feasible_upper_bound_repair.py",
        "e0d40_gate_b_solver.py",
        "e0d40_full_year_compute_gate.py",
        "planning_model.py",
    )
    return {name: _sha256(package / name) for name in names}


def constraint_identity(model: object) -> dict[str, Any]:
    """Hash active constraint names and expressions without changing the model."""

    from pyomo.environ import Constraint

    constraints = sorted(
        model.component_data_objects(
            Constraint,
            active=True,
            descend_into=True,
        ),
        key=lambda item: item.name,
    )
    name_digest = hashlib.sha256()
    expression_digest = hashlib.sha256()
    for constraint in constraints:
        name_digest.update(constraint.name.encode("utf-8"))
        name_digest.update(b"\0")
        expression_digest.update(constraint.name.encode("utf-8"))
        expression_digest.update(b"\0")
        for item in (constraint.lower, constraint.body, constraint.upper):
            expression_digest.update(str(item).encode("utf-8"))
            expression_digest.update(b"\0")
    return {
        "active_constraint_count": len(constraints),
        "active_constraint_names_sha256": name_digest.hexdigest(),
        "active_constraint_expressions_sha256": expression_digest.hexdigest(),
    }


def original_capacity_boundary_audit(
    model: object,
    architecture: Architecture,
) -> dict[str, Any]:
    """Require original finite capacity bounds and no D46 anchor fixing."""

    capacities = _continuous_capacity_variables(model, architecture)
    bounds: dict[str, dict[str, float | bool | None]] = {}
    passed = True
    for name, variable in sorted(capacities.items()):
        lower = None if variable.lb is None else float(variable.lb)
        upper = None if variable.ub is None else float(variable.ub)
        valid = (
            not variable.fixed
            and lower is not None
            and upper is not None
            and math.isfinite(lower)
            and math.isfinite(upper)
            and lower >= 0.0
            and upper >= lower
        )
        bounds[name] = {
            "lower": lower,
            "upper": upper,
            "fixed": bool(variable.fixed),
            "passed": valid,
        }
        passed = passed and valid
    expected_count = {
        Architecture.BESS: 4,
        Architecture.TES: 8,
        Architecture.HYBRID: 12,
    }[architecture]
    passed = passed and len(capacities) == expected_count
    return {
        "architecture": architecture.value,
        "continuous_capacity_variable_count": len(capacities),
        "expected_continuous_capacity_variable_count": expected_count,
        "fixed_continuous_capacity_variable_count": sum(
            bool(variable.fixed) for variable in capacities.values()
        ),
        "bounds": bounds,
        "d46_capacity_anchor_applied": False,
        "passed": passed,
    }


def replace_cost_objective_with_hamming(
    model: object,
    inventory: BinaryInventory,
    binary_seed: Mapping[str, int],
) -> dict[str, Any]:
    """Deactivate the sole original objective and add equal-weight Hamming."""

    from pyomo.environ import Objective, minimize, quicksum, value

    if set(binary_seed) != set(inventory.all_names):
        raise ValueError("D48 Hamming seed does not match the complete inventory")
    invalid = sorted(name for name, raw in binary_seed.items() if raw not in (0, 1))
    if invalid:
        raise ValueError(f"D48 Hamming seed contains invalid binaries: {invalid[:3]}")
    objectives = tuple(
        model.component_data_objects(
            Objective,
            active=True,
            descend_into=True,
        )
    )
    if len(objectives) != 1:
        raise ValueError("D48 requires exactly one active original objective")
    original = objectives[0]
    original_name = original.name
    original_sense = str(original.sense)
    original.deactivate()
    variables = _variable_map(model)
    expression = quicksum(
        variables[name] if binary_seed[name] == 0 else 1.0 - variables[name]
        for name in inventory.all_names
    )
    model.d48_hamming_distance = Objective(expr=expression, sense=minimize)
    active_after = tuple(
        model.component_data_objects(
            Objective,
            active=True,
            descend_into=True,
        )
    )
    seed_value = float(value(model.d48_hamming_distance, exception=True))
    passed = (
        len(active_after) == 1
        and active_after[0].name == "d48_hamming_distance"
        and seed_value == 0.0
    )
    return {
        "original_objective_name": original_name,
        "original_objective_sense": original_sense,
        "original_objective_active_after": bool(original.active),
        "hamming_objective_name": model.d48_hamming_distance.name,
        "hamming_binary_term_count": len(inventory.all_names),
        "hamming_binary_names_sha256": _name_list_sha256(inventory.all_names),
        "equal_binary_weight": 1.0,
        "auxiliary_variable_count": 0,
        "added_constraint_count": 0,
        "hamming_value_at_seed": seed_value,
        "active_objective_count_after": len(active_after),
        "passed": passed,
    }


def build_original_stage_model(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> tuple[object, object, BinaryInventory, dict[str, Any]]:
    """Rebuild the locked original MILP without D46 capacity anchors."""

    d41_gate_a = _load_locked_d41_gate_a(d41_gate_a_manifest_path)
    case, model, model_size = _build_gate_b_model(
        architecture,
        service_path,
        d40_gate_a_manifest_path,
        heat_path,
        vre_path,
        price_basis_path,
    )
    if model_size != EXPECTED_MODEL_SIZE[architecture]:
        raise ValueError("D48 original model size differs from the frozen contract")
    inventory = collect_binary_inventory(model)
    inventory_audit = _inventory_lock_audit(
        inventory,
        architecture,
        d41_gate_a,
    )
    if inventory_audit["passed"] is not True:
        raise ValueError("D48 binary inventory differs from locked D41 Gate A")
    capacity_audit = original_capacity_boundary_audit(model, architecture)
    if capacity_audit["passed"] is not True:
        raise ValueError("D48 original capacity boundary audit failed")
    return (
        case,
        model,
        inventory,
        {
            "model_size": model_size,
            "post_build_model_size": _linearity_audit(model),
            "binary_inventory_audit": inventory_audit,
            "original_capacity_boundary_audit": capacity_audit,
        },
    )


def prepare_hamming_model(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    guide_path: Path,
    require_locked_guide_hash: bool = True,
) -> tuple[dict[str, float], dict[str, int], dict[str, Any]]:
    """Load the complete D46 seed and replace only the objective."""

    guide_hash = _sha256(guide_path)
    expected_hash = D46_GUIDE_SHA256[architecture]
    if require_locked_guide_hash and guide_hash != expected_hash:
        raise ValueError("D48 D46 guide hash mismatch")
    variable_names = tuple(sorted(_variable_map(model)))
    values, binary_seed = read_seed_csv_gz(
        guide_path,
        expected_variable_names=variable_names,
        expected_binary_names=inventory.all_names,
    )
    seed_audit = apply_complete_seed(model, inventory, values, binary_seed)
    constraints_before = constraint_identity(model)
    objective_audit = replace_cost_objective_with_hamming(
        model,
        inventory,
        binary_seed,
    )
    constraints_after = constraint_identity(model)
    constraint_identity_preserved = constraints_before == constraints_after
    if not constraint_identity_preserved:
        raise ValueError("D48 objective replacement changed the active constraints")
    return (
        values,
        binary_seed,
        {
            "guide_sha256": guide_hash,
            "expected_guide_sha256": expected_hash,
            "guide_hash_required": require_locked_guide_hash,
            "seed_application_audit": seed_audit,
            "constraint_identity_before": constraints_before,
            "constraint_identity_after": constraints_after,
            "constraint_identity_preserved": constraint_identity_preserved,
            "objective_replacement_audit": objective_audit,
            "passed": (
                seed_audit["passed"]
                and objective_audit["passed"]
                and constraint_identity_preserved
            ),
        },
    )


def _configure_hamming_solver(
    *,
    time_limit_seconds: float,
    threads: int,
) -> object:
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0.0:
        raise ValueError("D48 candidate time limit must be finite and positive")
    solver = create_highs_solver(
        threads=threads,
        random_seed=FORMAL_RANDOM_SEED,
        mip_rel_gap=0.0,
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    solver.options["dual_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    solver.options["mip_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    for name, value in HIGHS_FEASIBILITY_OPTIONS.items():
        solver.options[name] = value
    solver.config.warmstart = True
    return solver


def highs_option_roundtrip() -> dict[str, Any]:
    """Round-trip every D48 native HiGHS option under the installed version."""

    import highspy

    highs = highspy.Highs()
    requested = {
        "threads": FORMAL_THREADS,
        "random_seed": FORMAL_RANDOM_SEED,
        "mip_feasibility_tolerance": SOLVER_FEASIBILITY_TOLERANCE,
        **HIGHS_FEASIBILITY_OPTIONS,
    }
    actual: dict[str, Any] = {}
    status: dict[str, str] = {}
    passed = True
    for name, expected in requested.items():
        set_status = highs.setOptionValue(name, expected)
        get_status, returned = highs.getOptionValue(name)
        status[name] = f"{set_status}/{get_status}"
        actual[name] = returned
        if isinstance(expected, float):
            equal = math.isclose(float(returned), expected, rel_tol=0.0, abs_tol=1e-15)
        else:
            equal = returned == expected
        passed = passed and equal and "kOk" in status[name]
    return {
        "highs_version": highs.version(),
        "requested": requested,
        "actual": actual,
        "status": status,
        "passed": passed,
    }


def capture_first_hamming_incumbent(
    model: object,
    *,
    time_limit_seconds: float,
    threads: int = FORMAL_THREADS,
) -> dict[str, Any]:
    """Capture the first complete Hamming-MILP incumbent and interrupt."""

    import highspy

    solver = _configure_hamming_solver(
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    solver.set_instance(model)
    expected_variable_names = set(_variable_map(model))
    mapped_variable_names = {
        solver._vars[variable_id][0].name
        for variable_id in solver._pyomo_var_to_solver_var_map
    }
    if mapped_variable_names != expected_variable_names:
        missing_count = len(expected_variable_names - mapped_variable_names)
        extra_count = len(mapped_variable_names - expected_variable_names)
        raise ValueError(
            "D48 HiGHS/Pyomo variable map does not cover the complete model "
            f"(missing={missing_count}, extra={extra_count})"
        )
    captured: dict[str, Any] = {}

    def _callback(event: object) -> None:
        if captured:
            return
        raw = tuple(float(item) for item in event.data_out.mip_solution)
        primal_bound = float(event.data_out.mip_primal_bound)
        if len(raw) != len(solver._pyomo_var_to_solver_var_map):
            return
        if not all(math.isfinite(item) for item in raw):
            return
        captured["column_values"] = raw
        captured["reported_hamming_objective"] = (
            primal_bound if math.isfinite(primal_bound) else None
        )
        event.interrupt()

    solver._solver_model.cbMipSolution.subscribe(_callback)
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(
            model,
            tee=True,
            load_solutions=False,
            warmstart=True,
        )
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    termination = str(results.solver.termination_condition).lower()
    model_status = solver._solver_model.getModelStatus()
    model_status_text = solver._solver_model.modelStatusToString(model_status)
    info = solver._solver_model.getInfo()
    solution = solver._solver_model.getSolution()
    solver_status = {
        "termination_condition": termination,
        "highs_model_status": model_status_text,
        "mip_node_count": int(getattr(info, "mip_node_count", -1)),
        "primal_solution_status": int(getattr(info, "primal_solution_status", -1)),
        "solution_value_valid": bool(getattr(solution, "value_valid", False)),
    }
    if not captured:
        complete_infeasible = (
            "infeasible" in termination
            and model_status_text.strip().lower() == "infeasible"
            and not solver_status["solution_value_valid"]
        )
        return {
            "status": (
                "engineering_mip_infeasible_under_original_bounds"
                if complete_infeasible
                else "no_primal_status_closure"
            ),
            "incumbent_captured": False,
            "runtime_seconds": runtime,
            "solver_status": solver_status,
            "complete_engineering_infeasible_status": complete_infeasible,
            "formal_upper_bound_eligible": False,
        }

    index_to_variable = {
        column: solver._vars[variable_id][0]
        for variable_id, column in solver._pyomo_var_to_solver_var_map.items()
    }
    if set(index_to_variable) != set(range(len(captured["column_values"]))):
        raise ValueError("D48 HiGHS/Pyomo column map is incomplete")
    values: dict[str, float] = {}
    for column, number in enumerate(captured["column_values"]):
        variable = index_to_variable[column]
        variable.set_value(number, skip_validation=True)
        values[variable.name] = number
    return {
        "status": "candidate_incumbent_captured",
        "incumbent_captured": True,
        "runtime_seconds": runtime,
        "solver_status": solver_status,
        "reported_hamming_objective": captured["reported_hamming_objective"],
        "variable_values": {name: values[name] for name in sorted(values)},
        "variable_count": len(values),
        "expected_variable_count": len(expected_variable_names),
        "complete_variable_mapping": True,
        "variable_names_sha256": _name_list_sha256(tuple(sorted(values))),
        "formal_upper_bound_eligible": False,
    }


def solve_hamming_candidate(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    guide_path: Path,
    candidate_output_path: Path,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
    threads: int = FORMAL_THREADS,
    require_locked_guide_hash: bool = True,
) -> dict[str, Any]:
    """Prepare one Hamming MILP and archive only an audited first incumbent."""

    _, _, preparation = prepare_hamming_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        require_locked_guide_hash=require_locked_guide_hash,
    )
    callback = capture_first_hamming_incumbent(
        model,
        time_limit_seconds=time_limit_seconds,
        threads=threads,
    )
    if callback["incumbent_captured"] is not True:
        return {
            **callback,
            "preparation_audit": preparation,
            "candidate_artifact": None,
        }
    values = callback.pop("variable_values")
    snapshot = extract_binary_snapshot(model, inventory, tolerance=1e-7)
    feasibility = _bound_and_constraint_audit(model)
    service = _service_audit(model)
    candidate_passed = feasibility["passed"] and service["passed"]
    artifact = None
    status = "no_primal_status_closure"
    if candidate_passed:
        artifact = write_seed_csv_gz(candidate_output_path, values, snapshot)
        status = "candidate_incumbent_captured"
    return {
        **callback,
        "status": status,
        "preparation_audit": preparation,
        "candidate_independent_feasibility_audit": feasibility,
        "candidate_service_audit": service,
        "candidate_audit_passed": candidate_passed,
        "binary_snapshot_variable_count": len(snapshot),
        "binary_snapshot_names_sha256": _name_list_sha256(tuple(sorted(snapshot))),
        "candidate_artifact": artifact,
        "candidate_requires_original_cost_repair": True,
        "formal_upper_bound_eligible": False,
    }


def d48_capacity_solution_audit(
    model: object,
    architecture: Architecture,
) -> dict[str, Any]:
    """Audit free continuous capacities and the fixed topology snapshot."""

    capacities = _continuous_capacity_variables(model, architecture)
    values: dict[str, float] = {}
    invalid: list[str] = []
    fixed: list[str] = []
    for name, variable in sorted(capacities.items()):
        if variable.fixed:
            fixed.append(name)
        raw = variable.value
        if raw is None or not math.isfinite(float(raw)):
            invalid.append(name)
            continue
        number = float(raw)
        values[name] = number
        if (
            variable.lb is not None
            and number < float(variable.lb) - INDEPENDENT_ABSOLUTE_TOLERANCE
        ):
            invalid.append(name)
        if (
            variable.ub is not None
            and number > float(variable.ub) + INDEPENDENT_ABSOLUTE_TOLERANCE
        ):
            invalid.append(name)
    return {
        "continuous_capacity_variable_count": len(capacities),
        "continuous_capacity_values": values,
        "fixed_continuous_capacity_count": len(fixed),
        "fixed_continuous_capacity_names_sha256": _name_list_sha256(tuple(fixed)),
        "invalid_continuous_capacity_count": len(set(invalid)),
        "invalid_continuous_capacity_names_sha256": _name_list_sha256(
            tuple(sorted(set(invalid)))
        ),
        "original_capacity_bounds_retained": True,
        "d46_capacity_anchor_applied": False,
        "passed": not fixed and not invalid,
    }


def audit_original_cost_repair(
    model: object,
    inventory: BinaryInventory,
    *,
    solver_primal_audit: Mapping[str, Any],
    architecture: Architecture,
    require_named_constraint_groups: bool = False,
) -> dict[str, Any]:
    """Grant a D48 upper bound only after the complete original-cost audit."""

    bounds_constraints = _bound_and_constraint_audit(model)
    binaries = _fixed_binary_audit(model, inventory)
    capacities = d48_capacity_solution_audit(model, architecture)
    named_groups = _constraint_group_audits(model, architecture)
    service = _service_audit(model)
    objective = _objective_audit(model)
    highs_objective = solver_primal_audit.get("highs_objective_value_cny")
    tolerance = max(
        OBJECTIVE_ABSOLUTE_TOLERANCE_CNY,
        OBJECTIVE_RELATIVE_TOLERANCE * abs(objective["model_objective_cny"]),
    )
    difference = (
        None
        if not isinstance(highs_objective, (int, float))
        or not math.isfinite(float(highs_objective))
        else objective["model_objective_cny"] - float(highs_objective)
    )
    objective["highs_objective_value_cny"] = highs_objective
    objective["model_minus_highs_objective_cny"] = difference
    objective["solver_objective_match"] = (
        difference is not None and abs(difference) <= tolerance
    )
    objective["passed"] = objective["passed"] and objective["solver_objective_match"]
    passed = all(
        (
            solver_primal_audit.get("passed") is True,
            bounds_constraints["passed"],
            binaries["passed"],
            capacities["passed"],
            named_groups["passed"] if require_named_constraint_groups else True,
            service["passed"],
            objective["passed"],
        )
    )
    return {
        "solver_primal": dict(solver_primal_audit),
        "bounds_and_constraints": bounds_constraints,
        "fixed_binaries": binaries,
        "capacity_policy": capacities,
        "named_constraint_groups": named_groups,
        "named_constraint_groups_required": require_named_constraint_groups,
        "service": service,
        "objective": objective,
        "engineering_numerical_feasibility_only": True,
        "rational_exact_feasibility_certificate": False,
        "audited_feasible_upper_bound_cny": (
            _ceil_upper_bound(objective["model_objective_cny"]) if passed else None
        ),
        "passed": passed,
    }


def solve_original_cost_repair(
    model: object,
    inventory: BinaryInventory,
    *,
    architecture: Architecture,
    candidate_path: Path,
    solution_output_path: Path,
    time_limit_seconds: float = REPAIR_HARD_WALL_SECONDS,
    threads: int = FORMAL_THREADS,
    require_named_constraint_groups: bool = False,
) -> dict[str, Any]:
    """Fix the complete candidate binary snapshot and solve the original LP."""

    import highspy

    variable_names = tuple(sorted(_variable_map(model)))
    values, snapshot = read_seed_csv_gz(
        candidate_path,
        expected_variable_names=variable_names,
        expected_binary_names=inventory.all_names,
    )
    apply_complete_seed(model, inventory, values, snapshot)
    fixing = fix_binary_snapshot(model, inventory, snapshot, tolerance=0.0)
    capacity_before = original_capacity_boundary_audit(model, architecture)
    if capacity_before["passed"] is not True:
        raise ValueError("D48 repair did not retain original free capacity bounds")
    solver = create_highs_solver(
        threads=threads,
        random_seed=FORMAL_RANDOM_SEED,
        mip_rel_gap=0.0,
    )
    solver.options["time_limit"] = time_limit_seconds
    solver.options["primal_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    solver.options["dual_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    solver.options["mip_feasibility_tolerance"] = SOLVER_FEASIBILITY_TOLERANCE
    started = perf_counter()
    highspy.Highs.resetGlobalScheduler(True)
    try:
        results = solver.solve(model, tee=True, load_solutions=False)
        try:
            solver.load_vars()
            solution_loaded = True
        except Exception:  # noqa: BLE001 - canonical failed-repair evidence
            solution_loaded = False
    finally:
        highspy.Highs.resetGlobalScheduler(True)
    runtime = perf_counter() - started
    audit = None
    solution_artifact = None
    if solution_loaded:
        audit = audit_original_cost_repair(
            model,
            inventory,
            solver_primal_audit=_solver_primal_audit(solver),
            architecture=architecture,
            require_named_constraint_groups=require_named_constraint_groups,
        )
        solution_values = {
            name: float(variable.value)
            for name, variable in sorted(_variable_map(model).items())
        }
        solution_artifact = write_seed_csv_gz(
            solution_output_path,
            solution_values,
            snapshot,
        )
    passed = bool(audit is not None and audit["passed"] is True)
    return {
        "schema_id": REPAIR_SCHEMA_ID,
        "status": (
            "audited_feasible_upper_bound_recovered"
            if passed
            else "candidate_found_but_repair_failed"
        ),
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "termination_condition": str(results.solver.termination_condition).lower(),
        "runtime_seconds": runtime,
        "solution_loaded": solution_loaded,
        "binary_fixing_audit": fixing,
        "original_capacity_boundary_audit_before_solve": capacity_before,
        "candidate_artifact_sha256": _sha256(candidate_path),
        "solution_artifact": solution_artifact,
        "solution_audit": audit,
    }


def _formal_base_payload(
    *,
    architecture: Architecture,
    stage: str,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
) -> dict[str, Any]:
    return {
        "schema_id": RESULT_SCHEMA_ID,
        "architecture": architecture.value,
        "stage": stage,
        "claim_scope": CLAIM_SCOPE,
        "formal_project_tac_ready": FORMAL_PROJECT_TAC_READY,
        "technical_ranking_permitted": TECHNICAL_RANKING_PERMITTED,
        "representative_period_input_used": False,
        "service_contract_sha256": _sha256(service_path),
        "d40_gate_a_manifest_sha256": _sha256(d40_gate_a_manifest_path),
        "d41_gate_a_manifest_sha256": _sha256(d41_gate_a_manifest_path),
        "input_sha256": {
            "heat": _sha256(heat_path),
            "vre": _sha256(vre_path),
            "price_basis_tree": _tree_sha256(price_basis_path),
        },
        "provenance": {"code_sha256": _code_hashes()},
    }


def solve_candidate_child(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    guide_path: Path,
    candidate_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = CANDIDATE_SOFT_TIME_LIMIT_SECONDS,
) -> dict[str, Any]:
    base = _formal_base_payload(
        architecture=architecture,
        stage="candidate",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    solver_invoked = False
    try:
        _, model, inventory, build_audit = build_original_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        candidate = solve_hamming_candidate(
            model,
            inventory,
            architecture=architecture,
            guide_path=guide_path,
            candidate_output_path=candidate_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_locked_guide_hash=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **candidate,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "no_primal_status_closure",
            "solver_invoked": solver_invoked,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "formal_upper_bound_eligible": False,
        }
    _write_json(result_output_path, payload)
    return payload


def solve_repair_child(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    candidate_path: Path,
    solution_output_path: Path,
    result_output_path: Path,
    threads: int = FORMAL_THREADS,
    time_limit_seconds: float = REPAIR_HARD_WALL_SECONDS,
) -> dict[str, Any]:
    base = _formal_base_payload(
        architecture=architecture,
        stage="repair",
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    solver_invoked = False
    try:
        _, model, inventory, build_audit = build_original_stage_model(
            architecture=architecture,
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        )
        solver_invoked = True
        repair = solve_original_cost_repair(
            model,
            inventory,
            architecture=architecture,
            candidate_path=candidate_path,
            solution_output_path=solution_output_path,
            time_limit_seconds=time_limit_seconds,
            threads=threads,
            require_named_constraint_groups=True,
        )
        payload = {
            **base,
            "solver_invoked": True,
            "build_audit": build_audit,
            **repair,
        }
    except Exception as error:  # noqa: BLE001 - canonical formal evidence
        payload = {
            **base,
            "status": "candidate_found_but_repair_failed",
            "solver_invoked": solver_invoked,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    _write_json(result_output_path, payload)
    return payload


def write_gate_a_build_audit(
    *,
    architecture: Architecture,
    service_path: Path,
    d40_gate_a_manifest_path: Path,
    d41_gate_a_manifest_path: Path,
    heat_path: Path,
    vre_path: Path,
    price_basis_path: Path,
    guide_path: Path,
    result_output_path: Path,
) -> dict[str, Any]:
    """Build and transform one formal 8784 h model without invoking HiGHS."""

    started = perf_counter()
    _, model, inventory, build_audit = build_original_stage_model(
        architecture=architecture,
        service_path=service_path,
        d40_gate_a_manifest_path=d40_gate_a_manifest_path,
        d41_gate_a_manifest_path=d41_gate_a_manifest_path,
        heat_path=heat_path,
        vre_path=vre_path,
        price_basis_path=price_basis_path,
    )
    _, _, preparation = prepare_hamming_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        require_locked_guide_hash=True,
    )
    post_size = _linearity_audit(model)
    passed = all(
        (
            build_audit["binary_inventory_audit"]["passed"],
            build_audit["original_capacity_boundary_audit"]["passed"],
            preparation["passed"],
            post_size == EXPECTED_MODEL_SIZE[architecture],
        )
    )
    payload = {
        **_formal_base_payload(
            architecture=architecture,
            stage="gate_a_build_only",
            service_path=service_path,
            d40_gate_a_manifest_path=d40_gate_a_manifest_path,
            d41_gate_a_manifest_path=d41_gate_a_manifest_path,
            heat_path=heat_path,
            vre_path=vre_path,
            price_basis_path=price_basis_path,
        ),
        "schema_id": BUILD_SCHEMA_ID,
        "status": "gate_a_build_passed" if passed else "gate_a_build_failed",
        "solver_invoked": False,
        "formal_optimization_invoked": False,
        "runtime_seconds": perf_counter() - started,
        "build_audit": build_audit,
        "hamming_preparation_audit": preparation,
        "post_hamming_model_size": post_size,
        "highs_option_roundtrip": highs_option_roundtrip(),
        "audit": {"passed": passed},
    }
    payload["audit"]["passed"] = (
        payload["audit"]["passed"] and payload["highs_option_roundtrip"]["passed"]
    )
    if payload["audit"]["passed"] is not True:
        payload["status"] = "gate_a_build_failed"
    _write_json(result_output_path, payload)
    return payload


def _add_formal_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--architecture",
        choices=[item.value for item in FORMAL_ARCHITECTURES],
        required=True,
    )
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--d40-gate-a", type=Path, required=True)
    parser.add_argument("--d41-gate-a", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--vre", type=Path, required=True)
    parser.add_argument("--price-basis", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    candidate = subparsers.add_parser("candidate")
    _add_formal_inputs(candidate)
    candidate.add_argument("--guide", type=Path, required=True)
    candidate.add_argument("--candidate-output", type=Path, required=True)
    candidate.add_argument("--result-output", type=Path, required=True)
    candidate.add_argument("--threads", type=int, default=FORMAL_THREADS)
    candidate.add_argument(
        "--time-limit", type=float, default=CANDIDATE_SOFT_TIME_LIMIT_SECONDS
    )
    repair = subparsers.add_parser("repair")
    _add_formal_inputs(repair)
    repair.add_argument("--candidate", type=Path, required=True)
    repair.add_argument("--solution-output", type=Path, required=True)
    repair.add_argument("--result-output", type=Path, required=True)
    repair.add_argument("--threads", type=int, default=FORMAL_THREADS)
    repair.add_argument("--time-limit", type=float, default=REPAIR_HARD_WALL_SECONDS)
    gate_a = subparsers.add_parser("gate-a-build")
    _add_formal_inputs(gate_a)
    gate_a.add_argument("--guide", type=Path, required=True)
    gate_a.add_argument("--result-output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    common = {
        "architecture": Architecture(args.architecture),
        "service_path": args.service,
        "d40_gate_a_manifest_path": args.d40_gate_a,
        "d41_gate_a_manifest_path": args.d41_gate_a,
        "heat_path": args.heat,
        "vre_path": args.vre,
        "price_basis_path": args.price_basis,
    }
    if args.command == "candidate":
        solve_candidate_child(
            **common,
            guide_path=args.guide,
            candidate_output_path=args.candidate_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit,
        )
        return
    if args.command == "repair":
        solve_repair_child(
            **common,
            candidate_path=args.candidate,
            solution_output_path=args.solution_output,
            result_output_path=args.result_output,
            threads=args.threads,
            time_limit_seconds=args.time_limit,
        )
        return
    write_gate_a_build_audit(
        **common,
        guide_path=args.guide,
        result_output_path=args.result_output,
    )


if __name__ == "__main__":
    main()
