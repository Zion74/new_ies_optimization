# -*- coding: utf-8 -*-
"""
分布式电热综合能源系统规划优化主程序
基于 NSGA-II 算法求解 Pareto 前沿

创新点：
1. 针对分布式电热综合能源系统（移除冷相关设备）
2. 提出基于 Pearson 相关系数的源荷匹配度指标
3. 双目标优化：经济性 vs 源荷匹配度

@author: Based on Frank's work
"""

import os
import datetime

# 强制指定 Gurobi 许可证文件路径
os.environ["GRB_LICENSE_FILE"] = r"C:\gurobi\gurobi.lic"

import geatpy as ea
from heat_ele_gaproblem import HeatEleProblem
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


class MyNSGA2(ea.moea_NSGA2_templet):
    """自定义 NSGA-II 算法，增加日志输出"""

    def logging(self, pop):
        super().logging(pop)

        # 输出当前代的最优解
        best_eco_idx = np.argmin(pop.ObjV[:, 0])
        best_eco_val = pop.ObjV[best_eco_idx, 0]
        best_eco_match = pop.ObjV[best_eco_idx, 1]

        best_match_idx = np.argmin(pop.ObjV[:, 1])
        best_match_val = pop.ObjV[best_match_idx, 1]
        best_match_eco = pop.ObjV[best_match_idx, 0]

        print(f"\n  [第 {self.currentGen} 代统计]")
        print(
            f"  ★ 最低成本方案: 成本={best_eco_val:,.2f}元, 匹配度={-best_eco_match:.4f}"
        )
        print(
            f"  ★ 最佳匹配方案: 成本={best_match_eco:,.2f}元, 匹配度={-best_match_val:.4f}"
        )
        print("-" * 60)


def run_optimization(
    nind=30,
    maxgen=10,
    matching_method="pearson",
    pool_type="Process",
):
    """
    运行优化

    Parameters
    ----------
    nind : int
        种群规模
    maxgen : int
        最大进化代数
    matching_method : str
        源荷匹配度计算方法: 'pearson', 'std', 'ltpr'
    pool_type : str
        并行计算方式: 'Process' 或 'Thread'
    """
    print("=" * 70)
    print("分布式电热综合能源系统规划优化")
    print("=" * 70)
    print(f"种群规模: {nind}")
    print(f"最大代数: {maxgen}")
    print(f"源荷匹配度方法: {matching_method}")
    print(f"并行方式: {pool_type}")
    print("=" * 70)

    # 实例化问题对象
    problem = HeatEleProblem(pool_type, matching_method=matching_method)

    # 种群设置
    Encoding = "RI"
    Field = ea.crtfld(Encoding, problem.varTypes, problem.ranges, problem.borders)
    population = ea.Population(Encoding, Field, nind)

    # 算法参数设置
    myAlgorithm = MyNSGA2(problem, population)
    myAlgorithm.MAXGEN = maxgen
    myAlgorithm.mutOper.Pm = 0.1  # 变异概率
    myAlgorithm.recOper.XOVR = 0.9  # 交叉概率
    myAlgorithm.logTras = 1
    myAlgorithm.verbose = True
    myAlgorithm.drawing = 1

    try:
        # 运行优化
        [BestIndi, population] = myAlgorithm.run()

        print(f"\n优化完成，耗时 {myAlgorithm.passTime:.2f} 秒")

        # 创建结果文件夹
        current_time = datetime.datetime.now().strftime("%m-%d-%H-%M")
        result_dir = f"Result_HeatEle_{matching_method}_{current_time}"
        os.makedirs(result_dir, exist_ok=True)
        print(f"创建结果文件夹: {result_dir}")

        if BestIndi.sizes != 0:
            print(f"找到 {BestIndi.sizes} 个 Pareto 前沿解")

            # 保存结果到 CSV
            var_names = ["PV", "WT", "GT", "HP", "ES", "HS"]
            obj_names = ["Economic_Cost", "Matching_Index"]

            data_vars = BestIndi.Phen
            data_objs = BestIndi.ObjV.copy()

            # 如果使用 pearson 方法，将匹配度指标转回正值
            if matching_method in ["pearson", "ltpr"]:
                data_objs[:, 1] = -data_objs[:, 1]
                obj_names[1] = "Matching_Degree"

            df_pareto = pd.DataFrame(
                np.hstack([data_objs, data_vars]), columns=obj_names + var_names
            )
            df_pareto = df_pareto.sort_values(by="Economic_Cost")

            csv_path = os.path.join(result_dir, "Pareto_Front.csv")
            df_pareto.to_csv(csv_path, index=True, index_label="Solution_ID")
            print(f"Pareto 前沿解已保存至: {csv_path}")

            # 绘制 Pareto 前沿曲线
            fig, ax = plt.subplots(figsize=(10, 7))

            if matching_method in ["pearson", "ltpr"]:
                x_data = df_pareto["Economic_Cost"] / 10000  # 万元
                y_data = df_pareto["Matching_Degree"]
                ylabel = "源荷匹配度 (Pearson 相关系数)"
            else:
                x_data = df_pareto["Economic_Cost"] / 10000
                y_data = df_pareto[obj_names[1]]
                ylabel = "源荷匹配度 (净负荷标准差, kW)"

            ax.scatter(
                x_data, y_data, c="steelblue", s=80, alpha=0.7, edgecolors="navy"
            )

            # 标注极值点
            min_cost_idx = x_data.idxmin()
            ax.scatter(
                x_data.loc[min_cost_idx],
                y_data.loc[min_cost_idx],
                c="red",
                s=150,
                marker="*",
                label="最低成本方案",
                zorder=5,
            )

            if matching_method in ["pearson", "ltpr"]:
                best_match_idx = y_data.idxmax()
            else:
                best_match_idx = y_data.idxmin()

            ax.scatter(
                x_data.loc[best_match_idx],
                y_data.loc[best_match_idx],
                c="green",
                s=150,
                marker="*",
                label="最佳匹配方案",
                zorder=5,
            )

            ax.set_xlabel("年化总成本 (万元)", fontsize=12)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_title("分布式电热综合能源系统规划 Pareto 前沿", fontsize=14)
            ax.legend(loc="best", fontsize=10)
            ax.grid(True, alpha=0.3)

            png_path = os.path.join(result_dir, "Pareto_Front.png")
            plt.savefig(png_path, dpi=150, bbox_inches="tight")
            print(f"Pareto 前沿图已保存至: {png_path}")
            plt.close()

            # 保存详细数据
            np.savetxt(
                os.path.join(result_dir, "ObjV.csv"), BestIndi.ObjV, delimiter=","
            )
            np.savetxt(
                os.path.join(result_dir, "Phen.csv"), BestIndi.Phen, delimiter=","
            )

            # 输出典型方案
            print("\n" + "=" * 70)
            print("典型规划方案")
            print("=" * 70)

            # 最低成本方案
            min_cost_row = df_pareto.loc[df_pareto["Economic_Cost"].idxmin()]
            print("\n【最低成本方案】")
            print(f"  年化总成本: {min_cost_row['Economic_Cost']:,.2f} 元")
            print(
                f"  源荷匹配度: {min_cost_row[obj_names[1] if matching_method == 'std' else 'Matching_Degree']:.4f}"
            )
            print(f"  设备配置:")
            print(f"    光伏: {min_cost_row['PV']:.1f} kW")
            print(f"    风电: {min_cost_row['WT']:.1f} kW")
            print(f"    燃气轮机CHP: {min_cost_row['GT']:.1f} kW")
            print(f"    电热泵: {min_cost_row['HP']:.1f} kW")
            print(f"    电储能: {min_cost_row['ES']:.1f} kW")
            print(f"    热储能: {min_cost_row['HS']:.1f} kW")

            # 最佳匹配方案
            if matching_method in ["pearson", "ltpr"]:
                best_match_row = df_pareto.loc[df_pareto["Matching_Degree"].idxmax()]
            else:
                best_match_row = df_pareto.loc[df_pareto[obj_names[1]].idxmin()]

            print("\n【最佳源荷匹配方案】")
            print(f"  年化总成本: {best_match_row['Economic_Cost']:,.2f} 元")
            print(
                f"  源荷匹配度: {best_match_row[obj_names[1] if matching_method == 'std' else 'Matching_Degree']:.4f}"
            )
            print(f"  设备配置:")
            print(f"    光伏: {best_match_row['PV']:.1f} kW")
            print(f"    风电: {best_match_row['WT']:.1f} kW")
            print(f"    燃气轮机CHP: {best_match_row['GT']:.1f} kW")
            print(f"    电热泵: {best_match_row['HP']:.1f} kW")
            print(f"    电储能: {best_match_row['ES']:.1f} kW")
            print(f"    热储能: {best_match_row['HS']:.1f} kW")

        else:
            print("未找到可行解！")

    finally:
        problem.kill_pool()

    return result_dir


if __name__ == "__main__":
    # 运行优化
    # 可选参数:
    #   nind: 种群规模 (建议 30-100)
    #   maxgen: 最大代数 (建议 50-200)
    #   matching_method: 'pearson' (推荐), 'std', 'ltpr'

    result_dir = run_optimization(
        nind=30,  # 种群规模
        maxgen=10,  # 最大代数（测试用，正式运行建议 50-100）
        matching_method="pearson",  # 使用 Pearson 相关系数方法
        pool_type="Process",
    )

    print(f"\n结果已保存至: {result_dir}")
