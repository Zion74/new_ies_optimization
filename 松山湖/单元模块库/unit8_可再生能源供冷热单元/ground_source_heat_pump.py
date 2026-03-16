"""
地源热泵 (Ground Source Heat Pump, GSHP)
=========================================
利用地下恒温层作为冷/热源

设备类型：地埋管地源热泵、地下水地源热泵

输入：
    - 电力 (ele_bus) [kW]
    - 地热能（隐含在COP中）

输出：
    - 热力 (heat_bus) [kW] - 制热模式
    - 冷量 (cool_bus) [kW] - 制冷模式
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class GroundSourceHeatPumpParams:
    """
    地源热泵参数
    """
    label: str = "GSHP"
    # 额定制热量 [kW]
    nominal_heat_capacity: float = 500.0
    # 额定制冷量 [kW]
    nominal_cool_capacity: float = 400.0
    # 制热COP
    cop_heating: float = 4.5
    # 制冷COP（EER）
    cop_cooling: float = 5.0


class GroundSourceHeatPumpUnit:
    """
    地源热泵单元（供热+制冷）
    
    制热模式：
        Q_heat = COP_h × W_ele
        
    制冷模式：
        Q_cool = COP_c × W_ele
        
    其中：
        W_ele: 电力输入功率 [kW]
        Q_heat: 热力输出功率 [kW]
        Q_cool: 冷量输出功率 [kW]
        COP_h: 制热系数
        COP_c: 制冷系数（EER）
    """
    
    def __init__(self, params: GroundSourceHeatPumpParams = None):
        """
        初始化地源热泵单元
        
        Args:
            params: 参数配置
        """
        self.params = params or GroundSourceHeatPumpParams()
        
    def create_heating_component(self, ele_bus: solph.Bus,
                                 heat_bus: solph.Bus) -> Transformer:
        """
        创建地源热泵制热组件
        
        Args:
            ele_bus: 电力母线
            heat_bus: 热力母线
            
        Returns:
            solph.Transformer: 地源热泵制热组件
        """
        p = self.params
        
        gshp_heat = Transformer(
            label=f"{p.label}_heating",
            inputs={ele_bus: solph.Flow()},
            outputs={
                heat_bus: solph.Flow(nominal_value=p.nominal_heat_capacity)
            },
            conversion_factors={heat_bus: p.cop_heating}
        )
        return gshp_heat
    
    def create_cooling_component(self, ele_bus: solph.Bus,
                                 cool_bus: solph.Bus) -> Transformer:
        """
        创建地源热泵制冷组件
        
        Args:
            ele_bus: 电力母线
            cool_bus: 冷量母线
            
        Returns:
            solph.Transformer: 地源热泵制冷组件
        """
        p = self.params
        
        gshp_cool = Transformer(
            label=f"{p.label}_cooling",
            inputs={ele_bus: solph.Flow()},
            outputs={
                cool_bus: solph.Flow(nominal_value=p.nominal_cool_capacity)
            },
            conversion_factors={cool_bus: p.cop_cooling}
        )
        return gshp_cool
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生能源供冷热单元 - 地源热泵",
            "单元编号": 8,
            "设备类型": ["地埋管地源热泵", "地下水地源热泵"],
            "输入": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_input",
                    "母线": "ele_bus"
                },
                "地热能": {
                    "说明": "隐含在COP中，无需单独建模"
                }
            },
            "输出": {
                "热力": {
                    "单位": "kW",
                    "变量": "heat_output",
                    "母线": "heat_bus",
                    "模式": "制热",
                    "额定值": 500
                },
                "冷量": {
                    "单位": "kW",
                    "变量": "cool_output",
                    "母线": "cool_bus",
                    "模式": "制冷",
                    "额定值": 400
                }
            },
            "关键参数": {
                "额定制热量": {"值": 500, "单位": "kW"},
                "额定制冷量": {"值": 400, "单位": "kW"},
                "制热COP": {"值": 4.5, "范围": "3.5-5.5"},
                "制冷COP(EER)": {"值": 5.0, "范围": "4.0-6.0"}
            }
        }
