# -*- coding: utf-8 -*-
"""
Created on Thu Apr 15 15:27:15 2021

@author: Frank
"""

import geatpy as ea
import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
from multiprocessing.dummy import Pool as ThreadPool


class MyProblem(ea.Problem):  # 继承Problem父类
    def __init__(self, PoolType):
        operation_data = pd.read_csv("mergedData.csv")
        self.operation_list = np.array(operation_data).tolist()
        self.typical_days = dict()
        typical_data = pd.read_excel("typicalDayData.xlsx")
        typical_day_id = typical_data["typicalDayId"]
        days_str = typical_data["days"]
        for i in range(len(typical_day_id)):
            days_list = list(map(int, days_str[i].split(",")))
            self.typical_days[typical_day_id[i]] = days_list
        name = "MyProblem"  # 初始化name（函数名称，可以随意设置）
        M = 2  # 初始化M（目标维数）
        Dim = 9  # 初始化Dim（决策变量维数）
        maxormins = (
            [1] * M
        )  # 初始化maxormins（目标最小最大化标记列表，1：最小化该目标；-1：最大化该目标）
        varTypes = [0] * Dim  # 初始化varTypes（决策变量的类型，0：实数；1：整数）
        lb = [0] * Dim  # 决策变量下界
        ub = [10000, 10000, 10000, 3000, 1000, 1000, 20000, 6000, 2000]  # 决策变量上界
        lbin = [1] * Dim  # 决策变量下边界（0表示不包含该变量的下边界，1表示包含）
        ubin = [1] * Dim  # 决策变量上边界（0表示不包含该变量的上边界，1表示包含）
        # 调用父类构造方法完成实例化
        ea.Problem.__init__(self, name, M, maxormins, Dim, varTypes, lb, ub, lbin, ubin)
        # 设置用多线程还是多进程
        self.PoolType = PoolType
        if self.PoolType == "Thread":
            self.pool = ThreadPool(4)  # 设置池的大小
        elif self.PoolType == "Process":
            num_cores = int(mp.cpu_count())  # 获得计算机的核心数
            print("num_cores:" + str(num_cores))
            self.pool = ProcessPool(num_cores)  # 设置池的大小

    def aimFunc(self, pop):  # 目标函数
        # 尝试获取当前代数，如果获取不到（第一代可能没有），则默认为 0 或 1
        # Geatpy 的 Problem 类本身不直接存储 currentGen，通常由 Algorithm 类控制
        # 但我们可以通过一个类属性来简单计数，或者尝试从外部传入（比较麻烦）
        # 这里使用一个简单的计数器属性，如果不存在则初始化
        if not hasattr(self, "gen_counter"):
            self.gen_counter = -1
        self.gen_counter += 1

        print(
            f"\n========== 开始计算第 {self.gen_counter} 代种群 (规模: {pop.sizes}) =========="
        )
        # 获取决策变量值
        Vars = pop.Phen  # 得到决策变量矩阵
        args = list(
            zip(
                list(range(pop.sizes)),
                [Vars] * pop.sizes,
                [self.operation_list] * pop.sizes,
                [self.typical_days] * pop.sizes,
                [pop.sizes] * pop.sizes,  # 传入种群总大小，用于控制打印频率
            )
        )
        if self.PoolType == "Thread":
            pop.ObjV = np.array(list(self.pool.map(subAimFunc, args)))
        elif self.PoolType == "Process":
            result = self.pool.map_async(subAimFunc, args)
            result.wait()
            pop.ObjV = np.array(result.get())

    def kill_pool(self):
        self.pool.close()


def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    return [
        ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
        for r, t in zip(solar_radiation_list, temperature_list)
    ]


def cal_wind_output(wind_speed_list, pwt):
    ret = [0 for _ in range(len(wind_speed_list))]
    for i in range(len(wind_speed_list)):
        w = wind_speed_list[i]
        if 2.5 <= w < 9:
            ret[i] = (w**3 - 2.5**3) / (9**3 - 2.5**3) * pwt
        elif 9 <= w < 25:
            ret[i] = pwt
    return ret


def subAimFunc(args):
    i = args[0]
    Vars = args[1]
    operation_list = args[2]
    typical_days = args[3]
    pop_size = args[4]  # 获取种群大小

    # 控制打印频率：只打印约 1/10 的日志
    # 由于是并行计算，打印顺序可能混乱，但总量会减少
    should_print = (i % 10 == 0) or (i == pop_size - 1)

    # print(f"  > 方案 {i+1} 开始计算...") # 调试用
    ppv = Vars[i, 0]  # 光伏额定功率
    pwt = Vars[i, 1]  # 风电额定功率
    pgt = Vars[i, 2]  # 燃气轮机额定功率
    php = Vars[i, 3]  # 电热泵额定功率
    pec = Vars[i, 4]  # 电制冷额定功率
    pac = Vars[i, 5]  # 吸收式制冷额定功率
    pes = Vars[i, 6]  # 电储能额定功率
    phs = Vars[i, 7]  # 热储能额定功率
    pcs = Vars[i, 8]  # 冷储能额定功率
    oc = 0
    net_ele_load = [0 for _ in range(8760)]  # 电净负荷
    net_heat_load = [0 for _ in range(8760)]  # 热净负荷
    net_cool_load = [0 for _ in range(8760)]  # 冷净负荷
    time_step = 24
    ele_price = [0.1598 for _ in range(time_step)]
    gas_price = [0.0286 for _ in range(time_step)]
    ele_load = [0 for _ in range(time_step)]
    heat_load = [0 for _ in range(time_step)]
    cool_load = [0 for _ in range(time_step)]
    solar_radiation_list = [0 for _ in range(time_step)]
    wind_speed_list = [0 for _ in range(time_step)]
    temperature_list = [0 for _ in range(time_step)]
    is_success = True
    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24
        # 下层模型参数设置
        for t in range(time_start, time_start + time_step):
            ele_load[t % 24] = operation_list[t][0]
            heat_load[t % 24] = operation_list[t][1]
            cool_load[t % 24] = operation_list[t][2]
            solar_radiation_list[t % 24] = operation_list[t][3]
            wind_speed_list[t % 24] = operation_list[t][4]
            temperature_list[t % 24] = operation_list[t][5]
        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)
        # 底层模型初始化及优化
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
        try:
            # 优化并获取结果
            operation_model.optimise()
            obj_val = operation_model.get_objective_value()
            if obj_val is None or np.isnan(obj_val):
                raise ValueError(
                    f"Optimization returned invalid objective value: {obj_val}"
                )
            oc += obj_val * len(typical_days[cluster_medoid])
            complementary_results = operation_model.get_complementary_results()

            # 检查结果中是否有 NaN
            for key, val in complementary_results.items():
                if np.any(np.isnan(val)):
                    raise ValueError(f"Result for {key} contains NaN values")

        except Exception as e:
            if should_print:
                print(f"  > 方案 {i + 1} 优化失败: {e}")
            is_success = False
            break
        for d in typical_days[cluster_medoid]:
            start_index = (d - 1) * 24
            for k in range(24):  # 使用 k 避免覆盖外层 i
                # 修正源荷匹配度计算逻辑：直接使用 (输入 - 输出) 计算净负荷，物理意义更明确且数值更稳健
                net_ele_load[start_index + k] = (
                    complementary_results["grid"][k]
                    - complementary_results["electricity overflow"][k]
                )
                net_heat_load[start_index + k] = (
                    complementary_results["heat source"][k]
                    - complementary_results["heat overflow"][k]
                )
                net_cool_load[start_index + k] = (
                    complementary_results["cool source"][k]
                    - complementary_results["cool overflow"][k]
                )

    # 计算上层模型目标函数值
    if is_success:
        # 经济目标
        economic_obj_i = (
            76.44188371 * ppv
            + 110.4233218 * pwt
            + 50.32074101 * pgt
            + 21.21527903 * php
            + 22.85563566 * pec
            + 21.81674313 * pac
            + 35.11456751 * pes
            + 1.689590459 * (phs + pcs)
            + 520 * (phs > 0.1)
            + 520 * (pcs > 0.1)
            + oc
        )
        # 源荷匹配目标
        complementary_obj_i = (
            np.std(net_ele_load) + np.std(net_heat_load) + np.std(net_cool_load)
        )

        # 检查是否为 NaN，如果是则设为惩罚值
        if np.isnan(complementary_obj_i) or np.isnan(economic_obj_i):
            complementary_obj_i = 1e10
            economic_obj_i = 1e10
            if should_print:
                print(
                    f"  > 警告: 方案 {i + 1} 计算结果为 NaN (可能是标准差计算异常或优化结果异常)"
                )
    else:
        # 惩罚值：如果优化失败，给予一个非常大的惩罚值，而不是 inf
        # Geatpy 处理 inf 有时会出问题，或者导致后续计算指标时出现 NaN
        economic_obj_i = 1e10
        complementary_obj_i = 1e10

    if should_print:
        print(
            f"  > 方案 {i + 1} 计算完成 | 经济成本: {economic_obj_i:,.2f} 元 | 源荷匹配度: {complementary_obj_i:.4f}"
        )
        print(
            f"    配置详情: 光伏={ppv:.1f}kW, 风机={pwt:.1f}kW, 燃气轮机={pgt:.1f}kW, 热泵={php:.1f}kW, "
            f"电制冷={pec:.1f}kW, 吸收式制冷={pac:.1f}kW, 电池={pes:.1f}kW, 蓄热={phs:.1f}kW, 蓄冷={pcs:.1f}kW"
        )

    return [economic_obj_i, complementary_obj_i]
