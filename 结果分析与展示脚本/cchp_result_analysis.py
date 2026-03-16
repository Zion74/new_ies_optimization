# -*- coding: utf-8 -*-
"""
CCHP系统规划结果 综合分析与可视化脚本

功能：
1. 图4-10 & 表4-2: 25个规划方案容量配置柱状图与表格
2. 图4-11~4-13: 系统#1与#25的典型日调度对比图
3. 图4-14~4-17: 负荷增长敏感性分析（1%、5%、10%场景）

@author: Based on Frank's thesis
"""

import os
import sys
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from operation import OperationModel

# 设置中文字体和样式
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

# 设备颜色配置（与师兄论文保持一致）
DEVICE_COLORS = {
    "PV": "#FFD700",  # 金色 - 光伏
    "WT": "#87CEEB",  # 天蓝 - 风电
    "GT": "#FF6347",  # 番茄红 - 燃气轮机
    "HP": "#32CD32",  # 绿色 - 电热泵
    "EC": "#9370DB",  # 紫色 - 电制冷
    "AC": "#FF69B4",  # 粉色 - 吸收式制冷
    "ES": "#4169E1",  # 皇家蓝 - 电储能
    "HS": "#FF8C00",  # 深橙 - 热储能
    "CS": "#00CED1",  # 深青 - 冷储能
}

DEVICE_NAMES_CN = {
    "PV": "光伏",
    "WT": "风电",
    "GT": "燃气轮机",
    "HP": "电热泵",
    "EC": "电制冷",
    "AC": "吸收式制冷",
    "ES": "电储能",
    "HS": "热储能",
    "CS": "冷储能",
}

VAR_NAMES = ["PV", "WT", "GT", "HP", "EC", "AC", "ES", "HS", "CS"]


def find_latest_result_dir(base_path="."):
    """查找最新的结果目录"""
    result_dirs = glob.glob(os.path.join(base_path, "Result_CCHP_Comparison_*"))
    if not result_dirs:
        print("未找到 Result_CCHP_Comparison_* 目录")
        return None
    result_dirs.sort(key=os.path.getmtime)
    return result_dirs[-1]


def load_pareto_data(method_dir):
    """加载某方法的Pareto前沿数据"""
    pareto_files = glob.glob(os.path.join(method_dir, "Pareto_*.csv"))
    if not pareto_files:
        return None
    df = pd.read_csv(pareto_files[0], index_col=0)
    return df


def select_representative_solutions(df, n_solutions=25, cost_col="Economic_Cost"):
    """
    从Pareto解集中选取代表性方案（去除重合度高的方案）

    方法：按成本均匀采样，并确保包含最优经济和最优匹配方案
    """
    if df is None or len(df) == 0:
        return None

    # 按成本排序
    df_sorted = df.sort_values(by=cost_col).reset_index(drop=True)

    if len(df_sorted) <= n_solutions:
        df_sorted["Solution_No"] = range(1, len(df_sorted) + 1)
        return df_sorted

    # 均匀采样
    indices = np.linspace(0, len(df_sorted) - 1, n_solutions, dtype=int)
    indices = list(set(indices))  # 去重

    # 确保包含首尾（最优经济和最优匹配）
    if 0 not in indices:
        indices.append(0)
    if len(df_sorted) - 1 not in indices:
        indices.append(len(df_sorted) - 1)

    indices.sort()
    df_selected = df_sorted.iloc[indices].copy()
    df_selected["Solution_No"] = range(1, len(df_selected) + 1)

    return df_selected


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
    """
    对指定方案在指定日运行调度优化

    Parameters
    ----------
    solution : dict or Series
        包含 PV, WT, GT, HP, EC, AC, ES, HS, CS 的方案配置
    operation_list : list
        全年运行数据
    day_id : int
        自然日ID (1-365)

    Returns
    -------
    dict : 调度结果
    """
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

    # 提取当日数据
    ele_load = [operation_list[time_start + t][0] for t in range(time_step)]
    heat_load = [operation_list[time_start + t][1] for t in range(time_step)]
    cool_load = [operation_list[time_start + t][2] for t in range(time_step)]
    solar_radiation_list = [operation_list[time_start + t][3] for t in range(time_step)]
    wind_speed_list = [operation_list[time_start + t][4] for t in range(time_step)]
    temperature_list = [operation_list[time_start + t][5] for t in range(time_step)]

    # 计算可再生能源出力
    pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
    wt_output = cal_wind_output(wind_speed_list, pwt)

    # 电价设置
    ele_price = [0.0025] * time_step
    gas_price = [0.0286] * time_step

    # 创建并优化模型
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

    # 添加原始数据
    results["ele_load"] = ele_load
    results["heat_load"] = heat_load
    results["cool_load"] = cool_load
    results["pv_output"] = pv_output
    results["wt_output"] = wt_output

    return results


# ============================================================================
# 图4-10 & 表4-2: 25个规划方案容量配置
# ============================================================================


def plot_capacity_configuration(df_solutions, output_dir, method_name):
    """
    绘制规划方案容量配置柱状图（图4-10）
    """
    if df_solutions is None or len(df_solutions) == 0:
        print(f"  {method_name}: 无数据，跳过容量配置图")
        return

    n_solutions = len(df_solutions)

    fig, ax = plt.subplots(figsize=(16, 8))

    x = np.arange(n_solutions)
    width = 0.08

    # 绘制每种设备的柱子
    for i, var in enumerate(VAR_NAMES):
        values = df_solutions[var].values
        offset = (i - len(VAR_NAMES) / 2 + 0.5) * width
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=f"{DEVICE_NAMES_CN[var]}({var})",
            color=DEVICE_COLORS[var],
            edgecolor="black",
            linewidth=0.5,
        )

    ax.set_xlabel("规划方案序号", fontsize=12)
    ax.set_ylabel("设备容量 (kW)", fontsize=12)
    ax.set_title(f"帕累托解集中规划方案的容量配置结果 - {method_name}", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i}" for i in df_solutions["Solution_No"]], fontsize=9)
    ax.legend(loc="upper left", ncol=3, fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # 保存
    save_path = os.path.join(
        output_dir, f"Fig4-10_Capacity_Configuration_{method_name}.png"
    )
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  已保存: {save_path}")


def save_capacity_table(df_solutions, output_dir, method_name):
    """
    保存容量配置表格（表4-2）
    """
    if df_solutions is None or len(df_solutions) == 0:
        return

    # 创建表格
    table_df = df_solutions[["Solution_No"] + VAR_NAMES].copy()

    # 添加目标值
    if "Economic_Cost" in df_solutions.columns:
        table_df["年化成本(€)"] = df_solutions["Economic_Cost"].round(2)
    if "Matching_Index" in df_solutions.columns:
        table_df["匹配度指标"] = df_solutions["Matching_Index"].round(2)

    # 重命名列
    rename_dict = {var: DEVICE_NAMES_CN[var] + f"({var})" for var in VAR_NAMES}
    rename_dict["Solution_No"] = "方案序号"
    table_df = table_df.rename(columns=rename_dict)

    # 保存CSV
    csv_path = os.path.join(output_dir, f"Tab4-2_Capacity_Data_{method_name}.csv")
    table_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  已保存: {csv_path}")

    # 保存Markdown表格
    md_path = os.path.join(output_dir, f"Tab4-2_Capacity_Data_{method_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 表4-2 帕累托解集中规划方案容量配置 - {method_name}\n\n")
        f.write(table_df.to_markdown(index=False))
    print(f"  已保存: {md_path}")


# ============================================================================
# 图4-11~4-13: 系统#1与#25的调度对比
# ============================================================================


def plot_dispatch_comparison(results_1, results_25, output_dir, method_name, day_id=7):
    """
    绘制系统#1和系统#25的电、热、冷调度对比图
    """
    hours = list(range(24))

    bus_configs = [
        {
            "bus": "electricity",
            "fig_num": "4-11",
            "title": "电调度",
            "components": [
                ("pv_output", "光伏出力", "#FFD700", 1),
                ("wt_output", "风电出力", "#87CEEB", 1),
                ("gt power", "燃气轮机发电", "#FF6347", 1),
                ("grid", "电网购电", "#808080", 1),
                ("electricity from storage", "储能放电", "#4169E1", 1),
                ("ele_load", "电负荷", "#000000", -1),
                ("ehp", "热泵耗电", "#32CD32", -1),
                ("ec", "电制冷耗电", "#9370DB", -1),
                ("electricity to storage", "储能充电", "#00008B", -1),
            ],
        },
        {
            "bus": "heat",
            "fig_num": "4-12",
            "title": "热调度",
            "components": [
                ("gt heat", "燃气轮机余热", "#FF6347", 1),
                ("ehp heat", "热泵供热", "#32CD32", 1),
                ("heat source", "外部热源", "#FF8C00", 1),
                ("heat from storage", "热储能放热", "#FFA07A", 1),
                ("heat_load", "热负荷", "#000000", -1),
                ("ac heat", "吸收式制冷耗热", "#FF69B4", -1),
                ("heat to storage", "热储能蓄热", "#CD5C5C", -1),
            ],
        },
        {
            "bus": "cool",
            "fig_num": "4-13",
            "title": "冷调度",
            "components": [
                ("ec cool", "电制冷供冷", "#9370DB", 1),
                ("ac cool", "吸收式制冷供冷", "#FF69B4", 1),
                ("cool source", "外部冷源", "#00CED1", 1),
                ("cool from storage", "冷储能放冷", "#E0FFFF", 1),
                ("cool_load", "冷负荷", "#000000", -1),
                ("cool to storage", "冷储能蓄冷", "#008B8B", -1),
            ],
        },
    ]

    for config in bus_configs:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        for ax_idx, (results, sys_name) in enumerate(
            [(results_1, "系统#1(经济最优)"), (results_25, "系统#25(匹配最优)")]
        ):
            ax = axes[ax_idx]

            # 分离正向（供给）和负向（消耗）
            positive_data = {}
            negative_data = {}

            for key, label, color, direction in config["components"]:
                if key in results:
                    values = np.array(results[key])
                    if direction > 0:
                        positive_data[label] = (values, color)
                    else:
                        negative_data[label] = (values, color)

            # 堆叠绘制正向
            bottom_pos = np.zeros(24)
            for label, (values, color) in positive_data.items():
                ax.bar(
                    hours,
                    values,
                    bottom=bottom_pos,
                    label=label,
                    color=color,
                    alpha=0.8,
                )
                bottom_pos += values

            # 堆叠绘制负向
            bottom_neg = np.zeros(24)
            for label, (values, color) in negative_data.items():
                ax.bar(
                    hours,
                    -values,
                    bottom=bottom_neg,
                    label=label,
                    color=color,
                    alpha=0.8,
                )
                bottom_neg -= values

            ax.axhline(y=0, color="black", linewidth=0.5)
            ax.set_xlabel("时间 (h)", fontsize=11)
            ax.set_ylabel("功率 (kW)", fontsize=11)
            ax.set_title(f"{sys_name} - 第{day_id}天", fontsize=12)
            ax.set_xticks(range(0, 24, 2))
            ax.legend(loc="upper left", fontsize=8, ncol=2)
            ax.grid(axis="y", alpha=0.3)

        fig.suptitle(
            f"图{config['fig_num']} {config['title']}对比 ({method_name})",
            fontsize=14,
            y=1.02,
        )
        plt.tight_layout()

        save_path = os.path.join(
            output_dir,
            f"Fig{config['fig_num']}_{config['bus']}_dispatch_{method_name}.png",
        )
        plt.savefig(save_path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"  已保存: {save_path}")


# ============================================================================
# 图4-14~4-17: 负荷增长敏感性分析
# ============================================================================


def calculate_annual_costs(solution, operation_list, typical_days, growth_rate=0.0):
    """
    计算指定负荷增长率下的年运行成本

    Parameters
    ----------
    growth_rate : float
        年负荷增长率 (如 0.01 表示1%)

    Returns
    -------
    float : 年运行成本
    """
    ppv, pwt, pgt = solution["PV"], solution["WT"], solution["GT"]
    php, pec, pac = solution["HP"], solution["EC"], solution["AC"]
    pes, phs, pcs = solution["ES"], solution["HS"], solution["CS"]

    time_step = 24
    ele_price = [0.0025] * time_step
    gas_price = [0.0286] * time_step

    total_oc = 0

    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24

        # 提取并按增长率调整负荷
        ele_load = [
            operation_list[time_start + t][0] * (1 + growth_rate)
            for t in range(time_step)
        ]
        heat_load = [
            operation_list[time_start + t][1] * (1 + growth_rate)
            for t in range(time_step)
        ]
        cool_load = [
            operation_list[time_start + t][2] * (1 + growth_rate)
            for t in range(time_step)
        ]
        solar_radiation_list = [
            operation_list[time_start + t][3] for t in range(time_step)
        ]
        wind_speed_list = [operation_list[time_start + t][4] for t in range(time_step)]
        temperature_list = [operation_list[time_start + t][5] for t in range(time_step)]

        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)

        try:
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
            obj_val = operation_model.get_objective_value()
            total_oc += obj_val * len(typical_days[cluster_medoid])
        except Exception as e:
            # 优化失败时返回惩罚值
            total_oc += 1e6

    return total_oc


def calculate_investment_maintenance_cost(solution):
    """计算年化投资和维护成本"""
    # 年化投资系数（与gaproblem一致）
    investment = (
        76.44188371 * solution["PV"]
        + 110.4233218 * solution["WT"]
        + 50.32074101 * solution["GT"]
        + 21.21527903 * solution["HP"]
        + 22.85563566 * solution["EC"]
        + 21.81674313 * solution["AC"]
        + 35.11456751 * solution["ES"]
        + 1.689590459 * (solution["HS"] + solution["CS"])
        + 520 * (solution["HS"] > 0.1)
        + 520 * (solution["CS"] > 0.1)
    )
    return investment


def plot_investment_maintenance(df_solutions, output_dir, method_name):
    """
    绘制图4-14: 年化投资和维护成本
    """
    if df_solutions is None or len(df_solutions) == 0:
        return

    n = len(df_solutions)
    x = np.arange(n)

    # 计算各方案的投资维护成本
    inv_costs = []
    for _, row in df_solutions.iterrows():
        inv = calculate_investment_maintenance_cost(row)
        inv_costs.append(inv)

    fig, ax = plt.subplots(figsize=(14, 6))

    bars = ax.bar(
        x, np.array(inv_costs) / 10000, color="#4169E1", edgecolor="black", alpha=0.8
    )

    ax.set_xlabel("规划方案序号", fontsize=12)
    ax.set_ylabel("年化投资和维护成本 (万€)", fontsize=12)
    ax.set_title(
        f"图4-14 帕累托解集中规划方案的年化投资和维护成本 - {method_name}", fontsize=14
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i}" for i in df_solutions["Solution_No"]], fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    # 添加数值标签
    for bar, cost in zip(bars, inv_costs):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{cost / 10000:.1f}",
            ha="center",
            va="bottom",
            fontsize=7,
        )

    save_path = os.path.join(
        output_dir, f"Fig4-14_Investment_Maintenance_{method_name}.png"
    )
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  已保存: {save_path}")


def plot_load_growth_analysis(
    df_solutions,
    operation_list,
    typical_days,
    output_dir,
    method_name,
    growth_rate,
    fig_num,
):
    """
    绘制负荷增长场景下的成本分析图
    """
    if df_solutions is None or len(df_solutions) == 0:
        return

    print(f"  计算场景 {fig_num[-1]} (增长率 {growth_rate * 100}%) ...")

    n = len(df_solutions)
    x = np.arange(n)

    # 计算各方案20年总成本
    planning_years = 20
    operating_costs = []
    investment_costs = []
    total_costs = []

    for idx, (_, row) in enumerate(df_solutions.iterrows()):
        # 年化投资成本
        inv = calculate_investment_maintenance_cost(row)
        investment_costs.append(inv)

        # 20年运行成本（考虑负荷增长）
        total_op = 0
        for year in range(planning_years):
            year_growth = (1 + growth_rate) ** year
            try:
                year_op = calculate_annual_costs(row, operation_list, typical_days, 0)
                total_op += year_op * year_growth
            except Exception:
                total_op += 1e6

        avg_op = total_op / planning_years
        operating_costs.append(avg_op)
        total_costs.append(inv + avg_op)

        if (idx + 1) % 5 == 0:
            print(f"    已完成 {idx + 1}/{n} 个方案")

    # 绘图
    fig, ax = plt.subplots(figsize=(14, 6))

    width = 0.35
    bars1 = ax.bar(
        x - width / 2,
        np.array(operating_costs) / 10000,
        width,
        label="年均运行成本",
        color="#FF6347",
        alpha=0.8,
    )
    bars2 = ax.bar(
        x + width / 2,
        np.array(total_costs) / 10000,
        width,
        label="年化总成本",
        color="#4169E1",
        alpha=0.8,
    )

    ax.set_xlabel("规划方案序号", fontsize=12)
    ax.set_ylabel("成本 (万€)", fontsize=12)
    ax.set_title(
        f"图{fig_num} 负荷年增长率{growth_rate * 100:.0f}%场景下不同方案成本 - {method_name}",
        fontsize=14,
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i}" for i in df_solutions["Solution_No"]], fontsize=9)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    save_path = os.path.join(
        output_dir,
        f"Fig{fig_num}_LoadGrowth_{int(growth_rate * 100)}pct_{method_name}.png",
    )
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  已保存: {save_path}")


# ============================================================================
# 主函数
# ============================================================================


def analyze_method_results(
    method_dir, method_name, operation_list, typical_days, n_solutions=25
):
    """
    分析单个方法的结果
    """
    print(f"\n{'=' * 60}")
    print(f"分析方法: {method_name}")
    print(f"{'=' * 60}")

    # 创建输出目录
    output_dir = os.path.join(method_dir, "结果分析与展示")
    os.makedirs(output_dir, exist_ok=True)

    # 加载Pareto数据
    df_pareto = load_pareto_data(method_dir)
    if df_pareto is None:
        print(f"  未找到Pareto数据，跳过")
        return

    print(f"  原始Pareto解数量: {len(df_pareto)}")

    # 选取代表性方案
    df_solutions = select_representative_solutions(df_pareto, n_solutions)
    print(f"  选取代表性方案: {len(df_solutions)} 个")

    # ========== 1. 图4-10 & 表4-2: 容量配置 ==========
    print("\n[1] 生成容量配置图表...")
    plot_capacity_configuration(df_solutions, output_dir, method_name)
    save_capacity_table(df_solutions, output_dir, method_name)

    # ========== 2. 图4-11~4-13: 调度对比 ==========
    print("\n[2] 生成调度对比图...")

    # 选取方案#1（经济最优）和方案#25（匹配最优）
    solution_1 = df_solutions[df_solutions["Solution_No"] == 1].iloc[0]
    solution_n = df_solutions[
        df_solutions["Solution_No"] == df_solutions["Solution_No"].max()
    ].iloc[0]

    # 选择第7天（1月7日）进行调度
    day_id = 7
    print(f"  运行第{day_id}天的调度优化...")

    try:
        results_1 = run_dispatch_for_day(solution_1, operation_list, day_id)
        results_n = run_dispatch_for_day(solution_n, operation_list, day_id)
        plot_dispatch_comparison(results_1, results_n, output_dir, method_name, day_id)
    except Exception as e:
        print(f"  调度优化失败: {e}")

    # ========== 3. 图4-14: 投资维护成本 ==========
    print("\n[3] 生成投资维护成本图...")
    plot_investment_maintenance(df_solutions, output_dir, method_name)

    # ========== 4. 图4-15~4-17: 负荷增长敏感性分析 ==========
    print("\n[4] 生成负荷增长敏感性分析图...")

    # 为了节省时间，只选取部分方案进行敏感性分析
    df_sensitivity = select_representative_solutions(df_pareto, min(10, len(df_pareto)))

    scenarios = [
        (0.01, "4-15"),  # 1% 增长
        (0.05, "4-16"),  # 5% 增长
        (0.10, "4-17"),  # 10% 增长
    ]

    for growth_rate, fig_num in scenarios:
        plot_load_growth_analysis(
            df_sensitivity,
            operation_list,
            typical_days,
            output_dir,
            method_name,
            growth_rate,
            fig_num,
        )

    print(f"\n✓ {method_name} 分析完成，结果保存在: {output_dir}")


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("CCHP系统规划结果 综合分析与可视化")
    print("=" * 70)

    # 切换到脚本所在目录的父目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    os.chdir(parent_dir)
    print(f"工作目录: {os.getcwd()}")

    # 设置 Gurobi 许可证
    os.environ["GRB_LICENSE_FILE"] = r"C:\gurobi\gurobi.lic"

    # 查找最新结果目录
    result_dir = find_latest_result_dir()
    if result_dir is None:
        print("错误: 未找到结果目录")
        return

    print(f"分析目录: {result_dir}")

    # 加载运行数据
    print("\n加载运行数据...")
    operation_data = pd.read_csv("mergedData.csv")
    operation_list = np.array(operation_data).tolist()

    # 加载典型日数据
    typical_days = dict()
    typical_data = pd.read_excel("typicalDayData.xlsx")
    typical_day_id = typical_data["typicalDayId"]
    days_str = typical_data["days"]
    for i in range(len(typical_day_id)):
        days_list = list(map(int, days_str[i].split(",")))
        typical_days[typical_day_id[i]] = days_list

    print(f"典型日数量: {len(typical_days)}")

    # 分析各方法结果
    methods = [
        ("Std", "方案B-波动率匹配度(师兄)"),
        ("Euclidean", "方案C-能质耦合匹配度(本文)"),
        ("Economic_only", "方案A-单目标经济"),
    ]

    for folder_name, method_name in methods:
        method_dir = os.path.join(result_dir, folder_name)
        if os.path.exists(method_dir):
            analyze_method_results(
                method_dir, method_name, operation_list, typical_days
            )
        else:
            print(f"\n跳过 {method_name}: 目录不存在 ({method_dir})")

    print("\n" + "=" * 70)
    print("所有分析完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
