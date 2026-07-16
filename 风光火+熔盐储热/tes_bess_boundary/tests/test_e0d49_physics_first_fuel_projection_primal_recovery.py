from __future__ import annotations

import math
from pathlib import Path

import pytest


def test_deterministic_fuel_lift_covers_every_segment_and_knot_tie() -> None:
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        deterministic_fuel_lift_point,
    )

    knots = ((10.0, 1.0), (20.0, 3.0), (30.0, 4.0), (40.0, 8.0))
    for segment, power in enumerate((15.0, 25.0, 35.0)):
        lifted = deterministic_fuel_lift_point(
            online=1.0,
            power_gross_mw=power,
            fuel_knots=knots,
        )
        assert lifted["selected_segment"] == segment
        assert sum(lifted["segment_active"]) == 1
        assert lifted["segment_fraction"][segment] == pytest.approx(0.5)
        assert lifted["fuel_code_bits"] == tuple(
            (segment >> bit) & 1 for bit in range(2)
        )

    first_internal_knot = deterministic_fuel_lift_point(
        online=1.0,
        power_gross_mw=20.0,
        fuel_knots=knots,
    )
    second_internal_knot = deterministic_fuel_lift_point(
        online=1.0,
        power_gross_mw=30.0,
        fuel_knots=knots,
    )
    maximum_knot = deterministic_fuel_lift_point(
        online=1.0,
        power_gross_mw=40.0,
        fuel_knots=knots,
    )
    assert first_internal_knot["selected_segment"] == 0
    assert first_internal_knot["segment_fraction"][0] == 1.0
    assert second_internal_knot["selected_segment"] == 1
    assert second_internal_knot["segment_fraction"][1] == 1.0
    assert maximum_knot["selected_segment"] == 2
    assert maximum_knot["segment_fraction"][2] == 1.0


def test_deterministic_fuel_lift_handles_offline_and_rejects_corruption() -> None:
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        deterministic_fuel_lift_point,
    )

    knots = ((10.0, 1.0), (20.0, 3.0), (30.0, 4.0))
    offline = deterministic_fuel_lift_point(
        online=0.0,
        power_gross_mw=0.0,
        fuel_knots=knots,
    )
    assert offline["selected_segment"] is None
    assert offline["fuel_tce_per_hour"] == 0.0
    assert offline["segment_active"] == (0, 0)
    assert offline["fuel_code_bits"] == (0,)

    with pytest.raises(ValueError, match="not binary"):
        deterministic_fuel_lift_point(
            online=0.5,
            power_gross_mw=0.0,
            fuel_knots=knots,
        )
    with pytest.raises(ValueError, match="offline CHP"):
        deterministic_fuel_lift_point(
            online=0.0,
            power_gross_mw=1.0,
            fuel_knots=knots,
        )
    with pytest.raises(ValueError, match="below the fuel domain"):
        deterministic_fuel_lift_point(
            online=1.0,
            power_gross_mw=9.0,
            fuel_knots=knots,
        )
    with pytest.raises(ValueError, match="above the fuel domain"):
        deterministic_fuel_lift_point(
            online=1.0,
            power_gross_mw=31.0,
            fuel_knots=knots,
        )


def _toy_case_and_model(architecture_name: str):
    from test_e0d46_full_year_feasible_upper_bound_repair import (
        _gate_a_24h_case,
    )

    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture = Architecture(architecture_name)
    case = _gate_a_24h_case(architecture)
    return architecture, case, build_endogenous_capacity_model(case)


def test_partition_and_dependency_audit_on_actual_chp_model() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        fuel_projection_dependency_audit,
        partition_fuel_code_binaries,
    )

    architecture, _, model = _toy_case_and_model("bess")
    inventory = collect_binary_inventory(model)
    partition, audit = partition_fuel_code_binaries(
        model,
        inventory,
        architecture=architecture,
        require_formal_counts=False,
    )
    assert audit["passed"] is True
    assert len(partition.projected_fuel_code_names) == 24
    assert len(partition.physical_binary_names) == len(inventory.all_names) - 24
    dependency = fuel_projection_dependency_audit(model)
    assert dependency["passed"] is True
    assert dependency["fuel_code_variable_count"] == 24
    assert dependency["fuel_flow_variable_count"] == 24
    assert dependency["objective_code_variable_count"] == 0
    assert dependency["objective_fuel_flow_variable_count"] == 24


def test_dependency_audit_rejects_a_new_fuel_cap() -> None:
    from pyomo.environ import Constraint

    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        fuel_projection_dependency_audit,
    )

    _, _, model = _toy_case_and_model("bess")
    model.forbidden_fuel_cap = Constraint(
        expr=sum(model.chp[0].fuel_tce_per_hour.values()) <= 1e9
    )
    audit = fuel_projection_dependency_audit(model)
    assert audit["passed"] is False
    assert audit["forbidden_flow_constraint_count"] == 1
    assert audit["fuel_or_emissions_cap_detected"] is True


def test_static_lift_audit_covers_registered_chp_segments() -> None:
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        static_fuel_lift_spec_audit,
    )

    _, case, _ = _toy_case_and_model("bess")
    audit = static_fuel_lift_spec_audit(case.chp_units)
    assert audit["passed"] is True
    assert audit["chp_unit_count"] == 1
    assert audit["unit_audit"]["0"]["midpoint_check_count"] == 1
    assert audit["unit_audit"]["0"]["minimum_knot_check_passed"] is True
    assert audit["unit_audit"]["0"]["maximum_knot_check_passed"] is True


def test_prepare_projects_only_fuel_codes_and_hamming_uses_physical_bits(
    tmp_path: Path,
) -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d46_full_year_feasible_upper_bound_repair import (
        write_seed_csv_gz,
    )
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        prepare_physics_first_model,
    )

    architecture, _, model = _toy_case_and_model("bess")
    inventory = collect_binary_inventory(model)
    values: dict[str, float] = {}
    for variable in model.component_data_objects(Var, active=True):
        variable.set_value(0.0, skip_validation=True)
        values[variable.name] = 0.0
    snapshot = {name: 0 for name in inventory.all_names}
    guide_path = tmp_path / "guide.csv.gz"
    write_seed_csv_gz(guide_path, values, snapshot)

    partition, _, audit = prepare_physics_first_model(
        model,
        inventory,
        architecture=architecture,
        guide_path=guide_path,
        require_locked_guide_hash=False,
        require_formal_counts=False,
    )
    assert audit["passed"] is True
    assert audit["constraint_identity_preserved"] is True
    objective = audit["objective_replacement_audit"]
    assert objective["hamming_physical_binary_term_count"] == len(
        partition.physical_binary_names
    )
    assert objective["projected_fuel_code_binary_term_count"] == 0
    variable_map = {
        variable.name: variable for variable in model.component_data_objects(Var)
    }
    assert all(
        not variable_map[name].is_binary()
        for name in partition.projected_fuel_code_names
    )
    assert all(
        variable_map[name].is_binary() for name in partition.physical_binary_names
    )


@pytest.mark.solver
@pytest.mark.integration
@pytest.mark.parametrize("architecture_name", ["bess", "tes", "hybrid"])
def test_gate_a_24h_physics_first_paths_recover_toy_upper_bound(
    tmp_path: Path,
    architecture_name: str,
) -> None:
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
    )
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        solve_d49_original_cost_repair,
        solve_physics_first_candidate,
    )
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture, case, guide_model = _toy_case_and_model(architecture_name)
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
    assert original_capacity_boundary_audit(candidate_model, architecture)["passed"]
    candidate_path = tmp_path / f"{architecture_name}_candidate.csv.gz"
    candidate = solve_physics_first_candidate(
        candidate_model,
        candidate_inventory,
        case.chp_units,
        architecture=architecture,
        guide_path=guide_path,
        candidate_output_path=candidate_path,
        time_limit_seconds=30.0,
        threads=1,
        require_locked_guide_hash=False,
        require_formal_counts=False,
    )
    assert candidate["status"] == "candidate_incumbent_captured_and_exactly_lifted"
    assert candidate["candidate_audit_passed"] is True
    assert candidate["exact_fuel_lift_audit"]["passed"] is True
    assert candidate["binary_snapshot_variable_count"] == len(
        candidate_inventory.all_names
    )

    repair_model = build_endogenous_capacity_model(case)
    repair_inventory = collect_binary_inventory(repair_model)
    solution_path = tmp_path / f"{architecture_name}_repair.csv.gz"
    repaired = solve_d49_original_cost_repair(
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
    assert repaired["schema_id"].endswith("e0d49_original_cost_repair.v1")
    audit = repaired["solution_audit"]
    assert audit["passed"] is True
    assert audit["capacity_policy"]["fixed_continuous_capacity_count"] == 0
    assert audit["audited_feasible_upper_bound_cny"] is not None
    assert math.isfinite(float(audit["audited_feasible_upper_bound_cny"]))
