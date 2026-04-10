# -*- coding: utf-8 -*-
"""
run_pipeline.py — 一键运行"优化 + 后验分析"完整流程
====================================================

用法：
  uv run python run_pipeline.py --test       # 测试模式（验证流程，~3分钟）
  uv run python run_pipeline.py --quick      # 快速模式（初步结果，~15分钟）
  uv run python run_pipeline.py --medium     # 中等模式（较可靠结果，~40分钟）
  uv run python run_pipeline.py --full       # 正式模式（论文级结果，~2-4小时）

  可选参数：
  --case german|songshan_lake   选择案例（默认 german）
  --skip-optimize               跳过优化，只跑后验分析（需指定 --result-dir）
  --result-dir DIR              指定已有结果目录（跳过优化时必须）
  --workers N                   并行进程数
  --cost-levels N               后验分析的成本水平数（默认3）

流程：
  Phase 1: 跑 exp1（5种方法的 NSGA-II 优化）
  Phase 2: 后验分析（从 Pareto 前沿选方案，跑 8760h 调度，算运行指标）
  Phase 3: 生成对比报告
"""

import sys
import os
import io
import time
import argparse
import datetime

# 编码修复
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ.setdefault("GRB_LICENSE_FILE", r"C:\Users\ikun\gurobi.lic")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── 四种模式参数 ─────────────────────────────────────────────────────────
PIPELINE_MODES = {
    "test": {
        "desc": "测试模式 — 验证流程是否跑通（~3分钟）",
        "nind": 10,
        "maxgen": 5,
        "methods": ["economic_only", "std", "euclidean"],
        "cost_levels": 2,
        "post_analysis_days": 14,  # 只跑14天（典型日）加速验证
    },
    "quick": {
        "desc": "快速模式 — 初步结果，看趋势（~15分钟）",
        "nind": 20,
        "maxgen": 20,
        "methods": ["economic_only", "std", "euclidean"],
        "cost_levels": 2,
        "post_analysis_days": 365,
    },
    "medium": {
        "desc": "中等模式 — 较可靠结果（~40分钟）",
        "nind": 30,
        "maxgen": 50,
        "methods": ["economic_only", "std", "euclidean", "ssr"],
        "cost_levels": 3,
        "post_analysis_days": 365,
    },
    "full": {
        "desc": "正式模式 — 论文级结果（~2-4小时）",
        "nind": 50,
        "maxgen": 100,
        "methods": ["economic_only", "std", "euclidean", "pearson", "ssr"],
        "cost_levels": 3,
        "post_analysis_days": 365,
    },
}

METHOD_FOLDER = {
    "economic_only": "Economic_only",
    "std": "Std",
    "euclidean": "Euclidean",
    "pearson": "Pearson",
    "ssr": "SSR",
}


# ── Phase 1: 优化 ────────────────────────────────────────────────────────
def run_optimization(case_name, nind, maxgen, methods, num_workers=None):
    """运行 NSGA-II 优化，返回结果目录路径"""
    from cchp_gasolution import run_comparative_study
    from case_config import get_case

    case_config = get_case(case_name)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir_name = f"pipeline_{case_name}_{nind}x{maxgen}_{len(methods)}methods_{timestamp}"

    print("\n" + "=" * 70)
    print("  Phase 1: NSGA-II 优化")
    print("=" * 70)
    print(f"  案例: {case_config['description']}")
    print(f"  能质系数: λ_e={case_config['lambda_e']:.3f}, λ_h={case_config['lambda_h']:.3f}, λ_c={case_config['lambda_c']:.3f}")
    print(f"  参数: nind={nind}, maxgen={maxgen}")
    print(f"  方法: {methods}")

    t0 = time.time()
    results, result_dir = run_comparative_study(
        nind=nind,
        maxgen=maxgen,
        pool_type="Process",
        inherit_population=True,
        methods_to_run=methods,
        case_config=case_config,
        num_workers=num_workers,
        result_dir_name=result_dir_name,
    )
    elapsed = time.time() - t0

    print(f"\n  Phase 1 完成，耗时 {elapsed/60:.1f} 分钟")
    print(f"  结果目录: {result_dir}")

    return result_dir, case_config


# ── Phase 2: 后验分析 ────────────────────────────────────────────────────
def run_post_analysis(result_dir, case_config, methods, cost_levels=3, max_days=365):
    """从 Pareto 前沿选方案，跑调度，算运行指标。同时跑两种对比模式。"""
    import pandas as pd
    import numpy as np
    from pathlib import Path
    from scripts.post_analysis import (
        load_pareto_solutions,
        select_solutions_at_cost_levels,
        select_solutions_by_budget_increment,
        run_8760h_simulation,
    )

    print("\n" + "=" * 70)
    print("  Phase 2: 后验运行指标分析")
    print("=" * 70)

    result_path = Path(result_dir)

    # 加载 Pareto 前沿
    print("\n加载 Pareto 前沿:")
    pareto_dfs = {}
    for method in methods:
        folder = METHOD_FOLDER.get(method, method.capitalize())
        df = load_pareto_solutions(result_path, folder)
        if df is not None:
            pareto_dfs[folder] = df

    if not pareto_dfs:
        print("  错误: 没有找到任何 Pareto 结果")
        return None, None

    # ── 模式1: 绝对成本水平对齐 ──
    print("\n" + "─" * 50)
    print("  对比模式1: 绝对成本水平对齐")
    print("─" * 50)
    selected_abs = select_solutions_at_cost_levels(pareto_dfs, cost_levels)

    # ── 模式2: 预算增量对齐（以 economic_only 为基准）──
    print("\n" + "─" * 50)
    print("  对比模式2: 预算增量对齐（以单目标最优为基准）")
    print("─" * 50)
    eco_folder = [f for f in pareto_dfs if "conomic" in f]
    if eco_folder:
        base_cost = pareto_dfs[eco_folder[0]]["Economic_Cost"].min()
    else:
        base_cost = min(df["Economic_Cost"].min() for df in pareto_dfs.values())

    selected_budget = select_solutions_by_budget_increment(
        pareto_dfs, base_cost, increments=[0.0, 0.1, 0.3, 0.5, 1.0]
    )

    # ── 合并去重，跑调度 ──
    all_selected = selected_abs + selected_budget
    # 用 (method, actual_cost) 去重
    seen = set()
    unique_selected = []
    for s in all_selected:
        key = (s["method"], round(s["actual_cost"], 0))
        if key not in seen:
            seen.add(key)
            unique_selected.append(s)

    days_desc = f"{max_days}天" if max_days == 365 else f"{max_days}天（快速验证）"
    print(f"\n运行调度模拟（{days_desc}，共 {len(unique_selected)} 个方案，去重后）")

    # 跑调度，缓存结果
    metrics_cache = {}
    t0 = time.time()
    for i, sol_info in enumerate(unique_selected):
        label = sol_info.get("budget_label", f"水平{sol_info['cost_level']}")
        key = (sol_info["method"], round(sol_info["actual_cost"], 0))
        print(f"\n  [{i+1}/{len(unique_selected)}] {sol_info['method']} (成本={sol_info['actual_cost']:,.0f})")

        if max_days < 365:
            metrics = _run_partial_simulation(sol_info["solution"], case_config, max_days)
        else:
            metrics = run_8760h_simulation(sol_info["solution"], case_config)

        metrics_cache[key] = metrics
        print(f"    峰值购电: {metrics['peak_grid_kW']:.1f} kW | "
              f"年购电量: {metrics['annual_grid_purchase_MWh']:.1f} MWh | "
              f"自给自足率: {metrics['self_sufficiency_%']:.1f}%")

    elapsed = time.time() - t0
    print(f"\n  调度模拟完成，耗时 {elapsed/60:.1f} 分钟")

    # 组装两种模式的结果
    def build_results(selected_list, tag):
        rows = []
        for s in selected_list:
            key = (s["method"], round(s["actual_cost"], 0))
            m = metrics_cache.get(key, {})
            rows.append({
                "mode": tag,
                "cost_level": s["cost_level"],
                "budget_label": s.get("budget_label", f"Level{s['cost_level']}"),
                "method": s["method"],
                "annual_cost": s["actual_cost"],
                "matching_index": s["matching_index"],
                **m,
            })
        return pd.DataFrame(rows)

    df_abs = build_results(selected_abs, "absolute")
    df_budget = build_results(selected_budget, "budget_increment")

    # 保存
    df_all = pd.concat([df_abs, df_budget], ignore_index=True)
    df_all.to_csv(result_path / "post_analysis_results.csv", index=False)
    df_budget.to_csv(result_path / "post_analysis_budget.csv", index=False)

    return df_abs, df_budget


def _run_partial_simulation(solution_row, case_config, max_days):
    """快速版：只跑前 max_days 天，按比例估算年化值"""
    import pandas as pd
    import numpy as np
    import datetime as dt
    from cchp_gaproblem import cal_solar_output, cal_wind_output
    from operation import OperationModel

    ppv = solution_row["PV"]
    pwt = solution_row["WT"]
    pgt = solution_row["GT"]
    php = solution_row["HP"]
    pec = solution_row["EC"]
    pac = solution_row["AC"]
    pes = solution_row["ES"]
    phs = solution_row["HS"]
    pcs = solution_row["CS"]
    cb_power = solution_row.get("CB_Power", 0) or 0
    cb_capacity = solution_row.get("CB_Capacity", 0) or 0

    operation_data = pd.read_csv(case_config["data_file"])
    time_step = 24
    ele_price = case_config["ele_price"][:time_step]
    gas_price = case_config["gas_price"][:time_step]

    total_grid_purchase = 0
    total_ele_overflow = 0
    total_pv_output = 0
    total_wt_output = 0
    total_ele_load = 0
    total_heat_load = 0
    total_cool_load = 0
    peak_grid = 0
    grid_power_series = []
    days_run = 0

    # 均匀采样 max_days 天
    day_indices = np.linspace(0, 364, max_days, dtype=int)

    for day in day_indices:
        start_idx = day * 24
        day_data = operation_data.iloc[start_idx:start_idx + 24]
        if len(day_data) < 24:
            continue

        ele_load = day_data["ele_load(kW)"].values
        heat_load = day_data["heat_load(kW)"].values
        cool_load = day_data["cool_load(kW)"].values
        solar_rad = day_data["solarRadiation(W/m-2)"].values
        wind_spd = day_data["windSpeed(m/s)"].values
        temp = day_data["temperature(C)"].values

        date_obj = dt.date(2019, 1, 1) + dt.timedelta(days=int(day))
        date_str = date_obj.strftime("%m/%d/%Y")

        pv_output = cal_solar_output(solar_rad.tolist(), temp.tolist(), ppv)
        wt_output = cal_wind_output(wind_spd.tolist(), pwt)

        try:
            model = OperationModel(
                date_str, time_step, ele_price, gas_price,
                ele_load.tolist(), heat_load.tolist(), cool_load.tolist(),
                wt_output, pv_output,
                pgt, php, pec, pac, pes, phs, pcs,
                config=case_config, cb_power=cb_power, cb_capacity=cb_capacity,
            )
            model.optimise()
            results = model.get_complementary_results()

            for h in range(24):
                grid_val = results["grid"][h]
                total_grid_purchase += max(0, grid_val)
                total_ele_overflow += results["electricity overflow"][h]
                total_pv_output += pv_output[h]
                total_wt_output += wt_output[h]
                total_ele_load += ele_load[h]
                total_heat_load += heat_load[h]
                total_cool_load += cool_load[h]
                if grid_val > peak_grid:
                    peak_grid = grid_val
                grid_power_series.append(grid_val)

            days_run += 1
        except Exception:
            continue

    # 按比例估算年化值
    scale = 365.0 / max(days_run, 1)
    total_renewable = total_pv_output + total_wt_output
    curtailment = (total_ele_overflow / total_renewable * 100) if total_renewable > 0 else 0
    total_demand = total_ele_load + total_heat_load + total_cool_load
    ssr = (1 - total_grid_purchase / total_demand) * 100 if total_demand > 0 else 0

    return {
        "peak_grid_kW": peak_grid,
        "annual_grid_purchase_MWh": total_grid_purchase * scale / 1000,
        "curtailment_rate_%": curtailment,
        "self_sufficiency_%": ssr,
        "grid_volatility_kW": np.std(grid_power_series) if grid_power_series else 0,
        "total_ele_overflow_MWh": total_ele_overflow * scale / 1000,
        "total_heat_overflow_MWh": 0,
        "total_cool_overflow_MWh": 0,
    }


# ── Phase 3: 报告 ────────────────────────────────────────────────────────
def print_comparison_report(df_abs, df_budget):
    """打印两种对比模式的报告"""
    print("\n" + "=" * 70)
    print("  Phase 3: 运行指标对比报告")
    print("=" * 70)

    # ── 报告A: 绝对成本水平对齐 ──
    if df_abs is not None and len(df_abs) > 0:
        print("\n" + "=" * 70)
        print("  [报告A] 绝对成本水平对齐")
        print("=" * 70)
        _print_table(df_abs, label_col="cost_level", label_prefix="成本水平 ")

    # ── 报告B: 预算增量对齐（核心报告）──
    if df_budget is not None and len(df_budget) > 0:
        print("\n" + "=" * 70)
        print("  [报告B] 预算增量对齐（以单目标最优为基准）")
        print("  问题：每多花 X% 的钱，各方法能把运行指标改善多少？")
        print("=" * 70)
        _print_table(df_budget, label_col="budget_label")


def _print_table(df, label_col="cost_level", label_prefix=""):
    """通用表格打印"""
    for level in sorted(df[label_col].unique(), key=str):
        level_data = df[df[label_col] == level]
        if len(level_data) == 0:
            continue

        print(f"\n{'─'*70}")
        print(f"  {label_prefix}{level}")
        print(f"{'─'*70}")

        for _, row in level_data.iterrows():
            print(f"\n  {row['method']:15s}")
            print(f"    年化成本:    {row['annual_cost']:>12,.0f}")
            print(f"    峰值购电:    {row.get('peak_grid_kW', 0):>12.1f} kW")
            print(f"    年购电量:    {row.get('annual_grid_purchase_MWh', 0):>12.1f} MWh")
            print(f"    弃光率:      {row.get('curtailment_rate_%', 0):>12.2f} %")
            print(f"    自给自足率:  {row.get('self_sufficiency_%', 0):>12.2f} %")
            print(f"    电网波动:    {row.get('grid_volatility_kW', 0):>12.1f} kW")

    print(f"\n{'='*70}")


# ── 主入口 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="一键运行优化+后验分析完整流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  uv run python run_pipeline.py --test           # 测试（~3分钟）
  uv run python run_pipeline.py --quick          # 快速（~15分钟）
  uv run python run_pipeline.py --medium         # 中等（~40分钟）
  uv run python run_pipeline.py --full           # 正式（~2-4小时）

  # 跳过优化，只对已有结果做后验分析：
  uv run python run_pipeline.py --skip-optimize --result-dir Results/xxx --quick
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--test", action="store_const", const="test", dest="mode")
    mode_group.add_argument("--quick", action="store_const", const="quick", dest="mode")
    mode_group.add_argument("--medium", action="store_const", const="medium", dest="mode")
    mode_group.add_argument("--full", action="store_const", const="full", dest="mode")

    parser.add_argument("--case", default="german", choices=["german", "songshan_lake"])
    parser.add_argument("--skip-optimize", action="store_true",
                        help="跳过优化阶段，只跑后验分析")
    parser.add_argument("--result-dir", help="已有结果目录（--skip-optimize 时必须）")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--cost-levels", type=int, default=None,
                        help="覆盖默认的成本水平数")

    args = parser.parse_args()
    cfg = PIPELINE_MODES[args.mode]
    cost_levels = args.cost_levels or cfg["cost_levels"]

    print("=" * 70)
    print(f"  IES 优化完整流程 — {cfg['desc']}")
    print("=" * 70)
    print(f"  案例: {args.case}")
    print(f"  优化参数: nind={cfg['nind']}, maxgen={cfg['maxgen']}")
    print(f"  方法: {cfg['methods']}")
    print(f"  后验分析: {cost_levels} 个成本水平 + 预算增量模式, {cfg['post_analysis_days']} 天调度")

    t_total = time.time()

    # Phase 1
    if args.skip_optimize:
        if not args.result_dir:
            print("错误: --skip-optimize 需要指定 --result-dir")
            return
        result_dir = args.result_dir
        from case_config import get_case
        case_config = get_case(args.case)
        print(f"\n  跳过优化，使用已有结果: {result_dir}")
    else:
        result_dir, case_config = run_optimization(
            args.case, cfg["nind"], cfg["maxgen"], cfg["methods"], args.workers
        )

    # Phase 2
    df_abs, df_budget = run_post_analysis(
        result_dir, case_config, cfg["methods"],
        cost_levels=cost_levels,
        max_days=cfg["post_analysis_days"],
    )

    # Phase 3
    if df_abs is not None or df_budget is not None:
        print_comparison_report(df_abs, df_budget)

    elapsed_total = time.time() - t_total
    print(f"\n  总耗时: {elapsed_total/60:.1f} 分钟")
    print(f"  结果目录: {result_dir}")
    print(f"  后验分析: {os.path.join(result_dir, 'post_analysis_results.csv')}")


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
