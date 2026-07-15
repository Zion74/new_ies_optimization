from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gate_b_classification_uses_preregistered_thresholds() -> None:
    from tes_bess_boundary.e0d40_gate_b_solver import classify_case

    qualified = classify_case(
        mode="formal",
        termination="maxTimeLimit",
        lower_bound=999.0,
        upper_bound=1_000.0,
        solution_loaded=True,
        solution_audit_passed=True,
    )
    bounded = classify_case(
        mode="formal",
        termination="maxTimeLimit",
        lower_bound=997.0,
        upper_bound=1_000.0,
        solution_loaded=True,
        solution_audit_passed=True,
    )
    failed = classify_case(
        mode="formal",
        termination="maxTimeLimit",
        lower_bound=994.0,
        upper_bound=1_000.0,
        solution_loaded=True,
        solution_audit_passed=True,
    )

    assert qualified[0] == "qualified_full_year"
    assert qualified[2] == pytest.approx(0.001)
    assert bounded[0] == "bounded_but_not_qualified"
    assert failed[0] == "monolithic_not_viable"


def test_gate_b_classification_requires_audited_incumbent_or_proof() -> None:
    from tes_bess_boundary.e0d40_gate_b_solver import classify_case

    invalid = classify_case(
        mode="formal",
        termination="optimal",
        lower_bound=1_000.0,
        upper_bound=1_000.0,
        solution_loaded=True,
        solution_audit_passed=False,
    )
    infeasible = classify_case(
        mode="formal",
        termination="infeasible",
        lower_bound=None,
        upper_bound=None,
        solution_loaded=False,
        solution_audit_passed=False,
    )
    preflight = classify_case(
        mode="preflight",
        termination="optimal",
        lower_bound=1.0,
        upper_bound=1.0,
        solution_loaded=True,
        solution_audit_passed=True,
    )

    assert invalid[0] == "monolithic_not_viable"
    assert infeasible[0] == "qualified_full_year"
    assert infeasible[3] is True
    assert preflight[0] == "preflight_only"


def test_constraint_and_balance_audits_detect_violations() -> None:
    from pyomo.environ import ConcreteModel, Constraint, RangeSet, Var

    from tes_bess_boundary.e0d40_gate_b_solver import (
        _constraint_residual_audit,
        _max_equality_residual,
    )

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.x = Var(model.periods, initialize=1.0)
    model.balance = Constraint(model.periods, rule=lambda m, p: m.x[p] == 1.0)
    model.limit = Constraint(model.periods, rule=lambda m, p: m.x[p] <= 2.0)

    assert _max_equality_residual(model.balance) == pytest.approx(0.0)
    assert _constraint_residual_audit(model)["passed"] is True

    model.x[1].set_value(2.1)
    assert _max_equality_residual(model.balance) == pytest.approx(1.1)
    audit = _constraint_residual_audit(model)
    assert audit["passed"] is False
    assert audit["worst_constraint"] == "balance[1]"


def test_solution_payload_audits_service_objective_and_bess_capacity() -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Expression, RangeSet, Var

    from tes_bess_boundary.e0d40_gate_b_solver import _solution_payload
    from tes_bess_boundary.model import Architecture

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.zero = Var(model.periods, initialize=0.0)
    for variable in model.zero.values():
        variable.fix(0.0)
    model.planning_pcc_balance = Constraint(
        model.periods, rule=lambda m, p: m.zero[p] == 0.0
    )
    model.planning_heat_allocation = Constraint(
        model.periods, rule=lambda m, p: m.zero[p] == 0.0
    )
    model.planning_heat_balance = Constraint(
        model.periods, rule=lambda m, p: m.zero[p] == 0.0
    )
    model.planning_total_cost_cny = Expression(expr=1_000.0)
    model.annual_operating_cost_cny = Expression(expr=900.0)
    model.planning_storage_capacity_cost_cny = Expression(expr=100.0)
    model.planning_bess_cycle_cost_cny = Expression(expr=0.0)
    model.planning_bess_variable_om_cost_cny = Expression(expr=0.0)
    model.annual_curtailment_mwh = Expression(expr=100.0)
    model.annual_pcc_export_mwh = Expression(expr=4_035_354.738554194)
    model.annual_fuel_tce = Expression(expr=10.0)
    model.planning_bess_ac_discharge_throughput_mwh = Expression(expr=50.0)
    model.bess = Block()
    model.bess.energy_capacity_mwh = Var(initialize=200.0)
    model.bess.charge_power_capacity_mw = Var(initialize=20.0)
    model.bess.discharge_power_capacity_mw = Var(initialize=20.0)
    model.bess.pcs_power_capacity_mw = Var(initialize=20.0)
    model.bess.installed = Var(initialize=1.0)

    solution, audit = _solution_payload(
        model,
        SimpleNamespace(timeseries=SimpleNamespace(dt_hours=1.0)),
        Architecture.BESS,
        1_000.0,
    )

    assert audit["passed"] is True
    assert solution["capacity_snapshot"]["bess"]["energy_capacity_mwh"] == 200.0
    assert solution["capacity_snapshot"]["tes"] is None


def _write_locked_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    import tes_bess_boundary.e0d40_gate_b_solver as gate_b

    service = tmp_path / "service.json"
    service.write_text("{}\n", encoding="utf-8")
    service_hash = _sha(service)
    gate = tmp_path / "gate_a.json"
    gate.write_text(
        json.dumps(
            {
                "schema_id": gate_b.GATE_A_SCHEMA_ID,
                "status": "gate_a_passed",
                "solver_invoked": False,
                "service_contract_sha256": service_hash,
                "audit": {"passed": True},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate_b, "SERVICE_SHA256", service_hash)
    monkeypatch.setattr(gate_b, "GATE_A_MANIFEST_SHA256", _sha(gate))
    monkeypatch.setattr(
        gate_b,
        "load_full_year_service",
        lambda _path: {"representative_period_input_used": False},
    )
    return service, gate


def test_locked_gate_a_rejects_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d40_gate_b_solver as gate_b

    service, gate = _write_locked_fixture(tmp_path, monkeypatch)
    assert gate_b._load_locked_gate_a(gate, service)["status"] == "gate_a_passed"

    gate.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        gate_b._load_locked_gate_a(gate, service)


def test_gate_b_compiler_applies_weakest_case_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d40_gate_b_solver as gate_b

    service, gate = _write_locked_fixture(tmp_path, monkeypatch)
    classifications = {
        "bess": "qualified_full_year",
        "tes": "bounded_but_not_qualified",
        "hybrid": "qualified_full_year",
    }
    expected_solver = {
        "name": "appsi_highs",
        "threads": gate_b.FORMAL_THREADS,
        "random_seed": gate_b.FORMAL_RANDOM_SEED,
        "time_limit_seconds": gate_b.FORMAL_TIME_LIMIT_SECONDS,
        "target_relative_mip_gap": gate_b.FORMAL_TARGET_RELATIVE_GAP,
        "primal_feasibility_tolerance": gate_b.SOLVER_FEASIBILITY_TOLERANCE,
        "dual_feasibility_tolerance": gate_b.SOLVER_FEASIBILITY_TOLERANCE,
        "mip_feasibility_tolerance": gate_b.SOLVER_FEASIBILITY_TOLERANCE,
        "warm_start_used": False,
    }
    for architecture in gate_b.FORMAL_ARCHITECTURES:
        name = architecture.value
        result_path, execution_path, _ = gate_b._case_paths(
            tmp_path, architecture, "formal"
        )
        gate_b._write_json(
            result_path,
            {
                "schema_id": gate_b.CASE_SCHEMA_ID,
                "mode": "formal",
                "formal_gate_b_eligible": True,
                "architecture": name,
                "service_contract_sha256": gate_b.SERVICE_SHA256,
                "gate_a_manifest_sha256": gate_b.GATE_A_MANIFEST_SHA256,
                "solver": expected_solver,
            },
        )
        gate_b._write_json(
            execution_path,
            {
                "schema_id": gate_b.EXECUTION_SCHEMA_ID,
                "mode": "formal",
                "architecture": name,
                "result_sha256": _sha(result_path),
                "effective_classification": classifications[name],
            },
        )

    manifest, execution = gate_b.compile_gate_b_manifest(service, gate, tmp_path)

    assert manifest["classification"] == "bounded_but_not_qualified"
    assert manifest["status"] == "gate_b_bounded_not_qualified"
    assert manifest["gate_b_passed"] is False
    assert execution["schema_id"].endswith(".execution")


def test_preflight_is_bess_only() -> None:
    from tes_bess_boundary.e0d40_gate_b_solver import run_monitored_case
    from tes_bess_boundary.model import Architecture

    with pytest.raises(ValueError, match="only the BESS preflight"):
        run_monitored_case(
            architecture=Architecture.TES,
            mode="preflight",
            service_path=Path("service.json"),
            gate_a_manifest_path=Path("gate_a.json"),
            heat_path=Path("heat.csv"),
            vre_path=Path("vre.csv"),
            price_basis_path=Path("prices"),
            output_dir=Path("results"),
        )
