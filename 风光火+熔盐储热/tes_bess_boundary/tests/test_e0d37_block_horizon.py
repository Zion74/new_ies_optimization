from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = [pytest.mark.solver, pytest.mark.integration]


def _canonical_periods_csv() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d36_representative_weeks"
        / "e0d36_representative_periods.csv"
    )


def _price_basis_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "数据采集" / "e0d4_price_basis_2024"


def _bess_spec():
    from tes_bess_boundary.capacity_planning import (
        BESSPlanningBounds,
        BESSPlanningSpec,
    )

    return BESSPlanningSpec(
        bounds=BESSPlanningBounds(20.0, 10.0, 10.0),
        soc_min=0.1,
        soc_max=0.9,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc_fraction=0.5,
        cyclic=True,
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
            salt_mass_upper_t=200.0,
            ht_tank_capacity_upper_t=200.0,
            mt_tank_capacity_upper_t=200.0,
            lt_tank_capacity_upper_t=200.0,
            electric_charge_input_upper_mw=20.0,
            steam_to_ht_input_upper_mw=20.0,
            steam_to_mt_input_upper_mw=20.0,
            electric_output_upper_mw=20.0,
            heat_output_upper_mw=20.0,
        ),
        initial_inventory_fractions=(0.0, 0.0, 1.0),
        cyclic=True,
    )


def test_canonical_d36_artifact_builds_seven_block_annual_horizon() -> None:
    from tes_bess_boundary.e0d37_block_horizon import load_e0d37_block_horizon

    loaded = load_e0d37_block_horizon(_canonical_periods_csv())

    assert loaded.timeseries.period_count == 1_080
    assert tuple(len(block.periods) for block in loaded.horizon.dispatch_blocks) == (
        168,
        168,
        168,
        168,
        168,
        168,
        72,
    )
    assert loaded.block_ids == (
        "representative_week_04",
        "representative_week_05",
        "representative_week_08",
        "representative_week_29",
        "representative_week_39",
        "representative_week_48",
        "year_end_tail",
    )
    assert loaded.horizon.period_weights[-72:-48] == (0.0,) * 24
    assert loaded.horizon.period_weights[-48:] == (1.0,) * 48
    assert loaded.horizon.weighted_hours(dt_hours=1.0) == pytest.approx(8_784.0)


def test_formal_hybrid_boundary_build_is_linear_without_invoking_solver() -> None:
    from tes_bess_boundary.e0d37_structural_audit import (
        build_e0d37_structural_audit,
    )

    audit, runtime_seconds = build_e0d37_structural_audit(
        _canonical_periods_csv(),
        _price_basis_dir(),
    )

    assert audit["audit"]["passed"] is True
    assert audit["solver_invoked"] is False
    assert audit["state_audit"]["bess_state_nodes"] == 1_087
    assert audit["state_audit"]["tes_state_nodes"] == 1_087
    assert audit["linearity_audit"]["nonlinear_component_count"] == 0
    assert runtime_seconds > 0.0


def test_block_horizon_rejects_invalid_partition_and_hidden_terminal_warmup() -> None:
    from tes_bess_boundary.economics import (
        AnnualDispatchBlock,
        BlockAnnualHorizonSpec,
    )

    with pytest.raises(ValueError, match="exact partition"):
        BlockAnnualHorizonSpec(
            period_weights=(4_392.0, 4_392.0),
            dispatch_blocks=(AnnualDispatchBlock("gap", (1,)),),
        )
    with pytest.raises(ValueError, match="warm-up periods must precede"):
        BlockAnnualHorizonSpec(
            period_weights=(8_784.0, 0.0),
            dispatch_blocks=(AnnualDispatchBlock("hidden-terminal", (0, 1)),),
        )
    with pytest.raises(ValueError, match="must contain a scored period"):
        BlockAnnualHorizonSpec(
            period_weights=(0.0, 8_784.0),
            dispatch_blocks=(
                AnnualDispatchBlock("zero-only", (0,)),
                AnnualDispatchBlock("scored", (1,)),
            ),
        )
    horizon = BlockAnnualHorizonSpec(
        period_weights=(0.0, 8_784.0),
        dispatch_blocks=(AnnualDispatchBlock("warmup-and-scored", (0, 1)),),
    )
    horizon.validate_time_grid(period_count=2, dt_hours=1.0)
    with pytest.raises(ValueError, match="8784 annual hours"):
        BlockAnnualHorizonSpec(
            period_weights=(1.0,),
            dispatch_blocks=(AnnualDispatchBlock("wrong-year", (0,)),),
        ).validate_time_grid(period_count=1, dt_hours=1.0)


def test_bess_uses_shared_capacity_but_independent_cyclic_block_states() -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import (
        BESSAnnualCapacityCost,
        add_endogenous_bess_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 3)
    model.bess = Block()
    add_endogenous_bess_dispatch(
        model.bess,
        model.periods,
        _bess_spec(),
        annual_capacity_cost=BESSAnnualCapacityCost(1.0, 1.0, 1.0),
        cyclic_period_blocks=((0, 1), (2, 3)),
    )
    model.capacity = Constraint(expr=model.bess.energy_capacity_mwh == 10.0)
    model.first_block_initial = Constraint(expr=model.bess.energy_mwh[0] == 2.0)
    model.second_block_initial = Constraint(expr=model.bess.energy_mwh[3] == 8.0)
    for period in model.periods:
        model.bess.charge_ac_mw[period].fix(0.0)
        model.bess.discharge_ac_mw[period].fix(0.0)
    model.objective = Objective(expr=model.bess.annual_capacity_cost_cny)

    solved = create_highs_solver().solve(model)

    assert str(solved.solver.termination_condition).lower() == "optimal"
    assert len(model.bess.energy_capacity_mwh) == 1
    assert value(model.bess.energy_mwh[0]) == pytest.approx(2.0)
    assert value(model.bess.energy_mwh[2]) == pytest.approx(2.0)
    assert value(model.bess.energy_mwh[3]) == pytest.approx(8.0)
    assert value(model.bess.energy_mwh[5]) == pytest.approx(8.0)


def test_tes_uses_shared_salt_but_independent_three_inventory_cycles() -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import add_endogenous_tes_dispatch
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.tes = Block()
    add_endogenous_tes_dispatch(
        model.tes,
        model.periods,
        _tes_spec(),
        certify_rated_discharge=False,
        cyclic_period_blocks=((0,), (1,)),
    )
    model.salt = Constraint(expr=model.tes.salt_mass_t == 100.0)
    model.block_0_ht = Constraint(expr=model.tes.ht_mass_t[0] == 20.0)
    model.block_0_mt = Constraint(expr=model.tes.mt_mass_t[0] == 30.0)
    model.block_1_ht = Constraint(expr=model.tes.ht_mass_t[2] == 60.0)
    model.block_1_mt = Constraint(expr=model.tes.mt_mass_t[2] == 10.0)
    for period in model.periods:
        model.tes.electric_lt_to_ht[period].fix(0.0)
        model.tes.steam_lt_to_ht[period].fix(0.0)
        model.tes.steam_lt_to_mt[period].fix(0.0)
        model.tes.power_ht_to_mt[period].fix(0.0)
        model.tes.heat_mt_to_lt[period].fix(0.0)
    model.objective = Objective(expr=model.tes.salt_mass_t)

    solved = create_highs_solver().solve(model)

    assert str(solved.solver.termination_condition).lower() == "optimal"
    for start, end in ((0, 1), (2, 3)):
        assert value(model.tes.ht_mass_t[end]) == pytest.approx(
            value(model.tes.ht_mass_t[start])
        )
        assert value(model.tes.mt_mass_t[end]) == pytest.approx(
            value(model.tes.mt_mass_t[start])
        )
        assert value(model.tes.lt_mass_t[end]) == pytest.approx(
            value(model.tes.lt_mass_t[start])
        )
        assert sum(
            value(inventory[end])
            for inventory in (
                model.tes.ht_mass_t,
                model.tes.mt_mass_t,
                model.tes.lt_mass_t,
            )
        ) == pytest.approx(100.0)
    assert value(model.tes.ht_mass_t[0]) != pytest.approx(
        value(model.tes.ht_mass_t[2])
    )


def test_chp_first_period_transition_and_ramp_reference_same_block_tail() -> None:
    from pyomo.core.expr.visitor import identify_variables
    from pyomo.environ import Block, ConcreteModel, RangeSet

    from tes_bess_boundary.components.chp import (
        CHPCommitmentSpec,
        CHPFeasibleRegion,
        CHPFuelPoint,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        LowLoadFuelRule,
        add_chp_unit_commitment,
    )

    spec = CHPCommitmentSpec(
        unit=CHPUnitSpec(
            name="d37_chp",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(50.0, 0.0),
                    CHPVertex(110.0, 0.0),
                    CHPVertex(50.0, 10.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(50.0, 10.0), CHPFuelPoint(110.0, 20.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
        normal_ramp_mw_per_min=1.0 / 60.0,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 3)
    model.chp = Block()
    add_chp_unit_commitment(
        model.chp,
        model.periods,
        spec,
        initial_online=0,
        cyclic_period_blocks=((0, 1), (2, 3)),
    )

    def component_indices(expression: object, local_name: str) -> set[int]:
        return {
            int(variable.index())
            for variable in identify_variables(expression)
            if variable.parent_component().local_name == local_name
        }

    assert component_indices(model.chp.commitment_transition[0].body, "online") == {
        0,
        1,
    }
    assert component_indices(model.chp.commitment_transition[2].body, "online") == {
        2,
        3,
    }
    assert component_indices(model.chp.normal_ramp_up[0].body, "power_gross") == {
        0,
        1,
    }
    assert component_indices(model.chp.normal_ramp_up[2].body, "power_gross") == {
        2,
        3,
    }
    assert tuple(model.chp.ramp_periods) == (0, 1, 2, 3)
