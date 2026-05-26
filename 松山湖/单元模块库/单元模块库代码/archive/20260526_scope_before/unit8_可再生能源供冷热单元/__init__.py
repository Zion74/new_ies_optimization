"""
单元8: 可再生能源供冷热单元
============================
涵盖设备：地源热泵、光热集热器

输入：电力 + 地热能/太阳辐射
输出：热力 / 冷量
"""

from .ground_source_heat_pump import GroundSourceHeatPumpUnit, GroundSourceHeatPumpParams
from .solar_thermal import SolarThermalUnit, SolarThermalParams

__all__ = [
    'GroundSourceHeatPumpUnit', 'GroundSourceHeatPumpParams',
    'SolarThermalUnit', 'SolarThermalParams'
]
