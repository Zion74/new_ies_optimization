# -*- coding: utf-8 -*-
"""
后验运行指标分析脚本
====================
从 Pareto 前沿结果中选取方案，用完整 8760 小时数据跑调度，
计算实际运行指标（峰值购电、弃光率、自给自足率等），
证明匹配度优化的实际价值。

用法：
  python scripts/post_analysis.py --result-dir Results/exp1_german_50x100_5methods_20240317_143022
  python scripts/post_analysis.py --result-dir Results/exp1_german_50x100_5methods_20240317_143022 --methods std euclidean
  python scripts/post_analysis.py --result-dir Results/exp1_german_50x100_5methods_20240317_143022 --cost-levels 3
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from operation import OperationModel
from case_config import get_case


def load_pareto_solutions(result_dir, method_name):
    """
    加载某个方法的 Pareto 前沿结果

    Returns
    -------
    pd.DataFrame or None
        列: Solution_ID, Economic_Cost, Matching_Index, PV, WT, GT, HP, EC, AC, ES, HS, CS, [CB_Power, CB_Capacity]
    """
    pareto_file = Path(result_dir) / method_name / f"Pareto_{method_name}.csv"
    if not pareto_file.exists():
        print(f"  警告: 未找到 {pareto_file}")
        return None

    df = pd.read_csv(pareto_file, index_col=0)
    print(f"  加载 {method_name}: {len(df)} 个 Pareto 解")
    return df


def select_solutions_at_cost_levels(pareto_dfs, cost_levels=3):
    """
    在多个方法的 Pareto 前沿中，选取相同成本水平的方案

    Parameters
    ----------
    pareto_dfs : dict
        {method_name: DataFrame}
    cost_levels : int
        要选取的成本水平数量（默认3：低/中/高）

    Returns
    -------
    list of dict
        每个 dict 包含: cost_level, method_name, solution_row
    """
    # 找到所有方法的成本范围交集
    all_costs = []
    for method, df in pareto_dfs.items():
        if df is not None and len(df) > 0:
            all_costs.extend(df["Economic_Cost"].values)

    if not all_costs:
        raise ValueError("没有可用的 Pareto 解")

    cost_min = np.min(all_costs)
    cost_max = np.max(all_costs)

    # 在交集范围内均匀选取成本水平
    if cost_levels == 1:
        target_costs = [np.median(all_costs)]
    else:
        target_costs = np.linspace(cost_min, cost_max, cost_levels)

    print(f"\n选取 {cost_levels} 个成本水平:")
    for i, cost in enumerate(target_costs):
        print(f"  水平 {i+1}: {cost:,.0f}")

    # 对每个成本水平，从每个方法的 Pareto 前沿中找最接近的解
    selected = []
    for i, target_cost in enumerate(target_costs):
        print(f"\n成本水平 {i+1} ({target_cost:,.0f}):")
        for method, df in pareto_dfs.items():
            if df is None or len(df) == 0:
                continue

            # 找最接近 target_cost 的解
            idx = (df["Economic_Cost"] - target_cost).abs().idxmin()
            sol = df.loc[idx]

            selected.append({
                "cost_level": i + 1,
                "target_cost": target_cost,
                "method": method,
                "actual_cost": sol["Economic_Cost"],
                "matching_index": sol.get("Matching_Index", np.nan),
                "solution": sol,
            })

            print(f"  {method:15s}: 成本={sol['Economic_Cost']:,.0f}, 匹配度={sol.get('Matching_Index', 'N/A')}")

    return selected


def run_8760h_simulation(solution_row, case_config):
    """
    用完整 8760 小时数据跑调度模型

    Parameters
    ----------
    solution_row : pd.Series
        Pareto 解的一行，包含设备容量
    case_config : dict
        案例配置

    Returns
    -------
    dict
        运行指标: peak_grid, annual_grid_purchase, curtailment_rate, self_sufficiency, grid_volatility, etc.
    """
    # 提取设备容量
    ppv = solution_row["PV"]
    pwt = solution_row["WT"]
    pgt = solution_row["GT"]
    php = solution_row["HP"]
    pec = solution_row["EC"]
    pac = solution_row["AC"]
    pes = solution_row["ES"]
    phs = solution_row["HS"]
    pcs = solution_row["CS"]

    cb_power = solution_row.get("CB_Power", 0)
    cb_capacity = solution_row.get("CB_Capacity", 0)

    # 加载完整 8760 小时数据
    operation_data = pd.read_csv(case_config["data_file"])

    # 累积指标
    total_grid_purchase = 0
    total_ele_overflow = 0
    total_heat_overflow = 0
    total_cool_overflow = 0
    total_pv_output = 0
    total_wt_output = 0
    total_ele_load = 0
    total_heat_load = 0
    total_cool_load = 0
    peak_grid = 0
    grid_power_series = []

    # 逐日跑调度（365天 × 24小时）
    time_step = 24
    ele_price = case_config["ele_price"][:time_step]
    gas_price = case_config["gas_price"][:time_step]

    from cchp_gaproblem import cal_solar_output, cal_wind_output
    import datetime

    for day in range(365):
        start_idx = day * 24
        end_idx = start_idx + 24

        # 提取当日数据
        day_data = operation_data.iloc[start_idx:end_idx]
        ele_load = day_data["ele_load(kW)"].values
        heat_load = day_data["heat_load(kW)"].values
        cool_load = day_data["cool_load(kW)"].values
        solar_radiation = day_data["solarRadiation(W/m-2)"].values
        wind_speed = day_data["windSpeed(m/s)"].values
        temperature = day_data["temperature(C)"].values

        # 生成合法日期字符串（MM/DD/YYYY）
        date_obj = datetime.date(2019, 1, 1) + datetime.timedelta(days=day)
        date_str = date_obj.strftime("%m/%d/%Y")

        # 计算可再生能源出力
        pv_output = cal_solar_output(solar_radiation.tolist(), temperature.tolist(), ppv)
        wt_output = cal_wind_output(wind_speed.tolist(), pwt)

        # 创建调度模型
        model = OperationModel(
            date_str,
            time_step,
            ele_price,
            gas_price,
            ele_load.tolist(),
            heat_load.tolist(),
            cool_load.tolist(),
            wt_output,
            pv_output,
            pgt, php, pec, pac, pes, phs, pcs,
            config=case_config,
            cb_power=cb_power,
            cb_capacity=cb_capacity,
        )

        try:
            model.optimise()
            results = model.get_complementary_results()

            # 累积指标
            for h in range(24):
                grid_val = results["grid"][h]
                total_grid_purchase += max(0, grid_val)  # 只累积购电
                total_ele_overflow += results["electricity overflow"][h]
                total_heat_overflow += results["heat overflow"][h]
                total_cool_overflow += results["cool overflow"][h]

                total_pv_output += pv_output[h]
                total_wt_output += wt_output[h]
                total_ele_load += ele_load[h]
                total_heat_load += heat_load[h]
                total_cool_load += cool_load[h]

                if grid_val > peak_grid:
                    peak_grid = grid_val

                grid_power_series.append(grid_val)

        except Exception as e:
            print(f"    警告: 第 {day+1} 天调度失败: {e}")
            continue

    # 计算运行指标
    total_renewable_output = total_pv_output + total_wt_output
    curtailment_rate = (total_ele_overflow / total_renewable_output * 100) if total_renewable_output > 0 else 0

    total_external_supply = total_grid_purchase  # 简化：只看电网购入
    total_demand = total_ele_load + total_heat_load + total_cool_load
    self_sufficiency = (1 - total_external_supply / total_demand) * 100 if total_demand > 0 else 0

    grid_volatility = np.std(grid_power_series)

    return {
        "peak_grid_kW": peak_grid,
        "annual_grid_purchase_MWh": total_grid_purchase / 1000,
        "curtailment_rate_%": curtailment_rate,
        "self_sufficiency_%": self_sufficiency,
        "grid_volatility_kW": grid_volatility,
        "total_ele_overflow_MWh": total_ele_overflow / 1000,
        "total_heat_overflow_MWh": total_heat_overflow / 1000,
        "total_cool_overflow_MWh": total_cool_overflow / 1000,
    }


def select_solutions_by_budget_increment(pareto_dfs, base_cost, increments=None):
    """
    以 economic_only 最优成本为基准，按预算增量百分比选取方案

    Parameters
    ----------
    pareto_dfs : dict
        {method_name: DataFrame}
    base_cost : float
        基准成本（economic_only 的最优解成本）
    increments : list of float
        预算增量百分比，如 [0.1, 0.3, 0.5] 表示 +10%, +30%, +50%

    Returns
    -------
    list of dict
    """
    if increments is None:
        increments = [0.0, 0.1, 0.3, 0.5]

    print(f"\n基准成本（单目标最优）: {base_cost:,.0f}")
    print(f"预算增量: {[f'+{x*100:.0f}%' for x in increments]}")

    selected = []
    for i, inc in enumerate(increments):
        target_cost = base_cost * (1 + inc)
        label = f"+{inc*100:.0f}%" if inc > 0 else "基准"
        print(f"\n预算 {label} (目标成本 {target_cost:,.0f}):")

        for method, df in pareto_dfs.items():
            if df is None or len(df) == 0:
                continue

            # 找成本不超过 target_cost 的最佳匹配度解
            # 如果没有不超过的，取最接近的
            affordable = df[df["Economic_Cost"] <= target_cost * 1.05]  # 5%容差
            if len(affordable) > 0:
                if "Matching_Index" in df.columns:
                    idx = affordable["Matching_Index"].idxmin()  # 匹配度越小越好
                else:
                    idx = affordable["Economic_Cost"].idxmin()
            else:
                idx = (df["Economic_Cost"] - target_cost).abs().idxmin()

            sol = df.loc[idx]
            selected.append({
                "cost_level": i + 1,
                "budget_label": label,
                "target_cost": target_cost,
                "method": method,
                "actual_cost": sol["Economic_Cost"],
                "matching_index": sol.get("Matching_Index", np.nan),
                "solution": sol,
            })

            cost_diff = (sol["Economic_Cost"] - base_cost) / base_cost * 100
            print(f"  {method:15s}: 成本={sol['Economic_Cost']:>12,.0f} ({cost_diff:+.1f}%), "
                  f"匹配度={sol.get('Matching_Index', 'N/A')}")

    return selected


def main():
    parser = argparse.ArgumentParser(description="后验运行指标分析")
    parser.add_argument("--result-dir", required=True, help="实验结果目录")
    parser.add_argument("--methods", nargs="+", default=["economic_only", "std", "euclidean"],
                        help="要分析的方法列表")
    parser.add_argument("--cost-levels", type=int, default=3,
                        help="成本水平数量（默认3：低/中/高）")
    parser.add_argument("--case", default="german", choices=["german", "songshan_lake"],
                        help="案例名称")
    parser.add_argument("--budget-mode", action="store_true",
                        help="使用预算增量模式（以economic_only为基准）")
    parser.add_argument("--increments", nargs="+", type=float, default=None,
                        help="预算增量百分比，如 0.1 0.3 0.5 表示 +10%% +30%% +50%%")
    args = parser.parse_args()

    result_dir = Path(args.result_dir)
    if not result_dir.exists():
        print(f"错误: 结果目录不存在: {result_dir}")
        return

    print("=" * 70)
    print("后验运行指标分析")
    print("=" * 70)
    print(f"结果目录: {result_dir}")
    print(f"分析方法: {args.methods}")
    print(f"成本水平: {args.cost_levels}")

    # 加载案例配置
    case_config = get_case(args.case)
    print(f"案例: {case_config['description']}")

    # 加载各方法的 Pareto 前沿
    print("\n加载 Pareto 前沿:")
    pareto_dfs = {}
    for method in args.methods:
        df = load_pareto_solutions(result_dir, method)
        if df is not None:
            pareto_dfs[method] = df

    if not pareto_dfs:
        print("错误: 没有找到任何 Pareto 结果")
        return

    # 选取方案：两种模式
    if args.budget_mode:
        # 预算增量模式：以 economic_only 最优成本为基准
        eco_folder = [f for f in pareto_dfs if "conomic" in f]
        if eco_folder:
            base_cost = pareto_dfs[eco_folder[0]]["Economic_Cost"].min()
        else:
            # 没有 economic_only，取所有方法的最低成本
            base_cost = min(df["Economic_Cost"].min() for df in pareto_dfs.values())

        increments = args.increments or [0.0, 0.1, 0.3, 0.5, 1.0]
        selected_solutions = select_solutions_by_budget_increment(
            pareto_dfs, base_cost, increments
        )
    else:
        selected_solutions = select_solutions_at_cost_levels(pareto_dfs, args.cost_levels)

    # 对每个选出的方案跑 8760h 调度
    print("\n" + "=" * 70)
    print("运行 8760 小时调度模拟（这可能需要 10-30 分钟）")
    print("=" * 70)

    results = []
    for i, sol_info in enumerate(selected_solutions):
        label = sol_info.get("budget_label", f"水平{sol_info['cost_level']}")
        print(f"\n[{i+1}/{len(selected_solutions)}] {sol_info['method']} @ {label}")

        metrics = run_8760h_simulation(sol_info["solution"], case_config)

        results.append({
            "cost_level": sol_info["cost_level"],
            "budget_label": sol_info.get("budget_label", f"Level{sol_info['cost_level']}"),
            "method": sol_info["method"],
            "annual_cost": sol_info["actual_cost"],
            "matching_index": sol_info["matching_index"],
            **metrics,
        })

        print(f"  峰值购电: {metrics['peak_grid_kW']:.1f} kW")
        print(f"  年购电量: {metrics['annual_grid_purchase_MWh']:.1f} MWh")
        print(f"  弃光率: {metrics['curtailment_rate_%']:.2f} %")
        print(f"  自给自足率: {metrics['self_sufficiency_%']:.2f} %")

    # 保存结果
    df_results = pd.DataFrame(results)
    suffix = "_budget" if args.budget_mode else ""
    output_file = result_dir / f"post_analysis_results{suffix}.csv"
    df_results.to_csv(output_file, index=False)
    print(f"\n结果已保存到: {output_file}")

    # 生成对比表
    print("\n" + "=" * 70)
    print("运行指标对比表")
    print("=" * 70)

    for level in sorted(df_results["cost_level"].unique()):
        level_data = df_results[df_results["cost_level"] == level]
        if len(level_data) == 0:
            continue

        label = level_data.iloc[0].get("budget_label", f"Level {level}")
        print(f"\n{'─'*60}")
        print(f"  {label}")
        print(f"{'─'*60}")
        for _, row in level_data.iterrows():
            print(f"  {row['method']:15s} | 成本={row['annual_cost']:>10,.0f} | "
                  f"峰值购电={row['peak_grid_kW']:>7.0f}kW | "
                  f"年购电={row['annual_grid_purchase_MWh']:>8.0f}MWh | "
                  f"自给率={row['self_sufficiency_%']:>5.1f}%")

    print("\n分析完成！")


if __name__ == "__main__":
    main()
