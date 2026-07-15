from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locked_gate_a(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b

    path = tmp_path / "gate_a_manifest.json"
    payload = {
        "schema_id": gate_b.D41_GATE_A_SCHEMA_ID,
        "status": "gate_a_passed",
        "solver_invoked": False,
        "audit": {"passed": True},
        "representative_period_input_used": False,
        "service_contract_sha256": "service",
        "d40_gate_a_manifest_sha256": "d40",
        "relaxation_containment": {
            "candidate_blocks_provide_formal_bound": False,
            "full_year_repair_required_for_upper_bound": True,
            "r0_contains_original_milp": True,
            "r1_contains_original_milp": True,
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(gate_b, "SERVICE_SHA256", "service")
    monkeypatch.setattr(gate_b, "D40_GATE_A_MANIFEST_SHA256", "d40")
    monkeypatch.setattr(gate_b, "D41_GATE_A_MANIFEST_SHA256", _sha(path))
    return path


def _toy_model():
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
    model.bess.charge_mode = Var(domain=Binary)
    model.y = Var(domain=NonNegativeReals)
    model.requirement = Constraint(
        expr=model.y
        >= 10.0 - 4.0 * model.bess.installed - 2.0 * model.bess.charge_mode
    )
    model.planning_cost = Objective(
        expr=model.y
        + 3.0 * model.bess.installed
        + 0.5 * model.bess.charge_mode,
        sense=minimize,
    )
    return model


def test_locked_gate_a_rejects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b

    path = _locked_gate_a(tmp_path, monkeypatch)
    assert gate_b._load_locked_d41_gate_a(path)["status"] == "gate_a_passed"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        gate_b._load_locked_d41_gate_a(path)


def test_dual_bound_audit_requires_finite_minimization_direction() -> None:
    from tes_bess_boundary.e0d41_gate_b_lower_bound import audit_dual_bound

    valid = audit_dual_bound(
        lower_bound=99.0,
        upper_bound=100.0,
        objective_audit_passed=True,
        domain_audit_passed=True,
        service_audit_passed=True,
        linearity_audit_passed=True,
        objective_value=100.0,
    )
    reversed_bound = audit_dual_bound(
        lower_bound=101.0,
        upper_bound=100.0,
        objective_audit_passed=True,
        domain_audit_passed=True,
        service_audit_passed=True,
        linearity_audit_passed=True,
        objective_value=100.0,
    )
    nonfinite = audit_dual_bound(
        lower_bound=None,
        upper_bound=None,
        objective_audit_passed=True,
        domain_audit_passed=True,
        service_audit_passed=True,
        linearity_audit_passed=True,
    )

    assert valid["passed"] is True
    assert reversed_bound["passed"] is False
    assert nonfinite["passed"] is False


def test_monitor_stop_reason_enforces_hard_wall_before_memory() -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b

    assert (
        gate_b.monitor_stop_reason(
            elapsed_seconds=720.0,
            hard_wall_seconds=720.0,
            child_tree_rss_gib=40.0,
            aggregate_rss_gib=80.0,
            available_memory_gib=10.0,
        )
        == "hard_wall_clock_reached"
    )
    assert (
        gate_b.monitor_stop_reason(
            elapsed_seconds=10.0,
            hard_wall_seconds=720.0,
            child_tree_rss_gib=gate_b.PROCESS_RSS_LIMIT_GIB,
            aggregate_rss_gib=1.0,
            available_memory_gib=90.0,
        )
        == "process_tree_rss_limit_reached"
    )


def test_r0_and_r1_solver_payloads_are_finite_and_r1_writes_guide(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        RelaxationMode,
        apply_relaxation,
        collect_binary_inventory,
    )

    monkeypatch.setattr(gate_b, "FORMAL_THREADS", 1)
    r0_model = _toy_model()
    r0_inventory = collect_binary_inventory(r0_model)
    assert apply_relaxation(r0_model, r0_inventory, RelaxationMode.R0)["passed"]
    r0_objective, r0_objective_audit = gate_b._objective_metadata(r0_model)
    assert r0_objective_audit["passed"] is True
    r0 = gate_b._solve_relaxed_model(
        model=r0_model,
        objective=r0_objective,
        mode=RelaxationMode.R0,
        inventory=r0_inventory,
        guide_path=tmp_path / "r0.csv.gz",
        soft_time_limit_seconds=10.0,
    )

    r1_model = _toy_model()
    r1_inventory = collect_binary_inventory(r1_model)
    assert apply_relaxation(r1_model, r1_inventory, RelaxationMode.R1)["passed"]
    r1_objective, _ = gate_b._objective_metadata(r1_model)
    guide_path = tmp_path / "r1.csv.gz"
    r1 = gate_b._solve_relaxed_model(
        model=r1_model,
        objective=r1_objective,
        mode=RelaxationMode.R1,
        inventory=r1_inventory,
        guide_path=guide_path,
        soft_time_limit_seconds=10.0,
    )

    assert r0["termination_condition"] == "optimal"
    assert r0["objective_lower_bound_cny"] is not None
    assert r0["candidate_guide"] is None
    assert r1["termination_condition"] == "optimal"
    assert r1["objective_lower_bound_cny"] is not None
    assert r1["candidate_guide"]["candidate_only"] is True
    assert r1["candidate_guide"]["file_sha256"] == _sha(guide_path)


def test_candidate_guide_is_deterministic_complete_and_classified(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.e0d41_gate_b_lower_bound import write_candidate_guide
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import (
        collect_binary_inventory,
    )

    model = _toy_model()
    model.bess.installed.set_value(1.0)
    model.bess.charge_mode.set_value(0.25)
    model.y.set_value(5.0)
    inventory = collect_binary_inventory(model)
    first = tmp_path / "first.csv.gz"
    second = tmp_path / "second.csv.gz"

    first_audit = write_candidate_guide(model, inventory, first)
    second_audit = write_candidate_guide(model, inventory, second)
    with gzip.open(first, "rt", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert first_audit["variable_row_count"] == 3
    assert first_audit["formal_bound_eligible"] is False
    assert _sha(first) == _sha(second)
    classes = {row["variable_name"]: row["variable_class"] for row in rows}
    assert classes["bess.installed"] == "topology_binary"
    assert classes["bess.charge_mode"] == "operational_binary"
    assert classes["y"] == "continuous"
    assert second_audit["all_values_finite"] is True


def _write_stage(
    result_dir: Path,
    gate_b: object,
    architecture: object,
    mode: object,
    lower_bound: float,
) -> None:
    paths = gate_b._paths(result_dir, architecture, mode)
    result = {
        "schema_id": gate_b.RESULT_SCHEMA_ID,
        "architecture": architecture.value,
        "relaxation_mode": mode.value,
        "d41_gate_a_manifest_sha256": gate_b.D41_GATE_A_MANIFEST_SHA256,
        "formal_lower_bound_eligible": True,
        "dual_bound_audit": {"passed": True},
        "objective_lower_bound_cny": lower_bound,
    }
    gate_b._write_json(paths["result"], result)
    execution = {
        "schema_id": gate_b.EXECUTION_SCHEMA_ID,
        "architecture": architecture.value,
        "relaxation_mode": mode.value,
        "status": "complete",
        "resource_gate_passed": True,
        "stop_reason": None,
        "return_code": 0,
        "hard_wall_enforced_by_parent": True,
        "result_sha256": _sha(paths["result"]),
        "candidate_guide_sha256": None,
    }
    gate_b._write_json(paths["execution"], execution)


def test_architecture_compiler_selects_stronger_bound_without_ranking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import RelaxationMode
    from tes_bess_boundary.model import Architecture

    gate_a = _locked_gate_a(tmp_path, monkeypatch)
    _write_stage(tmp_path, gate_b, Architecture.BESS, RelaxationMode.R0, 100.0)
    _write_stage(tmp_path, gate_b, Architecture.BESS, RelaxationMode.R1, 120.0)

    manifest = gate_b.compile_architecture_manifest(
        architecture=Architecture.BESS,
        d41_gate_a_manifest_path=gate_a,
        result_dir=tmp_path,
    )

    assert manifest["gate_b_passed"] is True
    assert manifest["strict_lower_bound_cny"] == 120.0
    assert manifest["selected_relaxation"] == "r1"
    assert manifest["technical_ranking_permitted"] is False


def test_architecture_compiler_rejects_missing_or_unmonitored_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import RelaxationMode
    from tes_bess_boundary.model import Architecture

    gate_a = _locked_gate_a(tmp_path, monkeypatch)
    _write_stage(tmp_path, gate_b, Architecture.TES, RelaxationMode.R0, 100.0)
    manifest = gate_b.compile_architecture_manifest(
        architecture=Architecture.TES,
        d41_gate_a_manifest_path=gate_a,
        result_dir=tmp_path,
    )
    assert manifest["gate_b_passed"] is False
    assert manifest["strict_lower_bound_cny"] is None

    _write_stage(tmp_path, gate_b, Architecture.TES, RelaxationMode.R1, 110.0)
    execution_path = gate_b._paths(
        tmp_path, Architecture.TES, RelaxationMode.R1
    )["execution"]
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["hard_wall_enforced_by_parent"] = False
    gate_b._write_json(execution_path, execution)
    manifest = gate_b.compile_architecture_manifest(
        architecture=Architecture.TES,
        d41_gate_a_manifest_path=gate_a,
        result_dir=tmp_path,
    )
    assert manifest["gate_b_passed"] is False


def test_frozen_time_limits_match_contract() -> None:
    import tes_bess_boundary.e0d41_gate_b_lower_bound as gate_b
    from tes_bess_boundary.e0d41_strict_full_year_decomposition import RelaxationMode

    assert gate_b._time_limits(RelaxationMode.R0) == (600.0, 720.0)
    assert gate_b._time_limits(RelaxationMode.R1) == (1_200.0, 1_320.0)
    assert gate_b.ARCHITECTURE_HARD_WALL_SECONDS == 7_200.0
    assert gate_b.HEARTBEAT_INTERVAL_SECONDS == 5.0
