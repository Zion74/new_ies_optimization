"""Public-contract tests for TES literature-cost capacity mapping."""

from __future__ import annotations

import pytest


def _tes_spec() -> object:
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=10.0,
            ht_tank_capacity_t=11.0,
            mt_tank_capacity_t=12.0,
            lt_tank_capacity_t=13.0,
            specific_heat_mwh_per_tonne_k=0.001,
            temperature_ht=600.0,
            temperature_mt=400.0,
            temperature_lt=200.0,
            electric_heater_efficiency=0.8,
            steam_to_ht_efficiency=0.9,
            steam_to_mt_efficiency=0.95,
            power_block_efficiency=0.4,
            heat_exchanger_efficiency=0.875,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 10.0),
        port_caps=TESPortCaps(
            electric_charge_input_mw=3.0,
            steam_to_ht_reference_input_mw=4.0,
            steam_to_mt_reference_input_mw=5.0,
            electric_output_mw=6.0,
            heat_output_mw=7.0,
        ),
    )


def test_tes_capacity_ledger_maps_inventory_temperature_span_and_port_bases() -> (
    None
):
    from tes_bess_boundary.tes_cost_mapping import (
        TESCapacityBasis,
        derive_tes_capacity_ledger,
    )

    ledger = derive_tes_capacity_ledger(_tes_spec())

    assert ledger.quantity(TESCapacityBasis.SALT_INVENTORY_KG) == pytest.approx(
        10_000.0
    )
    assert ledger.quantity(
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH
    ) == pytest.approx(4_000.0)
    assert ledger.quantity(TESCapacityBasis.HT_TANK_CAPACITY_T) == pytest.approx(
        11.0
    )
    assert ledger.quantity(TESCapacityBasis.MT_TANK_CAPACITY_T) == pytest.approx(
        12.0
    )
    assert ledger.quantity(TESCapacityBasis.LT_TANK_CAPACITY_T) == pytest.approx(
        13.0
    )
    assert ledger.quantity(
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL
    ) == pytest.approx(3_000.0)
    assert ledger.quantity(
        TESCapacityBasis.HIGH_GRADE_STEAM_HX_INPUT_KW_TH
    ) == pytest.approx(4_000.0)
    assert ledger.quantity(
        TESCapacityBasis.MEDIUM_GRADE_STEAM_HX_INPUT_KW_TH
    ) == pytest.approx(5_000.0)
    assert ledger.quantity(
        TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH
    ) == pytest.approx(15_000.0)
    assert ledger.quantity(
        TESCapacityBasis.HEAT_DELIVERY_HX_INPUT_KW_TH
    ) == pytest.approx(8_000.0)
    assert ledger.quantity(TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL) == pytest.approx(
        6_000.0
    )
    assert ledger.quantity(TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH) == pytest.approx(
        7_000.0
    )
    assert ledger.quantity(TESCapacityBasis.SYSTEM_COUNT) == pytest.approx(1.0)


def test_tes_component_bindings_create_exact_portfolio_quantities() -> None:
    from tes_bess_boundary.economics import (
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )
    from tes_bess_boundary.tes_cost_mapping import (
        TESCapacityBasis,
        TESComponent,
        TESComponentCostBinding,
        bind_tes_cost_portfolio,
    )

    common = dict(
        currency="CNY",
        price_base_year=2024,
        initial_cost_per_unit=1.0,
        service_life_years=20.0,
    )
    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="tes_salt",
                capacity_unit="kg",
                asset_class=LifecycleAssetClass.TES_COMPONENT,
                **common,
            ),
            LifecycleCostSpec(
                asset_id="tes_electric_heater",
                capacity_unit="kW_el",
                asset_class=LifecycleAssetClass.TES_COMPONENT,
                **common,
            ),
            LifecycleCostSpec(
                asset_id="tes_salt_to_steam_generator",
                capacity_unit="kW_th",
                asset_class=LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
                **common,
            ),
            LifecycleCostSpec(
                asset_id="tes_existing_turbine_reuse",
                capacity_unit="system",
                initial_cost_per_unit=0.0,
                asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
                **{
                    key: value
                    for key, value in common.items()
                    if key != "initial_cost_per_unit"
                },
            ),
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.05),
    )

    fixed = bind_tes_cost_portfolio(
        _tes_spec(),
        portfolio,
        (
            TESComponentCostBinding(
                "tes_salt",
                TESComponent.SALT,
                TESCapacityBasis.SALT_INVENTORY_KG,
                reference_temperature_range_c=(100.0, 700.0),
            ),
            TESComponentCostBinding(
                "tes_electric_heater",
                TESComponent.ELECTRIC_HEATER,
                TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
                reference_temperature_range_c=(100.0, 700.0),
            ),
            TESComponentCostBinding(
                "tes_salt_to_steam_generator",
                TESComponent.SALT_TO_STEAM_GENERATOR,
                TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH,
                reference_temperature_range_c=(350.0, 650.0),
            ),
            TESComponentCostBinding(
                "tes_existing_turbine_reuse",
                TESComponent.EXISTING_TURBINE_REUSE,
                TESCapacityBasis.SYSTEM_COUNT,
            ),
        ),
    )

    assert fixed.installed_quantities == {
        "tes_salt": 10_000.0,
        "tes_electric_heater": 3_000.0,
        "tes_salt_to_steam_generator": 15_000.0,
        "tes_existing_turbine_reuse": 1.0,
    }

    with pytest.raises(ValueError, match="not valid for TES component"):
        bind_tes_cost_portfolio(
            _tes_spec(),
            portfolio,
            (
                TESComponentCostBinding(
                    "tes_salt",
                    TESComponent.SALT,
                    TESCapacityBasis.SALT_INVENTORY_KG,
                    reference_temperature_range_c=(100.0, 700.0),
                ),
                TESComponentCostBinding(
                    "tes_electric_heater",
                    TESComponent.ELECTRIC_HEATER,
                    TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH,
                    reference_temperature_range_c=(100.0, 700.0),
                ),
                TESComponentCostBinding(
                    "tes_salt_to_steam_generator",
                    TESComponent.SALT_TO_STEAM_GENERATOR,
                    TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH,
                    reference_temperature_range_c=(350.0, 650.0),
                ),
                TESComponentCostBinding(
                    "tes_existing_turbine_reuse",
                    TESComponent.EXISTING_TURBINE_REUSE,
                    TESCapacityBasis.SYSTEM_COUNT,
                ),
            ),
        )

    wrong_unit_portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="tes_salt",
                capacity_unit="tonne",
                asset_class=LifecycleAssetClass.TES_COMPONENT,
                **common,
            ),
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.05),
    )
    with pytest.raises(ValueError, match="capacity unit"):
        bind_tes_cost_portfolio(
            _tes_spec(),
            wrong_unit_portfolio,
            (
                TESComponentCostBinding(
                    "tes_salt",
                    TESComponent.SALT,
                    TESCapacityBasis.SALT_INVENTORY_KG,
                    reference_temperature_range_c=(100.0, 700.0),
                ),
            ),
        )

    with pytest.raises(ValueError, match="temperature range"):
        bind_tes_cost_portfolio(
            _tes_spec(),
            build_lifecycle_cost_portfolio(
                (
                    LifecycleCostSpec(
                        asset_id="tes_salt",
                        capacity_unit="kg",
                        asset_class=LifecycleAssetClass.TES_COMPONENT,
                        **common,
                    ),
                ),
                ProjectFinance(project_years=20, real_discount_rate=0.05),
            ),
            (
                TESComponentCostBinding(
                    "tes_salt",
                    TESComponent.SALT,
                    TESCapacityBasis.SALT_INVENTORY_KG,
                    reference_temperature_range_c=(240.0, 650.0),
                ),
            ),
        )


def test_tes_component_temperature_windows_block_undisclosed_extrapolation() -> None:
    from tes_bess_boundary.tes_cost_mapping import (
        TESCapacityBasis,
        TESComponent,
        TESComponentCostBinding,
        derive_tes_capacity_ledger,
    )

    ledger = derive_tes_capacity_ledger(_tes_spec())

    assert ledger.required_temperature_interval_c(TESComponent.SALT) == (
        200.0,
        600.0,
    )
    assert ledger.required_temperature_interval_c(
        TESComponent.SALT_TO_STEAM_GENERATOR
    ) == (400.0, 600.0)
    assert ledger.required_temperature_interval_c(TESComponent.HEAT_DELIVERY_HX) == (
        200.0,
        400.0,
    )
    assert ledger.required_temperature_interval_c(
        TESComponent.EXISTING_TURBINE_REUSE
    ) is None

    compatible = TESComponentCostBinding(
        "generator",
        TESComponent.SALT_TO_STEAM_GENERATOR,
        TESCapacityBasis.SALT_TO_STEAM_GENERATOR_INPUT_KW_TH,
        reference_temperature_range_c=(290.0, 620.0),
    )
    assert ledger.temperature_compatible(compatible)

    outside_range = TESComponentCostBinding(
        "salt",
        TESComponent.SALT,
        TESCapacityBasis.SALT_INVENTORY_KG,
        reference_temperature_range_c=(240.0, 650.0),
    )
    assert not ledger.temperature_compatible(outside_range)


def test_full_sensible_heat_basis_requires_every_state_tank_to_hold_all_salt() -> (
    None
):
    from dataclasses import replace

    from tes_bess_boundary.tes_cost_mapping import derive_tes_capacity_ledger

    tes = _tes_spec()
    with pytest.raises(ValueError, match="full salt inventory"):
        derive_tes_capacity_ledger(
            replace(
                tes,
                physics=replace(tes.physics, mt_tank_capacity_t=9.0),
            )
        )
