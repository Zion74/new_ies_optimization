# -*- coding: utf-8 -*-
"""
测试 HeatEleModel 类 - 分布式电热综合能源系统调度模型
"""

import numpy as np
import pandas as pd
from operation import HeatEleModel


def generate_test_data(time_step=24):
    """
    生成测试数据
    """
    # 电负荷曲线（典型日负荷曲线，单位：kW）
    ele_load_base = np.array([
        600, 580, 550, 520, 500, 520, 600, 800,
        1000, 1100, 1150, 1100, 1050, 1000, 1050, 1100,
        1200, 1300, 1200, 1100, 1000, 900, 800, 700
    ])
    ele_load = ele_load_base[:time_step].tolist()
    
    # 热负荷曲线（单位：kW）
    heat_load_base = np.array([
        400, 380, 350, 320, 300, 350, 450, 500,
        550, 500, 450, 400, 400, 450, 500, 550,
        600, 650, 600, 550, 500, 480, 450, 420
    ])
    heat_load = heat_load_base[:time_step].tolist()
    
    # 太阳辐射曲线（W/m²）
    solar_radiation = np.array([
        0, 0, 0, 0, 0, 50, 200, 400,
        600, 750, 850, 900, 900, 850, 750, 600,
        400, 200, 50, 0, 0, 0, 0, 0
    ])[:time_step]
    
    # 风速曲线（m/s）
    wind_speed = np.array([
        5, 5.5, 6, 6.5, 7, 6.5, 5.5, 4.5,
        4, 3.5, 3, 3.5, 4, 4.5, 5, 5.5,
        6, 6.5, 7, 7.5, 7, 6.5, 6, 5.5
    ])[:time_step]
    
    # 环境温度曲线（°C）
    temperature = np.array([
        15, 14, 13, 12, 12, 13, 15, 18,
        21, 24, 26, 28, 29, 29, 28, 27,
        25, 23, 21, 19, 18, 17, 16, 15
    ])[:time_step]
    
    return ele_load, heat_load, solar_radiation, wind_speed, temperature


def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    """计算光伏出力"""
    return [
        ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
        for r, t in zip(solar_radiation_list, temperature_list)
    ]


def cal_wind_output(wind_speed_list, pwt):
    """计算风电出力"""
    ret = [0 for _ in range(len(wind_speed_list))]
    for i in range(len(wind_speed_list)):
        w = wind_speed_list[i]
        if 2.5 <= w < 9:
            ret[i] = (w**3 - 2.5**3) / (9**3 - 2.5**3) * pwt
        elif 9 <= w < 25:
            ret[i] = pwt
    return ret


def test_heat_ele_model():
    """
    测试 HeatEleModel 类
    """
    print("=" * 60)
    print("测试 HeatEleModel - 分布式电热综合能源系统")
    print("=" * 60)
    
    # 生成测试数据
    time_step = 24
    ele_load, heat_load, solar_radiation, wind_speed, temperature = generate_test_data(time_step)
    
    # 设备容量配置
    ppv = 2000  # 光伏容量 (kW)
    pwt = 1500  # 风电容量 (kW)
    pgt = 800   # 燃气轮机CHP容量 (kW)
    php = 500   # 电热泵容量 (kW)
    pes = 1000  # 电储能功率 (kW)
    phs = 500   # 热储能功率 (kW)
    
    # 计算可再生能源出力
    pv_output = cal_solar_output(solar_radiation, temperature, ppv)
    wt_output = cal_wind_output(wind_speed, pwt)
    
    # 价格设置
    ele_price = [0.6] * time_step  # 电价 (元/kWh)
    gas_price = [0.3] * time_step  # 气价 (元/kWh)
    
    print("\n【1】系统配置:")
    print(f"  光伏容量: {ppv} kW")
    print(f"  风电容量: {pwt} kW")
    print(f"  燃气轮机CHP: {pgt} kW")
    print(f"  电热泵: {php} kW")
    print(f"  电储能: {pes} kW")
    print(f"  热储能: {phs} kW")
    
    print("\n【2】负荷情况:")
    print(f"  电负荷峰值: {max(ele_load):.1f} kW")
    print(f"  电负荷谷值: {min(ele_load):.1f} kW")
    print(f"  热负荷峰值: {max(heat_load):.1f} kW")
    print(f"  热负荷谷值: {min(heat_load):.1f} kW")
    
    print("\n【3】可再生能源出力:")
    print(f"  光伏峰值出力: {max(pv_output):.1f} kW")
    print(f"  风电峰值出力: {max(wt_output):.1f} kW")
    
    # 创建模型并优化
    print("\n【4】创建并优化模型...")
    model = HeatEleModel(
        local_time="01/01/2024",
        time_step=time_step,
        ele_price=ele_price,
        gas_price=gas_price,
        ele_load=ele_load,
        heat_demand=heat_load,
        wt_output=wt_output,
        pv_output=pv_output,
        gt_capacity=pgt,
        ehp_capacity=php,
        ele_storage_io=pes,
        heat_storage_io=phs,
    )
    
    try:
        model.optimise()
        print("  优化成功!")
        
        # 获取结果
        obj_value = model.get_objective_value()
        print(f"\n【5】优化结果:")
        print(f"  运行成本: {obj_value:.2f} 元")
        
        # 计算源荷匹配度（多种方法）
        print(f"\n【6】源荷匹配度计算:")
        
        slmd_pearson = model.calc_source_load_matching_pearson()
        print(f"  基于Pearson相关系数: {slmd_pearson:.4f}")
        print(f"    (越接近1表示源荷匹配度越好)")
        
        slmd_std = model.calc_source_load_matching_std()
        print(f"  基于净负荷标准差: {slmd_std:.4f}")
        print(f"    (越小表示系统波动越小)")
        
        slmd_ltpr = model.calc_source_load_matching_ltpr()
        print(f"  基于负荷跟踪偏差率: {slmd_ltpr:.4f}")
        print(f"    (越接近1表示跟踪性能越好)")
        
        # 获取详细结果
        comp_results = model.get_complementary_results()
        print(f"\n【7】能量平衡结果:")
        print(f"  电网购电总量: {sum(comp_results['grid']):.2f} kWh")
        print(f"  弃电总量: {sum(comp_results['electricity overflow']):.2f} kWh")
        print(f"  补充热源总量: {sum(comp_results['heat source']):.2f} kWh")
        print(f"  弃热总量: {sum(comp_results['heat overflow']):.2f} kWh")
        
        # 绘制结果图
        print(f"\n【8】生成结果图...")
        model.result_process("electricity bus", save_path="test_ele_bus_result.png")
        model.result_process("heat bus", save_path="test_heat_bus_result.png")
        
        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"  优化失败: {e}")
        return False


if __name__ == "__main__":
    test_heat_ele_model()

