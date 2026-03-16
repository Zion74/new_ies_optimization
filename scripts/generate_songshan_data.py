# -*- coding: utf-8 -*-
"""
generate_songshan_data.py — 生成松山湖案例8760小时负荷数据
================================================================
基于松山湖PDF中的月度能量数据和东莞气候特征，合成全年逐时负荷数据。

数据来源：
  - 松山湖社区示范（一期）示范方案-0919.pdf 表4/表5
  - 东莞典型气象年数据（合成）

输出：
  - songshan_lake_data.csv  (8760×6)
  - songshan_lake_typical.xlsx (K-Medoids聚类结果)

用法：
  uv run python generate_songshan_data.py
"""

import sys
import io
import os
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
np.random.seed(42)


# ============================================================
# 1. 东莞气候数据合成（典型气象年）
# ============================================================

def generate_dongguan_climate(n_hours=8760):
    """
    合成东莞典型气象年数据

    东莞气候特征：
    - 亚热带季风气候，年均温 22.7°C
    - 夏季(6-9月) 28-33°C，冬季(12-2月) 10-18°C
    - 太阳辐射：年均 ~4.2 kWh/m²/day，夏季高冬季低
    - 风速：城区年均 1.5-2.5 m/s，较弱
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1  # 1-365
    hour_of_day = hours % 24

    # --- 温度模型 ---
    # 年周期：冬低夏高
    T_mean = 22.7
    T_amp_annual = 8.5  # 年振幅
    # 日周期：夜低昼高
    T_amp_daily = 4.0

    # 年周期相位：7月最热（day ~200）
    T_annual = T_mean + T_amp_annual * np.sin(2 * np.pi * (day_of_year - 105) / 365)
    # 日周期相位：14:00最热
    T_daily = T_amp_daily * np.sin(2 * np.pi * (hour_of_day - 8) / 24)
    # 随机扰动
    T_noise = np.random.normal(0, 1.5, n_hours)

    temperature = T_annual + T_daily + T_noise
    temperature = np.clip(temperature, 3.0, 38.0)

    # --- 太阳辐射模型 ---
    # 日出日落时间随季节变化（东莞纬度 ~23°N）
    declination = 23.45 * np.sin(2 * np.pi * (day_of_year - 81) / 365)
    latitude = 23.0
    # 简化：日照时间 ~11-13小时
    sunrise = 6.0 - 0.5 * np.sin(2 * np.pi * (day_of_year - 172) / 365)
    sunset = 18.5 + 0.5 * np.sin(2 * np.pi * (day_of_year - 172) / 365)

    # 晴天辐射包络
    solar_max_seasonal = 800 + 200 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    solar = np.zeros(n_hours)
    for i in range(n_hours):
        d = day_of_year[i]
        h = hour_of_day[i]
        sr = sunrise[i]
        ss = sunset[i]
        if sr < h < ss:
            # 正弦日变化
            frac = (h - sr) / (ss - sr)
            solar[i] = solar_max_seasonal[i] * np.sin(np.pi * frac)
        # 云量随机衰减（东莞多云多雨）
        cloud_factor = np.random.uniform(0.3, 1.0)
        solar[i] *= cloud_factor

    solar = np.clip(solar, 0, 1100)

    # --- 风速模型 ---
    # 东莞城区风速较低
    wind_mean = 2.0
    wind = np.random.weibull(2.0, n_hours) * wind_mean
    # 日变化：午后略大
    wind_daily = 0.5 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    wind = wind + wind_daily
    wind = np.clip(wind, 0.1, 8.0)

    return temperature, solar, wind


# ============================================================
# 2. 负荷数据合成
# ============================================================

# 松山湖PDF表4/表5 月度数据（万kW 或 万kWh）
MONTHLY_COOL_LOAD = {
    # 月份: 合计供冷量（万kW）
    1: 2.73, 2: 3.18, 3: 3.05, 4: 11.26,
    5: 20.49, 6: 35.74, 7: 49.34, 8: 47.83,
    9: 47.27, 10: 40.23, 11: 24.79, 12: 5.19,
}

MONTHLY_ELE_SUPPLY = {
    # 月份: 合计供电量（万kWh）
    1: 3.44, 2: 4.35, 3: 5.03, 4: 4.10,
    5: 8.08, 6: 8.71, 7: 8.70, 8: 7.16,
    9: 9.23, 10: 11.11, 11: 9.63, 12: 4.05,
}

# 年总电负荷 166.64万kWh，空调耗电97.05万kWh
# 非空调电负荷 ≈ 69.59万kWh（照明、办公、实验设备等）
ANNUAL_NON_AC_ELE = 69.59  # 万kWh
ANNUAL_TOTAL_ELE = 166.64  # 万kWh


def generate_load_profiles(temperature, n_hours=8760):
    """
    基于月度总量和温度生成逐时负荷曲线

    松山湖负荷特征：
    - 冷负荷主导（冷电比4.18），峰值5797kW
    - 电负荷：工作日8:00-19:00高，夜间低
    - 热负荷：以生活热水为主，全年较小
    - 运行时间：8:00-19:00
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24
    month = np.array([_day_to_month(d) for d in day_of_year])

    # ---- 冷负荷 ----
    cool_load = np.zeros(n_hours)
    for m in range(1, 13):
        mask = month == m
        n_hours_month = np.sum(mask)
        if n_hours_month == 0:
            continue

        total_cool_kwh = MONTHLY_COOL_LOAD[m] * 1e4  # 万kW → kW·h

        # 冷负荷日内分布：8:00-19:00有冷需求，与温度正相关
        hourly_weight = np.zeros(n_hours)
        for i in range(n_hours):
            if not mask[i]:
                continue
            h = hour_of_day[i]
            if 8 <= h <= 19:
                # 温度越高冷负荷越大
                T = max(temperature[i] - 18, 0)  # 18°C以上才有冷需求
                # 日内曲线：午后峰值
                time_factor = np.sin(np.pi * (h - 8) / 11) ** 0.8
                hourly_weight[i] = T * time_factor + 0.1
            else:
                hourly_weight[i] = 0.02  # 夜间极少量

        # 归一化到月度总量
        w_sum = np.sum(hourly_weight[mask])
        if w_sum > 0:
            cool_load[mask] = hourly_weight[mask] / w_sum * total_cool_kwh

    # 限幅到峰值
    cool_load = np.clip(cool_load, 0, 5800)

    # ---- 电负荷 ----
    ele_load = np.zeros(n_hours)

    # 非空调基础电负荷（照明、办公、实验设备）
    base_monthly = ANNUAL_NON_AC_ELE * 1e4 / 12  # 均匀分布到每月
    for m in range(1, 13):
        mask = month == m
        n_hours_month = np.sum(mask)
        if n_hours_month == 0:
            continue

        for i in range(n_hours):
            if not mask[i]:
                continue
            h = hour_of_day[i]
            # 工作时间高，夜间低
            if 8 <= h <= 19:
                ele_load[i] = base_monthly / n_hours_month * 2.2
            elif 7 <= h < 8 or 19 < h <= 22:
                ele_load[i] = base_monthly / n_hours_month * 1.2
            else:
                ele_load[i] = base_monthly / n_hours_month * 0.4

    # 空调耗电 ≈ 冷负荷 / 平均COP
    avg_cop = 3.2  # 综合COP（含溴化锂+电制冷+蓄冷）
    ac_ele = cool_load / avg_cop
    ele_load += ac_ele

    # 添加随机扰动
    ele_load *= (1 + np.random.normal(0, 0.05, n_hours))
    ele_load = np.clip(ele_load, 20, 3500)

    # ---- 热负荷 ----
    # 松山湖以生活热水为主，全年较小且平稳
    # 约1万人，人均热水 50L/天，ΔT=35°C → ~2000 kWh/天
    heat_load = np.zeros(n_hours)
    for i in range(n_hours):
        h = hour_of_day[i]
        m = month[i]
        # 热水需求：早晚高峰
        if 6 <= h <= 8:
            heat_load[i] = 120  # 早高峰
        elif 18 <= h <= 22:
            heat_load[i] = 150  # 晚高峰
        elif 8 < h < 18:
            heat_load[i] = 40   # 白天少量
        else:
            heat_load[i] = 20   # 深夜极少

        # 冬季热水需求略高
        seasonal_factor = 1.0 + 0.3 * np.cos(2 * np.pi * (m - 1) / 12)
        heat_load[i] *= seasonal_factor

    heat_load *= (1 + np.random.normal(0, 0.08, n_hours))
    heat_load = np.clip(heat_load, 5, 300)

    return ele_load, heat_load, cool_load


def _day_to_month(day_of_year):
    """将一年中的第几天转换为月份"""
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    cumulative = 0
    for m, d in enumerate(days_in_month, 1):
        cumulative += d
        if day_of_year <= cumulative:
            return m
    return 12


# ============================================================
# 3. 典型日聚类
# ============================================================

def run_clustering(data, n_clusters=14):
    """
    K-Medoids聚类提取典型日

    Parameters
    ----------
    data : pd.DataFrame
        8760×6 的负荷数据
    n_clusters : int
        典型日数量

    Returns
    -------
    pd.DataFrame
        典型日数据（typicalDayId, weight, days）
    """
    from sklearn_extra.cluster import KMedoids

    # 将8760小时数据重塑为365天×(24×6)特征
    n_features = data.shape[1]
    daily_data = data.values.reshape(365, 24 * n_features)

    # 标准化
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    daily_scaled = scaler.fit_transform(daily_data)

    # K-Medoids聚类
    kmedoids = KMedoids(n_clusters=n_clusters, random_state=42, method="pam")
    labels = kmedoids.fit_predict(daily_scaled)

    # 构建典型日表
    results = []
    for cluster_id in range(n_clusters):
        member_days = np.where(labels == cluster_id)[0] + 1  # 1-indexed
        medoid_idx = kmedoids.medoid_indices_[cluster_id]
        typical_day_id = medoid_idx + 1  # 1-indexed

        results.append({
            "typicalDayId": typical_day_id,
            "weight": len(member_days),
            "days": ",".join(map(str, member_days)),
        })

    df = pd.DataFrame(results)
    # 验证权重之和
    assert df["weight"].sum() == 365, f"权重之和={df['weight'].sum()}, 应为365"
    return df


def run_clustering_simple(data, n_clusters=14):
    """
    简化版聚类（不依赖sklearn_extra，使用scipy）
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    n_features = data.shape[1]
    daily_data = data.values.reshape(365, 24 * n_features)

    # 标准化
    mean = daily_data.mean(axis=0)
    std = daily_data.std(axis=0)
    std[std < 1e-6] = 1.0
    daily_scaled = (daily_data - mean) / std

    # 层次聚类
    Z = linkage(daily_scaled, method="ward")
    labels = fcluster(Z, t=n_clusters, criterion="maxclust") - 1  # 0-indexed

    # 找每个簇的medoid（距簇中心最近的点）
    results = []
    for cluster_id in range(n_clusters):
        member_indices = np.where(labels == cluster_id)[0]
        member_days = member_indices + 1  # 1-indexed

        # 找medoid
        cluster_data = daily_scaled[member_indices]
        centroid = cluster_data.mean(axis=0)
        dists = np.linalg.norm(cluster_data - centroid, axis=1)
        medoid_local = np.argmin(dists)
        typical_day_id = member_days[medoid_local]

        results.append({
            "typicalDayId": int(typical_day_id),
            "weight": len(member_days),
            "days": ",".join(map(str, member_days)),
        })

    df = pd.DataFrame(results)
    assert df["weight"].sum() == 365, f"权重之和={df['weight'].sum()}, 应为365"
    return df


# ============================================================
# 4. 主函数
# ============================================================

def main():
    print("=" * 60)
    print("  松山湖案例数据生成器")
    print("=" * 60)

    # 1. 生成气候数据
    print("\n[1/4] 生成东莞典型气象年数据...")
    temperature, solar, wind = generate_dongguan_climate()
    print(f"  温度: {temperature.min():.1f} ~ {temperature.max():.1f} °C, 均值 {temperature.mean():.1f} °C")
    print(f"  辐射: {solar.min():.0f} ~ {solar.max():.0f} W/m², 均值 {solar.mean():.0f} W/m²")
    print(f"  风速: {wind.min():.1f} ~ {wind.max():.1f} m/s, 均值 {wind.mean():.1f} m/s")

    # 2. 生成负荷数据
    print("\n[2/4] 生成负荷曲线...")
    ele_load, heat_load, cool_load = generate_load_profiles(temperature)
    print(f"  电负荷: {ele_load.min():.0f} ~ {ele_load.max():.0f} kW, 年总量 {ele_load.sum()/1e4:.1f} 万kWh")
    print(f"  热负荷: {heat_load.min():.0f} ~ {heat_load.max():.0f} kW, 年总量 {heat_load.sum()/1e4:.1f} 万kWh")
    print(f"  冷负荷: {cool_load.min():.0f} ~ {cool_load.max():.0f} kW, 年总量 {cool_load.sum()/1e4:.1f} 万kWh")
    print(f"  冷电比: {cool_load.sum() / ele_load.sum():.2f}")

    # 3. 保存CSV
    print("\n[3/4] 保存数据文件...")
    df = pd.DataFrame({
        "ele_load(kW)": ele_load,
        "heat_load(kW)": heat_load,
        "cool_load(kW)": cool_load,
        "solarRadiation(W/m-2)": solar,
        "windSpeed(m/s)": wind,
        "temperature(C)": temperature,
    })

    data_dir = os.path.join(os.path.dirname(BASE_DIR), "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, "songshan_lake_data.csv")
    df.to_csv(csv_path, index=False)
    print(f"  已保存: {csv_path}")
    print(f"  数据形状: {df.shape}")

    # 4. 典型日聚类
    print("\n[4/4] 运行典型日聚类 (14个典型日)...")
    try:
        typical_df = run_clustering(df, n_clusters=14)
        print("  使用 K-Medoids (PAM) 聚类")
    except ImportError:
        print("  sklearn_extra 不可用，使用层次聚类替代")
        typical_df = run_clustering_simple(df, n_clusters=14)

    xlsx_path = os.path.join(data_dir, "songshan_lake_typical.xlsx")
    typical_df.to_excel(xlsx_path, index=False)
    print(f"  已保存: {xlsx_path}")
    print(f"  典型日数量: {len(typical_df)}")
    print(f"  权重之和: {typical_df['weight'].sum()}")
    print(f"\n  典型日详情:")
    for _, row in typical_df.iterrows():
        print(f"    Day {row['typicalDayId']:3d}  权重={row['weight']:2d}  "
              f"代表 {row['weight']} 天")

    print("\n" + "=" * 60)
    print("  数据生成完成！")
    print(f"  负荷数据: songshan_lake_data.csv")
    print(f"  典型日:   songshan_lake_typical.xlsx")
    print("=" * 60)


if __name__ == "__main__":
    main()
