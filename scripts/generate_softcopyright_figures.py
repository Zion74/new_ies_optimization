from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import patheffects
from matplotlib import font_manager as fm


REPO = Path(__file__).resolve().parents[1]
RESULT_DIR = REPO / "Results" / "test_exp1_10x5_20260318_234055" / "exp1_german_10x5_5methods_20260318_234055"
TEMP_OUT = REPO / "generated_softcopyright_images"
TARGET_OUT = Path(r"D:\OneDrive\研究生\我的成果\软著\源荷匹配软著\images")
FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\simsun.ttc"),
]

METHOD_LABELS = {
    "Economic_only": "Economic",
    "Std": "Std",
    "Euclidean": "Euclidean",
    "Pearson": "Pearson",
    "SSR": "SSR",
}

METHOD_COLORS = {
    "Economic_only": "#5B6572",
    "Std": "#0B7285",
    "Euclidean": "#D9480F",
    "Pearson": "#7B2CBF",
    "SSR": "#2B8A3E",
}


def configure_style() -> None:
    font_name = "DejaVu Sans"
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            fm.fontManager.addfont(str(candidate))
            font_name = fm.FontProperties(fname=str(candidate)).get_name()
            break
    plt.rcParams.update(
        {
            "font.family": font_name,
            "font.sans-serif": [font_name, "DejaVu Sans"],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "#F8FAFC",
            "axes.edgecolor": "#CBD5E1",
            "axes.titlesize": 16,
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "xtick.color": "#334155",
            "ytick.color": "#334155",
            "axes.labelcolor": "#0F172A",
            "grid.color": "#CBD5E1",
            "grid.alpha": 0.65,
        }
    )


def ensure_dirs() -> None:
    TEMP_OUT.mkdir(parents=True, exist_ok=True)
    TARGET_OUT.mkdir(parents=True, exist_ok=True)


def run_help_text() -> str:
    proc = subprocess.run(
        ["uv", "run", "python", "run.py", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def parse_runtime_table(report_text: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    pattern = re.compile(
        r"^\|\s*(?P<scheme>[^|]+?)\s*\|\s*(?P<cost>[^|]+?)\s*\|\s*(?P<match>[^|]+?)\s*\|\s*(?P<time>[^|]+?)\s*\|\s*(?P<count>[^|]+?)\s*\|$"
    )
    method_map = {
        "方案A-单目标经济": "Economic_only",
        "方案B-波动率匹配度(师兄)": "Std",
        "方案C-能质耦合匹配度(本文)": "Euclidean",
        "方案D-皮尔逊相关系数": "Pearson",
        "方案E-供需重叠度SSR": "SSR",
    }
    for line in report_text.splitlines():
        matched = pattern.match(line.strip())
        if not matched:
            continue
        scheme = matched.group("scheme")
        if scheme not in method_map:
            continue
        cost_text = matched.group("cost").replace(",", "").strip()
        match_text = matched.group("match").replace(",", "").strip()
        time_text = matched.group("time").replace(",", "").strip()
        count_text = matched.group("count").replace(",", "").strip()
        rows.append(
            {
                "method": method_map[scheme],
                "runtime_s": float(time_text),
                "pareto_count": int(float(count_text)),
                "min_cost": float(cost_text),
                "best_match": math.nan if match_text == "-" else float(match_text),
            }
        )
    return pd.DataFrame(rows)


def load_data() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    pareto_frames: dict[str, pd.DataFrame] = {}
    for method in METHOD_LABELS:
        csv_path = RESULT_DIR / method / f"Pareto_{method}.csv"
        if csv_path.exists():
            pareto_frames[method] = pd.read_csv(csv_path)
    post = pd.read_csv(RESULT_DIR / "post_analysis_results.csv")
    report = parse_runtime_table((RESULT_DIR / "comparison_report.md").read_text(encoding="utf-8"))
    return pareto_frames, post, report


def save_figure(fig: plt.Figure, name: str) -> None:
    out_path = TEMP_OUT / name
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_cli_help(help_text: str) -> None:
    lines = help_text.splitlines()
    lines = lines[:24]
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor("#0F172A")
    ax.set_facecolor("#111827")
    ax.set_axis_off()

    ax.text(
        0.03,
        0.95,
        "运行命令与参数说明",
        fontsize=20,
        fontweight="bold",
        color="#E2E8F0",
        va="top",
        transform=ax.transAxes,
    )
    ax.text(
        0.03,
        0.90,
        "基于当前仓库 `uv run python run.py --help` 输出整理",
        fontsize=11,
        color="#94A3B8",
        va="top",
        transform=ax.transAxes,
    )

    y = 0.84
    for line in lines:
        color = "#E5E7EB"
        if line.startswith("usage:"):
            color = "#F8FAFC"
        elif line.strip().startswith("--"):
            color = "#93C5FD"
        elif line.strip().startswith("uv run python"):
            color = "#FDBA74"
        ax.text(
            0.04,
            y,
            line,
            fontsize=10,
            color=color,
            va="top",
            transform=ax.transAxes,
        )
        y -= 0.031
        if y < 0.07:
            break

    ax.text(
        0.72,
        0.90,
        "推荐入口",
        fontsize=14,
        fontweight="bold",
        color="#F8FAFC",
        transform=ax.transAxes,
    )
    quick_box = "\n".join(
        [
            "1. 环境检查",
            "   uv run python run.py --check",
            "",
            "2. 论文实验测试",
            "   uv run python run.py --exp 1 --test-run",
            "",
            "3. 自定义配置",
            "   uv run python run.py --mode custom --case songshan_lake",
        ]
    )
    ax.text(
        0.72,
        0.82,
        quick_box,
        fontsize=10,
        color="#E2E8F0",
        va="top",
        transform=ax.transAxes,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "#1E293B", "edgecolor": "#334155"},
    )

    save_figure(fig, "fig-cli-help.png")


def plot_experiment_summary(report_df: pd.DataFrame) -> None:
    methods = [m for m in METHOD_LABELS if m in report_df["method"].tolist()]
    df = report_df.set_index("method").loc[methods].reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)

    colors = [METHOD_COLORS[m] for m in df["method"]]
    labels = [METHOD_LABELS[m] for m in df["method"]]

    axes[0].bar(labels, df["runtime_s"], color=colors, edgecolor="#0F172A", linewidth=0.6)
    axes[0].set_title("预设实验运行耗时")
    axes[0].set_ylabel("耗时 / s")
    axes[0].grid(axis="y")
    for idx, value in enumerate(df["runtime_s"]):
        axes[0].text(idx, value + 0.25, f"{value:.1f}", ha="center", fontsize=10)

    axes[1].bar(labels, df["pareto_count"], color=colors, edgecolor="#0F172A", linewidth=0.6)
    axes[1].set_title("各方法输出的 Pareto 解数量")
    axes[1].set_ylabel("解数量")
    axes[1].grid(axis="y")
    for idx, value in enumerate(df["pareto_count"]):
        axes[1].text(idx, value + 0.2, f"{int(value)}", ha="center", fontsize=10)

    fig.suptitle("exp1 德国案例测试实验概览", fontsize=18, fontweight="bold")
    save_figure(fig, "fig-exp-run.png")


def plot_results_overview(pareto_frames: dict[str, pd.DataFrame]) -> None:
    fig = plt.figure(figsize=(13, 7))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.08, 1.0])
    ax_tree = fig.add_subplot(gs[0, 0])
    ax_bar = fig.add_subplot(gs[0, 1])

    tree_text = "\n".join(
        [
            "Results/test_exp1_10x5_20260318_234055/",
            "  exp1_german_10x5_5methods_20260318_234055/",
            "    Economic_only/",
            "      Pareto_Economic_only.csv",
            "    Std/",
            "      Pareto_Std.csv",
            "    Euclidean/",
            "      Pareto_Euclidean.csv",
            "    Pearson/",
            "      Pareto_Pearson.csv",
            "    SSR/",
            "      Pareto_SSR.csv",
            "    post_analysis_results.csv",
            "    comparison_report.md",
            "    Pareto_Comparison.png",
        ]
    )
    ax_tree.set_axis_off()
    ax_tree.text(
        0.02,
        0.96,
        "结果目录结构",
        fontsize=18,
        fontweight="bold",
        color="#0F172A",
        va="top",
        transform=ax_tree.transAxes,
    )
    ax_tree.text(
        0.02,
        0.88,
        tree_text,
        fontsize=10.5,
        color="#1E293B",
        va="top",
        transform=ax_tree.transAxes,
        bbox={"boxstyle": "round,pad=0.55", "facecolor": "#F8FAFC", "edgecolor": "#CBD5E1"},
    )

    counts = {method: len(df) for method, df in pareto_frames.items()}
    methods = [m for m in METHOD_LABELS if m in counts]
    labels = [METHOD_LABELS[m] for m in methods]
    values = [counts[m] for m in methods]
    colors = [METHOD_COLORS[m] for m in methods]
    ax_bar.barh(labels, values, color=colors, edgecolor="#0F172A", linewidth=0.6)
    ax_bar.set_title("各方法导出的 Pareto 解数量")
    ax_bar.set_xlabel("解数量")
    ax_bar.grid(axis="x")
    for idx, value in enumerate(values):
        ax_bar.text(value + 0.15, idx, str(value), va="center", fontsize=10)

    fig.suptitle("结果文件与输出结构概览", fontsize=18, fontweight="bold")
    save_figure(fig, "fig-results-folder.png")


def plot_pareto_comparison(pareto_frames: dict[str, pd.DataFrame], report_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 7))

    for method in ["Std", "Euclidean", "Pearson", "SSR"]:
        df = pareto_frames[method]
        ax.scatter(
            df["Economic_Cost"] / 1e6,
            df["Matching_Index"],
            s=90,
            alpha=0.82,
            color=METHOD_COLORS[method],
            edgecolor="white",
            linewidth=0.8,
            label=METHOD_LABELS[method],
        )

        best = df.sort_values(["Economic_Cost", "Matching_Index"]).iloc[0]
        ax.text(
            best["Economic_Cost"] / 1e6,
            best["Matching_Index"] + 18,
            METHOD_LABELS[method],
            fontsize=9.5,
            color=METHOD_COLORS[method],
            path_effects=[patheffects.withStroke(linewidth=3, foreground="white")],
        )

    econ_cost = report_df.set_index("method").at["Economic_only", "min_cost"] / 1e6
    ax.axvline(econ_cost, color=METHOD_COLORS["Economic_only"], linestyle="--", linewidth=1.4)
    ax.text(
        econ_cost + 0.005,
        ax.get_ylim()[1] * 0.92,
        f"Economic 仅成本最优\n{econ_cost:.3f} M€",
        fontsize=10,
        color=METHOD_COLORS["Economic_only"],
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#CBD5E1"},
    )

    ax.set_title("德国案例 Pareto 对比结果")
    ax.set_xlabel("年总成本 / 百万欧元")
    ax.set_ylabel("匹配指标")
    ax.grid(True)
    ax.legend(frameon=True, facecolor="white")
    save_figure(fig, "fig-pareto-comparison.png")


def plot_report_dashboard(post_df: pd.DataFrame) -> None:
    methods = ["Economic_only", "Std", "Euclidean"]
    subset = post_df[post_df["method"].isin(methods)].copy()
    subset.sort_values(["method", "cost_level"], inplace=True)

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    axes = axes.flatten()
    metrics = [
        ("annual_cost", "年总成本 / €"),
        ("peak_grid_kW", "峰值购电 / kW"),
        ("self_sufficiency_%", "自给率 / %"),
        ("curtailment_rate_%", "弃风弃光率 / %"),
    ]

    for ax, (metric, ylabel) in zip(axes, metrics):
        for method in methods:
            df = subset[subset["method"] == method]
            ax.plot(
                df["cost_level"],
                df[metric],
                marker="o",
                linewidth=2.2,
                markersize=6,
                color=METHOD_COLORS[method],
                label=METHOD_LABELS[method],
            )
        ax.set_xlabel("成本层级")
        ax.set_ylabel(ylabel)
        ax.grid(True)

    axes[0].set_title("年总成本")
    axes[1].set_title("峰值购电")
    axes[2].set_title("自给率")
    axes[3].set_title("弃风弃光率")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.03))
    fig.suptitle("8760 小时后验分析结果预览", fontsize=18, fontweight="bold")
    save_figure(fig, "fig-report-preview.png")


def copy_to_target() -> None:
    for png in TEMP_OUT.glob("*.png"):
        shutil.copy2(png, TARGET_OUT / png.name)


def main() -> None:
    configure_style()
    ensure_dirs()
    pareto_frames, post_df, report_df = load_data()
    plot_cli_help(run_help_text())
    plot_experiment_summary(report_df)
    plot_results_overview(pareto_frames)
    plot_pareto_comparison(pareto_frames, report_df)
    plot_report_dashboard(post_df)
    generated = len(list(TEMP_OUT.glob("*.png")))
    copy_to_target()
    shutil.rmtree(TEMP_OUT, ignore_errors=True)
    print(f"Generated {generated} figures into {TARGET_OUT}")


if __name__ == "__main__":
    main()
