"""
光热集热器 (Solar Thermal Collector)
=====================================
利用太阳辐射产生热能

设备类型：平板集热器、真空管集热器、槽式聚光集热器、塔式聚光集热器

输入：
    - 太阳辐射 (自然资源) [W/m²]
    - 环境温度 [°C]

输出：
    - 热力 (heat_bus) [kW]
"""

import oemof.solph as solph
from oemof.solph.components import Source
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SolarThermalParams:
    """
    光热集热器参数
    """
    label: str = "Solar Thermal"
    # 额定热输出 [kW]
    nominal_capacity: float = 500.0
    # 光学效率
    optical_efficiency: float = 0.75
    # 热损失系数 [W/(m²·K)]
    heat_loss_coefficient: float = 3.5
    # 集热面积 [m²]
    collector_area: float = 1000.0


class SolarThermalUnit:
    """
    光热集热器单元
    
    出力模型：
        Q = A × [η₀ × G - U × (T_m - T_a)]
        
    其中：
        A: 集热面积 [m²]
        η₀: 光学效率
        G: 太阳辐射强度 [W/m²]
        U: 热损失系数 [W/(m²·K)]
        T_m: 工质平均温度 [°C]
        T_a: 环境温度 [°C]
    """
    
    def __init__(self, params: SolarThermalParams = None):
        """
        初始化光热集热器单元
        
        Args:
            params: 参数配置
        """
        self.params = params or SolarThermalParams()
        
    def calc_output_curve(self, solar_radiation: List[float],
                         ambient_temp: List[float],
                         mean_fluid_temp: float = 60.0) -> List[float]:
        """
        计算光热出力曲线
        
        Args:
            solar_radiation: 太阳辐射时序数据 [W/m²]
            ambient_temp: 环境温度时序数据 [°C]
            mean_fluid_temp: 工质平均温度 [°C]
            
        Returns:
            出力时序数据 [kW]
        """
        p = self.params
        output = []
        
        for rad, t_a in zip(solar_radiation, ambient_temp):
            # 光热出力公式（简化模型）
            q = p.collector_area * (
                p.optical_efficiency * rad / 1000 - 
                p.heat_loss_coefficient * (mean_fluid_temp - t_a) / 1000
            )
            output.append(max(0, q))
            
        return output
        
    def create_component(self, heat_bus: solph.Bus,
                        output_curve: List[float]) -> Source:
        """
        创建光热集热器组件
        
        Args:
            heat_bus: 热力母线
            output_curve: 出力时序数据 [kW]
            
        Returns:
            solph.Source: 光热集热器组件
        """
        st = Source(
            label=self.params.label,
            outputs={
                heat_bus: solph.Flow(
                    fix=output_curve,
                    nominal_value=1  # 出力曲线直接使用功率值
                )
            }
        )
        return st
    
    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生能源供冷热单元 - 光热集热器",
            "单元编号": 8,
            "设备类型": ["平板集热器", "真空管集热器", "槽式聚光集热器", "塔式聚光集热器"],
            "输入": {
                "太阳辐射": {
                    "单位": "W/m²",
                    "变量": "solar_radiation",
                    "说明": "通过出力曲线转换"
                },
                "环境温度": {
                    "单位": "°C",
                    "变量": "ambient_temp",
                    "说明": "影响热损失"
                }
            },
            "输出": {
                "热力": {
                    "单位": "kW",
                    "变量": "heat_output",
                    "母线": "heat_bus"
                }
            },
            "关键参数": {
                "集热面积": {"值": 1000, "单位": "m²"},
                "光学效率": {"值": 0.75, "范围": "0.65-0.85"},
                "热损失系数": {"值": 3.5, "单位": "W/(m²·K)", "范围": "2-5"}
            },
            "出力曲线": {
                "公式": "Q = A × [η₀ × G - U × (T_m - T_a)]",
                "说明": "温差越大，热损失越大"
            }
        }
