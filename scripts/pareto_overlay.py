# -*- coding: utf-8 -*-
"""
Pareto 前沿叠图 (Pareto front overlay)
=======================================

把每个场景下所有方法的 Pareto 前沿（跨批合并）叠画在一张图上，
配套显示每方法的 cost_min / HV / 跨批 CV，作为论文 figure 直接素材。

为什么需要叠图：
- method_scenario_matrix 给的是数值矩阵，HV 给的是积分量，
  但读者最直观感受 Pareto trade-off 是看前沿形状本身。
- 叠图能一眼回答："Std 在 SL 看似 cost_min 低，但 Pareto 又窄又漂；
  Euclidean Pareto 又宽又稳" —— 这个论文叙事直接落到图上。

输出：
  - pareto_overlay_DE_base.png
  - pareto_overlay_DE_carnot.png
  - pareto_overlay_SL_base.png
  - pareto_overlay_SL_carnot.png
  - pareto_overlay_panel.png    (2×2 主图，论文 Figure 用)
  - pareto_overlay_summary.md   伴随说明

用法：
  python scripts/pareto_overlay.py
  python scripts/pareto_overlay.py --batches "<dir1>,<dir2>" --out Results/服务器结果
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import pandas as pd


INFEASIBLE_THRESHOLD = 1e8

SCENARIO_OF_EXP = {
    "exp1": "DE_base",
    "exp2a": "DE_base",
    "exp2b": "DE_carnot",
    "exp3": "SL_base",
    "exp4": "SL_carnot",
}
SCENARIO_ORDER = ["DE_base", "DE_carnot", "SL_base", "SL_carnot"]
SCENARIO_TITLES = {
    "DE_base": "Germany, baseline (no Carnot)",
    "DE_carnot": "Germany, with Carnot battery",
    "SL_base": "Songshan Lake, baseline",
    "SL_carnot": "Songshan Lake, with Carnot battery",
}
METHOD_ORDER = ["Economic_only", "Std", "Euclidean", "Pearson", "SSR"]
METHOD_COLORS = {
    "Economic_only": "#7f7f7f",
    "Std": "#1f77b4",
    "Euclidean": "#d62728",
    "Pearson": "#2ca02c",
    "SSR": "#ff7f0e",
}
METHOD_MARKERS = {
    "Economic_only": "x",
    "Std": "o",
    "Euclidean": "s",
    "Pearson": "^",
    "SSR": "D",
}


def parse_exp_id(name: str) -> Optional[str]:
    m = re.match(r"(exp\d+[a-z]?)__", name)
    return m.group(1) if m else None


def load_pareto(method_dir: Path, method: str) -> Optional[pd.DataFrame]:
    clean = method_dir / f"Pareto_{method}_clean.csv"
    raw = method_dir / f"Pareto_{method}.csv"
    if clean.exists():
        df = pd.read_csv(clean, index_col=0)
    elif raw.exists():
        df = pd.read_csv(raw, index_col=0)
        if "Economic_Cost" in df.columns:
            df = df[df["Economic_Cost"] <= INFEASIBLE_THRESHOLD].copy()
    else:
        return None
    return df if not df.empty else None


def hypervolume_2d(
    points: List[Tuple[float, float]], ref_x: float, ref_y: float
) -> float:
    pts = [(float(x), float(y)) for x, y in points if x < ref_x and y < ref_y]
    if not pts:
        return 0.0
    pts.sort(key=lambda p: (p[0], p[1]))
    front: List[Tuple[float, float]] = []
    best_y = float("inf")
    for x, y in pts:
        if y < best_y:
            front.append((x, y))
            best_y = y
    area = 0.0
    n = len(front)
    for i, (x, y) in enumerate(front):
        x_next = front[i + 1][0] if i + 1 < n else ref_x
        area += (x_next - x) * (ref_y - y)
    return area


def collect_scenario_data(
    batches: List[Path],
) -> Dict[str, Dict[str, List[pd.DataFrame]]]:
    """返回 {scenario: {method: [df_batch1, df_batch2, ...]}}."""
    data: Dict[str, Dict[str, List[pd.DataFrame]]] = {
        s: {m: [] for m in METHOD_ORDER} for s in SCENARIO_ORDER
    }
    for b in batches:
        for exp_dir in sorted(b.iterdir()):
            if not exp_dir.is_dir():
                continue
            exp_id = parse_exp_id(exp_dir.name)
            if exp_id is None or exp_id not in SCENARIO_OF_EXP:
                continue
            scenario = SCENARIO_OF_EXP[exp_id]
            for method in METHOD_ORDER:
                method_dir = exp_dir / method
                if not method_dir.is_dir():
                    continue
                df = load_pareto(method_dir, method)
                if df is None or "Matching_Index" not in df.columns:
                    continue
                if len(df) < 1:
                    continue
                df = df.copy()
                df["_exp_id"] = exp_id
                df["_batch"] = b.name
                data[scenario][method].append(df)
    return data


def plot_one_scenario(ax, scenario: str, methods_data: Dict[str, List[pd.DataFrame]]):
    """在一个 axis 上画一个场景的所有方法 Pareto 叠图。"""
    # 收集所有点用于决定参考点
    all_costs, all_matches = [], []
    for m, dfs in methods_data.items():
        for df in dfs:
            all_costs.extend(df["Economic_Cost"].tolist())
            all_matches.extend(df["Matching_Index"].tolist())
    if not all_costs:
        ax.text(0.5, 0.5, "(no data)", ha="center", va="center", transform=ax.transAxes)
        ax.set_title(SCENARIO_TITLES.get(scenario, scenario))
        return

    cost_max = max(all_costs)
    match_max = max(all_matches)
    ref_x = cost_max * 1.05
    ref_y = match_max * 1.05
    cost_floor = min(all_costs)
    match_floor = min(all_matches)
    denom = (ref_x - cost_floor) * (ref_y - match_floor)

    # 画每方法的 Pareto + 标 HV / cost_min
    legend_labels = []
    for method in METHOD_ORDER:
        dfs = methods_data.get(method, [])
        if not dfs:
            continue
        # 跨批合并散点
        merged = pd.concat(dfs, ignore_index=True)
        # 散点（半透明，区分批次：第一批实心，第二批空心；这里简单全用同色实心）
        ax.scatter(
            merged["Economic_Cost"],
            merged["Matching_Index"],
            s=22,
            alpha=0.45,
            color=METHOD_COLORS.get(method, "#444"),
            marker=METHOD_MARKERS.get(method, "o"),
            edgecolors="none",
        )
        # 画跨批合并后的"非支配前沿"折线
        pts = sorted(
            zip(merged["Economic_Cost"].tolist(), merged["Matching_Index"].tolist()),
            key=lambda p: (p[0], p[1]),
        )
        front_x, front_y = [], []
        best_y = float("inf")
        for x, y in pts:
            if y < best_y:
                front_x.append(x)
                front_y.append(y)
                best_y = y
        if front_x:
            ax.plot(
                front_x,
                front_y,
                color=METHOD_COLORS.get(method, "#444"),
                linewidth=1.4,
                alpha=0.9,
            )
        # 计算 HV（用本场景统一参考点）
        hv = hypervolume_2d(pts, ref_x, ref_y)
        hv_norm = hv / denom if denom > 0 else float("nan")
        cost_min = merged["Economic_Cost"].min()
        n_pts = len(merged)
        # legend label
        legend_labels.append(
            (
                method,
                f"{method}: HV={hv_norm:.3f}, cost_min={cost_min / 1e3:.1f} k, n={n_pts}",
            )
        )

    # 自定义 legend
    from matplotlib.lines import Line2D

    handles = [
        Line2D(
            [0],
            [0],
            color=METHOD_COLORS[m],
            marker=METHOD_MARKERS[m],
            linewidth=1.4,
            markersize=6,
            label=label,
        )
        for m, label in legend_labels
    ]
    ax.legend(handles=handles, fontsize=8, loc="upper right", framealpha=0.85)

    # 参考点叉
    ax.plot(ref_x, ref_y, marker="*", color="black", markersize=10, alpha=0.6)
    ax.annotate(
        " ref",
        (ref_x, ref_y),
        fontsize=7,
        color="black",
        alpha=0.7,
    )

    ax.set_xlabel("Economic cost  (currency / a)")
    ax.set_ylabel("Matching index  (lower is better)")
    ax.set_title(SCENARIO_TITLES.get(scenario, scenario))
    ax.grid(True, alpha=0.3, linestyle=":")


def render_all(
    data: Dict[str, Dict[str, List[pd.DataFrame]]], out_dir: Path, prefix: str
) -> List[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written = []

    # 单场景子图
    for scenario in SCENARIO_ORDER:
        fig, ax = plt.subplots(figsize=(7, 5))
        plot_one_scenario(ax, scenario, data[scenario])
        fig.tight_layout()
        path = out_dir / f"{prefix}_{scenario}.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        written.append(path)

    # 2×2 panel
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for ax, scenario in zip(axes.flat, SCENARIO_ORDER):
        plot_one_scenario(ax, scenario, data[scenario])
    fig.suptitle(
        "Pareto front overlay across methods, scenarios, and batches", fontsize=14
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    panel_path = out_dir / f"{prefix}_panel.png"
    fig.savefig(panel_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    written.append(panel_path)
    return written


def render_summary_md(
    data: Dict[str, Dict[str, List[pd.DataFrame]]],
    written: List[Path],
    batches: List[Path],
    out_path: Path,
):
    lines: List[str] = []
    lines.append("# Pareto 前沿叠图说明")
    lines.append("")
    lines.append(f"- 输入批次数：{len(batches)}")
    for b in batches:
        lines.append(f"  - `{b.as_posix()}`")
    lines.append("")
    lines.append("## 输出文件")
    lines.append("")
    for p in written:
        lines.append(f"- `{p.as_posix()}`")
    lines.append("")
    lines.append("## 图例约定")
    lines.append("")
    lines.append(
        "- 每个场景一张图，X 轴 = 经济成本（越小越好），Y 轴 = 匹配度（越小越好）"
    )
    lines.append("- 散点：跨批所有 Pareto 个体；折线：跨批合并后的非支配前沿")
    lines.append(
        "- 颜色 / 形状区分方法（Economic_only / Std / Euclidean / Pearson / SSR）"
    )
    lines.append("- 图例标注每方法的 HV（归一化）/ cost_min / 跨批合并后散点数 n")
    lines.append(
        "- 黑色 ★ = 该场景的统一 HV 参考点 (cost_max × 1.05, matching_max × 1.05)"
    )
    lines.append("")
    lines.append("## 论文使用建议")
    lines.append("")
    lines.append(
        "- `pareto_overlay_panel.png` 适合作 SCI 稿 results 章节主 figure"
        "（Figure: 跨场景 Pareto 比较，2×2 布局）"
    )
    lines.append(
        "- 单场景图可作 supplementary 或在正文里分别引用，例如 SL_carnot 那张能直接论证"
        "'Std 看似 cost_min 略低但 Pareto 又窄又漂'"
    )
    lines.append(
        "- 跨批散点叠加是稳定性的可视化证据：同方法跨批散点重叠度 = 跨批稳定性"
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches", type=str, default=None)
    parser.add_argument("--out", type=str, default="Results/服务器结果")
    parser.add_argument("--prefix", type=str, default="pareto_overlay")
    args = parser.parse_args()

    if args.batches:
        batches = [Path(p.strip()) for p in args.batches.split(",") if p.strip()]
    else:
        batches = sorted(Path("Results/服务器结果").glob("paper-batch__*"))
    batches = [b for b in batches if b.is_dir()]
    if not batches:
        raise SystemExit("[error] No batch directory found.")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = collect_scenario_data(batches)
    written = render_all(data, out_dir, args.prefix)
    render_summary_md(data, written, batches, out_dir / f"{args.prefix}_summary.md")

    print(f"[ok] {len(written)} figures written under {out_dir}")
    for p in written:
        print(f"     - {p.name}")


if __name__ == "__main__":
    main()
