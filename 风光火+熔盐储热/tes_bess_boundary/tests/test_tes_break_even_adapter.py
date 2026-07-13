"""Integration tests for the E0-D-17 annual-result adaptation seam."""

from __future__ import annotations

from dataclasses import replace

import pytest


pytestmark = [pytest.mark.solver, pytest.mark.integration]


def _chp_spec():
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        LowLoadFuelRule,
    )

    return CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="e0d17_synthetic_chp",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(10.0, 0.0),
                    CHPVertex(11.0, 0.0),
                    CHPVertex(10.0, 10.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.0,
        ),
        fuel_points=(
            CHPFuelPoint(10.0, 300.0),
            CHPFuelPoint(11.0, 300.0),
        ),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )


def _tes_spec():
    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
    )
    from tes_bess_boundary.model import TESFixedSpec, TESPortCaps

    return TESFixedSpec(
        physics=MoltenSaltPhysics(
            salt_mass_t=100.0,
            ht_tank_capacity_t=100.0,
            mt_tank_capacity_t=100.0,
            lt_tank_capacity_t=100.0,
            specific_heat_mwh_per_tonne_k=1.0,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=1.0,
            steam_to_ht_efficiency=1.0,
            steam_to_mt_efficiency=1.0,
            power_block_efficiency=1.0,
            heat_exchanger_efficiency=1.0,
        ),
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
        port_caps=TESPortCaps(
            electric_charge_input_mw=5.0,
            steam_to_ht_reference_input_mw=0.0,
            steam_to_mt_reference_input_mw=0.0,
            electric_output_mw=0.0,
            heat_output_mw=5.0,
        ),
        cyclic=True,
    )


def _annual_economics(*, with_tes_cost: bool = False):
    from tes_bess_boundary.economics import (
        AnnualEconomicsSpec,
        AnnualHorizonSpec,
        FixedCapacityNonCellCost,
        InstalledAssetQuantity,
        LifecycleAssetClass,
        LifecycleCostSpec,
        ProjectFinance,
        build_lifecycle_cost_portfolio,
    )

    horizon = AnnualHorizonSpec(period_weights=(2196.0,) * 4)
    if not with_tes_cost:
        return AnnualEconomicsSpec(horizon=horizon)
    portfolio = build_lifecycle_cost_portfolio(
        (
            LifecycleCostSpec(
                asset_id="synthetic_tes_fixed_om",
                capacity_unit="system",
                currency="CNY",
                price_base_year=2024,
                initial_cost_per_unit=0.0,
                service_life_years=20.0,
                fixed_om_per_unit_year=300.0,
                asset_class=LifecycleAssetClass.TES_COMPONENT,
            ),
        ),
        ProjectFinance(project_years=20, real_discount_rate=0.08),
    )
    return AnnualEconomicsSpec(
        horizon=horizon,
        non_cell_cost=FixedCapacityNonCellCost(
            portfolio=portfolio,
            quantities=(InstalledAssetQuantity("synthetic_tes_fixed_om", 1.0),),
        ),
    )


def _case(architecture, *, with_tes_cost: bool = False, penalty: float = 0.0):
    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
    )

    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    return E0CCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(5.0, 5.0, 5.0, 5.0),
            wind_available_mw=(20.0, 0.0, 20.0, 0.0),
            pv_available_mw=(0.0, 0.0, 0.0, 0.0),
        ),
        chp_units=(_chp_spec(),),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=15.0,
        tes=_tes_spec() if includes_tes else None,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=1.0,
            curtailment_penalty_cny_per_mwh=penalty,
        ),
        economics=_annual_economics(with_tes_cost=with_tes_cost),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id="natural_no_storage_curtailment",
            maximum_curtailment_mwh=65_880.0,
        ),
    )


def _adapter_spec():
    from tes_bess_boundary.tes_break_even_adapter import E0CBreakEvenAdapterSpec

    return E0CBreakEvenAdapterSpec(
        scenario_id="synthetic_e0d17",
        horizon_id="four_period_weighted_2024",
        known_cost_scope_id="fuel_and_verified_bess_only",
        omitted_non_tes_cost_terms=(
            "chp_variable_om",
            "carbon",
            "electricity_settlement",
        ),
    )


def test_annual_service_and_weighted_public_audits_are_enforced() -> None:
    from tes_bess_boundary.model import Architecture, solve_e0c

    result = solve_e0c(_case(Architecture.NO_STORAGE))

    assert result.annual_economics is not None
    annual = result.annual_economics
    assert annual.weighted_hours == pytest.approx(8_784.0)
    assert annual.weighted_renewable_available_mwh == pytest.approx(87_840.0)
    assert annual.weighted_curtailment_mwh == pytest.approx(65_880.0)
    assert annual.weighted_pcc_export_mwh == pytest.approx(109_800.0)
    assert annual.curtailment_service_id == "natural_no_storage_curtailment"
    assert annual.curtailment_ceiling_mwh == pytest.approx(65_880.0)


def test_penalty_free_incumbent_conditional_tie_break_preserves_cost_and_minimizes_curtailment() -> None:
    from tes_bess_boundary.model import Architecture, solve_e0c

    case = replace(
        _case(Architecture.NO_STORAGE),
        curtailment_service=None,
    )
    result = solve_e0c(
        case,
        lexicographic_minimize_curtailment=True,
    )

    assert result.annual_economics is not None
    assert result.lexicographic_curtailment_tie_break is True
    assert result.primary_cost_tolerance_cny is not None
    assert result.primary_cost_tolerance_cny > 0.0
    assert result.lexicographic_fixed_primary_integer_count is not None
    assert result.lexicographic_fixed_primary_integer_count > 0
    assert result.annual_economics.weighted_curtailment_mwh == pytest.approx(
        65_880.0
    )
    assert case.objective.curtailment_penalty_cny_per_mwh == 0.0


def test_e0d17_tes_slice_keeps_the_full_cascade_discharge_path() -> None:
    from tes_bess_boundary.e0d17_exploration import build_e0d17_tes_spec

    tes = build_e0d17_tes_spec()

    assert tes.port_caps.electric_charge_input_mw == pytest.approx(150.0)
    assert tes.port_caps.electric_output_mw == pytest.approx(150.0)
    assert tes.port_caps.heat_output_mw == pytest.approx(150.0)


def test_actual_e0c_pair_excludes_tes_ownership_and_remains_exploratory() -> None:
    from tes_bess_boundary.formal_tes_costs import (
        build_e0d15_tes_formal_cost_readiness,
    )
    from tes_bess_boundary.model import Architecture, solve_e0c
    from tes_bess_boundary.tes_break_even import TESBreakEvenClaimScope
    from tes_bess_boundary.tes_break_even_adapter import (
        compare_e0c_annual_break_even,
    )

    comparator_case = _case(Architecture.NO_STORAGE)
    candidate_case = _case(Architecture.TES, with_tes_cost=True)
    comparison = compare_e0c_annual_break_even(
        comparator_case,
        solve_e0c(comparator_case),
        candidate_case,
        solve_e0c(candidate_case),
        spec=_adapter_spec(),
        tes_readiness=build_e0d15_tes_formal_cost_readiness(),
    )

    assert comparison.candidate.excluded_tes_ownership_cost_cny_per_year == (
        pytest.approx(300.0)
    )
    assert comparison.candidate.outcome.known_cost.known_fixed_cost_cny == (
        pytest.approx(0.0)
    )
    assert comparison.candidate.outcome.known_cost.includes_tes_ownership_cost is False
    assert comparison.candidate.outcome.known_cost.non_tes_scope_complete is False
    assert comparison.break_even.claim_scope is (
        TESBreakEvenClaimScope.EXPLORATORY_THRESHOLD_ONLY
    )
    assert comparison.break_even.physical_delta.curtailment_reduction_mwh >= 0.0
    assert comparison.break_even.physical_delta.fuel_saving_tce >= 0.0
    assert comparison.break_even.maximum_tes_ownership_eac_cny_per_year >= 0.0


def test_adapter_rejects_penalties_missing_service_and_false_completeness() -> None:
    from tes_bess_boundary.model import Architecture, solve_e0c
    from tes_bess_boundary.tes_break_even_adapter import (
        E0CBreakEvenAdapterSpec,
        adapt_e0c_annual_outcome,
    )

    penalized = _case(Architecture.NO_STORAGE, penalty=1.0)
    with pytest.raises(ValueError, match="artificial curtailment penalties"):
        adapt_e0c_annual_outcome(
            penalized,
            solve_e0c(penalized),
            spec=_adapter_spec(),
        )

    without_service = replace(
        _case(Architecture.NO_STORAGE),
        curtailment_service=None,
    )
    with pytest.raises(ValueError, match="explicit curtailment service"):
        adapt_e0c_annual_outcome(
            without_service,
            solve_e0c(without_service),
            spec=_adapter_spec(),
        )

    with pytest.raises(ValueError, match="explicit non-empty tuple"):
        E0CBreakEvenAdapterSpec(
            scenario_id="synthetic_e0d17",
            horizon_id="four_period_weighted_2024",
            known_cost_scope_id="false_complete_scope",
            omitted_non_tes_cost_terms=(),
        )
