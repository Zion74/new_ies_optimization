from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest


def _portfolio(mode: str, scenario: str = "base", *, acknowledged: bool = True):
    from tes_bess_boundary.public_tes_costs import build_public_tes_cost_portfolio

    return build_public_tes_cost_portfolio(
        mode,
        scenario,
        acknowledge_author_assumptions=acknowledged,
    )


@pytest.mark.parametrize("mode", ["aggregate_storage", "component_ledger"])
def test_public_portfolio_covers_each_formal_account_exactly_once(mode: str) -> None:
    from tes_bess_boundary.formal_tes_costs import TESFormalCostAccount

    portfolio = _portfolio(mode)
    counts = Counter(
        account
        for item in portfolio.items
        for account in item.covered_accounts
    )
    counts.update(portfolio.lifecycle_policy.covered_accounts)

    assert set(counts) == set(TESFormalCostAccount)
    assert set(counts.values()) == {1}
    assert portfolio.public_sensitivity_ready
    assert not portfolio.formal_project_eligible


def test_aggregate_and_component_storage_routes_are_mutually_exclusive() -> None:
    from tes_bess_boundary.formal_tes_costs import TESFormalCostAccount
    from tes_bess_boundary.tes_cost_mapping import TESComponent

    aggregate = _portfolio("aggregate_storage")
    component = _portfolio("component_ledger")
    aggregate_components = {item.component for item in aggregate.items}
    component_components = {item.component for item in component.items}

    assert TESComponent.SALT not in aggregate_components
    assert TESComponent.CIRCULATION not in aggregate_components
    aggregate_package = next(
        item
        for item in aggregate.items
        if item.component is TESComponent.STORAGE_TANK_SYSTEM
    )
    assert aggregate_package.covered_accounts == frozenset(
        {
            TESFormalCostAccount.SALT_INVENTORY,
            TESFormalCostAccount.STORAGE_VESSELS,
            TESFormalCostAccount.SALT_CIRCULATION,
        }
    )

    assert TESComponent.SALT in component_components
    assert TESComponent.CIRCULATION in component_components
    assert not any(len(item.covered_accounts) > 1 for item in component.items)


def test_public_portfolio_requires_explicit_author_acknowledgement() -> None:
    portfolio = _portfolio("aggregate_storage", acknowledged=False)

    assert portfolio.assumed_price_year_count > 0
    assert portfolio.proxy_account_count > 0
    assert not portfolio.public_sensitivity_ready
    assert not portfolio.formal_project_eligible


def test_default_price_snapshot_resolves_a_registered_manifest() -> None:
    from tes_bess_boundary.public_tes_costs import default_price_basis_snapshot_path

    assert (Path(default_price_basis_snapshot_path()) / "manifest.json").is_file()


@pytest.mark.parametrize("mode", ["aggregate_storage", "component_ledger"])
def test_all_journal_cost_sources_meet_energy_quality_floor(mode: str) -> None:
    from tes_bess_boundary.public_tes_costs import (
        ENERGY_CURRENT_IMPACT_FACTOR,
        PublicEvidenceQuality,
    )

    portfolio = _portfolio(mode)
    journal_items = tuple(
        item
        for item in portfolio.items
        if item.evidence_quality is PublicEvidenceQuality.ENERGY_PLUS_JOURNAL
    )

    assert journal_items
    assert all(
        item.current_impact_factor is not None
        and item.current_impact_factor >= ENERGY_CURRENT_IMPACT_FACTOR
        for item in journal_items
    )
    assert not any("energies" in item.venue.lower() for item in portfolio.items)
    assert not any("10.3390/en" in item.source_locator for item in portfolio.items)


@pytest.mark.parametrize("mode", ["aggregate_storage", "component_ledger"])
def test_public_coefficients_convert_to_finite_cny2024_values(mode: str) -> None:
    portfolio = _portfolio(mode)
    coefficients = portfolio.annualized_coefficients()

    assert len(coefficients) == len(portfolio.items)
    assert all(
        coefficient.total_eac_cny2024_per_unit_year >= 0.0
        for coefficient in coefficients
    )
    assert any(
        coefficient.total_eac_cny2024_per_unit_year > 0.0
        for coefficient in coefficients
    )
    reuse = next(
        coefficient
        for coefficient in coefficients
        if coefficient.item.asset_id == "existing_turbine_reuse_boundary"
    )
    assert reuse.total_eac_cny2024_per_unit_year == 0.0


def test_aggregate_package_does_not_receive_project_additions_twice() -> None:
    portfolio = _portfolio("aggregate_storage")
    aggregate = next(
        coefficient
        for coefficient in portfolio.annualized_coefficients()
        if coefficient.item.asset_id == "dlr_two_tank_solar_salt_package"
    )

    assert not aggregate.item.apply_project_addition_multiplier
    assert aggregate.installed_cost_cny2024_per_unit == pytest.approx(
        aggregate.direct_cost_cny2024_per_unit
    )


@pytest.mark.parametrize("mode", ["aggregate_storage", "component_ledger"])
def test_low_base_high_costs_are_ordered_for_one_quantity_vector(mode: str) -> None:
    from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis

    quantities = {basis: 1.0 for basis in TESCapacityBasis}
    totals = [
        _portfolio(mode, scenario).total_annual_cost_cny2024(quantities)
        for scenario in ("low", "base", "high")
    ]

    assert totals[0] < totals[1] < totals[2]


def test_public_portfolio_rejects_missing_quantity_basis() -> None:
    portfolio = _portfolio("aggregate_storage")

    with pytest.raises(ValueError, match="missing public TES quantity"):
        portfolio.total_annual_cost_cny2024({})
