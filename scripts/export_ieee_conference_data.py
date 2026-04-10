# -*- coding: utf-8 -*-
"""
从 论文撰写/会议/data/raw_pareto 中的 Pareto CSV 汇总会议稿用标量（前沿宽度、解数等）。

用法（仓库根目录）:
  python scripts/export_ieee_conference_data.py
  python scripts/export_ieee_conference_data.py --pareto-dir 论文撰写/会议/data/raw_pareto
  python scripts/export_ieee_conference_data.py --feasible-max-cost 5000000  # 排除异常高成本解
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_PARETO = BASE / "论文撰写/会议/data/raw_pareto"
DEFAULT_OUT = BASE / "论文撰写/会议/data/summary_conference.csv"

FILES = [
    ("economic_only", "Pareto_Economic_only.csv"),
    ("std", "Pareto_Std.csv"),
    ("euclidean", "Pareto_Euclidean.csv"),
]


def _read_pareto(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return (r.fieldnames or [], rows)


def _filter_rows(rows: list[dict], feasible_max: float) -> list[dict]:
    if feasible_max <= 0:
        return rows
    out = []
    for row in rows:
        c = float(row["Economic_Cost"])
        if c == c and 0 < c <= feasible_max:
            out.append(row)
    return out


def main():
    p = argparse.ArgumentParser(description="汇总 IEEE 会议用 Pareto 统计")
    p.add_argument("--pareto-dir", type=Path, default=DEFAULT_PARETO)
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--feasible-max-cost",
        type=float,
        default=0.0,
        help="仅对 Economic_Cost≤该值的解计算 min/max/宽度；0 表示不过滤（期刊干净数据默认 0）",
    )
    args = p.parse_args()

    summaries = []
    for method, fname in FILES:
        path = args.pareto_dir / fname
        if not path.exists():
            raise FileNotFoundError(path)
        _, rows = _read_pareto(path)
        if not rows:
            raise ValueError(f"空文件: {path}")
        used = _filter_rows(rows, args.feasible_max_cost)
        if args.feasible_max_cost > 0 and len(used) < 1:
            raise ValueError(
                f"{path}: 过滤后无解（feasible_max_cost={args.feasible_max_cost}）"
            )
        stat_rows = used if args.feasible_max_cost > 0 else rows
        costs = [float(row["Economic_Cost"]) for row in stat_rows]
        cmin, cmax = min(costs), max(costs)
        width = cmax - cmin
        rec = {
            "method": method,
            "n_solutions_total": str(len(rows)),
            "n_solutions_used_for_range": str(len(stat_rows)),
            "feasible_max_cost_EUR": f"{args.feasible_max_cost:.1f}" if args.feasible_max_cost > 0 else "",
            "economic_cost_min_EUR": f"{cmin:.6f}",
            "economic_cost_max_EUR": f"{cmax:.6f}",
            "pareto_front_width_kEUR": f"{width / 1000.0:.6f}",
        }
        if "Matching_Index" in stat_rows[0] and stat_rows[0]["Matching_Index"] not in ("", None):
            mi = [float(row["Matching_Index"]) for row in stat_rows]
            rec["matching_index_min"] = f"{min(mi):.6f}"
            rec["matching_index_max"] = f"{max(mi):.6f}"
        else:
            rec["matching_index_min"] = ""
            rec["matching_index_max"] = ""
        summaries.append(rec)

    std_w = float(summaries[1]["pareto_front_width_kEUR"])
    for rec in summaries:
        rec["width_ratio_vs_std"] = (
            f"{float(rec['pareto_front_width_kEUR']) / std_w:.6f}" if std_w > 0 else ""
        )

    fieldnames = [
        "method",
        "n_solutions_total",
        "n_solutions_used_for_range",
        "feasible_max_cost_EUR",
        "economic_cost_min_EUR",
        "economic_cost_max_EUR",
        "pareto_front_width_kEUR",
        "matching_index_min",
        "matching_index_max",
        "width_ratio_vs_std",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(summaries)

    print(f"Wrote {args.output}")
    for rec in summaries:
        print(rec)
    eq_w = float(summaries[2]["pareto_front_width_kEUR"])
    if std_w > 0:
        print(f"\nEuclidean / Std width ratio = {eq_w / std_w:.3f}x")


if __name__ == "__main__":
    main()
