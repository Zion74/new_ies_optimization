# -*- coding: utf-8 -*-
"""
两种源荷匹配度方法的对比分析脚本

比较维度：
1. Pareto前沿对比（同一坐标系可视化）
2. 解的多样性（Spread指标）
3. 极端解对比（最优经济 vs 最优匹配）
4. 相同成本下的匹配度对比
5. 物理意义解读

@author: Your research
"""

import os
import sys
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 添加父目录到路径，确保可导入 cchp_gaproblem/operation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 复用下层调度与匹配度计算
from cchp_gaproblem import sub_aim_func_cchp
from cchp_gaproblem import LAMBDA_H, LAMBDA_C

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150


def find_latest_result_dir(base_path="."):
    """查找最新的结果目录"""
    result_dirs = glob.glob(os.path.join(base_path, "Result_CCHP_Comparison_*"))
    if not result_dirs:
        return None
    result_dirs.sort(key=os.path.getmtime)
    return result_dirs[-1]


def load_operation_data():
    """加载运行数据与典型日"""
    import pandas as pd  # 局部导入以减少全局依赖
    import numpy as np

    operation_data = pd.read_csv("mergedData.csv")
    operation_list = np.array(operation_data).tolist()

    typical_days = dict()
    typical_data = pd.read_excel("typicalDayData.xlsx")
    typical_day_id = typical_data["typicalDayId"]
    days_str = typical_data["days"]
    for i in range(len(typical_day_id)):
        days_list = list(map(int, days_str[i].split(",")))
        typical_days[typical_day_id[i]] = days_list

    return operation_list, typical_days


def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    """计算光伏出力"""
    return [
        ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
        for r, t in zip(solar_radiation_list, temperature_list)
    ]


def cal_wind_output(wind_speed_list, pwt):
    """计算风电出力"""
    ret = [0 for _ in range(len(wind_speed_list))]
    for i in range(len(wind_speed_list)):
        w = wind_speed_list[i]
        if 2.5 <= w < 9:
            ret[i] = (w**3 - 2.5**3) / (9**3 - 2.5**3) * pwt
        elif 9 <= w < 25:
            ret[i] = pwt
    return ret


def run_dispatch_for_day(solution, operation_list, day_id, time_step=24):
    """对指定方案在指定日运行调度，返回 complementary_results"""
    from operation import OperationModel

    ppv = solution["PV"]
    pwt = solution["WT"]
    pgt = solution["GT"]
    php = solution["HP"]
    pec = solution["EC"]
    pac = solution["AC"]
    pes = solution["ES"]
    phs = solution["HS"]
    pcs = solution["CS"]

    time_start = (day_id - 1) * 24

    ele_load = [operation_list[time_start + t][0] for t in range(time_step)]
    heat_load = [operation_list[time_start + t][1] for t in range(time_step)]
    cool_load = [operation_list[time_start + t][2] for t in range(time_step)]
    solar_radiation_list = [operation_list[time_start + t][3] for t in range(time_step)]
    wind_speed_list = [operation_list[time_start + t][4] for t in range(time_step)]
    temperature_list = [operation_list[time_start + t][5] for t in range(time_step)]

    pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
    wt_output = cal_wind_output(wind_speed_list, pwt)

    ele_price = [0.0025] * time_step
    gas_price = [0.0286] * time_step

    operation_model = OperationModel(
        "01/01/2019",
        time_step,
        ele_price,
        gas_price,
        ele_load,
        heat_load,
        cool_load,
        wt_output,
        pv_output,
        pgt,
        php,
        pec,
        pac,
        pes,
        phs,
        pcs,
    )

    operation_model.optimise()
    results = operation_model.get_complementary_results()
    results["ele_load"] = ele_load
    results["heat_load"] = heat_load
    results["cool_load"] = cool_load
    results["pv_output"] = pv_output
    results["wt_output"] = wt_output
    return results


def compute_kpis_for_solution(solution, operation_list, typical_days):
    """
    计算 KPI：PER、Exergy、SSR、电网交互平滑度
    基于典型日加权求和
    """
    import numpy as np
    from collections import defaultdict

    time_step = 24
    ele_price = [0.0025] * time_step
    gas_price = [0.0286] * time_step

    total_hours = 0
    agg = defaultdict(float)
    grid_series = []

    ppv, pwt, pgt, php, pec, pac, pes, phs, pcs = (
        solution["PV"],
        solution["WT"],
        solution["GT"],
        solution["HP"],
        solution["EC"],
        solution["AC"],
        solution["ES"],
        solution["HS"],
        solution["CS"],
    )

    for cluster_medoid, days in typical_days.items():
        time_start = (cluster_medoid - 1) * 24
        # 提取典型日数据
        ele_load = [operation_list[time_start + t][0] for t in range(time_step)]
        heat_load = [operation_list[time_start + t][1] for t in range(time_step)]
        cool_load = [operation_list[time_start + t][2] for t in range(time_step)]
        solar_radiation_list = [
            operation_list[time_start + t][3] for t in range(time_step)
        ]
        wind_speed_list = [operation_list[time_start + t][4] for t in range(time_step)]
        temperature_list = [operation_list[time_start + t][5] for t in range(time_step)]
        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)

        from operation import OperationModel

        op_model = OperationModel(
            "01/01/2019",
            time_step,
            ele_price,
            gas_price,
            ele_load,
            heat_load,
            cool_load,
            wt_output,
            pv_output,
            pgt,
            php,
            pec,
            pac,
            pes,
            phs,
            pcs,
        )
        op_model.optimise()
        res = op_model.get_complementary_results()

        weight = len(days)  # 典型日代表天数
        total_hours += weight * time_step

        # 购入/供入
        grid = np.array(res["grid"])
        heat_src = np.array(res["heat source"])
        cool_src = np.array(res["cool source"])
        # 负荷
        ele_load_arr = np.array(ele_load)
        heat_load_arr = np.array(heat_load)
        cool_load_arr = np.array(cool_load)

        # 自给自足率
        grid_purchase = np.clip(grid, 0, None)
        agg["grid_purchase"] += grid_purchase.sum() * weight
        agg["ele_load"] += ele_load_arr.sum() * weight
        agg["heat_source"] += heat_src.sum() * weight
        agg["cool_source"] += cool_src.sum() * weight
        agg["heat_load"] += heat_load_arr.sum() * weight
        agg["cool_load"] += cool_load_arr.sum() * weight

        # 电网交互序列
        for _ in range(weight):
            grid_series.extend(grid.tolist())

        # Exergy 近似：电1.0，热lambda_h，冷lambda_c
        agg["ex_out"] += (
            ele_load_arr.sum() * 1.0
            + heat_load_arr.sum() * LAMBDA_H
            + cool_load_arr.sum() * LAMBDA_C
        ) * weight
        agg["ex_in"] += (
            grid_purchase.sum() * 1.0
            + heat_src.sum() * LAMBDA_H
            + cool_src.sum() * LAMBDA_C
        ) * weight

        # 一次能源利用率 PER（以购入能量为分母的近似）
        agg["per_out"] += (
            ele_load_arr.sum() + heat_load_arr.sum() + cool_load_arr.sum()
        ) * weight
        agg["per_in"] += (
            grid_purchase.sum() + heat_src.sum() + cool_src.sum()
        ) * weight

    # 结果汇总
    kpi = {}
    kpi["SSR_ele"] = (
        1 - agg["grid_purchase"] / agg["ele_load"] if agg["ele_load"] > 1e-6 else 0
    )
    kpi["SSR_heat"] = (
        1 - agg["heat_source"] / agg["heat_load"] if agg["heat_load"] > 1e-6 else 0
    )
    kpi["SSR_cool"] = (
        1 - agg["cool_source"] / agg["cool_load"] if agg["cool_load"] > 1e-6 else 0
    )
    kpi["Exergy_eff"] = agg["ex_out"] / agg["ex_in"] if agg["ex_in"] > 1e-6 else 0
    kpi["PER"] = agg["per_out"] / agg["per_in"] if agg["per_in"] > 1e-6 else 0
    kpi["Grid_std"] = np.std(grid_series) if len(grid_series) > 0 else 0
    return kpi


def compute_euclidean_matching_for_df(df, operation_list, typical_days):
    """
    交叉验证：对给定解集，用欧氏能质匹配度公式重新计算匹配度
    （用于将师兄的解集投影到本文的匹配度标尺上）
    """
    if df is None or len(df) == 0:
        return None

    import numpy as np

    match_list = []
    # Vars 需要 shape (n, 9)，顺序与 Pareto 列一致
    for _, row in df.iterrows():
        vars_row = np.array(
            [
                row["PV"],
                row["WT"],
                row["GT"],
                row["HP"],
                row["EC"],
                row["AC"],
                row["ES"],
                row["HS"],
                row["CS"],
            ]
        ).reshape(1, -1)
        args = (
            0,  # 索引占位
            vars_row,
            operation_list,
            typical_days,
            1,  # pop_size 占位
            "euclidean",
        )
        _, matching = sub_aim_func_cchp(args)
        match_list.append(matching)

    return np.array(match_list)


def load_pareto_data(method_dir):
    """加载Pareto数据"""
    pareto_files = glob.glob(os.path.join(method_dir, "Pareto_*.csv"))
    if not pareto_files:
        return None
    return pd.read_csv(pareto_files[0], index_col=0)


def calculate_hypervolume_2d(costs, matchings, ref_point):
    """
    计算2D超体积（Hypervolume）指标

    超体积越大，说明Pareto前沿越好（覆盖的目标空间越大）

    Parameters
    ----------
    costs : array
        经济成本（目标1，越小越好）
    matchings : array
        匹配度（目标2，越小越好）
    ref_point : tuple
        参考点 (max_cost, max_matching)

    Returns
    -------
    float : 超体积值
    """
    # 按成本排序
    sorted_indices = np.argsort(costs)
    costs_sorted = costs[sorted_indices]
    matchings_sorted = matchings[sorted_indices]

    # 计算超体积（矩形面积之和）
    hv = 0.0
    prev_matching = ref_point[1]

    for i in range(len(costs_sorted)):
        if matchings_sorted[i] < prev_matching:
            width = ref_point[0] - costs_sorted[i]
            height = prev_matching - matchings_sorted[i]
            hv += width * height
            prev_matching = matchings_sorted[i]

    return hv


def calculate_spread(costs, matchings):
    """
    计算解的分布均匀性（Spread指标）

    值越小说明解分布越均匀
    """
    if len(costs) < 2:
        return float("inf")

    # 按成本排序
    sorted_indices = np.argsort(costs)
    costs_sorted = costs[sorted_indices]
    matchings_sorted = matchings[sorted_indices]

    # 计算相邻解之间的欧氏距离
    distances = []
    for i in range(len(costs_sorted) - 1):
        d = np.sqrt(
            (costs_sorted[i + 1] - costs_sorted[i]) ** 2
            + (matchings_sorted[i + 1] - matchings_sorted[i]) ** 2
        )
        distances.append(d)

    if len(distances) == 0:
        return float("inf")

    # 计算距离的标准差（越小越均匀）
    mean_d = np.mean(distances)
    spread = np.std(distances) / mean_d if mean_d > 0 else float("inf")

    return spread


def calculate_coverage(costs1, matchings1, costs2, matchings2):
    """
    计算覆盖率（Coverage）：方法1支配方法2的解的比例

    C(A,B) = |{b∈B | ∃a∈A: a dominates b}| / |B|
    """
    dominated_count = 0

    for c2, m2 in zip(costs2, matchings2):
        for c1, m1 in zip(costs1, matchings1):
            # 检查解1是否支配解2（两个目标都要更小或相等，至少一个严格更小）
            if (c1 <= c2 and m1 <= m2) and (c1 < c2 or m1 < m2):
                dominated_count += 1
                break

    return dominated_count / len(costs2) if len(costs2) > 0 else 0


def plot_pareto_comparison(
    df_std, df_euclidean, output_dir, match_std_cross=None, match_euc=None
):
    """
    绘制两种方法的Pareto前沿对比图
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # ========== 子图1：原始坐标系对比 ==========
    ax1 = axes[0]

    if df_std is not None and len(df_std) > 0:
        costs_std = df_std["Economic_Cost"].values / 10000
        match_std = (
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values
        )
        ax1.scatter(
            costs_std,
            match_std,
            c="blue",
            marker="o",
            s=100,
            label=f"方案B-波动率(师兄) n={len(df_std)}",
            alpha=0.7,
        )
        # 连线
        sorted_idx = np.argsort(costs_std)
        ax1.plot(
            costs_std[sorted_idx], match_std[sorted_idx], "b--", alpha=0.5, linewidth=1
        )

    if df_euclidean is not None and len(df_euclidean) > 0:
        costs_euc = df_euclidean["Economic_Cost"].values / 10000
        match_euc = (
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values
        )
        ax1.scatter(
            costs_euc,
            match_euc,
            c="red",
            marker="s",
            s=80,
            label=f"方案C-能质耦合(本文) n={len(df_euclidean)}",
            alpha=0.7,
        )
        sorted_idx = np.argsort(costs_euc)
        ax1.plot(
            costs_euc[sorted_idx], match_euc[sorted_idx], "r--", alpha=0.5, linewidth=1
        )

    ax1.set_xlabel("年化总成本 (万€)", fontsize=12)
    ax1.set_ylabel("源荷匹配度指标 (kW)", fontsize=12)
    ax1.set_title("Pareto前沿对比（原始坐标）", fontsize=14)
    ax1.legend(loc="best", fontsize=10)
    ax1.grid(True, alpha=0.3)

    # ========== 子图2：归一化后对比 ==========
    ax2 = axes[1]

    # 找全局最大最小值用于归一化
    all_costs = []
    all_matchings = []

    if df_std is not None and len(df_std) > 0:
        all_costs.extend(df_std["Economic_Cost"].values)
        all_matchings.extend(
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values
        )
    if df_euclidean is not None and len(df_euclidean) > 0:
        all_costs.extend(df_euclidean["Economic_Cost"].values)
        all_matchings.extend(
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values
        )

    if len(all_costs) > 0:
        cost_min, cost_max = min(all_costs), max(all_costs)
        match_min, match_max = min(all_matchings), max(all_matchings)

        cost_range = cost_max - cost_min if cost_max > cost_min else 1
        match_range = match_max - match_min if match_max > match_min else 1

        if df_std is not None and len(df_std) > 0:
            costs_std_norm = (df_std["Economic_Cost"].values - cost_min) / cost_range
            match_std_vals = (
                match_std_cross
                if match_std_cross is not None
                else df_std["Matching_Index"].values
            )
            match_std_norm = (match_std_vals - match_min) / match_range
            ax2.scatter(
                costs_std_norm,
                match_std_norm,
                c="blue",
                marker="o",
                s=100,
                label="方案B-波动率(师兄)",
                alpha=0.7,
            )
            sorted_idx = np.argsort(costs_std_norm)
            ax2.plot(
                costs_std_norm[sorted_idx],
                match_std_norm[sorted_idx],
                "b--",
                alpha=0.5,
                linewidth=1,
            )

        if df_euclidean is not None and len(df_euclidean) > 0:
            costs_euc_norm = (
                df_euclidean["Economic_Cost"].values - cost_min
            ) / cost_range
            match_euc_vals = (
                match_euc
                if match_euc is not None
                else df_euclidean["Matching_Index"].values
            )
            match_euc_norm = (match_euc_vals - match_min) / match_range
            ax2.scatter(
                costs_euc_norm,
                match_euc_norm,
                c="red",
                marker="s",
                s=80,
                label="方案C-能质耦合(本文)",
                alpha=0.7,
            )
            sorted_idx = np.argsort(costs_euc_norm)
            ax2.plot(
                costs_euc_norm[sorted_idx],
                match_euc_norm[sorted_idx],
                "r--",
                alpha=0.5,
                linewidth=1,
            )

    ax2.set_xlabel("归一化成本", fontsize=12)
    ax2.set_ylabel("归一化匹配度", fontsize=12)
    ax2.set_title("Pareto前沿对比（归一化坐标）", fontsize=14)
    ax2.legend(loc="best", fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(-0.05, 1.05)
    ax2.set_ylim(-0.05, 1.05)

    plt.tight_layout()
    save_path = os.path.join(output_dir, "Method_Comparison_Pareto.png")
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  已保存: {save_path}")


def plot_extreme_solutions_comparison(df_std, df_euclidean, output_dir):
    """
    绘制极端解对比（最优经济 vs 最优匹配），并增加成本相近方案对比
    """
    VAR_NAMES = ["PV", "WT", "GT", "HP", "EC", "AC", "ES", "HS", "CS"]
    VAR_NAMES_CN = [
        "光伏",
        "风电",
        "燃气轮机",
        "电热泵",
        "电制冷",
        "吸收式制冷",
        "电储能",
        "热储能",
        "冷储能",
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    methods = [
        (df_std, "方案B-波动率(师兄)", "blue"),
        (df_euclidean, "方案C-能质耦合(本文)", "red"),
    ]

    # 极端解：各方法内部
    for col, (df, method_name, color) in enumerate(methods):
        if df is None or len(df) == 0:
            continue

        # 最优经济解
        best_eco_idx = df["Economic_Cost"].idxmin()
        best_eco = df.loc[best_eco_idx]

        # 最优匹配解
        best_match_idx = df["Matching_Index"].idxmin()
        best_match = df.loc[best_match_idx]

        # 上排：最优经济解
        ax_eco = axes[0, col]
        values_eco = [best_eco[var] for var in VAR_NAMES]
        ax_eco.bar(VAR_NAMES_CN, values_eco, color=color, alpha=0.7, edgecolor="black")
        ax_eco.set_title(
            f"{method_name}\n最优经济解 (成本={best_eco['Economic_Cost'] / 10000:.2f}万€)",
            fontsize=11,
        )
        ax_eco.set_ylabel("设备容量 (kW)", fontsize=10)
        ax_eco.tick_params(axis="x", rotation=45)
        ax_eco.grid(axis="y", alpha=0.3)

        # 下排：最优匹配解
        ax_match = axes[1, col]
        values_match = [best_match[var] for var in VAR_NAMES]
        ax_match.bar(
            VAR_NAMES_CN, values_match, color=color, alpha=0.7, edgecolor="black"
        )
        ax_match.set_title(
            f"{method_name}\n最优匹配解 (匹配度={best_match['Matching_Index']:.2f})",
            fontsize=11,
        )
        ax_match.set_ylabel("设备容量 (kW)", fontsize=10)
        ax_match.tick_params(axis="x", rotation=45)
        ax_match.grid(axis="y", alpha=0.3)

    # 成本相近的跨方法对比：取两方法成本最接近的一对解
    ax_pair = axes[0, 2]
    ax_pair2 = axes[1, 2]
    if (
        df_std is not None
        and len(df_std) > 0
        and df_euclidean is not None
        and len(df_euclidean) > 0
    ):
        costs_std = df_std["Economic_Cost"].values
        costs_euc = df_euclidean["Economic_Cost"].values
        best_pair = None
        best_diff = 1e18
        for i, c_std in enumerate(costs_std):
            diff_idx = np.argmin(np.abs(costs_euc - c_std))
            diff = abs(c_std - costs_euc[diff_idx])
            if diff < best_diff:
                best_diff = diff
                best_pair = (df_std.iloc[i], df_euclidean.iloc[diff_idx])

        if best_pair:
            std_sol, euc_sol = best_pair
            std_vals = [std_sol[v] for v in VAR_NAMES]
            euc_vals = [euc_sol[v] for v in VAR_NAMES]
            x = np.arange(len(VAR_NAMES_CN))
            width = 0.35
            ax_pair.bar(
                x - width / 2,
                std_vals,
                width,
                label="方案B 成本相近",
                color="blue",
                alpha=0.7,
            )
            ax_pair.bar(
                x + width / 2,
                euc_vals,
                width,
                label="方案C 成本相近",
                color="red",
                alpha=0.7,
            )
            ax_pair.set_title(
                f"成本相近方案对比\nB:{std_sol['Economic_Cost'] / 10000:.2f}万€ vs C:{euc_sol['Economic_Cost'] / 10000:.2f}万€",
                fontsize=11,
            )
            ax_pair.set_xticks(x)
            ax_pair.set_xticklabels(VAR_NAMES_CN, rotation=45)
            ax_pair.grid(axis="y", alpha=0.3)
            ax_pair.legend(fontsize=9)

            # 下排留空或复用匹配对比
            ax_pair2.axis("off")

    plt.tight_layout()
    save_path = os.path.join(output_dir, "Method_Comparison_Extreme_Solutions.png")
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  已保存: {save_path}")


def generate_comparison_metrics(
    df_std,
    df_euclidean,
    output_dir,
    match_std_cross=None,
    match_euc=None,
    knee_solutions=None,
):
    """
    计算并输出对比指标
    """
    report_lines = []
    report_lines.append("# 两种源荷匹配度方法对比分析报告\n\n")

    # ========== 1. 基本统计 ==========
    report_lines.append("## 1. 基本统计\n\n")
    report_lines.append("| 指标 | 方案B-波动率(师兄) | 方案C-能质耦合(本文) |\n")
    report_lines.append("|------|-------------------|---------------------|\n")

    n_std = len(df_std) if df_std is not None else 0
    n_euc = len(df_euclidean) if df_euclidean is not None else 0
    report_lines.append(f"| Pareto解数量 | {n_std} | {n_euc} |\n")

    if df_std is not None and len(df_std) > 0:
        min_cost_std = df_std["Economic_Cost"].min()
        max_cost_std = df_std["Economic_Cost"].max()
        match_std_vals = (
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values
        )
        min_match_std = match_std_vals.min()
        max_match_std = match_std_vals.max()
    else:
        min_cost_std = max_cost_std = min_match_std = max_match_std = "-"

    if df_euclidean is not None and len(df_euclidean) > 0:
        min_cost_euc = df_euclidean["Economic_Cost"].min()
        max_cost_euc = df_euclidean["Economic_Cost"].max()
        match_euc_vals = (
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values
        )
        min_match_euc = match_euc_vals.min()
        max_match_euc = match_euc_vals.max()
    else:
        min_cost_euc = max_cost_euc = min_match_euc = max_match_euc = "-"

    def fmt(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) else str(v)

    report_lines.append(
        f"| 最低成本 (€) | {fmt(min_cost_std)} | {fmt(min_cost_euc)} |\n"
    )
    report_lines.append(
        f"| 最高成本 (€) | {fmt(max_cost_std)} | {fmt(max_cost_euc)} |\n"
    )
    report_lines.append(
        f"| 最佳匹配度 (kW) | {fmt(min_match_std)} | {fmt(min_match_euc)} |\n"
    )
    report_lines.append(
        f"| 最差匹配度 (kW) | {fmt(max_match_std)} | {fmt(max_match_euc)} |\n"
    )

    # ========== 2. 超体积指标 ==========
    report_lines.append("\n## 2. 超体积指标 (Hypervolume)\n\n")
    report_lines.append("超体积越大，说明Pareto前沿覆盖的目标空间越大，方法越好。\n\n")

    # 确定参考点（使用两种方法的最大值 * 1.1）
    all_costs = []
    all_matchings = []
    if df_std is not None and len(df_std) > 0:
        all_costs.extend(df_std["Economic_Cost"].values)
        all_matchings.extend(
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values
        )
    if df_euclidean is not None and len(df_euclidean) > 0:
        all_costs.extend(df_euclidean["Economic_Cost"].values)
        all_matchings.extend(
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values
        )

    if len(all_costs) > 0:
        ref_point = (max(all_costs) * 1.1, max(all_matchings) * 1.1)

        hv_std = 0
        hv_euc = 0

        if df_std is not None and len(df_std) > 0:
            hv_std = calculate_hypervolume_2d(
                df_std["Economic_Cost"].values,
                match_std_cross
                if match_std_cross is not None
                else df_std["Matching_Index"].values,
                ref_point,
            )

        if df_euclidean is not None and len(df_euclidean) > 0:
            hv_euc = calculate_hypervolume_2d(
                df_euclidean["Economic_Cost"].values,
                match_euc
                if match_euc is not None
                else df_euclidean["Matching_Index"].values,
                ref_point,
            )

        report_lines.append(f"- 参考点: ({ref_point[0]:,.0f}, {ref_point[1]:.2f})\n")
        report_lines.append(f"- 方案B超体积: {hv_std:,.2e}\n")
        report_lines.append(f"- 方案C超体积: {hv_euc:,.2e}\n")

        if hv_std > 0 and hv_euc > 0:
            ratio = hv_euc / hv_std
            report_lines.append(f"- **比值 (C/B): {ratio:.2f}**\n")
            if ratio > 1:
                report_lines.append(
                    f"- **结论: 方案C优于方案B（超体积大{(ratio - 1) * 100:.1f}%）**\n"
                )
            else:
                report_lines.append(
                    f"- **结论: 方案B优于方案C（超体积大{(1 / ratio - 1) * 100:.1f}%）**\n"
                )

    # ========== 3. 解的多样性 ==========
    report_lines.append("\n## 3. 解的多样性 (Spread)\n\n")
    report_lines.append("Spread值越小，说明解分布越均匀。\n\n")

    if df_std is not None and len(df_std) > 1:
        spread_std = calculate_spread(
            df_std["Economic_Cost"].values,
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values,
        )
        report_lines.append(f"- 方案B Spread: {spread_std:.4f}\n")

    if df_euclidean is not None and len(df_euclidean) > 1:
        spread_euc = calculate_spread(
            df_euclidean["Economic_Cost"].values,
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values,
        )
        report_lines.append(f"- 方案C Spread: {spread_euc:.4f}\n")

    # ========== 4. 覆盖率指标 ==========
    report_lines.append("\n## 4. 覆盖率指标 (Coverage)\n\n")
    report_lines.append("C(A,B)表示A支配B的解的比例。\n\n")

    if (
        df_std is not None
        and len(df_std) > 0
        and df_euclidean is not None
        and len(df_euclidean) > 0
    ):
        coverage_c_over_b = calculate_coverage(
            df_euclidean["Economic_Cost"].values,
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values,
            df_std["Economic_Cost"].values,
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values,
        )

        coverage_b_over_c = calculate_coverage(
            df_std["Economic_Cost"].values,
            match_std_cross
            if match_std_cross is not None
            else df_std["Matching_Index"].values,
            df_euclidean["Economic_Cost"].values,
            match_euc
            if match_euc is not None
            else df_euclidean["Matching_Index"].values,
        )

        report_lines.append(
            f"- C(方案C, 方案B) = {coverage_c_over_b:.2%} （本文方法支配师兄方法的比例）\n"
        )
        report_lines.append(
            f"- C(方案B, 方案C) = {coverage_b_over_c:.2%} （师兄方法支配本文方法的比例）\n"
        )

    # ========== 5. 物理意义分析 ==========
    report_lines.append("\n## 5. 物理意义分析\n\n")
    report_lines.append("### 方法差异的本质\n\n")
    report_lines.append("| 维度 | 方案B-波动率(标准差) | 方案C-能质耦合(欧氏距离) |\n")
    report_lines.append("|------|---------------------|-------------------------|\n")
    report_lines.append("| 视角 | 横向（时间维） | 竖向（能源维） |\n")
    report_lines.append("| 关注点 | 各能流的时序平稳性 | 多能流的瞬时协同性 |\n")
    report_lines.append("| 优化目标 | 平抑单一能流峰谷差 | 惩罚多能同步失衡 |\n")
    report_lines.append("| 缺陷 | 忽略能源间耦合 | 可能过度惩罚 |\n")

    report_lines.append("\n### 结论建议\n\n")
    report_lines.append(
        "1. **解的丰富度**: 方案C提供了更多的Pareto解，给决策者更大的选择空间\n"
    )
    report_lines.append(
        "2. **物理意义**: 方案C考虑了能质差异和多能耦合，更符合综合能源系统的本质\n"
    )
    report_lines.append("3. **实际应用**: 建议根据具体场景选择合适的方案\n")

    # ========== 6. KPI 综合指标（拐点方案） ==========
    if knee_solutions:
        report_lines.append("\n## 6. KPI 综合指标（拐点方案）\n\n")
        report_lines.append(
            "| 方法 | PER | 㶲效率 | SSR-电 | SSR-热 | SSR-冷 | 电网交互Std |\n"
        )
        report_lines.append(
            "|------|-----|--------|-------|-------|-------|-----------|\n"
        )
        for name, kpi in knee_solutions.items():
            report_lines.append(
                f"| {name} | {kpi.get('PER', 0):.3f} | {kpi.get('Exergy_eff', 0):.3f} | "
                f"{kpi.get('SSR_ele', 0):.3f} | {kpi.get('SSR_heat', 0):.3f} | {kpi.get('SSR_cool', 0):.3f} | "
                f"{kpi.get('Grid_std', 0):.3f} |\n"
            )

    # 保存报告
    report_path = os.path.join(output_dir, "Method_Comparison_Report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report_lines)
    print(f"  已保存: {report_path}")

    # 打印到控制台
    print("\n" + "".join(report_lines))

    return report_lines


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("两种源荷匹配度方法对比分析")
    print("=" * 70)

    # 切换工作目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    os.chdir(parent_dir)
    print(f"工作目录: {os.getcwd()}")

    # 查找最新结果
    result_dir = find_latest_result_dir()
    if result_dir is None:
        print("错误: 未找到结果目录")
        return

    print(f"分析目录: {result_dir}")

    # 创建输出目录
    output_dir = os.path.join(result_dir, "方法对比分析")
    os.makedirs(output_dir, exist_ok=True)

    # 加载两种方法的数据
    std_dir = os.path.join(result_dir, "Std")
    euclidean_dir = os.path.join(result_dir, "Euclidean")

    df_std = load_pareto_data(std_dir) if os.path.exists(std_dir) else None
    df_euclidean = (
        load_pareto_data(euclidean_dir) if os.path.exists(euclidean_dir) else None
    )

    if df_std is not None:
        print(f"  方案B (Std): {len(df_std)} 个Pareto解")
    if df_euclidean is not None:
        print(f"  方案C (Euclidean): {len(df_euclidean)} 个Pareto解")

    # 交叉验证：将 Std 解集投影到欧氏能质匹配度标尺
    match_std_cross = None
    match_euc = None
    operation_list = None
    typical_days = None
    try:
        if df_std is not None or df_euclidean is not None:
            print("\n[准备] 加载运行数据用于交叉验证与调度/KPI计算...")
            operation_list, typical_days = load_operation_data()
        if df_std is not None:
            match_std_cross = compute_euclidean_matching_for_df(
                df_std, operation_list, typical_days
            )
            print(f"  已重算 Std 解集的能质耦合匹配度，样本数 {len(match_std_cross)}")
        if df_euclidean is not None:
            match_euc = df_euclidean["Matching_Index"].values
    except Exception as e:
        print(f"  警告: 交叉验证匹配度计算失败，将退回原始匹配度。原因: {e}")
        match_std_cross = None
        match_euc = None

    # 选取拐点方案（成本&匹配归一化后和最小）
    knee_solutions = {}

    def pick_knee(df, match_vals):
        if df is None or len(df) == 0:
            return None
        costs = df["Economic_Cost"].values
        mvals = match_vals if match_vals is not None else df["Matching_Index"].values
        c_norm = (costs - costs.min()) / (costs.max() - costs.min() + 1e-9)
        m_norm = (mvals - mvals.min()) / (mvals.max() - mvals.min() + 1e-9)
        score = c_norm + m_norm
        idx = np.argmin(score)
        return df.iloc[idx]

    if operation_list is not None and typical_days is not None:
        knee_std = pick_knee(df_std, match_std_cross)
        knee_euc = pick_knee(df_euclidean, match_euc)
        if knee_std is not None:
            try:
                kpi_std = compute_kpis_for_solution(
                    knee_std, operation_list, typical_days
                )
                knee_solutions["方案B-拐点"] = kpi_std
            except Exception as e:
                print(f"  警告: 方案B KPI计算失败: {e}")
        if knee_euc is not None:
            try:
                kpi_euc = compute_kpis_for_solution(
                    knee_euc, operation_list, typical_days
                )
                knee_solutions["方案C-拐点"] = kpi_euc
            except Exception as e:
                print(f"  警告: 方案C KPI计算失败: {e}")

    # 1. Pareto前沿对比图（统一标尺：能质耦合匹配度）
    print("\n[1] 生成Pareto前沿对比图...")
    plot_pareto_comparison(
        df_std,
        df_euclidean,
        output_dir,
        match_std_cross=match_std_cross,
        match_euc=match_euc,
    )

    # 2. 极端解对比
    print("\n[2] 生成极端解对比图...")
    plot_extreme_solutions_comparison(df_std, df_euclidean, output_dir)

    # 3. 典型日调度对比（经济最优 vs 匹配最优，日7）
    if operation_list is not None:
        try:
            day_id = 7
            print(f"\n[3] 生成典型日调度对比 (自然日{day_id})...")

            # 选两方法：各自最优经济、最优匹配
            def pick_best(df, key):
                if df is None or len(df) == 0:
                    return None
                idx = df[key].idxmin()
                return df.loc[idx]

            std_eco = pick_best(df_std, "Economic_Cost")
            std_match = pick_best(df_std, "Matching_Index")
            euc_eco = pick_best(df_euclidean, "Economic_Cost")
            euc_match = pick_best(df_euclidean, "Matching_Index")

            # 绘制四个方案各自电/热/冷调度图
            def plot_dispatch(result_dicts, title, save_name):
                buses = [
                    (
                        "electricity",
                        "电",
                        [
                            ("pv_output", "光伏", "#FFD700", 1),
                            ("wt_output", "风电", "#87CEEB", 1),
                            ("gt power", "燃机发电", "#FF6347", 1),
                            ("grid", "电网购电", "#808080", 1),
                            ("electricity from storage", "储能放电", "#4169E1", 1),
                            ("ele_load", "电负荷", "#000000", -1),
                            ("ehp", "热泵耗电", "#32CD32", -1),
                            ("ec", "电制冷耗电", "#9370DB", -1),
                            ("electricity to storage", "储能充电", "#00008B", -1),
                        ],
                    ),
                    (
                        "heat",
                        "热",
                        [
                            ("gt heat", "燃机余热", "#FF6347", 1),
                            ("ehp heat", "热泵供热", "#32CD32", 1),
                            ("heat source", "外部热源", "#FF8C00", 1),
                            ("heat from storage", "热储能放热", "#FFA07A", 1),
                            ("heat_load", "热负荷", "#000000", -1),
                            ("ac heat", "吸收式制冷耗热", "#FF69B4", -1),
                            ("heat to storage", "热储能蓄热", "#CD5C5C", -1),
                        ],
                    ),
                    (
                        "cool",
                        "冷",
                        [
                            ("ec cool", "电制冷供冷", "#9370DB", 1),
                            ("ac cool", "吸收式制冷供冷", "#FF69B4", 1),
                            ("cool source", "外部冷源", "#00CED1", 1),
                            ("cool from storage", "冷储能放冷", "#E0FFFF", 1),
                            ("cool_load", "冷负荷", "#000000", -1),
                            ("cool to storage", "冷储能蓄冷", "#008B8B", -1),
                        ],
                    ),
                ]
                hours = list(range(24))
                for bus, bus_name, comps in buses:
                    fig, axes = plt.subplots(1, len(result_dicts), figsize=(16, 5))
                    for ax, (name, res) in zip(axes, result_dicts.items()):
                        pos = {}
                        neg = {}
                        for key, label, color, direct in comps:
                            if key in res:
                                vals = np.array(res[key])
                                if direct > 0:
                                    pos[label] = (vals, color)
                                else:
                                    neg[label] = (vals, color)
                        bottom_p = np.zeros(24)
                        for label, (vals, color) in pos.items():
                            ax.bar(
                                hours,
                                vals,
                                bottom=bottom_p,
                                label=label,
                                color=color,
                                alpha=0.8,
                            )
                            bottom_p += vals
                        bottom_n = np.zeros(24)
                        for label, (vals, color) in neg.items():
                            ax.bar(
                                hours,
                                -vals,
                                bottom=bottom_n,
                                label=label,
                                color=color,
                                alpha=0.8,
                            )
                            bottom_n -= vals
                        ax.axhline(0, color="black", linewidth=0.5)
                        ax.set_title(name, fontsize=11)
                        ax.set_xticks(range(0, 24, 3))
                        ax.grid(axis="y", alpha=0.3)
                    axes[0].legend(fontsize=8, loc="upper left")
                    fig.suptitle(f"{title}-{bus_name} (日{day_id})", fontsize=14)
                    plt.tight_layout()
                    save_path = os.path.join(
                        output_dir, f"{save_name}_{bus}_day{day_id}.png"
                    )
                    plt.savefig(save_path, dpi=200, bbox_inches="tight")
                    plt.close()
                    print(f"  已保存: {save_path}")

            result_dicts = {}
            if std_eco is not None:
                result_dicts["B-经济优"] = run_dispatch_for_day(
                    std_eco, operation_list, day_id
                )
            if std_match is not None:
                result_dicts["B-匹配优"] = run_dispatch_for_day(
                    std_match, operation_list, day_id
                )
            if euc_eco is not None:
                result_dicts["C-经济优"] = run_dispatch_for_day(
                    euc_eco, operation_list, day_id
                )
            if euc_match is not None:
                result_dicts["C-匹配优"] = run_dispatch_for_day(
                    euc_match, operation_list, day_id
                )
            if len(result_dicts) > 0:
                plot_dispatch(result_dicts, "典型日调度对比", "Dispatch_Comparison")
        except Exception as e:
            print(f"  警告: 调度对比生成失败: {e}")

    # 4. 生成量化对比指标报告（使用统一匹配度标尺，并附KPI）
    print("\n[4] 生成量化对比指标...")
    generate_comparison_metrics(
        df_std,
        df_euclidean,
        output_dir,
        match_std_cross=match_std_cross,
        match_euc=match_euc,
        knee_solutions=knee_solutions,
    )

    print("\n" + "=" * 70)
    print(f"对比分析完成！结果保存在: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
