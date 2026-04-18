# -*- coding: utf-8 -*-
"""
phase2_sentinel_filter.py — Phase 2 结果污染过滤（二次解析）
================================================================

扫描指定结果根目录下所有 `Pareto_*.csv` 与 `post_analysis_results.csv`，
把 GA 惩罚值（对应 OEMOF 不可行解的 "infinite cost" 占位）过滤掉，
生成可直接用于后续对比的 `*_clean.csv`。

背景：
------
2026-04-18 体检两批次 n80×g150 正式结果发现 `euclidean` 方法在松山湖
配置空间里约 20-55% 的 Pareto 解会触发 OEMOF 不可行，被
`cchp_gaproblem.sub_aim_func_cchp()` 赋予 1e9~1e12 级别的惩罚值。这些
惩罚值流入 `Pareto_Euclidean.csv`，再导致 `select_solutions_at_cost_levels()`
以 1e11 作为 cost_max，使 absolute Level 2/3 的 annual_cost 出现
"数百亿/数万亿"的荒唐值，污染 `post_analysis_results.csv` 与所有下游图表。

业务成本上界：德国约 3×10⁶ €，松山湖约 3×10⁶ ¥，均远低于 1e8。
污染解下界：~4×10¹¹，远高于 1e8。1e8 是绝对安全的判别阈值。

输出（per 实验目录）：
---------------------
- `Pareto_<Method>_clean.csv`       只保留 feasible 解
- `Pareto_<Method>_infeasible.csv`  记录被过滤的解（便于审计）
- `post_analysis_results_clean.csv` 加 `is_feasible` 列、infeasible 行剥离
- `post_analysis_infeasible.csv`    被过滤的 absolute Level 2/3 行

输出（per 批次根目录 or 用户指定）：
----------------------------------
- `phase2_sentinel_report.md`       污染占比、阈值、被过滤清单汇总

用法：
-----
扫描单个批次目录（默认）：

    python scripts/phase2_sentinel_filter.py \
        --root "Results/服务器结果/paper-batch__exp-all__full__n80__g150__w28__20260417_170546"

扫描整个 服务器结果/ 下所有 paper-batch__* 批次：

    python scripts/phase2_sentinel_filter.py --scan-all

自定义阈值：

    python scripts/phase2_sentinel_filter.py --root ... --threshold 1e7

不加 --write 时只做 dry-run（只生成报告，不改文件）。
"""

import argparse
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


# 默认阈值：1e8 远大于业务上界（3e6），远小于污染下界（4e11），5 个数量级缓冲
DEFAULT_THRESHOLD = 1e8
SERVER_RESULTS_DIR = Path("Results") / "服务器结果"


def _iter_experiment_dirs(batch_root: Path) -> Iterable[Path]:
    """批次根目录下的 expN__* 子目录"""
    for p in sorted(batch_root.iterdir()):
        if p.is_dir() and p.name.startswith("exp"):
            yield p


def _iter_pareto_files(exp_dir: Path) -> Iterable[Path]:
    """单个实验目录下的 Pareto_*.csv（不含 *_clean/*_infeasible）"""
    for method_dir in sorted(exp_dir.iterdir()):
        if not method_dir.is_dir():
            continue
        for p in sorted(method_dir.glob("Pareto_*.csv")):
            # 跳过我们自己生成的副本
            stem = p.stem
            if stem.endswith("_clean") or stem.endswith("_infeasible"):
                continue
            yield p


def _filter_pareto_csv(
    pareto_file: Path, threshold: float, write: bool
) -> dict:
    """过滤单个 Pareto_*.csv，返回统计"""
    df = pd.read_csv(pareto_file, index_col=0)
    n = len(df)
    if "Economic_Cost" not in df.columns:
        return {
            "path": pareto_file,
            "n": n,
            "n_infeasible": 0,
            "n_clean": n,
            "cost_max": None,
            "cost_max_clean": None,
            "skipped": True,
        }

    mask_infeasible = df["Economic_Cost"] > threshold
    df_clean = df[~mask_infeasible].copy()
    df_infeas = df[mask_infeasible].copy()

    out = {
        "path": pareto_file,
        "n": n,
        "n_infeasible": int(len(df_infeas)),
        "n_clean": int(len(df_clean)),
        "cost_max": float(df["Economic_Cost"].max()) if n else None,
        "cost_max_clean": float(df_clean["Economic_Cost"].max())
        if len(df_clean) > 0
        else None,
        "skipped": False,
    }

    if write and len(df_infeas) > 0:
        clean_path = pareto_file.with_name(pareto_file.stem + "_clean.csv")
        infeas_path = pareto_file.with_name(pareto_file.stem + "_infeasible.csv")
        df_clean.to_csv(clean_path)
        df_infeas.to_csv(infeas_path)
        out["clean_written"] = clean_path
        out["infeas_written"] = infeas_path

    return out


def _filter_post_analysis_csv(
    post_file: Path, threshold: float, write: bool
) -> dict:
    """过滤单个 post_analysis_results.csv，返回统计"""
    df = pd.read_csv(post_file)
    n = len(df)
    if "annual_cost" not in df.columns:
        return {
            "path": post_file,
            "n": n,
            "n_infeasible": 0,
            "n_clean": n,
            "skipped": True,
        }

    df["is_feasible"] = df["annual_cost"] <= threshold
    n_infeas = int((~df["is_feasible"]).sum())

    out = {
        "path": post_file,
        "n": n,
        "n_infeasible": n_infeas,
        "n_clean": n - n_infeas,
        "skipped": False,
    }

    if write:
        clean_path = post_file.with_name(post_file.stem + "_clean.csv")
        infeas_path = post_file.with_name("post_analysis_infeasible.csv")
        df[df["is_feasible"]].drop(columns=["is_feasible"]).to_csv(
            clean_path, index=False
        )
        if n_infeas > 0:
            df[~df["is_feasible"]].drop(columns=["is_feasible"]).to_csv(
                infeas_path, index=False
            )
        out["clean_written"] = clean_path
        if n_infeas > 0:
            out["infeas_written"] = infeas_path

    return out


def process_batch(batch_root: Path, threshold: float, write: bool) -> dict:
    """处理单个批次目录"""
    batch_root = batch_root.resolve()
    if not batch_root.exists() or not batch_root.is_dir():
        return {"error": f"batch_root 不存在或非目录: {batch_root}"}

    batch_summary = {
        "batch_root": batch_root,
        "threshold": threshold,
        "write": write,
        "experiments": [],
    }

    for exp_dir in _iter_experiment_dirs(batch_root):
        exp_entry = {
            "exp_dir": exp_dir,
            "pareto_files": [],
            "post_file": None,
        }

        for pfile in _iter_pareto_files(exp_dir):
            stat = _filter_pareto_csv(pfile, threshold, write)
            exp_entry["pareto_files"].append(stat)

        post_file = exp_dir / "post_analysis_results.csv"
        if post_file.exists():
            exp_entry["post_file"] = _filter_post_analysis_csv(
                post_file, threshold, write
            )

        batch_summary["experiments"].append(exp_entry)

    return batch_summary


def write_batch_report(summary: dict, report_path: Path) -> None:
    """把批次汇总写成 markdown 报告"""
    lines = []
    lines.append("# Phase 2 哨兵过滤报告\n")
    lines.append(f"- 批次目录：`{summary['batch_root']}`")
    lines.append(f"- 阈值：`Economic_Cost / annual_cost > {summary['threshold']:.1e}` 视为不可行")
    lines.append(f"- 写入模式：`{'ON' if summary['write'] else 'DRY-RUN'}`")
    lines.append("")

    lines.append("## 各实验 Pareto 污染汇总\n")
    lines.append("| 实验 | 方法 | 总数 | 不可行 | 占比 | 原始 cost_max | 过滤后 cost_max |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")

    any_pareto_infeas = False
    for exp_entry in summary["experiments"]:
        exp_name = exp_entry["exp_dir"].name
        for stat in exp_entry["pareto_files"]:
            if stat.get("skipped"):
                continue
            method = stat["path"].parent.name
            ratio = stat["n_infeasible"] / stat["n"] * 100 if stat["n"] else 0
            if stat["n_infeasible"] > 0:
                any_pareto_infeas = True
            cost_max_str = (
                f"{stat['cost_max']:.3e}" if stat["cost_max"] is not None else "-"
            )
            cost_max_clean_str = (
                f"{stat['cost_max_clean']:,.0f}"
                if stat["cost_max_clean"] is not None
                else "-"
            )
            lines.append(
                f"| `{exp_name}` | `{method}` | {stat['n']} | "
                f"{stat['n_infeasible']} | {ratio:.1f}% | "
                f"{cost_max_str} | {cost_max_clean_str} |"
            )

    if not any_pareto_infeas:
        lines.append("\n**所有 Pareto CSV 都干净**，无需过滤。\n")

    lines.append("\n## 各实验 post_analysis_results.csv 污染汇总\n")
    lines.append("| 实验 | 行数 | 不可行行数 | 占比 |")
    lines.append("|---|---:|---:|---:|")

    for exp_entry in summary["experiments"]:
        exp_name = exp_entry["exp_dir"].name
        pf = exp_entry["post_file"]
        if pf is None:
            lines.append(f"| `{exp_name}` | - | - | - (no post_analysis_results.csv) |")
            continue
        if pf.get("skipped"):
            lines.append(f"| `{exp_name}` | {pf['n']} | skipped | - (no annual_cost col) |")
            continue
        ratio = pf["n_infeasible"] / pf["n"] * 100 if pf["n"] else 0
        lines.append(
            f"| `{exp_name}` | {pf['n']} | {pf['n_infeasible']} | {ratio:.1f}% |"
        )

    lines.append("\n## 输出文件清单\n")
    if summary["write"]:
        for exp_entry in summary["experiments"]:
            exp_name = exp_entry["exp_dir"].name
            outputs = []
            for stat in exp_entry["pareto_files"]:
                if stat.get("clean_written"):
                    outputs.append(Path(stat["clean_written"]).name)
                if stat.get("infeas_written"):
                    outputs.append(Path(stat["infeas_written"]).name)
            pf = exp_entry["post_file"]
            if pf and pf.get("clean_written"):
                outputs.append(Path(pf["clean_written"]).name)
            if pf and pf.get("infeas_written"):
                outputs.append(Path(pf["infeas_written"]).name)
            if outputs:
                lines.append(f"### `{exp_name}`")
                for o in outputs:
                    lines.append(f"- {o}")
                lines.append("")
    else:
        lines.append("DRY-RUN 模式，未写入任何文件。加 `--write` 实际生成 `*_clean.csv`。")

    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase 2 结果哨兵过滤（二次解析，不重跑实验）"
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="单个批次目录路径",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="扫描 Results/服务器结果/ 下所有 paper-batch__* 批次",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"不可行解阈值（默认 {DEFAULT_THRESHOLD:.0e}）",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="实际写入 *_clean.csv 与 *_infeasible.csv（默认 dry-run）",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="汇总报告输出位置（默认每个批次目录下 phase2_sentinel_report.md）",
    )
    args = parser.parse_args()

    if not args.root and not args.scan_all:
        parser.error("至少指定 --root 或 --scan-all 其中一个")

    targets: list[Path] = []
    if args.root:
        targets.append(args.root)
    if args.scan_all:
        if not SERVER_RESULTS_DIR.exists():
            parser.error(f"目录不存在: {SERVER_RESULTS_DIR}")
        for p in sorted(SERVER_RESULTS_DIR.iterdir()):
            if p.is_dir() and p.name.startswith("paper-batch__"):
                targets.append(p)

    if not targets:
        parser.error("没有可处理的批次目录")

    for batch_root in targets:
        print(f"\n=== 处理批次: {batch_root} ===")
        summary = process_batch(batch_root, args.threshold, args.write)
        if "error" in summary:
            print(f"  跳过：{summary['error']}")
            continue

        report_path = args.report_path or (batch_root / "phase2_sentinel_report.md")
        write_batch_report(summary, report_path)
        print(f"  报告写入: {report_path}")

        total_infeas = sum(
            s["n_infeasible"]
            for e in summary["experiments"]
            for s in e["pareto_files"]
            if not s.get("skipped")
        )
        print(f"  Pareto 不可行解总数: {total_infeas}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
