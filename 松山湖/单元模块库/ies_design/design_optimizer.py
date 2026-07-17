from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from current_cchp_adapter import CurrentCCHPAdapter


Runner = Callable[..., Tuple[Dict[str, Any], str]]


class DesignOptimizer:
    """Bridge resolved scenario dictionaries to the current CCHP optimizer."""

    @classmethod
    def build_run_config(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        output_root: str | Path | None = None,
    ) -> dict[str, Any]:
        project_root = Path(project_root)
        optimization = resolved.get("optimization", {})
        scenario = resolved.get("scenario", {})
        mode = optimization.get("mode") or "test"
        nind = optimization.get("nind")
        maxgen = optimization.get("maxgen")
        methods = optimization.get("methods") or [optimization.get("matching_method", "euclidean")]

        if nind is None or maxgen is None:
            raise ValueError("optimization.nind and optimization.maxgen are required before running")

        scenario_id = scenario.get("id", "scenario")
        result_root = Path(output_root) if output_root else project_root / "DesignResults"
        return {
            "nind": int(nind),
            "maxgen": int(maxgen),
            "pool_type": optimization.get("pool_type") or optimization.get("PoolType") or "Process",
            "inherit_population": bool(optimization.get("inherit_population", True)),
            "methods_to_run": list(methods),
            "case_config": CurrentCCHPAdapter.to_case_config(resolved, project_root=project_root),
            "num_workers": optimization.get("workers"),
            "result_root": str(result_root),
            "result_dir_name": cls._result_dir_name(scenario_id, mode),
        }

    @classmethod
    def run(
        cls,
        resolved: dict[str, Any],
        project_root: str | Path,
        output_root: str | Path | None = None,
        runner: Runner | None = None,
    ) -> dict[str, Any]:
        if runner is None:
            from cchp_gasolution import run_comparative_study

            runner = run_comparative_study

        run_config = cls.build_run_config(resolved, project_root=project_root, output_root=output_root)
        results, result_dir = runner(**run_config)
        return {
            "results": results,
            "result_dir": result_dir,
            "run_config": run_config,
        }

    @staticmethod
    def _result_dir_name(scenario_id: str, mode: str) -> str:
        safe_scenario = _safe_token(scenario_id)
        safe_mode = _safe_token(mode)
        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"design__{safe_scenario}__{safe_mode}__{timestamp}"


def _safe_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value)).strip("_")
    return token or "scenario"
