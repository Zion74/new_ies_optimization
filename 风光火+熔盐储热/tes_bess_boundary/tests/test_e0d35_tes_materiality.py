from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _result(**overrides):
    values = {
        "weighted_curtailment_mwh": 578_514.502570776,
        "weighted_pcc_export_mwh": 4_656_918.485025815,
        "tes_salt_mass_t": 0.0,
        "tes_installation_binary": None,
        "tes_electric_charge_input_capacity_mw": 0.0,
        "tes_steam_to_ht_input_capacity_mw": 0.0,
        "tes_steam_to_mt_input_capacity_mw": 0.0,
        "tes_electric_output_capacity_mw": 0.0,
        "tes_heat_output_capacity_mw": 0.0,
        "tes_electric_charge_installation_binary": None,
        "tes_steam_to_ht_installation_binary": None,
        "tes_steam_to_mt_installation_binary": None,
        "tes_electric_output_installation_binary": None,
        "tes_heat_output_installation_binary": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_d35_grid_and_reference_thresholds_are_locked() -> None:
    from tes_bess_boundary.e0d35_tes_materiality import (
        MATERIALITY_GRID,
        build_e0d35_materiality_policy,
        reference_materiality_payload,
    )

    assert MATERIALITY_GRID == (0.0, 0.01, 0.05, 0.10)
    assert build_e0d35_materiality_policy(0.0) is None
    reference = reference_materiality_payload()
    policy = build_e0d35_materiality_policy(0.01)
    assert policy is not None
    assert reference["sensible_heat_mwh"] == pytest.approx(1_200.0)
    assert reference["common_port_scale_mw"] == pytest.approx(150.0)
    assert reference["salt_mass_t"] == pytest.approx(13_913.71563843664)
    assert policy.minimum_salt_mass_t == pytest.approx(139.1371563843664)
    assert policy.minimum_port_capacity_mw == pytest.approx(1.5)


def test_d35_rejects_post_registration_grid_drift() -> None:
    from tes_bess_boundary.e0d35_tes_materiality import (
        build_e0d35_materiality_policy,
    )

    with pytest.raises(ValueError, match="must be one of"):
        build_e0d35_materiality_policy(0.02)


def test_d35_continuous_baseline_audit_has_no_materiality_binaries() -> None:
    from tes_bess_boundary.e0d35_tes_materiality import (
        SERVICES,
        audit_materiality_result,
    )

    audit = audit_materiality_result(
        _result(),
        fraction=0.0,
        service=SERVICES["natural"],
    )

    assert audit["passed"] is True
    assert audit["tes_installation_binary"] is None
    assert audit["minimum_salt_mass_t"] == pytest.approx(0.0)


def test_d35_positive_materiality_audits_every_active_port() -> None:
    from tes_bess_boundary.e0d35_tes_materiality import (
        SERVICES,
        audit_materiality_result,
    )

    audit = audit_materiality_result(
        _result(
            tes_salt_mass_t=140.0,
            tes_installation_binary=1.0,
            tes_electric_charge_input_capacity_mw=1.5,
            tes_steam_to_ht_input_capacity_mw=0.0,
            tes_steam_to_mt_input_capacity_mw=1.5,
            tes_electric_output_capacity_mw=0.0,
            tes_heat_output_capacity_mw=1.5,
            tes_electric_charge_installation_binary=1.0,
            tes_steam_to_ht_installation_binary=0.0,
            tes_steam_to_mt_installation_binary=1.0,
            tes_electric_output_installation_binary=0.0,
            tes_heat_output_installation_binary=1.0,
        ),
        fraction=0.01,
        service=SERVICES["natural"],
    )

    assert audit["passed"] is True
    assert audit["tes_installation_binary"] == 1
    assert audit["ports"]["heat_output"]["installation_binary"] == 1
    assert audit["ports"]["electric_output"]["installation_binary"] == 0


def test_d35_audit_rejects_a_micro_active_port() -> None:
    from tes_bess_boundary.e0d35_tes_materiality import (
        SERVICES,
        audit_materiality_result,
    )

    with pytest.raises(ValueError, match="below its materiality threshold"):
        audit_materiality_result(
            _result(
                tes_salt_mass_t=140.0,
                tes_installation_binary=1.0,
                tes_electric_charge_input_capacity_mw=1.5,
                tes_steam_to_ht_input_capacity_mw=0.0,
                tes_steam_to_mt_input_capacity_mw=0.0,
                tes_electric_output_capacity_mw=0.5,
                tes_heat_output_capacity_mw=0.0,
                tes_electric_charge_installation_binary=1.0,
                tes_steam_to_ht_installation_binary=0.0,
                tes_steam_to_mt_installation_binary=0.0,
                tes_electric_output_installation_binary=1.0,
                tes_heat_output_installation_binary=0.0,
            ),
            fraction=0.01,
            service=SERVICES["natural"],
        )


def _probe_payload(service_name: str, architecture: str, fraction: float) -> dict:
    from tes_bess_boundary.e0d35_tes_materiality import (
        MATERIALITY_GRID,
        SCHEMA_ID,
        SERVICES,
        reference_materiality_payload,
    )

    enabled = fraction > 0.0
    binary = 0.0 if enabled else None
    port_audit = {
        name: {
            "capacity_mw": 0.0,
            "installation_binary": 0 if enabled else None,
            "minimum_if_active_mw": 150.0 * fraction,
            "passed": True,
        }
        for name in (
            "electric_charge_input",
            "steam_to_ht_input",
            "steam_to_mt_input",
            "electric_output",
            "heat_output",
        )
    }
    service = SERVICES[service_name]
    return {
        "schema_id": SCHEMA_ID,
        "generated_at": "2026-07-15T00:00:00+08:00",
        "service_name": service_name,
        "materiality_fraction": fraction,
        "materiality_grid": list(MATERIALITY_GRID),
        "materiality_enabled": enabled,
        "reference": reference_materiality_payload(),
        "solver": {"name": "appsi_highs", "mip_rel_gap": 0.001},
        "materiality_audit": {
            "passed": True,
            "ports": port_audit,
            "curtailment_margin_mwh": 0.0,
            "pcc_export_residual_mwh": 0.0,
        },
        "result": {
            "architecture": architecture,
            "termination_condition": "optimal",
            "objective_lower_bound_cny": 100.0,
            "objective_upper_bound_cny": 100.0,
            "relative_mip_gap": 0.0,
            "annual_total_cost_cny": 100.0,
            "annual_operating_cost_cny": 100.0,
            "annual_storage_capacity_cost_cny": 0.0,
            "annual_bess_cycle_cost_cny": 0.0,
            "annual_bess_variable_om_cost_cny": 0.0,
            "weighted_fuel_tce": 1.0,
            "weighted_curtailment_mwh": service.curtailment_ceiling_mwh,
            "weighted_pcc_export_mwh": service.pcc_export_target_mwh,
            "tes_salt_mass_t": 0.0,
            "tes_ht_service_salt_mass_t": 0.0,
            "tes_mt_service_salt_mass_t": 0.0,
            "tes_electric_charge_input_capacity_mw": 0.0,
            "tes_steam_to_ht_input_capacity_mw": 0.0,
            "tes_steam_to_mt_input_capacity_mw": 0.0,
            "tes_electric_output_capacity_mw": 0.0,
            "tes_heat_output_capacity_mw": 0.0,
            "tes_installation_binary": binary,
            "tes_electric_charge_installation_binary": binary,
            "tes_steam_to_ht_installation_binary": binary,
            "tes_steam_to_mt_installation_binary": binary,
            "tes_electric_output_installation_binary": binary,
            "tes_heat_output_installation_binary": binary,
            "bess_common_pcs_power_capacity_mw": (
                0.0 if architecture == "hybrid" else None
            ),
            "bess_energy_capacity_mwh": 0.0 if architecture == "hybrid" else None,
            "tes_auxiliary_mwh": 0.0,
            "runtime_seconds": 1.0,
        },
    }


def _write_probe_grid(root) -> None:
    from tes_bess_boundary.e0d35_materiality_bundle import (
        ARCHITECTURES,
        REFINED_ZERO_GAP_IDENTITIES,
    )
    from tes_bess_boundary.e0d35_tes_materiality import MATERIALITY_GRID, SERVICES

    refined = root / "refined"
    refined.mkdir(parents=True)
    for service in SERVICES:
        for architecture in ARCHITECTURES:
            for fraction in MATERIALITY_GRID:
                label = "0" if fraction == 0.0 else f"{fraction:.2f}".replace(".", "p")
                payload = _probe_payload(service, architecture, fraction)
                (root / f"{service}_{architecture}_f{label}.json").write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )
                identity = (service, architecture, fraction)
                if identity in REFINED_ZERO_GAP_IDENTITIES:
                    (refined / f"{service}_{architecture}_f{label}_g000.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )


def test_d35_bundle_selects_refined_witnesses_and_is_deterministic(tmp_path) -> None:
    from tes_bess_boundary.e0d35_materiality_bundle import (
        CSV_NAME,
        EXECUTION_NAME,
        MANIFEST_NAME,
        build_bundle,
    )

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _write_probe_grid(inputs)
    output_a = tmp_path / "output_a"
    output_b = tmp_path / "output_b"

    manifest_a = build_bundle(inputs, output_a)
    manifest_b = build_bundle(inputs, output_b)

    assert manifest_a == manifest_b
    assert manifest_a["row_count"] == 16
    assert (output_a / CSV_NAME).read_bytes() == (output_b / CSV_NAME).read_bytes()
    assert (output_a / MANIFEST_NAME).read_bytes() == (
        output_b / MANIFEST_NAME
    ).read_bytes()
    execution = json.loads((output_a / EXECUTION_NAME).read_text(encoding="utf-8"))
    selected = {source["source_file"] for source in execution["sources"]}
    assert "refined/natural_tes_f0p05_g000.json" in selected
    assert "refined/natural_hybrid_f0p10_g000.json" in selected
