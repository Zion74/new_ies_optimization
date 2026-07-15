from __future__ import annotations

import json
from copy import deepcopy

import pytest


def _tes_toy_model():
    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
    )

    model = ConcreteModel()
    model.x = Var(domain=NonNegativeReals, bounds=(0.0, 10.0))
    model.online = Var(domain=Binary)
    model.service = Constraint(expr=model.x + model.online >= 2.0)
    model.cost = Objective(expr=model.x + 0.2 * model.online, sense=minimize)
    return model


def _hybrid_toy_model():
    from pyomo.environ import (
        Binary,
        Block,
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        minimize,
    )

    model = ConcreteModel()
    model.bess = Block()
    model.bess.installed = Var(domain=Binary)
    model.online = Var(domain=Binary)
    model.x = Var(domain=NonNegativeReals, bounds=(0.0, 10.0))
    model.service = Constraint(
        expr=model.x + model.online >= 1.0 + model.bess.installed
    )
    model.cost = Objective(
        expr=model.x + 0.2 * model.online + 0.5 * model.bess.installed,
        sense=minimize,
    )
    return model


def test_input_hashes_accept_locked_price_basis_directory(tmp_path) -> None:
    from tes_bess_boundary.e0d42_full_year_structure_gate import _input_hashes

    paths = {}
    for name in ("service", "d40", "d41", "heat", "vre"):
        path = tmp_path / f"{name}.txt"
        path.write_text(name, encoding="utf-8")
        paths[name] = path
    price_basis = tmp_path / "price_basis"
    price_basis.mkdir()
    (price_basis / "snapshot.json").write_text("{}", encoding="utf-8")

    hashes = _input_hashes(
        service_path=paths["service"],
        d40_gate_a_manifest_path=paths["d40"],
        d41_gate_a_manifest_path=paths["d41"],
        heat_path=paths["heat"],
        vre_path=paths["vre"],
        price_basis_path=price_basis,
    )

    assert set(hashes) == {
        "service",
        "d40_gate_a_manifest",
        "d41_gate_a_manifest",
        "heat",
        "vre",
        "price_basis_tree",
    }
    assert len(hashes["price_basis_tree"]) == 64


@pytest.mark.solver
def test_tes_r0_and_r1_have_identical_native_and_presolved_lp_identity() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        audit_relaxed_model_lp,
    )

    r0 = audit_relaxed_model_lp(
        _tes_toy_model(),
        mode=RelaxationMode.R0,
        topology_value=None,
    )
    r1 = audit_relaxed_model_lp(
        _tes_toy_model(),
        mode=RelaxationMode.R1,
        topology_value=None,
    )

    assert r0["original_lp"]["lp_sha256"] == r1["original_lp"]["lp_sha256"]
    assert (
        r0["presolved_lp"]["presolved_lp_sha256"]
        == r1["presolved_lp"]["presolved_lp_sha256"]
    )
    assert r0["optimization_invoked"] is False


@pytest.mark.solver
def test_hybrid_r1_exact_branches_are_continuous_and_distinct() -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        HYBRID_TOPOLOGY_NAME,
        audit_relaxed_model_lp,
    )

    branch0 = audit_relaxed_model_lp(
        _hybrid_toy_model(),
        mode=RelaxationMode.R1,
        topology_value=0,
    )
    branch1 = audit_relaxed_model_lp(
        _hybrid_toy_model(),
        mode=RelaxationMode.R1,
        topology_value=1,
    )

    assert branch0["topology_branch"] == {
        "variable_name": HYBRID_TOPOLOGY_NAME,
        "fixed_value": 0,
        "exact_fix_applied_before_domain_relaxation": True,
    }
    assert branch1["topology_branch"]["fixed_value"] == 1
    assert branch0["original_lp"]["noncontinuous_column_count"] == 0
    assert branch1["presolved_lp"]["noncontinuous_column_count"] == 0
    assert (
        branch0["original_lp"]["lp_sha256"]
        != branch1["original_lp"]["lp_sha256"]
    )


def test_structure_gate_rejects_unregistered_topology_or_invalid_branch() -> None:
    from pyomo.environ import Binary, Block, Var

    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        audit_relaxed_model_lp,
    )

    with pytest.raises(ValueError, match="requires topology_value"):
        audit_relaxed_model_lp(
            _hybrid_toy_model(),
            mode=RelaxationMode.R1,
            topology_value=None,
        )

    unregistered = _tes_toy_model()
    unregistered.tes = Block()
    unregistered.tes.installed = Var(domain=Binary)
    with pytest.raises(ValueError, match="locked Hybrid topology binary"):
        audit_relaxed_model_lp(
            unregistered,
            mode=RelaxationMode.R1,
            topology_value=0,
        )


def _case_payload(case_key: str, lp_audit: dict[str, object]) -> dict[str, object]:
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        CASE_SCHEMA_ID,
        STRUCTURE_CASES,
    )

    case = next(item for item in STRUCTURE_CASES if item.key == case_key)

    return {
        "schema_id": CASE_SCHEMA_ID,
        "case_key": case_key,
        "architecture": case.architecture.value,
        "relaxation_mode": case.mode.value,
        "topology_value": case.topology_value,
        "input_sha256": {"locked": "same"},
        "lp_identity_audit": lp_audit,
        "d41_structure_lock": {
            "model_size_matches": True,
            "binary_inventory_matches": True,
        },
        "optimization_invoked": False,
        "presolve_invoked": True,
        "audit": {"passed": True},
    }


@pytest.mark.solver
def test_structure_manifest_enforces_tes_identity_and_hybrid_coverage(
    tmp_path,
) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        CASE_FILE_TEMPLATE,
        STRUCTURE_CASES,
        audit_relaxed_model_lp,
        compile_structure_manifest,
    )

    audits = {
        "tes_r0": audit_relaxed_model_lp(
            _tes_toy_model(), mode=RelaxationMode.R0, topology_value=None
        ),
        "tes_r1": audit_relaxed_model_lp(
            _tes_toy_model(), mode=RelaxationMode.R1, topology_value=None
        ),
        "hybrid_r0": audit_relaxed_model_lp(
            _hybrid_toy_model(), mode=RelaxationMode.R0, topology_value=None
        ),
        "hybrid_r1_bess0": audit_relaxed_model_lp(
            _hybrid_toy_model(), mode=RelaxationMode.R1, topology_value=0
        ),
        "hybrid_r1_bess1": audit_relaxed_model_lp(
            _hybrid_toy_model(), mode=RelaxationMode.R1, topology_value=1
        ),
    }
    for case in STRUCTURE_CASES:
        path = tmp_path / CASE_FILE_TEMPLATE.format(case_key=case.key)
        path.write_text(
            json.dumps(_case_payload(case.key, audits[case.key])),
            encoding="utf-8",
        )

    manifest = compile_structure_manifest(tmp_path)

    assert manifest["audit"]["passed"] is True
    assert manifest["formal_gate_b_permitted"] is True
    assert manifest["tes_r0_r1_identity"]["presolved_lp_fingerprint_equal"]
    assert manifest["hybrid_r1_branch_coverage"]["fixed_values"] == [0, 1]
    assert manifest["technical_ranking_permitted"] is False


@pytest.mark.solver
def test_structure_manifest_rejects_changed_tes_fingerprint(tmp_path) -> None:
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
    )
    from tes_bess_boundary.e0d42_full_year_structure_gate import (
        CASE_FILE_TEMPLATE,
        STRUCTURE_CASES,
        audit_relaxed_model_lp,
        compile_structure_manifest,
    )

    common = audit_relaxed_model_lp(
        _tes_toy_model(), mode=RelaxationMode.R0, topology_value=None
    )
    branch0 = audit_relaxed_model_lp(
        _hybrid_toy_model(), mode=RelaxationMode.R1, topology_value=0
    )
    branch1 = audit_relaxed_model_lp(
        _hybrid_toy_model(), mode=RelaxationMode.R1, topology_value=1
    )
    payloads = {
        "tes_r0": _case_payload("tes_r0", deepcopy(common)),
        "tes_r1": _case_payload("tes_r1", deepcopy(common)),
        "hybrid_r0": _case_payload("hybrid_r0", deepcopy(common)),
        "hybrid_r1_bess0": _case_payload("hybrid_r1_bess0", branch0),
        "hybrid_r1_bess1": _case_payload("hybrid_r1_bess1", branch1),
    }
    payloads["tes_r1"]["lp_identity_audit"]["original_lp"][
        "lp_sha256"
    ] = "0" * 64
    for case in STRUCTURE_CASES:
        path = tmp_path / CASE_FILE_TEMPLATE.format(case_key=case.key)
        path.write_text(json.dumps(payloads[case.key]), encoding="utf-8")

    with pytest.raises(ValueError, match="TES R0/R1 LP fingerprints differ"):
        compile_structure_manifest(tmp_path)
