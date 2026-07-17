"""Public-contract tests for E0-D-16 TES break-even accounting."""

from __future__ import annotations

from dataclasses import replace

import pytest


def _capacity_ledger():
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps
    from tes_bess_boundary.tes_cost_mapping import derive_tes_capacity_ledger

    tes = TESFixedSpec(
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
    return derive_tes_capacity_ledger(tes)


def _outcome(
    architecture,
    *,
    outcome_id: str,
    fuel_tce: float,
    curtailment_mwh: float,
    pcc_export_mwh: float,
    operating_cost_cny: float,
    known_fixed_cost_cny: float,
    scope_complete: bool = False,
):
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import (
        AnnualPhysicalOutcome,
        ComparableAnnualOutcome,
        KnownAnnualCostScope,
    )

    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    return ComparableAnnualOutcome(
        outcome_id=outcome_id,
        scenario_id="yangling_base",
        service_id="curtailment_ceiling_10pct",
        horizon_id="2024_weighted_8784h",
        architecture=architecture,
        service_curtailment_ceiling_mwh=1_000.0,
        physical=AnnualPhysicalOutcome(
            weighted_hours=8_784.0,
            fuel_tce=fuel_tce,
            curtailment_mwh=curtailment_mwh,
            renewable_available_mwh=10_000.0,
            pcc_export_mwh=pcc_export_mwh,
            tes_auxiliary_mwh_e=50.0 if includes_tes else 0.0,
        ),
        known_cost=KnownAnnualCostScope(
            scope_id="fuel_plus_verified_storage_ownership",
            operating_cost_cny=operating_cost_cny,
            known_fixed_cost_cny=known_fixed_cost_cny,
            non_tes_scope_complete=scope_complete,
        ),
        mip_gap=0.0,
        tes_capacity_ledger=_capacity_ledger() if includes_tes else None,
    )


def test_break_even_ceiling_separates_operating_and_known_fixed_value() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        build_e0d15_tes_formal_cost_readiness,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import (
        TESBreakEvenClaimScope,
        compare_tes_break_even,
    )
    from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis

    comparator = _outcome(
        Architecture.BESS,
        outcome_id="bess",
        fuel_tce=10_000.0,
        curtailment_mwh=1_000.0,
        pcc_export_mwh=5_000.0,
        operating_cost_cny=100_000_000.0,
        known_fixed_cost_cny=20_000_000.0,
    )
    candidate = _outcome(
        Architecture.TES,
        outcome_id="tes_zero_ownership",
        fuel_tce=9_000.0,
        curtailment_mwh=800.0,
        pcc_export_mwh=5_200.0,
        operating_cost_cny=85_000_000.0,
        known_fixed_cost_cny=5_000_000.0,
    )

    result = compare_tes_break_even(
        comparator,
        candidate,
        tes_readiness=build_e0d15_tes_formal_cost_readiness(),
    )

    assert result.operating_cost_saving_cny_per_year == pytest.approx(15_000_000.0)
    assert result.known_fixed_cost_advantage_cny_per_year == pytest.approx(
        15_000_000.0
    )
    assert result.maximum_tes_ownership_eac_cny_per_year == pytest.approx(
        30_000_000.0
    )
    assert result.physical_delta.fuel_saving_tce == pytest.approx(1_000.0)
    assert result.physical_delta.curtailment_reduction_mwh == pytest.approx(200.0)
    assert result.physical_delta.pcc_export_change_mwh == pytest.approx(200.0)
    assert result.physical_delta.tes_auxiliary_mwh_e == pytest.approx(50.0)
    assert result.claim_scope is TESBreakEvenClaimScope.EXPLORATORY_THRESHOLD_ONLY
    assert result.formal_tes_portfolio_ready is False
    assert result.viable_at_nonnegative_tes_ownership_cost is True
    assert result.headroom_at_tes_eac(25_000_000.0) == pytest.approx(5_000_000.0)
    assert result.normalization(
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH
    ).system_eac_ceiling_per_unit_year == pytest.approx(7_500.0)


def test_negative_ceiling_marks_tes_dominated_even_when_ownership_is_free() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        build_e0d15_tes_formal_cost_readiness,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import compare_tes_break_even

    comparator = _outcome(
        Architecture.NO_STORAGE,
        outcome_id="no_storage",
        fuel_tce=10_000.0,
        curtailment_mwh=1_000.0,
        pcc_export_mwh=5_000.0,
        operating_cost_cny=100.0,
        known_fixed_cost_cny=0.0,
    )
    candidate = _outcome(
        Architecture.TES,
        outcome_id="tes",
        fuel_tce=10_100.0,
        curtailment_mwh=900.0,
        pcc_export_mwh=4_900.0,
        operating_cost_cny=101.0,
        known_fixed_cost_cny=0.0,
    )

    result = compare_tes_break_even(
        comparator,
        candidate,
        tes_readiness=build_e0d15_tes_formal_cost_readiness(),
    )

    assert result.maximum_tes_ownership_eac_cny_per_year == pytest.approx(-1.0)
    assert result.viable_at_nonnegative_tes_ownership_cost is False
    assert result.headroom_at_tes_eac(0.0) == pytest.approx(-1.0)


def test_break_even_rejects_non_comparable_or_artificial_value() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        build_e0d15_tes_formal_cost_readiness,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import compare_tes_break_even

    comparator = _outcome(
        Architecture.BESS,
        outcome_id="bess",
        fuel_tce=10_000.0,
        curtailment_mwh=1_000.0,
        pcc_export_mwh=5_000.0,
        operating_cost_cny=100.0,
        known_fixed_cost_cny=20.0,
    )
    candidate = _outcome(
        Architecture.TES,
        outcome_id="tes",
        fuel_tce=9_000.0,
        curtailment_mwh=900.0,
        pcc_export_mwh=5_100.0,
        operating_cost_cny=90.0,
        known_fixed_cost_cny=0.0,
    )
    readiness = build_e0d15_tes_formal_cost_readiness()

    with pytest.raises(ValueError, match="same service_id"):
        compare_tes_break_even(
            comparator,
            replace(candidate, service_id="different_service"),
            tes_readiness=readiness,
        )
    with pytest.raises(ValueError, match="artificial curtailment penalties"):
        compare_tes_break_even(
            comparator,
            replace(
                candidate,
                known_cost=replace(
                    candidate.known_cost,
                    includes_artificial_penalties=True,
                ),
            ),
            tes_readiness=readiness,
        )
    with pytest.raises(ValueError, match="exclude all TES ownership costs"):
        compare_tes_break_even(
            comparator,
            replace(
                candidate,
                known_cost=replace(
                    candidate.known_cost,
                    includes_tes_ownership_cost=True,
                ),
            ),
            tes_readiness=readiness,
        )
    with pytest.raises(ValueError, match="optimal outcomes"):
        compare_tes_break_even(
            comparator,
            replace(candidate, solver_termination="max_time_limit"),
            tes_readiness=readiness,
        )


def test_tes_outcome_requires_real_inventory_and_a_discharge_port() -> None:
    from tes_bess_boundary.components.molten_salt import SaltInventory
    from tes_bess_boundary.model import Architecture, TESFixedSpec, TESPortCaps
    from tes_bess_boundary.tes_cost_mapping import derive_tes_capacity_ledger

    source = _outcome(
        Architecture.TES,
        outcome_id="tes",
        fuel_tce=9_000.0,
        curtailment_mwh=900.0,
        pcc_export_mwh=5_100.0,
        operating_cost_cny=90.0,
        known_fixed_cost_cny=0.0,
    )
    tes = _capacity_ledger().tes
    no_discharge = TESFixedSpec(
        physics=tes.physics,
        initial_inventory=SaltInventory(0.0, 0.0, tes.physics.salt_mass_t),
        port_caps=TESPortCaps(
            electric_charge_input_mw=tes.port_caps.electric_charge_input_mw,
            steam_to_ht_reference_input_mw=(
                tes.port_caps.steam_to_ht_reference_input_mw
            ),
            steam_to_mt_reference_input_mw=(
                tes.port_caps.steam_to_mt_reference_input_mw
            ),
            electric_output_mw=0.0,
            heat_output_mw=0.0,
        ),
    )

    with pytest.raises(ValueError, match="positive discharge-service port"):
        replace(
            source,
            tes_capacity_ledger=derive_tes_capacity_ledger(no_discharge),
        )


def test_system_normalizations_never_allocate_the_ceiling_to_components() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        build_e0d15_tes_formal_cost_readiness,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import compare_tes_break_even
    from tes_bess_boundary.tes_cost_mapping import TESCapacityBasis

    comparator = _outcome(
        Architecture.BESS,
        outcome_id="bess",
        fuel_tce=10_000.0,
        curtailment_mwh=1_000.0,
        pcc_export_mwh=5_000.0,
        operating_cost_cny=120.0,
        known_fixed_cost_cny=0.0,
    )
    candidate = _outcome(
        Architecture.HYBRID,
        outcome_id="hybrid_without_tes_ownership",
        fuel_tce=9_000.0,
        curtailment_mwh=900.0,
        pcc_export_mwh=5_100.0,
        operating_cost_cny=90.0,
        known_fixed_cost_cny=0.0,
    )

    result = compare_tes_break_even(
        comparator,
        candidate,
        tes_readiness=build_e0d15_tes_formal_cost_readiness(),
    )

    assert tuple(item.basis for item in result.normalizations) == (
        TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
        TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
        TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL,
        TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH,
    )
    for item in result.normalizations:
        assert item.quantity * item.system_eac_ceiling_per_unit_year == pytest.approx(
            result.maximum_tes_ownership_eac_cny_per_year
        )
    with pytest.raises(ValueError, match="unavailable"):
        result.normalization(TESCapacityBasis.SALT_INVENTORY_KG)


def test_auditable_claim_requires_complete_scope_and_formal_tes_readiness() -> None:
    from tes_bess_boundary.cost_evidence import (
        CostEvidenceAudit,
        CostEvidenceRecord,
        CostEvidenceUse,
        CostSourceProvenance,
        PriceBaseStatus,
        TechnologyBoundaryFit,
        VenueEvidenceTier,
    )
    from tes_bess_boundary.formal_tes_costs import (
        TESFormalCostAccount,
        TESFormalCostReadinessAudit,
        TESFormalCostRequirement,
        TESFormalEvidenceRequest,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.tes_break_even import (
        TESBreakEvenClaimScope,
        compare_tes_break_even,
    )

    evidence = CostEvidenceRecord(
        evidence_id="synthetic_formal_tes",
        source_locator="10.1016/j.apenergy.2026.000001",
        venue_tier=VenueEvidenceTier.CORE_PEER_REVIEWED,
        price_base_status=PriceBaseStatus.EXPLICIT,
        currency="CNY",
        price_base_year=2024,
        capacity_denominator="component_specific",
        technology_fit=TechnologyBoundaryFit.DIRECT,
        provenance=CostSourceProvenance.AUTHOR_BOTTOM_UP_OR_NORMALIZED,
        allowed_use=CostEvidenceUse.FORMAL_CANDIDATE,
        note="Synthetic gate-only record.",
    )
    readiness = TESFormalCostReadinessAudit(
        evidence_audit=CostEvidenceAudit((evidence,)),
        requirements=tuple(
            TESFormalCostRequirement(
                account,
                (
                    TESFormalEvidenceRequest(
                        evidence.evidence_id,
                        "component_specific",
                    ),
                ),
            )
            for account in TESFormalCostAccount
        ),
        aggregate_anchor_ids=(),
    )
    comparator = _outcome(
        Architecture.BESS,
        outcome_id="bess",
        fuel_tce=10_000.0,
        curtailment_mwh=1_000.0,
        pcc_export_mwh=5_000.0,
        operating_cost_cny=120.0,
        known_fixed_cost_cny=0.0,
        scope_complete=True,
    )
    candidate = _outcome(
        Architecture.TES,
        outcome_id="tes",
        fuel_tce=9_000.0,
        curtailment_mwh=900.0,
        pcc_export_mwh=5_100.0,
        operating_cost_cny=90.0,
        known_fixed_cost_cny=0.0,
        scope_complete=True,
    )

    result = compare_tes_break_even(
        comparator,
        candidate,
        tes_readiness=readiness,
    )

    assert readiness.formal_portfolio_ready is True
    assert result.claim_scope is TESBreakEvenClaimScope.AUDITABLE_NON_TES_COST_CEILING
    assert result.formal_tes_portfolio_ready is True
    assert result.non_tes_cost_scope_complete is True
