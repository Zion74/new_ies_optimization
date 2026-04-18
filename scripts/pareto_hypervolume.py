# -*- coding: utf-8 -*-
"""
Pareto 超体积 (Hypervolume) 评估
==================================

对所有正式批次的 Pareto 结果计算 2D 超体积（双目标 minimize：经济成本，匹配度）。

为什么需要 HV：
- 单端点（cost_min / matching_min）对 GA 随机性敏感（参考 method_scenario_matrix
  里 DE_carnot×Euclidean 的 cost_min CV=7.08%、SL×Std 的 matching_min CV=12-20%）；
- HV 是积分量，把整条 Pareto 前沿到参考点的覆盖面积当作"集合质量"打分，
  对单点抖动鲁棒得多；
- 用来回答：Carnot 储能在 DE 与 SL 场景下是否真的拓宽了 Pareto？
  对应比较 HV(exp2b) vs HV(exp2a) 与 HV(exp4) vs HV(exp3)，分方法分批次。

参考点策略：
- 每个 scenario 内，取所有方法所有批次 cost_max × 1.05、matching_max × 1.05
  作为该 scenario 的统一参考点 → 同 scenario 不同方法 / 不同批次 HV 可比；
- 跨 scenario 不可比（量级不同）。

输出：
- pareto_hypervolume_long.csv     长表 (scenario, exp_id, method, batch, hv, ref_*)
- pareto_hypervolume_summary.csv  按 (scenario, method) 聚合 hv mean/std/CV
- pareto_hypervolume_carnot_gain.csv  Carnot 收益对比表
- pareto_hypervolume_report.md   markdown 主报告

用法：
  python scripts/pareto_hypervolume.py
  python scripts/pareto_hypervolume.py --batches "<dir1>,<dir2>"
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


INFEASIBLE_THRESHOLD = 1e8

# 同一 scenario 不同 exp 编号映射；HV 比较以 exp_id 为 key（保留 exp1 / exp2a 区分）
SCENARIO_OF_EXP = {
    "exp1": "DE_base",
    "exp2a": "DE_base",
    "exp2b": "DE_carnot",
    "exp3": "SL_base",
    "exp4": "SL_carnot",
}
EXP_ORDER = ["exp1", "exp2a", "exp2b", "exp3", "exp4"]
METHOD_ORDER = ["Economic_only", "Std", "Euclidean", "Pearson", "SSR"]

# Carnot 收益比较对：(无 carnot exp_id, 有 carnot exp_id)
# DE 侧：exp2a 与 exp2b 是同样的方法集合（std + euclidean），可严格对照；
# 也加上 exp1 vs exp2b（exp1 是 5 方法但取 std/euclidean 子集对照）作为辅助。
# SL 侧：exp3 与 exp4 是同样方法集合（std + euclidean）。
CARNOT_PAIRS = [
    ("exp2a", "exp2b", "DE: exp2a (no Carnot) → exp2b (with Carnot)"),
    ("exp1", "exp2b", "DE: exp1 (no Carnot, 5 methods) → exp2b (with Carnot)"),
    ("exp3", "exp4", "SL: exp3 (no Carnot) → exp4 (with Carnot)"),
]


def parse_exp_id(exp_dir_name: str) -> Optional[str]:
    m = re.match(r"(exp\d+[a-z]?)__", exp_dir_name)
    return m.group(1) if m else None


def load_pareto(method_dir: Path, method: str) -> Optional[pd.DataFrame]:
    """读 Pareto CSV，过滤惩罚值。优先用 _clean.csv（哨兵脚本产出）。"""
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
    """
    双目标最小化下的 2D 超体积。
    points 中每个 (x, y) 都应满足 x < ref_x 且 y < ref_y，否则被裁掉。

    算法：
      1. 过滤掉 dominated 的点；
      2. 按 x 升序排列剩下的非支配前沿；
      3. 求"阶梯下方"到参考点 (ref_x, ref_y) 围成的总面积。
    """
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


def collect_all_runs(batches: List[Path]) -> pd.DataFrame:
    """对每个 (batch, exp, method) 抽出所有可行 Pareto 点。返回长表。"""
    rows = []
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
                # 单目标 economic_only Pareto 退化为单点，HV 无意义，跳过
                if len(df) < 2:
                    continue
                rows.append(
                    {
                        "batch": b.name,
                        "exp_id": exp_id,
                        "scenario": scenario,
                        "method": method,
                        "n_points": len(df),
                        "cost_min": float(df["Economic_Cost"].min()),
                        "cost_max": float(df["Economic_Cost"].max()),
                        "matching_min": float(df["Matching_Index"].min()),
                        "matching_max": float(df["Matching_Index"].max()),
                        "_points": list(
                            zip(
                                df["Economic_Cost"].tolist(),
                                df["Matching_Index"].tolist(),
                            )
                        ),
                    }
                )
    return pd.DataFrame(rows)


def compute_hv(long_df: pd.DataFrame, ref_margin: float = 0.05) -> pd.DataFrame:
    """对每个 (scenario, method, batch, exp_id) 计算 HV，并给出统一参考点。"""
    # 同 scenario 共享同一参考点（取该 scenario 内所有方法所有批次 max 的 (1+margin) 倍）
    ref_table = (
        long_df.groupby("scenario")
        .agg(cost_ref_base=("cost_max", "max"), match_ref_base=("matching_max", "max"))
        .reset_index()
    )
    ref_table["cost_ref"] = ref_table["cost_ref_base"] * (1 + ref_margin)
    ref_table["matching_ref"] = ref_table["match_ref_base"] * (1 + ref_margin)
    ref_map = {
        r["scenario"]: (r["cost_ref"], r["matching_ref"])
        for _, r in ref_table.iterrows()
    }

    out_rows = []
    for _, r in long_df.iterrows():
        ref_x, ref_y = ref_map[r["scenario"]]
        hv = hypervolume_2d(r["_points"], ref_x, ref_y)
        out_rows.append(
            {
                "batch": r["batch"],
                "exp_id": r["exp_id"],
                "scenario": r["scenario"],
                "method": r["method"],
                "n_points": r["n_points"],
                "cost_min": r["cost_min"],
                "matching_min": r["matching_min"],
                "cost_ref": ref_x,
                "matching_ref": ref_y,
                "hv": hv,
                # 归一化 HV：除以 (cost_ref - cost_floor) * (matching_ref - matching_floor)
                # 其中 floor 取该 scenario 全局最小（"最理想角"）
                # 让 HV ∈ [0, 1]，跨场景定性可比
            }
        )
    out = pd.DataFrame(out_rows)

    # 计算每场景"理想角"做归一化
    for s, sub in out.groupby("scenario"):
        cost_floor = long_df[long_df["scenario"] == s]["cost_min"].min()
        match_floor = long_df[long_df["scenario"] == s]["matching_min"].min()
        ref_x, ref_y = ref_map[s]
        denom = (ref_x - cost_floor) * (ref_y - match_floor)
        out.loc[out["scenario"] == s, "hv_norm"] = (
            out.loc[out["scenario"] == s, "hv"] / denom if denom > 0 else np.nan
        )

    return out


def aggregate_hv(hv_df: pd.DataFrame) -> pd.DataFrame:
    """按 (scenario, exp_id, method) 在批次维度聚合（mean/std/CV）。"""
    g = hv_df.groupby(["scenario", "exp_id", "method"], as_index=False).agg(
        hv_mean=("hv", "mean"),
        hv_std=("hv", "std"),
        hv_n=("hv", "count"),
        hv_norm_mean=("hv_norm", "mean"),
        hv_norm_std=("hv_norm", "std"),
    )
    g["hv_cv_pct"] = (100.0 * g["hv_std"] / g["hv_mean"]).where(
        g["hv_mean"] > 0, np.nan
    )
    g["hv_norm_cv_pct"] = (100.0 * g["hv_norm_std"] / g["hv_norm_mean"]).where(
        g["hv_norm_mean"] > 0, np.nan
    )
    return g


def carnot_gain(agg: pd.DataFrame) -> pd.DataFrame:
    """对预定义 (no_carnot_exp, with_carnot_exp) 对，计算 ΔHV%。"""
    rows = []
    for no_exp, with_exp, label in CARNOT_PAIRS:
        sub_no = agg[agg["exp_id"] == no_exp]
        sub_with = agg[agg["exp_id"] == with_exp]
        common_methods = sorted(set(sub_no["method"]) & set(sub_with["method"]))
        for m in common_methods:
            r_no = sub_no[sub_no["method"] == m].iloc[0]
            r_w = sub_with[sub_with["method"] == m].iloc[0]
            hv_no = r_no["hv_norm_mean"]
            hv_w = r_w["hv_norm_mean"]
            d_pct = (
                100.0 * (hv_w - hv_no) / hv_no
                if hv_no and not np.isnan(hv_no)
                else np.nan
            )
            rows.append(
                {
                    "comparison": label,
                    "method": m,
                    "hv_norm_no_carnot": hv_no,
                    "hv_norm_with_carnot": hv_w,
                    "delta_hv_pct": d_pct,
                    "no_carnot_cv_pct": r_no["hv_norm_cv_pct"],
                    "with_carnot_cv_pct": r_w["hv_norm_cv_pct"],
                    "n_batches_no": int(r_no["hv_n"]),
                    "n_batches_with": int(r_w["hv_n"]),
                }
            )
    return pd.DataFrame(rows)


def fmt_hv(v: float) -> str:
    if pd.isna(v):
        return "—"
    return f"{v:.4f}"


def fmt_pct_signed(v: float) -> str:
    if pd.isna(v):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def render_markdown(
    long_df: pd.DataFrame,
    agg: pd.DataFrame,
    gain: pd.DataFrame,
    batches: List[Path],
    out_path: Path,
) -> None:
    lines: List[str] = []
    lines.append("# Pareto Hypervolume 评估")
    lines.append("")
    lines.append(f"- 输入批次数：{len(batches)}")
    for b in batches:
        lines.append(f"  - `{b.as_posix()}`")
    lines.append("- 双目标都是最小化：(Economic_Cost, Matching_Index)")
    lines.append(
        "- 参考点：每场景内所有方法所有批次 cost_max × 1.05, matching_max × 1.05"
    )
    lines.append(
        "- HV 已用每场景的 (ref_x − cost_floor) × (ref_y − matching_floor) 归一化为 hv_norm ∈ [0, 1]"
    )
    lines.append("- Economic_only 是单目标退化为单点，HV 无意义，已跳过")
    lines.append("")

    lines.append("## 1. 各 (实验, 方法) 的归一化 HV（跨批均值 ± CV%）")
    lines.append("")
    lines.append("| Exp | Method | hv_norm 均值 | hv_norm CV% | n batches |")
    lines.append("|---|---|---|---|---|")
    for exp_id in EXP_ORDER:
        sub = agg[agg["exp_id"] == exp_id]
        if sub.empty:
            continue
        for _, r in sub.iterrows():
            cv = r["hv_norm_cv_pct"]
            cv_str = "—" if pd.isna(cv) else f"{cv:.2f}%"
            lines.append(
                f"| {exp_id} | {r['method']} | {fmt_hv(r['hv_norm_mean'])} | "
                f"{cv_str} | "
                f"{int(r['hv_n'])} |"
            )
    lines.append("")
    lines.append(
        "*hv_norm 越高越好（Pareto 前沿覆盖参考矩形的比例越大）。CV% 越低越稳。*"
    )
    lines.append("")

    lines.append("## 2. Carnot 储能价值（ΔHV%）")
    lines.append("")
    if gain.empty:
        lines.append("无可比对（缺少配对数据）。")
    else:
        for cmp_label in gain["comparison"].unique():
            lines.append(f"### {cmp_label}")
            lines.append("")
            lines.append(
                "| Method | hv_norm (no Carnot) | hv_norm (with Carnot) | ΔHV% | CV (no) | CV (with) |"
            )
            lines.append("|---|---|---|---|---|---|")
            for _, r in gain[gain["comparison"] == cmp_label].iterrows():
                cv_no = r["no_carnot_cv_pct"]
                cv_with = r["with_carnot_cv_pct"]
                cv_no_str = "—" if pd.isna(cv_no) else f"{cv_no:.2f}%"
                cv_with_str = "—" if pd.isna(cv_with) else f"{cv_with:.2f}%"
                lines.append(
                    f"| {r['method']} | {fmt_hv(r['hv_norm_no_carnot'])} | "
                    f"{fmt_hv(r['hv_norm_with_carnot'])} | "
                    f"{fmt_pct_signed(r['delta_hv_pct'])} | "
                    f"{cv_no_str} | "
                    f"{cv_with_str} |"
                )
            lines.append("")

    lines.append("## 3. 自动解读（机器生成，请人工校验）")
    lines.append("")

    # 3.1 每场景 hv_norm 排名
    lines.append("**3.1 各 (exp, 方法) 按 hv_norm 排序（同场景内可比）**：")
    for s in sorted(agg["scenario"].unique()):
        sub = agg[agg["scenario"] == s].sort_values("hv_norm_mean", ascending=False)
        lines.append(f"  - **{s}**:")
        for _, r in sub.iterrows():
            cv = r["hv_norm_cv_pct"]
            cv_str = "—" if pd.isna(cv) else f"{cv:.2f}%"
            lines.append(
                f"    - `{r['exp_id']} × {r['method']}`: hv_norm = {fmt_hv(r['hv_norm_mean'])} "
                f"(CV {cv_str})"
            )
    lines.append("")

    # 3.2 Carnot 收益判定
    lines.append("**3.2 Carnot 收益判定（ΔHV > 0 视为 Carnot 拓宽 Pareto）**：")
    if not gain.empty:
        positive = gain[gain["delta_hv_pct"] > 0]
        negative = gain[gain["delta_hv_pct"] <= 0]
        lines.append(
            f"  - Carnot 增益的对比组合（ΔHV > 0）：{len(positive)} / {len(gain)}"
        )
        for _, r in positive.iterrows():
            lines.append(
                f"    - ✓ `{r['comparison']} × {r['method']}`: "
                f"ΔHV = {fmt_pct_signed(r['delta_hv_pct'])}"
            )
        if not negative.empty:
            lines.append("  - Carnot 未增益甚至损益（ΔHV ≤ 0）：")
            for _, r in negative.iterrows():
                lines.append(
                    f"    - ❌ `{r['comparison']} × {r['method']}`: "
                    f"ΔHV = {fmt_pct_signed(r['delta_hv_pct'])}"
                )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batches", type=str, default=None)
    parser.add_argument("--out", type=str, default="Results/服务器结果")
    parser.add_argument("--prefix", type=str, default="pareto_hypervolume")
    parser.add_argument("--ref-margin", type=float, default=0.05)
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

    long_df = collect_all_runs(batches)
    if long_df.empty:
        raise SystemExit("[error] No (scenario, method, batch) collected.")

    hv_df = compute_hv(long_df, ref_margin=args.ref_margin)
    # 落盘 long 表（去掉巨大的 _points 列）
    hv_df.to_csv(
        out_dir / f"{args.prefix}_long.csv",
        index=False,
        encoding="utf-8-sig",
    )

    agg = aggregate_hv(hv_df)
    agg.to_csv(
        out_dir / f"{args.prefix}_summary.csv", index=False, encoding="utf-8-sig"
    )

    gain = carnot_gain(agg)
    gain.to_csv(
        out_dir / f"{args.prefix}_carnot_gain.csv",
        index=False,
        encoding="utf-8-sig",
    )

    md_path = out_dir / f"{args.prefix}_report.md"
    render_markdown(long_df, agg, gain, batches, md_path)

    print(f"[ok] long table -> {out_dir / f'{args.prefix}_long.csv'}")
    print(f"[ok] summary    -> {out_dir / f'{args.prefix}_summary.csv'}")
    print(f"[ok] carnot gain-> {out_dir / f'{args.prefix}_carnot_gain.csv'}")
    print(f"[ok] markdown   -> {md_path}")


if __name__ == "__main__":
    main()
