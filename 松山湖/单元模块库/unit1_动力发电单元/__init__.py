"""
单元1: 动力发电单元
==================
涵盖设备：热电联产机组（CHP/燃气轮机/燃气内燃机）

输入：天然气
输出：电力 + 热力
"""

from .chp import CHPUnit, CHPParams

__all__ = ['CHPUnit', 'CHPParams']
