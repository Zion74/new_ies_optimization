# -*- coding: utf-8 -*-
"""
方法 × 场景适用性矩阵 (method-scenario suitability matrix)
==========================================================

把多批正式实验的 Pareto 结果聚合成一张三维评分矩阵：

  行 = 场景 (DE_base / DE_carnot / SL_base / SL_carnot)
  列 = 度量方法 (Economic_only / Std / Euclidean / Pearson / SSR)
  单元格 = (经济性, 可行性鲁棒性, 跨批稳定性)

输出：
  - method_scenario_matrix_long.csv     长表，机读
  - method_scenario_matrix_economy.csv  经济性宽表（cost_min mean）
  - method_scenario_matrix_feasibility.csv 可行性宽表 (1 - infeasibility_rate)
  - method_scenario_matrix_stability.csv 稳定性宽表（cost_min CV%）
  - method_scenario_matrix_report.md    Markdown 主报告
  - method_scenario_matrix_heatmaps.png 三联热力图（若装了 matplotlib）

用法：
  python scripts/method_scenario_matrix.py \
      --batches "Results/服务器结果/paper-batch__exp-all__full__n80__g150__w28__20260417_105519,Results/服务器结果/paper-batch__exp-all__full__n80__g150__w28__20260417_170546" \
      --out "Results/服务器结果"

  # 默认行为：自动扫描 Results/服务器结果/paper-batch__*/，至少需要 1 批
  python scripts/method_scenario_matrix.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
import numpy as np


# 经济成本不可行哨兵阈值（与 phase2_sentinel_filter / post_analysis 保持一致）
INFEASIBLE_THRESHOLD = 1e8

# 场景识别（实验目录名前缀 → 场景代号）。
# exp2a 与 exp1 都覆盖 DE_base 的 std/euclidean，按"信息更丰富者优先"取 exp1，
# 但仍把 exp2a 数据合入 DE_base 用于跨实验交叉一致性检验（多两个样本）。
SCENARIO_OF_EXP = {
    "exp1": "DE_base",
    "exp2a": "DE_base",
    "exp2b": "DE_carnot",
    "exp3": "SL_base",
    "exp4": "SL_carnot",
}
SCENARIO_ORDER = ["DE_base", "DE_carnot", "SL_base", "SL_carnot"]
METHOD_ORDER = ["Economic_only", "Std", "Euclidean", "Pearson", "SSR"]


def parse_exp_id(exp_dir_name: str) -> Optional[str]:
    """从实验目录名提取 expN 编号，例如 'exp2b__german__carnot__...' -> 'exp2b'."""
    m = re.match(r"(exp\d+[a-z]?)__", exp_dir_name)
    return m.group(1) if m else None


def load_pareto(method_dir: Path, method: str) -> Optional[pd.DataFrame]:
    """读 Pareto CSV（兼容 _clean / 原始两种），并就地过滤掉惩罚值。"""
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


def count_infeasible(method_dir: Path, method: str) -> tuple[int, int]:
    """返回 (n_clean, n_infeasible)。优先用哨兵脚本产出的 _infeasible.csv。"""
    raw = method_dir / f"Pareto_{method}.csv"
    inf = method_dir / f"Pareto_{method}_infeasible.csv"
    if raw.exists():
        df_raw = pd.read_csv(raw, index_col=0)
        n_total = len(df_raw)
        if "Economic_Cost" in df_raw.columns:
            n_inf_calc = int((df_raw["Economic_Cost"] > INFEASIBLE_THRESHOLD).sum())
        else:
            n_inf_calc = 0
        n_clean = n_total - n_inf_calc
        return n_clean, n_inf_calc
    # 退化路径：只有 _clean.csv 没有原始（不应发生）
    if (method_dir / f"Pareto_{method}_clean.csv").exists():
        df_clean = pd.read_csv(method_dir / f"Pareto_{method}_clean.csv", index_col=0)
        n_inf = len(pd.read_csv(inf, index_col=0)) if inf.exists() else 0
        return len(df_clean), n_inf
    return 0, 0


def collect_one_batch(batch_dir: Path) -> List[dict]:
    """扫描单个批次目录，对每个 (实验, 方法) 收集原始指标。"""
    rows = []
    for exp_dir in sorted(batch_dir.iterdir()):
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
            n_clean, n_inf = count_infeasible(method_dir, method)
            if df is None or n_clean == 0:
                continue
            cost_min = float(df["Economic_Cost"].min())
            cost_max = float(df["Economic_Cost"].max())
            matching_min = (
                float(df["Matching_Index"].min())
                if "Matching_Index" in df.columns
                else np.nan
            )
            matching_max = (
                float(df["Matching_Index"].max())
                if "Matching_Index" in df.columns
                else np.nan
            )
            n_total = n_clean + n_inf
            infeas_rate = n_inf / n_total if n_total > 0 else 0.0
            rows.append(
                {
                    "batch": batch_dir.name,
                    "exp_id": exp_id,
                    "scenario": scenario,
                    "method": method,
                    "n_pareto_clean": n_clean,
                    "n_pareto_infeasible": n_inf,
                    "infeasibility_rate": infeas_rate,
                    "cost_min": cost_min,
                    "cost_max": cost_max,
                    "matching_min": matching_min,
                    "matching_max": matching_max,
                }
            )
    return rows


def aggregate(long_df: pd.DataFrame) -> pd.DataFrame:
    """按 (scenario, method) 聚合多批多实验，计算均值/CV/可行率。

    注意：DE_base 同时来自 exp1 与 exp2a，两个实验同方法的样本会一起进均值。
    这就是"跨实验+跨批次"双层稳定性合并的版本。
    """
    grouped = long_df.groupby(["scenario", "method"], as_index=False).agg(
        cost_min_mean=("cost_min", "mean"),
        cost_min_std=("cost_min", "std"),
        cost_min_n=("cost_min", "count"),
        infeasibility_rate_mean=("infeasibility_rate", "mean"),
        n_pareto_clean_mean=("n_pareto_clean", "mean"),
        cost_max_mean=("cost_max", "mean"),
        matching_min_mean=("matching_min", "mean"),
        matching_min_std=("matching_min", "std"),
        matching_max_mean=("matching_max", "mean"),
        matching_max_std=("matching_max", "std"),
    )
    grouped["cost_min_cv_pct"] = (
        100.0 * grouped["cost_min_std"] / grouped["cost_min_mean"]
    ).where(grouped["cost_min_mean"] > 0, np.nan)
    grouped["matching_min_cv_pct"] = (
        100.0 * grouped["matching_min_std"] / grouped["matching_min_mean"].abs()
    ).where(grouped["matching_min_mean"].abs() > 0, np.nan)
    grouped["matching_max_cv_pct"] = (
        100.0 * grouped["matching_max_std"] / grouped["matching_max_mean"].abs()
    ).where(grouped["matching_max_mean"].abs() > 0, np.nan)
    grouped["feasibility_rate_mean"] = 1.0 - grouped["infeasibility_rate_mean"]
    return grouped


def to_wide(agg: pd.DataFrame, value_col: str) -> pd.DataFrame:
    pivot = agg.pivot(index="scenario", columns="method", values=value_col)
    return pivot.reindex(index=SCENARIO_ORDER, columns=METHOD_ORDER)


def fmt_cost(v: float) -> str:
    if pd.isna(v):
        return "—"
    if v >= 1e6:
        return f"{v / 1e6:.3f} M"
    if v >= 1e3:
        return f"{v / 1e3:.1f} k"
    return f"{v:.0f}"


def fmt_pct(v: float, digits: int = 2) -> str:
    return "—" if pd.isna(v) else f"{100 * v:.{digits}f}%"


def fmt_cv(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.2f}%"


def render_markdown(
    long_df: pd.DataFrame,
    agg: pd.DataFrame,
    batches: List[Path],
    out_path: Path,
) -> None:
    cost_wide = to_wide(agg, "cost_min_mean")
    feas_wide = to_wide(agg, "feasibility_rate_mean")
    cv_wide = to_wide(agg, "cost_min_cv_pct")
    n_wide = to_wide(agg, "cost_min_n")
    pareto_wide = to_wide(agg, "n_pareto_clean_mean")

    lines: List[str] = []
    lines.append("# Method × Scenario Suitability Matrix")
    lines.append("")
    lines.append(f"- 输入批次数：{len(batches)}")
    for b in batches:
        lines.append(f"  - `{b.as_posix()}`")
    lines.append(f"- 不可行哨兵阈值：`Economic_Cost > {INFEASIBLE_THRESHOLD:.0e}`")
    lines.append(
        "- DE_base 行同时由 `exp1` 与 `exp2a` 贡献（多实验+多批次双层合并）；其余行各自只来自一个实验编号"
    )
    lines.append("")

    lines.append("## 1. 经济性（最低 Pareto 经济成本均值）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [fmt_cost(cost_wide.at[s, m]) for m in METHOD_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "*单位为案例对应货币（DE: €，SL: ¥）；'—' 表示该 (场景, 方法) 组合未运行。*"
    )
    lines.append("")

    lines.append("## 2. 可行性鲁棒性（1 − Pareto 不可行解占比，越高越好）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [fmt_pct(feas_wide.at[s, m]) for m in METHOD_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "*100% 表示所有 Pareto 个体都通过 OEMOF 求解；< 100% 表示 GA 在 Pareto 上保留了 1e9 级惩罚值（被哨兵过滤前的占比）。*"
    )
    lines.append("")

    lines.append("## 3. 跨批次稳定性（cost_min 的变异系数 CV%，越低越稳）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [fmt_cv(cv_wide.at[s, m]) for m in METHOD_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("*CV = std/mean × 100%。CV < 1% 视为稳定；1-3% 边缘；> 3% 不稳。*")
    lines.append("")

    matching_min_cv_wide = to_wide(agg, "matching_min_cv_pct")
    matching_max_cv_wide = to_wide(agg, "matching_max_cv_pct")

    lines.append(
        "## 3b. 匹配度跨批稳定性（matching_min CV%，越低说明 Pareto 形状越稳）"
    )
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [fmt_cv(matching_min_cv_wide.at[s, m]) for m in METHOD_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "*matching_min 是该方法 Pareto 上的'最佳匹配端点'。同方法跨批比较有意义，跨方法不可比（量纲不同）。*"
    )
    lines.append("")

    lines.append("## 3c. 匹配度跨批稳定性（matching_max CV%，最大端点）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [fmt_cv(matching_max_cv_wide.at[s, m]) for m in METHOD_ORDER]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "*matching_max 是 Pareto 上'经济性优先 / 匹配度最差'端点。两端点都稳才能说 Pareto 形状稳。*"
    )
    lines.append("")

    lines.append("## 4. 样本量（参与聚合的批次×实验组合数）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [
            "—" if pd.isna(n_wide.at[s, m]) else f"{int(n_wide.at[s, m])}"
            for m in METHOD_ORDER
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("*DE_base 的列出现 4 是因为 exp1 + exp2a 各两批；其余 = 批次数。*")
    lines.append("")

    lines.append("## 5. Pareto 可行解规模（n_pareto_clean 均值）")
    lines.append("")
    lines.append("| Scenario \\ Method | " + " | ".join(METHOD_ORDER) + " |")
    lines.append("|---" * (len(METHOD_ORDER) + 1) + "|")
    for s in SCENARIO_ORDER:
        row = [s] + [
            "—" if pd.isna(pareto_wide.at[s, m]) else f"{pareto_wide.at[s, m]:.0f}"
            for m in METHOD_ORDER
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 自动解读
    lines.append("## 6. 自动解读（机器生成，请人工校验）")
    lines.append("")
    interp = []

    # 6.1 经济性最优方法（每场景）
    interp.append("**6.1 各场景经济性最优方法（cost_min 最小）**：")
    for s in SCENARIO_ORDER:
        row = cost_wide.loc[s].dropna()
        if row.empty:
            continue
        best_method = row.idxmin()
        best_val = row.min()
        runner_up = row.drop(best_method).min() if len(row) > 1 else np.nan
        gap = (
            (runner_up - best_val) / best_val * 100
            if not pd.isna(runner_up) and best_val > 0
            else np.nan
        )
        gap_str = f"，相对次优 +{gap:.2f}%" if not pd.isna(gap) else ""
        interp.append(f"  - `{s}`: **{best_method}** → {fmt_cost(best_val)}{gap_str}")
    interp.append("")

    # 6.2 可行性鲁棒性短板
    interp.append("**6.2 可行性鲁棒性 < 100% 的组合（GA 把惩罚值塞进了 Pareto）**：")
    bad = agg[agg["infeasibility_rate_mean"] > 0].sort_values(
        "infeasibility_rate_mean", ascending=False
    )
    if bad.empty:
        interp.append("  - 无（所有方法×场景组合都是 100% 可行）")
    else:
        for _, r in bad.iterrows():
            interp.append(
                f"  - `{r['scenario']} × {r['method']}`: "
                f"infeasibility = {fmt_pct(r['infeasibility_rate_mean'])} "
                f"(均值, n={int(r['cost_min_n'])})"
            )
    interp.append("")

    # 6.3 跨批稳定性短板
    interp.append("**6.3 跨批稳定性 CV > 3% 的组合（端点对 GA 随机性敏感）**：")
    unstable = agg[agg["cost_min_cv_pct"] > 3.0].sort_values(
        "cost_min_cv_pct", ascending=False
    )
    if unstable.empty:
        interp.append("  - 无（所有方法×场景组合的 cost_min 跨批 CV < 3%）")
    else:
        for _, r in unstable.iterrows():
            interp.append(
                f"  - `{r['scenario']} × {r['method']}`: "
                f"CV = {fmt_cv(r['cost_min_cv_pct'])} "
                f"(n={int(r['cost_min_n'])})"
            )
    interp.append("")

    # 6.4 匹配度跨批不稳（"经济稳但匹配度漂"）
    interp.append(
        "**6.4 匹配度端点跨批不稳的组合（matching_min CV > 5% 视为 Pareto 形状漂移）**："
    )
    matching_unstable = agg[agg["matching_min_cv_pct"] > 5.0].sort_values(
        "matching_min_cv_pct", ascending=False
    )
    if matching_unstable.empty:
        interp.append("  - 无（所有组合的 matching_min 跨批 CV < 5%）")
    else:
        for _, r in matching_unstable.iterrows():
            interp.append(
                f"  - `{r['scenario']} × {r['method']}`: "
                f"matching_min CV = {fmt_cv(r['matching_min_cv_pct'])}, "
                f"matching_max CV = {fmt_cv(r['matching_max_cv_pct'])} "
                f"(n={int(r['cost_min_n'])})"
            )
    interp.append(
        "  *注：matching_min 跨批不稳意味着 GA 找到的 Pareto 前沿在'匹配度最优端点'上漂移，"
        "即使 cost_min 看起来稳，整条 Pareto 的形状可能并不一致。*"
    )
    interp.append("")

    # 6.5 综合判定（候选 hero method per scenario，四维过滤）
    interp.append(
        "**6.5 综合候选 (经济性最优 ∧ 可行性=100% ∧ cost CV<3% ∧ matching_min CV<5%)**："
    )
    for s in SCENARIO_ORDER:
        candidates = agg[
            (agg["scenario"] == s)
            & (agg["infeasibility_rate_mean"] == 0)
            & (agg["cost_min_cv_pct"].fillna(1e9) < 3.0)
            & (agg["matching_min_cv_pct"].fillna(1e9) < 5.0)
        ]
        if candidates.empty:
            interp.append(f"  - `{s}`: ❌ 无方法同时满足四条件")
            continue
        best = candidates.loc[candidates["cost_min_mean"].idxmin()]
        interp.append(
            f"  - `{s}`: ✓ **{best['method']}** "
            f"(cost={fmt_cost(best['cost_min_mean'])}, "
            f"feas=100%, cost_CV={fmt_cv(best['cost_min_cv_pct'])}, "
            f"match_CV={fmt_cv(best['matching_min_cv_pct'])})"
        )
    interp.append("")

    lines.extend(interp)

    out_path.write_text("\n".join(lines), encoding="utf-8")


def render_heatmaps(agg: pd.DataFrame, out_png: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    cost_wide = to_wide(agg, "cost_min_mean")
    feas_wide = to_wide(agg, "feasibility_rate_mean") * 100  # 转百分比
    cv_wide = to_wide(agg, "cost_min_cv_pct")

    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5))

    panels = [
        (axes[0], cost_wide, "Economic optimum (cost_min mean)", "viridis_r", ".2e"),
        (axes[1], feas_wide, "Feasibility robustness (%)", "RdYlGn", ".0f"),
        (axes[2], cv_wide, "Cross-batch stability (CV %)", "RdYlGn_r", ".2f"),
    ]
    for ax, data, title, cmap, fmt in panels:
        arr = data.values.astype(float)
        im = ax.imshow(arr, cmap=cmap, aspect="auto")
        ax.set_xticks(range(len(METHOD_ORDER)))
        ax.set_xticklabels(METHOD_ORDER, rotation=30, ha="right")
        ax.set_yticks(range(len(SCENARIO_ORDER)))
        ax.set_yticklabels(SCENARIO_ORDER)
        ax.set_title(title)
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                v = arr[i, j]
                if np.isnan(v):
                    ax.text(
                        j, i, "—", ha="center", va="center", fontsize=9, color="gray"
                    )
                else:
                    ax.text(
                        j,
                        i,
                        format(v, fmt),
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="black",
                    )
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle("Method × Scenario Suitability Matrix", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batches",
        type=str,
        default=None,
        help="Comma-separated batch directories. If omitted, auto-scan Results/服务器结果/paper-batch__*/",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="Results/服务器结果",
        help="Output directory for matrix files.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="method_scenario_matrix",
        help="Filename prefix.",
    )
    args = parser.parse_args()

    if args.batches:
        batches = [Path(p.strip()) for p in args.batches.split(",") if p.strip()]
    else:
        root = Path("Results/服务器结果")
        batches = sorted(root.glob("paper-batch__*"))
    batches = [b for b in batches if b.is_dir()]
    if not batches:
        raise SystemExit("[error] No batch directory found.")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[dict] = []
    for b in batches:
        all_rows.extend(collect_one_batch(b))
    long_df = pd.DataFrame(all_rows)
    if long_df.empty:
        raise SystemExit("[error] No (scenario, method) cell collected.")

    agg = aggregate(long_df)

    long_csv = out_dir / f"{args.prefix}_long.csv"
    long_df.to_csv(long_csv, index=False, encoding="utf-8-sig")

    cost_wide = to_wide(agg, "cost_min_mean")
    cost_wide.to_csv(out_dir / f"{args.prefix}_economy.csv", encoding="utf-8-sig")
    to_wide(agg, "feasibility_rate_mean").to_csv(
        out_dir / f"{args.prefix}_feasibility.csv", encoding="utf-8-sig"
    )
    to_wide(agg, "cost_min_cv_pct").to_csv(
        out_dir / f"{args.prefix}_stability.csv", encoding="utf-8-sig"
    )

    md_path = out_dir / f"{args.prefix}_report.md"
    render_markdown(long_df, agg, batches, md_path)

    png_path = out_dir / f"{args.prefix}_heatmaps.png"
    has_png = render_heatmaps(agg, png_path)

    print(f"[ok] long table -> {long_csv}")
    print(f"[ok] markdown   -> {md_path}")
    if has_png:
        print(f"[ok] heatmaps   -> {png_path}")
    else:
        print("[warn] matplotlib not available, heatmaps skipped")


if __name__ == "__main__":
    main()
