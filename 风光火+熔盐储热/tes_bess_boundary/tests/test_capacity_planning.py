from __future__ import annotations

import pytest


pytestmark = pytest.mark.solver


def _assert_linear(model: object) -> None:
    from pyomo.environ import Constraint, Objective
    from pyomo.repn import generate_standard_repn

    for component_type in (Constraint, Objective):
        for item in model.component_data_objects(component_type, active=True):
            expression = item.body if component_type is Constraint else item.expr
            representation = generate_standard_repn(expression)
            assert representation.nonlinear_expr is None
            assert representation.quadratic_vars in (None, ())


def _bess_spec(*, cyclic: bool = False):
    from tes_bess_boundary.capacity_planning import (
        BESSPlanningBounds,
        BESSPlanningSpec,
    )

    return BESSPlanningSpec(
        bounds=BESSPlanningBounds(
            energy_capacity_upper_mwh=20.0,
            charge_power_upper_mw=10.0,
            discharge_power_upper_mw=10.0,
        ),
        soc_min=0.1,
        soc_max=0.9,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        initial_soc_fraction=0.9,
        minimum_discharge_duration_hours=2.0,
        maximum_discharge_duration_hours=24.0,
        cyclic=cyclic,
    )


def _tes_spec(*, cyclic: bool = False):
    from tes_bess_boundary.capacity_planning import TESPlanningBounds, TESPlanningSpec
    from tes_bess_boundary.components.molten_salt import MoltenSaltPhysics

    physics = MoltenSaltPhysics(
        salt_mass_t=1.0,
        ht_tank_capacity_t=1.0,
        mt_tank_capacity_t=1.0,
        lt_tank_capacity_t=1.0,
        specific_heat_mwh_per_tonne_k=0.0004,
        temperature_ht=565.0,
        temperature_mt=390.0,
        temperature_lt=230.0,
        electric_heater_efficiency=0.98,
        steam_to_ht_efficiency=0.95,
        steam_to_mt_efficiency=0.95,
        power_block_efficiency=0.4,
        heat_exchanger_efficiency=0.95,
    )
    bounds = TESPlanningBounds(
        salt_mass_upper_t=1_000.0,
        ht_tank_capacity_upper_t=1_000.0,
        mt_tank_capacity_upper_t=1_000.0,
        lt_tank_capacity_upper_t=1_000.0,
        electric_charge_input_upper_mw=100.0,
        steam_to_ht_input_upper_mw=100.0,
        steam_to_mt_input_upper_mw=100.0,
        electric_output_upper_mw=100.0,
        heat_output_upper_mw=100.0,
    )
    return TESPlanningSpec(
        physics_template=physics,
        bounds=bounds,
        initial_inventory_fractions=(1.0, 0.0, 0.0),
        minimum_service_duration_hours=2.0,
        maximum_service_duration_hours=24.0,
        cyclic=cyclic,
    )


def _public_portfolio(mode: str, *, acknowledged: bool = True):
    from tes_bess_boundary.public_tes_costs import build_public_tes_cost_portfolio

    return build_public_tes_cost_portfolio(
        mode,
        "base",
        acknowledge_author_assumptions=acknowledged,
    )


def test_endogenous_bess_is_linear_and_highs_sizes_required_service() -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import (
        BESSAnnualCapacityCost,
        add_endogenous_bess_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.bess = Block()
    add_endogenous_bess_dispatch(
        model.bess,
        model.periods,
        _bess_spec(),
        annual_capacity_cost=BESSAnnualCapacityCost(1.0, 1.0, 1.0),
    )
    model.service = Constraint(expr=model.bess.discharge_ac_mw[0] >= 1.0)
    model.objective = Objective(expr=model.bess.annual_capacity_cost_cny)
    _assert_linear(model)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.bess.discharge_power_capacity_mw) == pytest.approx(1.0)
    assert value(model.bess.energy_capacity_mwh) == pytest.approx(2.0 / (0.8 * 0.95))


def test_endogenous_bess_allows_zero_capacity_without_service() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import (
        BESSAnnualCapacityCost,
        add_endogenous_bess_dispatch,
    )
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.bess = Block()
    add_endogenous_bess_dispatch(
        model.bess,
        model.periods,
        _bess_spec(cyclic=True),
        annual_capacity_cost=BESSAnnualCapacityCost(1.0, 1.0, 1.0),
    )
    model.objective = Objective(expr=model.bess.annual_capacity_cost_cny)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.bess.energy_capacity_mwh) == pytest.approx(0.0)
    assert value(model.bess.charge_power_capacity_mw) == pytest.approx(0.0)
    assert value(model.bess.discharge_power_capacity_mw) == pytest.approx(0.0)


@pytest.mark.parametrize("mode", ["aggregate_storage", "component_ledger"])
def test_endogenous_tes_is_linear_and_accepts_each_public_cost_route(mode: str) -> None:
    from pyomo.environ import Block, ConcreteModel, Constraint, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import add_endogenous_tes_dispatch
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.tes = Block()
    spec = _tes_spec()
    add_endogenous_tes_dispatch(
        model.tes,
        model.periods,
        spec,
        cost_portfolio=_public_portfolio(mode),
    )
    model.service = Constraint(expr=model.tes.electric_output_mw[0] >= 1.0)
    model.objective = Objective(expr=model.tes.annual_capacity_cost_cny)
    _assert_linear(model)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.tes.electric_output_capacity_mw) == pytest.approx(1.0)
    assert value(model.tes.electric_output_mw[0]) == pytest.approx(1.0)
    service_hours = (
        spec.physics_template.power_block_efficiency
        * spec.physics_template.specific_heat_mwh_per_tonne_k
        * spec.physics_template.delta_ht_mt
        * value(model.tes.ht_service_salt_mass_t)
        / value(model.tes.electric_output_capacity_mw)
    )
    assert 2.0 - 1e-8 <= service_hours <= 24.0 + 1e-8
    assert value(model.tes.annual_capacity_cost_cny) > 0.0


def test_endogenous_tes_allows_zero_capacity_without_service() -> None:
    from pyomo.environ import Block, ConcreteModel, Objective, RangeSet, value

    from tes_bess_boundary.capacity_planning import add_endogenous_tes_dispatch
    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.periods = RangeSet(0, 1)
    model.tes = Block()
    add_endogenous_tes_dispatch(
        model.tes,
        model.periods,
        _tes_spec(cyclic=True),
        cost_portfolio=_public_portfolio("aggregate_storage"),
    )
    model.objective = Objective(expr=model.tes.annual_capacity_cost_cny)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.tes.salt_mass_t) == pytest.approx(0.0)
    assert value(model.tes.electric_output_capacity_mw) == pytest.approx(0.0)
    assert value(model.tes.heat_output_capacity_mw) == pytest.approx(0.0)


def test_endogenous_tes_rejects_unacknowledged_public_assumptions() -> None:
    from pyomo.environ import Block, ConcreteModel, RangeSet

    from tes_bess_boundary.capacity_planning import add_endogenous_tes_dispatch

    model = ConcreteModel()
    model.periods = RangeSet(0, 0)
    model.tes = Block()

    with pytest.raises(ValueError, match="explicitly acknowledged"):
        add_endogenous_tes_dispatch(
            model.tes,
            model.periods,
            _tes_spec(),
            cost_portfolio=_public_portfolio(
                "aggregate_storage",
                acknowledged=False,
            ),
        )
