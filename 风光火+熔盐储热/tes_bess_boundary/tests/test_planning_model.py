from __future__ import annotations

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
            name="planning_test_chp",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(50.0, 0.0),
                    CHPVertex(51.0, 0.0),
                    CHPVertex(50.0, 30.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(50.0, 10.0), CHPFuelPoint(51.0, 10.2)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )


def _bess_spec():
    from tes_bess_boundary.capacity_planning import (
        BESSPlanningBounds,
        BESSPlanningSpec,
    )

    return BESSPlanningSpec(
        bounds=BESSPlanningBounds(40.0, 10.0, 10.0),
        soc_min=0.1,
        soc_max=0.9,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc_fraction=0.5,
        cyclic=True,
    )


def _bess_economics():
    from tes_bess_boundary.economics import PriceBasisConversion, ProjectFinance
    from tes_bess_boundary.formal_bess_costs import (
        build_resolved_rahman_bess_join_contract,
    )

    return build_resolved_rahman_bess_join_contract().build_planning_economics(
        finance=ProjectFinance(project_years=20, real_discount_rate=0.10),
        conversion=PriceBasisConversion(
            source_currency="USD",
            source_price_base_year=2019,
            target_currency="CNY",
            target_price_base_year=2024,
            source_price_index=255.657,
            target_price_index=313.689,
            target_currency_per_source_currency=7.1217,
            price_index_series_id="BLS CUUR0000SA0 CPI-U",
            exchange_rate_series_id="NBS 2024 CNY per USD",
        ),
        reference_annual_ac_efc=365.0,
        ac_deliverable_fraction=0.8 * 0.95,
    )


def _tes_spec():
    from tes_bess_boundary.capacity_planning import TESPlanningBounds, TESPlanningSpec
    from tes_bess_boundary.components.molten_salt import MoltenSaltPhysics

    return TESPlanningSpec(
        physics_template=MoltenSaltPhysics(
            salt_mass_t=1.0,
            ht_tank_capacity_t=1.0,
            mt_tank_capacity_t=1.0,
            lt_tank_capacity_t=1.0,
            specific_heat_mwh_per_tonne_k=0.01,
            temperature_ht=3.0,
            temperature_mt=2.0,
            temperature_lt=1.0,
            electric_heater_efficiency=0.95,
            steam_to_ht_efficiency=0.95,
            steam_to_mt_efficiency=0.95,
            power_block_efficiency=0.4,
            heat_exchanger_efficiency=0.95,
        ),
        bounds=TESPlanningBounds(
            salt_mass_upper_t=1_000.0,
            ht_tank_capacity_upper_t=1_000.0,
            mt_tank_capacity_upper_t=1_000.0,
            lt_tank_capacity_upper_t=1_000.0,
            electric_charge_input_upper_mw=20.0,
            steam_to_ht_input_upper_mw=20.0,
            steam_to_mt_input_upper_mw=20.0,
            electric_output_upper_mw=20.0,
            heat_output_upper_mw=20.0,
        ),
        initial_inventory_fractions=(0.0, 0.0, 1.0),
        cyclic=True,
    )


def _tes_costs():
    from tes_bess_boundary.public_tes_costs import build_public_tes_cost_portfolio

    return build_public_tes_cost_portfolio(
        "aggregate_storage",
        "base",
        acknowledge_author_assumptions=True,
    )


def _case(architecture):
    from tes_bess_boundary.economics import AnnualHorizonSpec
    from tes_bess_boundary.model import Architecture, E0CTimeSeries, ValidationObjectiveSpec
    from tes_bess_boundary.planning_model import EndogenousCapacityCase

    includes_bess = architecture in (Architecture.BESS, Architecture.HYBRID)
    includes_tes = architecture in (Architecture.TES, Architecture.HYBRID)
    return EndogenousCapacityCase(
        architecture=architecture,
        timeseries=E0CTimeSeries(
            heat_demand_mw=(10.0, 10.0, 10.0, 10.0),
            wind_available_mw=(0.0, 10.0, 10.0, 0.0),
            pv_available_mw=(0.0, 0.0, 0.0, 0.0),
        ),
        chp_units=(_chp_spec(),),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=100.0,
        horizon=AnnualHorizonSpec((2_196.0,) * 4),
        bess=_bess_spec() if includes_bess else None,
        bess_economics=_bess_economics() if includes_bess else None,
        tes=_tes_spec() if includes_tes else None,
        tes_cost_portfolio=_tes_costs() if includes_tes else None,
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=800.0,
            curtailment_penalty_cny_per_mwh=0.0,
        ),
    )


@pytest.mark.parametrize(
    "architecture_name",
    ["no_storage", "bess", "tes", "hybrid"],
)
def test_full_endogenous_model_solves_each_architecture(architecture_name: str) -> None:
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import solve_endogenous_capacity

    result = solve_endogenous_capacity(_case(Architecture(architecture_name)))

    assert result.termination_condition == "optimal"
    assert result.annual_total_cost_cny >= 0.0
    assert result.objective_lower_bound_cny <= result.objective_upper_bound_cny + 1e-7
    assert result.relative_mip_gap <= 1e-8
    assert result.formal_project_tac_ready is False
    if architecture_name in {"bess", "hybrid"}:
        assert result.bess_common_pcs_power_capacity_mw is not None
    if architecture_name in {"tes", "hybrid"}:
        assert result.tes_public_cost_mode == "aggregate_storage"


def test_hybrid_full_model_is_linear_and_uses_both_certified_capacity_blocks() -> None:
    from pyomo.environ import Constraint, Objective, value
    from pyomo.repn import generate_standard_repn

    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model
    from tes_bess_boundary.solver import create_highs_solver

    model = build_endogenous_capacity_model(_case(Architecture.HYBRID))
    model.force_bess = Constraint(expr=model.bess.discharge_power_capacity_mw >= 1.0)
    model.force_tes_power = Constraint(expr=model.tes.electric_output_capacity_mw >= 1.0)
    model.force_tes_heat = Constraint(expr=model.tes.heat_output_capacity_mw >= 1.0)
    for component_type in (Constraint, Objective):
        for item in model.component_data_objects(component_type, active=True):
            expression = item.body if component_type is Constraint else item.expr
            representation = generate_standard_repn(expression)
            assert representation.nonlinear_expr is None
            assert representation.quadratic_vars in (None, ())

    solved = create_highs_solver().solve(model)

    assert str(solved.solver.termination_condition).lower() == "optimal"
    assert value(model.bess.pcs_power_capacity_mw) >= 5.0 - 1e-8
    assert value(model.tes.ht_service_salt_mass_t) > 0.0
    assert value(model.tes.mt_service_salt_mass_t) > 0.0
    assert value(model.tes.ht_rated_output[0].body) == pytest.approx(0.0)
    assert value(model.tes.mt_rated_output[0].body) == pytest.approx(0.0)


def test_d37_hybrid_model_shares_capacity_and_uses_two_cyclic_state_blocks() -> None:
    from dataclasses import replace

    from pyomo.environ import Constraint, Objective, value
    from pyomo.repn import generate_standard_repn

    from tes_bess_boundary.economics import (
        AnnualDispatchBlock,
        BlockAnnualHorizonSpec,
    )
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import build_endogenous_capacity_model

    block_case = replace(
        _case(Architecture.HYBRID),
        chp_terminal_online=(0,),
        horizon=BlockAnnualHorizonSpec(
            period_weights=(2_196.0,) * 4,
            dispatch_blocks=(
                AnnualDispatchBlock("first", (0, 1)),
                AnnualDispatchBlock("second", (2, 3)),
            ),
        ),
    )
    model = build_endogenous_capacity_model(block_case)

    assert len(model.bess.energy_capacity_mwh) == 1
    assert len(model.tes.salt_mass_t) == 1
    assert tuple(model.bess.states) == (0, 1, 2, 3, 4, 5)
    assert tuple(model.tes.states) == (0, 1, 2, 3, 4, 5)
    assert not hasattr(model.bess, "initial_energy")
    assert not hasattr(model.tes, "initial_ht")
    assert not hasattr(model.chp[0], "terminal_online")
    assert tuple(value(model.annual_period_weight[p]) for p in model.periods) == (
        2_196.0,
        2_196.0,
        2_196.0,
        2_196.0,
    )
    for component_type in (Constraint, Objective):
        for item in model.component_data_objects(component_type, active=True):
            expression = item.body if component_type is Constraint else item.expr
            representation = generate_standard_repn(expression)
            assert representation.nonlinear_expr is None
            assert representation.quadratic_vars in (None, ())


def test_full_endogenous_model_preserves_common_curtailment_and_pcc_services() -> None:
    from dataclasses import replace

    from tes_bess_boundary.model import (
        AnnualCurtailmentServiceSpec,
        AnnualPCCExportServiceSpec,
        Architecture,
    )
    from tes_bess_boundary.planning_model import solve_endogenous_capacity

    reference = solve_endogenous_capacity(_case(Architecture.NO_STORAGE))
    constrained = replace(
        _case(Architecture.BESS),
        curtailment_service=AnnualCurtailmentServiceSpec(
            service_id="planning-test-common-curtailment",
            maximum_curtailment_mwh=reference.weighted_curtailment_mwh + 1e-6,
        ),
        pcc_export_service=AnnualPCCExportServiceSpec(
            service_id="planning-test-common-pcc",
            target_export_mwh=reference.weighted_pcc_export_mwh,
        ),
    )

    result = solve_endogenous_capacity(constrained)

    assert result.weighted_curtailment_mwh <= (
        reference.weighted_curtailment_mwh + 1e-6 + 1e-7
    )
    assert result.weighted_pcc_export_mwh == pytest.approx(
        reference.weighted_pcc_export_mwh,
        abs=1e-7,
    )
    assert result.bess_energy_capacity_mwh is not None
    assert result.bess_energy_capacity_mwh >= 0.0


def test_complete_capacity_snapshot_fixes_every_storage_design_variable() -> None:
    from pyomo.environ import value

    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import (
        EndogenousCapacitySnapshot,
        build_endogenous_capacity_model,
        fix_endogenous_capacity_snapshot,
        solve_endogenous_capacity,
    )

    case = _case(Architecture.HYBRID)
    planned = solve_endogenous_capacity(case)
    snapshot = EndogenousCapacitySnapshot.from_result(planned)
    model = build_endogenous_capacity_model(case)

    fix_endogenous_capacity_snapshot(model, case, snapshot)

    fixed_variables = (
        model.bess.energy_capacity_mwh,
        model.bess.charge_power_capacity_mw,
        model.bess.discharge_power_capacity_mw,
        model.bess.pcs_power_capacity_mw,
        model.bess.installed,
        model.tes.salt_mass_t,
        model.tes.ht_tank_capacity_t,
        model.tes.mt_tank_capacity_t,
        model.tes.lt_tank_capacity_t,
        model.tes.ht_service_salt_mass_t,
        model.tes.mt_service_salt_mass_t,
        model.tes.electric_charge_input_capacity_mw,
        model.tes.steam_to_ht_input_capacity_mw,
        model.tes.steam_to_mt_input_capacity_mw,
        model.tes.electric_output_capacity_mw,
        model.tes.heat_output_capacity_mw,
    )
    assert all(variable.fixed for variable in fixed_variables)
    assert value(model.tes.ht_tank_capacity_t) == pytest.approx(
        planned.tes_ht_tank_capacity_t
    )

    replayed = solve_endogenous_capacity(case, fixed_capacity=snapshot)

    assert replayed.annual_total_cost_cny == pytest.approx(
        planned.annual_total_cost_cny,
        rel=1e-8,
        abs=1e-6,
    )
    replayed_snapshot = EndogenousCapacitySnapshot.from_result(replayed)
    assert replayed_snapshot.bess_energy_capacity_mwh == pytest.approx(
        snapshot.bess_energy_capacity_mwh
    )
    assert replayed_snapshot.bess_common_pcs_power_capacity_mw == pytest.approx(
        snapshot.bess_common_pcs_power_capacity_mw
    )
    assert replayed_snapshot.tes_salt_mass_t == pytest.approx(snapshot.tes_salt_mass_t)
    assert replayed_snapshot.tes_ht_tank_capacity_t == pytest.approx(
        snapshot.tes_ht_tank_capacity_t
    )
    assert replayed_snapshot.tes_heat_output_capacity_mw == pytest.approx(
        snapshot.tes_heat_output_capacity_mw
    )


def test_zero_fuel_objective_relaxation_preserves_minimum_curtailment() -> None:
    from dataclasses import replace

    from tes_bess_boundary.components.chp import FuelSegmentFormulation
    from tes_bess_boundary.model import Architecture, ValidationObjectiveSpec
    from tes_bess_boundary.planning_model import solve_endogenous_capacity

    case = replace(
        _case(Architecture.NO_STORAGE),
        objective=ValidationObjectiveSpec(
            coal_price_cny_per_tce=0.0,
            curtailment_penalty_cny_per_mwh=1.0,
        ),
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
    )

    exact = solve_endogenous_capacity(case)
    projected = solve_endogenous_capacity(
        case,
        relax_zero_cost_fuel_segments=True,
    )

    assert projected.weighted_curtailment_mwh == pytest.approx(
        exact.weighted_curtailment_mwh,
        abs=1e-7,
    )
    assert projected.binary_variable_count < exact.binary_variable_count


def test_fuel_segment_relaxation_rejects_a_fuel_cost_objective() -> None:
    from tes_bess_boundary.model import Architecture
    from tes_bess_boundary.planning_model import solve_endogenous_capacity

    with pytest.raises(ValueError, match="only at zero fuel cost"):
        solve_endogenous_capacity(
            _case(Architecture.NO_STORAGE),
            relax_zero_cost_fuel_segments=True,
        )
