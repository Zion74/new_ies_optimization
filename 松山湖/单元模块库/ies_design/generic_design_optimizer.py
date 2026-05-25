from __future__ import annotations

from typing import Any, Iterable

from generic_dispatch_model import GenericDispatchModel


class GenericDesignOptimizer:
    """Outer design optimizer facade for variable-dimensional generic scenarios.

    The current implementation performs a deterministic smoke-search over the
    dynamic capacity space. It is intentionally algorithm-light so a real
    NSGA-II/DE backend can replace the candidate generator later.
    """

    def __init__(self, resolved: dict[str, Any]):
        self.resolved = resolved
        self.dispatch_model = GenericDispatchModel(resolved)
        self.capacity_space = self.dispatch_model.capacity_space

    def run_demo_search(self, levels: Iterable[float] | None = None) -> dict[str, Any]:
        levels = list(levels if levels is not None else [0.0, 0.5, 1.0])
        _validate_levels(levels)

        solutions = []
        for solution_id, level in enumerate(levels):
            vector = [
                lower + (upper - lower) * level
                for lower, upper in zip(self.capacity_space.lower_bounds, self.capacity_space.upper_bounds)
            ]
            evaluation = self.dispatch_model.evaluate(vector)
            solutions.append({
                "solution_id": solution_id,
                "level": level,
                "vector": vector,
                "investment_cost": evaluation["investment_cost"],
                "dispatch_solved": evaluation["dispatch_solved"],
                "capacity_assignment": evaluation["capacity_assignment"],
                "status": evaluation["status"],
            })

        return {
            "status": "build_only",
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "capacity_variable_count": len(self.capacity_space.variables),
            "capacity_variable_names": self.capacity_space.names,
            "solutions": solutions,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
            "next_step": "replace demo levels with NSGA-II/DE candidates and solve dispatch in GenericDispatchModel",
        }


def _validate_levels(levels: list[float]) -> None:
    if not levels:
        raise ValueError("at least one demo search level is required")
    for level in levels:
        if level < 0 or level > 1:
            raise ValueError(f"demo search level must be between 0 and 1, got {level}")
