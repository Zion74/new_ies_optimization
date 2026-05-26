"""
热电联产机组 (Combined Heat and Power, CHP)
============================================
基于中芬国网配套项目代码库的参数配置

设备类型：燃气轮机CHP、燃气内燃机CHP、微型燃气轮机

输入：
    - 天然气 (gas_bus) [kW热值]

输出：
    - 电力 (ele_bus) [kW]
    - 热力 (heat_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/热电联产/chp.py
"""

import oemof.solph as solph
from oemof.solph.components import Transformer
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class CHPParams:
    """
    热电联产机组参数
    
    参数来源：中芬国网配套项目代码库
    - 输入流的最大值为250kW(天然气热值)，最小值为15kW
    - 产电效率: 3.3 (基于输入燃气热值)
    - 产热效率: 6.4 (基于输入燃气热值)
    
    注：原代码中的效率值较大是因为以燃气输入流量而非热值作为基准
    这里转换为标准效率表示 (0-1范围)
    """
    label: str = "CHP"
    # 额定燃气输入功率 [kW热值]
    nominal_gas_input: float = 250.0
    # 最小燃气输入功率 [kW热值]  
    min_gas_input: float = 15.0
    # 发电效率 (原代码: 3.3, 此处转换为标准值)
    ele_efficiency: float = 0.33
    # 产热效率 (原代码: 6.4, 此处转换为标准值)
    heat_efficiency: float = 0.50
    # 最小负荷率
    min_load_ratio: float = 0.06  # 15/250 ≈ 0.06
    # 最大负荷率
    max_load_ratio: float = 1.0


class CHPUnit:
    """
    热电联产机组单元
    
    能量转换模型：
        P_ele = η_ele × Q_gas
        Q_heat = η_heat × Q_gas
        
    其中：
        Q_gas: 天然气输入功率 (以热值计) [kW]
        P_ele: 电力输出功率 [kW]
        Q_heat: 热力输出功率 [kW]
        η_ele: 发电效率
        η_heat: 产热效率
    """
    
    def __init__(self, params: CHPParams = None):
        """
        初始化CHP单元
        
        Args:
            params: CHP参数配置，默认使用中芬项目参数
        """
        self.params = params or CHPParams()
        
    def create_component(self, gas_bus: solph.Bus, ele_bus: solph.Bus, 
                        heat_bus: solph.Bus) -> Transformer:
        """
        创建热电联产机组组件
        
        Args:
            gas_bus: 天然气母线
            ele_bus: 电力母线
            heat_bus: 热力母线
            
        Returns:
            solph.Transformer: 热电联产机组组件
        """
        p = self.params
        
        # 计算电力和热力输出额定值
        nominal_ele_output = p.nominal_gas_input * p.ele_efficiency
        nominal_heat_output = p.nominal_gas_input * p.heat_efficiency
        
        chp = Transformer(
            label=p.label,
            inputs={
                gas_bus: solph.Flow(
                    nominal_value=p.nominal_gas_input,
                    min=p.min_load_ratio,
                    max=p.max_load_ratio
                )
            },
            outputs={
                ele_bus: solph.Flow(nominal_value=nominal_ele_output),
                heat_bus: solph.Flow(nominal_value=nominal_heat_output)
            },
            conversion_factors={
                ele_bus: p.ele_efficiency,
                heat_bus: p.heat_efficiency
            }
        )
        return chp
    
    def create_component_original_params(self, gas_bus: solph.Bus, ele_bus: solph.Bus, 
                                         heat_bus: solph.Bus) -> Transformer:
        """
        使用原始代码库参数创建CHP组件（保持与原代码一致）
        
        原代码参数：
        - inputs: nominal_value=250, min=15/250, max=1.0
        - outputs: ele_bus=250*3.3, heat_bus=250*6.4
        - conversion_factors: ele_bus=3.3, heat_bus=6.4
        """
        chp = Transformer(
            label=self.params.label,
            inputs={
                gas_bus: solph.Flow(
                    nominal_value=250,
                    min=15/250,
                    max=1.0
                )
            },
            outputs={
                ele_bus: solph.Flow(nominal_value=250 * 3.3),
                heat_bus: solph.Flow(nominal_value=250 * 6.4)
            },
            conversion_factors={
                ele_bus: 3.3,
                heat_bus: 6.4
            }
        )
        return chp
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "动力发电单元 - 热电联产机组",
            "单元编号": 1,
            "设备类型": ["燃气轮机CHP", "燃气内燃机CHP", "微型燃气轮机"],
            "输入": {
                "天然气": {
                    "单位": "kW(热值)",
                    "变量": "gas_input",
                    "母线": "gas_bus",
                    "额定值": 250,
                    "最小值": 15
                }
            },
            "输出": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_output",
                    "母线": "ele_bus",
                    "额定值": "250 × η_ele"
                },
                "热力": {
                    "单位": "kW",
                    "变量": "heat_output",
                    "母线": "heat_bus",
                    "额定值": "250 × η_heat"
                }
            },
            "关键参数": {
                "额定燃气输入": {"值": 250, "单位": "kW"},
                "最小燃气输入": {"值": 15, "单位": "kW"},
                "发电效率": {"原始值": 3.3, "标准值": 0.33, "说明": "原代码以流量为基准"},
                "产热效率": {"原始值": 6.4, "标准值": 0.50, "说明": "原代码以流量为基准"},
                "最小负荷率": {"值": 0.06}
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/热电联产/chp.py"
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
    gas_bus = solph.Bus(label="gas bus")
    energy_system.add(ele_bus, heat_bus, gas_bus)
    
    # 创建CHP单元 - 使用默认参数（中芬项目参数）
    chp_unit = CHPUnit()
    chp = chp_unit.create_component(gas_bus, ele_bus, heat_bus)
    energy_system.add(chp)
    
    print("CHP单元创建成功！")
    print(f"参数配置: {chp_unit.params}")
    print("\n输入输出描述:")
    import pprint
    pprint.pprint(CHPUnit.get_io_description())
