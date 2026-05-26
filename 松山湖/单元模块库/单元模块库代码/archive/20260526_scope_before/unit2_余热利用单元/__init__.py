"""
单元2: 余热利用单元
==================
涵盖设备：吸收式制冷机（AHP）、余热锅炉

输入：余热/热力 (+ 辅助电力)
输出：冷量 / 热力
"""

from .absorption_chiller import AbsorptionChillerUnit, AbsorptionChillerParams
from .waste_heat_boiler import WasteHeatBoilerUnit, WasteHeatBoilerParams

__all__ = [
    'AbsorptionChillerUnit', 'AbsorptionChillerParams',
    'WasteHeatBoilerUnit', 'WasteHeatBoilerParams'
]
