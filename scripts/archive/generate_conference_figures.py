# -*- coding: utf-8 -*-
"""Generate conference-paper figures and compact data tables.

Outputs:
- 论文撰写/会议/figures/pareto_normalized.(pdf|png)
- 论文撰写/会议/figures/budget_sweep.(pdf|png)
- 论文撰写/会议/data/conference_budget_path.csv
- 论文撰写/会议/data/conference_selected_capacities.csv
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
CONF_DIR = ROOT / "论文撰写" / "会议"
DATA_DIR = CONF_DIR / "data"
FIG_DIR = CONF_DIR / "figures"

RAW_DIR = DATA_DIR / "raw_pareto"
POST_DIR = DATA_DIR / "post_analysis_budget"

COLORS = {
    "Economic": "#C73E1D",
    "Std": "#2E86AB",
    "IEMI": "#3A7D44",
}

METHOD_MAP = {
    "economic_only": "Economic",
    "std": "Std",
    "euclidean": "IEMI",
}


def _read_pareto(method_key: str, filename: str) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / filename).copy()
    df["Method"] = METHOD_MAP[method_key]
    df["Economic_Cost_kEUR"] = df["Economic_Cost"] / 1000.0
    if "Matching_Index" in df.columns:
        mi_min = df["Matching_Index"].min()
        mi_max = df["Matching_Index"].max()
        if mi_max > mi_min:
            df["Normalized_Mismatch"] = (df["Matching_Index"] - mi_min) / (mi_max - mi_min)
        else:
            df["Normalized_Mismatch"] = 0.0
    return df.sort_values("Economic_Cost").reset_index(drop=True)


def _select_budget_point(df: pd.DataFrame, target_cost: float, tolerance: float = 0.05) -> pd.Series:
    affordable = df[df["Economic_Cost"] <= target_cost * (1.0 + tolerance)]
    if len(affordable) > 0 and "Matching_Index" in affordable.columns:
        return affordable.sort_values(["Matching_Index", "Economic_Cost"]).iloc[0]
    if len(affordable) > 0:
        return affordable.sort_values("Economic_Cost").iloc[0]
    return df.iloc[(df["Economic_Cost"] - target_cost).abs().argmin()]


def export_supporting_csvs(
    eco_df: pd.DataFrame,
    std_df: pd.DataFrame,
    iemi_df: pd.DataFrame,
    budget_df: pd.DataFrame,
) -> None:
    base_cost = float(eco_df["Economic_Cost"].min())
    target_cost = 2.0 * base_cost

    selected_rows = [
        {
            "design": "Economic optimum",
            "budget_case": "Baseline",
            "annual_cost_EUR": float(eco_df["Economic_Cost"].min()),
            "PV_kW": float(eco_df.iloc[0]["PV"]),
            "WT_kW": float(eco_df.iloc[0]["WT"]),
            "GT_kW": float(eco_df.iloc[0]["GT"]),
            "HP_kW": float(eco_df.iloc[0]["HP"]),
            "EC_kW": float(eco_df.iloc[0]["EC"]),
            "AC_kW": float(eco_df.iloc[0]["AC"]),
            "HS_kW": float(eco_df.iloc[0]["HS"]),
            "CS_kW": float(eco_df.iloc[0]["CS"]),
        }
    ]

    for label, df in [("Std", std_df), ("IEMI", iemi_df)]:
        row = _select_budget_point(df, target_cost)
        selected_rows.append(
            {
                "design": label,
                "budget_case": "+100% allowance",
                "annual_cost_EUR": float(row["Economic_Cost"]),
                "PV_kW": float(row["PV"]),
                "WT_kW": float(row["WT"]),
                "GT_kW": float(row["GT"]),
                "HP_kW": float(row["HP"]),
                "EC_kW": float(row["EC"]),
                "AC_kW": float(row["AC"]),
                "HS_kW": float(row["HS"]),
                "CS_kW": float(row["CS"]),
            }
        )

    pd.DataFrame(selected_rows).to_csv(
        DATA_DIR / "conference_selected_capacities.csv",
        index=False,
    )

    budget_export = budget_df.copy()
    budget_export["budget_pct"] = budget_export["cost_level"].map({
        1: 0,
        2: 10,
        3: 30,
        4: 50,
        5: 100,
    })
    budget_export["method_plot"] = budget_export["method"].map({
        "Std": "Std",
        "Euclidean": "IEMI",
    })
    budget_export = budget_export[budget_export["method_plot"].notna()].copy()
    budget_export = budget_export.sort_values(["budget_pct", "method_plot"])
    budget_export.to_csv(DATA_DIR / "conference_budget_path.csv", index=False)


def make_pareto_figure(
    eco_df: pd.DataFrame,
    std_df: pd.DataFrame,
    iemi_df: pd.DataFrame,
) -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    ax.plot(
        std_df["Economic_Cost_kEUR"],
        std_df["Normalized_Mismatch"],
        color=COLORS["Std"],
        marker="o",
        markersize=3.2,
        linewidth=1.4,
        label="Std (normalized within method)",
    )
    ax.plot(
        iemi_df["Economic_Cost_kEUR"],
        iemi_df["Normalized_Mismatch"],
        color=COLORS["IEMI"],
        marker="s",
        markersize=3.2,
        linewidth=1.4,
        label="IEMI (normalized within method)",
    )

    eco_cost = float(eco_df["Economic_Cost"].min()) / 1000.0
    ax.axvline(
        eco_cost,
        color=COLORS["Economic"],
        linestyle="--",
        linewidth=1.4,
        label="Economic optimum",
    )
    ax.annotate(
        "Economic optimum",
        xy=(eco_cost, 0.93),
        xytext=(eco_cost + 45, 0.97),
        arrowprops={"arrowstyle": "-", "color": COLORS["Economic"], "lw": 1.0},
        color=COLORS["Economic"],
        fontsize=8,
    )

    ax.set_xlim(400, 1800)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Annualized cost (kEUR)")
    ax.set_ylabel("Normalized matching score")
    ax.set_title("Pareto-front progression on the German benchmark")
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "pareto_normalized.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIG_DIR / "pareto_normalized.pdf", bbox_inches="tight")
    plt.close(fig)


def make_budget_figure(budget_df: pd.DataFrame) -> None:
    plot_df = budget_df.copy()
    plot_df["budget_pct"] = plot_df["cost_level"].map({
        1: 0,
        2: 10,
        3: 30,
        4: 50,
        5: 100,
    })
    plot_df["method_plot"] = plot_df["method"].map({
        "Std": "Std",
        "Euclidean": "IEMI",
    })
    plot_df = plot_df[plot_df["method_plot"].notna()].copy()
    plot_df = plot_df.sort_values(["method_plot", "budget_pct"])

    fig, axes = plt.subplots(2, 2, figsize=(6.8, 5.4), sharex=True)
    panels = [
        ("annual_cost", "Selected cost (kEUR)", 1 / 1000.0),
        ("peak_grid_kW", "Peak grid import (kW)", 1.0),
        ("annual_grid_purchase_MWh", "Annual grid purchase (MWh)", 1.0),
        ("self_sufficiency_%", "Self-sufficiency (%)", 1.0),
    ]

    for ax, (column, ylabel, scale) in zip(axes.flat, panels):
        for method in ["Std", "IEMI"]:
            subset = plot_df[plot_df["method_plot"] == method]
            ax.plot(
                subset["budget_pct"],
                subset[column] * scale,
                marker="o" if method == "Std" else "s",
                markersize=4,
                linewidth=1.6,
                color=COLORS[method],
                label=method,
            )
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)

    axes[1, 0].set_xlabel("Budget allowance (%)")
    axes[1, 1].set_xlabel("Budget allowance (%)")
    axes[0, 0].legend(frameon=False, loc="best", fontsize=8)
    fig.suptitle("Budget sweep of full-year operational indicators", y=1.02, fontsize=10)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "budget_sweep.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIG_DIR / "budget_sweep.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    eco_df = _read_pareto("economic_only", "Pareto_Economic_only.csv")
    std_df = _read_pareto("std", "Pareto_Std.csv")
    iemi_df = _read_pareto("euclidean", "Pareto_Euclidean.csv")
    budget_df = pd.read_csv(POST_DIR / "post_analysis_budget.csv")

    export_supporting_csvs(eco_df, std_df, iemi_df, budget_df)
    make_pareto_figure(eco_df, std_df, iemi_df)
    make_budget_figure(budget_df)

    print(f"Wrote figures to {FIG_DIR}")
    print(f"Wrote supporting CSVs to {DATA_DIR}")


if __name__ == "__main__":
    main()
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
