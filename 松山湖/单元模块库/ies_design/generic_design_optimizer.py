from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Iterable

from generic_dispatch_model import GenericDispatchModel


class GenericDesignOptimizer:
    """Outer design optimizer facade for variable-dimensional generic scenarios."""

    def __init__(self, resolved: dict[str, Any]):
        self.resolved = resolved
        self.dispatch_model = GenericDispatchModel(resolved)
        self.capacity_space = self.dispatch_model.capacity_space

    def run_demo_search(
        self,
        levels: Iterable[float] | None = None,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Any]:
        levels = list(levels if levels is not None else [0.0, 0.5, 1.0])
        _validate_levels(levels)

        solutions = []
        for solution_id, level in enumerate(levels):
            vector = [
                lower + (upper - lower) * level
                for lower, upper in zip(self.capacity_space.lower_bounds, self.capacity_space.upper_bounds)
            ]
            solutions.append(self._evaluate_solution(
                solution_id=solution_id,
                vector=vector,
                level=level,
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
            ))

        return {
            "status": "build_only",
            "search_strategy": "demo_levels",
            "candidate_count": len(solutions),
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "capacity_variable_count": len(self.capacity_space.variables),
            "capacity_variable_names": self.capacity_space.names,
            "solutions": solutions,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
            "next_step": "replace demo levels with NSGA-II/DE candidates and solve full dispatch in GenericDispatchModel",
        }

    def run_capacity_search(
        self,
        candidate_count: int = 8,
        random_seed: int = 1,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Any]:
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")

        vectors = _capacity_search_vectors(
            lower_bounds=self.capacity_space.lower_bounds,
            upper_bounds=self.capacity_space.upper_bounds,
            candidate_count=candidate_count,
            random_seed=random_seed,
        )
        solutions = [
            self._evaluate_solution(
                solution_id=solution_id,
                vector=vector,
                level="",
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                search_strategy="random",
            )
            for solution_id, vector in enumerate(vectors)
        ]
        return {
            "status": "capacity_search",
            "search_strategy": "random",
            "candidate_count": len(solutions),
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "capacity_variable_count": len(self.capacity_space.variables),
            "capacity_variable_names": self.capacity_space.names,
            "solutions": solutions,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
            "next_step": "replace random candidate generation with NSGA-II/DE while reusing GenericDispatchModel.evaluate",
        }

    def run_de_search(
        self,
        population_size: int = 12,
        generations: int = 5,
        random_seed: int = 1,
        mutation_factor: float = 0.6,
        crossover_rate: float = 0.7,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Any]:
        if population_size < 4:
            raise ValueError("population_size must be at least 4 for differential evolution")
        if generations < 0:
            raise ValueError("generations must be non-negative")

        rng = random.Random(random_seed)
        lower_bounds = self.capacity_space.lower_bounds
        upper_bounds = self.capacity_space.upper_bounds
        population = _initial_de_population(lower_bounds, upper_bounds, population_size, rng)
        scores = [
            self._evaluate_vector_score(
                vector,
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
            )
            for vector in population
        ]

        for _generation in range(generations):
            for idx, current in enumerate(population):
                a, b, c = _sample_other_vectors(population, idx, rng)
                mutant = _clip_vector(
                    [
                        av + mutation_factor * (bv - cv)
                        for av, bv, cv in zip(a, b, c)
                    ],
                    lower_bounds,
                    upper_bounds,
                )
                trial = _crossover(current, mutant, crossover_rate, rng)
                trial_score = self._evaluate_vector_score(
                    trial,
                    project_root=project_root,
                    solve_electric_dispatch=solve_electric_dispatch,
                    electric_dispatch_scope=electric_dispatch_scope,
                    dispatch_periods=dispatch_periods,
                )
                if trial_score <= scores[idx]:
                    population[idx] = trial
                    scores[idx] = trial_score

        solutions = [
            self._evaluate_solution(
                solution_id=solution_id,
                vector=vector,
                level="",
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                search_strategy="differential_evolution",
            )
            for solution_id, vector in enumerate(population)
        ]
        best_solution = min(solutions, key=lambda item: item.get("total_objective", float("inf"))) if solutions else {}
        return {
            "status": "capacity_search",
            "search_strategy": "differential_evolution",
            "candidate_count": len(solutions),
            "population_size": population_size,
            "generation_count": generations,
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "capacity_variable_count": len(self.capacity_space.variables),
            "capacity_variable_names": self.capacity_space.names,
            "solutions": solutions,
            "best_solution": best_solution,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
            "next_step": "connect differential_evolution outputs to multi-objective NSGA-II/DE selection and full-year dispatch metrics",
        }

    def _evaluate_vector_score(
        self,
        vector: list[float],
        project_root: str | Path | None,
        solve_electric_dispatch: bool,
        electric_dispatch_scope: str,
        dispatch_periods: int,
    ) -> float:
        solution = self._evaluate_solution(
            solution_id=-1,
            vector=vector,
            level="",
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            search_strategy="differential_evolution",
        )
        return _solution_score(solution, solve_electric_dispatch)

    def _evaluate_solution(
        self,
        solution_id: int,
        vector: list[float],
        level: float | str,
        project_root: str | Path | None,
        solve_electric_dispatch: bool,
        electric_dispatch_scope: str,
        dispatch_periods: int,
        search_strategy: str = "demo_levels",
    ) -> dict[str, Any]:
        evaluation = self.dispatch_model.evaluate(
            vector,
            project_root=str(project_root) if project_root else None,
            solve_electric_dispatch=solve_electric_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
        )
        real_dispatch = evaluation.get("generic_model", {}).get("real_dispatch", {}) or {}
        dispatch_objective = _objective_value(real_dispatch)
        investment_cost = evaluation["investment_cost"]
        return {
            "solution_id": solution_id,
            "level": level,
            "search_strategy": search_strategy,
            "vector": vector,
            "investment_cost": investment_cost,
            "dispatch_objective": dispatch_objective,
            "total_objective": investment_cost + dispatch_objective,
            "dispatch_solved": bool(real_dispatch.get("dispatch_solved", evaluation["dispatch_solved"])),
            "capacity_assignment": evaluation["capacity_assignment"],
            "generic_model": evaluation.get("generic_model", {}),
            "status": evaluation["status"],
        }

    @classmethod
    def export_demo_search(
        cls,
        resolved: dict[str, Any],
        output_dir: str | Path,
        levels: Iterable[float] | None = None,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_demo_search(
            levels=levels,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
        }

    @classmethod
    def export_capacity_search(
        cls,
        resolved: dict[str, Any],
        output_dir: str | Path,
        candidate_count: int = 8,
        random_seed: int = 1,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_capacity_search(
            candidate_count=candidate_count,
            random_seed=random_seed,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
        }

    @classmethod
    def export_de_search(
        cls,
        resolved: dict[str, Any],
        output_dir: str | Path,
        population_size: int = 12,
        generations: int = 5,
        random_seed: int = 1,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_de_search(
            population_size=population_size,
            generations=generations,
            random_seed=random_seed,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
        }


def _validate_levels(levels: list[float]) -> None:
    if not levels:
        raise ValueError("at least one demo search level is required")
    for level in levels:
        if level < 0 or level > 1:
            raise ValueError(f"demo search level must be between 0 and 1, got {level}")


def _capacity_search_vectors(
    lower_bounds: list[float],
    upper_bounds: list[float],
    candidate_count: int,
    random_seed: int,
) -> list[list[float]]:
    rng = random.Random(random_seed)
    vectors: list[list[float]] = []
    if candidate_count >= 1:
        vectors.append(list(upper_bounds))
    while len(vectors) < candidate_count:
        vectors.append([
            lower + (upper - lower) * rng.random()
            for lower, upper in zip(lower_bounds, upper_bounds)
        ])
    return vectors


def _initial_de_population(
    lower_bounds: list[float],
    upper_bounds: list[float],
    population_size: int,
    rng: random.Random,
) -> list[list[float]]:
    population = [list(upper_bounds), list(lower_bounds)]
    while len(population) < population_size:
        population.append([
            lower + (upper - lower) * rng.random()
            for lower, upper in zip(lower_bounds, upper_bounds)
        ])
    return population[:population_size]


def _sample_other_vectors(
    population: list[list[float]],
    current_index: int,
    rng: random.Random,
) -> tuple[list[float], list[float], list[float]]:
    candidates = [idx for idx in range(len(population)) if idx != current_index]
    selected = rng.sample(candidates, 3)
    return population[selected[0]], population[selected[1]], population[selected[2]]


def _clip_vector(
    vector: list[float],
    lower_bounds: list[float],
    upper_bounds: list[float],
) -> list[float]:
    return [
        min(max(value, lower), upper)
        for value, lower, upper in zip(vector, lower_bounds, upper_bounds)
    ]


def _crossover(
    current: list[float],
    mutant: list[float],
    crossover_rate: float,
    rng: random.Random,
) -> list[float]:
    if not current:
        return []
    forced_index = rng.randrange(len(current))
    return [
        mutant[idx] if idx == forced_index or rng.random() < crossover_rate else current[idx]
        for idx in range(len(current))
    ]


def _solution_score(solution: dict[str, Any], solve_dispatch_requested: bool) -> float:
    if solve_dispatch_requested and not solution.get("dispatch_solved"):
        return 1e18 + float(solution.get("investment_cost", 0.0) or 0.0)
    return float(solution.get("total_objective", 0.0) or 0.0)


def _objective_value(dispatch: dict[str, Any]) -> float:
    if not dispatch.get("dispatch_solved"):
        return 0.0
    value = dispatch.get("objective_value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _write_solutions_csv(path: Path, result: dict[str, Any]) -> None:
    variable_names = result.get("capacity_variable_names", []) or []
    columns = [
        "solution_id",
        "level",
        "search_strategy",
        "status",
        "dispatch_solved",
        "investment_cost",
        "dispatch_objective",
        "total_objective",
        *variable_names,
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for solution in result.get("solutions", []):
            row = {
                "solution_id": solution.get("solution_id", ""),
                "level": solution.get("level", ""),
                "search_strategy": solution.get("search_strategy", ""),
                "status": solution.get("status", ""),
                "dispatch_solved": solution.get("dispatch_solved", ""),
                "investment_cost": solution.get("investment_cost", ""),
                "dispatch_objective": solution.get("dispatch_objective", ""),
                "total_objective": solution.get("total_objective", ""),
            }
            row.update(dict(zip(variable_names, solution.get("vector", []) or [])))
            writer.writerow(row)


def _build_design_report(result: dict[str, Any]) -> str:
    lines = [
        "# GenericDesignOptimizer 设计搜索报告",
        "",
        f"- 场景 ID: `{result.get('scenario_id', '')}`",
        f"- 当前状态: `{result.get('status', '')}`",
        f"- 搜索策略: `{result.get('search_strategy', '')}`",
        f"- 容量变量数量: {result.get('capacity_variable_count', 0)}",
        f"- 候选方案数量: {len(result.get('solutions', []) or [])}",
        "- 内层调度求解: 当前支持可选真实调度切片求解，完整冷热储能/氢/蒸汽调度尚未接入。",
        f"- 容量变量已应用到组件规格: {_all_solutions_capacity_applied(result)}",
        "",
        "## 容量变量",
        "",
    ]
    for name in result.get("capacity_variable_names", []) or []:
        lines.append(f"- `{name}`")

    lines.extend([
        "",
        "## 候选方案",
        "",
        "| ID | Level | Strategy | Status | Dispatch Solved | Investment Cost | Dispatch Objective | Total Objective |",
        "|---:|---:|---|---|---|---:|---:|---:|",
    ])
    for solution in result.get("solutions", []) or []:
        lines.append(
            f"| {solution.get('solution_id', '')} | {solution.get('level', '')} | "
            f"{solution.get('search_strategy', '')} | {solution.get('status', '')} | "
            f"{solution.get('dispatch_solved', '')} | {solution.get('investment_cost', '')} | "
            f"{solution.get('dispatch_objective', '')} | {solution.get('total_objective', '')} |"
        )

    lines.extend(["", "## 真实调度切片", ""])
    dispatch_rows = _dispatch_rows(result)
    if dispatch_rows:
        lines.extend([
            "| ID | Scope | Solved | Solver | Termination | Objective |",
            "|---:|---|---|---|---|---:|",
        ])
        for row in dispatch_rows:
            lines.append(
                f"| {row.get('solution_id', '')} | {row.get('scope', '')} | "
                f"{row.get('dispatch_solved', '')} | {row.get('solver', '')} | "
                f"{row.get('termination_condition', '')} | {row.get('objective_value', '')} |"
            )
    else:
        lines.append("- 未启用真实调度切片求解。")

    lines.extend(["", "## 构建缺口", ""])
    gaps = result.get("build_gaps", []) or []
    if gaps:
        lines.extend(f"- [{gap.get('category', '')}] {gap.get('target', '')}: {gap.get('message', '')}" for gap in gaps)
    else:
        lines.append("- 当前通用组件构建层未发现阻断性缺口。")

    lines.extend(["", "## 后续补齐", "", f"- {result.get('next_step', '')}"])
    return "\n".join(lines) + "\n"


def _all_solutions_capacity_applied(result: dict[str, Any]) -> bool:
    solutions = result.get("solutions", []) or []
    return bool(solutions) and all(
        solution.get("generic_model", {}).get("capacity_applied") is True
        for solution in solutions
    )


def _dispatch_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for solution in result.get("solutions", []) or []:
        dispatch = solution.get("generic_model", {}).get("real_dispatch", {}) or {}
        if dispatch.get("scope"):
            rows.append({"solution_id": solution.get("solution_id", ""), **dispatch})
    return rows
