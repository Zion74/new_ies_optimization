"""
单元6：储能单元
===============
涵盖设备：电储能、热储能、冷储能
主要能源转换形式：电/热/冷储能充放

说明：储能单元用于支撑系统动态平衡和运行管理仿真，不作为新增多能转化类型数量达标的唯一依据。
"""

from .battery_storage import BatteryStorageUnit, BatteryStorageParams
from .thermal_storage import ThermalStorageUnit, ThermalStorageParams

__all__ = [
    "BatteryStorageUnit",
    "BatteryStorageParams",
    "ThermalStorageUnit",
    "ThermalStorageParams",
]
