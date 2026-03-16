# -*- coding: utf-8 -*-
"""
分布式电热综合能源系统规划优化问题定义
基于 NSGA-II 算法的双目标优化：
  - 目标1：年化总成本（经济性）
  - 目标2：源荷匹配度（基于 Pearson 相关系数，越大越好，取负值转为最小化）

决策变量（6个）：
  - ppv: 光伏容量 (kW)
  - pwt: 风电容量 (kW)
  - pgt: 燃气轮机CHP容量 (kW)
  - php: 电热泵容量 (kW)
  - pes: 电储能功率 (kW)
  - phs: 热储能功率 (kW)

@author: Based on Frank's work, modified for heat-electricity system

                    ┌─────────────────────────────────────┐
                    │        遗传算法 (NSGA-II)           │
                    │   种群规模=30, 进化代数=100         │
                    └─────────────┬───────────────────────┘
                                  │ 每一代调用 aimFunc()
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         HeatEleProblem.aimFunc()                    │
│  输入: pop.Phen (30×7 矩阵，每行一个方案)                            │
│  输出: pop.ObjV (30×2 矩阵，每行两个目标值)                          │
└─────────────────────────────────────┬───────────────────────────────┘
                                      │ 并行调用
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
        ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
        │ 方案1计算      │   │ 方案2计算      │   │ 方案30计算    │
        │               │   │               │   │               │
        │ sub_aim_func  │   │ sub_aim_func  │   │ sub_aim_func  │
        │ _heat_ele()   │   │ _heat_ele()   │   │ _heat_ele()   │
        └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
                │                   │                   │
                ▼                   ▼                   ▼
        ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
        │ HeatEleModel  │   │ HeatEleModel  │   │ HeatEleModel  │
        │ 调度优化       │   │ 调度优化       │   │ 调度优化       │
        └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
                │                   │                   │
                ▼                   ▼                   ▼
        [成本, 匹配度]      [成本, 匹配度]      [成本, 匹配度]
"""

import geatpy as ea
import pandas as pd
import numpy as np
from operation import HeatEleModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
from multiprocessing.dummy import Pool as ThreadPool


class HeatEleProblem(ea.Problem):
    """分布式电热综合能源系统规划问题"""

    def __init__(self, PoolType, matching_method="pearson"):
        """
        初始化问题

        Parameters
        ----------
        PoolType : str
            'Thread' 使用多线程, 'Process' 使用多进程
        matching_method : str
            源荷匹配度计算方法:
            - 'pearson': Pearson相关系数（推荐，本文创新点）
            - 'std': 净负荷标准差（与原代码兼容）
            - 'ltpr': 负荷跟踪偏差率
        """
        # 加载运行数据
        operation_data = pd.read_csv("mergedData.csv")
        self.operation_list = np.array(operation_data).tolist()

        # 加载典型日数据
        self.typical_days = dict()
        typical_data = pd.read_excel("typicalDayData.xlsx")
        typical_day_id = typical_data["typicalDayId"]
        days_str = typical_data["days"]
        for i in range(len(typical_day_id)):
            days_list = list(map(int, days_str[i].split(",")))
            self.typical_days[typical_day_id[i]] = days_list

        # 保存源荷匹配度计算方法
        self.matching_method = matching_method

        name = "HeatEleProblem"  # 问题名称
        M = 2  # 目标维数
        Dim = 6  # 决策变量维数（6个设备容量）

        # 目标最小化标记（1：最小化，-1：最大化）
        # 两个目标都是最小化：成本最小化，源荷匹配度取负后最小化
        maxormins = [1] * M

        varTypes = [0] * Dim  # 决策变量类型（0：实数）

        # 决策变量边界（与原项目数据保持一致）
        # [ppv, pwt, pgt, php, pes, phs]
        lb = [0] * Dim  # 下界
        ub = [
            10000,  # ppv: 光伏容量上限 10MW
            10000,  # pwt: 风电容量上限 10MW
            10000,  # pgt: 燃气轮机CHP上限 10MW
            3000,  # php: 电热泵上限 3MW
            20000,  # pes: 电储能功率上限 20MW
            6000,  # phs: 热储能功率上限 6MW
        ]
        lbin = [1] * Dim  # 包含下边界
        ubin = [1] * Dim  # 包含上边界

        # 调用父类构造方法
        ea.Problem.__init__(self, name, M, maxormins, Dim, varTypes, lb, ub, lbin, ubin)

        # 设置并行计算
        self.PoolType = PoolType
        if self.PoolType == "Thread":
            self.pool = ThreadPool(4)
        elif self.PoolType == "Process":
            num_cores = int(mp.cpu_count())
            print(f"使用 {num_cores} 核心进行并行计算")
            self.pool = ProcessPool(num_cores)

    def aimFunc(self, pop):
        """目标函数计算"""
        if not hasattr(self, "gen_counter"):
            self.gen_counter = -1
        self.gen_counter += 1

        print(
            f"\n{'=' * 60}\n开始计算第 {self.gen_counter} 代种群 (规模: {pop.sizes})\n{'=' * 60}"
        )

        Vars = pop.Phen
        args = list(
            zip(
                list(range(pop.sizes)),
                [Vars] * pop.sizes,
                [self.operation_list] * pop.sizes,
                [self.typical_days] * pop.sizes,
                [pop.sizes] * pop.sizes,
                [self.matching_method] * pop.sizes,
            )
        )

        if self.PoolType == "Thread":
            pop.ObjV = np.array(list(self.pool.map(sub_aim_func_heat_ele, args)))
        elif self.PoolType == "Process":
            result = self.pool.map_async(sub_aim_func_heat_ele, args)
            result.wait()
            pop.ObjV = np.array(result.get())

    def kill_pool(self):
        """关闭进程池"""
        self.pool.close()


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


def sub_aim_func_heat_ele(args):
    """
    子目标函数：计算单个方案的目标函数值
    用于并行计算
    """
    i = args[0]
    Vars = args[1]
    operation_list = args[2]
    typical_days = args[3]
    pop_size = args[4]
    matching_method = args[5]

    should_print = (i % 10 == 0) or (i == pop_size - 1)

    # 解析决策变量
    ppv = Vars[i, 0]  # 光伏容量
    pwt = Vars[i, 1]  # 风电容量
    pgt = Vars[i, 2]  # 燃气轮机CHP容量
    php = Vars[i, 3]  # 电热泵容量
    pes = Vars[i, 4]  # 电储能功率
    phs = Vars[i, 5]  # 热储能功率

    # 初始化
    oc = 0  # 运行成本
    net_ele_load = [0 for _ in range(8760)]
    net_heat_load = [0 for _ in range(8760)]

    # 用于 Pearson 相关系数计算的累积值
    all_re_output = []
    all_ele_load = []
    all_heat_load = []

    time_step = 24
    ele_price = [0.1598] * time_step  # 电价 (元/kWh)，与原项目数据一致
    gas_price = [0.0286] * time_step  # 气价 (元/kWh)，与原项目数据一致

    ele_load = [0] * time_step
    heat_load = [0] * time_step
    solar_radiation_list = [0] * time_step
    wind_speed_list = [0] * time_step
    temperature_list = [0] * time_step

    is_success = True

    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24

        # 提取典型日数据
        for t in range(time_start, time_start + time_step):
            ele_load[t % 24] = operation_list[t][0]
            heat_load[t % 24] = operation_list[t][1]
            # cool_load 不再使用
            solar_radiation_list[t % 24] = operation_list[t][3]
            wind_speed_list[t % 24] = operation_list[t][4]
            temperature_list[t % 24] = operation_list[t][5]

        # 计算可再生能源出力
        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)

        # 创建并优化模型
        operation_model = HeatEleModel(
            "01/01/2019",
            time_step,
            ele_price,
            gas_price,
            ele_load,
            heat_load,
            wt_output,
            pv_output,
            pgt,
            php,
            pes,
            phs,
        )

        try:
            operation_model.optimise()
            obj_val = operation_model.get_objective_value()

            if obj_val is None or np.isnan(obj_val):
                raise ValueError(f"Invalid objective value: {obj_val}")

            oc += obj_val * len(typical_days[cluster_medoid])
            complementary_results = operation_model.get_complementary_results()

            # 检查结果
            for key, val in complementary_results.items():
                if np.any(np.isnan(val)):
                    raise ValueError(f"Result for {key} contains NaN")

        except Exception as e:
            if should_print:
                print(f"  > 方案 {i + 1} 优化失败: {e}")
            is_success = False
            break

        # 记录净负荷数据
        for d in typical_days[cluster_medoid]:
            start_index = (d - 1) * 24
            for k in range(24):
                net_ele_load[start_index + k] = (
                    complementary_results["grid"][k]
                    - complementary_results["electricity overflow"][k]
                )
                net_heat_load[start_index + k] = (
                    complementary_results["heat source"][k]
                    - complementary_results["heat overflow"][k]
                )

        # 累积数据用于 Pearson 计算
        re_output = [pv + wt for pv, wt in zip(pv_output, wt_output)]
        all_re_output.extend(re_output * len(typical_days[cluster_medoid]))
        all_ele_load.extend(ele_load * len(typical_days[cluster_medoid]))
        all_heat_load.extend(heat_load * len(typical_days[cluster_medoid]))

    # 计算目标函数值
    if is_success:
        # =============== 目标1：经济性（年化总成本） ===============
        # 采用与原项目一致的年化投资系数 (元/(kW·年))
        # 年化系数已包含投资成本年化和运维成本
        economic_obj = (
            76.44188371 * ppv  # 光伏年化系数
            + 110.4233218 * pwt  # 风电年化系数
            + 50.32074101 * pgt  # 燃气轮机CHP年化系数
            + 21.21527903 * php  # 电热泵年化系数
            + 35.11456751 * pes  # 电储能年化系数
            + 1.689590459 * phs  # 热储能年化系数
            + 520 * (phs > 0.1)  # 热储能固定成本（如果配置了热储能）
            + oc  # 运行成本
        )

        # =============== 目标2：源荷匹配度 ===============
        if matching_method == "pearson":
            # 基于 Pearson 相关系数的源荷匹配度
            # 计算可再生能源出力与负荷的相关系数
            re_arr = np.array(all_re_output)
            ele_arr = np.array(all_ele_load)
            heat_arr = np.array(all_heat_load)

            # 电侧相关系数
            if np.std(re_arr) > 1e-6 and np.std(ele_arr) > 1e-6:
                rho_ele = np.corrcoef(re_arr, ele_arr)[0, 1]
            else:
                rho_ele = 0.0

            # 热侧相关系数
            if np.std(re_arr) > 1e-6 and np.std(heat_arr) > 1e-6:
                rho_heat = np.corrcoef(re_arr, heat_arr)[0, 1]
            else:
                rho_heat = 0.0

            # 加权平均（按负荷比例）
            total_ele = np.sum(ele_arr)
            total_heat = np.sum(heat_arr)
            ele_weight = total_ele / (total_ele + total_heat + 1e-6)
            heat_weight = 1 - ele_weight

            slmd = ele_weight * rho_ele + heat_weight * rho_heat

            # 取负值，使其成为最小化问题（相关系数越大越好）
            matching_obj = -slmd

        elif matching_method == "std":
            # 基于净负荷标准差（与原代码兼容）
            matching_obj = np.std(net_ele_load) + np.std(net_heat_load)

        elif matching_method == "ltpr":
            # 基于负荷跟踪偏差率
            re_arr = np.array(all_re_output)
            ele_arr = np.array(all_ele_load)
            if np.max(ele_arr) > 1e-6:
                deviation = np.mean(np.abs(re_arr - ele_arr)) / np.max(ele_arr)
                ltpr = 1 - deviation
            else:
                ltpr = 0
            # 取负值，使其成为最小化问题
            matching_obj = -ltpr

        else:
            matching_obj = np.std(net_ele_load) + np.std(net_heat_load)

        # 检查 NaN
        if np.isnan(matching_obj) or np.isnan(economic_obj):
            matching_obj = 1e10
            economic_obj = 1e10
            if should_print:
                print(f"  > 警告: 方案 {i + 1} 计算结果为 NaN")

    else:
        # 优化失败，给予惩罚值
        economic_obj = 1e10
        matching_obj = 1e10

    if should_print:
        print(
            f"  > 方案 {i + 1} | 经济成本: {economic_obj:,.2f} 元 | "
            f"源荷匹配度: {matching_obj:.4f}"
        )
        print(
            f"    配置: PV={ppv:.0f}kW, WT={pwt:.0f}kW, GT={pgt:.0f}kW, "
            f"HP={php:.0f}kW, ES={pes:.0f}kW, HS={phs:.0f}kW"
        )

    return [economic_obj, matching_obj]
