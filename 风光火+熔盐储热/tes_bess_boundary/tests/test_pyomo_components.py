from __future__ import annotations

import pytest


pytestmark = [pytest.mark.solver, pytest.mark.integration]


def _assert_model_is_linear(model: object) -> None:
    from pyomo.core import Constraint, Objective
    from pyomo.repn.standard_repn import generate_standard_repn

    for constraint in model.component_data_objects(Constraint, active=True):
        representation = generate_standard_repn(constraint.body)
        assert representation.is_linear(), constraint.name
    for objective in model.component_data_objects(Objective, active=True):
        representation = generate_standard_repn(objective.expr)
        assert representation.is_linear(), objective.name


def test_chp_pyomo_block_reproduces_table_power_floor() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.chp import (
        CHPFeasibleRegion,
        CHPUnitSpec,
        CHPVertex,
        HeatBasis,
        add_chp_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.chp = Block()
    spec = CHPUnitSpec(
        name="synthetic_resolved_unit",
        feasible_region=CHPFeasibleRegion(
            (
                CHPVertex(98.0, 0.0),
                CHPVertex(350.0, 0.0),
                CHPVertex(286.0, 438.0),
                CHPVertex(98.0, 83.0),
            )
        ),
        heat_basis=HeatBasis.USEFUL,
        auxiliary_rate=0.04601,
    )
    add_chp_dispatch(model.chp, model.periods, spec)
    model.chp.online[0].fix(1)
    model.chp.heat[0].fix(200.0)
    model.objective = Objective(expr=model.chp.power_gross[0])

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.chp.power_gross[0]) == pytest.approx(159.960563, abs=1e-6)
    _assert_model_is_linear(model)


def test_chp_exact_adjacent_segment_fuel_is_independent_of_heat_weights() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.chp import (
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )
    from tes_bess_boundary.solver import create_highs_solver

    unit_1, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.LINEAR_TOTAL_FLOW_EXTRAPOLATION
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 2)
    model.chp = Block()
    add_chp_unit_commitment(model.chp, model.periods, unit_1)
    fixed_points = ((140.0, 0.0), (175.0, 0.0), (175.0, 100.0))
    for period, (power, heat) in enumerate(fixed_points):
        model.chp.online[period].fix(1)
        model.chp.power_gross[period].fix(power)
        model.chp.heat[period].fix(heat)
    model.objective = Objective(
        expr=sum(model.chp.fuel_tce_per_hour[period] for period in model.periods)
    )

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    exact_140 = value(model.chp.fuel_tce_per_hour[0])
    assert exact_140 == pytest.approx(49.57077879027101)
    assert exact_140 != pytest.approx(47.244945576, abs=1e-6)
    assert value(model.chp.fuel_tce_per_hour[1]) == pytest.approx(54.96777437863549)
    assert value(model.chp.fuel_tce_per_hour[2]) == pytest.approx(54.96777437863549)
    assert value(model.chp.transition_proxy_cost) == 0.0
    assert model.chp.vertex_weight is not model.chp.fuel_segment_fraction
    _assert_model_is_linear(model)


def test_chp_commitment_transitions_allow_unresolved_startup_shutdown_ramps() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.chp import (
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )
    from tes_bess_boundary.solver import create_highs_solver

    unit_1, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.RAISE_MIN_POWER_TO_105
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 2)
    model.chp = Block()
    add_chp_unit_commitment(
        model.chp,
        model.periods,
        unit_1,
        time_step_hours=1.0 / 60.0,
        initial_online=0,
        cycle_event_cost_proxy_cny=unit_1.unresolved_cycle_event_cost_cny,
    )
    for period, (online, power) in enumerate(((0, 0.0), (1, 350.0), (0, 0.0))):
        model.chp.online[period].fix(online)
        model.chp.power_gross[period].fix(power)
        model.chp.heat[period].fix(0.0)
    model.objective = Objective(expr=model.chp.transition_proxy_cost)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert tuple(value(model.chp.startup[t]) for t in model.periods) == (0.0, 1.0, 0.0)
    assert tuple(value(model.chp.shutdown[t]) for t in model.periods) == (0.0, 0.0, 1.0)
    assert value(model.chp.transition_proxy_cost) == 300_000.0
    assert value(model.chp.power_gross[0]) == 0.0
    assert value(model.chp.heat[0]) == 0.0
    assert value(model.chp.fuel_tce_per_hour[0]) == 0.0
    assert not hasattr(model.chp, "minimum_up_time")
    assert not hasattr(model.chp, "minimum_down_time")
    _assert_model_is_linear(model)


def test_chp_normal_ramp_applies_only_between_two_online_periods() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet

    from tes_bess_boundary.components.chp import (
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )
    from tes_bess_boundary.solver import create_highs_solver

    unit_1, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.RAISE_MIN_POWER_TO_105
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.chp = Block()
    add_chp_unit_commitment(
        model.chp,
        model.periods,
        unit_1,
        time_step_hours=1.0 / 60.0,
        initial_online=1,
    )
    for period, power in enumerate((105.0, 120.0)):
        model.chp.online[period].fix(1)
        model.chp.power_gross[period].fix(power)
        model.chp.heat[period].fix(0.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model, load_solutions=False)

    assert str(results.solver.termination_condition).lower() == "infeasible"


def test_chp_commitment_rejects_unordered_pyomo_period_set() -> None:
    from pyomo.environ import Block, ConcreteModel, Set

    from tes_bess_boundary.components.chp import (
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )

    unit_1, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.RAISE_MIN_POWER_TO_105
    )
    model = ConcreteModel()
    model.periods = Set(initialize=(0, 1), ordered=False)
    model.chp = Block()

    with pytest.raises(ValueError, match="ordered"):
        add_chp_unit_commitment(model.chp, model.periods, unit_1)


def test_chp_commitment_without_ramp_evidence_omits_ramp_constraints() -> None:
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
            name="synthetic_without_ramp_evidence",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(100.0, 0.0),
                    CHPVertex(140.0, 0.0),
                    CHPVertex(120.0, 40.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(100.0, 350.0), CHPFuelPoint(140.0, 330.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.chp = Block()

    add_chp_unit_commitment(model.chp, model.periods, spec)

    assert not hasattr(model.chp, "normal_ramp_up")
    assert not hasattr(model.chp, "normal_ramp_down")
    assert not hasattr(model.chp, "ramp_periods")


@pytest.mark.parametrize(
    "kwargs",
    (
        {"time_step_hours": float("nan")},
        {"cycle_event_cost_proxy_cny": float("inf")},
    ),
)
def test_chp_commitment_rejects_non_finite_model_inputs(
    kwargs: dict[str, float],
) -> None:
    from pyomo.environ import Block, ConcreteModel, RangeSet

    from tes_bess_boundary.components.chp import (
        LowLoadFuelRule,
        add_chp_unit_commitment,
        yangling_chp_specs,
    )

    unit_1, _ = yangling_chp_specs(
        low_load_fuel_rule=LowLoadFuelRule.RAISE_MIN_POWER_TO_105
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.chp = Block()

    with pytest.raises(ValueError, match="finite"):
        add_chp_unit_commitment(model.chp, model.periods, unit_1, **kwargs)


def test_chp_fuel_contract_is_validated_before_block_construction() -> None:
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
            name="short_curve_must_fail_before_modeling",
            feasible_region=CHPFeasibleRegion(
                (
                    CHPVertex(98.0, 0.0),
                    CHPVertex(350.0, 0.0),
                    CHPVertex(286.0, 438.0),
                )
            ),
            heat_basis=HeatBasis.USEFUL,
            auxiliary_rate=0.05,
        ),
        fuel_points=(CHPFuelPoint(105.0, 400.0), CHPFuelPoint(140.0, 350.0)),
        low_load_fuel_rule=LowLoadFuelRule.CLAMP_30_PERCENT_RATE,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.chp = Block()

    with pytest.raises(ValueError, match="cover.*maximum"):
        add_chp_unit_commitment(model.chp, model.periods, spec)

    assert not hasattr(model.chp, "online")


def test_bess_pyomo_block_closes_an_ac_round_trip() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.bess import BESSPhysics, add_bess_dispatch
    from tes_bess_boundary.solver import create_highs_solver

    physics = BESSPhysics(
        energy_capacity_mwh=100.0,
        charge_power_mw=20.0,
        discharge_power_mw=20.0,
        soc_min=0.10,
        soc_max=0.90,
        charge_efficiency=0.95,
        discharge_efficiency=0.90,
        hourly_loss=0.0,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.bess = Block()
    add_bess_dispatch(
        model.bess,
        model.periods,
        physics,
        initial_energy_mwh=10.0,
        cyclic=True,
    )
    model.bess.charge_ac[0].fix(10.0)
    model.bess.discharge_ac[0].fix(0.0)
    model.bess.charge_ac[1].fix(0.0)
    model.bess.discharge_ac[1].fix(8.55)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.bess.energy[1]) == pytest.approx(19.5)
    assert value(model.bess.energy[2]) == pytest.approx(10.0)
    _assert_model_is_linear(model)


def test_molten_salt_pyomo_block_reuses_salt_for_power_then_heat() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(10.0, 0.0, 90.0),
        cyclic=False,
    )
    flow_names = (
        "electric_lt_to_ht",
        "steam_lt_to_ht",
        "steam_lt_to_mt",
        "power_ht_to_mt",
        "heat_mt_to_lt",
    )
    for name in flow_names:
        flow = getattr(model.salt, name)
        flow[0].fix(10.0 if name == "power_ht_to_mt" else 0.0)
        flow[1].fix(10.0 if name == "heat_mt_to_lt" else 0.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.salt.ht_mass[1]) == pytest.approx(0.0)
    assert value(model.salt.mt_mass[1]) == pytest.approx(10.0)
    assert value(model.salt.lt_mass[2]) == pytest.approx(100.0)
    assert value(model.salt.electric_output[0]) == pytest.approx(5.0)
    assert value(model.salt.heat_output[1]) == pytest.approx(8.0)
    assert not model.salt.loss_ht_to_mt[0].is_variable_type()
    assert not model.salt.loss_mt_to_lt[0].is_variable_type()
    assert value(model.salt.loss_ht_to_mt[0]) == pytest.approx(0.0)
    assert value(model.salt.loss_mt_to_lt[0]) == pytest.approx(0.0)
    _assert_model_is_linear(model)


def test_molten_salt_pyomo_block_rejects_zero_net_full_cycle() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(10.0, 0.0, 90.0),
    )
    model.salt.electric_lt_to_ht[0].fix(10.0)
    model.salt.steam_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_mt[0].fix(0.0)
    model.salt.power_ht_to_mt[0].fix(10.0)
    model.salt.heat_mt_to_lt[0].fix(10.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model, load_solutions=False)

    assert str(results.solver.termination_condition).lower() == "infeasible"


def test_molten_salt_rejects_direct_mt_charge_and_heat_discharge_loop() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
    )
    model.salt.electric_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_mt[0].fix(10.0)
    model.salt.power_ht_to_mt[0].fix(0.0)
    model.salt.heat_mt_to_lt[0].fix(10.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model, load_solutions=False)

    assert str(results.solver.termination_condition).lower() == "infeasible"


def test_molten_salt_allows_ht_charging_while_mt_supplies_heat() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(0.0, 10.0, 90.0),
    )
    model.salt.electric_lt_to_ht[0].fix(10.0)
    model.salt.steam_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_mt[0].fix(0.0)
    model.salt.power_ht_to_mt[0].fix(0.0)
    model.salt.heat_mt_to_lt[0].fix(10.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.salt.ht_mass[1]) == pytest.approx(10.0)
    assert value(model.salt.mt_mass[1]) == pytest.approx(0.0)
    assert value(model.salt.lt_mass[1]) == pytest.approx(90.0)


def test_molten_salt_allows_power_then_heat_cascade_in_one_period() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(10.0, 0.0, 90.0),
    )
    model.salt.electric_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_ht[0].fix(0.0)
    model.salt.steam_lt_to_mt[0].fix(0.0)
    model.salt.power_ht_to_mt[0].fix(10.0)
    model.salt.heat_mt_to_lt[0].fix(10.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.salt.ht_mass[1]) == pytest.approx(0.0)
    assert value(model.salt.mt_mass[1]) == pytest.approx(0.0)
    assert value(model.salt.lt_mass[1]) == pytest.approx(100.0)
    assert value(model.salt.electric_output[0]) == pytest.approx(5.0)
    assert value(model.salt.heat_output[0]) == pytest.approx(8.0)


def test_molten_salt_pyomo_charge_flows_require_input_energy() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

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
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.96,
        power_block_efficiency=0.5,
        heat_exchanger_efficiency=0.8,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(0.0, 0.0, 100.0),
    )
    model.salt.electric_lt_to_ht[0].fix(10.0)
    model.salt.steam_lt_to_ht[0].fix(10.0)
    model.salt.steam_lt_to_mt[0].fix(10.0)
    model.salt.power_ht_to_mt[0].fix(0.0)
    model.salt.heat_mt_to_lt[0].fix(0.0)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.salt.electric_charge_input[0]) == pytest.approx(20.0 / 0.9)
    assert value(model.salt.steam_to_ht_input[0]) == pytest.approx(20.0 / 0.95)
    assert value(model.salt.steam_to_mt_input[0]) == pytest.approx(10.0 / 0.96)
    _assert_model_is_linear(model)


def test_molten_salt_inventory_loss_tracing_and_pump_auxiliary_are_explicit() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.components.molten_salt import (
        MoltenSaltPhysics,
        SaltInventory,
        add_molten_salt_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver
    from tes_bess_boundary.tes_loss_auxiliary import (
        LossCompensationMode,
        TESLossAuxiliarySpec,
        TESParameterIdentity,
        TESPumpAuxiliarySpec,
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
        electric_heater_efficiency=1.0,
        steam_to_ht_efficiency=1.0,
        steam_to_mt_efficiency=1.0,
        power_block_efficiency=1.0,
        heat_exchanger_efficiency=1.0,
    )
    loss_auxiliary = TESLossAuxiliarySpec(
        ht_standing_loss_fraction_per_hour=0.10,
        mt_standing_loss_fraction_per_hour=0.20,
        ht_loss_compensation_fraction=0.50,
        mt_loss_compensation_fraction=0.25,
        tracing_heater_efficiency=0.50,
        pump=TESPumpAuxiliarySpec(1.0, 2.0, 3.0, 4.0, 5.0),
        compensation_mode=LossCompensationMode.FIXED_FRACTION,
        parameter_identity=TESParameterIdentity.AUTHOR_SENSITIVITY,
        parameter_source_id="author:e0d9_synthetic_gold",
        evidence_source_ids=("doi:10.1016/j.enconman.2022.116362",),
        reference_ambient_temperature_c=0.0,
    )
    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.salt = Block()
    add_molten_salt_dispatch(
        model.salt,
        model.periods,
        physics,
        initial_inventory=SaltInventory(10.0, 20.0, 70.0),
        loss_auxiliary=loss_auxiliary,
        cyclic=False,
    )
    fixed_flows = {
        "electric_lt_to_ht": 0.0,
        "steam_lt_to_ht": 0.0,
        "steam_lt_to_mt": 0.0,
        "power_ht_to_mt": 4.0,
        "heat_mt_to_lt": 5.0,
    }
    for name, flow in fixed_flows.items():
        getattr(model.salt, name)[0].fix(flow)
    model.objective = Objective(expr=0.0)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.salt.raw_loss_ht_to_mt[0]) == pytest.approx(1.0)
    assert value(model.salt.raw_loss_mt_to_lt[0]) == pytest.approx(4.0)
    assert value(model.salt.loss_ht_to_mt[0]) == pytest.approx(0.5)
    assert value(model.salt.loss_mt_to_lt[0]) == pytest.approx(3.0)
    assert value(model.salt.tracing_auxiliary[0]) == pytest.approx(3.0)
    assert value(model.salt.pump_auxiliary[0]) == pytest.approx(0.041)
    assert value(model.salt.auxiliary_power[0]) == pytest.approx(3.041)
    assert value(model.salt.ht_mass[1]) == pytest.approx(5.5)
    assert value(model.salt.mt_mass[1]) == pytest.approx(16.5)
    assert value(model.salt.lt_mass[1]) == pytest.approx(78.0)
    _assert_model_is_linear(model)
