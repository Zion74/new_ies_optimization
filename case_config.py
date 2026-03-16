# -*- coding: utf-8 -*-
"""
案例配置系统
============
将所有案例相关的硬编码参数提取为配置字典，支持德国案例和松山湖案例切换。
"""

import copy
import os as _os

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
    "T0": 298.15,        # 环境温度 K
    "T_heat": 343.15,    # 供热温度 K (70°C)
    "T_cool": 280.15,    # 供冷温度 K (7°C)
    "lambda_e": 1.0,     # 电能质系数
    "lambda_h": 0.6,     # 热能质系数
    "lambda_c": 0.5,     # 冷能质系数

    # ---- 卡诺电池（默认关闭）----
    "enable_carnot_battery": False,
    "cb_power_ub": 2000,       # kW 功率上界
    "cb_capacity_ub": 10000,   # kWh 容量上界
    "cb_rte": 0.60,            # 往返效率
    "cb_loss_rate": 0.005,     # 热损失率
    "cb_invest_power": 10.0,   # €/(kW·a) 功率年化投资
    "cb_invest_capacity": 2.0, # €/(kWh·a) 容量年化投资
    "cb_heat_recovery_ratio": 0.25,  # 余热回收比例
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
    # 松山湖规模较小，冷负荷主导
    # pwt=0: 东莞城区风资源差，不配风电
    "var_ub": [1000, 0, 800, 300, 2000, 800, 2000, 500, 2000],

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
    "lambda_e": 1.0,
    "lambda_h": 0.6,
    "lambda_c": 0.5,

    # ---- 卡诺电池（默认关闭，可通过 --carnot 开启）----
    "enable_carnot_battery": False,
    "cb_power_ub": 500,        # kW
    "cb_capacity_ub": 3000,    # kWh
    "cb_rte": 0.60,
    "cb_loss_rate": 0.005,
    "cb_invest_power": 72.0,   # ¥/(kW·a) Rankine PTES
    "cb_invest_capacity": 15.0,# ¥/(kWh·a)
    "cb_heat_recovery_ratio": 0.25,
}


# ============================================================
# 工具函数
# ============================================================

def get_case(name="german"):
    """
    获取案例配置的深拷贝

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
    return copy.deepcopy(cases[name])


def enable_carnot_battery(config):
    """在配置中启用卡诺电池"""
    config["enable_carnot_battery"] = True
    return config


def list_cases():
    """列出所有可用案例"""
    for name, cfg in [("german", GERMAN_CASE), ("songshan_lake", SONGSHAN_LAKE_CASE)]:
        print(f"  {name:20s}  {cfg['description']}")
