from __future__ import annotations

import pytest

from tes_bess_boundary.components.molten_salt import (
    MoltenSaltFlows,
    MoltenSaltPhysics,
    SaltInventory,
)


@pytest.fixture
def salt() -> MoltenSaltPhysics:
    return MoltenSaltPhysics(
        salt_mass_t=100.0,
        ht_tank_capacity_t=100.0,
        mt_tank_capacity_t=100.0,
        lt_tank_capacity_t=100.0,
        specific_heat_mwh_per_tonne_k=1.0,
        temperature_ht=3.0,
        temperature_mt=2.0,
        temperature_lt=1.0,
        electric_heater_efficiency=0.90,
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.50,
        heat_exchanger_efficiency=0.80,
    )


def test_inventory_energy_uses_non_overlapping_temperature_intervals(
    salt: MoltenSaltPhysics,
) -> None:
    inventory = SaltInventory(ht_mass_t=40.0, mt_mass_t=30.0, lt_mass_t=30.0)

    assert salt.high_grade_energy_mwh(inventory) == pytest.approx(40.0)
    assert salt.low_grade_energy_mwh(inventory) == pytest.approx(70.0)
    assert salt.total_stored_energy_mwh(inventory) == pytest.approx(110.0)


def test_allowed_paths_conserve_the_same_salt_mass(salt: MoltenSaltPhysics) -> None:
    inventory = SaltInventory(ht_mass_t=40.0, mt_mass_t=30.0, lt_mass_t=30.0)
    flows = MoltenSaltFlows(
        electric_lt_to_ht_tph=10.0,
        steam_lt_to_ht_tph=0.0,
        steam_lt_to_mt_tph=0.0,
        power_ht_to_mt_tph=5.0,
        heat_mt_to_lt_tph=3.0,
        loss_ht_to_mt_tph=0.0,
        loss_mt_to_lt_tph=0.0,
    )

    updated = salt.step(inventory, flows, dt_hours=1.0)

    assert updated == SaltInventory(ht_mass_t=45.0, mt_mass_t=32.0, lt_mass_t=23.0)
    assert updated.total_mass_t == pytest.approx(100.0)


def test_same_salt_can_generate_power_then_supply_heat_without_double_counting(
    salt: MoltenSaltPhysics,
) -> None:
    initial = SaltInventory(ht_mass_t=10.0, mt_mass_t=0.0, lt_mass_t=90.0)
    after_power = salt.step(
        initial,
        MoltenSaltFlows(power_ht_to_mt_tph=10.0),
        dt_hours=1.0,
    )
    after_heat = salt.step(
        after_power,
        MoltenSaltFlows(heat_mt_to_lt_tph=10.0),
        dt_hours=1.0,
    )

    assert salt.electric_output_mw(10.0) == pytest.approx(5.0)
    assert salt.heat_output_mw(10.0) == pytest.approx(8.0)
    assert after_power == SaltInventory(ht_mass_t=0.0, mt_mass_t=10.0, lt_mass_t=90.0)
    assert after_heat == SaltInventory(ht_mass_t=0.0, mt_mass_t=0.0, lt_mass_t=100.0)


def test_charge_input_efficiencies_use_input_side_energy_basis(
    salt: MoltenSaltPhysics,
) -> None:
    assert salt.electric_charge_input_mw(10.0) == pytest.approx(20.0 / 0.90)
    assert salt.steam_to_ht_input_mw(10.0) == pytest.approx(20.0 / 0.95)
    assert salt.steam_to_mt_input_mw(10.0) == pytest.approx(10.0 / 0.96)


def test_negative_or_capacity_violating_flows_are_rejected(
    salt: MoltenSaltPhysics,
) -> None:
    inventory = SaltInventory(ht_mass_t=0.0, mt_mass_t=0.0, lt_mass_t=100.0)

    with pytest.raises(ValueError):
        salt.step(
            inventory,
            MoltenSaltFlows(power_ht_to_mt_tph=1.0),
            dt_hours=1.0,
        )


def test_invalid_temperature_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="temperature"):
        MoltenSaltPhysics(
            salt_mass_t=1.0,
            ht_tank_capacity_t=1.0,
            mt_tank_capacity_t=1.0,
            lt_tank_capacity_t=1.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=2.0,
            temperature_mt=3.0,
            temperature_lt=1.0,
            electric_heater_efficiency=0.9,
            steam_to_ht_efficiency=0.9,
            steam_to_mt_efficiency=0.9,
            power_block_efficiency=0.5,
            heat_exchanger_efficiency=0.8,
        )
