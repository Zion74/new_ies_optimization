"""
吸收式制冷机 (Absorption Heat Pump/Chiller, AHP)
=================================================
基于中芬国网配套项目代码库的参数配置

设备类型：溴化锂吸收式制冷机、氨水吸收式制冷机

输入：
    - 热力 (heat_bus) [kW] - 驱动热源（余热）
    - 电力 (ele_bus) [kW] - 辅助电力

输出：
    - 冷量 (cool_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/吸收式制冷机/ahp.py
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class AbsorptionChillerParams:
    """
    吸收式制冷机参数
    
    参数来源：中芬国网配套项目代码库
    - 额定制冷量: 212 kW
    - COP: 0.75
    - 热能输入比: 0.983 (98.3%)
    - 辅助电能输入比: 0.017 (1.7%)
    """
    label: str = "AHP"
    # 额定制冷量 [kW]
    nominal_capacity: float = 212.0
    # 制冷系数 COP
    cop: float = 0.75
    # 热能输入比例（占总能量输入）
    heat_ratio: float = 0.983
    # 辅助电能输入比例（占总能量输入）
    ele_ratio: float = 0.017


class AbsorptionChillerUnit:
    """
    吸收式制冷机单元（余热驱动）
    
    能量转换模型：
        Q_cool = COP × (Q_heat + W_ele)
        Q_heat : W_ele = heat_ratio : ele_ratio = 0.983 : 0.017
        
    其中：
        Q_heat: 驱动热源输入功率 [kW]
        W_ele: 辅助电力输入功率 [kW]
        Q_cool: 冷量输出功率 [kW]
        COP: 制冷系数
    """
    
    def __init__(self, params: AbsorptionChillerParams = None):
        """
        初始化吸收式制冷机单元
        
        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or AbsorptionChillerParams()
        
    def create_component(self, heat_bus: solph.Bus, ele_bus: solph.Bus,
                        cool_bus: solph.Bus) -> Transformer:
        """
        创建吸收式制冷机组件
        
        Args:
            heat_bus: 热力母线（驱动热源）
            ele_bus: 电力母线（辅助电）
            cool_bus: 冷量母线
            
        Returns:
            solph.Transformer: 吸收式制冷机组件
        """
        p = self.params
        
        ahp = Transformer(
            label=p.label,
            inputs={
                heat_bus: solph.Flow(),
                ele_bus: solph.Flow()
            },
            outputs={
                cool_bus: solph.Flow(nominal_value=p.nominal_capacity)
            },
            conversion_factors={
                cool_bus: p.cop,
                heat_bus: p.heat_ratio,
                ele_bus: p.ele_ratio
            }
        )
        return ahp
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "余热利用单元 - 吸收式制冷机",
            "单元编号": 2,
            "设备类型": ["溴化锂吸收式制冷机", "氨水吸收式制冷机"],
            "输入": {
                "热力": {
                    "单位": "kW",
                    "变量": "heat_input",
                    "母线": "heat_bus",
                    "说明": "驱动热源（余热）",
                    "输入比例": 0.983
                },
                "电力": {
                    "单位": "kW",
                    "变量": "ele_input",
                    "母线": "ele_bus",
                    "说明": "辅助电力",
                    "输入比例": 0.017
                }
            },
            "输出": {
                "冷量": {
                    "单位": "kW",
                    "变量": "cool_output",
                    "母线": "cool_bus",
                    "额定值": 212
                }
            },
            "关键参数": {
                "额定制冷量": {"值": 212, "单位": "kW"},
                "制冷系数COP": {"值": 0.75},
                "热能输入比": {"值": 0.983, "说明": "98.3%"},
                "辅助电能输入比": {"值": 0.017, "说明": "1.7%"}
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/吸收式制冷机/ahp.py"
        }


# =============================================================================
# 使用示例
# =============================================================================
if __name__ == "__main__":
    import pandas as pd
    
    # 创建时间索引
    time_step = 24
    date_time_index = pd.date_range("2024-01-01", periods=time_step, freq="H")
    
    # 创建能源系统
    energy_system = solph.EnergySystem(
        timeindex=date_time_index, 
        infer_last_interval=True
    )
    
    # 创建母线
    ele_bus = solph.Bus(label="electricity bus")
    heat_bus = solph.Bus(label="heat bus")
    cool_bus = solph.Bus(label="cool bus")
    energy_system.add(ele_bus, heat_bus, cool_bus)
    
    # 创建吸收式制冷机单元
    ahp_unit = AbsorptionChillerUnit()
    ahp = ahp_unit.create_component(heat_bus, ele_bus, cool_bus)
    energy_system.add(ahp)
    
    print("吸收式制冷机单元创建成功！")
    print(f"参数配置: {ahp_unit.params}")
    print("\n输入输出描述:")
    import pprint
    pprint.pprint(AbsorptionChillerUnit.get_io_description())
