from __future__ import annotations

from dataclasses import replace

import pytest


def test_rahman_linked_package_is_qualified_but_not_silently_tac_ready() -> None:
    from tes_bess_boundary.formal_bess_costs import (
        build_rahman2019_bess_cost_basis,
    )

    basis = build_rahman2019_bess_cost_basis()

    assert basis.formal_source_qualified is True
    assert basis.formal_portfolio_ready is False
    assert basis.source_currency == "USD"
    assert basis.source_price_base_year == 2019
    assert basis.source_real_discount_rate == pytest.approx(0.081399921352733)
    assert basis.reference_cycle_life == pytest.approx(4389.60215351849)
    assert basis.direct_by_id["battery_capex"].source_value == 216.27
    assert basis.direct_by_id["enclosure_foundation"].source_value == pytest.approx(
        4.81032
    )
    assert basis.deferred_ids == (
        "cell_replacement_and_calendar_life_join",
        "variable_om_throughput_side",
        "pcs_modular_scale_curve",
    )


def test_rahman_non_cell_mapping_is_complete_and_avoids_cell_double_count() -> None:
    from tes_bess_boundary.economics import LifecycleAssetClass
    from tes_bess_boundary.formal_bess_costs import (
        build_rahman2019_bess_cost_basis,
    )

    specs = build_rahman2019_bess_cost_basis().source_non_cell_specs()
    by_id = {spec.asset_id: spec for spec in specs}

    assert set(by_id) == {
        "bess_pcs",
        "bess_bop",
        "bess_enclosure_foundation",
        "bess_battery_fixed_om",
        "bess_power_contingency",
        "bess_energy_contingency",
    }
    assert all(
        spec.asset_class is LifecycleAssetClass.BESS_NON_CELL for spec in specs
    )
    assert by_id["bess_pcs"].initial_cost_per_unit == pytest.approx(206810.0)
    assert by_id["bess_pcs"].fixed_om_per_unit_year == pytest.approx(2630.0)
    assert by_id["bess_bop"].initial_cost_per_unit == pytest.approx(106750.0)
    assert by_id["bess_enclosure_foundation"].initial_cost_per_unit == pytest.approx(
        4810.32
    )
    assert by_id["bess_battery_fixed_om"].fixed_om_per_unit_year == pytest.approx(
        10350.0
    )
    assert by_id["bess_power_contingency"].initial_cost_per_unit == pytest.approx(
        31356.0
    )
    assert by_id["bess_energy_contingency"].initial_cost_per_unit == pytest.approx(
        22108.032
    )
    assert all(spec.residual_recovery_fraction == 0.0 for spec in specs)


def test_rahman_non_cell_mapping_uses_one_audited_price_bridge() -> None:
    from tes_bess_boundary.economics import PriceBasisConversion
    from tes_bess_boundary.formal_bess_costs import (
        build_rahman2019_bess_cost_basis,
    )

    conversion = PriceBasisConversion(
        source_currency="USD",
        source_price_base_year=2019,
        target_currency="CNY",
        target_price_base_year=2024,
        source_price_index=255.657,
        target_price_index=313.689,
        target_currency_per_source_currency=7.1217,
        price_index_series_id="BLS CUUR0000SA0 CPI-U",
        exchange_rate_series_id="NBS 2024 CNY per USD",
    )
    converted = build_rahman2019_bess_cost_basis().convert_non_cell_specs(
        conversion
    )

    assert len(converted) == 6
    assert all(item.conversion == conversion for item in converted)
    assert all(item.converted_spec.currency == "CNY" for item in converted)
    assert all(item.converted_spec.price_base_year == 2024 for item in converted)
    by_id = {item.converted_spec.asset_id: item for item in converted}
    assert by_id["bess_pcs"].conversion_factor == pytest.approx(
        8.73826631502364
    )
    assert by_id["bess_pcs"].converted_spec.initial_cost_per_unit == pytest.approx(
        1807160.85661004
    )


def test_rahman_builder_refuses_a_downgraded_evidence_record() -> None:
    from tes_bess_boundary.cost_evidence import (
        CostEvidenceAudit,
        CostEvidenceUse,
        build_e0d10_reference_cost_audit,
    )
    from tes_bess_boundary.formal_bess_costs import (
        RAHMAN_EVIDENCE_ID,
        build_rahman2019_bess_cost_basis,
    )

    reference = build_e0d10_reference_cost_audit()
    records = tuple(
        replace(record, allowed_use=CostEvidenceUse.SENSITIVITY_ONLY)
        if record.evidence_id == RAHMAN_EVIDENCE_ID
        else record
        for record in reference.records
    )

    with pytest.raises(ValueError, match="allowed_use"):
        build_rahman2019_bess_cost_basis(CostEvidenceAudit(records))


def _formal_price_bridge() -> object:
    from tes_bess_boundary.economics import PriceBasisConversion

    return PriceBasisConversion(
        source_currency="USD",
        source_price_base_year=2019,
        target_currency="CNY",
        target_price_base_year=2024,
        source_price_index=255.657,
        target_price_index=313.689,
        target_currency_per_source_currency=7.1217,
        price_index_series_id="BLS CUUR0000SA0 CPI-U",
        exchange_rate_series_id="NBS 2024 CNY per USD",
    )


def test_resolved_join_uses_one_calendar_throughput_replacement_kernel() -> None:
    from tes_bess_boundary.economics import LifecycleAssetClass
    from tes_bess_boundary.formal_bess_costs import (
        BESSCellLifecycleJoin,
        build_resolved_rahman_bess_join_contract,
    )

    contract = build_resolved_rahman_bess_join_contract()
    degradation = contract.source_cell_degradation_spec(
        reference_annual_ac_efc=365.0,
        ac_deliverable_fraction=0.8,
    )

    assert contract.formal_fixed_capacity_ready is True
    assert contract.cell_lifecycle_join is (
        BESSCellLifecycleJoin.EXTERNAL_CALENDAR_AC_THROUGHPUT
    )
    assert degradation.cell_lifecycle.asset_class is LifecycleAssetClass.BESS_CELL
    assert degradation.cell_lifecycle.initial_cost_per_unit == pytest.approx(216270.0)
    assert degradation.cell_lifecycle.service_life_years == pytest.approx(13.0)
    assert degradation.cycle_life_ac_efc == pytest.approx(3250.0)
    assert degradation.cycle_life_ac_efc != pytest.approx(
        contract.source_basis.reference_cycle_life
    )


def test_resolved_variable_om_is_converted_on_ac_discharge_basis() -> None:
    from tes_bess_boundary.formal_bess_costs import (
        BESSVariableOMBasis,
        build_resolved_rahman_bess_join_contract,
    )

    contract = build_resolved_rahman_bess_join_contract()
    converted = contract.convert_variable_om_spec(_formal_price_bridge())

    assert contract.variable_om_basis is BESSVariableOMBasis.AC_DISCHARGE
    assert converted.source_spec.cost_per_ac_discharge_mwh == pytest.approx(2.74)
    assert converted.converted_spec.currency == "CNY"
    assert converted.converted_spec.price_base_year == 2024
    assert converted.converted_spec.cost_per_ac_discharge_mwh == pytest.approx(
        2.74 * 8.73826631502364
    )


def test_resolved_pcs_policy_enforces_source_domain_without_fake_pwl() -> None:
    from tes_bess_boundary.formal_bess_costs import (
        PCSScalePolicy,
        build_resolved_rahman_bess_join_contract,
    )

    contract = build_resolved_rahman_bess_join_contract()

    assert contract.pcs_scale_policy is (
        PCSScalePolicy.CONSTANT_UNIT_COST_WITHIN_SOURCE_RANGE
    )
    assert contract.exact_pcs_multiplicity_curve_supported is False
    contract.validate_pcs_power_mw(5.0)
    contract.validate_pcs_power_mw(100.0)
    with pytest.raises(ValueError, match="5-100 MW"):
        contract.validate_pcs_power_mw(4.999)
    with pytest.raises(ValueError, match="5-100 MW"):
        contract.validate_pcs_power_mw(100.001)


def test_resolved_contract_builds_complete_fixed_capacity_bess_economics() -> None:
    from tes_bess_boundary.economics import (
        AnnualHorizonSpec,
        BESSCellCostCalibration,
        ProjectFinance,
    )
    from tes_bess_boundary.formal_bess_costs import (
        build_resolved_rahman_bess_join_contract,
    )

    economics = build_resolved_rahman_bess_join_contract().build_annual_economics(
        horizon=AnnualHorizonSpec(period_weights=(8784.0,)),
        finance=ProjectFinance(project_years=20, real_discount_rate=0.10),
        conversion=_formal_price_bridge(),
        pcs_power_mw=5.0,
        nominal_energy_mwh=20.0,
        reference_annual_ac_efc=365.0,
        ac_deliverable_fraction=0.8,
    )

    assert isinstance(economics.bess_cell_cost, BESSCellCostCalibration)
    assert economics.bess_cell_cost.degradation.cell_lifecycle.service_life_years == (
        pytest.approx(13.0)
    )
    assert economics.bess_variable_om_per_ac_discharge_mwh == pytest.approx(
        2.74 * 8.73826631502364
    )
    assert economics.non_cell_cost is not None
    quantities = economics.non_cell_cost.installed_quantities
    assert quantities["bess_pcs"] == pytest.approx(5.0)
    assert quantities["bess_bop"] == pytest.approx(5.0)
    assert quantities["bess_enclosure_foundation"] == pytest.approx(20.0)
    assert quantities["bess_energy_contingency"] == pytest.approx(20.0)
