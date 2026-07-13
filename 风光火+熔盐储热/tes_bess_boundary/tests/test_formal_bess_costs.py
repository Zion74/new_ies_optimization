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
