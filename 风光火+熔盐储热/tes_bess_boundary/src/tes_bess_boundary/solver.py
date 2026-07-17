"""Deterministic HiGHS configuration and E0 solver smoke test."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True)
class SolverSmokeResult:
    solver_name: str
    solver_version: str
    termination: str
    objective: float
    integer_value: float
    relative_gap: float
    runtime_seconds: float


def create_highs_solver(
    *,
    threads: int = 1,
    random_seed: int = 0,
    mip_rel_gap: float = 0.0,
) -> object:
    """Create the only supported solver with deterministic E0 defaults."""

    from pyomo.environ import SolverFactory

    if threads < 1:
        raise ValueError("threads must be at least one")
    if mip_rel_gap < 0:
        raise ValueError("mip_rel_gap must be non-negative")
    solver = SolverFactory("appsi_highs")
    if not solver.available(exception_flag=False):
        raise RuntimeError("appsi_highs is unavailable; no fallback solver is permitted")
    solver.options["threads"] = threads
    solver.options["random_seed"] = random_seed
    solver.options["mip_rel_gap"] = mip_rel_gap
    return solver


def solve_highs_smoke() -> SolverSmokeResult:
    """Solve a unique binary MILP with appsi_highs and return auditable metadata."""

    import highspy
    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        Objective,
        Var,
        minimize,
        value,
    )

    model = ConcreteModel()
    model.x = Var(domain=Binary)
    model.require_one = Constraint(expr=model.x >= 1)
    model.objective = Objective(expr=model.x, sense=minimize)

    solver = create_highs_solver()

    started = perf_counter()
    results = solver.solve(model, tee=False)
    runtime = perf_counter() - started
    termination = str(results.solver.termination_condition).lower()
    if termination != "optimal":
        raise RuntimeError(f"HiGHS smoke model did not solve optimally: {termination}")
    lower_bound = float(results.problem.lower_bound)
    upper_bound = float(results.problem.upper_bound)
    relative_gap = abs(upper_bound - lower_bound) / max(abs(upper_bound), 1e-12)

    return SolverSmokeResult(
        solver_name="appsi_highs",
        solver_version=highspy.Highs().version(),
        termination=termination,
        objective=float(value(model.objective)),
        integer_value=float(value(model.x)),
        relative_gap=relative_gap,
        runtime_seconds=runtime,
    )
