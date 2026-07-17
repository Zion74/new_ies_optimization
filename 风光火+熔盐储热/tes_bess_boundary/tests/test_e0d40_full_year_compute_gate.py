from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _synthetic_service_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import tes_bess_boundary.e0d40_full_year_compute_gate as d40

    heat = tmp_path / "heat.csv"
    vre = tmp_path / "vre.csv"
    prices = tmp_path / "prices"
    heat.write_text("heat\n", encoding="utf-8")
    vre.write_text("vre\n", encoding="utf-8")
    prices.mkdir()
    (prices / "basis.json").write_text('{"basis": 2024}\n', encoding="utf-8")

    heat_sha = _sha(heat)
    vre_sha = _sha(vre)
    price_sha = _tree_sha(prices)
    monkeypatch.setattr(d40, "FORMAL_HEAT_SHA256", heat_sha)
    monkeypatch.setattr(d40, "LEGACY_VRE_SHA256", vre_sha)
    monkeypatch.setattr(d40, "PRICE_BASIS_TREE_SHA256", price_sha)

    source_payload = {
        "schema_id": "tes_bess_boundary.e0d38_service_contract.v1",
        "status": "complete",
        "formal_project_tac_ready": False,
        "state": {
            "state_id": "baseline",
            "heat_scale": 1.0,
            "pcc_export_capacity_mw": 700.0,
        },
        "actual_renewable_available_mwh": d40.ACTUAL_RENEWABLE_AVAILABLE_MWH,
        "epsilon_curtailment_ceiling_mwh": (
            d40.EPSILON_CURTAILMENT_CEILING_MWH
        ),
        "pcc_export_target_mwh": d40.PCC_EXPORT_TARGET_MWH,
        "provenance": {
            "actual_heat_file_sha256": heat_sha,
            "actual_vre_file_sha256": vre_sha,
            "price_basis_tree_sha256": price_sha,
        },
    }
    source = tmp_path / "source_service.json"
    source.write_text(
        json.dumps(source_payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    d39_payload = {
        "status": "complete",
        "actual_minimum_curtailment_mwh": d40.ACTUAL_MINIMUM_CURTAILMENT_MWH,
        "actual_renewable_available_mwh": d40.ACTUAL_RENEWABLE_AVAILABLE_MWH,
        "epsilon_10_percent_ceiling_mwh": (
            d40.EPSILON_CURTAILMENT_CEILING_MWH
        ),
        "minimum_curtailment_prevalidation_gate": {"passed": False},
        "provenance": {
            "heat_file_sha256": heat_sha,
            "vre_file_sha256": vre_sha,
        },
    }
    d39 = tmp_path / "d39_gate_b.json"
    d39.write_text(
        json.dumps(d39_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(d40, "D38_BASELINE_SERVICE_SHA256", _sha(source))
    monkeypatch.setattr(d40, "D39_GATE_B_RESULT_SHA256", _sha(d39))
    return d40, source, d39, heat, vre, prices


def test_d40_service_excludes_representative_period_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d40, source, d39, heat, vre, prices = _synthetic_service_inputs(
        tmp_path, monkeypatch
    )

    payload = d40.build_full_year_service_payload(
        source, d39, heat, vre, prices
    )
    service = tmp_path / d40.SERVICE_NAME
    service.write_bytes(d40._canonical_json_bytes(payload))

    assert payload["representative_period_input_used"] is False
    assert set(payload["provenance"]) == {
        "heat_file_sha256",
        "vre_file_sha256",
        "price_basis_tree_sha256",
        "code_sha256",
    }
    assert "d36_periods" not in json.dumps(payload, sort_keys=True)
    assert d40.load_full_year_service(service) == payload


def test_d40_service_rejects_changed_source_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d40, source, d39, heat, vre, prices = _synthetic_service_inputs(
        tmp_path, monkeypatch
    )
    source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="source D38 baseline service hash"):
        d40.build_full_year_service_payload(source, d39, heat, vre, prices)


def test_d40_service_specs_use_locked_absolute_annual_values() -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        EPSILON_CURTAILMENT_CEILING_MWH,
        PCC_EXPORT_TARGET_MWH,
        _service_specs,
    )

    curtailment, pcc = _service_specs(
        {
            "epsilon_curtailment_ceiling_mwh": (
                EPSILON_CURTAILMENT_CEILING_MWH
            ),
            "pcc_export_target_mwh": PCC_EXPORT_TARGET_MWH,
        }
    )

    assert curtailment.service_id.startswith("e0d40_")
    assert curtailment.maximum_curtailment_mwh == (
        EPSILON_CURTAILMENT_CEILING_MWH
    )
    assert pcc.service_id.startswith("e0d40_")
    assert pcc.target_export_mwh == PCC_EXPORT_TARGET_MWH


def _toy_bess_model():
    from pyomo.environ import Binary, Block, ConcreteModel, Constraint, Var

    model = ConcreteModel()
    model.bess = Block()
    block = model.bess
    block.energy_capacity_mwh = Var(bounds=(0.0, 100.0))
    block.charge_power_capacity_mw = Var(bounds=(0.0, 50.0))
    block.discharge_power_capacity_mw = Var(bounds=(0.0, 50.0))
    block.pcs_power_capacity_mw = Var(bounds=(0.0, 50.0))
    block.installed = Var(domain=Binary)
    block.pcs_installed_upper = Constraint(
        expr=block.pcs_power_capacity_mw <= 50.0 * block.installed
    )
    block.energy_requires_installation = Constraint(
        expr=block.energy_capacity_mwh <= 100.0 * block.installed
    )
    block.charge_uses_common_pcs = Constraint(
        expr=block.charge_power_capacity_mw <= block.pcs_power_capacity_mw
    )
    block.discharge_uses_common_pcs = Constraint(
        expr=block.discharge_power_capacity_mw <= block.pcs_power_capacity_mw
    )
    return model


def test_capacity_bound_audit_requires_finite_bounds_and_installation_links() -> None:
    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        _capacity_bound_audit,
    )
    from tes_bess_boundary.model import Architecture

    model = _toy_bess_model()
    assert _capacity_bound_audit(model, Architecture.BESS)["passed"] is True

    model.bess.del_component("energy_requires_installation")
    failed = _capacity_bound_audit(model, Architecture.BESS)
    assert failed["passed"] is False
    assert (
        failed["installation_link_components"][
            "bess.energy_requires_installation"
        ]
        is False
    )


def test_capacity_bound_audit_accepts_continuous_zero_capacity_tes_policy() -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Var

    from tes_bess_boundary.e0d40_full_year_compute_gate import (
        _capacity_bound_audit,
    )
    from tes_bess_boundary.model import Architecture

    model = ConcreteModel()
    model.tes = Block()
    block = model.tes
    capacity_names = (
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
    for name in capacity_names:
        setattr(block, name, Var(bounds=(0.0, 100.0)))
    link_names = (
        "ht_state_capacity",
        "mt_state_capacity",
        "lt_state_capacity",
        "ht_full_inventory_capacity",
        "mt_full_inventory_capacity",
        "lt_full_inventory_capacity",
        "electric_charge_capacity_limit",
        "steam_to_ht_capacity_limit",
        "steam_to_mt_capacity_limit",
        "electric_output_capacity_limit",
        "heat_output_capacity_limit",
        "ht_service_mass_limit",
        "mt_service_mass_limit",
    )
    for index, name in enumerate(link_names):
        setattr(
            block,
            name,
            Constraint(expr=block.salt_mass_t <= 100.0 + index),
        )

    audit = _capacity_bound_audit(model, Architecture.TES)

    assert audit["tes_capacity_policy"] == "continuous_zero_capacity_allowed"
    assert audit["all_capacity_bounds_finite_nonnegative"] is True
    assert audit["all_installation_links_present"] is True
    assert audit["passed"] is True


def test_linearity_audit_detects_nonlinear_constraint() -> None:
    from pyomo.environ import ConcreteModel, Constraint, Objective, Var

    from tes_bess_boundary.e0d40_full_year_compute_gate import _linearity_audit

    model = ConcreteModel()
    model.x = Var(bounds=(0.0, 1.0))
    model.y = Var(bounds=(0.0, 1.0))
    model.linear = Constraint(expr=model.x + model.y <= 1.0)
    model.objective = Objective(expr=model.x)
    assert _linearity_audit(model)["nonlinear_component_count"] == 0

    model.nonlinear = Constraint(expr=model.x * model.y <= 1.0)
    audit = _linearity_audit(model)
    assert audit["nonlinear_component_count"] == 1
    assert audit["nonlinear_components"] == ["nonlinear"]


def test_failed_build_audit_is_written_before_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tes_bess_boundary.e0d40_full_year_compute_gate as d40

    failed = {
        "schema_id": d40.BUILD_SCHEMA_ID,
        "architecture": "no_storage",
        "audit": {"passed": False},
    }
    monkeypatch.setattr(d40, "build_architecture_manifest", lambda *_args: failed)
    monkeypatch.setattr(d40, "_available_memory_gib", lambda: 90.0)
    monkeypatch.setattr(d40, "_peak_rss_gib", lambda: 1.0)

    with pytest.raises(RuntimeError, match="build audit failed"):
        d40.write_architecture_audit(
            d40.Architecture.NO_STORAGE,
            tmp_path / "service.json",
            tmp_path / "heat.csv",
            tmp_path / "vre.csv",
            tmp_path / "prices",
            tmp_path,
        )

    assert json.loads(
        (tmp_path / "build_no_storage.json").read_text(encoding="utf-8")
    ) == failed
    execution = json.loads(
        (tmp_path / "build_no_storage_execution.json").read_text(encoding="utf-8")
    )
    assert execution["manifest_sha256"] == _sha(
        tmp_path / "build_no_storage.json"
    )


def test_gate_a_compiler_enforces_resource_thresholds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d40, source, d39, heat, vre, prices = _synthetic_service_inputs(
        tmp_path, monkeypatch
    )
    service_payload = d40.build_full_year_service_payload(
        source, d39, heat, vre, prices
    )
    service_path = tmp_path / d40.SERVICE_NAME
    service_path.write_bytes(d40._canonical_json_bytes(service_payload))
    service_sha = _sha(service_path)
    sizes = {
        "no_storage": (100, 10, 90),
        "bess": (150, 20, 140),
        "tes": (180, 30, 170),
        "hybrid": (230, 40, 220),
    }
    for architecture, (variables, binaries, constraints) in sizes.items():
        manifest = {
            "schema_id": d40.BUILD_SCHEMA_ID,
            "architecture": architecture,
            "service_contract_sha256": service_sha,
            "solver_invoked": False,
            "audit": {"passed": True},
            "linearity_audit": {
                "active_variable_count": variables,
                "active_binary_variable_count": binaries,
                "active_constraint_count": constraints,
                "nonlinear_component_count": 0,
                "nonlinear_components": [],
            },
        }
        manifest_path = tmp_path / f"build_{architecture}.json"
        manifest_path.write_bytes(d40._canonical_json_bytes(manifest))
        execution = {
            "schema_id": f"{d40.BUILD_SCHEMA_ID}.execution",
            "architecture": architecture,
            "peak_process_rss_gib": 5.0,
            "available_memory_before_gib": 90.0,
            "available_memory_after_gib": 85.0,
            "manifest_sha256": _sha(manifest_path),
        }
        (tmp_path / f"build_{architecture}_execution.json").write_bytes(
            d40._canonical_json_bytes(execution)
        )

    manifest, _execution = d40.compile_gate_a_manifest(service_path, tmp_path)
    assert manifest["audit"]["passed"] is True

    hybrid_execution = tmp_path / "build_hybrid_execution.json"
    payload = json.loads(hybrid_execution.read_text(encoding="utf-8"))
    payload["peak_process_rss_gib"] = 20.1
    hybrid_execution.write_bytes(d40._canonical_json_bytes(payload))
    manifest, _execution = d40.compile_gate_a_manifest(service_path, tmp_path)
    assert manifest["resource_gate_passed"] is False
    assert manifest["audit"]["passed"] is False
