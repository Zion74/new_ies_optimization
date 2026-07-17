from __future__ import annotations

import math
from pathlib import Path

import pytest


def _small_bess_model(*, infeasible: bool = False):
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        Expression,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
    )

    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        PCC_EXPORT_TARGET_MWH,
    )

    model = ConcreteModel()
    model.x = Var(domain=Binary)
    model.y = Var(domain=Binary)
    model.require_x = Constraint(expr=model.x == 1)
    model.require_y = Constraint(expr=model.y == 0)
    if infeasible:
        model.reject_x = Constraint(expr=model.x == 0)
    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.bess.energy_capacity_mwh = Var(
        domain=NonNegativeReals,
        bounds=(0.0, 2_400.0),
    )
    model.bess.charge_power_capacity_mw = Var(
        domain=NonNegativeReals,
        bounds=(0.0, 100.0),
    )
    model.bess.discharge_power_capacity_mw = Var(
        domain=NonNegativeReals,
        bounds=(0.0, 100.0),
    )
    model.bess.pcs_power_capacity_mw = Var(
        domain=NonNegativeReals,
        bounds=(0.0, 100.0),
    )
    model.capacity_link = Constraint(
        expr=(
            model.bess.energy_capacity_mwh
            + model.bess.charge_power_capacity_mw
            + model.bess.discharge_power_capacity_mw
            + model.bess.pcs_power_capacity_mw
            >= 2.0 * model.x
        )
    )
    model.annual_pcc_export_mwh = Expression(expr=PCC_EXPORT_TARGET_MWH)
    model.annual_curtailment_mwh = Expression(expr=0.0)
    model.annual_operating_cost_cny = Expression(expr=10.0 + model.x)
    model.planning_storage_capacity_cost_cny = Expression(
        expr=model.bess.energy_capacity_mwh
    )
    model.planning_bess_cycle_cost_cny = Expression(expr=0.0)
    model.planning_bess_variable_om_cost_cny = Expression(expr=0.0)
    model.planning_total_cost_cny = Expression(
        expr=(
            model.annual_operating_cost_cny
            + model.planning_storage_capacity_cost_cny
            + model.planning_bess_cycle_cost_cny
            + model.planning_bess_variable_om_cost_cny
        )
    )
    model.planning_cost = Objective(
        expr=model.planning_total_cost_cny,
        sense=minimize,
    )
    for variable in model.component_data_objects(Var, active=True):
        variable.set_value(0.0, skip_validation=True)
    return model


def _write_small_seed(model, inventory, path: Path) -> dict[str, int]:
    from pyomo.environ import Var

    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        write_seed_csv_gz,
    )

    values = {
        variable.name: float(variable.value)
        for variable in model.component_data_objects(
            Var,
            active=True,
            descend_into=True,
        )
    }
    binaries = {name: 0 for name in inventory.all_names}
    values.update({name: float(raw) for name, raw in binaries.items()})
    write_seed_csv_gz(path, values, binaries)
    return binaries


def test_hamming_objective_is_equal_weight_and_constraint_preserving() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        constraint_identity,
        replace_cost_objective_with_hamming,
    )

    model = _small_bess_model()
    inventory = collect_binary_inventory(model)
    seed = {name: 0 for name in inventory.all_names}
    before = constraint_identity(model)
    audit = replace_cost_objective_with_hamming(model, inventory, seed)
    after = constraint_identity(model)

    assert audit["passed"] is True
    assert audit["equal_binary_weight"] == 1.0
    assert audit["hamming_binary_term_count"] == len(inventory.all_names)
    assert audit["auxiliary_variable_count"] == 0
    assert audit["added_constraint_count"] == 0
    assert value(model.d48_hamming_distance) == 0.0
    assert before == after
    assert model.planning_cost.active is False


def test_original_capacity_boundary_rejects_d46_anchor_fixing() -> None:
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        original_capacity_boundary_audit,
    )
    from tes_bess_boundary.model import Architecture

    model = _small_bess_model()
    assert original_capacity_boundary_audit(model, Architecture.BESS)["passed"]
    model.bess.energy_capacity_mwh.fix(2_400.0)
    audit = original_capacity_boundary_audit(model, Architecture.BESS)
    assert audit["passed"] is False
    assert audit["d46_capacity_anchor_applied"] is False
    assert audit["fixed_continuous_capacity_variable_count"] == 1


def test_prepare_hamming_model_rejects_fractional_or_incomplete_seed(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from pyomo.environ import Var

    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        write_seed_csv_gz,
    )
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        prepare_hamming_model,
        replace_cost_objective_with_hamming,
    )
    from tes_bess_boundary.model import Architecture

    model = _small_bess_model()
    inventory = collect_binary_inventory(model)
    fractional = {name: 0 for name in inventory.all_names}
    first = inventory.all_names[0]
    fractional[first] = 0.5
    with pytest.raises(ValueError, match="invalid binaries"):
        replace_cost_objective_with_hamming(model, inventory, fractional)

    incomplete_model = _small_bess_model()
    incomplete_inventory = collect_binary_inventory(incomplete_model)
    values = {
        variable.name: float(variable.value)
        for variable in incomplete_model.component_data_objects(
            Var,
            active=True,
            descend_into=True,
        )
    }
    binaries = {name: 0 for name in incomplete_inventory.all_names}
    values.update({name: float(raw) for name, raw in binaries.items()})
    continuous_name = next(name for name in values if name not in binaries)
    values.pop(continuous_name)
    seed_path = tmp_path / "incomplete_seed.csv.gz"
    write_seed_csv_gz(seed_path, values, binaries)
    with pytest.raises(ValueError, match="variable names"):
        prepare_hamming_model(
            incomplete_model,
            incomplete_inventory,
            architecture=Architecture.BESS,
            guide_path=seed_path,
            require_locked_guide_hash=False,
        )


def test_highs_1151_feasibility_options_round_trip() -> None:
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        highs_option_roundtrip,
    )

    audit = highs_option_roundtrip()
    assert audit["highs_version"] == "1.15.1"
    assert audit["passed"] is True
    assert audit["actual"]["mip_heuristic_effort"] == 0.2
    assert audit["actual"]["mip_heuristic_run_shifting"] is True
    assert audit["actual"]["mip_heuristic_run_zi_round"] is True


@pytest.mark.solver
def test_hamming_candidate_and_free_capacity_original_cost_repair(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        solve_hamming_candidate,
        solve_original_cost_repair,
    )
    from tes_bess_boundary.model import Architecture

    guide_model = _small_bess_model()
    guide_inventory = collect_binary_inventory(guide_model)
    guide_path = tmp_path / "guide.csv.gz"
    _write_small_seed(guide_model, guide_inventory, guide_path)

    candidate_model = _small_bess_model()
    candidate_inventory = collect_binary_inventory(candidate_model)
    candidate_path = tmp_path / "candidate.csv.gz"
    candidate = solve_hamming_candidate(
        candidate_model,
        candidate_inventory,
        architecture=Architecture.BESS,
        guide_path=guide_path,
        candidate_output_path=candidate_path,
        time_limit_seconds=30.0,
        threads=1,
        require_locked_guide_hash=False,
    )
    assert candidate["status"] == "candidate_incumbent_captured"
    assert candidate["candidate_audit_passed"] is True
    assert candidate["reported_hamming_objective"] is not None
    assert candidate_path.is_file()

    repair_model = _small_bess_model()
    repair_inventory = collect_binary_inventory(repair_model)
    solution_path = tmp_path / "solution.csv.gz"
    repair = solve_original_cost_repair(
        repair_model,
        repair_inventory,
        architecture=Architecture.BESS,
        candidate_path=candidate_path,
        solution_output_path=solution_path,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert repair["status"] == "audited_feasible_upper_bound_recovered"
    assert repair["solution_audit"]["passed"] is True
    assert (
        repair["solution_audit"]["capacity_policy"]["fixed_continuous_capacity_count"]
        == 0
    )
    assert (
        float(repair["solution_audit"]["audited_feasible_upper_bound_cny"])
        >= repair["solution_audit"]["objective"]["model_objective_cny"]
    )
    assert solution_path.is_file()


@pytest.mark.solver
def test_complete_infeasible_status_is_separate_from_timeout() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        capture_first_hamming_incumbent,
        replace_cost_objective_with_hamming,
    )

    model = _small_bess_model(infeasible=True)
    inventory = collect_binary_inventory(model)
    replace_cost_objective_with_hamming(
        model,
        inventory,
        {name: 0 for name in inventory.all_names},
    )
    result = capture_first_hamming_incumbent(
        model,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert result["status"] == "engineering_mip_infeasible_under_original_bounds"
    assert result["complete_engineering_infeasible_status"] is True
    assert result["incumbent_captured"] is False


@pytest.mark.solver
@pytest.mark.integration
@pytest.mark.parametrize("architecture_name", ["bess", "tes", "hybrid"])
def test_gate_a_24h_hamming_paths_recover_toy_upper_bound(
    tmp_path: Path,
    architecture_name: str,
) -> None:
    from test_e0d46_full_year_feasible_upper_bound_repair import (
        _gate_a_24h_case,
    )

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        fix_engineering_capacity_anchor,
        solve_continuous_guide,
    )
    from tes_bess_boundary.e0d48_hamming_primal_recovery import (
        original_capacity_boundary_audit,
        solve_hamming_candidate,
        solve_original_cost_repair,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture = Architecture(architecture_name)
    case = _gate_a_24h_case(architecture)
    guide_model = build_endogenous_capacity_model(case)
    guide_inventory = collect_binary_inventory(guide_model)
    assert fix_engineering_capacity_anchor(guide_model, architecture)["passed"]
    assert apply_relaxation(
        guide_model,
        guide_inventory,
        RelaxationMode.R0,
    )["passed"]
    guide_path = tmp_path / f"{architecture_name}_guide.csv.gz"
    guide = solve_continuous_guide(
        guide_model,
        guide_inventory,
        seed_output_path=guide_path,
        time_limit_seconds=30.0,
        threads=1,
    )
    assert guide["status"] == "continuous_guide_recovered"

    candidate_model = build_endogenous_capacity_model(case)
    candidate_inventory = collect_binary_inventory(candidate_model)
    assert original_capacity_boundary_audit(
        candidate_model,
        architecture,
    )["passed"]
    candidate_path = tmp_path / f"{architecture_name}_candidate.csv.gz"
    candidate = solve_hamming_candidate(
        candidate_model,
        candidate_inventory,
        architecture=architecture,
        guide_path=guide_path,
        candidate_output_path=candidate_path,
        time_limit_seconds=30.0,
        threads=1,
        require_locked_guide_hash=False,
    )
    assert candidate["status"] == "candidate_incumbent_captured"
    assert candidate["candidate_audit_passed"] is True

    repair_model = build_endogenous_capacity_model(case)
    repair_inventory = collect_binary_inventory(repair_model)
    solution_path = tmp_path / f"{architecture_name}_repair.csv.gz"
    repaired = solve_original_cost_repair(
        repair_model,
        repair_inventory,
        architecture=architecture,
        candidate_path=candidate_path,
        solution_output_path=solution_path,
        time_limit_seconds=30.0,
        threads=1,
        require_named_constraint_groups=True,
    )
    assert repaired["status"] == "audited_feasible_upper_bound_recovered"
    audit = repaired["solution_audit"]
    assert audit["passed"] is True
    assert audit["capacity_policy"]["fixed_continuous_capacity_count"] == 0
    assert audit["audited_feasible_upper_bound_cny"] is not None
    assert math.isfinite(float(audit["audited_feasible_upper_bound_cny"]))
