from __future__ import annotations

import json
import math
from pathlib import Path

import pytest


def _toy_case_and_model():
    from test_e0d46_full_year_feasible_upper_bound_repair import _gate_a_24h_case

    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture = Architecture.BESS
    case = _gate_a_24h_case(architecture)
    return architecture, case, build_endogenous_capacity_model(case)


def _toy_partition(model: object):
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )
    from tes_bess_boundary.e0d49_physics_first_fuel_projection_primal_recovery import (
        partition_fuel_code_binaries,
    )

    from tes_bess_boundary.model import Architecture

    inventory = collect_binary_inventory(model)
    partition, audit = partition_fuel_code_binaries(
        model,
        inventory,
        architecture=Architecture.BESS,
        require_formal_counts=False,
    )
    assert audit["passed"] is True
    return inventory, partition


def test_formal_commit_blocks_cover_real_year_without_padding_or_wraparound() -> None:
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        commit_block_coverage_audit,
        build_commit_blocks,
    )

    periods = tuple(range(8784))
    blocks = build_commit_blocks(periods)
    audit = commit_block_coverage_audit(
        periods,
        blocks,
        require_formal_counts=True,
    )
    assert audit["passed"] is True
    assert len(blocks) == 53
    assert [block.hours for block in blocks[:-1]] == [168] * 52
    assert blocks[-1].hours == 48
    assert blocks[-1].periods == tuple(range(8736, 8784))


def test_actual_bess_model_physical_layout_is_complete_and_time_indexed() -> None:
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        build_physical_time_layout,
    )

    _, _, model = _toy_case_and_model()
    _, partition = _toy_partition(model)
    layout, audit = build_physical_time_layout(
        model,
        partition.physical_binary_names,
        require_formal_counts=False,
    )
    assert audit["passed"] is True
    assert audit["period_count"] == 24
    assert audit["hourly_binary_count_per_period"] == 2
    assert layout.global_names == ("bess.installed",)
    assert set(layout.all_names) == set(partition.physical_binary_names)


def test_three_block_domain_plans_have_exact_fixed_active_relaxed_counts() -> None:
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        build_commit_blocks,
        build_physical_time_layout,
        make_stage_domain_plan,
    )

    _, _, model = _toy_case_and_model()
    _, partition = _toy_partition(model)
    layout, _ = build_physical_time_layout(
        model,
        partition.physical_binary_names,
        require_formal_counts=False,
    )
    blocks = build_commit_blocks(layout.periods, commit_hours=8)
    plans = [
        make_stage_domain_plan(
            layout,
            blocks,
            partition.projected_fuel_code_names,
            index,
        )
        for index in range(3)
    ]
    assert [len(plan.fixed_physical_names) for plan in plans] == [0, 17, 33]
    assert [len(plan.active_physical_names) for plan in plans] == [33, 32, 16]
    assert [len(plan.relaxed_physical_names) for plan in plans] == [16, 0, 0]
    for plan in plans:
        categories = (
            set(plan.fixed_physical_names),
            set(plan.active_physical_names),
            set(plan.relaxed_physical_names),
            set(plan.projected_fuel_names),
        )
        assert set().union(*categories) == set(_toy_partition(model)[0].all_names)
        assert all(
            not categories[left] & categories[right]
            for left in range(4)
            for right in range(left + 1, 4)
        )


def test_stage_domain_application_rejects_an_incomplete_fixed_prefix() -> None:
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        apply_stage_domain_plan,
        build_commit_blocks,
        build_physical_time_layout,
        make_stage_domain_plan,
    )

    _, _, model = _toy_case_and_model()
    inventory, partition = _toy_partition(model)
    layout, _ = build_physical_time_layout(
        model,
        partition.physical_binary_names,
        require_formal_counts=False,
    )
    blocks = build_commit_blocks(layout.periods, commit_hours=8)
    plan = make_stage_domain_plan(
        layout,
        blocks,
        partition.projected_fuel_code_names,
        1,
    )
    with pytest.raises(ValueError, match="fixed snapshot"):
        apply_stage_domain_plan(model, inventory, plan, {})


def test_layout_rejects_an_unregistered_physical_binary() -> None:
    from pyomo.environ import Binary, Var

    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        build_physical_time_layout,
    )

    _, _, model = _toy_case_and_model()
    _, partition = _toy_partition(model)
    model.forbidden_physical = Var(domain=Binary)
    _, audit = build_physical_time_layout(
        model,
        (*partition.physical_binary_names, "forbidden_physical"),
        require_formal_counts=False,
    )
    assert audit["passed"] is False
    assert audit["forbidden_physical_name_count"] == 1


@pytest.mark.solver
@pytest.mark.integration
def test_shortened_three_block_path_lifts_and_repairs_original_cost(
    tmp_path: Path,
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
    from tes_bess_boundary.e0d50_full_year_coupled_physical_block_relax_and_fix import (
        solve_block_relax_and_fix_candidate,
        solve_d50_original_cost_repair,
    )
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    architecture, case, guide_model = _toy_case_and_model()
    guide_inventory = collect_binary_inventory(guide_model)
    assert fix_engineering_capacity_anchor(guide_model, architecture)["passed"]
    assert apply_relaxation(
        guide_model,
        guide_inventory,
        RelaxationMode.R0,
    )["passed"]
    guide_path = tmp_path / "guide.csv.gz"
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
    candidate_path = tmp_path / "candidate.csv.gz"
    candidate = solve_block_relax_and_fix_candidate(
        candidate_model,
        candidate_inventory,
        case.chp_units,
        architecture=architecture,
        guide_path=guide_path,
        stage_output_dir=tmp_path / "stages",
        progress_output_path=tmp_path / "progress.jsonl",
        physical_snapshot_output_path=tmp_path / "physical.json",
        candidate_output_path=candidate_path,
        commit_hours=8,
        time_limit_seconds=30.0,
        threads=1,
        require_locked_guide_hash=False,
        require_formal_counts=False,
    )
    assert candidate["status"] == "candidate_incumbent_captured_and_exactly_lifted"
    assert candidate["stage_count"] == 3
    assert candidate["completed_stage_count"] == 3
    assert candidate["physical_snapshot_complete"] is True
    assert candidate["candidate_audit_passed"] is True
    assert len(list((tmp_path / "stages").glob("stage_*.json"))) == 3
    progress = [
        json.loads(line)
        for line in (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sum(item["event"] == "stage_started" for item in progress) == 3
    assert sum(item["event"] == "stage_committed" for item in progress) == 3
    assert progress[-1]["event"] == "candidate_complete"

    repair_model = build_endogenous_capacity_model(case)
    repair_inventory = collect_binary_inventory(repair_model)
    repaired = solve_d50_original_cost_repair(
        repair_model,
        repair_inventory,
        architecture=architecture,
        candidate_path=candidate_path,
        solution_output_path=tmp_path / "solution.csv.gz",
        time_limit_seconds=30.0,
        threads=1,
        require_named_constraint_groups=True,
    )
    assert repaired["status"] == "audited_feasible_upper_bound_recovered"
    assert repaired["schema_id"].endswith("e0d50_original_cost_repair.v1")
    upper = repaired["solution_audit"]["audited_feasible_upper_bound_cny"]
    assert upper is not None and math.isfinite(float(upper))
