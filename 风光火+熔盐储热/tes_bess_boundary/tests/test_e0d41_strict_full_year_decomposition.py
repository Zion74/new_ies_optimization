from __future__ import annotations

import json
from pathlib import Path

import pytest


def _toy_model():
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        RangeSet,
        Var,
        minimize,
    )

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.bess.charge_mode = Var(model.periods, domain=Binary)
    model.online = Var(model.periods, domain=Binary)
    model.startup = Var(model.periods, domain=Binary)
    model.dispatch = Var(model.periods, domain=NonNegativeReals)
    model.capacity = Var(bounds=(0.0, 10.0))
    model.install_link = Constraint(
        expr=model.capacity <= 10.0 * model.bess.installed
    )
    model.demand = Constraint(
        model.periods,
        rule=lambda block, period: block.dispatch[period] >= 2.0 + period,
    )
    model.online_limit = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.dispatch[period] <= 10.0 * block.online[period]
        ),
    )
    model.capacity_limit = Constraint(
        model.periods,
        rule=lambda block, period: block.dispatch[period] <= block.capacity,
    )
    model.mode_link = Constraint(
        model.periods,
        rule=lambda block, period: (
            block.bess.charge_mode[period] <= block.online[period]
        ),
    )
    model.start_link = Constraint(
        model.periods,
        rule=lambda block, period: block.startup[period] >= block.online[period],
    )
    model.cost = Objective(
        expr=(
            3.0 * model.bess.installed
            + model.capacity
            + sum(model.online[period] for period in model.periods)
            + 0.1 * sum(model.dispatch[period] for period in model.periods)
        ),
        sense=minimize,
    )
    return model


def _solve(model) -> float:
    from pyomo.environ import value

    from tes_bess_boundary.solver import create_highs_solver

    result = create_highs_solver(threads=1, random_seed=0).solve(model)
    assert str(result.solver.termination_condition).lower() == "optimal"
    return float(value(model.cost))


def test_binary_inventory_is_complete_disjoint_and_topology_aware() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )

    inventory = collect_binary_inventory(_toy_model())

    assert inventory.topology_names == ("bess.installed",)
    assert len(inventory.all_names) == 7
    assert len(inventory.operational_names) == 6
    assert inventory.to_audit()["classification_complete"] is True
    assert inventory.to_audit()["component_counts"] == {
        "bess.charge_mode": 2,
        "bess.installed": 1,
        "online": 2,
        "startup": 2,
    }


def test_r0_relaxes_every_binary_and_restore_is_exact() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
        restore_binary_domains,
    )

    model = _toy_model()
    inventory = collect_binary_inventory(model)
    audit = apply_relaxation(model, inventory, RelaxationMode.R0)

    assert audit["passed"] is True
    assert audit["relaxed_binary_variable_count"] == 7
    assert audit["remaining_binary_variable_count"] == 0
    restore_binary_domains(model, inventory)
    assert collect_binary_inventory(model) == inventory


def test_r1_keeps_only_time_invariant_topology_binary() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )

    model = _toy_model()
    inventory = collect_binary_inventory(model)
    audit = apply_relaxation(model, inventory, RelaxationMode.R1)

    assert audit["passed"] is True
    assert audit["relaxed_binary_variable_count"] == 6
    assert audit["remaining_binary_variable_count"] == 1
    assert model.bess.installed.is_binary()
    assert not model.online[0].is_binary()
    assert not model.bess.charge_mode[0].is_binary()


def test_relaxation_rejects_binary_added_after_inventory_lock() -> None:
    from pyomo.environ import Binary, Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )

    model = _toy_model()
    inventory = collect_binary_inventory(model)
    model.late_binary = Var(domain=Binary)

    with pytest.raises(ValueError, match="locked binary inventory"):
        apply_relaxation(model, inventory, RelaxationMode.R0)


def test_binary_snapshot_rejects_fractional_or_incomplete_candidate() -> None:
    from pyomo.environ import Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
        extract_binary_snapshot,
        fix_binary_snapshot,
    )

    model = _toy_model()
    inventory = collect_binary_inventory(model)
    for name in inventory.all_names:
        next(
            variable
            for variable in model.component_data_objects(
                Var, active=True, descend_into=True
            )
            if variable.name == name
        ).set_value(0.0)
    model.online[0].set_value(0.4)
    with pytest.raises(ValueError, match="fractional"):
        extract_binary_snapshot(model, inventory)

    complete = {name: 0 for name in inventory.all_names}
    complete.pop(inventory.all_names[0])
    with pytest.raises(ValueError, match="keys do not match"):
        fix_binary_snapshot(model, inventory, complete)


@pytest.mark.solver
def test_r0_and_r1_objectives_are_valid_lower_bounds() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )

    original = _toy_model()
    original_objective = _solve(original)

    r0 = _toy_model()
    apply_relaxation(r0, collect_binary_inventory(r0), RelaxationMode.R0)
    r0_objective = _solve(r0)

    r1 = _toy_model()
    apply_relaxation(r1, collect_binary_inventory(r1), RelaxationMode.R1)
    r1_objective = _solve(r1)

    assert r0_objective <= r1_objective + 1e-8
    assert r1_objective <= original_objective + 1e-8


@pytest.mark.solver
def test_complete_fixed_snapshot_produces_a_valid_repair_upper_bound() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
        extract_binary_snapshot,
        fix_binary_snapshot,
    )

    candidate = _toy_model()
    optimum = _solve(candidate)
    candidate_inventory = collect_binary_inventory(candidate)
    snapshot = extract_binary_snapshot(candidate, candidate_inventory)

    repair = _toy_model()
    repair_inventory = collect_binary_inventory(repair)
    audit = fix_binary_snapshot(repair, repair_inventory, snapshot)
    repaired_objective = _solve(repair)

    assert audit["passed"] is True
    assert audit["unfixed_binary_variable_count"] == 0
    assert repaired_objective >= optimum - 1e-8


def _architecture_payload(name: str) -> dict[str, object]:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        ARCHITECTURE_SCHEMA_ID,
    )
    from tes_bess_boundary.e0d40_gate_b_solver import (
        GATE_A_MANIFEST_SHA256,
        SERVICE_SHA256,
    )

    return {
        "schema_id": ARCHITECTURE_SCHEMA_ID,
        "architecture": name,
        "service_contract_sha256": SERVICE_SHA256,
        "d40_gate_a_manifest_sha256": GATE_A_MANIFEST_SHA256,
        "solver_invoked": False,
        "audit": {"passed": True},
        "r0_relaxation": {"passed": True},
        "r1_relaxation": {"passed": True},
        "synthetic_complete_fixing_audit": {"passed": True},
        "model_size": {"active_binary_variable_count": 1},
        "binary_inventory": {"classification_complete": True},
    }


def test_gate_a_compiler_enforces_all_three_locked_architectures(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        ARCHITECTURE_FILE_TEMPLATE,
        compile_gate_a_manifest,
    )
    from tes_bess_boundary.e0d40_gate_b_solver import FORMAL_ARCHITECTURES

    for architecture in FORMAL_ARCHITECTURES:
        payload = _architecture_payload(architecture.value)
        path = tmp_path / ARCHITECTURE_FILE_TEMPLATE.format(
            architecture=architecture.value
        )
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    manifest = compile_gate_a_manifest(tmp_path)

    assert manifest["status"] == "gate_a_passed"
    assert manifest["solver_invoked"] is False
    assert manifest["representative_period_input_used"] is False
    assert set(manifest["architecture_audit_sha256"]) == {
        "bess",
        "tes",
        "hybrid",
    }
    assert (
        manifest["relaxation_containment"][
            "candidate_blocks_provide_formal_bound"
        ]
        is False
    )


def test_gate_a_compiler_rejects_tampered_relaxation_audit(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        ARCHITECTURE_FILE_TEMPLATE,
        compile_gate_a_manifest,
    )
    from tes_bess_boundary.e0d40_gate_b_solver import FORMAL_ARCHITECTURES

    for architecture in FORMAL_ARCHITECTURES:
        payload = _architecture_payload(architecture.value)
        if architecture.value == "tes":
            payload["r1_relaxation"] = {"passed": False}
        path = tmp_path / ARCHITECTURE_FILE_TEMPLATE.format(
            architecture=architecture.value
        )
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="tes R1 audit failed"):
        compile_gate_a_manifest(tmp_path)
