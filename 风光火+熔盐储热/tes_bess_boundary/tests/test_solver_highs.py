from __future__ import annotations

import pytest


pytestmark = pytest.mark.solver


def test_highs_solves_a_binary_milp_and_reports_metadata() -> None:
    from tes_bess_boundary.solver import solve_highs_smoke

    result = solve_highs_smoke()

    assert result.solver_name == "appsi_highs"
    assert result.termination == "optimal"
    assert result.objective == pytest.approx(1.0)
    assert result.integer_value == pytest.approx(1.0)
    assert result.relative_gap == pytest.approx(0.0)
    assert result.runtime_seconds >= 0.0
    assert result.solver_version


def test_highs_repeated_solution_is_reproducible() -> None:
    from tes_bess_boundary.solver import solve_highs_smoke

    first = solve_highs_smoke()
    second = solve_highs_smoke()

    assert second.termination == first.termination
    assert second.objective == pytest.approx(first.objective, abs=1e-10)
    assert second.integer_value == pytest.approx(first.integer_value, abs=1e-10)


def test_highs_solves_a_unique_linear_program() -> None:
    from pyomo.environ import (
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        Var,
        value,
    )

    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.x = Var(domain=NonNegativeReals)
    model.y = Var(domain=NonNegativeReals)
    model.demand = Constraint(expr=model.x + model.y >= 1.0)
    model.objective = Objective(expr=model.x + 2.0 * model.y)

    results = create_highs_solver().solve(model)

    assert str(results.solver.termination_condition).lower() == "optimal"
    assert value(model.x) == pytest.approx(1.0)
    assert value(model.y) == pytest.approx(0.0)


def test_highs_reports_infeasible_without_loading_a_solution() -> None:
    from pyomo.environ import ConcreteModel, Constraint, Objective, Var

    from tes_bess_boundary.solver import create_highs_solver

    model = ConcreteModel()
    model.x = Var()
    model.lower = Constraint(expr=model.x >= 1.0)
    model.upper = Constraint(expr=model.x <= 0.0)
    model.objective = Objective(expr=model.x)

    results = create_highs_solver().solve(model, load_solutions=False)

    assert str(results.solver.termination_condition).lower() == "infeasible"
