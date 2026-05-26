"""
光伏发电机组 (Photovoltaic, PV)
================================
基于中芬国网配套项目代码库的出力曲线模型

设备类型：晶硅光伏、薄膜光伏、聚光光伏

输入：
    - 太阳辐射 (自然资源) [W/m²]
    - 环境温度 [°C]

输出：
    - 电力 (ele_bus) [kW]

参考数据来源：松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备/蓄水罐储冷储热/water_tank.py
    (其中包含光伏出力计算函数)
"""

import oemof.solph as solph
from oemof.solph.components import Source
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class PhotovoltaicParams:
    """
    光伏发电机组参数

    出力曲线参数来源：中芬国网配套项目代码库
    - 系统效率: 0.9 (含逆变器)
    - 温度系数: -0.0035 /°C
    - 参考温度: 25°C
    """

    label: str = "Photovoltaic"
    # 额定功率 [kW]
    nominal_power: float = 1000.0
    # 系统效率（含逆变器）
    efficiency: float = 0.9
    # 温度系数 [1/°C]
    temp_coefficient: float = -0.0035
    # 参考温度 [°C]
    ref_temperature: float = 25.0


class PhotovoltaicUnit:
    """
    光伏发电机组单元

    出力曲线模型（来自中芬项目代码库）：
        P = P_r × η × (G/1000) × [1 + α × (T - T_ref)]

    原始代码：
    ```python
    def cal_solar_output(solar_radiation_list, temperature_list, ppv):
        return [ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
                for r, t in zip(solar_radiation_list, temperature_list)]
    ```

    其中：
        P_r: 额定功率 [kW]
        η: 系统效率
        G: 太阳辐射强度 [W/m²]
        α: 温度系数 [1/°C]
        T: 环境温度 [°C]
        T_ref: 参考温度 [°C]
    """

    def __init__(self, params: PhotovoltaicParams = None):
        """
        初始化光伏发电机组单元

        Args:
            params: 参数配置，默认使用中芬项目参数
        """
        self.params = params or PhotovoltaicParams()

    def calc_output_curve(
        self, solar_radiation: List[float], temperature: List[float]
    ) -> List[float]:
        """
        计算光伏出力曲线（基于中芬项目代码库）

        Args:
            solar_radiation: 太阳辐射时序数据 [W/m²]
            temperature: 环境温度时序数据 [°C]

        Returns:
            出力时序数据 [kW]
        """
        p = self.params
        output = []

        for rad, temp in zip(solar_radiation, temperature):
            # 光伏出力公式
            power = (
                p.nominal_power
                * p.efficiency
                * rad
                / 1000
                * (1 + p.temp_coefficient * (temp - p.ref_temperature))
            )
            output.append(max(0, power))  # 确保出力非负

        return output

    def create_component(self, ele_bus: solph.Bus, output_curve: List[float]) -> Source:
        """
        创建光伏发电机组件

        Args:
            ele_bus: 电力母线
            output_curve: 出力时序数据 [kW]

        Returns:
            solph.Source: 光伏发电机组件
        """
        pv = Source(
            label=self.params.label,
            outputs={
                ele_bus: solph.Flow(
                    fix=output_curve,
                    nominal_value=1,  # 出力曲线直接使用功率值
                )
            },
        )
        return pv

    @staticmethod
    def get_io_description() -> Dict[str, Any]:
        """获取输入输出描述"""
        return {
            "单元名称": "可再生能源光发电单元",
            "单元编号": 4,
            "设备类型": ["晶硅光伏", "薄膜光伏", "聚光光伏"],
            "输入": {
                "太阳辐射": {
                    "单位": "W/m²",
                    "变量": "solar_radiation",
                    "说明": "通过出力曲线转换为电力输出",
                },
                "环境温度": {
                    "单位": "°C",
                    "变量": "temperature",
                    "说明": "影响光伏效率",
                },
            },
            "输出": {"电力": {"单位": "kW", "变量": "ele_output", "母线": "ele_bus"}},
            "关键参数": {
                "额定功率": {"单位": "kW", "说明": "可配置"},
                "系统效率": {"值": 0.9, "说明": "含逆变器"},
                "温度系数": {"值": -0.0035, "单位": "1/°C"},
                "参考温度": {"值": 25, "单位": "°C"},
            },
            "出力曲线": {
                "公式": "P = P_r × η × (G/1000) × [1 + α × (T - T_ref)]",
                "说明": "温度越高，效率越低",
            },
            "数据来源": "松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备",
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
        timeindex=date_time_index, infer_last_interval=True
    )

    # 创建母线
    ele_bus = solph.Bus(label="electricity bus")
    energy_system.add(ele_bus)

    # 模拟气象数据
    solar_radiation = [
        max(0, 800 * np.sin(np.pi * (t - 6) / 12)) for t in range(time_step)
    ]
    temperature = [15 + 10 * np.sin(2 * np.pi * (t - 6) / 24) for t in range(time_step)]

    # 创建光伏发电单元
    pv_unit = PhotovoltaicUnit(PhotovoltaicParams(nominal_power=500))
    pv_output = pv_unit.calc_output_curve(solar_radiation, temperature)
    pv = pv_unit.create_component(ele_bus, pv_output)
    energy_system.add(pv)

    print("光伏发电单元创建成功！")
    print(f"参数配置: {pv_unit.params}")
    print(f"\n太阳辐射: {[round(r, 1) for r in solar_radiation[:8]]}...")
    print(f"环境温度: {[round(t, 1) for t in temperature[:8]]}...")
    print(f"出力数据: {[round(p, 1) for p in pv_output[:8]]}...")
    print("\n输入输出描述:")
    import pprint

    pprint.pprint(PhotovoltaicUnit.get_io_description())
