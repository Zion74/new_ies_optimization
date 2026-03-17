# -*- coding: utf-8 -*-
import sys, io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
电-热-冷综合能源系统(CCHP)规划优化 - 对比实验主程序

实验设计（5种源荷匹配度量化方法）：
  - 方案A (economic_only)：单目标经济最优（基准组）
  - 方案B (std)：师兄的波动率匹配度（对照组）
  - 方案C (euclidean)：本文三维能质耦合匹配度（实验组-核心创新）
  - 方案D (pearson)：皮尔逊相关系数法（对照组-只看趋势不看大小）
  - 方案E (ssr)：供需重叠度/自给自足率法（对照组-只看总量不看能质）

基于师兄EI论文德国案例数据，采用两部制电价：
  - 基础电价：0.0025 €/kWh
  - 容量费：114.29 €/(kW·a)
  - 气价：0.0286 €/kWh

@author: Based on Frank's work
"""

import os
import datetime

# 强制指定 Gurobi 许可证文件路径
os.environ["GRB_LICENSE_FILE"] = r"C:\gurobi\gurobi.lic"

import geatpy as ea
from cchp_gaproblem import CCHPProblem, LAMBDA_E, LAMBDA_H, LAMBDA_C
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


class MyNSGA2(ea.moea_NSGA2_templet):
    """自定义 NSGA-II 算法"""

    def __init__(self, problem, population, method_name=""):
        super().__init__(problem, population)
        self.method_name = method_name

    def logging(self, pop):
        super().logging(pop)

        best_eco_idx = np.argmin(pop.ObjV[:, 0])
        best_eco_val = pop.ObjV[best_eco_idx, 0]

        print(f"\n  [{self.method_name}] 第 {self.currentGen} 代")
        print(f"  ★ 最低成本: {best_eco_val:,.2f} €")

        if pop.ObjV.shape[1] > 1:
            best_match_idx = np.argmin(pop.ObjV[:, 1])
            best_match_val = pop.ObjV[best_match_idx, 1]
            print(f"  ★ 最佳匹配度: {best_match_val:.2f}")
        print("-" * 50)


class MySGA(ea.soea_DE_rand_1_bin_templet):
    """单目标差分进化算法（用于方案A）"""

    def __init__(self, problem, population, method_name=""):
        super().__init__(problem, population)
        self.method_name = method_name

    def logging(self, pop):
        super().logging(pop)
        best_idx = np.argmin(pop.ObjV[:, 0])
        best_val = pop.ObjV[best_idx, 0]
        print(
            f"\n  [{self.method_name}] 第 {self.currentGen} 代 | 最优成本: {best_val:,.2f} €"
        )


def run_single_experiment(
    method,
    nind=30,
    maxgen=50,
    pool_type="Process",
    initial_population=None,
    case_config=None,
):
    """
    运行单个实验

    Parameters
    ----------
    method : str
        'economic_only', 'std', 'euclidean', 'pearson', 'ssr'
    nind : int
        种群规模
    maxgen : int
        最大进化代数
    initial_population : ea.Population, optional
        初始种群（用于种群继承）
    case_config : dict, optional
        案例配置字典
    """
    method_names = {
        "economic_only": "方案A-单目标经济",
        "std": "方案B-波动率匹配度(师兄)",
        "euclidean": "方案C-能质耦合匹配度(本文)",
        "pearson": "方案D-皮尔逊相关系数",
        "ssr": "方案E-供需重叠度SSR",
    }

    print("\n" + "=" * 70)
    print(f"开始运行: {method_names[method]}")
    if initial_population is not None:
        print("  >> 使用继承的初始种群")
    print("=" * 70)

    problem = CCHPProblem(pool_type, method=method, case_config=case_config)

    Encoding = "RI"
    Field = ea.crtfld(Encoding, problem.varTypes, problem.ranges, problem.borders)

    if initial_population is not None and method != "economic_only":
        # 使用继承的种群
        population = initial_population.copy()
        # 更新种群的Field信息
        population.Field = Field
        # 清除旧的目标值，让新算法重新计算
        population.ObjV = None
        population.FitnV = None
        print(f"  >> 继承种群规模: {population.sizes}")
    else:
        # 创建新种群
        population = ea.Population(Encoding, Field, nind)

    if method == "economic_only":
        # 单目标优化
        algorithm = MySGA(problem, population, method_name=method_names[method])
    else:
        # 多目标优化
        algorithm = MyNSGA2(problem, population, method_name=method_names[method])

    algorithm.MAXGEN = maxgen
    algorithm.mutOper.Pm = 0.1
    algorithm.recOper.XOVR = 0.9
    algorithm.logTras = 1
    algorithm.verbose = True
    algorithm.drawing = 0  # 不自动绘图

    try:
        [BestIndi, population] = algorithm.run()
        print(f"\n{method_names[method]} 完成，耗时 {algorithm.passTime:.2f} 秒")

        return {
            "method": method,
            "name": method_names[method],
            "best_indi": BestIndi,
            "population": population,
            "time": algorithm.passTime,
        }
    finally:
        problem.kill_pool()


def run_comparative_study(
    nind=30,
    maxgen=50,
    pool_type="Process",
    inherit_population=True,
    methods_to_run=None,
    case_config=None,
):
    """
    运行完整的对比实验

    Parameters
    ----------
    nind : int
        种群规模
    maxgen : int
        最大进化代数
    pool_type : str
        并行方式
    inherit_population : bool
        是否让本文方法(euclidean)继承师兄方法(std)的最终种群
        注意：其他方法(pearson/ssr)不会继承任何种群，总是从头开始
    methods_to_run : list, optional
        要运行的方法列表，可选值：
        - 'economic_only': 方案A-单目标经济（基准组）
        - 'std': 方案B-波动率匹配度（师兄方法）
        - 'euclidean': 方案C-能质耦合欧氏距离（本文核心创新）
        - 'pearson': 方案D-皮尔逊相关系数（只看趋势不看大小）
        - 'ssr': 方案E-供需重叠度SSR（只看总量不看能质）
        默认为 ['std', 'euclidean', 'economic_only']
    """
    # 默认运行的方法
    if methods_to_run is None:
        methods_to_run = ["std", "euclidean", "economic_only"]

    # 加载案例配置
    if case_config is None:
        from case_config import GERMAN_CASE
        case_config = GERMAN_CASE

    case_name = case_config.get("name", "german")
    currency = case_config.get("currency", "€")
    lambda_e = case_config.get("lambda_e", LAMBDA_E)
    lambda_h = case_config.get("lambda_h", LAMBDA_H)
    lambda_c = case_config.get("lambda_c", LAMBDA_C)

    # 方法名称映射与文件夹名称
    method_info = {
        "economic_only": ("方案A-单目标经济", "Economic_only"),
        "std": ("方案B-波动率匹配度(师兄)", "Std"),
        "euclidean": ("方案C-能质耦合匹配度(本文)", "Euclidean"),
        "pearson": ("方案D-皮尔逊相关系数", "Pearson"),
        "ssr": ("方案E-供需重叠度SSR", "SSR"),
    }

    print("\n" + "=" * 70)
    print(f"电-热-冷综合能源系统 源荷匹配优化配置 对比实验 [{case_name}]")
    print("=" * 70)
    print(f"\n案例: {case_config.get('description', case_name)}")
    print(f"货币: {currency}")
    print("\n能质系数设置:")
    print(f"  λ_e (电) = {lambda_e:.3f}")
    print(f"  λ_h (热) = {lambda_h:.3f}")
    print(f"  λ_c (冷) = {lambda_c:.3f}")
    if case_config.get("enable_carnot_battery", False):
        print("\n卡诺电池: 已启用")
        print(f"  往返效率: {case_config.get('cb_rte', 0.60):.0%}")
        print(f"  功率上界: {case_config.get('cb_power_ub', 0)} kW")
        print(f"  容量上界: {case_config.get('cb_capacity_ub', 0)} kWh")
    print("\n实验参数:")
    print(f"  种群规模: {nind}")
    print(f"  最大代数: {maxgen}")
    print(f"  并行方式: {pool_type}")
    print(f"  种群继承: {'开启' if inherit_population else '关闭'}")
    print("\n本次运行的方法:")
    for m in methods_to_run:
        if m in method_info:
            print(f"  - {method_info[m][0]}")

    # 创建结果目录（统一放在 Results/ 子文件夹下）
    current_time = datetime.datetime.now().strftime("%m-%d-%H-%M")
    results_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Results")
    os.makedirs(results_root, exist_ok=True)
    result_dir = os.path.join(results_root, f"CCHP_{case_name}_{current_time}")
    os.makedirs(result_dir, exist_ok=True)
    print(f"\n结果目录: {result_dir}")

    results = {}

    # ========== 按顺序运行实验 ==========
    for method in methods_to_run:
        if method not in method_info:
            print(f"\n警告: 未知方法 '{method}'，跳过")
            continue

        method_name, folder_name = method_info[method]

        # 种群继承逻辑：只有本文方法(euclidean)继承师兄方法(std)的种群
        initial_pop = None
        if inherit_population and method == "euclidean" and "std" in results:
            if results["std"]["population"] is not None:
                initial_pop = results["std"]["population"]
                print(f"\n>> {method_name} 将继承师兄方法(Std)的最终种群作为初始解")

        results[method] = run_single_experiment(
            method,
            nind=nind,
            maxgen=maxgen,
            pool_type=pool_type,
            initial_population=initial_pop,
            case_config=case_config,
        )
        save_method_results(results[method], result_dir, folder_name)

    # 生成对比分析报告
    generate_comparison_report(results, result_dir, inherit_population)

    return results, result_dir


def save_method_results(result, result_dir, method_folder_name):
    """
    保存单个方法的详细结果到子文件夹

    目录结构:
    result_dir/
      └── method_folder_name/
            ├── ObjV_xxx.csv
            ├── Phen_xxx.csv
            ├── Chrom_xxx.csv
            ├── FitnV_xxx.csv
            └── Pareto_xxx.csv (如果是多目标)
    """
    method = result["method"]
    BestIndi = result["best_indi"]

    # 创建子文件夹
    method_dir = os.path.join(result_dir, method_folder_name)
    os.makedirs(method_dir, exist_ok=True)

    if BestIndi.sizes == 0:
        print(f"  {result['name']}: 未找到可行解")
        return

    print(f"\n保存 {result['name']} 结果到 {method_dir}/")

    # 1. 保存 ObjV (目标函数值)
    if BestIndi.ObjV is not None:
        objv_path = os.path.join(method_dir, f"ObjV_{method_folder_name}.csv")
        np.savetxt(objv_path, BestIndi.ObjV, delimiter=",")
        print(f"  - ObjV: {objv_path}")

    # 2. 保存 Phen (表现型/决策变量)
    if BestIndi.Phen is not None:
        phen_path = os.path.join(method_dir, f"Phen_{method_folder_name}.csv")
        np.savetxt(phen_path, BestIndi.Phen, delimiter=",")
        print(f"  - Phen: {phen_path}")

    # 3. 保存 Chrom (染色体/基因)
    if BestIndi.Chrom is not None:
        chrom_path = os.path.join(method_dir, f"Chrom_{method_folder_name}.csv")
        np.savetxt(chrom_path, BestIndi.Chrom, delimiter=",")
        print(f"  - Chrom: {chrom_path}")

    # 4. 保存 FitnV (适应度)
    if BestIndi.FitnV is not None:
        fitnv_path = os.path.join(method_dir, f"FitnV_{method_folder_name}.csv")
        np.savetxt(fitnv_path, BestIndi.FitnV, delimiter=",")
        print(f"  - FitnV: {fitnv_path}")

    # 5. 保存 Pareto 前沿解（带变量名的完整表格）
    var_names = ["PV", "WT", "GT", "HP", "EC", "AC", "ES", "HS", "CS"]
    # 卡诺电池启用时多2个决策变量
    if BestIndi.Phen.shape[1] > 9:
        var_names = var_names + ["CB_Power", "CB_Capacity"]

    if method == "economic_only":
        obj_names = ["Economic_Cost"]
    else:
        obj_names = ["Economic_Cost", "Matching_Index"]

    data = np.hstack([BestIndi.ObjV, BestIndi.Phen])
    df = pd.DataFrame(data, columns=obj_names + var_names)
    df = df.sort_values(by="Economic_Cost")

    pareto_path = os.path.join(method_dir, f"Pareto_{method_folder_name}.csv")
    df.to_csv(pareto_path, index=True, index_label="Solution_ID")
    print(f"  - Pareto: {pareto_path}")


def generate_comparison_report(results, result_dir, inherit_population):
    """生成对比分析报告"""
    print("\n" + "=" * 70)
    print("生成对比分析报告")
    print("=" * 70)

    report_lines = []
    report_lines.append("# 电-热-冷综合能源系统 源荷匹配优化配置 对比实验报告\n\n")
    report_lines.append(
        f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    report_lines.append("## 能质系数设置\n\n")
    report_lines.append(f"- λ_e (电能权重) = {LAMBDA_E:.3f}\n")
    report_lines.append(f"- λ_h (热能权重) = {LAMBDA_H:.3f}\n")
    report_lines.append(f"- λ_c (冷能权重) = {LAMBDA_C:.3f}\n\n")

    report_lines.append("## 实验配置\n\n")
    report_lines.append(f"- 种群继承: {'开启' if inherit_population else '关闭'}\n")
    if inherit_population:
        report_lines.append(
            "  - 本文方法(Euclidean)继承师兄方法(Std)的最终种群作为初始解\n"
        )
        report_lines.append(
            "  - 其他对照方法(Pearson/SSR)均从头开始优化，不继承任何种群\n"
        )
    report_lines.append("\n")

    report_lines.append("## 实验结果汇总\n\n")
    report_lines.append(
        "| 方案 | 最低成本(€) | 最佳匹配度 | 耗时(s) | Pareto解数量 |\n"
    )
    report_lines.append("|------|-----------|----------|---------|-------------|\n")

    comparison_data = []

    # 遍历所有已运行的方法
    for method in ["std", "euclidean", "pearson", "ssr", "economic_only"]:
        if method not in results:
            continue

        result = results[method]
        BestIndi = result["best_indi"]

        if BestIndi.sizes > 0:
            min_cost = np.min(BestIndi.ObjV[:, 0])
            num_solutions = BestIndi.sizes

            if BestIndi.ObjV.shape[1] > 1:
                best_match = np.min(BestIndi.ObjV[:, 1])
                match_str = f"{best_match:.2f}"
            else:
                best_match = None
                match_str = "-"

            comparison_data.append(
                {
                    "method": method,
                    "name": result["name"],
                    "min_cost": min_cost,
                    "best_match": best_match,
                    "num_solutions": num_solutions,
                    "time": result["time"],
                    "best_vars": BestIndi.Phen[np.argmin(BestIndi.ObjV[:, 0])],
                }
            )

            report_lines.append(
                f"| {result['name']} | {min_cost:,.2f} | {match_str} | {result['time']:.1f} | {num_solutions} |\n"
            )
        else:
            report_lines.append(f"| {result['name']} | - | - | - | 0 |\n")

    # 详细配置对比
    if len(comparison_data) > 0:
        report_lines.append("\n## 最优方案设备配置对比\n\n")

        # 动态生成表头
        method_short_names = {
            "std": "Std(师兄)",
            "euclidean": "Euclidean(本文)",
            "pearson": "Pearson",
            "ssr": "SSR",
            "economic_only": "Economic",
        }
        methods_in_data = [d["method"] for d in comparison_data]
        header = "| 设备 |"
        separator = "|------|"
        for m in ["std", "euclidean", "pearson", "ssr", "economic_only"]:
            if m in methods_in_data:
                header += f" {method_short_names[m]} |"
                separator += "----------|"
        report_lines.append(header + "\n")
        report_lines.append(separator + "\n")

        var_names = [
            "PV(kW)",
            "WT(kW)",
            "GT(kW)",
            "HP(kW)",
            "EC(kW)",
            "AC(kW)",
            "ES(kW)",
            "HS(kW)",
            "CS(kW)",
        ]

        for idx, var_name in enumerate(var_names):
            row = f"| {var_name} |"
            for method in ["std", "euclidean", "pearson", "ssr", "economic_only"]:
                if method not in methods_in_data:
                    continue
                found = False
                for data in comparison_data:
                    if data["method"] == method:
                        row += f" {data['best_vars'][idx]:.1f} |"
                        found = True
                        break
                if not found:
                    row += " - |"
            report_lines.append(row + "\n")

    # 保存报告
    report_path = os.path.join(result_dir, "comparison_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report_lines)
    print(f"\n对比报告已保存: {report_path}")

    # 绘制Pareto前沿对比图
    plot_pareto_comparison(results, result_dir)

    # 打印到控制台
    print("\n" + "".join(report_lines))


def plot_pareto_comparison(results, result_dir):
    """绘制Pareto前沿对比图"""
    fig, ax = plt.subplots(figsize=(12, 8))

    colors = {
        "economic_only": "red",
        "std": "blue",
        "euclidean": "green",
        "pearson": "purple",
        "ssr": "orange",
    }
    markers = {
        "economic_only": "*",
        "std": "o",
        "euclidean": "s",
        "pearson": "^",
        "ssr": "D",
    }
    labels = {
        "economic_only": "方案A: 单目标经济",
        "std": "方案B: 波动率匹配度(师兄)",
        "euclidean": "方案C: 能质耦合匹配度(本文)",
        "pearson": "方案D: 皮尔逊相关系数",
        "ssr": "方案E: 供需重叠度SSR",
    }

    has_data = False

    # 绘制所有双目标方法
    for method in ["std", "euclidean", "pearson", "ssr"]:
        if method not in results:
            continue

        result = results[method]
        BestIndi = result["best_indi"]

        if BestIndi.sizes > 0 and BestIndi.ObjV.shape[1] > 1:
            costs = BestIndi.ObjV[:, 0] / 10000  # 转为万欧元
            matching = BestIndi.ObjV[:, 1]

            ax.scatter(
                costs,
                matching,
                c=colors[method],
                marker=markers[method],
                s=80,
                alpha=0.7,
                label=labels[method],
            )
            has_data = True

    # 方案A只有单目标，用竖线标注
    if "economic_only" in results:
        result = results["economic_only"]
        if result["best_indi"].sizes > 0:
            min_cost = np.min(result["best_indi"].ObjV[:, 0]) / 10000
            ax.axvline(
                x=min_cost,
                color=colors["economic_only"],
                linestyle="--",
                linewidth=2,
                label=f"{labels['economic_only']} (成本={min_cost:.2f}万€)",
            )
            has_data = True

    if has_data:
        ax.set_xlabel("年化总成本 (万€)", fontsize=12)
        ax.set_ylabel("源荷匹配度指标", fontsize=12)
        ax.set_title("CCHP系统规划 Pareto前沿对比", fontsize=14)
        ax.legend(loc="best", fontsize=10)
        ax.grid(True, alpha=0.3)

        png_path = os.path.join(result_dir, "Pareto_Comparison.png")
        plt.savefig(png_path, dpi=150, bbox_inches="tight")
        print(f"Pareto对比图已保存: {png_path}")
    else:
        print("警告: 没有足够数据绘制Pareto对比图")

    plt.close()


if __name__ == "__main__":
    # ========== 实验参数配置 ==========
    # nind: 种群规模 (建议 30-100)
    # maxgen: 最大代数 (测试用10，正式运行建议 50-100)
    # inherit_population: 是否让本文方法(euclidean)继承师兄方法(std)的种群
    #                     注意：pearson/ssr等对照方法永远不继承，保证对比公平性
    # methods_to_run: 选择要运行的方法（可自由组合）

    # ========== 可选方法说明 ==========
    # 'economic_only': 方案A-单目标经济（基准组）
    # 'std':           方案B-波动率匹配度（师兄方法，对照组）
    # 'euclidean':     方案C-能质耦合欧氏距离（本文核心创新，实验组）
    # 'pearson':       方案D-皮尔逊相关系数（只看趋势不看大小，对照组）
    # 'ssr':           方案E-供需重叠度SSR（只看总量不看能质，对照组）

    results, result_dir = run_comparative_study(
        nind=20,  # 种群规模
        maxgen=10,  # 最大代数（测试用，正式运行改为200）
        pool_type="Process",
        inherit_population=False,  # 开启种群继承(仅euclidean继承std)
        methods_to_run=[
            "std",  # 师兄方法（必须先运行，供euclidean继承）
            "euclidean",  # 本文方法（继承std种群）
            # "pearson",  # 皮尔逊法（独立运行）
            # "ssr",  # SSR法（独立运行）
            # "economic_only",  # 单目标基准
        ],
    )

    print(f"\n\n{'=' * 70}")
    print("所有实验完成！")
    print(f"结果保存在: {result_dir}")
    print("=" * 70)
