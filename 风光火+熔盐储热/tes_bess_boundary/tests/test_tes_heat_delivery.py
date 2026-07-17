from __future__ import annotations

from dataclasses import replace

import pytest


def _tes_spec(
    *,
    temperature_ht: float = 390.0,
    temperature_mt: float = 200.0,
    temperature_lt: float = 180.0,
):
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=10.0,
            ht_tank_capacity_t=10.0,
            mt_tank_capacity_t=10.0,
            lt_tank_capacity_t=10.0,
            specific_heat_mwh_per_tonne_k=1.55 / 3_600.0,
            temperature_ht=temperature_ht,
            temperature_mt=temperature_mt,
            temperature_lt=temperature_lt,
            electric_heater_efficiency=0.98,
            steam_to_ht_efficiency=0.95,
            steam_to_mt_efficiency=0.95,
            power_block_efficiency=0.4,
            heat_exchanger_efficiency=0.95,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 10.0),
        port_caps=TESPortCaps(3.0, 4.0, 5.0, 1.0, 1.0),
    )


def _reference_audit(*, temperature_mt: float = 200.0):
    from tes_bess_boundary.tes_heat_delivery import (
        TESHeatDeliveryPinchAudit,
        build_hitec_candidate_envelope,
        build_li2026_reference_heat_network,
    )

    return TESHeatDeliveryPinchAudit(
        tes=_tes_spec(temperature_mt=temperature_mt),
        heat_network=build_li2026_reference_heat_network(
            hot_end_minimum_approach_k=15.0,
            cold_end_minimum_approach_k=15.0,
        ),
        material=build_hitec_candidate_envelope(
            minimum_liquid_margin_k=20.0
        ),
        dispatch_interval_hours=1.0,
    )


def test_li2026_reference_is_not_mislabeled_as_yangling_primary_data() -> None:
    from tes_bess_boundary.tes_heat_delivery import (
        HeatNetworkTemperatureBasis,
        build_li2026_reference_heat_network,
    )

    network = build_li2026_reference_heat_network(
        hot_end_minimum_approach_k=10.0,
        cold_end_minimum_approach_k=10.0,
    )

    assert network.supply_temperature_c == 120.0
    assert network.return_temperature_c == 70.0
    assert (
        network.temperature_basis
        is HeatNetworkTemperatureBasis.CORE_REFERENCE_SCENARIO
    )
    assert network.source_id == "10.1016/j.energy.2026.141711"


def test_reference_heat_network_proves_feasibility_but_does_not_identify_mt() -> None:
    audit = _reference_audit(temperature_mt=200.0)

    assert audit.pinch_mt_lower_bound_c == 135.0
    assert audit.hot_end_pinch_binds_above_lt is False
    assert audit.hot_end_approach_k == 80.0
    assert audit.cold_end_approach_k == 110.0
    assert audit.liquid_margin_k == 38.0
    assert audit.maximum_supply_temperature_c == 185.0
    assert audit.maximum_return_temperature_c == 165.0
    assert audit.violations == ()
    audit.certify_heat_delivery()


def test_pinch_and_liquid_margin_failures_are_independently_reported() -> None:
    from tes_bess_boundary.tes_heat_delivery import (
        HeatNetworkPinchSpec,
        HeatNetworkTemperatureBasis,
        TESHeatDeliveryPinchAudit,
        build_hitec_candidate_envelope,
    )

    network = HeatNetworkPinchSpec(
        supply_temperature_c=190.0,
        return_temperature_c=170.0,
        hot_end_minimum_approach_k=15.0,
        cold_end_minimum_approach_k=15.0,
        temperature_basis=HeatNetworkTemperatureBasis.AUTHOR_SENSITIVITY,
        source_id="author-high-temperature-network-sensitivity",
    )
    audit = TESHeatDeliveryPinchAudit(
        tes=_tes_spec(temperature_mt=200.0, temperature_lt=150.0),
        heat_network=network,
        material=build_hitec_candidate_envelope(
            minimum_liquid_margin_k=20.0
        ),
        dispatch_interval_hours=1.0,
    )

    assert audit.violations == (
        "hot-end pinch is violated",
        "cold-end pinch is violated",
        "LT salt liquid margin is violated",
    )
    with pytest.raises(ValueError, match="hot-end pinch"):
        audit.certify_heat_delivery()


def test_heat_delivery_capacity_and_required_flows_use_explicit_units() -> None:
    audit = _reference_audit(temperature_mt=200.0)

    expected_per_tonne = 0.95 * (1.55 / 3_600.0) * 20.0
    assert audit.useful_heat_per_tonne_mwh == pytest.approx(expected_per_tonne)
    assert audit.inventory_limited_useful_heat_mw == pytest.approx(
        expected_per_tonne * 10.0
    )
    assert audit.effective_heat_output_cap_mw == pytest.approx(
        expected_per_tonne * 10.0
    )
    assert audit.port_cap_is_inventory_redundant is True
    assert audit.required_salt_flow_tph(1.0) == pytest.approx(
        1.0 / expected_per_tonne
    )
    assert audit.required_water_flow_tph(
        1.0,
        water_specific_heat_mwh_per_tonne_k=4.186 / 3_600.0,
    ) == pytest.approx(1.0 / ((4.186 / 3_600.0) * 50.0))


def test_material_upper_limit_and_inactive_heat_port_block_certification() -> None:
    from tes_bess_boundary.model import TESPortCaps
    from tes_bess_boundary.tes_heat_delivery import (
        TESHeatDeliveryPinchAudit,
        build_hitec_candidate_envelope,
        build_li2026_reference_heat_network,
    )

    hot_tes = _tes_spec(
        temperature_ht=600.0,
        temperature_mt=550.0,
        temperature_lt=180.0,
    )
    audit = TESHeatDeliveryPinchAudit(
        tes=hot_tes,
        heat_network=build_li2026_reference_heat_network(
            hot_end_minimum_approach_k=10.0,
            cold_end_minimum_approach_k=10.0,
        ),
        material=build_hitec_candidate_envelope(
            minimum_liquid_margin_k=20.0
        ),
        dispatch_interval_hours=1.0,
    )
    assert audit.violations == ("MT exceeds the material operating limit",)

    active = _tes_spec()
    inactive = replace(
        active,
        port_caps=TESPortCaps(3.0, 4.0, 5.0, 1.0, 0.0),
    )
    inactive_audit = replace(_reference_audit(), tes=inactive)
    with pytest.raises(ValueError, match="active heat port"):
        inactive_audit.certify_heat_delivery()


def test_temperature_and_approach_inputs_have_no_silent_defaults() -> None:
    from tes_bess_boundary.tes_heat_delivery import (
        HeatNetworkPinchSpec,
        HeatNetworkTemperatureBasis,
        MoltenSaltMaterialEnvelope,
    )

    with pytest.raises(ValueError, match="supply temperature"):
        HeatNetworkPinchSpec(
            70.0,
            120.0,
            10.0,
            10.0,
            HeatNetworkTemperatureBasis.AUTHOR_SENSITIVITY,
            "author-sensitivity",
        )
    with pytest.raises(ValueError, match="DOI"):
        HeatNetworkPinchSpec(
            120.0,
            70.0,
            10.0,
            10.0,
            HeatNetworkTemperatureBasis.CORE_REFERENCE_SCENARIO,
            "Li-2026",
        )
    with pytest.raises(ValueError, match="requires a DOI"):
        MoltenSaltMaterialEnvelope("HITEC", 142.0, 20.0, 540.0, "Wang-2025")
