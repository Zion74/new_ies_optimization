"""
蓄电池 (Battery Storage)
========================
基于中芬国网配套项目代码库的参数配置

设备类型：锂离子电池、铅酸电池、钠硫电池、液流电池

输入/输出：
    - 电力 (ele_bus) [kW] - 双向

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/蓄电池/ele_storage.py
及 operation.py
"""

import oemof.solph as solph
from oemof.solph.components import GenericStorage
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class BatteryStorageParams:
    """
    蓄电池参数
    
    参数来源：operation.py
    - 容量 = 功率 × 2 (即2小时储能)
    - 充电效率: 0.95
    - 放电效率: 0.90
    - 自放电率: 0.000125/h
    """
    label: str = "Battery Storage"
    # 额定功率 [kW]
    nominal_power: float = 500.0
    # 额定容量 [kWh] (默认为功率×2)
    nominal_capacity: float = 1000.0
    # 充电效率
    charge_efficiency: float = 0.95
    # 放电效率
    discharge_efficiency: float = 0.90
    # 自放电损耗率 [1/h]
    loss_rate: float = 0.000125
    # 初始SOC
    initial_soc: Optional[float] = None


class BatteryStorageUnit:
    """
    蓄电池储能单元
    
    状态方程：
        E(t+1) = E(t) × (1 - σ) + P_ch × η_ch - P_dis / η_dis
        
    其中：
        E(t): t时刻储能量 [kWh]
        σ: 自放电率 [1/h]
        P_ch: 充电功率 [kW]
        P_dis: 放电功率 [kW]
        η_ch: 充电效率
        η_dis: 放电效率
    """
    
    def __init__(self, params: BatteryStorageParams = None):
        """
        初始化蓄电池单元
        
        Args:
            params: 参数配置，默认使用operation.py参数
        """
        self.params = params or BatteryStorageParams()
        
    def create_component(self, ele_bus: solph.Bus) -> GenericStorage:
        """
        创建蓄电池组件
        
        Args:
            ele_bus: 电力母线
            
        Returns:
            solph.GenericStorage: 蓄电池组件
        """
        p = self.params
        
        battery = GenericStorage(
            label=p.label,
            nominal_storage_capacity=p.nominal_capacity,
            inputs={
                ele_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            outputs={
                ele_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            loss_rate=p.loss_rate,
            initial_storage_level=p.initial_soc,
            inflow_conversion_factor=p.charge_efficiency,
            outflow_conversion_factor=p.discharge_efficiency
        )
        return battery
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "化学储能单元 - 蓄电池",
            "单元编号": 7,
            "设备类型": ["锂离子电池", "铅酸电池", "钠硫电池", "液流电池"],
            "输入": {
                "电力(充电)": {
                    "单位": "kW",
                    "变量": "ele_charge",
                    "母线": "ele_bus"
                }
            },
            "输出": {
                "电力(放电)": {
                    "单位": "kW",
                    "变量": "ele_discharge",
                    "母线": "ele_bus"
                }
            },
            "状态变量": {
                "储能量": {"单位": "kWh", "变量": "storage_content"}
            },
            "关键参数": {
                "额定功率": {"值": 500, "单位": "kW"},
                "额定容量": {"值": 1000, "单位": "kWh", "说明": "功率×2"},
                "充电效率": {"值": 0.95},
                "放电效率": {"值": 0.90},
                "自放电率": {"值": 0.000125, "单位": "1/h"}
            },
            "数据来源": "operation.py"
        }
