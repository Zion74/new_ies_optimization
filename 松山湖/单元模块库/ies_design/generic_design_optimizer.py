from __future__ import annotations

import csv
import json
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
            evaluation = self.dispatch_model.evaluate(
                vector,
                project_root=str(project_root) if project_root else None,
                solve_electric_dispatch=solve_electric_dispatch,
                electric_dispatch_scope=electric_dispatch_scope,
                dispatch_periods=dispatch_periods,
            )
            solutions.append({
                "solution_id": solution_id,
                "level": level,
                "vector": vector,
                "investment_cost": evaluation["investment_cost"],
                "dispatch_solved": evaluation["dispatch_solved"],
                "capacity_assignment": evaluation["capacity_assignment"],
                "generic_model": evaluation.get("generic_model", {}),
                "status": evaluation["status"],
            })

        return {
            "status": "build_only",
            "scenario_id": self.resolved.get("scenario", {}).get("id", ""),
            "capacity_variable_count": len(self.capacity_space.variables),
            "capacity_variable_names": self.capacity_space.names,
            "solutions": solutions,
            "build_gaps": self.dispatch_model.model_spec.get("build_gaps", []),
            "next_step": "replace demo levels with NSGA-II/DE candidates and solve full dispatch in GenericDispatchModel",
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


def _validate_levels(levels: list[float]) -> None:
    if not levels:
        raise ValueError("at least one demo search level is required")
    for level in levels:
        if level < 0 or level > 1:
            raise ValueError(f"demo search level must be between 0 and 1, got {level}")


def _write_solutions_csv(path: Path, result: dict[str, Any]) -> None:
    variable_names = result.get("capacity_variable_names", []) or []
    columns = ["solution_id", "level", "status", "dispatch_solved", "investment_cost", *variable_names]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for solution in result.get("solutions", []):
            row = {
                "solution_id": solution.get("solution_id", ""),
                "level": solution.get("level", ""),
                "status": solution.get("status", ""),
                "dispatch_solved": solution.get("dispatch_solved", ""),
                "investment_cost": solution.get("investment_cost", ""),
            }
            row.update(dict(zip(variable_names, solution.get("vector", []) or [])))
            writer.writerow(row)


def _build_design_report(result: dict[str, Any]) -> str:
    lines = [
        "# GenericDesignOptimizer 设计搜索报告",
        "",
        f"- 场景 ID: `{result.get('scenario_id', '')}`",
        f"- 当前状态: `{result.get('status', '')}`",
        f"- 容量变量数量: {result.get('capacity_variable_count', 0)}",
        f"- 候选方案数量: {len(result.get('solutions', []) or [])}",
        "- 内层调度求解: 当前仅支持可选的真实电力切片求解，完整冷热电/氢/蒸汽调度尚未接入。",
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
        "| ID | Level | Status | Dispatch Solved | Investment Cost |",
        "|---:|---:|---|---|---:|",
    ])
    for solution in result.get("solutions", []) or []:
        lines.append(
            f"| {solution.get('solution_id', '')} | {solution.get('level', '')} | "
            f"{solution.get('status', '')} | {solution.get('dispatch_solved', '')} | "
            f"{solution.get('investment_cost', '')} |"
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
