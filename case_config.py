# -*- coding: utf-8 -*-
"""
案例配置系统
============
将所有案例相关的硬编码参数提取为配置字典，支持德国案例和松山湖案例切换。
"""

import copy
import os as _os


def _carnot_lambda(T0, T_heat, T_cool):
    """
    基于卡诺㶲系数计算能质系数

    依据热力学第二定律（Bejan, Advanced Engineering Thermodynamics, 2016）：
    - 电能㶲系数 = 1.0（纯㶲，基准值）
    - 热能㶲系数 = 1 - T0/T_heat（卡诺供热效率）
    - 冷能㶲系数 = T0/T_cool - 1（卡诺制冷系数）

    物理意义：λ 不是"权重"，而是"单位转换系数"——
    将 kW 的能量偏差转换为 kW 的㶲偏差，使不同品位的能流在㶲空间中可比。
    """
    lambda_e = 1.0
    lambda_h = 1.0 - T0 / T_heat
    lambda_c = T0 / T_cool - 1.0
    return lambda_e, lambda_h, lambda_c

# 项目根目录（case_config.py 所在目录）
_BASE = _os.path.dirname(_os.path.abspath(__file__))


def _build_dongguan_tou_price():
    """
    构建东莞分时电价（科研用电）

    基于南方电网代理购电工商业用户价格：
    - 尖峰: 1.75 元/kWh (14:00-15:00)  — 松山湖科研电价不适用尖峰
    - 高峰: 1.41 元/kWh (10:00-12:00, 14:00-19:00)
    - 平时: 0.84 元/kWh (8:00-10:00, 12:00-14:00, 19:00-22:00)
    - 低谷: 0.34 元/kWh (0:00-8:00, 22:00-24:00)

    但松山湖社区为科研用电，统一电价 0.6746 元/kWh。
    这里使用统一电价作为基础，蓄冷部分另行处理。
    """
    # 科研用电统一电价
    return [0.6746] * 24


def _build_dongguan_tou_price_industrial():
    """
    构建东莞工商业分时电价（用于蓄冷电价场景）

    峰平谷时段划分（夏季）：
    - 高峰: 10:00-12:00, 14:00-19:00
    - 平时: 8:00-10:00, 12:00-14:00, 19:00-22:00
    - 低谷: 0:00-8:00, 22:00-24:00
    """
    price = [0.0] * 24
    for h in range(24):
        if 0 <= h < 8 or 22 <= h < 24:
            price[h] = 0.34   # 低谷
        elif (10 <= h < 12) or (14 <= h < 19):
            price[h] = 1.41   # 高峰
        else:
            price[h] = 0.84   # 平时
    return price


# ============================================================
# 德国案例配置（与现有代码完全一致的默认值）
# ============================================================
GERMAN_CASE = {
    "name": "german",
    "description": "德国案例 — 热主导型综合能源系统",
    "currency": "€",
    "data_file": _os.path.join(_BASE, "data", "mergedData.csv"),
    "typical_day_file": _os.path.join(_BASE, "data", "typicalDayData.xlsx"),

    # ---- 能源价格 ----
    "ele_price": [0.0025] * 24,       # €/kWh 基础电度电价
    "gas_price": [0.0286] * 24,       # €/kWh 天然气价格
    "capacity_charge": 114.29,         # €/(kW·a) 容量电费

    # ---- 决策变量上界 [ppv, pwt, pgt, php, pec, pac, pes, phs, pcs] ----
    "var_ub": [10000, 10000, 10000, 3000, 1000, 1000, 20000, 6000, 2000],

    # ---- 年化投资系数（与现有代码 cchp_gaproblem.py 完全一致）----
    "invest_coeff": [
        76.44188371,   # ppv: 光伏
        110.4233218,   # pwt: 风电
        50.32074101,   # pgt: 燃气轮机CHP
        21.21527903,   # php: 电热泵
        22.85563566,   # pec: 电制冷
        21.81674313,   # pac: 吸收式制冷
        35.11456751,   # pes: 电储能
        1.689590459,   # phs: 热储能
        1.689590459,   # pcs: 冷储能
    ],
    "storage_fixed_cost": 520,  # 热/冷储能固定成本

    # ---- 设备效率参数 ----
    "gt_eta_e": 0.33,    # 燃气轮机发电效率
    "gt_eta_h": 0.50,    # 燃气轮机供热效率
    "ac_cop": 0.75,      # 吸收式制冷COP
    "ac_heat_ratio": 0.983,  # 吸收式制冷热输入比
    "ac_ele_ratio": 0.017,   # 吸收式制冷电输入比
    "ehp_cop": 4.44,     # 电热泵COP
    "ec_cop": 2.87,      # 电制冷COP
    "es_charge_eff": 0.95,    # 电储能充电效率
    "es_discharge_eff": 0.90, # 电储能放电效率
    "es_loss_rate": 0.000125, # 电储能自放电率
    "hs_cs_charge_eff": 0.90, # 热/冷储能充放效率
    "hs_cs_discharge_eff": 0.90,
    "hs_cs_loss_rate": 0.001, # 热/冷储能损失率

    # ---- 热力学参数 ----
    "T0": 298.15,        # 环境温度 K (25°C)
    "T_heat": 343.15,    # 供热温度 K (70°C)
    "T_cool": 280.15,    # 供冷温度 K (7°C)
    # 能质系数由卡诺㶲公式自动计算（见下方 _apply_carnot_lambda）

    # ---- 卡诺电池（默认关闭；见 docs/辩论确认/carnot_battery_parameters_consensus.md）----
    "enable_carnot_battery": False,
    "cb_power_ub": 2000,       # kW 功率上界
    "cb_capacity_ub": 10000,   # kWh 容量上界
    # E/P 时长约束（4h ≤ capacity/power ≤ 8h）在 cchp_gaproblem.py 中实施
    "cb_rte": 0.60,            # 往返效率（0.45/0.60/0.65 三档敏感性）
    "cb_loss_rate": 0.002,     # 热损失率 /h（低中温TI-CB基准，从旧值0.005下调）
    # 默认成本参数 = reference-literature 情景（Frate 2020 / Zhao 2022 锚定）
    "cb_invest_power": 37.0,    # €/(kW·a)
    "cb_invest_capacity": 2.5,  # €/(kWh·a)
    # 三情景成本表（通过 apply_carnot_scenario(config, "optimistic") 切换）
    "cb_cost_scenarios": {
        "reference":    {"cb_invest_power": 37.0, "cb_invest_capacity": 2.5},
        "optimistic":   {"cb_invest_power": 13.0, "cb_invest_capacity": 2.0},
        "intermediate": {"cb_invest_power": 22.0, "cb_invest_capacity": 3.0},
    },
    "cb_active_scenario": "reference",
}


# ============================================================
# 松山湖案例配置
# ============================================================
SONGSHAN_LAKE_CASE = {
    "name": "songshan_lake",
    "description": "松山湖案例 — 冷主导型分布式综合能源系统（东莞）",
    "currency": "¥",
    "data_file": _os.path.join(_BASE, "data", "songshan_lake_data.csv"),
    "typical_day_file": _os.path.join(_BASE, "data", "songshan_lake_typical.xlsx"),

    # ---- 能源价格 ----
    "ele_price": _build_dongguan_tou_price(),  # 科研统一电价
    "gas_price": [0.45] * 24,   # 4.5元/Nm³ ÷ ~10kWh/Nm³ ≈ 0.45 元/kWh
    "capacity_charge": 0,        # 科研电价无容量费

    # ---- 决策变量上界 [ppv, pwt, pgt, php, pec, pac, pes, phs, pcs] ----
    # 松山湖规模较小，冷负荷主导（峰值5797kW）
    # pwt=0: 东莞城区风资源差，不配风电
    # pec需要足够大以覆盖冷负荷峰值（EC+AC+CS需≥5797kW）
    "var_ub": [1000, 0, 800, 300, 5000, 1500, 2000, 500, 3000],

    # ---- 年化投资系数（¥/(kW·a)，中国市场价格）----
    # 基于松山湖PDF设备投资预算 + 20年寿命 + 8%折现率
    "invest_coeff": [
        520.0,    # ppv: 光伏 (~4000¥/kW, 25年, CRF=0.13)
        0.0,      # pwt: 风电（不配置）
        380.0,    # pgt: 燃气内燃机CHP (~4500¥/kW, 15年)
        165.0,    # php: 电热泵 (~1200¥/kW, 15年)
        175.0,    # pec: 电制冷 (~1300¥/kW, 15年)
        170.0,    # pac: 吸收式制冷 (~1800¥/kW, 20年)
        280.0,    # pes: 电储能 (~2000¥/kWh, 10年)
        15.0,     # phs: 热储能 (~200¥/kWh, 20年)
        15.0,     # pcs: 冷储能/蓄冷 (~200¥/kWh, 20年)
    ],
    "storage_fixed_cost": 3600,  # 储能固定成本 ¥

    # ---- 设备效率参数（基于松山湖PDF设备选型）----
    "gt_eta_e": 0.35,    # CAT G3512E 发电效率
    "gt_eta_h": 0.45,    # CAT G3512E 余热回收效率
    "ac_cop": 0.70,      # 烟气热水型溴化锂机组
    "ac_heat_ratio": 0.983,
    "ac_ele_ratio": 0.017,
    "ehp_cop": 4.0,      # 电热泵COP（亚热带气候）
    "ec_cop": 3.5,       # 电制冷COP（高效离心机组）
    "es_charge_eff": 0.95,
    "es_discharge_eff": 0.90,
    "es_loss_rate": 0.000125,
    "hs_cs_charge_eff": 0.90,
    "hs_cs_discharge_eff": 0.90,
    "hs_cs_loss_rate": 0.001,

    # ---- 热力学参数（亚热带气候）----
    "T0": 300.15,        # 环境温度 K (27°C, 东莞年均温)
    "T_heat": 333.15,    # 供热温度 K (60°C, 生活热水)
    "T_cool": 280.15,    # 供冷温度 K (7°C)
    # 能质系数由卡诺㶲公式自动计算（见下方 _apply_carnot_lambda）

    # ---- 卡诺电池（默认关闭，可通过 --carnot 开启）----
    "enable_carnot_battery": False,
    "cb_power_ub": 500,        # kW
    "cb_capacity_ub": 3000,    # kWh
    # E/P 时长约束（4h ≤ capacity/power ≤ 8h）在 cchp_gaproblem.py 中实施
    "cb_rte": 0.60,            # 往返效率（0.45/0.60/0.65 三档敏感性）
    "cb_loss_rate": 0.002,     # 热损失率 /h（低中温TI-CB基准）
    # 默认成本参数 = reference-literature 情景（换算 1 € ≈ 7.5 ¥）
    "cb_invest_power": 278.0,  # ¥/(kW·a)
    "cb_invest_capacity": 18.0,# ¥/(kWh·a)
    "cb_cost_scenarios": {
        "reference":    {"cb_invest_power": 278.0, "cb_invest_capacity": 18.0},
        "optimistic":   {"cb_invest_power": 100.0, "cb_invest_capacity": 15.0},
        "intermediate": {"cb_invest_power": 170.0, "cb_invest_capacity": 22.0},
    },
    "cb_active_scenario": "reference",
}


# ============================================================
# 工具函数
# ============================================================

def _apply_carnot_lambda(config):
    """根据温度参数自动计算并注入卡诺㶲能质系数"""
    T0 = config["T0"]
    T_heat = config["T_heat"]
    T_cool = config["T_cool"]
    le, lh, lc = _carnot_lambda(T0, T_heat, T_cool)
    config["lambda_e"] = le
    config["lambda_h"] = lh
    config["lambda_c"] = lc
    return config


def get_case(name="german"):
    """
    获取案例配置的深拷贝（能质系数由卡诺公式自动计算）

    Parameters
    ----------
    name : str
        "german" 或 "songshan_lake"

    Returns
    -------
    dict
    """
    cases = {
        "german": GERMAN_CASE,
        "songshan_lake": SONGSHAN_LAKE_CASE,
    }
    if name not in cases:
        raise ValueError(f"未知案例: {name}，可选: {list(cases.keys())}")
    config = copy.deepcopy(cases[name])
    _apply_carnot_lambda(config)
    return config


def enable_carnot_battery(config):
    """在配置中启用卡诺电池"""
    config["enable_carnot_battery"] = True
    return config


def apply_carnot_scenario(config, scenario="reference"):
    """
    按情景覆盖卡诺电池投资成本参数

    Parameters
    ----------
    config : dict
        案例配置（深拷贝后的）
    scenario : str
        "reference" | "optimistic" | "intermediate"
        依据 docs/辩论确认/carnot_battery_parameters_consensus.md

    Returns
    -------
    dict
        原 config 对象（原地修改并返回，便于链式调用）
    """
    scenarios = config.get("cb_cost_scenarios")
    if not scenarios:
        return config
    if scenario not in scenarios:
        raise ValueError(
            f"未知的卡诺电池成本情景: {scenario}，可选: {list(scenarios.keys())}"
        )
    params = scenarios[scenario]
    config["cb_invest_power"] = params["cb_invest_power"]
    config["cb_invest_capacity"] = params["cb_invest_capacity"]
    config["cb_active_scenario"] = scenario
    return config


def list_cases():
    """列出所有可用案例"""
    for name, cfg in [("german", GERMAN_CASE), ("songshan_lake", SONGSHAN_LAKE_CASE)]:
        print(f"  {name:20s}  {cfg['description']}")
