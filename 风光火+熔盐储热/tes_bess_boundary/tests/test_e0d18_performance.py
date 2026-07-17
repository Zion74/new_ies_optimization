from __future__ import annotations

import pytest


@pytest.mark.solver
def test_logarithmic_chp_fuel_encoding_is_exact_and_uses_fewer_binaries() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, Var, value

    from tes_bess_boundary.components.chp import (
        FuelSegmentFormulation,
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )
    from tes_bess_boundary.solver import create_highs_solver

    spec, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )

    def solved(formulation: FuelSegmentFormulation) -> tuple[float, int]:
        model = ConcreteModel()
        model.periods = RangeSet(0, 0)
        model.chp = Block()
        add_chp_unit_commitment(
            model.chp,
            model.periods,
            spec,
            initial_online=1,
            fuel_segment_formulation=formulation,
        )
        model.chp.online[0].fix(1)
        model.chp.power_gross[0].fix(160.0)
        model.chp.heat[0].fix(0.0)
        model.objective = Objective(expr=model.chp.fuel_tce_per_hour[0])
        result = create_highs_solver().solve(model)
        assert str(result.solver.termination_condition).lower() == "optimal"
        binary_count = sum(
            variable.is_binary() and not variable.fixed
            for variable in model.component_data_objects(Var, active=True)
        )
        return float(value(model.chp.fuel_tce_per_hour[0])), binary_count

    one_hot_fuel, one_hot_binary = solved(FuelSegmentFormulation.ONE_HOT)
    logarithmic_fuel, logarithmic_binary = solved(
        FuelSegmentFormulation.LOGARITHMIC
    )

    assert logarithmic_fuel == pytest.approx(one_hot_fuel, abs=1e-10)
    assert logarithmic_binary < one_hot_binary


def test_transition_envelope_makes_continuous_startup_shutdown_exact() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.chp import (
        CommitmentTransitionFormulation,
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )
    from tes_bess_boundary.solver import create_highs_solver

    spec, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 2)
    model.chp = Block()
    add_chp_unit_commitment(
        model.chp,
        model.periods,
        spec,
        initial_online=0,
        transition_formulation=(
            CommitmentTransitionFormulation.CONTINUOUS_ENVELOPE
        ),
    )
    for period, online in enumerate((0, 1, 0)):
        model.chp.online[period].fix(online)
    model.objective = Objective(expr=0.0)

    result = create_highs_solver().solve(model)

    assert str(result.solver.termination_condition).lower() == "optimal"
    assert not model.chp.startup[1].is_binary()
    assert tuple(value(model.chp.startup[t]) for t in model.periods) == (0.0, 1.0, 0.0)
    assert tuple(value(model.chp.shutdown[t]) for t in model.periods) == (0.0, 0.0, 1.0)


def test_tes_path_bounds_tighten_modes_and_fix_a_zero_capacity_path() -> None:
    from pyomo.environ import Block, ConcreteModel, RangeSet

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltFlowBounds,
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )

    physics = MoltenSaltPhysics(
        salt_mass_t=100.0,
        ht_tank_capacity_t=100.0,
        mt_tank_capacity_t=100.0,
        lt_tank_capacity_t=100.0,
        specific_heat_mwh_per_tonne_k=1.0,
        temperature_ht=3.0,
        temperature_mt=2.0,
        temperature_lt=1.0,
        electric_heater_efficiency=0.9,
        steam_to_ht_efficiency=0.9,
        steam_to_mt_efficiency=0.9,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    bounds = MoltenSaltFlowBounds(2.0, 0.0, 0.0, 3.0, 4.0)
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.tes = Block()
    add_molten_salt_dispatch(
        model.tes,
        model.periods,
        physics,
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
        path_flow_bounds=bounds,
    )

    assert model.tes.electric_lt_to_ht[0].ub == pytest.approx(2.0)
    assert model.tes.power_ht_to_mt[0].ub == pytest.approx(3.0)
    assert model.tes.heat_mt_to_lt[0].ub == pytest.approx(4.0)
    assert not model.tes.ht_receiving_mode[0].fixed
    assert model.tes.mt_direct_charge_mode[0].fixed
    assert model.tes.mt_direct_charge_mode[0].value == 0


@pytest.mark.solver
def test_e0c_result_exposes_primary_primal_and_dual_bounds() -> None:
    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        FuelSegmentFormulation,
        HeatBasis,
        LowLoadFuelRule,
    )
    from tes_bess_boundary.economics import AnnualEconomicsSpec, AnnualHorizonSpec
    from tes_bess_boundary.model import (
        Architecture,
        E0CCase,
        E0CTimeSeries,
        ValidationObjectiveSpec,
        solve_e0c,
    )

    unit = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="bounds_fixture",
            feasible_region=CHPFeasibleRegion(
                (CHPVertex(10.0, 0.0), CHPVertex(20.0, 0.0), CHPVertex(15.0, 10.0))
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.0,
        ),
        fuel_points=(CHPFuelPoint(10.0, 300.0), CHPFuelPoint(20.0, 300.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    case = E0CCase(
        architecture=Architecture.NO_STORAGE,
        timeseries=E0CTimeSeries((5.0,), (0.0,), (0.0,)),
        chp_units=(unit,),
        chp_initial_online=(1,),
        chp_terminal_online=(1,),
        pcc_export_capacity_mw=20.0,
        objective=ValidationObjectiveSpec(coal_price_cny_per_tce=800.0),
        economics=AnnualEconomicsSpec(AnnualHorizonSpec((8_784.0,))),
        chp_fuel_segment_formulation=FuelSegmentFormulation.LOGARITHMIC,
    )

    result = solve_e0c(case)

    assert result.primary_objective_lower_bound == pytest.approx(result.objective_value)
    assert result.primary_objective_upper_bound == pytest.approx(result.objective_value)
    assert result.primary_cost_mip_gap == pytest.approx(0.0)
