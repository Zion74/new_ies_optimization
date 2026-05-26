"""
单元6: 电热转化单元（包括冷）
============================
涵盖设备：电热泵、电制冷机

输入：电力
输出：热力 / 冷量
"""

from .heat_pump import HeatPumpUnit, HeatPumpParams
from .electric_chiller import ElectricChillerUnit, ElectricChillerParams

__all__ = [
    'HeatPumpUnit', 'HeatPumpParams',
    'ElectricChillerUnit', 'ElectricChillerParams'
]
