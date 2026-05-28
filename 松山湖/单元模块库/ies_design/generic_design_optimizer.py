from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Iterable

from generic_capacity_space import GenericCapacitySpace
from generic_dispatch_model import GenericDispatchModel
from generic_energy_hub_inputs import GenericEnergyHubInputs


class GenericDesignOptimizer:
    """Outer design optimizer facade for variable-dimensional generic scenarios."""

    def __init__(self, resolved: dict[str, Any]):
        self.resolved = resolved
        self.dispatch_model = GenericDispatchModel(resolved)
        self.capacity_space = self.dispatch_model.capacity_space

    def _common_result_fields(self, capacity_space: GenericCapacitySpace | None = None) -> dict[str, Any]:
        capacity_space = capacity_space or self.capacity_space
        summary = self.dispatch_model.model_spec.get("conversion_type_summary", {}) or {}
        return {
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "conversion_type_count": summary.get("type_count", 0),
            "conversion_type_summary": summary,
            "capacity_variable_count": len(capacity_space.variables),
            "capacity_variable_names": capacity_space.names,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
        }

    def _capacity_space_for_run(
        self,
        project_root: str | Path | None,
        solve_generic_dispatch: bool,
        dispatch_periods: int,
        dispatch_month: int,
        accept_default_bounds: bool,
    ) -> GenericCapacitySpace:
        if not solve_generic_dispatch or not accept_default_bounds or not project_root:
            return self.capacity_space
        dispatch_spec = GenericEnergyHubInputs.build_dispatch_spec(
            self.resolved,
            project_root=project_root,
            month=dispatch_month,
            periods=dispatch_periods,
            capacity_assignment={},
            accept_default_bounds=True,
        )
        return GenericCapacitySpace.from_dispatch_spec(dispatch_spec)

    def run_demo_search(
        self,
        levels: Iterable[float] | None = None,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        levels = list(levels if levels is not None else [0.0, 0.5, 1.0])
        _validate_levels(levels)
        capacity_space = self._capacity_space_for_run(
            project_root,
            solve_generic_dispatch,
            dispatch_periods,
            dispatch_month,
            accept_default_bounds,
        )

        solutions = []
        for solution_id, level in enumerate(levels):
            vector = [
                lower + (upper - lower) * level
                for lower, upper in zip(capacity_space.lower_bounds, capacity_space.upper_bounds)
            ]
            solutions.append(self._evaluate_solution(
                solution_id=solution_id,
                vector=vector,
                level=level,
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                solve_generic_dispatch=solve_generic_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                dispatch_month=dispatch_month,
                accept_default_bounds=accept_default_bounds,
                capacity_space=capacity_space,
            ))

        return {
            **self._common_result_fields(capacity_space),
            "status": "build_only",
            "search_strategy": "demo_levels",
            "candidate_count": len(solutions),
            "solutions": solutions,
            "next_step": "replace demo levels with NSGA-II/DE candidates and solve full dispatch in GenericDispatchModel",
        }

    def run_capacity_search(
        self,
        candidate_count: int = 8,
        random_seed: int = 1,
        project_root: str | Path | None = None,
        solve_electric_dispatch: bool = False,
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
        capacity_space = self._capacity_space_for_run(
            project_root,
            solve_generic_dispatch,
            dispatch_periods,
            dispatch_month,
            accept_default_bounds,
        )

        vectors = _capacity_search_vectors(
            lower_bounds=capacity_space.lower_bounds,
            upper_bounds=capacity_space.upper_bounds,
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
                solve_generic_dispatch=solve_generic_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                dispatch_month=dispatch_month,
                accept_default_bounds=accept_default_bounds,
                capacity_space=capacity_space,
                search_strategy="random",
            )
            for solution_id, vector in enumerate(vectors)
        ]
        return {
            **self._common_result_fields(capacity_space),
            "status": "capacity_search",
            "search_strategy": "random",
            "candidate_count": len(solutions),
            "solutions": solutions,
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
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Any]:
        if population_size < 4:
            raise ValueError("population_size must be at least 4 for differential evolution")
        if generations < 0:
            raise ValueError("generations must be non-negative")

        capacity_space = self._capacity_space_for_run(
            project_root,
            solve_generic_dispatch,
            dispatch_periods,
            dispatch_month,
            accept_default_bounds,
        )
        rng = random.Random(random_seed)
        lower_bounds = capacity_space.lower_bounds
        upper_bounds = capacity_space.upper_bounds
        population = _initial_de_population(lower_bounds, upper_bounds, population_size, rng)
        scores = [
            self._evaluate_vector_score(
                vector,
                project_root=project_root,
                solve_electric_dispatch=solve_electric_dispatch,
                solve_generic_dispatch=solve_generic_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                dispatch_month=dispatch_month,
                accept_default_bounds=accept_default_bounds,
                capacity_space=capacity_space,
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
                    solve_generic_dispatch=solve_generic_dispatch,
                    electric_dispatch_scope=electric_dispatch_scope,
                    dispatch_periods=dispatch_periods,
                    dispatch_month=dispatch_month,
                    accept_default_bounds=accept_default_bounds,
                    capacity_space=capacity_space,
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
                solve_generic_dispatch=solve_generic_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
                dispatch_month=dispatch_month,
                accept_default_bounds=accept_default_bounds,
                capacity_space=capacity_space,
                search_strategy="differential_evolution",
            )
            for solution_id, vector in enumerate(population)
        ]
        best_solution = _select_best_solution(
            solutions,
            solve_dispatch_requested=solve_electric_dispatch or solve_generic_dispatch,
        )
        return {
            **self._common_result_fields(capacity_space),
            "status": "capacity_search",
            "search_strategy": "differential_evolution",
            "candidate_count": len(solutions),
            "population_size": population_size,
            "generation_count": generations,
            "solutions": solutions,
            "best_solution": best_solution,
            "next_step": "connect differential_evolution outputs to multi-objective NSGA-II/DE selection and full-year dispatch metrics",
        }

    def _evaluate_vector_score(
        self,
        vector: list[float],
        project_root: str | Path | None,
        solve_electric_dispatch: bool,
        solve_generic_dispatch: bool,
        electric_dispatch_scope: str,
        dispatch_periods: int,
        dispatch_month: int,
        accept_default_bounds: bool,
        capacity_space: GenericCapacitySpace | None = None,
    ) -> float:
        solution = self._evaluate_solution(
            solution_id=-1,
            vector=vector,
            level="",
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            solve_generic_dispatch=solve_generic_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            dispatch_month=dispatch_month,
            accept_default_bounds=accept_default_bounds,
            capacity_space=capacity_space,
            search_strategy="differential_evolution",
        )
        return _solution_score(solution, solve_electric_dispatch or solve_generic_dispatch)

    def _evaluate_solution(
        self,
        solution_id: int,
        vector: list[float],
        level: float | str,
        project_root: str | Path | None,
        solve_electric_dispatch: bool,
        solve_generic_dispatch: bool,
        electric_dispatch_scope: str,
        dispatch_periods: int,
        dispatch_month: int,
        accept_default_bounds: bool,
        capacity_space: GenericCapacitySpace | None = None,
        search_strategy: str = "demo_levels",
    ) -> dict[str, Any]:
        evaluation = self.dispatch_model.evaluate(
            vector,
            project_root=str(project_root) if project_root else None,
            solve_electric_dispatch=solve_electric_dispatch,
            solve_generic_dispatch=solve_generic_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            dispatch_month=dispatch_month,
            accept_default_bounds=accept_default_bounds,
            capacity_space=capacity_space,
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
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_demo_search(
            levels=levels,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            solve_generic_dispatch=solve_generic_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            dispatch_month=dispatch_month,
            accept_default_bounds=accept_default_bounds,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        acceptance_outputs = _write_level3_acceptance_artifacts(output_dir, result)
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
            **acceptance_outputs,
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
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_capacity_search(
            candidate_count=candidate_count,
            random_seed=random_seed,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            solve_generic_dispatch=solve_generic_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            dispatch_month=dispatch_month,
            accept_default_bounds=accept_default_bounds,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        acceptance_outputs = _write_level3_acceptance_artifacts(output_dir, result)
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
            **acceptance_outputs,
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
        solve_generic_dispatch: bool = False,
        electric_dispatch_scope: str = "grid",
        dispatch_periods: int = 24,
        dispatch_month: int = 1,
        accept_default_bounds: bool = False,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = cls(resolved).run_de_search(
            population_size=population_size,
            generations=generations,
            random_seed=random_seed,
            project_root=project_root,
            solve_electric_dispatch=solve_electric_dispatch,
            solve_generic_dispatch=solve_generic_dispatch,
            electric_dispatch_scope=electric_dispatch_scope,
            dispatch_periods=dispatch_periods,
            dispatch_month=dispatch_month,
            accept_default_bounds=accept_default_bounds,
        )

        json_path = output_dir / "generic_design_solutions.json"
        csv_path = output_dir / "generic_design_solutions.csv"
        report_path = output_dir / "generic_design_report.md"

        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_solutions_csv(csv_path, result)
        report_path.write_text(_build_design_report(result), encoding="utf-8")
        acceptance_outputs = _write_level3_acceptance_artifacts(output_dir, result)
        return {
            "generic_design_solutions": json_path,
            "generic_design_solutions_csv": csv_path,
            "generic_design_report": report_path,
            **acceptance_outputs,
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


def _write_level3_acceptance_artifacts(output_dir: Path, result: dict[str, Any]) -> dict[str, Path]:
    outputs = {
        "capacity_solution": output_dir / "capacity_solution.csv",
        "dispatch_summary": output_dir / "dispatch_summary.csv",
        "energy_flow_summary": output_dir / "energy_flow_summary.csv",
        "conversion_type_summary": output_dir / "conversion_type_summary.csv",
    }
    best = _best_solution(result)
    _write_capacity_solution_csv(outputs["capacity_solution"], result, best)
    _write_dispatch_summary_csv(outputs["dispatch_summary"], result)
    _write_energy_flow_summary_csv(outputs["energy_flow_summary"], best)
    _write_conversion_type_summary_csv(outputs["conversion_type_summary"], result)
    return outputs


def _best_solution(result: dict[str, Any]) -> dict[str, Any]:
    explicit = result.get("best_solution")
    if isinstance(explicit, dict) and explicit.get("dispatch_solved"):
        return explicit
    solutions = result.get("solutions", []) or []
    return _select_best_solution(solutions, solve_dispatch_requested=_any_dispatch_requested(solutions))


def _select_best_solution(
    solutions: list[dict[str, Any]],
    solve_dispatch_requested: bool,
) -> dict[str, Any]:
    if not solutions:
        return {}
    if solve_dispatch_requested:
        solved = [item for item in solutions if item.get("dispatch_solved")]
        if solved:
            return min(solved, key=lambda item: _float(item.get("total_objective")))
    return min(solutions, key=lambda item: _solution_score(item, solve_dispatch_requested))


def _any_dispatch_requested(solutions: list[dict[str, Any]]) -> bool:
    return any(
        bool(solution.get("generic_model", {}).get("real_dispatch", {}).get("scope"))
        for solution in solutions
    )


def _write_capacity_solution_csv(path: Path, result: dict[str, Any], solution: dict[str, Any]) -> None:
    columns = ["scenario_id", "solution_id", "device_id", "variable_name", "value", "unit"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        assignment = solution.get("capacity_assignment", {}) or {}
        for device_id, values in assignment.items():
            for variable_name, value in (values or {}).items():
                writer.writerow({
                    "scenario_id": result.get("scenario_id", ""),
                    "solution_id": solution.get("solution_id", ""),
                    "device_id": device_id,
                    "variable_name": variable_name,
                    "value": value,
                    "unit": _unit_from_variable_name(variable_name),
                })


def _write_dispatch_summary_csv(path: Path, result: dict[str, Any]) -> None:
    columns = [
        "solution_id",
        "scope",
        "dispatch_solved",
        "solver",
        "termination_condition",
        "objective_value",
        "month",
        "node_count",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in _dispatch_rows(result):
            writer.writerow({column: row.get(column, "") for column in columns})


def _write_energy_flow_summary_csv(path: Path, solution: dict[str, Any]) -> None:
    columns = ["solution_id", "record_type", "from", "to", "storage", "sum", "max", "final"]
    dispatch = solution.get("generic_model", {}).get("real_dispatch", {}) or {}
    summary = dispatch.get("dispatch_summary", {}) or {}
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in summary.get("flow_totals", []) or []:
            writer.writerow({
                "solution_id": solution.get("solution_id", ""),
                "record_type": "flow_total",
                "from": row.get("from", ""),
                "to": row.get("to", ""),
                "storage": "",
                "sum": row.get("sum", ""),
                "max": row.get("max", ""),
                "final": "",
            })
        for row in summary.get("storage_content", []) or []:
            writer.writerow({
                "solution_id": solution.get("solution_id", ""),
                "record_type": "storage_content",
                "from": "",
                "to": "",
                "storage": row.get("storage", ""),
                "sum": "",
                "max": row.get("max", ""),
                "final": row.get("final", ""),
            })


def _write_conversion_type_summary_csv(path: Path, result: dict[str, Any]) -> None:
    columns = [
        "abstract_type",
        "component_types",
        "device_count",
        "device_ids",
        "input_carriers",
        "output_carriers",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        summary = result.get("conversion_type_summary", {}) or {}
        for item in summary.get("types", []) or []:
            writer.writerow({
                "abstract_type": item.get("abstract_type", ""),
                "component_types": ";".join(item.get("component_types", []) or []),
                "device_count": item.get("device_count", 0),
                "device_ids": ";".join(item.get("device_ids", []) or []),
                "input_carriers": ";".join(item.get("input_carriers", []) or []),
                "output_carriers": ";".join(item.get("output_carriers", []) or []),
            })


def _unit_from_variable_name(variable_name: str) -> str:
    if variable_name.endswith("_kwh"):
        return "kWh"
    if variable_name.endswith("_t_h"):
        return "t/h"
    if variable_name.endswith("_kg_h"):
        return "kg/h"
    if variable_name.endswith("_kg"):
        return "kg"
    if variable_name.endswith("_kw"):
        return "kW"
    return ""


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_design_report(result: dict[str, Any]) -> str:
    lines = [
        "# GenericDesignOptimizer 设计搜索报告",
        "",
        "- 验收等级: `Level 3`（真实场景 + 通用线性 Energy Hub 调度求解 + 容量结果导出）",
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

    summary = result.get("conversion_type_summary", {}) or {}
    lines.extend([
        "",
        "## 多能转换类型统计",
        "",
        f"- 转换/模块类型数量: {summary.get('type_count', 0)}",
        f"- 启用设备数量: {summary.get('device_count', 0)}",
        "",
        "| 抽象类型 | 通用组件 | 设备数量 | 设备实例 | 输入载体 | 输出载体 |",
        "|---|---|---:|---|---|---|",
    ])
    for item in summary.get("types", []) or []:
        lines.append(
            "| {abstract} | {ctypes} | {count} | {devices} | {inputs} | {outputs} |".format(
                abstract=item.get("abstract_type", ""),
                ctypes=", ".join(item.get("component_types", []) or []),
                count=item.get("device_count", 0),
                devices=", ".join(item.get("device_ids", []) or []),
                inputs=", ".join(item.get("input_carriers", []) or []),
                outputs=", ".join(item.get("output_carriers", []) or []),
            )
        )

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
