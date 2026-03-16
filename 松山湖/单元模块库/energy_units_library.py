"""
多能转化单元模块库 - 综合能源系统设备模型
================================================================================
基于 oemof.solph 的规划设计阶段简化模型库

单元分类（8类）：
1. 动力发电单元 - 热电联产机组（CHP/燃气轮机）
2. 余热利用单元 - 吸收式制冷机（余热驱动）、余热锅炉
3. 可再生能源风力发电单元 - 风力发电机组
4. 可再生能源光发电单元 - 光伏发电机组
5. 可再生燃料制备单元 - 电解槽制氢、储氢罐
6. 电热转化单元（包括冷）- 电热泵、电制冷机
7. 化学储能单元 - 蓄电池、蓄热/冷罐
8. 可再生能源供冷热单元 - 地源热泵、光热集热器

参数来源：
- 松山湖/23中芬国网配套项目代码库模块/10类能源系统典型设备
- operation.py

作者: 郑浩男
日期: 2026-02
================================================================================
"""

# =============================================================================
# 导入所有单元模块
# =============================================================================

# 单元1: 动力发电单元
from unit1_动力发电单元 import CHPUnit, CHPParams

# 单元2: 余热利用单元
from unit2_余热利用单元 import (
    AbsorptionChillerUnit,
    AbsorptionChillerParams,
    WasteHeatBoilerUnit,
    WasteHeatBoilerParams,
)

# 单元3: 风力发电单元
from unit3_风力发电单元 import WindTurbineUnit, WindTurbineParams

# 单元4: 光伏发电单元
from unit4_光伏发电单元 import PhotovoltaicUnit, PhotovoltaicParams

# 单元5: 燃料制备单元
from unit5_燃料制备单元 import (
    ElectrolyzerUnit,
    ElectrolyzerParams,
    H2StorageUnit,
    H2StorageParams,
)

# 单元6: 电热转化单元
from unit6_电热转化单元 import (
    HeatPumpUnit,
    HeatPumpParams,
    ElectricChillerUnit,
    ElectricChillerParams,
)

# 单元7: 化学储能单元
from unit7_化学储能单元 import (
    BatteryStorageUnit,
    BatteryStorageParams,
    ThermalStorageUnit,
    ThermalStorageParams,
)

# 单元8: 可再生能源供冷热单元
from unit8_可再生能源供冷热单元 import (
    GroundSourceHeatPumpUnit,
    GroundSourceHeatPumpParams,
    SolarThermalUnit,
    SolarThermalParams,
)


# =============================================================================
# 单元类型映射
# =============================================================================

UNIT_TYPES = {
    "1_动力发电单元": {
        "CHP": CHPUnit,
    },
    "2_余热利用单元": {
        "AbsorptionChiller": AbsorptionChillerUnit,
        "WasteHeatBoiler": WasteHeatBoilerUnit,
    },
    "3_风力发电单元": {
        "WindTurbine": WindTurbineUnit,
    },
    "4_光伏发电单元": {
        "Photovoltaic": PhotovoltaicUnit,
    },
    "5_燃料制备单元": {
        "Electrolyzer": ElectrolyzerUnit,
        "H2Storage": H2StorageUnit,
    },
    "6_电热转化单元": {
        "HeatPump": HeatPumpUnit,
        "ElectricChiller": ElectricChillerUnit,
    },
    "7_化学储能单元": {
        "BatteryStorage": BatteryStorageUnit,
        "ThermalStorage": ThermalStorageUnit,
    },
    "8_可再生供冷热单元": {
        "GroundSourceHeatPump": GroundSourceHeatPumpUnit,
        "SolarThermal": SolarThermalUnit,
    },
}


# =============================================================================
# 工具函数
# =============================================================================


def list_all_units():
    """列出所有可用的单元类型"""
    result = {}
    for category, units in UNIT_TYPES.items():
        result[category] = list(units.keys())
    return result


def get_unit_class(category: str, unit_name: str):
    """获取指定单元类"""
    return UNIT_TYPES.get(category, {}).get(unit_name)


def get_all_io_descriptions():
    """获取所有单元的输入输出描述"""
    descriptions = {}
    for category, units in UNIT_TYPES.items():
        descriptions[category] = {}
        for name, unit_class in units.items():
            if hasattr(unit_class, "get_io_description"):
                descriptions[category][name] = unit_class.get_io_description()
    return descriptions


def print_io_summary():
    """打印所有单元的输入输出摘要"""
    print("=" * 80)
    print("综合能源系统多能转化单元模块库 - 输入/输出列表")
    print("=" * 80)

    descriptions = get_all_io_descriptions()
    for category, units in descriptions.items():
        print(f"\n{'=' * 60}")
        print(f"【{category}】")
        print(f"{'=' * 60}")

        for name, desc in units.items():
            print(f"\n--- {desc['单元名称']} ({name}) ---")
            print(f"设备类型: {', '.join(desc['设备类型'])}")

            print("\n输入:")
            for input_name, input_info in desc["输入"].items():
                unit = input_info.get("单位", "-")
                bus = input_info.get("母线", "-")
                note = input_info.get("说明", "")
                print(f"  - {input_name}: [{unit}] (母线:{bus}) {note}")

            print("\n输出:")
            for output_name, output_info in desc["输出"].items():
                unit = output_info.get("单位", "-")
                bus = output_info.get("母线", "-")
                mode = output_info.get("模式", "")
                print(f"  - {output_name}: [{unit}] (母线:{bus}) {mode}")

            if "状态变量" in desc:
                print("\n状态变量:")
                for var_name, var_info in desc["状态变量"].items():
                    unit = var_info.get("单位", "-")
                    print(f"  - {var_name}: [{unit}]")

            print("\n关键参数:")
            for param_name, param_info in desc["关键参数"].items():
                if isinstance(param_info, dict):
                    typical = param_info.get("值", param_info.get("典型值", "-"))
                    range_val = param_info.get("范围", "-")
                    unit = param_info.get("单位", "")
                    print(f"  - {param_name}: 值={typical}, 范围={range_val} {unit}")
                else:
                    print(f"  - {param_name}: {param_info}")


# =============================================================================
# 示例：创建完整的综合能源系统
# =============================================================================


def create_example_energy_system():
    """
    创建示例综合能源系统

    演示如何使用模块库构建完整的能源系统模型
    """
    import oemof.solph as solph
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
    heat_bus = solph.Bus(label="heat bus")
    cool_bus = solph.Bus(label="cool bus")
    gas_bus = solph.Bus(label="gas bus")
    h2_bus = solph.Bus(label="hydrogen bus")

    energy_system.add(ele_bus, heat_bus, cool_bus, gas_bus, h2_bus)

    # 示例气象数据
    wind_speed = [5 + 3 * np.sin(2 * np.pi * t / 24) for t in range(time_step)]
    solar_radiation = [
        max(0, 800 * np.sin(np.pi * (t - 6) / 12)) for t in range(time_step)
    ]
    temperature = [15 + 10 * np.sin(2 * np.pi * (t - 6) / 24) for t in range(time_step)]

    # 1. 动力发电单元 - CHP (使用中芬项目参数)
    chp_unit = CHPUnit(CHPParams(label="CHP_unit"))
    chp = chp_unit.create_component(gas_bus, ele_bus, heat_bus)

    # 2. 余热利用单元 - 吸收式制冷机 (使用中芬项目参数)
    ac_unit = AbsorptionChillerUnit(AbsorptionChillerParams(label="AC_unit"))
    ac = ac_unit.create_component(heat_bus, ele_bus, cool_bus)

    # 3. 风力发电单元
    wt_unit = WindTurbineUnit(WindTurbineParams(label="WT_unit", nominal_power=500))
    wt_output = wt_unit.calc_output_curve(wind_speed)
    wt = wt_unit.create_component(ele_bus, wt_output)

    # 4. 光伏发电单元
    pv_unit = PhotovoltaicUnit(PhotovoltaicParams(label="PV_unit", nominal_power=500))
    pv_output = pv_unit.calc_output_curve(solar_radiation, temperature)
    pv = pv_unit.create_component(ele_bus, pv_output)

    # 5. 电解槽制氢
    electrolyzer_unit = ElectrolyzerUnit(ElectrolyzerParams(label="Electrolyzer_unit"))
    electrolyzer = electrolyzer_unit.create_component(ele_bus, h2_bus)

    # 6. 电热转化单元 - 电热泵 + 电制冷机 (使用中芬项目参数)
    hp_unit = HeatPumpUnit(HeatPumpParams(label="HP_unit"))
    hp = hp_unit.create_component(ele_bus, heat_bus)

    ec_unit = ElectricChillerUnit(ElectricChillerParams(label="EC_unit"))
    ec = ec_unit.create_component(ele_bus, cool_bus)

    # 7. 化学储能单元 - 蓄电池
    battery_unit = BatteryStorageUnit(BatteryStorageParams(label="Battery_unit"))
    battery = battery_unit.create_component(ele_bus)

    # 蓄热罐
    heat_storage_unit = ThermalStorageUnit(
        ThermalStorageParams(label="Heat_storage"), storage_type="heat"
    )
    heat_storage = heat_storage_unit.create_component(heat_bus)

    # 8. 光热集热器
    st_unit = SolarThermalUnit(SolarThermalParams(label="ST_unit"))
    st_output = st_unit.calc_output_curve(solar_radiation, temperature)
    st = st_unit.create_component(heat_bus, st_output)

    # 添加所有组件到系统
    energy_system.add(chp, ac, wt, pv, electrolyzer, hp, ec, battery, heat_storage, st)

    print("示例能源系统创建成功！")
    print(
        f"包含设备: CHP, 吸收式制冷机, 风机, 光伏, 电解槽, 热泵, 电制冷机, 蓄电池, 蓄热罐, 光热集热器"
    )

    return energy_system


# =============================================================================
# 导出列表
# =============================================================================

__all__ = [
    # 单元1
    "CHPUnit",
    "CHPParams",
    # 单元2
    "AbsorptionChillerUnit",
    "AbsorptionChillerParams",
    "WasteHeatBoilerUnit",
    "WasteHeatBoilerParams",
    # 单元3
    "WindTurbineUnit",
    "WindTurbineParams",
    # 单元4
    "PhotovoltaicUnit",
    "PhotovoltaicParams",
    # 单元5
    "ElectrolyzerUnit",
    "ElectrolyzerParams",
    "H2StorageUnit",
    "H2StorageParams",
    # 单元6
    "HeatPumpUnit",
    "HeatPumpParams",
    "ElectricChillerUnit",
    "ElectricChillerParams",
    # 单元7
    "BatteryStorageUnit",
    "BatteryStorageParams",
    "ThermalStorageUnit",
    "ThermalStorageParams",
    # 单元8
    "GroundSourceHeatPumpUnit",
    "GroundSourceHeatPumpParams",
    "SolarThermalUnit",
    "SolarThermalParams",
    # 工具函数
    "UNIT_TYPES",
    "list_all_units",
    "get_unit_class",
    "get_all_io_descriptions",
    "print_io_summary",
    "create_example_energy_system",
]


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == "__main__":
    # 打印所有单元的输入输出摘要
    print_io_summary()

    print("\n" + "=" * 80)
    print("创建示例能源系统...")
    print("=" * 80)

    # 创建示例系统
    es = create_example_energy_system()
