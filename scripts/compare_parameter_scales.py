#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Compare multiple run directories produced by run.py and summarize whether
population size / generation count changes materially affect the results.

Supports both:
1. batch experiment roots like paper-batch__exp-all__...
2. flat custom result roots like custom__german__base__m5__n50__g100__...
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pandas as pd


METHOD_LABELS = {
    "Economic_only": "economic_only",
    "Std": "std",
    "Euclidean": "euclidean",
    "Pearson": "pearson",
    "SSR": "ssr",
}
METHOD_DIR_NAMES = set(METHOD_LABELS.keys())


@dataclass
class RunSummary:
    path: Path
    label: str
    total_elapsed: Optional[str]
    params_text: Optional[str]
    records: List[dict]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare 50/100, 80/150, 100/200 style experiment outputs."
    )
    parser.add_argument(
        "result_dirs",
        nargs="+",
        help="One or more run result directories to compare.",
    )
    parser.add_argument(
        "--output",
        help="Optional output markdown path. Default writes to Results/parameter_scale_comparison.md",
    )
    return parser.parse_args()


def _scan_root(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Result directory not found: {path}")

    children = [p for p in path.iterdir() if p.is_dir()]
    if any(child.name.startswith("exp") for child in children):
        return path

    if any(child.name in METHOD_DIR_NAMES for child in children):
        return path

    nested = [
        child
        for child in children
        if any(
            grand.is_dir() and (grand.name.startswith("exp") or grand.name in METHOD_DIR_NAMES)
            for grand in child.iterdir()
        )
    ]
    if len(nested) == 1:
        return nested[0]

    return path


def _extract_label(path: Path) -> str:
    name = path.name
    match_n = re.search(r"__n(\d+)", name)
    match_g = re.search(r"__g(\d+)", name)
    if match_n and match_g:
        return f"n{match_n.group(1)}_g{match_g.group(1)}"

    match_ng = re.search(r"_(\d+)x(\d+)_", name)
    if match_ng:
        return f"n{match_ng.group(1)}_g{match_ng.group(2)}"

    return name


def _extract_params_from_name(path: Path) -> Optional[str]:
    name = path.name
    match_n = re.search(r"__n(\d+)", name)
    match_g = re.search(r"__g(\d+)", name)
    if match_n and match_g:
        return f"nind={match_n.group(1)}, maxgen={match_g.group(1)}"

    match_ng = re.search(r"_(\d+)x(\d+)_", name)
    if match_ng:
        return f"nind={match_ng.group(1)}, maxgen={match_ng.group(2)}"

    return None


def _seconds_to_hms(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _parse_comparison_report_total_time(path: Path) -> Optional[str]:
    report = path / "comparison_report.md"
    if not report.exists():
        return None

    total_seconds = 0.0
    found = False
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        try:
            total_seconds += float(cells[3])
            found = True
        except ValueError:
            continue

    if not found:
        return None
    return _seconds_to_hms(total_seconds)


def _parse_batch_timing(path: Path) -> Tuple[Optional[str], Optional[str]]:
    report = path / "batch_timing_summary.md"
    if not report.exists():
        return _parse_comparison_report_total_time(path), _extract_params_from_name(path)

    total_elapsed = None
    params_text = None
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("- 参数:"):
            params_text = line.split("`")[1] if "`" in line else line.removeprefix("- 参数:").strip()
        elif line.startswith("- 总耗时:"):
            total_elapsed = line.split("`")[1] if "`" in line else line.removeprefix("- 总耗时:").strip()
    return total_elapsed, params_text


def _iter_experiment_dirs(root: Path) -> Iterable[Path]:
    children = [p for p in root.iterdir() if p.is_dir()]
    if any(child.name in METHOD_DIR_NAMES for child in children):
        yield root
        return

    for child in sorted(children):
        if child.name.startswith("exp"):
            yield child


def _experiment_key(exp_dir: Path, root: Path) -> str:
    if exp_dir == root:
        name = root.name
        name = re.sub(r"__n\d+__g\d+.*$", "", name)
        name = re.sub(r"_\d+x\d+_.*$", "", name)
        return name
    return exp_dir.name.split("__")[0]


def _collect_records(root: Path) -> List[dict]:
    rows: List[dict] = []
    for exp_dir in _iter_experiment_dirs(root):
        for csv_path in sorted(exp_dir.glob("**/Pareto_*.csv")):
            df = pd.read_csv(csv_path)
            method_dir = csv_path.parent.name
            method_key = METHOD_LABELS.get(method_dir, method_dir.lower())
            min_cost = float(df["Economic_Cost"].min()) if "Economic_Cost" in df.columns else None
            min_match = float(df["Matching_Index"].min()) if "Matching_Index" in df.columns else None
            rows.append(
                {
                    "experiment": _experiment_key(exp_dir, root),
                    "experiment_dir": exp_dir.name,
                    "method": method_key,
                    "method_dir": method_dir,
                    "pareto_count": int(len(df)),
                    "min_cost": min_cost,
                    "min_match": min_match,
                }
            )
    return rows


def load_run_summary(path_text: str) -> RunSummary:
    raw_path = Path(path_text).expanduser().resolve()
    root = _scan_root(raw_path)
    total_elapsed, params_text = _parse_batch_timing(root)
    return RunSummary(
        path=root,
        label=_extract_label(root),
        total_elapsed=total_elapsed,
        params_text=params_text,
        records=_collect_records(root),
    )


def _format_num(value: Optional[float], digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:,.{digits}f}"


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def build_markdown(runs: List[RunSummary]) -> str:
    lines: List[str] = []
    lines.append("# 参数规模对比分析\n\n")
    lines.append("## 运行集合\n\n")
    lines.append("| 标签 | 参数 | 总耗时 | 目录 |\n")
    lines.append("|---|---|---|---|\n")
    for run in runs:
        lines.append(
            f"| `{run.label}` | `{run.params_text or '-'}` | `{run.total_elapsed or '-'}` | `{run.path.as_posix()}` |\n"
        )

    baseline = runs[0]
    baseline_map = {
        (row["experiment"], row["method"]): row
        for row in baseline.records
    }

    grouped_keys = sorted(
        {
            (row["experiment"], row["method"])
            for run in runs
            for row in run.records
        }
    )

    lines.append("\n## 分实验 / 分方法对比\n\n")
    for experiment, method in grouped_keys:
        lines.append(f"### `{experiment}` / `{method}`\n\n")
        lines.append("| 标签 | 最低成本 | 成本变化(相对基线) | 最佳匹配度 | 匹配度变化(相对基线) | Pareto解数 |\n")
        lines.append("|---|---:|---:|---:|---:|---:|\n")

        base_row = baseline_map.get((experiment, method))
        base_cost = base_row["min_cost"] if base_row else None
        base_match = base_row["min_match"] if base_row else None

        for run in runs:
            row = next(
                (item for item in run.records if item["experiment"] == experiment and item["method"] == method),
                None,
            )
            if row is None:
                lines.append(f"| `{run.label}` | - | - | - | - | - |\n")
                continue

            cost_delta_pct = None
            if base_cost not in (None, 0):
                cost_delta_pct = (row["min_cost"] - base_cost) / base_cost * 100.0

            match_delta_pct = None
            if base_match not in (None, 0):
                match_delta_pct = (row["min_match"] - base_match) / base_match * 100.0

            lines.append(
                f"| `{run.label}` | {_format_num(row['min_cost'])} | {_format_pct(cost_delta_pct)} | "
                f"{_format_num(row['min_match'], 4)} | {_format_pct(match_delta_pct)} | {row['pareto_count']} |\n"
            )
        lines.append("\n")

    lines.append("## 如何判断 50/100 是否足够\n\n")
    lines.append("建议按下面四条判断，而不要只看单次运行耗时：\n\n")
    lines.append("1. `最低成本是否稳定`：若从 `50/100` 提高到 `80/150`、`100/200` 后，关键方法的最低成本变化已很小（例如 1% 以内），说明参数基本足够。\n")
    lines.append("2. `最佳匹配度是否稳定`：若匹配指标也只剩小幅变化，说明 Pareto 前沿已趋于收敛。\n")
    lines.append("3. `Pareto 解规模是否稳定`：若 Pareto 解数始终接近满规模，且前沿形态变化不大，说明进化搜索已较充分。\n")
    lines.append("4. `结论是否翻转`：若扩大参数后，论文结论发生翻转（如某方法从优变劣），则 `50/100` 还不够稳。\n")

    lines.append("\n## 自动结论摘要\n\n")
    lines.append("| 实验 | 方法 | 最低成本相对波动 | 最佳匹配度相对波动 | 稳定性判断 |\n")
    lines.append("|---|---|---:|---:|---|\n")
    for experiment, method in grouped_keys:
        method_rows = []
        for run in runs:
            row = next(
                (item for item in run.records if item["experiment"] == experiment and item["method"] == method),
                None,
            )
            if row is not None:
                method_rows.append(row)

        if not method_rows:
            continue

        costs = [row["min_cost"] for row in method_rows if row["min_cost"] is not None]
        matches = [row["min_match"] for row in method_rows if row["min_match"] is not None]

        cost_spread = None
        if costs and min(costs) > 0:
            cost_spread = (max(costs) - min(costs)) / min(costs) * 100.0

        match_spread = None
        if matches and min(matches) > 0:
            match_spread = (max(matches) - min(matches)) / min(matches) * 100.0

        valid_spreads = [value for value in (cost_spread, match_spread) if value is not None]
        worst_spread = max(valid_spreads) if valid_spreads else None
        if worst_spread is None:
            verdict = "信息不足"
        elif worst_spread <= 2:
            verdict = "较稳定，可支撑当前参数"
        elif worst_spread <= 5:
            verdict = "中度波动，建议补充复现"
        else:
            verdict = "波动较大，建议增大参数或重复运行"

        cost_spread_text = "-" if cost_spread is None else f"{cost_spread:.2f}%"
        match_spread_text = "-" if match_spread is None else f"{match_spread:.2f}%"
        lines.append(
            f"| `{experiment}` | `{method}` | {cost_spread_text} | {match_spread_text} | {verdict} |\n"
        )

    return "".join(lines)


def main() -> None:
    args = parse_args()
    runs = [load_run_summary(path_text) for path_text in args.result_dirs]
    markdown = build_markdown(runs)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = (Path.cwd() / "Results" / "parameter_scale_comparison.md").resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Comparison written to: {output_path}")


if __name__ == "__main__":
    main()
