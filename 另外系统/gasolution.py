# -*- coding: utf-8 -*-
"""
Created on Thu Apr 15 15:47:38 2021

@author: Frank
"""

import os
import datetime

# 强制指定 Gurobi 许可证文件路径（解决许可证过期问题）
os.environ["GRB_LICENSE_FILE"] = r"C:\gurobi\gurobi.lic"

import geatpy as ea
from gaproblem import MyProblem
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# 自定义算法类，用于输出每一代的最优结果
class MyNSGA2(ea.moea_NSGA2_templet):
    def logging(self, pop):
        # 调用父类的 logging 方法保持原有输出
        super().logging(pop)

        # 找出当前种群中非支配解（Pareto前沿）或者单目标最优解
        # 这里我们输出两个极端：经济成本最低的 和 源荷匹配度最好的

        # 1. 经济成本最低 (Objective 0)
        best_eco_idx = np.argmin(pop.ObjV[:, 0])
        best_eco_val = pop.ObjV[best_eco_idx, 0]
        best_eco_match = pop.ObjV[best_eco_idx, 1]

        # 2. 源荷匹配度最好 (Objective 1)
        best_match_idx = np.argmin(pop.ObjV[:, 1])
        best_match_val = pop.ObjV[best_match_idx, 1]
        best_match_eco = pop.ObjV[best_match_idx, 0]

        print(f"\n  [第 {self.currentGen} 代统计]")
        print(
            f"  ★ 最低经济成本方案: 成本={best_eco_val:,.2f} 元, 匹配度={best_eco_match:.4f}"
        )
        print(
            f"  ★ 最佳源荷匹配方案: 成本={best_match_eco:,.2f} 元, 匹配度={best_match_val:.4f}"
        )
        print("-" * 60)


# 我是 项目总指挥 。我规定了我们要尝试设计 50 个方案（种群规模），进化 200 代（迭代次数），最后找出最好的设计方案。

if __name__ == "__main__":
    """================================实例化问题对象==========================="""
    PoolType = "Process"  # 'Thread'用多线程，'Process'用多进程
    problem = MyProblem(PoolType)  # 生成问题对象
    """==================================种群设置=============================="""
    Encoding = "RI"  # 编码方式
    NIND = 30  # 种群规模 (建议 50-100)
    Field = ea.crtfld(
        Encoding, problem.varTypes, problem.ranges, problem.borders
    )  # 创建区域描述器
    population = ea.Population(
        Encoding, Field, NIND
    )  # 实例化种群对象（此时种群还没被初始化，仅仅是完成种群对象的实例化）
    """================================算法参数设置============================="""
    myAlgorithm = MyNSGA2(problem, population)  # 实例化自定义算法对象
    myAlgorithm.MAXGEN = 10  # 最大进化代数 (建议 100-200)
    myAlgorithm.mutOper.Pm = 0.1  # 变异概率
    myAlgorithm.recOper.XOVR = 0.9  # 交叉概率
    myAlgorithm.logTras = 1  # 设置每隔多少代记录日志，若设置成0则表示不记录日志
    myAlgorithm.verbose = True  # 设置是否打印输出日志信息
    myAlgorithm.drawing = 1  # 设置绘图方式（0：不绘图；1：绘制结果图；2：绘制目标空间过程动画；3：绘制决策空间过程动画）
    """===========================调用算法模板进行种群进化========================"""
    try:
        [BestIndi, population] = (
            myAlgorithm.run()
        )  # 执行算法模板，得到最优个体以及最后一代种群

        print("时间已过 %s 秒" % (myAlgorithm.passTime))

        """=================================结果保存==============================="""
        # 1. 创建带时间戳的结果文件夹
        current_time = datetime.datetime.now().strftime("%m-%d-%H-%M")
        result_dir = f"Result_{current_time}"
        os.makedirs(result_dir, exist_ok=True)
        print(f"创建结果文件夹: {result_dir}")

        if BestIndi.sizes != 0:
            print(f"找到 {BestIndi.sizes} 个帕累托前沿解。")

            # 2. 保存帕累托前沿解到 CSV 文件
            var_names = ["PV", "WT", "GT", "HP", "EC", "AC", "ES", "HS", "CS"]
            obj_names = ["Economic Cost", "Matching Degree"]

            data_vars = BestIndi.Phen
            data_objs = BestIndi.ObjV

            df_pareto = pd.DataFrame(
                np.hstack([data_objs, data_vars]), columns=obj_names + var_names
            )
            df_pareto = df_pareto.sort_values(by="Economic Cost")

            csv_path = os.path.join(result_dir, "Pareto_Front.csv")
            df_pareto.to_csv(csv_path, index=True, index_label="Solution_ID")
            print(f"帕累托前沿解已保存至: {csv_path}")

            # 3. 绘制帕累托前沿曲线
            plt.figure(figsize=(10, 6))
            plt.scatter(
                df_pareto["Economic Cost"],
                df_pareto["Matching Degree"],
                c="blue",
                marker="o",
                label="Pareto Solutions",
            )
            plt.xlabel("Economic Cost (RMB)")
            plt.ylabel("Source-Load Matching Degree")
            plt.title("Pareto Front: Cost vs Matching")
            plt.grid(True)
            plt.legend()

            # 标注关键点
            min_cost_idx = df_pareto["Economic Cost"].idxmin()
            min_match_idx = df_pareto["Matching Degree"].idxmin()

            plt.scatter(
                df_pareto.loc[min_cost_idx, "Economic Cost"],
                df_pareto.loc[min_cost_idx, "Matching Degree"],
                c="red",
                s=100,
                label="Min Cost",
            )
            plt.scatter(
                df_pareto.loc[min_match_idx, "Economic Cost"],
                df_pareto.loc[min_match_idx, "Matching Degree"],
                c="green",
                s=100,
                label="Best Matching",
            )

            png_path = os.path.join(result_dir, "Pareto_Front_Curve.png")
            plt.show()
            plt.savefig(png_path)
            print(f"帕累托前沿曲线已保存至: {png_path}")

            # 4. 保存 Population Info (原始数据)
            # 保存最优个体的 ObjV (目标函数值), Phen (表现型/决策变量), Chrom (染色体/基因)
            np.savetxt(
                os.path.join(result_dir, "ObjV.csv"), BestIndi.ObjV, delimiter=","
            )
            np.savetxt(
                os.path.join(result_dir, "Phen.csv"), BestIndi.Phen, delimiter=","
            )
            if BestIndi.Chrom is not None:
                np.savetxt(
                    os.path.join(result_dir, "Chrom.csv"), BestIndi.Chrom, delimiter=","
                )

            # 保存适应度
            if BestIndi.FitnV is not None:
                np.savetxt(
                    os.path.join(result_dir, "FitnV.csv"), BestIndi.FitnV, delimiter=","
                )

            print(
                f"种群详细信息 (ObjV, Phen, Chrom, FitnV) 已保存至文件夹: {result_dir}"
            )

            print("最优的目标函数值为：%s" % (BestIndi.ObjV[0][0]))
            print("最优的控制变量值为：")
            for i in range(BestIndi.Phen.shape[1]):
                print(BestIndi.Phen[0, i])
        else:
            print("没找到可行解。")
    finally:
        problem.kill_pool()
