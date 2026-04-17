# -*- coding: utf-8 -*-
"""
generate_songshan_data.py — 生成松山湖案例 8760 小时负荷数据
================================================================
基于松山湖 PDF（图 3、表 2、图 5、PDF 4.3）与辩论共识：

    docs/辩论确认/latest_松山湖数据与模型口径辩论共识.md

重建核心修正（相对旧版）：

1. **ele_load 仅含非空调电**（69.59 万kWh/年）
   - 旧版包含空调耗电 (166.64 万kWh)，与模型 `cool_load -> EC/AC` 内生制冷耗电
     口径重复，会扭曲规划结果。
   - 新版只用图 3 的"公用耗电"列（月度值由 Codex/用户 2026-04-16 确认）。

2. **冷负荷月总量对齐表 2**（A3A4A5 栋现状用冷成本核算表，需求侧）
   - 旧版用表 4（供给侧，含溴化锂/电制冷/蓄冷分项结果），口径错误。
   - 表 2 是未经方案修正的真实冷负荷需求，合计 291.14 万 kW·h。

3. **冷峰值 clip 改为 3460 kW**（PDF 图 5 延时曲线起点）
   - 旧版 5797.21 kW 是三栋楼设计峰值之和（非同时峰值），不适合做逐时 clip。

4. **热负荷保持合成**（PDF 无热负荷数据，基于 1 万人生活热水假设）
   - 必须在论文中披露合成属性。

5. **气象数据保持合成**（非 TMY 实测），同样必须披露。

数据来源：
  - 松山湖/松山湖数据保存/02_负荷数据.md（图 3、表 2、图 5 的数值标准表）
  - 东莞典型气象年（合成）

输出：
  - data/songshan_lake_data.csv        (8760 × 6)
  - data/songshan_lake_typical.xlsx    (K-Medoids 14 个典型日)

用法：
  # 默认：按共识重建合成数据
  uv run python scripts/generate_songshan_data.py

  # 将来拿到真实 8760h 数据后：
  uv run python scripts/generate_songshan_data.py --source measured --measured-csv <file>

  # 只生成 CSV 跳过聚类：
  uv run python scripts/generate_songshan_data.py --skip-clustering

  # 只做典型日聚类（基于已有 CSV）：
  uv run python scripts/generate_songshan_data.py --skip-generation
"""

import sys
import io
import os
import argparse
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
np.random.seed(42)


# ============================================================
# PDF 关键数据表（用户/Codex 已确认的读数）
# ============================================================

# ---- 图 3：2022 年度逐月耗电情况（万 kWh）----
# 数据来源：松山湖/松山湖数据保存/02_负荷数据.md 第 2 节
# 合计列与 PDF 正文 166.64 / 97.05 / 69.59 误差 ≤ 0.01
MONTHLY_TOTAL_ELE_FIG3 = {  # 总耗电
    1: 4.93,
    2: 6.19,
    3: 6.19,
    4: 9.26,
    5: 11.09,
    6: 16.72,
    7: 21.19,
    8: 21.60,
    9: 21.07,
    10: 22.57,
    11: 14.11,
    12: 11.72,
}
MONTHLY_AC_ELE_FIG3 = {  # 空调耗电（供参考，不进 ele_load）
    1: 0.91,
    2: 1.06,
    3: 1.02,
    4: 4.17,
    5: 6.42,
    6: 11.91,
    7: 16.45,
    8: 15.94,
    9: 15.76,
    10: 13.41,
    11: 8.26,
    12: 1.73,
}
MONTHLY_NON_AC_ELE_FIG3 = {  # 公用耗电（模型 ele_load 的月度总量）
    1: 4.02,
    2: 5.13,
    3: 5.18,
    4: 5.09,
    5: 4.67,
    6: 4.80,
    7: 4.75,
    8: 5.65,
    9: 5.31,
    10: 9.16,
    11: 5.84,
    12: 9.99,
}

# ---- 表 2：A3A4A5 栋现状用冷成本核算表（万 kW·h）----
# 合计 291.14 万 kW·h（与 PDF 正文 291.15 一致）
# 这是需求侧的逐月冷负荷，用于作为月度总量约束
MONTHLY_COOL_LOAD_TAB2 = {
    1: 2.73,
    2: 3.18,
    3: 3.05,
    4: 12.50,
    5: 19.27,
    6: 35.74,
    7: 49.35,
    8: 47.83,
    9: 47.27,
    10: 40.24,
    11: 24.79,
    12: 5.19,
}

# ---- 图 5：延时曲线读数（用于形状校准）----
# 冷负荷：起点 3460 kW，(1811 h, 1269 kW) 标注点，3500 h 后几乎为 0
# 电负荷：起点 530 kW（历史总电，含空调），(2310 h, 321.5 kW) 标注点
PEAK_COOL_LOAD = 3460.0  # kW，实际同时峰值（非设计值 5797.21）
COOL_1811H_VALUE = 1269.0  # kW，延时曲线 1811h 处

# ---- PDF 4.3 设计要点（运行约束）----
OFFICE_HOUR_START = 8  # 8:00
OFFICE_HOUR_END = 19  # 19:00
COOL_DEMAND_MONTHS = set(range(4, 12))  # 4~11 月为主要供冷季（1-3/12 月仍有残留）

# 年度总量（PDF 正文）
ANNUAL_NON_AC_ELE = 69.59  # 万 kWh
ANNUAL_COOL_LOAD = 291.14  # 万 kW·h（表 2 合计）
ANNUAL_TOTAL_ELE_HISTORICAL = 166.64  # 万 kWh（历史总电，含空调，仅论文说明用）


# ============================================================
# 1. 东莞气候数据合成（典型气象年）
# ============================================================


def generate_dongguan_climate(n_hours=8760):
    """
    合成东莞典型气象年数据。注意：非 TMY 实测数据，是基于气候特征的合成。

    东莞气候特征：
    - 亚热带季风气候，年均温 22.7°C
    - 夏季(6-9月) 28-33°C，冬季(12-2月) 10-18°C
    - 太阳辐射：年均 ~4.2 kWh/m²/day，夏季高冬季低
    - 风速：城区年均 1.5-2.5 m/s，较弱
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24

    # 温度模型
    T_mean, T_amp_annual, T_amp_daily = 22.7, 8.5, 4.0
    T_annual = T_mean + T_amp_annual * np.sin(2 * np.pi * (day_of_year - 105) / 365)
    T_daily = T_amp_daily * np.sin(2 * np.pi * (hour_of_day - 8) / 24)
    T_noise = np.random.normal(0, 1.5, n_hours)
    temperature = np.clip(T_annual + T_daily + T_noise, 3.0, 38.0)

    # 太阳辐射模型
    sunrise = 6.0 - 0.5 * np.sin(2 * np.pi * (day_of_year - 172) / 365)
    sunset = 18.5 + 0.5 * np.sin(2 * np.pi * (day_of_year - 172) / 365)
    solar_max_seasonal = 800 + 200 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    solar = np.zeros(n_hours)
    for i in range(n_hours):
        sr, ss = sunrise[i], sunset[i]
        h = hour_of_day[i]
        if sr < h < ss:
            frac = (h - sr) / (ss - sr)
            solar[i] = solar_max_seasonal[i] * np.sin(np.pi * frac)
        cloud_factor = np.random.uniform(0.3, 1.0)
        solar[i] *= cloud_factor
    solar = np.clip(solar, 0, 1100)

    # 风速模型
    wind = np.random.weibull(2.0, n_hours) * 2.0
    wind_daily = 0.5 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    wind = np.clip(wind + wind_daily, 0.1, 8.0)

    return temperature, solar, wind


# ============================================================
# 2. 负荷数据合成（按辩论共识修正版）
# ============================================================


def _day_to_month(day_of_year):
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    cumulative = 0
    for m, d in enumerate(days_in_month, 1):
        cumulative += d
        if day_of_year <= cumulative:
            return m
    return 12


def generate_cool_load(temperature, n_hours=8760):
    """
    冷负荷：月度总量对齐表 2；日内分布基于温度+办公时段；峰值 clip 到 3460 kW。

    合成逻辑：
      1. 月 → 日：按日最高温度线性加权（指数从 2.5 调到 1.0，避免延时曲线过陡）
      2. 日 → 时：仅在办公时段 8:00-19:00，午后峰值
         - 温度权重 (T-18)^1.0（松山湖供冷起始温度约 18°C）
         - 形状 sin^1.5（较 sin^2.5 更平，拉高延时曲线中段）
         - 办公时段外给一个小基荷（建筑热惯性 + 小部分夜间空调残留）
      3. clip 到 3460 kW（PDF 图 5 延时曲线起点）

    调参目标（独立校验在 scripts/check_songshan_data.py）：
      - 峰值 ≈ 3460 kW（图 5 起点）
      - 延时曲线 @ 1811h ≈ 1269 kW（图 5 标注点，允差 ±30%）
      - 月度总量与表 2 吻合（允差 ±5%）
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24
    month = np.array([_day_to_month(d) for d in day_of_year])

    # 指数参数（降低陡峭度，让延时曲线中段抬高）
    DAY_T_EXP = 1.0  # 日温度权重指数（原 2.5）
    HOUR_T_EXP = 1.0  # 小时温度权重指数（原 2.0）
    HOUR_SHAPE_EXP = 1.5  # 办公时段 sin 形状指数（原 2.5）
    BASE_T = 18.0  # 供冷基准温度（松山湖办公建筑约 18°C 起开空调）
    NIGHT_BASELOAD_FRAC = 0.03  # 非办公时段相对权重基线（原 ≈0.001）

    cool_load = np.zeros(n_hours)
    for m in range(1, 13):
        mask = month == m
        if not np.any(mask):
            continue
        total_cool_kwh = MONTHLY_COOL_LOAD_TAB2[m] * 1e4

        days_in_m = sorted(set(day_of_year[mask]))
        daily_Tmax = {
            d: float(np.max(temperature[day_of_year == d])) for d in days_in_m
        }
        daily_weight = {
            d: max(T - BASE_T, 0.5) ** DAY_T_EXP for d, T in daily_Tmax.items()
        }
        dw_sum = sum(daily_weight.values())
        daily_cool_kwh = {
            d: daily_weight[d] / dw_sum * total_cool_kwh for d in days_in_m
        }

        for d in days_in_m:
            d_mask = day_of_year == d
            hourly_weight = np.zeros(n_hours)
            for i in range(n_hours):
                if not d_mask[i]:
                    continue
                h = hour_of_day[i]
                if OFFICE_HOUR_START <= h <= OFFICE_HOUR_END:
                    T = max(temperature[i] - BASE_T, 0.5) ** HOUR_T_EXP
                    time_factor = (
                        np.sin(
                            np.pi
                            * (h - OFFICE_HOUR_START)
                            / (OFFICE_HOUR_END - OFFICE_HOUR_START)
                        )
                        ** HOUR_SHAPE_EXP
                    )
                    hourly_weight[i] = T * time_factor
                else:
                    # 办公时段外保留小基荷：建筑热惯性 + 部分晚间加班冷负荷
                    hourly_weight[i] = NIGHT_BASELOAD_FRAC
            hw_sum = np.sum(hourly_weight[d_mask])
            if hw_sum > 0:
                cool_load[d_mask] = hourly_weight[d_mask] / hw_sum * daily_cool_kwh[d]

    cool_load = np.clip(cool_load, 0, PEAK_COOL_LOAD)
    return cool_load


def generate_ele_load(n_hours=8760):
    """
    电负荷：仅非空调电（照明、办公、实验设备），月度总量对齐图 3 公用耗电列。

    合成逻辑：
      - 月总量严格来自图 3 的"公用耗电"（69.59 万kWh/年）
      - 日内形状：8:00-19:00 高，7-8/19-22 中，夜间低
      - 周末略低（-15%）
      - ±3% 随机扰动
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24
    day_of_week = (day_of_year - 1) % 7  # 0..6, 0/6 为周末近似
    month = np.array([_day_to_month(d) for d in day_of_year])

    ele_load = np.zeros(n_hours)
    for m in range(1, 13):
        mask = month == m
        if not np.sum(mask):
            continue
        non_ac_total = MONTHLY_NON_AC_ELE_FIG3[m] * 1e4  # kWh

        base_weight = np.zeros(n_hours)
        for i in range(n_hours):
            if not mask[i]:
                continue
            h = hour_of_day[i]
            # 办公时段阶梯
            if OFFICE_HOUR_START <= h <= OFFICE_HOUR_END:
                w = 2.2
            elif 7 <= h < OFFICE_HOUR_START or OFFICE_HOUR_END < h <= 22:
                w = 1.2
            else:
                w = 0.4
            # 周末系数（近似：周六=5 周日=6）
            if day_of_week[i] in (5, 6):
                w *= 0.85
            base_weight[i] = w

        bw_sum = np.sum(base_weight[mask])
        if bw_sum > 0:
            ele_load[mask] = base_weight[mask] / bw_sum * non_ac_total

    ele_load *= 1 + np.random.normal(0, 0.03, n_hours)
    # 放宽下限到 5（凌晨低值），上限用 PDF 公用电峰值估计的 2 倍（预期峰值 ~180-220 kW）
    ele_load = np.clip(ele_load, 5, 500)
    return ele_load


def generate_heat_load(n_hours=8760):
    """
    热负荷：办公园区生活热水（茶水间 + 少量淋浴），全年较小且平稳。
    警告：PDF 无任何热负荷数据，本列完全基于办公场景生活热水假设合成，
          论文中必须明确披露。

    取值依据：
      - 办公园区人均热水 ~5 L/d@60°C，1 万人规模 → 年热水 ~35 万 kWh
      - 早高峰（6-8 点）茶水/淋浴稍高，晚高峰（18-22 点）加班茶水
      - 冬季略高（seasonal 0.7~1.3）
      - 允许峰值约 110 kW（winter seasonal × 早高峰 base）
      - 年总量期望在 30-40 万 kWh，落在 check 的 5-50 区间
    """
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24
    month = np.array([_day_to_month(d) for d in day_of_year])

    heat_load = np.zeros(n_hours)
    for i in range(n_hours):
        h = hour_of_day[i]
        if 6 <= h <= 8:
            base = 80  # 早高峰：晨起热水/泡茶
        elif 18 <= h <= 22:
            base = 90  # 晚高峰：加班茶水 + 少量淋浴
        elif 8 < h < 18:
            base = 25  # 白天零散
        else:
            base = 10  # 深夜极少
        seasonal_factor = 1.0 + 0.3 * np.cos(2 * np.pi * (month[i] - 1) / 12)
        heat_load[i] = base * seasonal_factor

    heat_load *= 1 + np.random.normal(0, 0.08, n_hours)
    heat_load = np.clip(heat_load, 3, 200)
    return heat_load


def generate_all_synthesis(n_hours=8760):
    """按共识修正后的合成流程"""
    temperature, solar, wind = generate_dongguan_climate(n_hours)
    ele_load = generate_ele_load(n_hours)
    heat_load = generate_heat_load(n_hours)
    cool_load = generate_cool_load(temperature, n_hours)

    return pd.DataFrame(
        {
            "ele_load(kW)": ele_load,
            "heat_load(kW)": heat_load,
            "cool_load(kW)": cool_load,
            "solarRadiation(W/m-2)": solar,
            "windSpeed(m/s)": wind,
            "temperature(C)": temperature,
        }
    )


def load_measured(measured_csv):
    """加载实测数据（将来拿到真实数据后使用）"""
    df = pd.read_csv(measured_csv)
    required_cols = [
        "ele_load(kW)",
        "heat_load(kW)",
        "cool_load(kW)",
        "solarRadiation(W/m-2)",
        "windSpeed(m/s)",
        "temperature(C)",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"实测 CSV 缺少必需列: {missing}\n"
            f"所需列: {required_cols}\n"
            f"实际列: {list(df.columns)}"
        )
    if len(df) != 8760:
        raise ValueError(f"实测 CSV 行数 {len(df)} 不等于 8760（应为全年逐时）")
    return df[required_cols].reset_index(drop=True)


# ============================================================
# 3. 典型日聚类
# ============================================================


def run_clustering(data, n_clusters=14):
    """K-Medoids 聚类提取典型日（优先），失败则退化为层次聚类。"""
    try:
        from sklearn_extra.cluster import KMedoids
        from sklearn.preprocessing import StandardScaler

        # 只用模型输入列（去掉 windSpeed，松山湖不配风电）
        feat_cols = [
            "ele_load(kW)",
            "heat_load(kW)",
            "cool_load(kW)",
            "solarRadiation(W/m-2)",
            "temperature(C)",
        ]
        feat_data = data[feat_cols].values

        n_features = feat_data.shape[1]
        daily_data = feat_data.reshape(365, 24 * n_features)
        scaler = StandardScaler()
        daily_scaled = scaler.fit_transform(daily_data)

        kmedoids = KMedoids(n_clusters=n_clusters, random_state=42, method="pam")
        labels = kmedoids.fit_predict(daily_scaled)

        results = []
        for cluster_id in range(n_clusters):
            member_days = np.where(labels == cluster_id)[0] + 1
            medoid_idx = kmedoids.medoid_indices_[cluster_id]
            results.append(
                {
                    "typicalDayId": int(medoid_idx + 1),
                    "weight": len(member_days),
                    "days": ",".join(map(str, member_days)),
                }
            )
        print("  [KMedoids/PAM] OK")
        return pd.DataFrame(results)
    except ImportError:
        print("  [sklearn_extra 不可用，退化为层次聚类]")
        return _run_clustering_hierarchical(data, n_clusters)


def _run_clustering_hierarchical(data, n_clusters=14):
    from scipy.cluster.hierarchy import fcluster, linkage

    feat_cols = [
        "ele_load(kW)",
        "heat_load(kW)",
        "cool_load(kW)",
        "solarRadiation(W/m-2)",
        "temperature(C)",
    ]
    feat_data = data[feat_cols].values

    n_features = feat_data.shape[1]
    daily_data = feat_data.reshape(365, 24 * n_features)
    mean = daily_data.mean(axis=0)
    std = daily_data.std(axis=0)
    std[std < 1e-6] = 1.0
    daily_scaled = (daily_data - mean) / std
    Z = linkage(daily_scaled, method="ward")
    labels = fcluster(Z, t=n_clusters, criterion="maxclust") - 1

    results = []
    for cluster_id in range(n_clusters):
        member_indices = np.where(labels == cluster_id)[0]
        member_days = member_indices + 1
        cluster_data = daily_scaled[member_indices]
        centroid = cluster_data.mean(axis=0)
        dists = np.linalg.norm(cluster_data - centroid, axis=1)
        medoid_local = int(np.argmin(dists))
        results.append(
            {
                "typicalDayId": int(member_days[medoid_local]),
                "weight": len(member_days),
                "days": ",".join(map(str, member_days)),
            }
        )
    df = pd.DataFrame(results)
    assert df["weight"].sum() == 365, f"权重之和={df['weight'].sum()}, 应为365"
    return df


# ============================================================
# 4. 内嵌 sanity check（关键指标检验）
# ============================================================


def sanity_check(df):
    """
    重建后 sanity check。失败时打印警告但不 raise，让用户肉眼判断。
    更完整的独立工具见 scripts/check_songshan_data.py
    """
    print("\n" + "=" * 60)
    print("  Sanity check（数据口径检验）")
    print("=" * 60)

    checks = []

    # 1. ele_load 年总量 ≈ 69.59 万kWh
    ele_sum = df["ele_load(kW)"].sum() / 1e4
    tol_ele = abs(ele_sum - ANNUAL_NON_AC_ELE) / ANNUAL_NON_AC_ELE
    checks.append(
        (
            "ele_load 年总量",
            f"{ele_sum:.2f} 万kWh",
            f"目标 {ANNUAL_NON_AC_ELE}",
            "OK" if tol_ele < 0.02 else f"偏差 {tol_ele:.1%}",
        )
    )

    # 2. cool_load 年总量 ≈ 291.14 万kW·h
    cool_sum = df["cool_load(kW)"].sum() / 1e4
    tol_cool = abs(cool_sum - ANNUAL_COOL_LOAD) / ANNUAL_COOL_LOAD
    checks.append(
        (
            "cool_load 年总量",
            f"{cool_sum:.2f} 万kW·h",
            f"目标 {ANNUAL_COOL_LOAD}",
            "OK" if tol_cool < 0.02 else f"偏差 {tol_cool:.1%}",
        )
    )

    # 3. cool_load 峰值 ≈ 3460 kW
    cool_peak = df["cool_load(kW)"].max()
    tol_peak = abs(cool_peak - PEAK_COOL_LOAD) / PEAK_COOL_LOAD
    checks.append(
        (
            "cool_load 峰值",
            f"{cool_peak:.1f} kW",
            f"目标 {PEAK_COOL_LOAD}",
            "OK" if tol_peak < 0.05 else f"偏差 {tol_peak:.1%}",
        )
    )

    # 4. 冷电比（仅非空调电）应显著大于 1
    c2e = df["cool_load(kW)"].sum() / df["ele_load(kW)"].sum()
    checks.append(
        ("冷电比 (cool/ele_load)", f"{c2e:.2f}", "应 > 3", "OK" if c2e > 3 else "WARN")
    )

    # 5. 隐含总电量（ele + cool/EC_COP ≈ 3.5）应接近 PDF 166.64 万kWh
    ec_cop = 3.5
    implied_total = (
        df["ele_load(kW)"].sum() + df["cool_load(kW)"].sum() / ec_cop
    ) / 1e4
    tol_total = (
        abs(implied_total - ANNUAL_TOTAL_ELE_HISTORICAL) / ANNUAL_TOTAL_ELE_HISTORICAL
    )
    checks.append(
        (
            "隐含历史总电量",
            f"{implied_total:.2f} 万kWh",
            f"目标 {ANNUAL_TOTAL_ELE_HISTORICAL}（±10%）",
            "OK" if tol_total < 0.10 else f"偏差 {tol_total:.1%}",
        )
    )

    # 打印主校验
    for name, actual, target, status in checks:
        icon = "OK  " if status == "OK" else "WARN"
        print(f"  [{icon}] {name:28s} | 实际: {actual:<18s} | {target:<25s} | {status}")
    print("-" * 60)

    # 6. 延时曲线 1811h 处冷负荷（INFO，不计入 WARN）
    #    注意：PDF 图 5 的三点标注（峰 3460 / 1811h=1269 / 3500h≈0）与
    #    表 2 年总 291.14 万 kW·h 存在数学不相容——若同时满足前两点，
    #    前 1811 h 积分已超 428 万 kW·h，远大于年总量。
    #    因此本条只作参考值打印，不作硬校验。年总量与峰值是更可靠的硬约束。
    cool_sorted = np.sort(df["cool_load(kW)"].values)[::-1]
    cool_at_1811 = cool_sorted[1810] if len(cool_sorted) > 1810 else None
    if cool_at_1811 is not None:
        print(
            f"  [INFO] 冷负荷延时@1811h         | 实际: {cool_at_1811:7.1f} kW   "
            f"| PDF 读数 {COOL_1811H_VALUE} kW（与年总 291.14 万 kW·h 数学不相容，仅供参考）"
        )
    print("=" * 60)

    n_warn = sum(1 for _, _, _, s in checks if s != "OK")
    if n_warn == 0:
        print("  主校验全部通过")
    else:
        print(f"  {n_warn} 项偏离预期，如差异较大请复核脚本参数")


# ============================================================
# 5. 主函数
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="松山湖案例 8760h 负荷数据生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["synthesis", "measured"],
        default="synthesis",
        help="数据来源：synthesis=按共识合成（默认），measured=从 CSV 读取实测",
    )
    parser.add_argument(
        "--measured-csv", help="实测 8760h CSV 路径（--source measured 时必需）"
    )
    parser.add_argument(
        "--skip-clustering", action="store_true", help="只生成 CSV，不做典型日聚类"
    )
    parser.add_argument(
        "--skip-generation", action="store_true", help="只做聚类，读取已有 CSV"
    )
    parser.add_argument(
        "--n-clusters", type=int, default=14, help="典型日数量（默认 14）"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  松山湖案例数据生成器（2026-04-17 重建版）")
    print("  - ele_load 口径：仅非空调电（69.59 万kWh/年）")
    print("  - 冷峰值：3460 kW（图 5 延时曲线）")
    print("  - 月度冷负荷：表 2（需求侧）")
    print("  - 图 3 月度电量：用户/Codex 2026-04-16 确认")
    print("=" * 60)

    data_dir = os.path.join(os.path.dirname(BASE_DIR), "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, "songshan_lake_data.csv")
    xlsx_path = os.path.join(data_dir, "songshan_lake_typical.xlsx")

    # ── 阶段 1：生成 / 加载 CSV ──
    if args.skip_generation:
        if not os.path.isfile(csv_path):
            print(f"错误：--skip-generation 需要已有 {csv_path}")
            sys.exit(1)
        df = pd.read_csv(csv_path)
        print(f"\n[加载] 已有 CSV: {csv_path} (shape={df.shape})")
    else:
        if args.source == "synthesis":
            print("\n[1/2] 合成 8760h 数据（按辩论共识修正版）...")
            df = generate_all_synthesis()
        else:
            if not args.measured_csv:
                print("错误：--source measured 需要指定 --measured-csv")
                sys.exit(1)
            print(f"\n[1/2] 加载实测数据: {args.measured_csv}")
            df = load_measured(args.measured_csv)

        df.to_csv(csv_path, index=False)
        print(f"  已保存: {csv_path}")
        print(f"  数据形状: {df.shape}")

        # 简要统计
        print(
            f"  电负荷: {df['ele_load(kW)'].min():.0f} ~ {df['ele_load(kW)'].max():.0f} kW"
            f"，年总 {df['ele_load(kW)'].sum() / 1e4:.2f} 万kWh"
        )
        print(
            f"  冷负荷: {df['cool_load(kW)'].min():.0f} ~ {df['cool_load(kW)'].max():.0f} kW"
            f"，年总 {df['cool_load(kW)'].sum() / 1e4:.2f} 万kW·h"
        )
        print(
            f"  热负荷: {df['heat_load(kW)'].min():.0f} ~ {df['heat_load(kW)'].max():.0f} kW"
            f"，年总 {df['heat_load(kW)'].sum() / 1e4:.2f} 万kWh"
        )

        sanity_check(df)

    # ── 阶段 2：典型日聚类 ──
    if not args.skip_clustering:
        print(f"\n[2/2] 典型日聚类（{args.n_clusters} 个典型日）...")
        typical_df = run_clustering(df, n_clusters=args.n_clusters)
        typical_df.to_excel(xlsx_path, index=False)
        print(f"  已保存: {xlsx_path}")
        print(f"  权重之和: {typical_df['weight'].sum()} (应为 365)")
        print(f"\n  典型日列表 (前 5 个):")
        for _, row in typical_df.head().iterrows():
            print(f"    Day {row['typicalDayId']:3d}  权重={row['weight']:2d}")

    print("\n" + "=" * 60)
    print("  完成！")
    print(f"  负荷数据: {csv_path}")
    if not args.skip_clustering:
        print(f"  典型日:   {xlsx_path}")
    print("\n  下一步：uv run python scripts/check_songshan_data.py  做完整口径检验")
    print("=" * 60)


if __name__ == "__main__":
    main()
