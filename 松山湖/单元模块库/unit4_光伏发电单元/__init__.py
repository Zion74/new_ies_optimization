"""
单元4: 可再生能源光发电单元
============================
涵盖设备：光伏发电机组

输入：太阳辐射（自然资源）
输出：电力
"""

from .photovoltaic import PhotovoltaicUnit, PhotovoltaicParams

__all__ = ['PhotovoltaicUnit', 'PhotovoltaicParams']
