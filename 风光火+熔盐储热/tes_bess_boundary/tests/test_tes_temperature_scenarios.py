from __future__ import annotations

from dataclasses import replace

import pytest


def _base_tes():
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=1_000.0,
            ht_tank_capacity_t=1_000.0,
            mt_tank_capacity_t=1_000.0,
            lt_tank_capacity_t=1_000.0,
            specific_heat_mwh_per_tonne_k=1.55 / 3_600.0,
            temperature_ht=390.0,
            temperature_mt=285.0,
            temperature_lt=180.0,
            electric_heater_efficiency=0.98,
            steam_to_ht_efficiency=0.95,
            steam_to_mt_efficiency=0.95,
            power_block_efficiency=0.40,
            heat_exchanger_efficiency=0.95,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 1_000.0),
        port_caps=TESPortCaps(100.0, 100.0, 100.0, 50.0, 50.0),
    )


def test_e0d8_hitec_set_uses_normalized_enthalpy_quartiles() -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        MTTemperatureBasis,
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    scenarios = build_e0d8_hitec_normalized_mt_scenarios()

    assert scenarios.temperature_lt_c == 180.0
    assert scenarios.temperature_ht_c == 390.0
    assert scenarios.endpoint_source_doi == "10.1016/j.apenergy.2025.126876"
    assert scenarios.scenario_ids == (
        "low_grade_25",
        "balanced_50",
        "low_grade_75",
    )
    assert tuple(point.low_grade_enthalpy_fraction for point in scenarios.points) == (
        0.25,
        0.50,
        0.75,
    )
    assert tuple(point.temperature_mt_c for point in scenarios.points) == (
        232.5,
        285.0,
        337.5,
    )
    assert all(
        point.temperature_basis
        is MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY
        for point in scenarios.points
    )
    assert all(point.source_id.startswith("author:") for point in scenarios.points)


def test_fraction_is_exact_raw_sensible_enthalpy_partition() -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    scenarios = build_e0d8_hitec_normalized_mt_scenarios()

    for point in scenarios.points:
        assert point.low_grade_delta_k == pytest.approx(
            point.low_grade_enthalpy_fraction * scenarios.total_delta_k
        )
        assert point.high_grade_delta_k == pytest.approx(
            point.high_grade_enthalpy_fraction * scenarios.total_delta_k
        )
        assert (
            point.low_grade_enthalpy_fraction
            + point.high_grade_enthalpy_fraction
        ) == pytest.approx(1.0)


def test_apply_changes_only_mt_and_preserves_installed_boundary() -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    base = _base_tes()
    scenarios = build_e0d8_hitec_normalized_mt_scenarios()
    heat_rich = scenarios.apply_to_tes(base, "low_grade_75")

    assert heat_rich.physics.temperature_mt == 337.5
    assert heat_rich.physics.temperature_lt == base.physics.temperature_lt
    assert heat_rich.physics.temperature_ht == base.physics.temperature_ht
    assert heat_rich.physics.salt_mass_t == base.physics.salt_mass_t
    assert heat_rich.initial_inventory == base.initial_inventory
    assert heat_rich.port_caps == base.port_caps


def test_all_e0d8_candidates_pass_reference_pinch_and_material_envelope() -> None:
    from tes_bess_boundary.tes_heat_delivery import (
        build_hitec_candidate_envelope,
        build_li2026_reference_heat_network,
    )
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    scenarios = build_e0d8_hitec_normalized_mt_scenarios()
    audits = scenarios.certify_heat_delivery(
        _base_tes(),
        heat_network=build_li2026_reference_heat_network(
            hot_end_minimum_approach_k=15.0,
            cold_end_minimum_approach_k=15.0,
        ),
        material=build_hitec_candidate_envelope(
            minimum_liquid_margin_k=20.0
        ),
        dispatch_interval_hours=1.0,
    )

    assert len(audits) == 3
    assert tuple(audit.tes.physics.temperature_mt for audit in audits) == (
        232.5,
        285.0,
        337.5,
    )
    assert all(audit.violations == () for audit in audits)


def test_scenario_set_rejects_arbitrary_or_degenerate_partitions() -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        MTScenarioPoint,
        MTScenarioSet,
        MTTemperatureBasis,
    )

    with pytest.raises(ValueError, match="strictly between zero and one"):
        MTScenarioPoint(
            scenario_id="degenerate",
            temperature_lt_c=180.0,
            temperature_mt_c=389.0,
            temperature_ht_c=390.0,
            low_grade_enthalpy_fraction=1.0,
            temperature_basis=MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY,
            source_id="author:invalid",
        )

    mismatched = MTScenarioPoint(
        scenario_id="mismatched",
        temperature_lt_c=180.0,
        temperature_mt_c=300.0,
        temperature_ht_c=390.0,
        low_grade_enthalpy_fraction=0.5,
        temperature_basis=MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY,
        source_id="author:mismatched",
    )
    with pytest.raises(ValueError, match="normalized enthalpy definition"):
        MTScenarioSet(
            set_id="invalid",
            temperature_lt_c=180.0,
            temperature_ht_c=390.0,
            endpoint_source_doi="10.1016/j.apenergy.2025.126876",
            points=(mismatched,),
        )


def test_provenance_rules_prevent_author_values_being_mislabeled_as_paper_data(
) -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        MTScenarioPoint,
        MTTemperatureBasis,
    )

    with pytest.raises(ValueError, match="DOI source_id"):
        MTScenarioPoint(
            scenario_id="paper-value",
            temperature_lt_c=180.0,
            temperature_mt_c=285.0,
            temperature_ht_c=390.0,
            low_grade_enthalpy_fraction=0.5,
            temperature_basis=MTTemperatureBasis.CORE_PAPER_DIRECT,
            source_id="Lv-2025",
        )
    with pytest.raises(ValueError, match="author:"):
        MTScenarioPoint(
            scenario_id="author-value",
            temperature_lt_c=180.0,
            temperature_mt_c=285.0,
            temperature_ht_c=390.0,
            low_grade_enthalpy_fraction=0.5,
            temperature_basis=MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY,
            source_id="10.1016/j.energy.2025.135580",
        )


def test_apply_rejects_tes_with_different_endpoint_temperatures() -> None:
    from tes_bess_boundary.tes_temperature_scenarios import (
        build_e0d8_hitec_normalized_mt_scenarios,
    )

    base = _base_tes()
    incompatible = replace(
        base,
        physics=replace(
            base.physics,
            temperature_ht=400.0,
        ),
    )
    scenarios = build_e0d8_hitec_normalized_mt_scenarios()

    with pytest.raises(ValueError, match="LT/HT endpoints"):
        scenarios.apply_to_tes(incompatible, "balanced_50")
