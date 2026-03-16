# -*- coding: utf-8 -*-
"""
OEMOF 框架中的卡诺电池集成代码片段

本文件展示如何在现有 operation.py 中集成卡诺电池
只需在相应位置粘贴代码即可
"""

# ============================================================================
# 片段1：在OperationModel.__init__() 开头添加导入
# ============================================================================

# 在 operation.py 的导入部分添加
from carnot_battery_module import (
    CarnotBatteryParameters,
    CarnotBatteryUnit,
    CarnotBatteryOperationStrategy
)

# ============================================================================
# 片段2：在OperationModel.__init__() 中添加卡诺电池参数
# ============================================================================

"""
在 def __init__() 函数的参数列表中添加：

    pcb_power: float = 0,           # 卡诺电池功率容量 (kW)
    pcb_capacity: float = 0,        # 卡诺电池能量容量 (kWh)
    cb_type: str = "rankine",       # 卡诺电池类型 ('brayton'/'rankine'/'azelio')
"""

# 在 OperationModel.__init__() 的早期添加以下代码：

# ========== 卡诺电池初始化 ==========
self.pcb_power = pcb_power
self.pcb_capacity = pcb_capacity

# 只有当卡诺电池容量不为0时才创建
if self.pcb_capacity > 0 and self.pcb_power > 0:
    # 创建卡诺电池参数对象
    cb_params = CarnotBatteryParameters(technology_type=cb_type)
    
    # 创建卡诺电池单元
    self.carnot_battery = CarnotBatteryUnit(
        unit_id=1,
        nominal_power_kw=pcb_power,
        capacity_kwh=pcb_capacity,
        params=cb_params
    )
    
    # 创建卡诺电池运行策略管理器
    self.cb_strategy = CarnotBatteryOperationStrategy(self.carnot_battery)
    
    print(f"[能源系统] 卡诺电池已初始化:")
    print(f"  类型: {cb_params.name}")
    print(f"  功率: {pcb_power} kW")
    print(f"  容量: {pcb_capacity} kWh")
    print(f"  往返效率: {cb_params.round_trip_efficiency*100:.1f}%")
else:
    self.carnot_battery = None
    self.cb_strategy = None


# ============================================================================
# 片段3：在能源系统中添加卡诺电池母线和转换器
# ============================================================================

"""
在创建其他母线（ele_bus, heat_bus等）后，添加以下代码：
"""

# ========== 如果需要卡诺电池，创建其母线和转换器 ==========
if self.pcb_capacity > 0:
    # 创建卡诺电池储能母线
    cb_bus = solph.Bus(label="carnot_battery bus")
    self.energy_system.add(cb_bus)
    
    # 卡诺电池充电器 (电能 -> 热能)
    # 模式：当电价低/可再生能源富余时，将电能转换为热能储存
    cb_charger = Transformer(
        label="carnot_charger",
        inputs={
            ele_bus: solph.Flow()
        },
        outputs={
            cb_bus: solph.Flow(
                nominal_value=self.pcb_power,
                variable_costs=0  # 充电不额外计费
            )
        },
        conversion_factors={
            cb_bus: self.carnot_battery.params.charger_efficiency
        }
    )
    
    # 卡诺电池放电器 (热能 -> 电能)
    # 模式：当电价高/负荷缺电时，将热能转换为电能释放
    cb_discharger = Transformer(
        label="carnot_discharger",
        inputs={
            cb_bus: solph.Flow()
        },
        outputs={
            ele_bus: solph.Flow(
                nominal_value=self.pcb_power,
                variable_costs=0  # 放电不额外计费
            )
        },
        conversion_factors={
            ele_bus: self.carnot_battery.params.discharger_efficiency
        }
    )
    
    # 卡诺电池热能储存器
    # 储存容量: pcb_capacity kWh
    # 损耗率: parasitic_loss_rate (通常 0.1% ~ 0.2% 每小时)
    cb_storage = GenericStorage(
        label="carnot_thermal_storage",
        nominal_storage_capacity=self.pcb_capacity,
        inputs={
            cb_bus: solph.Flow(nominal_value=self.pcb_power)
        },
        outputs={
            cb_bus: solph.Flow(nominal_value=self.pcb_power)
        },
        loss_rate=self.carnot_battery.params.parasitic_loss_rate,
        initial_storage_level=None,  # 让优化器决定初始SOC
        inflow_conversion_factor=1.0,  # 入库效率100%（损耗已在充电器中计算）
        outflow_conversion_factor=1.0  # 出库效率100%（损耗已在放电器中计算）
    )
    
    # 将卡诺电池组件添加到能源系统
    self.energy_system.add(cb_charger, cb_discharger, cb_storage)


# ============================================================================
# 片段4：在运行优化后，提取卡诺电池的运行结果
# ============================================================================

"""
在 def solve() 或数据处理函数中，优化运行后添加：
"""

# ========== 提取卡诺电池的运行结果 ==========
if self.carnot_battery is not None:
    
    # 获取卡诺电池的充放电功率序列
    cb_charger_flow = results[('carnot_charger', 'ele_bus')].sequences.values
    cb_discharger_flow = results[('ele_bus', 'carnot_discharger')].sequences.values
    
    # 卡诺电池的净功率（负数=充电，正数=放电）
    cb_net_power = cb_discharger_flow - cb_charger_flow  # [kW]
    
    # 获取储能器的SOC
    cb_storage_soc = results[('carnot_thermal_storage', 'carnot_battery bus')].sequences.values
    
    # 计算关键指标
    total_charging_energy = np.sum(cb_charger_flow) * self.time_step / 1000  # [MWh]
    total_discharging_energy = np.sum(cb_discharger_flow) * self.time_step / 1000  # [MWh]
    
    if total_charging_energy > 0:
        actual_round_trip_efficiency = total_discharging_energy / total_charging_energy
    else:
        actual_round_trip_efficiency = 0
    
    # 存储运行结果
    self.cb_results = {
        'charging_power': cb_charger_flow,
        'discharging_power': cb_discharger_flow,
        'net_power': cb_net_power,
        'soc': cb_storage_soc,
        'total_charged_energy_mwh': total_charging_energy,
        'total_discharged_energy_mwh': total_discharging_energy,
        'actual_rte': actual_round_trip_efficiency
    }
    
    print(f"\n[卡诺电池运行结果]")
    print(f"  年充电能量: {total_charging_energy:.1f} MWh")
    print(f"  年放电能量: {total_discharging_energy:.1f} MWh")
    print(f"  实际往返效率: {actual_round_trip_efficiency*100:.1f}%")
    print(f"  (与设计值 {self.carnot_battery.params.round_trip_efficiency*100:.1f}% 对比)")


# ============================================================================
# 片段5：在目标函数中计算卡诺电池的成本
# ============================================================================

"""
在 sub_aim_func_cchp() 中，计算经济目标时添加：
"""

# ========== 卡诺电池的投资和运维成本 ==========
if pcb_capacity > 0 and pcb_power > 0:
    
    # 获取卡诺电池参数
    cb_type_name = ['brayton', 'rankine', 'azelio'][int(cb_type)] \
                    if isinstance(cb_type, (int, float)) else cb_type
    cb_params = CarnotBatteryParameters(technology_type=cb_type_name)
    
    # 计算一次性投资成本 (CAPEX) - 分摊到年度成本
    cb_capex = cb_params.calculate_capex(pcb_power, pcb_capacity)
    cb_capex_annual = cb_capex / cb_params.lifetime  # €/年
    
    # 计算年度运维成本 (OPEX)
    # 从运行结果中获取年能量吞吐量
    if hasattr(om, 'cb_results'):
        annual_energy_throughput = om.cb_results['total_charged_energy_mwh'] * 1000  # [kWh]
    else:
        annual_energy_throughput = pcb_capacity * 200  # 保守估计：200循环/年
    
    cb_opex = cb_params.calculate_opex(annual_energy_throughput, annual_cycling_times=200)
    
    # 总年化成本
    cb_cost_annual = cb_capex_annual + cb_opex
    
    # 添加到经济目标
    oc += cb_cost_annual
    
    if should_print:
        print(f"  卡诺电池CAPEX分摊: {cb_capex_annual:,.0f} €/年")
        print(f"  卡诺电池OPEX: {cb_opex:,.0f} €/年")
        print(f"  卡诺电池总年化成本: {cb_cost_annual:,.0f} €/年")


# ============================================================================
# 片段6：在源荷匹配度计算中考虑卡诺电池
# ============================================================================

"""
在计算匹配度指标时，添加以下逻辑：
"""

# ========== 计算包含卡诺电池的源荷匹配度 ==========
if pcb_capacity > 0:
    
    # 从运行结果中提取卡诺电池的净功率序列
    if hasattr(om, 'cb_results'):
        cb_net_power = om.cb_results['net_power']  # [kW]
    else:
        cb_net_power = np.zeros(len(ele_load))
    
    # 卡诺电池可以减少电力净负荷
    # (当CB放电时，负数抵消正的P_net_e)
    # (当CB充电时，正数抵消负的P_net_e)
    P_net_e_after_cb = P_net_e + cb_net_power  # 修正后的电力净负荷
    
    # 计算能质加权欧氏距离
    # 使用修正后的电力净负荷
    matching_degree = np.sqrt(
        np.sum((LAMBDA_E * P_net_e_after_cb) ** 2) +
        np.sum((LAMBDA_H * P_net_h) ** 2) +
        np.sum((LAMBDA_C * P_net_c) ** 2)
    )
    
    # 如果考虑分时电价权重
    if ele_price is not None:
        omega_e = ele_price / np.mean(ele_price)
        matching_degree = np.sqrt(
            np.sum((omega_e * P_net_e_after_cb) ** 2) +
            np.sum((LAMBDA_H * P_net_h) ** 2) +
            np.sum((LAMBDA_C * P_net_c) ** 2)
        )

else:
    # 原始计算（无卡诺电池）
    matching_degree = np.sqrt(
        np.sum((LAMBDA_E * P_net_e) ** 2) +
        np.sum((LAMBDA_H * P_net_h) ** 2) +
        np.sum((LAMBDA_C * P_net_c) ** 2)
    )


# ============================================================================
# 片段7：完整的集成示例（Mini版operation函数）
# ============================================================================

def operation_with_carnot(pcb_power, pcb_capacity, cb_type, 
                          ele_load, heat_demand, cool_demand,
                          wt_output, pv_output, ele_price):
    """
    简化的综合能源系统运行模型（包含卡诺电池）
    
    Parameters
    ----------
    pcb_power : float
        卡诺电池功率 (kW)
    pcb_capacity : float
        卡诺电池容量 (kWh)
    cb_type : str
        卡诺电池类型
    ele_load : array
        电力负荷 (kW)
    heat_demand : array
        热力需求 (kW)
    cool_demand : array
        冷力需求 (kW)
    wt_output : array
        风电出力 (kW)
    pv_output : array
        光伏出力 (kW)
    ele_price : array
        电价 (€/kWh)
    
    Returns
    -------
    dict
        运行结果和成本指标
    """
    
    time_steps = len(ele_load)
    dt = 1.0  # 1小时时间步长
    
    # 初始化存储变量
    ele_net_balance = np.zeros(time_steps)  # 电力净负荷
    heat_net_balance = np.zeros(time_steps)
    cool_net_balance = np.zeros(time_steps)
    
    cb_charging = np.zeros(time_steps)
    cb_discharging = np.zeros(time_steps)
    cb_soc = np.zeros(time_steps)
    
    operating_cost = 0
    
    # 如果有卡诺电池，初始化
    if pcb_capacity > 0:
        cb_params = CarnotBatteryParameters(cb_type)
        cb_unit = CarnotBatteryUnit(1, pcb_power, pcb_capacity, cb_params)
        cb_strategy = CarnotBatteryOperationStrategy(cb_unit)
    
    # 逐时间步仿真
    for t in range(time_steps):
        
        # 1. 计算能源平衡
        ele_net_balance[t] = ele_load[t] - wt_output[t] - pv_output[t]
        
        # 2. 卡诺电池运行策略
        if pcb_capacity > 0:
            # 简化的套利策略
            price_median = np.median(ele_price)
            
            if ele_price[t] < 0.7 * price_median and cb_unit.soc < 0.8 * cb_capacity:
                # 低价充电
                cb_charge_cmd = min(pcb_power * 0.8, 
                                    (0.8 * pcb_capacity - cb_unit.soc) / dt)
                result = cb_unit.step_charge(cb_charge_cmd, dt_hours=dt)
                cb_charging[t] = result['p_charge_actual']
                ele_net_balance[t] += cb_charging[t]  # 增加用电
                
            elif ele_price[t] > 1.3 * price_median and cb_unit.soc > 0.2 * pcb_capacity:
                # 高价放电
                cb_discharge_cmd = min(pcb_power * 0.8,
                                       (cb_unit.soc - 0.1 * pcb_capacity) / dt)
                result = cb_unit.step_discharge(cb_discharge_cmd, dt_hours=dt)
                cb_discharging[t] = result['p_discharge_actual']
                ele_net_balance[t] -= cb_discharging[t]  # 减少用电
            
            cb_soc[t] = cb_unit.soc
        
        # 3. 计算运行成本
        # 从电网购电成本
        if ele_net_balance[t] > 0:
            operating_cost += ele_net_balance[t] * ele_price[t] * dt  # €
    
    # 卡诺电池的投资成本
    capex_annual = 0
    opex_annual = 0
    if pcb_capacity > 0:
        capex = cb_params.calculate_capex(pcb_power, pcb_capacity)
        capex_annual = capex / cb_params.lifetime
        opex_annual = cb_params.calculate_opex(
            np.sum(cb_charging) * dt,
            annual_cycling_times=200
        )
    
    total_annual_cost = operating_cost + capex_annual + opex_annual
    
    return {
        'ele_net_balance': ele_net_balance,
        'cb_charging': cb_charging,
        'cb_discharging': cb_discharging,
        'cb_soc': cb_soc,
        'operating_cost': operating_cost,
        'capex_annual': capex_annual,
        'opex_annual': opex_annual,
        'total_annual_cost': total_annual_cost
    }

