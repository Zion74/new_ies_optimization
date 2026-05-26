"""
电制冷机 (Electric Chiller)
===========================
基于中芬国网配套项目代码库的参数配置

设备类型：离心式冷水机组、螺杆式冷水机组、涡旋式冷水机组

输入：
    - 电力 (ele_bus) [kW]

输出：
    - 冷量 (cool_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/电制冷机/ele_chiller.py
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ElectricChillerParams:
    """
    电制冷机参数
    
    参数来源：中芬国网配套项目代码库
    - 额定制冷量: 198 kW
    - COP: 2.81
    - 单台制冷量: 33 kW（6台机组）
    """
    label: str = "Electric Chiller"
    # 额定制冷量 [kW]
    nominal_capacity: float = 198.0
    # 单台制冷量 [kW]
    unit_capacity: float = 33.0
    # 机组数量
    num_units: int = 6
    # 制冷系数 COP
    cop: float = 2.81


class ElectricChillerUnit:
    """
    电制冷机单元
    
    能量转换模型：
        Q_cool = COP × W_ele
        
    其中：
        W_ele: 电力输入功率 [kW]
        Q_cool: 冷量输出功率 [kW]
        COP: 制冷系数
    """
    
    def __init__(self, params: ElectricChillerParams = None):
        """
        初始化电制冷机单元
        
        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or ElectricChillerParams()
        
    def create_component(self, ele_bus: solph.Bus,
                        cool_bus: solph.Bus) -> Transformer:
        """
        创建电制冷机组件
        
        Args:
            ele_bus: 电力母线
            cool_bus: 冷量母线
            
        Returns:
            solph.Transformer: 电制冷机组件
        """
        p = self.params
        
        ec = Transformer(
            label=p.label,
            inputs={ele_bus: solph.Flow()},
            outputs={
                cool_bus: solph.Flow(nominal_value=p.nominal_capacity)
            },
            conversion_factors={cool_bus: p.cop}
        )
        return ec
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "电热转化单元 - 电制冷机",
            "单元编号": 6,
            "设备类型": ["离心式冷水机组", "螺杆式冷水机组", "涡旋式冷水机组"],
            "输入": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_input",
                    "母线": "ele_bus"
                }
            },
            "输出": {
                "冷量": {
                    "单位": "kW",
                    "变量": "cool_output",
                    "母线": "cool_bus",
                    "额定值": 198
                }
            },
            "关键参数": {
                "单台制冷量": {"值": 33, "单位": "kW"},
                "机组数量": {"值": 6, "单位": "台"},
                "总额定制冷量": {"值": 198, "单位": "kW"},
                "制冷系数COP": {"值": 2.81}
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/电制冷机/ele_chiller.py"
        }
