#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run Phase 2 post-analysis for existing result directories produced by run.py.

Supports:
- a single result directory
- a parent directory containing multiple result directories

Example
-------
uv run python scripts/run_existing_post_analysis.py "Results/服务器结果/第三次实验"
uv run python scripts/run_existing_post_analysis.py "Results/服务器结果/full_all_50x100_20260413_134312" --skip-existing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from case_config import get_case
from scripts.post_analysis_report import (
    POST_ANALYSIS_MODES,
    print_comparison_report,
    run_post_analysis,
)


METHOD_MAP = {
    "Economic_only": "economic_only",
    "Std": "std",
    "Euclidean": "euclidean",
    "Pearson": "pearson",
    "SSR": "ssr",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 2 post-analysis for existing result folders."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more result directories or parent folders containing result directories.",
    )
    parser.add_argument(
        "--mode",
        choices=["test", "quick", "medium", "full"],
        default="full",
        help="Reuse Phase 2 settings from scripts/post_analysis_report.py.",
    )
    parser.add_argument(
        "--cost-levels",
        type=int,
        default=None,
        help="Override the default number of cost levels.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip result directories that already contain post_analysis_results.csv.",
    )
    return parser.parse_args()


def _has_method_dirs(path: Path) -> bool:
    return any((path / name).is_dir() for name in METHOD_MAP)


def _is_result_dir(path: Path) -> bool:
    return path.is_dir() and (
        _has_method_dirs(path) or (path / "comparison_report.md").exists()
    )


def _find_result_dirs(path: Path) -> List[Path]:
    path = path.resolve()
    if _is_result_dir(path):
        return [path]

    found: List[Path] = []
    for child in path.rglob("*"):
        if _is_result_dir(child):
            found.append(child)
    # keep deterministic order and drop nested duplicates if parent already selected
    unique: List[Path] = []
    for item in sorted(found):
        if not any(parent in item.parents for parent in unique):
            unique.append(item)
    return unique


def _infer_case_name(path: Path) -> str:
    text = str(path).lower()
    return "songshan_lake" if "songshan_lake" in text else "german"


def _infer_methods(path: Path) -> List[str]:
    methods = []
    for folder, method in METHOD_MAP.items():
        if (path / folder).is_dir():
            methods.append(method)
    return methods


def _should_skip(path: Path, skip_existing: bool) -> bool:
    return skip_existing and (path / "post_analysis_results.csv").exists()


def main() -> None:
    args = parse_args()
    cfg = POST_ANALYSIS_MODES[args.mode]
    cost_levels = args.cost_levels or cfg["cost_levels"]

    targets: List[Path] = []
    for path_text in args.paths:
        target_path = Path(path_text).expanduser()
        if not target_path.is_absolute():
            target_path = (BASE_DIR / target_path).resolve()
        targets.extend(_find_result_dirs(target_path))

    if not targets:
        raise SystemExit("No result directories found.")

    print("=" * 70)
    print("  批量补跑 Phase 2 后验分析")
    print("=" * 70)
    print(f"  目标目录数: {len(targets)}")
    print(f"  模式: {args.mode}")
    print(f"  cost levels: {cost_levels}")
    print(f"  max days: {cfg['post_analysis_days']}")

    for result_dir in targets:
        if _should_skip(result_dir, args.skip_existing):
            print(f"\n[跳过] {result_dir}")
            continue

        methods = _infer_methods(result_dir)
        if not methods:
            print(f"\n[跳过] {result_dir} (未识别到方法子目录)")
            continue

        case_name = _infer_case_name(result_dir)
        case_config = get_case(case_name)

        print("\n" + "-" * 70)
        print(f"结果目录: {result_dir}")
        print(f"案例: {case_name}")
        print(f"方法: {methods}")

        df_abs, df_budget = run_post_analysis(
            str(result_dir),
            case_config,
            methods,
            cost_levels=cost_levels,
            max_days=cfg["post_analysis_days"],
        )
        if df_abs is not None or df_budget is not None:
            print_comparison_report(df_abs, df_budget)


if __name__ == "__main__":
    main()
