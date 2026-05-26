"""
电热泵 (Electric Heat Pump)
===========================
基于中芬国网配套项目代码库的参数配置

设备类型：空气源热泵、水源热泵、地源热泵

输入：
    - 电力 (ele_bus) [kW]

输出：
    - 热力 (heat_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/吸收式制冷机/ahp.py
    (其中包含电热泵参数：单台制热量37kW)
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class HeatPumpParams:
    """
    电热泵参数
    
    参数来源：中芬国网配套项目代码库
    - 单台制热量: 37 kW
    - 机组数量: 6台（可配置）
    - 默认COP: 4.0
    """
    label: str = "Heat Pump"
    # 额定制热量 [kW]（单台37kW × 6台 = 222kW）
    nominal_capacity: float = 222.0
    # 单台制热量 [kW]
    unit_capacity: float = 37.0
    # 机组数量
    num_units: int = 6
    # 制热系数 COP
    cop: float = 4.0


class HeatPumpUnit:
    """
    电热泵单元
    
    能量转换模型：
        Q_heat = COP × W_ele
        
    其中：
        W_ele: 电力输入功率 [kW]
        Q_heat: 热力输出功率 [kW]
        COP: 制热系数
    """
    
    def __init__(self, params: HeatPumpParams = None):
        """
        初始化电热泵单元
        
        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or HeatPumpParams()
        
    def create_component(self, ele_bus: solph.Bus,
                        heat_bus: solph.Bus) -> Transformer:
        """
        创建电热泵组件
        
        Args:
            ele_bus: 电力母线
            heat_bus: 热力母线
            
        Returns:
            solph.Transformer: 电热泵组件
        """
        p = self.params
        
        hp = Transformer(
            label=p.label,
            inputs={ele_bus: solph.Flow()},
            outputs={
                heat_bus: solph.Flow(nominal_value=p.nominal_capacity)
            },
            conversion_factors={heat_bus: p.cop}
        )
        return hp
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "电热转化单元 - 电热泵",
            "单元编号": 6,
            "设备类型": ["空气源热泵", "水源热泵", "地源热泵"],
            "输入": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_input",
                    "母线": "ele_bus"
                }
            },
            "输出": {
                "热力": {
                    "单位": "kW",
                    "变量": "heat_output",
                    "母线": "heat_bus",
                    "额定值": 222
                }
            },
            "关键参数": {
                "单台制热量": {"值": 37, "单位": "kW"},
                "机组数量": {"值": 6, "单位": "台"},
                "总额定制热量": {"值": 222, "单位": "kW"},
                "制热系数COP": {"值": 4.0, "范围": "2.5-5.0"}
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备"
        }
