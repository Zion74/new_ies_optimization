import pytest


def test_project_finance_factors_match_independent_twenty_year_golden() -> None:
    from tes_bess_boundary.economics import ProjectFinance

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)

    assert finance.present_value_annuity_factor == pytest.approx(8.513563719758556)
    assert finance.capital_recovery_factor == pytest.approx(0.11745962477254576)
    assert finance.discount_factor(7.0) == pytest.approx(0.5131581182307065)
    assert finance.equivalent_annual_cost(1_774.4749292218408) == pytest.approx(
        208.4291593546871
    )

    zero_discount = ProjectFinance(project_years=5, real_discount_rate=0.0)
    assert zero_discount.present_value_annuity_factor == pytest.approx(5.0)
    assert zero_discount.capital_recovery_factor == pytest.approx(0.2)

    tiny_rate = ProjectFinance(project_years=20, real_discount_rate=1e-16)
    assert tiny_rate.present_value_annuity_factor == pytest.approx(20.0)
    assert tiny_rate.capital_recovery_factor == pytest.approx(0.05)


def test_lifecycle_ledger_matches_independent_replacement_residual_fom_golden() -> None:
    from tes_bess_boundary.economics import (
        CashFlowKind,
        LifecycleCostSpec,
        ProjectFinance,
        annualize_lifecycle_cost,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)
    spec = LifecycleCostSpec(
        asset_id="synthetic_heat_exchanger",
        capacity_unit="MW",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=1_000.0,
        service_life_years=7.0,
        replacement_cost_per_unit=800.0,
        fixed_om_per_unit_year=20.0,
        residual_recovery_fraction=1.0,
    )

    ledger = annualize_lifecycle_cost(spec, finance)

    assert ledger.replacement_years == pytest.approx((7.0, 14.0))
    assert ledger.remaining_life_fraction == pytest.approx(1.0 / 7.0)
    assert ledger.terminal_residual_value_per_unit == pytest.approx(800.0 / 7.0)
    assert ledger.initial_cost_present_value == pytest.approx(1_000.0)
    assert ledger.replacement_cost_present_value == pytest.approx(621.191498029429)
    assert ledger.residual_credit_present_value == pytest.approx(16.98784320275925)
    assert ledger.capital_net_present_value == pytest.approx(1_604.2036548266697)
    assert ledger.fixed_om_present_value == pytest.approx(170.27127439517113)
    assert ledger.total_net_present_value == pytest.approx(1_774.4749292218408)
    assert ledger.annualized_capital_cost == pytest.approx(188.42915935468713)
    assert ledger.annualized_fixed_om_cost == pytest.approx(20.0)
    assert ledger.total_equivalent_annual_cost == pytest.approx(208.4291593546871)

    assert sum(event.kind is CashFlowKind.REPLACEMENT for event in ledger.events) == 2
    assert sum(event.kind is CashFlowKind.FIXED_OM for event in ledger.events) == 20
    residual_event = next(
        event for event in ledger.events if event.kind is CashFlowKind.RESIDUAL_CREDIT
    )
    assert residual_event.year == pytest.approx(20.0)
    assert residual_event.amount_per_unit == pytest.approx(-800.0 / 7.0)
    assert residual_event.present_value_per_unit == pytest.approx(-16.98784320275925)

    higher_replacement = annualize_lifecycle_cost(
        LifecycleCostSpec(
            asset_id="synthetic_heat_exchanger",
            capacity_unit="MW",
            currency="CNY",
            price_base_year=2025,
            initial_cost_per_unit=1_000.0,
            service_life_years=7.0,
            replacement_cost_per_unit=1_000.0,
            fixed_om_per_unit_year=20.0,
            residual_recovery_fraction=1.0,
        ),
        finance,
    )
    assert higher_replacement.total_equivalent_annual_cost == pytest.approx(
        226.1715430002226
    )
    assert higher_replacement.total_equivalent_annual_cost > (
        ledger.total_equivalent_annual_cost
    )


def test_bess_two_anchor_calibration_recovers_complete_cell_cash_flows() -> None:
    from tes_bess_boundary.economics import (
        BESSCellDegradationSpec,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        calibrate_bess_cell_cost,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)
    cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
        replacement_cost_per_unit=100.0,
        residual_recovery_fraction=1.0,
    )
    degradation = BESSCellDegradationSpec(
        cell_lifecycle=cell,
        cycle_life_ac_efc=1_000.0,
        reference_annual_ac_efc=100.0,
        ac_deliverable_fraction=1.0,
    )

    calibration = calibrate_bess_cell_cost(degradation, finance)

    assert calibration.reference_effective_life_years == pytest.approx(5.0)
    assert calibration.zero_cycle_ledger.replacement_years == pytest.approx((10.0,))
    assert calibration.reference_cycle_ledger.replacement_years == pytest.approx(
        (5.0, 10.0, 15.0)
    )
    assert calibration.zero_cycle_anchor_eac_per_nominal_mwh == pytest.approx(
        16.27453948825115
    )
    assert calibration.reference_cycle_anchor_eac_per_nominal_mwh == pytest.approx(
        26.379748079474528
    )
    assert calibration.calendar_cost_per_nominal_mwh_year == pytest.approx(
        16.27453948825115
    )
    assert calibration.cycle_cost_per_ac_discharge_mwh == pytest.approx(
        0.10105208591223377
    )

    assert calibration.annual_cell_cost(
        nominal_energy_mwh=2.0,
        ac_discharge_throughput_mwh=0.0,
    ) == pytest.approx(32.5490789765023)
    assert calibration.maximum_annual_ac_throughput_mwh(2.0) == pytest.approx(200.0)
    assert calibration.annual_cell_cost(
        nominal_energy_mwh=2.0,
        ac_discharge_throughput_mwh=200.0,
    ) == pytest.approx(52.759496158949055)
    assert calibration.annual_cell_cost(
        nominal_energy_mwh=2.0,
        ac_discharge_throughput_mwh=200.0,
    ) == pytest.approx(2.0 * calibration.reference_cycle_anchor_eac_per_nominal_mwh)


def test_lifecycle_boundaries_do_not_replace_at_the_project_endpoint() -> None:
    from tes_bess_boundary.economics import (
        LifecycleCostSpec,
        ProjectFinance,
        annualize_lifecycle_cost,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.0)
    common = dict(
        asset_id="boundary_asset",
        capacity_unit="MW",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        fixed_om_per_unit_year=3.0,
        residual_recovery_fraction=1.0,
    )

    exact_life = annualize_lifecycle_cost(
        LifecycleCostSpec(service_life_years=20.0, **common),
        finance,
    )
    assert exact_life.replacement_years == ()
    assert exact_life.remaining_life_fraction == pytest.approx(0.0)
    assert exact_life.total_equivalent_annual_cost == pytest.approx(8.0)

    longer_life = annualize_lifecycle_cost(
        LifecycleCostSpec(service_life_years=25.0, **common),
        finance,
    )
    assert longer_life.replacement_years == ()
    assert longer_life.remaining_life_fraction == pytest.approx(0.2)
    assert longer_life.terminal_residual_value_per_unit == pytest.approx(20.0)
    assert longer_life.total_equivalent_annual_cost == pytest.approx(7.0)

    no_residual = annualize_lifecycle_cost(
        LifecycleCostSpec(
            service_life_years=25.0,
            **{**common, "residual_recovery_fraction": 0.0},
        ),
        finance,
    )
    assert no_residual.residual_credit_present_value == pytest.approx(0.0)
    assert no_residual.total_equivalent_annual_cost == pytest.approx(8.0)
    assert no_residual.total_equivalent_annual_cost > (
        longer_life.total_equivalent_annual_cost
    )


def test_public_cash_flow_event_rejects_an_invalid_audit_record() -> None:
    from tes_bess_boundary.economics import CashFlowEvent, CashFlowKind

    with pytest.raises(ValueError, match="year"):
        CashFlowEvent(
            kind=CashFlowKind.REPLACEMENT,
            year=-1.0,
            amount_per_unit=100.0,
            discount_factor=1.0,
        )
    underflowed = CashFlowEvent(
        kind=CashFlowKind.REPLACEMENT,
        year=10_000.0,
        amount_per_unit=100.0,
        discount_factor=0.0,
    )
    assert underflowed.present_value_per_unit == pytest.approx(0.0)


def test_fixed_life_bess_sensitivity_has_no_second_replacement_or_cycle_charge() -> (
    None
):
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        fixed_life_bess_cell_cost,
    )

    cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
        replacement_cost_per_unit=100.0,
        residual_recovery_fraction=1.0,
    )

    fixed = fixed_life_bess_cell_cost(
        cell,
        ProjectFinance(project_years=20, real_discount_rate=0.10),
    )

    assert fixed.lifecycle_ledger.replacement_years == pytest.approx((10.0,))
    assert fixed.calendar_cost_per_nominal_mwh_year == pytest.approx(16.27453948825115)
    assert fixed.cycle_cost_per_ac_discharge_mwh == pytest.approx(0.0)
    assert fixed.annual_cell_cost(
        nominal_energy_mwh=2.0,
        ac_discharge_throughput_mwh=999.0,
    ) == pytest.approx(32.5490789765023)
    with pytest.raises(ValueError, match="canonical"):
        replace(fixed, calendar_cost_per_nominal_mwh_year=-1_000_000.0)
    with pytest.raises(ValueError, match="canonical"):
        replace(fixed, cycle_cost_per_ac_discharge_mwh=123.0)


def test_component_portfolio_preserves_asset_ledgers_and_capacity_homogeneity() -> None:
    from tes_bess_boundary.economics import (
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )

    finance = ProjectFinance(project_years=10, real_discount_rate=0.0)
    shared = dict(currency="CNY", price_base_year=2025)
    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="bess_charge_converter",
                capacity_unit="MW_charge",
                initial_cost_per_unit=100.0,
                service_life_years=10.0,
                fixed_om_per_unit_year=5.0,
                **shared,
            ),
            LifecycleCostSpec(
                asset_id="tes_salt",
                capacity_unit="tonne",
                initial_cost_per_unit=10.0,
                service_life_years=20.0,
                **shared,
            ),
            LifecycleCostSpec(
                asset_id="tes_ht_tank",
                capacity_unit="tonne_capacity",
                initial_cost_per_unit=50.0,
                service_life_years=5.0,
                **shared,
            ),
        ),
        finance,
    )

    annual = portfolio.evaluate(
        {
            "bess_charge_converter": 2.0,
            "tes_salt": 100.0,
            "tes_ht_tank": 3.0,
        }
    )

    assert portfolio.asset_ids == (
        "bess_charge_converter",
        "tes_salt",
        "tes_ht_tank",
    )
    assert annual.currency == "CNY"
    assert annual.price_base_year == 2025
    assert annual.initial_cost_present_value == pytest.approx(1_350.0)
    assert annual.replacement_cost_present_value == pytest.approx(150.0)
    assert annual.residual_credit_present_value == pytest.approx(500.0)
    assert annual.fixed_om_present_value == pytest.approx(100.0)
    assert annual.capital_net_present_value == pytest.approx(1_000.0)
    assert annual.total_net_present_value == pytest.approx(1_100.0)
    assert annual.annualized_capital_cost == pytest.approx(100.0)
    assert annual.annualized_fixed_om_cost == pytest.approx(10.0)
    assert annual.total_annual_cost == pytest.approx(110.0)
    assert annual.by_asset_id[
        "bess_charge_converter"
    ].total_annual_cost == pytest.approx(30.0)
    converter = annual.by_asset_id["bess_charge_converter"]
    assert converter.capacity_unit == "MW_charge"
    assert converter.installed_quantity == pytest.approx(2.0)
    assert converter.initial_cost_present_value == pytest.approx(200.0)
    assert converter.fixed_om_present_value == pytest.approx(100.0)
    assert converter.capital_net_present_value == pytest.approx(200.0)
    assert converter.total_net_present_value == pytest.approx(300.0)
    assert annual.by_asset_id["tes_salt"].total_annual_cost == pytest.approx(50.0)
    salt = annual.by_asset_id["tes_salt"]
    assert salt.capacity_unit == "tonne"
    assert salt.installed_quantity == pytest.approx(100.0)
    assert salt.initial_cost_present_value == pytest.approx(1_000.0)
    assert salt.residual_credit_present_value == pytest.approx(500.0)
    assert salt.capital_net_present_value == pytest.approx(500.0)
    assert salt.total_net_present_value == pytest.approx(500.0)
    assert annual.by_asset_id["tes_ht_tank"].total_annual_cost == pytest.approx(30.0)
    tank = annual.by_asset_id["tes_ht_tank"]
    assert tank.capacity_unit == "tonne_capacity"
    assert tank.installed_quantity == pytest.approx(3.0)
    assert tank.initial_cost_present_value == pytest.approx(150.0)
    assert tank.replacement_cost_present_value == pytest.approx(150.0)
    assert tank.capital_net_present_value == pytest.approx(300.0)
    assert tank.total_net_present_value == pytest.approx(300.0)

    doubled = portfolio.evaluate(
        {
            "bess_charge_converter": 4.0,
            "tes_salt": 200.0,
            "tes_ht_tank": 6.0,
        }
    )
    assert doubled.total_annual_cost == pytest.approx(2.0 * annual.total_annual_cost)


def test_bess_calibration_uses_ac_deliverable_fraction_exactly_once() -> None:
    from tes_bess_boundary.economics import (
        BESSCellDegradationSpec,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        calibrate_bess_cell_cost,
    )

    cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
        replacement_cost_per_unit=100.0,
    )
    calibration = calibrate_bess_cell_cost(
        BESSCellDegradationSpec(
            cell_lifecycle=cell,
            cycle_life_ac_efc=1_000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.10),
    )

    assert calibration.cycle_cost_per_ac_discharge_mwh == pytest.approx(
        0.12631510739029222
    )
    assert calibration.maximum_annual_ac_throughput_mwh(2.0) == pytest.approx(160.0)
    assert calibration.annual_cell_cost(
        nominal_energy_mwh=2.0,
        ac_discharge_throughput_mwh=160.0,
    ) == pytest.approx(52.759496158949055)
    with pytest.raises(ValueError, match="EFC limit"):
        calibration.annual_cell_cost(
            nominal_energy_mwh=2.0,
            ac_discharge_throughput_mwh=160.001,
        )


def test_generic_portfolio_rejects_a_calibrated_bess_cell_asset() -> None:
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        BESSCellDegradationSpec,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
        calibrate_bess_cell_cost,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)
    cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
    )
    calibrated_cell = calibrate_bess_cell_cost(
        BESSCellDegradationSpec(
            cell_lifecycle=cell,
            cycle_life_ac_efc=1_000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        ),
        finance,
    )
    with pytest.raises(ValueError, match="canonical"):
        replace(calibrated_cell, cycle_cost_per_ac_discharge_mwh=-1.0)

    with pytest.raises(ValueError, match="double count"):
        build_lifecycle_cost_portfolio(
            (cell,),
            finance,
        )

    non_cell = LifecycleCostSpec(
        asset_id="bess_converter",
        capacity_unit="MW",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=50.0,
        service_life_years=10.0,
    )
    portfolio = build_lifecycle_cost_portfolio(
        (non_cell,),
        finance,
        bess_cell_cost=calibrated_cell,
    )
    disguised_cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
    )
    with pytest.raises(ValueError, match="double count"):
        build_lifecycle_cost_portfolio(
            (disguised_cell,),
            finance,
            bess_cell_cost=calibrated_cell,
        )
    with pytest.raises(ValueError, match="double count"):
        type(portfolio)(
            finance=finance,
            ledgers=(calibrated_cell.zero_cycle_ledger,),
        )
    with pytest.raises(ValueError, match="tuple"):
        type(portfolio)(
            finance=finance,
            ledgers=[portfolio.ledgers[0]],
        )


def test_bess_cell_unit_and_common_finance_price_basis_are_mandatory() -> None:
    from tes_bess_boundary.economics import (
        BESSCellDegradationSpec,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
        calibrate_bess_cell_cost,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.10)
    wrong_unit_cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="kWh_internal",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
    )
    with pytest.raises(ValueError, match="MWh_internal"):
        BESSCellDegradationSpec(
            cell_lifecycle=wrong_unit_cell,
            cycle_life_ac_efc=1_000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        )

    cell = LifecycleCostSpec(
        asset_id="bess_cell",
        capacity_unit="MWh_internal",
        currency="USD",
        price_base_year=2020,
        initial_cost_per_unit=100.0,
        service_life_years=10.0,
        asset_class=LifecycleAssetClass.BESS_CELL,
    )
    calibrated_cell = calibrate_bess_cell_cost(
        BESSCellDegradationSpec(
            cell_lifecycle=cell,
            cycle_life_ac_efc=1_000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        ),
        finance,
    )
    non_cell = LifecycleCostSpec(
        asset_id="bess_converter",
        capacity_unit="MW",
        currency="CNY",
        price_base_year=2025,
        initial_cost_per_unit=50.0,
        service_life_years=10.0,
    )
    with pytest.raises(ValueError, match="currency and price base year"):
        build_lifecycle_cost_portfolio(
            (non_cell,),
            finance,
            bess_cell_cost=calibrated_cell,
        )

    other_finance_cell = calibrate_bess_cell_cost(
        BESSCellDegradationSpec(
            cell_lifecycle=LifecycleCostSpec(
                asset_id="bess_cell",
                capacity_unit="MWh_internal",
                currency="CNY",
                price_base_year=2025,
                initial_cost_per_unit=100.0,
                service_life_years=10.0,
                asset_class=LifecycleAssetClass.BESS_CELL,
            ),
            cycle_life_ac_efc=1_000.0,
            reference_annual_ac_efc=100.0,
            ac_deliverable_fraction=0.8,
        ),
        ProjectFinance(project_years=25, real_discount_rate=0.05),
    )
    with pytest.raises(ValueError, match="common project finance"):
        build_lifecycle_cost_portfolio(
            (non_cell,),
            finance,
            bess_cell_cost=other_finance_cell,
        )

    with pytest.raises(ValueError, match="one currency and one price base year"):
        build_lifecycle_cost_portfolio(
            (
                non_cell,
                LifecycleCostSpec(
                    asset_id="tes_pump_usd",
                    capacity_unit="MW_flow",
                    currency="USD",
                    price_base_year=2025,
                    initial_cost_per_unit=10.0,
                    service_life_years=10.0,
                ),
            ),
            finance,
        )

    with pytest.raises(ValueError, match="one currency and one price base year"):
        build_lifecycle_cost_portfolio(
            (
                non_cell,
                LifecycleCostSpec(
                    asset_id="tes_pump_old_cny",
                    capacity_unit="MW_flow",
                    currency="CNY",
                    price_base_year=2020,
                    initial_cost_per_unit=10.0,
                    service_life_years=10.0,
                ),
            ),
            finance,
        )

    with pytest.raises(ValueError, match="unique"):
        build_lifecycle_cost_portfolio(
            (
                non_cell,
                LifecycleCostSpec(
                    asset_id="bess_converter",
                    capacity_unit="MW",
                    currency="CNY",
                    price_base_year=2025,
                    initial_cost_per_unit=60.0,
                    service_life_years=12.0,
                ),
            ),
            finance,
        )


def test_price_basis_conversion_is_explicit_auditable_and_exact() -> None:
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        LifecycleAssetClass,
        LifecycleCostSpec,
        PriceBasisConversion,
        convert_lifecycle_cost_spec,
    )

    source = LifecycleCostSpec(
        asset_id="bess_cell_pack",
        capacity_unit="MWh_internal",
        currency="USD",
        price_base_year=2020,
        initial_cost_per_unit=100.0,
        replacement_cost_per_unit=80.0,
        fixed_om_per_unit_year=2.0,
        service_life_years=10.0,
        residual_recovery_fraction=0.25,
        asset_class=LifecycleAssetClass.BESS_NON_CELL,
    )
    conversion = PriceBasisConversion(
        source_currency="USD",
        source_price_base_year=2020,
        target_currency="CNY",
        target_price_base_year=2024,
        source_price_index=100.0,
        target_price_index=125.0,
        target_currency_per_source_currency=7.0,
        price_index_series_id="synthetic-cpi",
        exchange_rate_series_id="synthetic-fx",
    )

    audit = convert_lifecycle_cost_spec(source, conversion)

    assert audit.source_spec is source
    assert audit.conversion is conversion
    assert audit.inflation_factor == pytest.approx(1.25)
    assert audit.conversion_factor == pytest.approx(8.75)
    assert audit.converted_spec == LifecycleCostSpec(
        asset_id="bess_cell_pack",
        capacity_unit="MWh_internal",
        currency="CNY",
        price_base_year=2024,
        initial_cost_per_unit=875.0,
        replacement_cost_per_unit=700.0,
        fixed_om_per_unit_year=17.5,
        service_life_years=10.0,
        residual_recovery_fraction=0.25,
        asset_class=LifecycleAssetClass.BESS_NON_CELL,
    )
    with pytest.raises(ValueError, match="canonical"):
        replace(audit, converted_spec=source)

    with pytest.raises(ValueError, match="source currency and price base year"):
        convert_lifecycle_cost_spec(
            source,
            PriceBasisConversion(
                source_currency="EUR",
                source_price_base_year=2020,
                target_currency="CNY",
                target_price_base_year=2024,
                source_price_index=100.0,
                target_price_index=125.0,
                target_currency_per_source_currency=7.0,
                price_index_series_id="synthetic-cpi",
                exchange_rate_series_id="synthetic-fx",
            ),
        )


def test_price_basis_conversion_rejects_ambiguous_currency_and_false_same_currency_fx() -> (
    None
):
    from tes_bess_boundary.economics import PriceBasisConversion

    common = dict(
        source_price_base_year=2020,
        target_currency="CNY",
        target_price_base_year=2024,
        source_price_index=100.0,
        target_price_index=125.0,
        target_currency_per_source_currency=7.0,
        price_index_series_id="synthetic-cpi",
        exchange_rate_series_id="synthetic-fx",
    )
    with pytest.raises(ValueError, match="ISO 4217"):
        PriceBasisConversion(source_currency="$", **common)

    with pytest.raises(ValueError, match="same-currency conversion"):
        PriceBasisConversion(
            source_currency="CNY",
            **common,
        )


def test_existing_turbine_reuse_rejects_initial_or_replacement_capex() -> None:
    from tes_bess_boundary.economics import (
        LifecycleAssetClass,
        LifecycleCostSpec,
    )

    common = dict(
        asset_id="existing_turbine_reuse",
        capacity_unit="system",
        currency="CNY",
        price_base_year=2024,
        service_life_years=20.0,
        asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
    )
    with pytest.raises(ValueError, match="must not carry capital cost"):
        LifecycleCostSpec(initial_cost_per_unit=1.0, **common)
    with pytest.raises(ValueError, match="must not carry capital cost"):
        LifecycleCostSpec(
            initial_cost_per_unit=0.0,
            replacement_cost_per_unit=1.0,
            **common,
        )

    marker = LifecycleCostSpec(
        initial_cost_per_unit=0.0,
        fixed_om_per_unit_year=2.0,
        **common,
    )
    assert marker.asset_class is LifecycleAssetClass.EXISTING_TURBINE_REUSE


def test_tes_generation_cost_roles_are_complete_mutually_exclusive_and_count_once() -> (
    None
):
    from tes_bess_boundary.economics import (
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )

    finance = ProjectFinance(project_years=20, real_discount_rate=0.0)
    common = dict(
        capacity_unit="system",
        currency="CNY",
        price_base_year=2024,
        service_life_years=20.0,
    )
    generator = LifecycleCostSpec(
        asset_id="salt_to_steam_generator",
        initial_cost_per_unit=100.0,
        asset_class=LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
        **common,
    )
    reuse = LifecycleCostSpec(
        asset_id="existing_turbine_reuse",
        initial_cost_per_unit=0.0,
        fixed_om_per_unit_year=2.0,
        asset_class=LifecycleAssetClass.EXISTING_TURBINE_REUSE,
        **common,
    )
    new_power_block = LifecycleCostSpec(
        asset_id="new_power_block",
        initial_cost_per_unit=50.0,
        asset_class=LifecycleAssetClass.NEW_POWER_BLOCK,
        **common,
    )

    for incomplete in ((reuse,), (generator,), (generator, reuse, new_power_block)):
        with pytest.raises(ValueError, match="TES generation cost classification"):
            build_lifecycle_cost_portfolio(incomplete, finance)

    reuse_portfolio = build_lifecycle_cost_portfolio((generator, reuse), finance)
    reuse_audit = reuse_portfolio.evaluate(
        {"salt_to_steam_generator": 1.0, "existing_turbine_reuse": 1.0}
    )
    assert reuse_audit.total_annual_cost == pytest.approx(7.0)
    assert reuse_audit.by_asset_id[
        "existing_turbine_reuse"
    ].annualized_capital_cost == pytest.approx(0.0)

    new_build = build_lifecycle_cost_portfolio((generator, new_power_block), finance)
    assert new_build.evaluate(
        {"salt_to_steam_generator": 1.0, "new_power_block": 1.0}
    ).total_annual_cost == pytest.approx(7.5)


def test_portfolio_rejects_nonfinite_scaled_costs_and_heterogeneous_wrong_keys() -> (
    None
):
    from dataclasses import replace

    from tes_bess_boundary.economics import (
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )

    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="huge_component",
                capacity_unit="MW",
                currency="CNY",
                price_base_year=2025,
                initial_cost_per_unit=1e308,
                service_life_years=20.0,
            ),
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.10),
    )
    with pytest.raises(ValueError, match="finite"):
        portfolio.evaluate({"huge_component": 1e308})
    with pytest.raises(ValueError, match="cover each asset exactly"):
        portfolio.evaluate({"huge_component": 1.0, "extra": 1.0, 7: 1.0})

    corrupt = replace(
        portfolio.ledgers[0],
        annualized_capital_cost=-1_000_000.0,
        total_equivalent_annual_cost=-1_000_000.0,
    )
    with pytest.raises(ValueError, match="canonical"):
        type(portfolio)(finance=portfolio.finance, ledgers=(corrupt,))

    overflowing_aggregate = build_lifecycle_cost_portfolio(
        tuple(
            LifecycleCostSpec(
                asset_id=f"huge_{index}",
                capacity_unit="MW",
                currency="CNY",
                price_base_year=2025,
                initial_cost_per_unit=9e307,
                service_life_years=20.0,
            )
            for index in range(2)
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.10),
    )
    with pytest.raises(ValueError, match="totals must remain finite"):
        overflowing_aggregate.evaluate({"huge_0": 1.0, "huge_1": 1.0})


def test_public_specs_reject_non_numeric_values_with_value_errors() -> None:
    from tes_bess_boundary.economics import LifecycleCostSpec, ProjectFinance

    with pytest.raises(ValueError, match="real_discount_rate"):
        ProjectFinance(project_years=20, real_discount_rate="0.1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="real_discount_rate"):
        ProjectFinance(project_years=20, real_discount_rate=10**400)
    with pytest.raises(ValueError, match="initial_cost_per_unit"):
        LifecycleCostSpec(
            asset_id="invalid",
            capacity_unit="MW",
            currency="CNY",
            price_base_year=2025,
            initial_cost_per_unit="100",  # type: ignore[arg-type]
            service_life_years=10.0,
        )
