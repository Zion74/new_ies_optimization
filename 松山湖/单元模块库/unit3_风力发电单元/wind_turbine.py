"""
风力发电机组 (Wind Turbine)
===========================
基于中芬国网配套项目代码库的出力曲线模型

设备类型：水平轴风力发电机、垂直轴风力发电机

输入：
    - 风能 (自然资源，通过出力曲线转换)

输出：
    - 电力 (ele_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/蓄水罐储冷储热/water_tank.py
    (其中包含风电出力计算函数)
"""

import oemof.solph as solph
from oemof.solph.components import Source
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class WindTurbineParams:
    """
    风力发电机组参数
    
    出力曲线参数来源：中芬国网配套项目代码库
    - 切入风速: 2.5 m/s
    - 额定风速: 9.0 m/s
    - 切出风速: 25.0 m/s
    """
    label: str = "Wind Turbine"
    # 额定功率 [kW]
    nominal_power: float = 1000.0
    # 切入风速 [m/s]
    cut_in_speed: float = 2.5
    # 额定风速 [m/s]
    rated_speed: float = 9.0
    # 切出风速 [m/s]
    cut_out_speed: float = 25.0


class WindTurbineUnit:
    """
    风力发电机组单元
    
    出力曲线模型（来自中芬项目代码库）：
        P = 0                                    , v < v_ci (切入风速)
        P = P_r × (v³ - v_ci³)/(v_r³ - v_ci³)   , v_ci ≤ v < v_r (额定风速)
        P = P_r                                  , v_r ≤ v < v_co (切出风速)
        P = 0                                    , v ≥ v_co
        
    其中：
        v: 风速 [m/s]
        P_r: 额定功率 [kW]
        v_ci: 切入风速 [m/s]
        v_r: 额定风速 [m/s]
        v_co: 切出风速 [m/s]
    """
    
    def __init__(self, params: WindTurbineParams = None):
        """
        初始化风力发电机组单元
        
        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or WindTurbineParams()
        
    def calc_output_curve(self, wind_speed: List[float]) -> List[float]:
        """
        计算风电出力曲线（基于中芬项目代码库）
        
        原始代码：
        ```python
        def cal_wind_output(wind_speed_list, pwt):
            ret = [0 for _ in range(len(wind_speed_list))]
            for i in range(len(wind_speed_list)):
                w = wind_speed_list[i]
                if 2.5 <= w < 9:
                    ret[i] = (w ** 3 - 2.5 ** 3) / (9 ** 3 - 2.5 ** 3) * pwt
                elif 9 <= w < 25:
                    ret[i] = pwt
            return ret
        ```
        
        Args:
            wind_speed: 风速时序数据 [m/s]
            
        Returns:
            出力时序数据 [kW]
        """
        p = self.params
        output = []
        
        for w in wind_speed:
            if w < p.cut_in_speed:
                # 风速低于切入风速，不发电
                output.append(0)
            elif w < p.rated_speed:
                # 切入到额定风速之间，按立方规律
                power = p.nominal_power * (w**3 - p.cut_in_speed**3) / \
                       (p.rated_speed**3 - p.cut_in_speed**3)
                output.append(power)
            elif w < p.cut_out_speed:
                # 额定到切出风速之间，满发
                output.append(p.nominal_power)
            else:
                # 风速超过切出风速，停机保护
                output.append(0)
                
        return output
        
    def create_component(self, ele_bus: solph.Bus, 
                        output_curve: List[float]) -> Source:
        """
        创建风力发电机组件
        
        Args:
            ele_bus: 电力母线
            output_curve: 出力时序数据 [kW]
            
        Returns:
            solph.Source: 风力发电机组件
        """
        wt = Source(
            label=self.params.label,
            outputs={
                ele_bus: solph.Flow(
                    fix=output_curve,
                    nominal_value=1  # 出力曲线直接使用功率值
                )
            }
        )
        return wt
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生能源风力发电单元",
            "单元编号": 3,
            "设备类型": ["水平轴风力发电机", "垂直轴风力发电机"],
            "输入": {
                "风能": {
                    "单位": "m/s",
                    "变量": "wind_speed",
                    "说明": "通过出力曲线转换为电力输出"
                }
            },
            "输出": {
                "电力": {
                    "单位": "kW",
                    "变量": "ele_output",
                    "母线": "ele_bus"
                }
            },
            "关键参数": {
                "额定功率": {"单位": "kW", "说明": "可配置"},
                "切入风速": {"值": 2.5, "单位": "m/s"},
                "额定风速": {"值": 9.0, "单位": "m/s"},
                "切出风速": {"值": 25.0, "单位": "m/s"}
            },
            "出力曲线": {
                "公式": "P = P_r × (v³ - v_ci³)/(v_r³ - v_ci³)",
                "说明": "切入到额定风速之间按立方规律变化"
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备"
        }


# =============================================================================
# 使用示例
# =============================================================================
if __name__ == "__main__":
    import pandas as pd
    import numpy as np
    
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
    energy_system.add(ele_bus)
    
    # 模拟风速数据
    wind_speed = [5 + 3*np.sin(2*np.pi*t/24) for t in range(time_step)]
    
    # 创建风力发电单元
    wt_unit = WindTurbineUnit(WindTurbineParams(nominal_power=500))
    wt_output = wt_unit.calc_output_curve(wind_speed)
    wt = wt_unit.create_component(ele_bus, wt_output)
    energy_system.add(wt)
    
    print("风力发电单元创建成功！")
    print(f"参数配置: {wt_unit.params}")
    print(f"\n风速数据: {wind_speed[:6]}...")
    print(f"出力数据: {[round(p, 1) for p in wt_output[:6]]}...")
    print("\n输入输出描述:")
    import pprint
    pprint.pprint(WindTurbineUnit.get_io_description())
