# -*- coding: utf-8 -*-
"""
统一重绘 Exp3 / Exp4 图表
=========================

用途：
1. 统一绘制 Exp3（无卡诺 vs 有卡诺）的 Pareto 与后验运行指标图
2. 统一绘制 Exp4（有卡诺条件下 Std vs Euclidean）的 Pareto 与后验运行指标图
3. 避免直接使用包含超高成本尾部的原始 Pareto 图

示例：
  uv run python scripts/redraw_carnot_figures.py ^
    --exp3a-dir C:\\codex_tmp\\exp3a ^
    --exp3b-dir C:\\codex_tmp\\exp3b ^
    --exp4-dir  C:\\codex_tmp\\exp4
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd


plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150


SERIES_STYLE = {
    "exp3a": {"label": "EQD without Carnot", "color": "#4169E1", "marker": "o"},
    "exp3b": {"label": "EQD with Carnot", "color": "#FF6347", "marker": "^"},
    "std": {"label": "Std with Carnot", "color": "#808080", "marker": "s"},
    "euclidean": {"label": "EQD with Carnot", "color": "#FF6347", "marker": "^"},
}


def _load_pareto(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    if "Economic_Cost" not in df.columns:
        raise ValueError(f"Missing Economic_Cost in {path}")
    return df.sort_values("Economic_Cost").reset_index(drop=True)


def _load_budget_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "budget_label" not in df.columns:
        raise ValueError(f"Missing budget_label in {path}")
    return df


def _filter_affordable(df: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    min_cost = df["Economic_Cost"].min()
    filtered = df[df["Economic_Cost"] <= min_cost * multiplier].copy()
    if len(filtered) == 0:
        filtered = df.nsmallest(10, "Economic_Cost").copy()
    return filtered.sort_values("Economic_Cost")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _cost_to_million(cost_series: Iterable[float]) -> List[float]:
    return [float(x) / 1_000_000 for x in cost_series]


def plot_exp3_pareto(exp3a_dir: Path, exp3b_dir: Path, output_dir: Path, cost_multiplier: float) -> Path:
    df_a = _filter_affordable(_load_pareto(exp3a_dir / "Euclidean" / "Pareto_Euclidean.csv"), cost_multiplier)
    df_b = _filter_affordable(_load_pareto(exp3b_dir / "Euclidean" / "Pareto_Euclidean.csv"), cost_multiplier)

    fig, ax = plt.subplots(figsize=(10, 6))

    for key, df in [("exp3a", df_a), ("exp3b", df_b)]:
        style = SERIES_STYLE[key]
        x = _cost_to_million(df["Economic_Cost"])
        y = df["Matching_Index"].astype(float).tolist()
        ax.plot(x, y, marker=style["marker"], color=style["color"], linewidth=2,
                markersize=6, label=style["label"])

        best = df.iloc[0]
        ax.scatter([best["Economic_Cost"] / 1_000_000], [best["Matching_Index"]],
                   color=style["color"], s=100, edgecolors="black", zorder=3)

    ax.set_xlabel("Annualized cost (million)")
    ax.set_ylabel("Matching index")
    ax.set_title("Exp3: Carnot battery ablation within affordable cost range")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    ax.text(
        0.02,
        0.98,
        f"Pareto points with cost <= {cost_multiplier:.1f}x minimum cost",
        transform=ax.transAxes,
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    save_path = output_dir / "Fig_Exp3_Carnot_Ablation_Pareto.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    return save_path


def plot_exp3_budget(exp3a_dir: Path, exp3b_dir: Path, output_dir: Path) -> Path:
    df_a = _load_budget_results(exp3a_dir / "post_analysis_budget.csv")
    df_b = _load_budget_results(exp3b_dir / "post_analysis_budget.csv")

    budget_order = ["基准", "+10%", "+30%", "+50%", "+100%"]
    metrics = [
        ("peak_grid_kW", "Peak grid purchase (kW)"),
        ("annual_grid_purchase_MWh", "Annual grid purchase (MWh)"),
        ("self_sufficiency_%", "Self-sufficiency (%)"),
        ("grid_volatility_kW", "Grid volatility (kW)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes = axes.flatten()

    for ax, (metric, title) in zip(axes, metrics):
        for key, df in [("exp3a", df_a), ("exp3b", df_b)]:
            style = SERIES_STYLE[key]
            series = []
            labels = []
            for budget in budget_order:
                row = df[df["budget_label"] == budget]
                if len(row) == 0:
                    continue
                labels.append(budget)
                series.append(float(row.iloc[0][metric]))
            x = list(range(len(series)))
            ax.plot(x, series, marker=style["marker"], color=style["color"], linewidth=2,
                    markersize=6, label=style["label"])
            ax.set_xticks(x)
            ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)

    axes[0].legend(loc="best")
    fig.suptitle("Exp3: operational validation under budget-aligned solutions", fontsize=14, y=0.98)

    save_path = output_dir / "Fig_Exp3_Carnot_Ablation_Budget.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    return save_path


def plot_exp4_pareto(exp4_dir: Path, output_dir: Path, cost_multiplier: float) -> Path:
    df_std = _filter_affordable(_load_pareto(exp4_dir / "Std" / "Pareto_Std.csv"), cost_multiplier)
    df_euc = _filter_affordable(_load_pareto(exp4_dir / "Euclidean" / "Pareto_Euclidean.csv"), cost_multiplier)

    fig, ax = plt.subplots(figsize=(10, 6))

    for key, df in [("std", df_std), ("euclidean", df_euc)]:
        style = SERIES_STYLE[key]
        x = _cost_to_million(df["Economic_Cost"])
        y = df["Matching_Index"].astype(float).tolist()
        ax.plot(x, y, marker=style["marker"], color=style["color"], linewidth=2,
                markersize=6, label=style["label"])
        best = df.iloc[0]
        ax.scatter([best["Economic_Cost"] / 1_000_000], [best["Matching_Index"]],
                   color=style["color"], s=100, edgecolors="black", zorder=3)

    ax.set_xlabel("Annualized cost (million)")
    ax.set_ylabel("Matching index")
    ax.set_title("Exp4: Std vs EQD under Carnot integration")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    ax.text(
        0.02,
        0.98,
        f"Pareto points with cost <= {cost_multiplier:.1f}x minimum cost",
        transform=ax.transAxes,
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    save_path = output_dir / "Fig_Exp4_Carnot_Joint_Pareto.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    return save_path


def plot_exp4_budget(exp4_dir: Path, output_dir: Path) -> Path:
    df = _load_budget_results(exp4_dir / "post_analysis_budget.csv")
    df_std = df[df["method"] == "Std"].copy()
    df_euc = df[df["method"] == "Euclidean"].copy()

    budget_order = ["基准", "+10%", "+30%", "+50%", "+100%"]
    metrics = [
        ("peak_grid_kW", "Peak grid purchase (kW)"),
        ("annual_grid_purchase_MWh", "Annual grid purchase (MWh)"),
        ("self_sufficiency_%", "Self-sufficiency (%)"),
        ("grid_volatility_kW", "Grid volatility (kW)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes = axes.flatten()

    for ax, (metric, title) in zip(axes, metrics):
        for key, sub_df in [("std", df_std), ("euclidean", df_euc)]:
            style = SERIES_STYLE[key]
            series = []
            labels = []
            for budget in budget_order:
                row = sub_df[sub_df["budget_label"] == budget]
                if len(row) == 0:
                    continue
                labels.append(budget)
                series.append(float(row.iloc[0][metric]))
            x = list(range(len(series)))
            ax.plot(x, series, marker=style["marker"], color=style["color"], linewidth=2,
                    markersize=6, label=style["label"])
            ax.set_xticks(x)
            ax.set_xticklabels(labels)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)

    axes[0].legend(loc="best")
    fig.suptitle("Exp4: budget-aligned operational comparison under Carnot integration", fontsize=14, y=0.98)

    save_path = output_dir / "Fig_Exp4_Carnot_Joint_Budget.png"
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close()
    return save_path


def write_summary(exp3a_dir: Path, exp3b_dir: Path, exp4_dir: Path, output_dir: Path) -> Path:
    df_exp3a = _load_pareto(exp3a_dir / "Euclidean" / "Pareto_Euclidean.csv")
    df_exp3b = _load_pareto(exp3b_dir / "Euclidean" / "Pareto_Euclidean.csv")
    df_exp4_std = _load_pareto(exp4_dir / "Std" / "Pareto_Std.csv")
    df_exp4_euc = _load_pareto(exp4_dir / "Euclidean" / "Pareto_Euclidean.csv")

    post_exp3a = pd.read_csv(exp3a_dir / "post_analysis_results.csv")
    post_exp3b = pd.read_csv(exp3b_dir / "post_analysis_results.csv")
    budget_exp3a = _load_budget_results(exp3a_dir / "post_analysis_budget.csv")
    budget_exp3b = _load_budget_results(exp3b_dir / "post_analysis_budget.csv")
    budget_exp4 = _load_budget_results(exp4_dir / "post_analysis_budget.csv")

    def _min_row(df: pd.DataFrame) -> pd.Series:
        return df.sort_values("Economic_Cost").iloc[0]

    def _nearest_operational_row(df: pd.DataFrame, target_cost: float) -> pd.Series:
        return df.iloc[(df["annual_cost"].astype(float) - float(target_cost)).abs().argmin()]

    def _budget_row(df: pd.DataFrame, label: str) -> pd.Series | None:
        row = df[df["budget_label"] == label]
        return row.iloc[0] if len(row) else None

    lines = []
    lines.append("# Carnot Figures Redraw Summary\n\n")
    lines.append("## Exp3 minimum-cost solutions\n\n")
    lines.append("| Scenario | Cost | Matching | Peak grid | Annual grid | Self-sufficiency |\n")
    lines.append("|---|---:|---:|---:|---:|---:|\n")

    exp3a_min = _min_row(df_exp3a)
    exp3b_min = _min_row(df_exp3b)
    exp3a_op = _nearest_operational_row(post_exp3a, float(exp3a_min["Economic_Cost"]))
    exp3b_op = _nearest_operational_row(post_exp3b, float(exp3b_min["Economic_Cost"]))

    lines.append(
        f"| EQD without Carnot | {exp3a_min['Economic_Cost']:.2f} | {exp3a_min['Matching_Index']:.2f} | "
        f"{exp3a_op['peak_grid_kW']:.1f} | {exp3a_op['annual_grid_purchase_MWh']:.1f} | {exp3a_op['self_sufficiency_%']:.2f} |\n"
    )
    lines.append(
        f"| EQD with Carnot | {exp3b_min['Economic_Cost']:.2f} | {exp3b_min['Matching_Index']:.2f} | "
        f"{exp3b_op['peak_grid_kW']:.1f} | {exp3b_op['annual_grid_purchase_MWh']:.1f} | {exp3b_op['self_sufficiency_%']:.2f} |\n"
    )

    lines.append("\n## Exp4 budget-aligned comparison\n\n")
    lines.append("| Budget | Method | Cost | Peak grid | Annual grid | Self-sufficiency |\n")
    lines.append("|---|---|---:|---:|---:|---:|\n")

    for budget in ["基准", "+10%", "+30%", "+50%", "+100%"]:
        subset = budget_exp4[budget_exp4["budget_label"] == budget]
        for _, row in subset.iterrows():
            lines.append(
                f"| {budget} | {row['method']} | {row['annual_cost']:.2f} | {row['peak_grid_kW']:.1f} | "
                f"{row['annual_grid_purchase_MWh']:.1f} | {row['self_sufficiency_%']:.2f} |\n"
            )

    lines.append("\n## Notes\n\n")
    lines.append("- Pareto redraws intentionally clip the extreme-cost tail.\n")
    lines.append("- Budget plots use `post_analysis_budget.csv` and therefore focus on affordable operating validation.\n")

    save_path = output_dir / "carnot_redraw_summary.md"
    save_path.write_text("".join(lines), encoding="utf-8")
    return save_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统一重绘 Exp3 / Exp4 图表")
    parser.add_argument("--exp3a-dir", required=True, help="Exp3a 结果目录")
    parser.add_argument("--exp3b-dir", required=True, help="Exp3b 结果目录")
    parser.add_argument("--exp4-dir", required=True, help="Exp4 结果目录")
    parser.add_argument("--output-dir", default=r"C:\codex_tmp\carnot_redraw", help="输出目录")
    parser.add_argument("--cost-multiplier", type=float, default=1.5,
                        help="Pareto 裁剪阈值，保留 cost <= min_cost * multiplier")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    exp3a_dir = Path(args.exp3a_dir)
    exp3b_dir = Path(args.exp3b_dir)
    exp4_dir = Path(args.exp4_dir)
    output_dir = Path(args.output_dir)
    _ensure_dir(output_dir)

    print("\n" + "=" * 70)
    print("重绘 Carnot 相关图表")
    print("=" * 70)
    print(f"Exp3a: {exp3a_dir}")
    print(f"Exp3b: {exp3b_dir}")
    print(f"Exp4 : {exp4_dir}")
    print(f"Output: {output_dir}")

    outputs = []
    outputs.append(plot_exp3_pareto(exp3a_dir, exp3b_dir, output_dir, args.cost_multiplier))
    outputs.append(plot_exp3_budget(exp3a_dir, exp3b_dir, output_dir))
    outputs.append(plot_exp4_pareto(exp4_dir, output_dir, args.cost_multiplier))
    outputs.append(plot_exp4_budget(exp4_dir, output_dir))
    outputs.append(write_summary(exp3a_dir, exp3b_dir, exp4_dir, output_dir))

    print("\nGenerated files:")
    for path in outputs:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
