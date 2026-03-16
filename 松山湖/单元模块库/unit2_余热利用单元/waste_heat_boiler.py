"""
余热锅炉 (Waste Heat Boiler)
============================
用于回收烟气等余热产生热水/蒸汽

设备类型：烟气余热锅炉、蒸汽余热锅炉

输入：
    - 烟气余热 (flue_gas_bus) [kW]

输出：
    - 热力 (heat_bus) [kW]
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class WasteHeatBoilerParams:
    """
    余热锅炉参数
    """
    label: str = "Waste Heat Boiler"
    # 额定热输出 [kW]
    nominal_capacity: float = 500.0
    # 余热回收效率
    efficiency: float = 0.85


class WasteHeatBoilerUnit:
    """
    余热锅炉单元
    
    能量转换模型：
        Q_heat_out = η × Q_flue_gas
        
    其中：
        Q_flue_gas: 烟气余热输入功率 [kW]
        Q_heat_out: 热力输出功率 [kW]
        η: 余热回收效率
    """
    
    def __init__(self, params: WasteHeatBoilerParams = None):
        """
        初始化余热锅炉单元
        
        Args:
            params: 参数配置
        """
        self.params = params or WasteHeatBoilerParams()
        
    def create_component(self, flue_gas_bus: solph.Bus, 
                        heat_bus: solph.Bus) -> Transformer:
        """
        创建余热锅炉组件
        
        Args:
            flue_gas_bus: 烟气余热母线
            heat_bus: 热力母线
            
        Returns:
            solph.Transformer: 余热锅炉组件
        """
        p = self.params
        
        whb = Transformer(
            label=p.label,
            inputs={flue_gas_bus: solph.Flow()},
            outputs={
                heat_bus: solph.Flow(nominal_value=p.nominal_capacity)
            },
            conversion_factors={heat_bus: p.efficiency}
        )
        return whb
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "余热利用单元 - 余热锅炉",
            "单元编号": 2,
            "设备类型": ["烟气余热锅炉", "蒸汽余热锅炉"],
            "输入": {
                "烟气余热": {
                    "单位": "kW",
                    "变量": "flue_gas_input",
                    "母线": "flue_gas_bus"
                }
            },
            "输出": {
                "热力": {
                    "单位": "kW",
                    "变量": "heat_output",
                    "母线": "heat_bus",
                    "额定值": 500
                }
            },
            "关键参数": {
                "额定热输出": {"值": 500, "单位": "kW"},
                "余热回收效率": {"值": 0.85, "范围": "0.70-0.90"}
            }
        }
