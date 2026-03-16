
# -*- coding: utf-8 -*-
"""
卡诺电池集成到综合能源系统(CCHP)的建模与优化

包含内容：
1. 卡诺电池技术参数（基于欧洲实际项目数据）
2. Energy Hub模型扩展（加入卡诺电池）
3. 能质系数加权的目标函数
4. 卡诺电池的运行策略

参考资源：
- DLR (2024): Carnot Battery cost 150-200 €/kW, 20-90 €/kWh
- Azelio TES.POD: 13 kW output, 165 kWh capacity (13h duration)
- Round-trip efficiency: 55-75% (Brayton/Rankine cycles)
- Høje Taastrup PTES: 70,000 m³, charging 4-6h, discharging 8-12h
"""

import numpy as np
import pandas as pd

# ============================================================================
# Part 1: 卡诺电池技术参数（欧洲部署数据）
# ============================================================================

class CarnotBatteryParameters:
    """
    卡诺电池参数基于以下欧洲实际项目：

    1. Azelio TES.POD (瑞典商业化产品)
    2. DLR Carnot Battery Studies (德国研究)
    3. Høje Taastrup PTES (丹麦示范项目)
    """

    # ========== 技术类型选择 ==========
    # 1. Brayton PTES (Pumped Thermal Energy Storage)
    #    - 工作流体：氩气或空气
    #    - 工作温度：-70°C ~ 1000°C
    #    - 应用场景：大规模、长时间储能

    # 2. Rankine PTES (有机朗肯循环)
    #    - 工作温度：50°C ~ 300°C
    #    - 应用场景：中等规模、与热系统耦合

    # 3. Azelio型热储能 (相变材料+斯特林引擎)
    #    - 工作温度：600°C
    #    - 应用场景：分布式、与太阳能耦合

    def __init__(self, technology_type="rankine"):
        """
        Parameters
        ----------
        technology_type : str
            'brayton', 'rankine', 或 'azelio'
        """
        self.technology_type = technology_type
        self._set_parameters()

    def _set_parameters(self):
        """根据技术类型设置参数"""

        if self.technology_type == "brayton":
            # Brayton PTES (超高温、高效率)
            # 来源: DLR, RWTH Aachen 研究
            self.name = "Brayton PTES"
            self.round_trip_efficiency = 0.65  # 65% RTE (中值)
            self.power_spec_cost = 150  # €/kW (功率特定成本)
            self.energy_spec_cost = 20   # €/kWh (能量特定成本)
            self.lifetime = 25  # 年
            self.min_charging_time = 2  # 小时
            self.max_charging_time = 8  # 小时
            self.min_discharging_time = 2  # 小时
            self.max_discharging_time = 8  # 小时
            self.min_capacity_ratio = 0.25  # 最小功率/容量比
            self.max_capacity_ratio = 1.0   # 最大功率/容量比
            self.parasitic_loss_rate = 0.001  # 每小时1‰损耗
            self.charger_efficiency = 0.95  # 充电器效率 (电→热)
            self.discharger_efficiency = 0.95  # 放电器效率 (热→电)

        elif self.technology_type == "rankine":
            # Rankine PTES (中温、与热系统集成)
            # 来源: DLR, Azelio 研究
            self.name = "Rankine PTES (Heat Pump + ORC)"
            self.round_trip_efficiency = 0.55  # 55% RTE (保守估计)
            self.power_spec_cost = 120  # €/kW
            self.energy_spec_cost = 25   # €/kWh
            self.lifetime = 25  # 年
            self.min_charging_time = 2  # 小时
            self.max_charging_time = 6  # 小时
            self.min_discharging_time = 3  # 小时
            self.max_discharging_time = 12  # 小时 (长时间放电)
            self.min_capacity_ratio = 0.2  # 更灵活的功率/容量比
            self.max_capacity_ratio = 0.5   # 
            self.parasitic_loss_rate = 0.002  # 2‰损耗
            self.charger_efficiency = 0.92  # 热泵充电
            self.discharger_efficiency = 0.93  # ORC放电

        elif self.technology_type == "azelio":
            # Azelio TES.POD (分布式、商业产品)
            # 来源: Azelio 官方数据
            self.name = "Azelio TES.POD (PCM + Stirling)"
            self.round_trip_efficiency = 0.70  # 70% RTE (较高)
            self.power_spec_cost = 350  # €/kW (分布式更贵)
            self.energy_spec_cost = 45   # €/kWh
            self.lifetime = 30  # 年 (30年寿命)
            self.min_charging_time = 4  # 小时
            self.max_charging_time = 6  # 小时
            self.min_discharging_time = 6  # 小时
            self.max_discharging_time = 13  # 小时 (13小时容量)
            self.min_capacity_ratio = 0.078  # 13kW / 165kWh ≈ 0.078
            self.max_capacity_ratio = 0.15   # 允许过载放电
            self.parasitic_loss_rate = 0.0005  # 低损耗
            self.charger_efficiency = 0.98  # 电阻加热，高效
            self.discharger_efficiency = 0.92  # Stirling发动机

        else:
            raise ValueError(f"未知的技术类型: {self.technology_type}")

    def calculate_capex(self, power_kw, capacity_kwh):
        """
        计算卡诺电池的总投资成本 (CAPEX)

        Parameters
        ----------
        power_kw : float
            功率容量 (kW)
        capacity_kwh : float
            能量容量 (kWh)

        Returns
        -------
        float
            总成本 (€)
        """
        power_cost = self.power_spec_cost * power_kw
        energy_cost = self.energy_spec_cost * capacity_kwh
        return power_cost + energy_cost

    def calculate_opex(self, annual_energy_throughput_kwh, annual_cycling_times=300):
        """
        计算年运维成本 (OPEX)

        Parameters
        ----------
        annual_energy_throughput_kwh : float
            年能量吞吐量 (kWh)
        annual_cycling_times : int
            年循环次数 (次/年)

        Returns
        -------
        float
            年运维成本 (€/年)
        """
        # 简化模型：O&M成本为CAPEX的1-2%/年
        om_rate = 0.01  # 1%/年
        capex_total = self.calculate_capex(1, 1)  # 单位成本
        return om_rate * capex_total

    def get_levelized_cost_of_storage(self, power_kw, capacity_kwh, 
                                       discount_rate=0.08, annual_cycles=300):
        """
        计算储能成本均化值 (LCOS)

        Parameters
        ----------
        power_kw : float
            功率
        capacity_kwh : float
            容量
        discount_rate : float
            折现率 (8% = 0.08)
        annual_cycles : int
            年循环次数

        Returns
        -------
        dict
            包含LCOS和关键参数的字典
        """
        capex = self.calculate_capex(power_kw, capacity_kwh)

        # 计算净现值（NPV）
        total_pv = capex
        for year in range(1, self.lifetime + 1):
            annual_opex = self.calculate_opex(capacity_kwh * annual_cycles)
            pv_factor = 1 / (1 + discount_rate) ** year
            total_pv += annual_opex * pv_factor

        # 计算年平均能量吞吐量
        total_energy = capacity_kwh * annual_cycles * self.lifetime

        # LCOS = 总NPV / 总能量
        lcos_per_kwh = total_pv / total_energy

        return {
            "lcos": lcos_per_kwh,
            "capex": capex,
            "capex_per_kw": self.power_spec_cost,
            "capex_per_kwh": self.energy_spec_cost,
            "lifetime_years": self.lifetime,
            "total_pv": total_pv
        }


# ============================================================================
# Part 2: Energy Hub 模型扩展（加入卡诺电池）
# ============================================================================

class CarnotBatteryUnit:
    """
    卡诺电池运行单元

    物理模型：
    - 充电过程（Power to Heat）：电能 → 热能储存
      Q_hot = η_charge * P_input * Δt

    - 放电过程（Heat to Power）：热能 → 电能释放
      P_output = η_discharge * Q_hot / Δt

    - 往返效率（RTE）：η_rte = η_charge * η_discharge
    """

    def __init__(self, unit_id, nominal_power_kw, capacity_kwh, params):
        """
        Parameters
        ----------
        unit_id : int
            单元编号
        nominal_power_kw : float
            额定功率 (kW)
        capacity_kwh : float
            储能容量 (kWh)
        params : CarnotBatteryParameters
            参数对象
        """
        self.unit_id = unit_id
        self.nominal_power = nominal_power_kw
        self.capacity = capacity_kwh
        self.params = params

        # 状态变量
        self.soc = 0.5 * self.capacity  # 初始荷电状态 (SOC) = 50%
        self.soc_min = 0.1 * self.capacity  # 最小SOC = 10%
        self.soc_max = 0.95 * self.capacity  # 最大SOC = 95%

        # 历史记录
        self.history = {
            'power_charge': [],  # 充电功率
            'power_discharge': [],  # 放电功率
            'soc': [self.soc],
            'thermal_loss': []
        }

    def step_charge(self, p_charge_kw, dt_hours=1.0):
        """
        单时间步的充电过程

        Parameters
        ----------
        p_charge_kw : float
            充电功率 (kW)
        dt_hours : float
            时间步长 (小时)

        Returns
        -------
        dict
            包含能量流、SOC更新等信息
        """
        # 限制充电功率不超过额定功率
        p_charge_limited = min(p_charge_kw, self.nominal_power)

        # 计算本步充入的电能
        e_charge_kwh = p_charge_limited * dt_hours

        # 应用充电器效率
        e_stored_kwh = e_charge_kwh * self.params.charger_efficiency

        # 计算热损失
        q_loss_kwh = e_charge_kwh * (1 - self.params.charger_efficiency)

        # 检查SOC约束
        new_soc = self.soc + e_stored_kwh
        if new_soc > self.soc_max:
            e_stored_kwh = self.soc_max - self.soc
            p_charge_limited = e_stored_kwh / (self.params.charger_efficiency * dt_hours)

        self.soc += e_stored_kwh

        # 记录
        self.history['power_charge'].append(p_charge_limited)
        self.history['power_discharge'].append(0)
        self.history['soc'].append(self.soc)
        self.history['thermal_loss'].append(q_loss_kwh)

        return {
            'p_charge_actual': p_charge_limited,
            'e_stored': e_stored_kwh,
            'q_loss': q_loss_kwh,
            'soc_after': self.soc
        }

    def step_discharge(self, p_discharge_kw, dt_hours=1.0):
        """
        单时间步的放电过程

        Parameters
        ----------
        p_discharge_kw : float
            放电功率 (kW)
        dt_hours : float
            时间步长 (小时)

        Returns
        -------
        dict
            包含能量流、SOC更新等信息
        """
        # 限制放电功率不超过额定功率
        p_discharge_limited = min(p_discharge_kw, self.nominal_power)

        # 计算本步释放的电能
        e_discharge_kwh = p_discharge_limited * dt_hours

        # 应用放电器效率
        e_released_kwh = e_discharge_kwh * self.params.discharger_efficiency

        # 计算热损失
        q_loss_kwh = e_discharge_kwh * (1 - self.params.discharger_efficiency)

        # 检查SOC约束
        new_soc = self.soc - e_discharge_kwh
        if new_soc < self.soc_min:
            e_discharge_kwh = self.soc - self.soc_min
            p_discharge_limited = e_discharge_kwh / dt_hours

        self.soc -= e_discharge_kwh

        # 记录
        self.history['power_discharge'].append(p_discharge_limited)
        self.history['power_charge'].append(0)
        self.history['soc'].append(self.soc)
        self.history['thermal_loss'].append(q_loss_kwh)

        return {
            'p_discharge_actual': p_discharge_limited,
            'e_released': e_released_kwh,
            'q_loss': q_loss_kwh,
            'soc_after': self.soc
        }

    def get_soc_penalty(self):
        """
        计算SOC偏离目标值的惩罚
        用于优化中的约束条件
        """
        target_soc = 0.5 * self.capacity
        penalty = abs(self.soc - target_soc) / self.capacity
        return penalty


# ============================================================================
# Part 3: 与CCHP集成的目标函数
# ============================================================================

def calculate_exergy_weighted_matching_degree_with_carnot(
    power_net_e, power_net_h, power_net_c, power_cb,
    lambda_e=1.0, lambda_h=0.13, lambda_c=0.064,
    electricity_price=None
):
    """
    计算包含卡诺电池的能质加权欧氏距离源荷匹配度

    Parameters
    ----------
    power_net_e : array
        电力净负荷 (kW)
    power_net_h : array
        热力净负荷 (kW)
    power_net_c : array
        冷力净负荷 (kW)
    power_cb : array
        卡诺电池功率 (负数=充电, 正数=放电) (kW)
    lambda_e, lambda_h, lambda_c : float
        能质系数
    electricity_price : array, optional
        分时电价 (€/kWh)

    Returns
    -------
    float
        源荷匹配度值
    """
    # 如果提供电价，用电价权重调整电能系数
    if electricity_price is not None:
        price_avg = np.mean(electricity_price)
        omega_e = electricity_price / price_avg  # 时变权重
    else:
        omega_e = np.ones_like(power_net_e) * lambda_e

    # 卡诺电池的接入相当于减少电网交互
    # (充电时吸收多余电能，放电时补充不足电能)
    power_net_e_after_cb = power_net_e + power_cb

    # 计算三维欧氏距离
    matching_degree = np.sqrt(
        np.sum((omega_e * power_net_e_after_cb) ** 2) +
        np.sum((lambda_h * power_net_h) ** 2) +
        np.sum((lambda_c * power_net_c) ** 2)
    )

    return matching_degree


# ============================================================================
# Part 4: 卡诺电池的运行策略 (Operation Strategy)
# ============================================================================

class CarnotBatteryOperationStrategy:
    """
    卡诺电池的运行策略

    策略1: 套利模式 (Arbitrage)
    - 在电价低谷时充电
    - 在电价高峰时放电

    策略2: 削峰填谷 (Peak Shaving)
    - 平抑电力净负荷的波动

    策略3: 可再生能源消纳 (RES Accommodation)
    - 在可再生能源富余时充电
    - 在可再生能源不足时放电

    策略4: 能质梯级利用 (Exergy Cascade)
    - 优先满足高品位电能的平衡
    - 利用卡诺电池的灵活性支撑电网
    """

    def __init__(self, cb_unit):
        """
        Parameters
        ----------
        cb_unit : CarnotBatteryUnit
            卡诺电池单元
        """
        self.cb = cb_unit

    def arbitrage_strategy(self, power_net_e, electricity_price, dt=1.0):
        """
        套利策略：低价充电，高价放电

        Parameters
        ----------
        power_net_e : array
            电力净负荷时间序列
        electricity_price : array
            电价时间序列
        dt : float
            时间步长 (小时)

        Returns
        -------
        array
            推荐的卡诺电池功率指令 (negative=charge, positive=discharge)
        """
        cb_power = np.zeros_like(power_net_e)
        price_percentile_low = np.percentile(electricity_price, 33)  # 低价区间
        price_percentile_high = np.percentile(electricity_price, 67)  # 高价区间

        for t in range(len(power_net_e)):
            if electricity_price[t] < price_percentile_low and self.cb.soc < 0.8 * self.cb.capacity:
                # 低价时段：充电
                cb_power[t] = -min(self.cb.nominal_power, 0.5 * self.cb.nominal_power)

            elif electricity_price[t] > price_percentile_high and self.cb.soc > 0.3 * self.cb.capacity:
                # 高价时段：放电
                cb_power[t] = min(self.cb.nominal_power, 0.8 * self.cb.nominal_power)

            # 执行操作
            if cb_power[t] < 0:  # 充电
                self.cb.step_charge(-cb_power[t], dt_hours=dt)
            else:  # 放电
                self.cb.step_discharge(cb_power[t], dt_hours=dt)

        return cb_power

    def peak_shaving_strategy(self, power_net_e, dt=1.0):
        """
        削峰填谷策略：平抑电力波动

        Parameters
        ----------
        power_net_e : array
            电力净负荷时间序列
        dt : float
            时间步长 (小时)

        Returns
        -------
        array
            推荐的卡诺电池功率指令
        """
        cb_power = np.zeros_like(power_net_e)
        e_net_mean = np.mean(power_net_e)
        e_net_std = np.std(power_net_e)

        for t in range(len(power_net_e)):
            # 标准化偏差
            normalized_deviation = (power_net_e[t] - e_net_mean) / e_net_std if e_net_std > 0 else 0

            if normalized_deviation > 0.5 and self.cb.soc > 0.2 * self.cb.capacity:
                # 负荷高峰：放电
                cb_power[t] = normalized_deviation * self.cb.nominal_power * 0.5

            elif normalized_deviation < -0.5 and self.cb.soc < 0.8 * self.cb.capacity:
                # 负荷低谷：充电
                cb_power[t] = -(-normalized_deviation) * self.cb.nominal_power * 0.5

            # 执行操作
            if cb_power[t] < 0:
                self.cb.step_charge(-cb_power[t], dt_hours=dt)
            else:
                self.cb.step_discharge(cb_power[t], dt_hours=dt)

        return cb_power

    def hybrid_strategy(self, power_net_e, electricity_price, pv_output, dt=1.0):
        """
        混合策略：结合套利、削峰、可再生能源消纳

        优先级：
        1. 消纳可再生能源（避免弃光弃风）
        2. 进行价格套利
        3. 削峰填谷

        Parameters
        ----------
        power_net_e : array
            电力净负荷
        electricity_price : array
            电价
        pv_output : array
            光伏出力
        dt : float
            时间步长

        Returns
        -------
        array
            推荐的卡诺电池功率指令
        """
        cb_power = np.zeros_like(power_net_e)
        price_median = np.median(electricity_price)

        for t in range(len(power_net_e)):
            # 优先级1：消纳可再生能源
            if pv_output[t] > 100 and self.cb.soc < 0.9 * self.cb.capacity:
                # PV富余，充电
                cb_power[t] = -min(pv_output[t] * 0.3, self.cb.nominal_power)

            # 优先级2：价格套利
            elif electricity_price[t] < price_median * 0.7 and self.cb.soc < 0.8 * self.cb.capacity:
                cb_power[t] = -0.5 * self.cb.nominal_power

            elif electricity_price[t] > price_median * 1.3 and self.cb.soc > 0.3 * self.cb.capacity:
                cb_power[t] = 0.8 * self.cb.nominal_power

            # 优先级3：削峰填谷
            else:
                e_mean = np.mean(power_net_e)
                if power_net_e[t] > e_mean and self.cb.soc > 0.2 * self.cb.capacity:
                    cb_power[t] = 0.3 * self.cb.nominal_power
                elif power_net_e[t] < e_mean and self.cb.soc < 0.8 * self.cb.capacity:
                    cb_power[t] = -0.3 * self.cb.nominal_power

            # 执行操作
            if cb_power[t] < 0:
                self.cb.step_charge(-cb_power[t], dt_hours=dt)
            else:
                self.cb.step_discharge(cb_power[t], dt_hours=dt)

        return cb_power


# ============================================================================
# 测试与验证
# ============================================================================

if __name__ == "__main__":

    print("=" * 80)
    print("卡诺电池集成到综合能源系统 - 参数与运行策略测试")
    print("=" * 80)

    # 1. 创建三种卡诺电池参数
    print("\n1. 卡诺电池参数对比")
    print("-" * 80)

    params_rankine = CarnotBatteryParameters(technology_type="rankine")
    params_brayton = CarnotBatteryParameters(technology_type="brayton")
    params_azelio = CarnotBatteryParameters(technology_type="azelio")

    tech_list = [
        ("Rankine PTES", params_rankine),
        ("Brayton PTES", params_brayton),
        ("Azelio TES.POD", params_azelio)
    ]

    for tech_name, params in tech_list:
        lcos_info = params.get_levelized_cost_of_storage(
            power_kw=500, 
            capacity_kwh=3000
        )

        print(f"\n{tech_name}:")
        print(f"  往返效率 (RTE):        {params.round_trip_efficiency*100:.1f}%")
        print(f"  功率成本:              {params.power_spec_cost} €/kW")
        print(f"  能量成本:              {params.energy_spec_cost} €/kWh")
        print(f"  总投资成本 (500kW,3MWh): {lcos_info['capex']:,.0f} €")
        print(f"  储能成本均化值 (LCOS):  {lcos_info['lcos']:.2f} €/kWh")
        print(f"  设计寿命:              {params.lifetime} 年")

    # 2. 创建卡诺电池单元
    print("\n\n2. 卡诺电池单元操作模拟")
    print("-" * 80)

    cb_unit = CarnotBatteryUnit(
        unit_id=1,
        nominal_power_kw=500,
        capacity_kwh=3000,
        params=params_rankine
    )

    print(f"创建卡诺电池单元:")
    print(f"  额定功率: {cb_unit.nominal_power} kW")
    print(f"  储能容量: {cb_unit.capacity} kWh")
    print(f"  初始SOC: {cb_unit.soc:.1f} kWh ({cb_unit.soc/cb_unit.capacity*100:.1f}%)")

    # 模拟充放电
    print(f"\n  时间步长充放电操作:")

    # 充电1小时
    charge_result = cb_unit.step_charge(300, dt_hours=1.0)
    print(f"  [t=0] 充电300kW, 1小时:")
    print(f"        实际充电: {charge_result['p_charge_actual']:.1f} kW")
    print(f"        储存能量: {charge_result['e_stored']:.1f} kWh")
    print(f"        热损失: {charge_result['q_loss']:.1f} kWh")
    print(f"        SOC: {charge_result['soc_after']:.1f} kWh")

    # 放电1小时
    discharge_result = cb_unit.step_discharge(400, dt_hours=1.0)
    print(f"  [t=1] 放电400kW, 1小时:")
    print(f"        实际放电: {discharge_result['p_discharge_actual']:.1f} kW")
    print(f"        释放能量: {discharge_result['e_released']:.1f} kWh")
    print(f"        热损失: {discharge_result['q_loss']:.1f} kWh")
    print(f"        SOC: {discharge_result['soc_after']:.1f} kWh")

    # 3. 运行策略测试
    print("\n\n3. 卡诺电池运行策略对比")
    print("-" * 80)

    # 创建模拟数据
    t_hours = np.arange(0, 24)
    # 正弦波负荷
    power_net_e = 2000 * np.sin(np.pi * t_hours / 12) + 500
    # 正弦波电价 (反向)
    electricity_price = 100 * (1 - 0.3 * np.sin(np.pi * t_hours / 12)) + 20
    pv_output = np.maximum(0, 800 * np.sin(np.pi * (t_hours - 6) / 12))

    # 重新创建卡诺电池
    cb_unit = CarnotBatteryUnit(
        unit_id=1,
        nominal_power_kw=500,
        capacity_kwh=3000,
        params=params_rankine
    )

    strategy = CarnotBatteryOperationStrategy(cb_unit)

    # 运行混合策略
    cb_power = strategy.hybrid_strategy(
        power_net_e=power_net_e,
        electricity_price=electricity_price,
        pv_output=pv_output,
        dt=1.0
    )

    print(f"混合策略 (套利+削峰+可再生消纳)")
    print(f"  平均充电功率: {-np.mean(cb_power[cb_power < 0]):.1f} kW")
    print(f"  平均放电功率: {np.mean(cb_power[cb_power > 0]):.1f} kW")
    print(f"  最终SOC: {cb_unit.soc:.1f} kWh ({cb_unit.soc/cb_unit.capacity*100:.1f}%)")

    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
