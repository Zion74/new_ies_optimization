# -*- coding: utf-8 -*-
import sys, io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
电-热-冷综合能源系统(CCHP)规划优化问题定义
基于师兄EI论文原型，采用德国案例数据

对比实验设计（5种源荷匹配度量化方法）：
  - 方案A (economic_only)：单目标经济最优（基准组）
  - 方案B (std)：师兄的波动率匹配度（对照组）
  - 方案C (euclidean)：本文三维能质耦合匹配度（实验组-核心创新）
  - 方案D (pearson)：皮尔逊相关系数法（对照组-只看趋势不看大小）
  - 方案E (ssr)：供需重叠度/自给自足率法（对照组-只看总量不看能质）

决策变量（9个）：
  - ppv: 光伏容量 (kW)
  - pwt: 风电容量 (kW)
  - pgt: 燃气轮机CHP容量 (kW)
  - php: 电热泵容量 (kW)
  - pec: 电制冷容量 (kW)
  - pac: 吸收式制冷容量 (kW)
  - pes: 电储能功率 (kW)
  - phs: 热储能功率 (kW)
  - pcs: 冷储能功率 (kW)

@author: Based on Frank's work, modified for comparative study
"""

import geatpy as ea
import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
from multiprocessing.dummy import Pool as ThreadPool


# ========== 热力学参数（能质系数计算） ==========
T0 = 298.15  # 环境温度 25°C (K)
T_HEAT = 343.15  # 供热温度 70°C (K)
T_COOL = 280.15  # 供冷温度 7°C (K)

# 能质系数（基于卡诺因子）
LAMBDA_E = 1.0  # 电能权重（基准值）
LAMBDA_H = 0.6
LAMBDA_C = 0.5
# LAMBDA_H = 1 - T0 / T_HEAT  # 热能权重 ≈ 0.131
# LAMBDA_C = (T0 - T_COOL) / T_COOL  # 冷能权重 ≈ 0.064

# print(f"能质系数: λ_e={LAMBDA_E:.3f}, λ_h={LAMBDA_H:.3f}, λ_c={LAMBDA_C:.3f}")


class CCHPProblem(ea.Problem):
    """电-热-冷综合能源系统规划问题（CCHP）"""

    def __init__(self, PoolType, method="euclidean", case_config=None):
        """
        初始化问题

        Parameters
        ----------
        PoolType : str
            'Thread' 使用多线程, 'Process' 使用多进程
        method : str
            源荷匹配度计算方法:
            - 'economic_only': 单目标经济优化（方案A）
            - 'std': 净负荷标准差-师兄方法（方案B）
            - 'euclidean': 三维能质耦合欧氏距离-本文创新（方案C）
            - 'pearson': 皮尔逊相关系数法（方案D，只看趋势不看大小）
            - 'ssr': 供需重叠度/自给自足率法（方案E，只看总量不看能质）
        case_config : dict or None
            案例配置字典。None 则使用德国案例默认值（向后兼容）。
        """
        # 加载案例配置
        if case_config is None:
            from case_config import GERMAN_CASE
            case_config = GERMAN_CASE
        self.case_config = case_config

        # 从配置加载数据文件
        operation_data = pd.read_csv(case_config["data_file"])
        self.operation_list = np.array(operation_data).tolist()

        # 加载典型日数据
        self.typical_days = dict()
        typical_data = pd.read_excel(case_config["typical_day_file"])
        typical_day_id = typical_data["typicalDayId"]
        days_str = typical_data["days"]
        for i in range(len(typical_day_id)):
            days_list = list(map(int, days_str[i].split(",")))
            self.typical_days[typical_day_id[i]] = days_list

        # 保存方法类型
        self.method = method

        name = "CCHPProblem"

        # 根据方法确定目标维数
        if method == "economic_only":
            M = 1  # 单目标
        else:
            M = 2  # 双目标

        # 决策变量维数：基础9个 + 卡诺电池2个（可选）
        Dim = 9
        ub = list(case_config["var_ub"])
        if case_config.get("enable_carnot_battery", False):
            Dim = 11
            ub.append(case_config.get("cb_power_ub", 2000))
            ub.append(case_config.get("cb_capacity_ub", 10000))

        maxormins = [1] * M  # 都是最小化

        varTypes = [0] * Dim  # 决策变量类型（0：实数）

        lb = [0] * Dim
        lbin = [1] * Dim
        ubin = [1] * Dim

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
            f"\n{'=' * 60}\n[{self.method}] 第 {self.gen_counter} 代 (规模: {pop.sizes})\n{'=' * 60}"
        )

        Vars = pop.Phen
        args = list(
            zip(
                list(range(pop.sizes)),
                [Vars] * pop.sizes,
                [self.operation_list] * pop.sizes,
                [self.typical_days] * pop.sizes,
                [pop.sizes] * pop.sizes,
                [self.method] * pop.sizes,
                [self.case_config] * pop.sizes,
            )
        )

        if self.PoolType == "Thread":
            results = np.array(list(self.pool.map(sub_aim_func_cchp, args)))
        elif self.PoolType == "Process":
            result = self.pool.map_async(sub_aim_func_cchp, args)
            result.wait()
            results = np.array(result.get())

        # 根据方法设置目标值
        if self.method == "economic_only":
            pop.ObjV = results[:, 0:1]  # 只取经济目标
        else:
            pop.ObjV = results  # 取两个目标

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


def sub_aim_func_cchp(args):
    """
    子目标函数：计算单个方案的目标函数值

    返回: [economic_obj, matching_obj]
    """
    # 子进程里显式设置 Gurobi 许可证路径，确保多进程下 Gurobi 可用
    import os as _os
    _os.environ.setdefault("GRB_LICENSE_FILE", r"C:\Users\ikun\gurobi.lic")

    i = args[0]
    Vars = args[1]
    operation_list = args[2]
    typical_days = args[3]
    pop_size = args[4]
    method = args[5]
    config = args[6]

    # 从配置读取能质系数
    lambda_e = config.get("lambda_e", LAMBDA_E)
    lambda_h = config.get("lambda_h", LAMBDA_H)
    lambda_c = config.get("lambda_c", LAMBDA_C)
    currency = config.get("currency", "€")

    should_print = (i % 20 == 0) or (i == pop_size - 1)

    # 解析决策变量（9个基础 + 可选2个卡诺电池）
    ppv = Vars[i, 0]  # 光伏容量
    pwt = Vars[i, 1]  # 风电容量
    pgt = Vars[i, 2]  # 燃气轮机CHP容量
    php = Vars[i, 3]  # 电热泵容量
    pec = Vars[i, 4]  # 电制冷容量
    pac = Vars[i, 5]  # 吸收式制冷容量
    pes = Vars[i, 6]  # 电储能功率
    phs = Vars[i, 7]  # 热储能功率
    pcs = Vars[i, 8]  # 冷储能功率

    # 卡诺电池决策变量（可选）
    cb_power = 0
    cb_capacity = 0
    if config.get("enable_carnot_battery", False) and Vars.shape[1] >= 11:
        cb_power = Vars[i, 9]
        cb_capacity = Vars[i, 10]

    # 初始化
    oc = 0  # 运行成本

    # ===== 关键修复：使用8760长度数组，与师兄原始代码一致 =====
    net_ele_load = [0.0 for _ in range(8760)]  # 电净负荷
    net_heat_load = [0.0 for _ in range(8760)]  # 热净负荷
    net_cool_load = [0.0 for _ in range(8760)]  # 冷净负荷

    # 用于方案C（欧氏距离方法）的累积值
    euclidean_sum = 0.0

    # 用于方案D（皮尔逊相关系数）的累积数组
    gen_ele_list = [0.0 for _ in range(8760)]  # 电源侧出力（PV+WT+GT发电）
    gen_heat_list = [0.0 for _ in range(8760)]  # 热源侧出力（GT余热+EHP）
    gen_cool_list = [0.0 for _ in range(8760)]  # 冷源侧出力（EC+AC）
    load_ele_list = [0.0 for _ in range(8760)]  # 电负荷
    load_heat_list = [0.0 for _ in range(8760)]  # 热负荷
    load_cool_list = [0.0 for _ in range(8760)]  # 冷负荷

    # 用于方案E（SSR供需重叠度）的累积值
    total_grid_purchase = 0.0  # 总购网电量
    total_heat_source = 0.0  # 总外部热源补热
    total_cool_source = 0.0  # 总外部冷源补冷
    total_ele_load = 0.0  # 总电负荷
    total_heat_load = 0.0  # 总热负荷
    total_cool_load = 0.0  # 总冷负荷

    time_step = 24
    # 从配置读取电价和气价
    ele_price = config["ele_price"][:time_step]
    gas_price = config["gas_price"][:time_step]

    ele_load = [0] * time_step
    heat_load = [0] * time_step
    cool_load = [0] * time_step
    solar_radiation_list = [0] * time_step
    wind_speed_list = [0] * time_step
    temperature_list = [0] * time_step

    is_success = True
    max_grid_power = 0  # 记录电网最大需量

    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24

        # 提取典型日数据
        for t in range(time_start, time_start + time_step):
            ele_load[t % 24] = operation_list[t][0]
            heat_load[t % 24] = operation_list[t][1]
            cool_load[t % 24] = operation_list[t][2]
            solar_radiation_list[t % 24] = operation_list[t][3]
            wind_speed_list[t % 24] = operation_list[t][4]
            temperature_list[t % 24] = operation_list[t][5]

        # 计算可再生能源出力
        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)

        # 创建并优化模型（使用OperationModel，传入配置和卡诺电池参数）
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
            config=config,
            cb_power=cb_power,
            cb_capacity=cb_capacity,
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

        # ===== 关键修复：按照师兄原始代码的方式填充8760数组 =====
        for d in typical_days[cluster_medoid]:
            start_index = (d - 1) * 24  # 按日期索引填充
            for k in range(24):
                # 计算三维净负荷偏差
                # 电：电网交互量（购电为正，弃电为负）
                p_net_e = (
                    complementary_results["grid"][k]
                    - complementary_results["electricity overflow"][k]
                )
                # 热：热源补热 - 弃热
                p_net_h = (
                    complementary_results["heat source"][k]
                    - complementary_results["heat overflow"][k]
                )
                # 冷：冷源补冷 - 弃冷
                p_net_c = (
                    complementary_results["cool source"][k]
                    - complementary_results["cool overflow"][k]
                )

                # 填充到8760数组对应位置
                net_ele_load[start_index + k] = p_net_e
                net_heat_load[start_index + k] = p_net_h
                net_cool_load[start_index + k] = p_net_c

                # 更新电网最大需量
                grid_power = complementary_results["grid"][k]
                if grid_power > max_grid_power:
                    max_grid_power = grid_power

                # 方案C：计算欧氏距离（使用配置中的能质系数）
                if method == "euclidean":
                    term = np.sqrt(
                        (lambda_e * abs(p_net_e)) ** 2
                        + (lambda_h * abs(p_net_h)) ** 2
                        + (lambda_c * abs(p_net_c)) ** 2
                    )
                    euclidean_sum += term

                # 方案D/E：收集源侧出力和负荷数据
                if method in ("pearson", "ssr"):
                    # 由于 complementary_results 不包含详细设备出力，
                    # 使用能量平衡近似计算本地供应量：
                    #   本地供应 = 负荷 - 外购 + 弃能

                    # 电：本地发电 = 电负荷 - 电网购入 + 弃电
                    grid_val = complementary_results["grid"][k]
                    ele_overflow = complementary_results["electricity overflow"][k]
                    gen_e = ele_load[k] - grid_val + ele_overflow

                    # 热：本地供热 = 热负荷 - 热源购入 + 弃热
                    heat_src_val = complementary_results["heat source"][k]
                    heat_overflow = complementary_results["heat overflow"][k]
                    gen_h = heat_load[k] - heat_src_val + heat_overflow

                    # 冷：本地供冷 = 冷负荷 - 冷源购入 + 弃冷
                    cool_src_val = complementary_results["cool source"][k]
                    cool_overflow = complementary_results["cool overflow"][k]
                    gen_c = cool_load[k] - cool_src_val + cool_overflow

                    gen_ele_list[start_index + k] = gen_e
                    gen_heat_list[start_index + k] = gen_h
                    gen_cool_list[start_index + k] = gen_c
                    load_ele_list[start_index + k] = ele_load[k]
                    load_heat_list[start_index + k] = heat_load[k]
                    load_cool_list[start_index + k] = cool_load[k]

                    # SSR累积：只累积购入量（正值表示购入）
                    total_grid_purchase += max(0, grid_val)  # 购电为正
                    total_heat_source += max(0, heat_src_val)  # 购热为正
                    total_cool_source += max(0, cool_src_val)  # 购冷为正
                    total_ele_load += ele_load[k]
                    total_heat_load += heat_load[k]
                    total_cool_load += cool_load[k]

    # 计算目标函数值
    if is_success:
        # =============== 目标1：经济性（年化总成本） ===============
        # 使用配置中的年化投资系数
        coeff = config["invest_coeff"]
        storage_fixed = config.get("storage_fixed_cost", 520)
        cap_charge = config.get("capacity_charge", 114.29)
        vars_list = [ppv, pwt, pgt, php, pec, pac, pes, phs, pcs]

        economic_obj = sum(c * v for c, v in zip(coeff, vars_list))
        economic_obj += storage_fixed * (phs > 0.1)  # 热储能固定成本
        economic_obj += storage_fixed * (pcs > 0.1)  # 冷储能固定成本
        economic_obj += cap_charge * max_grid_power   # 容量费
        economic_obj += oc  # 运行成本

        # 卡诺电池投资成本（可选）
        if config.get("enable_carnot_battery", False) and cb_power > 0:
            economic_obj += config.get("cb_invest_power", 10.0) * cb_power
            economic_obj += config.get("cb_invest_capacity", 2.0) * cb_capacity

        # =============== 目标2：源荷匹配度 ===============
        if method == "euclidean":
            # 方案C：三维能质耦合欧氏距离（越小越好）
            # 除以8760归一化为"平均每小时不匹配功率"，单位：kW
            # 这样与师兄的标准差方法（单位也是kW）在数量级上对齐
            matching_obj = euclidean_sum / 8760

        elif method == "std":
            # 方案B：净负荷标准差之和（越小越好）
            # 与师兄原始代码完全一致
            matching_obj = (
                np.std(net_ele_load) + np.std(net_heat_load) + np.std(net_cool_load)
            )

        elif method == "pearson":
            # 方案D：皮尔逊相关系数法（最大化相关性 → 最小化 1-ρ）
            # 缺陷：只看趋势不看大小，可能导致配置容量过小
            gen_e_arr = np.array(gen_ele_list)
            gen_h_arr = np.array(gen_heat_list)
            gen_c_arr = np.array(gen_cool_list)
            load_e_arr = np.array(load_ele_list)
            load_h_arr = np.array(load_heat_list)
            load_c_arr = np.array(load_cool_list)

            # 计算三维皮尔逊相关系数（避免除零）
            def safe_corrcoef(x, y):
                if np.std(x) < 1e-6 or np.std(y) < 1e-6:
                    return 0.0  # 无波动时返回0
                return np.corrcoef(x, y)[0, 1]

            rho_e = safe_corrcoef(gen_e_arr, load_e_arr)
            rho_h = safe_corrcoef(gen_h_arr, load_h_arr)
            rho_c = safe_corrcoef(gen_c_arr, load_c_arr)

            # 转换为最小化目标：1 - 平均相关系数（越小越好）
            # 乘以1000使数量级与其他方法对齐
            avg_rho = (rho_e + rho_h + rho_c) / 3
            matching_obj = (1 - avg_rho) * 1000

        elif method == "ssr":
            # 方案E：供需重叠度/自给自足率法（最大化SSR → 最小化 1-SSR）
            # 缺陷：只看总量不看能质，认为1kWh缺电=1kWh缺热
            total_external = total_grid_purchase + total_heat_source + total_cool_source
            total_load = total_ele_load + total_heat_load + total_cool_load

            if total_load > 1e-6:
                ssr = 1 - total_external / total_load
            else:
                ssr = 1.0

            # 转换为最小化目标：1 - SSR（越小越好）
            # 乘以1000使数量级与其他方法对齐
            matching_obj = (1 - ssr) * 1000

        else:  # economic_only
            # 方案A：单目标，匹配度设为0
            matching_obj = 0

        # 检查 NaN
        if np.isnan(matching_obj) or np.isnan(economic_obj):
            matching_obj = 1e10
            economic_obj = 1e10
            if should_print:
                print(f"  > 警告: 方案 {i + 1} 计算结果为 NaN")

    else:
        economic_obj = 1e10
        matching_obj = 1e10

    if should_print:
        print(
            f"  > 方案 {i + 1} | 成本: {economic_obj:,.2f}{currency} | "
            f"匹配度: {matching_obj:.2f} | 最大需量: {max_grid_power:.1f}kW"
        )
        cb_str = f", CB_P={cb_power:.0f}, CB_C={cb_capacity:.0f}" if cb_power > 0 else ""
        print(
            f"    配置: PV={ppv:.0f}, WT={pwt:.0f}, GT={pgt:.0f}, "
            f"HP={php:.0f}, EC={pec:.0f}, AC={pac:.0f}, "
            f"ES={pes:.0f}, HS={phs:.0f}, CS={pcs:.0f}{cb_str}"
        )

    return [economic_obj, matching_obj]
