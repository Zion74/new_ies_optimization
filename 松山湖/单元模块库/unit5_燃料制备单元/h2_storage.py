"""
储氢罐 (Hydrogen Storage Tank)
==============================
基于中芬国网配套项目代码库的参数配置

设备类型：高压储氢罐、低温液态储氢罐

输入/输出：
    - 氢气 (h2_bus) [kW热值] - 双向

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/储氢罐/h2_storage.py
"""

import oemof.solph as solph
from oemof.solph.components import GenericStorage
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class H2StorageParams:
    """
    储氢罐参数
    
    参数来源：中芬国网配套项目代码库
    - 额定储气量: 1760 (单位待确认)
    - 最小储气量: 1240
    - 损耗率: 3%
    - 充放效率: 95%
    """
    label: str = "H2 Storage"
    # 额定储气容量
    nominal_capacity: float = 1760.0
    # 额定充放功率
    nominal_power: float = 1760.0
    # 最小储气比例
    min_storage_level: float = 1240 / 1760  # ≈ 0.705
    # 损耗率 [1/h]
    loss_rate: float = 0.03
    # 充气效率
    charge_efficiency: float = 0.95
    # 放气效率
    discharge_efficiency: float = 0.95
    # 初始储气水平
    initial_level: Optional[float] = None


class H2StorageUnit:
    """
    储氢罐单元
    
    状态方程：
        E(t+1) = E(t) × (1 - σ) + P_ch × η_ch - P_dis / η_dis
        
    约束条件：
        E_min ≤ E(t) ≤ E_max
        
    其中：
        E(t): t时刻储气量
        σ: 损耗率
        P_ch: 充气功率
        P_dis: 放气功率
        η_ch: 充气效率
        η_dis: 放气效率
    """
    
    def __init__(self, params: H2StorageParams = None):
        """
        初始化储氢罐单元
        
        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or H2StorageParams()
        
    def create_component(self, h2_bus: solph.Bus) -> GenericStorage:
        """
        创建储氢罐组件
        
        Args:
            h2_bus: 氢气母线
            
        Returns:
            solph.GenericStorage: 储氢罐组件
        """
        p = self.params
        
        h2_storage = GenericStorage(
            label=p.label,
            nominal_storage_capacity=p.nominal_capacity,
            inputs={
                h2_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            outputs={
                h2_bus: solph.Flow(nominal_value=p.nominal_power)
            },
            loss_rate=p.loss_rate,
            min_storage_level=p.min_storage_level,
            initial_storage_level=p.initial_level,
            inflow_conversion_factor=p.charge_efficiency,
            outflow_conversion_factor=p.discharge_efficiency
        )
        return h2_storage
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生燃料制备单元 - 储氢罐",
            "单元编号": 5,
            "设备类型": ["高压储氢罐", "低温液态储氢罐"],
            "输入": {
                "氢气(充气)": {
                    "单位": "kW(热值)",
                    "变量": "h2_charge",
                    "母线": "h2_bus"
                }
            },
            "输出": {
                "氢气(放气)": {
                    "单位": "kW(热值)",
                    "变量": "h2_discharge",
                    "母线": "h2_bus"
                }
            },
            "状态变量": {
                "储气量": {"单位": "kWh(热值)", "变量": "storage_content"}
            },
            "关键参数": {
                "额定储气容量": {"值": 1760},
                "最小储气量": {"值": 1240, "比例": 0.705},
                "损耗率": {"值": 0.03, "说明": "3%/h"},
                "充气效率": {"值": 0.95},
                "放气效率": {"值": 0.95}
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/储氢罐/h2_storage.py"
        }
