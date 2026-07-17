"""
蓄热/蓄冷罐 (Thermal Storage Tank)
==================================
基于中芬国网配套项目代码库的参数配置

设备类型：蓄热水罐、蓄冷水罐、相变储热

输入/输出：
    - 热力 (heat_bus) / 冷量 (cool_bus) [kW] - 双向

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/蓄水罐储冷储热/water_tank.py
及 operation.py
"""

import oemof.solph as solph
from oemof.solph.components import GenericStorage
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ThermalStorageParams:
    """
    蓄热/蓄冷罐参数
    
    参数来源：operation.py
    - 容量 = 功率 × 4/3
    - 蓄能效率: 0.9
    - 放能效率: 0.9
    - 热损失率: 0.001/h
    """
    label: str = "Thermal Storage"
    # 额定功率 [kW]
    nominal_power: float = 500.0
    # 额定容量 [kWh] (默认为功率×4/3)
    nominal_capacity: float = 666.67
    # 蓄能效率
    charge_efficiency: float = 0.90
    # 放能效率
    discharge_efficiency: float = 0.90
    # 热损失率 [1/h]
    loss_rate: float = 0.001
    # 初始储能水平
    initial_level: Optional[float] = None
    # 储能类型: "heat" 或 "cool"
    storage_type: str = "heat"


class ThermalStorageUnit:
    """
    蓄热/蓄冷罐储能单元
    
    状态方程：
        E(t+1) = E(t) × (1 - σ) + P_ch × η_ch - P_dis / η_dis
        
    其中：
        E(t): t时刻储能量 [kWh]
        σ: 热损失率 [1/h]
        P_ch: 蓄能功率 [kW]
        P_dis: 放能功率 [kW]
        η_ch: 蓄能效率
        η_dis: 放能效率
    """
    
    def __init__(self, params: ThermalStorageParams = None, storage_type: str = "heat"):
        """
        初始化蓄热/蓄冷罐单元
        
        Args:
            params: 参数配置，默认使用operation.py参数
            storage_type: 储能类型，"heat" 或 "cool"
        """
        self.params = params or ThermalStorageParams()
        if params is None:
            self.params.storage_type = storage_type
            if storage_type == "heat":
                self.params.label = "Heat Storage"
            else:
                self.params.label = "Cool Storage"
        
    def create_component(self, thermal_bus: solph.Bus) -> GenericStorage:
        """
        创建蓄热/蓄冷罐组件
        
        Args:
            thermal_bus: 热力/冷量母线
            
        Returns:
            solph.GenericStorage: 蓄热/蓄冷罐组件
        """
        p = self.params
        
        # 如果未指定容量，按功率×4/3计算
        capacity = p.nominal_capacity if p.nominal_capacity else p.nominal_power * 4 / 3
        
        storage = GenericStorage(
            label=p.label,
            nominal_storage_capacity=capacity,
            inputs={
                thermal_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            outputs={
                thermal_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            loss_rate=p.loss_rate,
            initial_storage_level=p.initial_level,
            inflow_conversion_factor=p.charge_efficiency,
            outflow_conversion_factor=p.discharge_efficiency
        )
        return storage
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "化学储能单元 - 蓄热/蓄冷罐",
            "单元编号": 7,
            "设备类型": ["蓄热水罐", "蓄冷水罐", "相变储热"],
            "输入": {
                "热力/冷量(蓄能)": {
                    "单位": "kW",
                    "变量": "thermal_charge",
                    "母线": "heat_bus/cool_bus"
                }
            },
            "输出": {
                "热力/冷量(放能)": {
                    "单位": "kW",
                    "变量": "thermal_discharge",
                    "母线": "heat_bus/cool_bus"
                }
            },
            "状态变量": {
                "储能量": {"单位": "kWh", "变量": "storage_content"}
            },
            "关键参数": {
                "额定功率": {"值": 500, "单位": "kW"},
                "额定容量": {"值": "功率×4/3", "单位": "kWh"},
                "蓄能效率": {"值": 0.90},
                "放能效率": {"值": 0.90},
                "热损失率": {"值": 0.001, "单位": "1/h"}
            },
            "数据来源": "operation.py"
        }
