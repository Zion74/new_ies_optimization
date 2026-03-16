"""
电解槽 (Electrolyzer)
=====================
用于电解水制取氢气

设备类型：碱性电解槽(AEL)、质子交换膜电解槽(PEMEL)、固体氧化物电解槽(SOEL)

输入：
    - 电力 (ele_bus) [kW]

输出：
    - 氢气 (h2_bus) [kW热值]
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ElectrolyzerParams:
    """
    电解槽参数
    """
    label: str = "Electrolyzer"
    # 额定电功率 [kW]
    nominal_power: float = 500.0
    # 电解效率（电能转氢能）
    efficiency: float = 0.70
    # 氢气低热值 [kWh/kg]
    h2_heat_value: float = 33.33


class ElectrolyzerUnit:
    """
    电解槽单元（制氢）
    
    能量转换模型：
        Q_H2 = η × W_ele
        m_H2 = Q_H2 / LHV_H2
        
    其中：
        W_ele: 电力输入功率 [kW]
        Q_H2: 氢气输出功率（以热值计）[kW]
        η: 电解效率
        m_H2: 氢气产量 [kg/h]
        LHV_H2: 氢气低热值 [kWh/kg]
    """
    
    def __init__(self, params: ElectrolyzerParams = None):
        """
        初始化电解槽单元
        
        Args:
            params: 参数配置
        """
        self.params = params or ElectrolyzerParams()
        
    def create_component(self, ele_bus: solph.Bus, 
                        h2_bus: solph.Bus) -> Transformer:
        """
        创建电解槽组件
        
        Args:
            ele_bus: 电力母线
            h2_bus: 氢气母线
            
        Returns:
            solph.Transformer: 电解槽组件
        """
        p = self.params
        
        electrolyzer = Transformer(
            label=p.label,
            inputs={ele_bus: solph.Flow()},
            outputs={
                h2_bus: solph.Flow(
                    nominal_value=p.nominal_power * p.efficiency
                )
            },
            conversion_factors={h2_bus: p.efficiency}
        )
        return electrolyzer
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生燃料制备单元 - 电解槽",
            "单元编号": 5,
            "设备类型": ["碱性电解槽(AEL)", "质子交换膜电解槽(PEMEL)", "固体氧化物电解槽(SOEL)"],
            "输入": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_input",
                    "母线": "ele_bus"
                }
            },
            "输出": {
                "氢气": {
                    "单位": "kW(热值)",
                    "变量": "h2_output",
                    "母线": "h2_bus"
                }
            },
            "关键参数": {
                "额定电功率": {"值": 500, "单位": "kW"},
                "电解效率": {"值": 0.70, "范围": "0.60-0.80"},
                "氢气低热值": {"值": 33.33, "单位": "kWh/kg"}
            }
        }
