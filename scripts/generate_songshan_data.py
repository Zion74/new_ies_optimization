# -*- coding: utf-8 -*-
"""
generate_songshan_data.py — 生成松山湖案例 8760 小时负荷数据（v3 XLS 源版）
================================================================================

数据来源（优先级递减）：
  1. 松山湖/松山湖社区方案-0901.xls  — 项目方提供的源数据
     - Sheet 1 "负荷数据"：逐月精确总量（空调/公用/冷负荷）
     - Sheet 3 "社区负荷分布"：12月×24h 工作日冷负荷典型日 + 工作日天数
     - Sheet 4 "社区电负荷分布"：12月×24h 工作日公用电负荷典型日
     - Sheet 2 "光伏发电量"：逐月发电量 + 典型日逐时曲线
  2. 东莞气候合成模型 — 温度/风速（无实测 TMY）
  3. 办公场景假设 — 热负荷（PDF 无数据）

口径规则（辩论共识 2026-04-16）：
  - ele_load = 仅非空调公用电（69.59 万kWh/年），制冷耗电由模型内生
  - cool_load = 需求侧冷负荷（291.15 万kWh/年），来自 XLS 表C
  - 冷负荷峰值 clip ≈ 3460 kW（图5 延时曲线起点，非设计值 5797）
  - 热负荷/气象为合成数据，论文中必须披露

输出：
  - data/songshan_lake_data.csv        (8760 × 6)
  - data/songshan_lake_typical.xlsx    (K-Medoids 14 个典型日)

用法：
  uv run python scripts/generate_songshan_data.py
  uv run python scripts/generate_songshan_data.py --skip-clustering
  uv run python scripts/generate_songshan_data.py --skip-generation
"""

import sys
import io
import os
import argparse
import datetime
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
np.random.seed(42)

# XLS 文件路径
XLS_PATH = os.path.join(PROJECT_DIR, "松山湖", "松山湖社区方案-0901.xls")

# 年度基准数（用于 sanity check）
ANNUAL_NON_AC_ELE = 69.59   # 万kWh
ANNUAL_COOL_LOAD = 291.15   # 万kWh
PEAK_COOL_LOAD = 3460.0     # kW（图5 延时曲线起点）

# 2022 年日历（数据基准年）
YEAR = 2022
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


# ============================================================
# 1. 从 XLS 提取源数据
# ============================================================

def load_xls_data(xls_path):
    """从项目方 XLS 提取所有源数据，返回字典"""
    xls = pd.ExcelFile(xls_path)

    # --- Sheet 1: 月度总量 ---
    df1 = pd.read_excel(xls, sheet_name="负荷数据", header=None)
    monthly_cool = {}      # 冷负荷月总量 (万kWh)
    monthly_pub_ele = {}   # 公用电月总量 (万kWh)
    for i in range(19, 31):
        m = int(df1.iloc[i, 1])
        monthly_pub_ele[m] = float(df1.iloc[i, 3])   # 公用耗电/万kWh
    for i in range(19, 31):
        m = int(df1.iloc[i, 6])
        monthly_cool[m] = float(df1.iloc[i, 7])       # 空调冷负荷/万kW

    # --- Sheet 3: 冷负荷 12月×24h + 工作日天数 ---
    df3 = pd.read_excel(xls, sheet_name="社区负荷分布", header=None)

    # 工作日天数
    workdays = {}
    for i in range(4, 16):
        m = int(df3.iloc[i, 3])
        workdays[m] = int(df3.iloc[i, 7])

    # 工作日冷负荷 24h（列 9=时刻, 10-21=1月-12月）
    cool_profile = {}  # {month: [24 values in kW]}
    for m in range(1, 13):
        cool_profile[m] = np.zeros(24)
    for i in range(10, 34):
        h_val = df3.iloc[i, 9]
        if pd.isna(h_val):
            continue
        h = int(float(h_val)) - 1  # XLS用1-24, 转为0-23
        for m_idx, col in enumerate(range(10, 22)):
            m = m_idx + 1
            val = df3.iloc[i, col]
            cool_profile[m][h] = float(val) if pd.notna(val) else 0.0

    # --- Sheet 4: 公用电负荷 12月×24h ---
    df4 = pd.read_excel(xls, sheet_name="社区电负荷分布", header=None)

    ele_profile = {}  # {month: [24 values in kW]}
    for m in range(1, 13):
        ele_profile[m] = np.zeros(24)
    for i in range(9, 33):
        h_val = df4.iloc[i, 3]
        if pd.isna(h_val):
            continue
        try:
            h = int(float(h_val)) - 1  # 1-24 → 0-23
        except (ValueError, TypeError):
            continue
        for m_idx, col in enumerate(range(4, 16)):
            m = m_idx + 1
            val = df4.iloc[i, col]
            ele_profile[m][h] = float(val) if pd.notna(val) else 0.0

    # --- Sheet 2: 光伏 ---
    df2 = pd.read_excel(xls, sheet_name="光伏发电量", header=None)
    pv_capacity = float(df2.iloc[3, 1])  # 2748.9 kW

    monthly_pv = {}
    for i in range(6, 18):
        m = int(df2.iloc[i, 2])
        monthly_pv[m] = float(df2.iloc[i, 3])  # 万kWh

    pv_hourly = np.zeros(24)  # 典型日逐时 (kWh)
    for i in range(26, 38):
        h = int(df2.iloc[i, 2])
        pv_hourly[h] = float(df2.iloc[i, 3])

    return {
        "monthly_cool": monthly_cool,
        "monthly_pub_ele": monthly_pub_ele,
        "workdays": workdays,
        "cool_profile": cool_profile,
        "ele_profile": ele_profile,
        "pv_capacity": pv_capacity,
        "monthly_pv": monthly_pv,
        "pv_hourly": pv_hourly,
    }


# ============================================================
# 2. 日历工具
# ============================================================

def build_calendar(year=YEAR):
    """返回 365 天的 (month, is_workday) 列表"""
    calendar = []
    for m, days in enumerate(DAYS_IN_MONTH, 1):
        for d in range(1, days + 1):
            dt = datetime.date(year, m, d)
            is_workday = dt.weekday() < 5  # Mon=0 .. Fri=4
            calendar.append((m, is_workday))
    assert len(calendar) == 365
    return calendar


# ============================================================
# 3. 负荷生成（基于 XLS 典型日形状）
# ============================================================

def generate_cool_load(xls_data, calendar):
    """
    冷负荷：XLS 工作日典型日形状 × 月度总量缩放。
    - 工作日：使用 XLS Sheet 3 的 24h 形状
    - 周末：冷负荷 = 0（XLS 数据验证：workday_daily × workdays ≈ monthly_total）
    - 月度总量严格匹配 XLS 表C
    """
    cool_profile = xls_data["cool_profile"]
    monthly_cool = xls_data["monthly_cool"]

    cool_load = np.zeros(8760)

    for m in range(1, 13):
        # 找到本月所有天及其类型
        month_days = [(day_idx, is_wd) for day_idx, (mo, is_wd)
                      in enumerate(calendar) if mo == m]
        workday_indices = [idx for idx, is_wd in month_days if is_wd]
        n_workdays = len(workday_indices)

        if n_workdays == 0:
            continue

        # XLS 典型日形状
        profile = cool_profile[m]  # 24 values (kW)
        profile_sum = np.sum(profile)  # kWh per workday

        # 月总量 (kWh)
        target_total = monthly_cool[m] * 1e4

        # 缩放因子：确保 workday_profile × n_workdays = monthly_total
        if profile_sum > 0:
            scale = target_total / (profile_sum * n_workdays)
        else:
            scale = 0.0

        # 填入工作日
        for day_idx in workday_indices:
            start_h = day_idx * 24
            cool_load[start_h:start_h + 24] = profile * scale

    # clip 到图5延时曲线起点
    cool_load = np.clip(cool_load, 0, PEAK_COOL_LOAD)
    return cool_load


def generate_ele_load(xls_data, calendar):
    """
    公用电负荷：XLS Sheet 4 的 24h 形状，所有天使用相同形状。
    - XLS 验证：daily_sum × total_days ≈ monthly_total（电负荷无工作日/周末区分）
    - 月度总量严格匹配 XLS 表B 公用耗电列
    - 添加 ±2% 随机扰动增加日间变异
    """
    ele_profile = xls_data["ele_profile"]
    monthly_pub_ele = xls_data["monthly_pub_ele"]

    ele_load = np.zeros(8760)

    for m in range(1, 13):
        month_days = [(day_idx, is_wd) for day_idx, (mo, is_wd)
                      in enumerate(calendar) if mo == m]
        n_days = len(month_days)

        profile = ele_profile[m]  # 24 values (kW)
        profile_sum = np.sum(profile)  # kWh per day

        target_total = monthly_pub_ele[m] * 1e4  # kWh

        if profile_sum > 0:
            scale = target_total / (profile_sum * n_days)
        else:
            scale = 0.0

        for day_idx, _ in month_days:
            start_h = day_idx * 24
            # 添加日间扰动 (±2%)
            daily_noise = 1.0 + np.random.normal(0, 0.02)
            ele_load[start_h:start_h + 24] = profile * scale * daily_noise

    ele_load = np.clip(ele_load, 3, 500)
    return ele_load


def generate_solar_radiation(xls_data, calendar):
    """
    太阳辐射：基于 XLS 光伏典型日形状 + 月度发电量缩放 + 随机云量。

    转换逻辑：
      PV_output(kW) = solar_irradiance(W/m²) × area(m²) × efficiency / 1000
      → solar(W/m²) = PV_output(kW) / capacity(kW) × 1000

    XLS 基准：2748.9 kW 装机，峰值输出 1091 kW → 峰值辐射 ≈ 397 W/m²（含云量均值）
    按月度发电量比值缩放，再加随机云量变化。
    """
    pv_hourly = xls_data["pv_hourly"]   # 24h (kWh for 2748.9kW)
    pv_capacity = xls_data["pv_capacity"]
    monthly_pv = xls_data["monthly_pv"]

    # 典型日发电总量
    typical_day_total = np.sum(pv_hourly)  # kWh

    # 归一化到辐射 (W/m²)：solar = pv_kw / capacity_kw * 1000
    typical_solar_profile = pv_hourly / pv_capacity * 1000  # W/m²

    solar = np.zeros(8760)

    for m in range(1, 13):
        month_days = [(day_idx, _) for day_idx, (mo, _)
                      in enumerate(calendar) if mo == m]
        n_days = len(month_days)

        # 月度缩放因子
        avg_daily_pv = monthly_pv[m] * 1e4 / n_days  # kWh/day
        if typical_day_total > 0:
            month_scale = avg_daily_pv / typical_day_total
        else:
            month_scale = 1.0

        for day_idx, _ in month_days:
            start_h = day_idx * 24
            # 随机云量 (0.5~1.2，模拟晴天/多云)
            cloud_factor = np.random.uniform(0.5, 1.2)
            solar[start_h:start_h + 24] = (
                typical_solar_profile * month_scale * cloud_factor
            )

    solar = np.clip(solar, 0, 1100)
    return solar


def generate_heat_load(calendar):
    """
    热负荷：办公园区生活热水（茶水间 + 少量淋浴）。
    警告：PDF/XLS 无任何热负荷数据，完全基于假设，论文中必须披露。
    """
    heat_load = np.zeros(8760)
    for day_idx, (m, _) in enumerate(calendar):
        start_h = day_idx * 24
        seasonal = 1.0 + 0.3 * np.cos(2 * np.pi * (m - 1) / 12)
        for h in range(24):
            if 6 <= h <= 8:
                base = 80
            elif 18 <= h <= 22:
                base = 90
            elif 8 < h < 18:
                base = 25
            else:
                base = 10
            noise = 1.0 + np.random.normal(0, 0.08)
            heat_load[start_h + h] = base * seasonal * noise

    heat_load = np.clip(heat_load, 3, 200)
    return heat_load


def generate_climate_synthetic(calendar):
    """合成温度和风速（非实测 TMY）"""
    n_hours = 8760
    hours = np.arange(n_hours)
    day_of_year = hours // 24 + 1
    hour_of_day = hours % 24

    # 温度
    T_mean, T_amp_annual, T_amp_daily = 22.7, 8.5, 4.0
    T_annual = T_mean + T_amp_annual * np.sin(2 * np.pi * (day_of_year - 105) / 365)
    T_daily = T_amp_daily * np.sin(2 * np.pi * (hour_of_day - 8) / 24)
    temperature = np.clip(T_annual + T_daily + np.random.normal(0, 1.5, n_hours), 3, 38)

    # 风速
    wind = np.random.weibull(2.0, n_hours) * 2.0
    wind += 0.5 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    wind = np.clip(wind, 0.1, 8.0)

    return temperature, wind


# ============================================================
# 4. 主生成函数
# ============================================================

def generate_all(xls_path):
    """基于 XLS 源数据生成完整 8760h 数据集"""
    print(f"  读取 XLS: {xls_path}")
    xls_data = load_xls_data(xls_path)
    calendar = build_calendar(YEAR)

    print("  生成冷负荷（XLS 工作日典型日形状）...")
    cool_load = generate_cool_load(xls_data, calendar)

    print("  生成公用电负荷（XLS 典型日形状）...")
    ele_load = generate_ele_load(xls_data, calendar)

    print("  生成太阳辐射（XLS 光伏曲线反推）...")
    solar = generate_solar_radiation(xls_data, calendar)

    print("  生成热负荷（合成，无源数据）...")
    heat_load = generate_heat_load(calendar)

    print("  生成温度/风速（合成）...")
    temperature, wind = generate_climate_synthetic(calendar)

    return pd.DataFrame({
        "ele_load(kW)": ele_load,
        "heat_load(kW)": heat_load,
        "cool_load(kW)": cool_load,
        "solarRadiation(W/m-2)": solar,
        "windSpeed(m/s)": wind,
        "temperature(C)": temperature,
    })


# ============================================================
# 5. Sanity check
# ============================================================

def sanity_check(df):
    print("\n" + "=" * 60)
    print("  Sanity check")
    print("=" * 60)

    checks = []

    # 1. ele_load 年总量
    ele_sum = df["ele_load(kW)"].sum() / 1e4
    tol = abs(ele_sum - ANNUAL_NON_AC_ELE) / ANNUAL_NON_AC_ELE
    checks.append(("ele_load 年总量", f"{ele_sum:.2f} 万kWh",
                    f"目标 {ANNUAL_NON_AC_ELE}", "OK" if tol < 0.03 else f"偏差 {tol:.1%}"))

    # 2. cool_load 年总量
    cool_sum = df["cool_load(kW)"].sum() / 1e4
    tol = abs(cool_sum - ANNUAL_COOL_LOAD) / ANNUAL_COOL_LOAD
    checks.append(("cool_load 年总量", f"{cool_sum:.2f} 万kWh",
                    f"目标 {ANNUAL_COOL_LOAD}", "OK" if tol < 0.03 else f"偏差 {tol:.1%}"))

    # 3. cool_load 峰值
    cool_peak = df["cool_load(kW)"].max()
    checks.append(("cool_load 峰值", f"{cool_peak:.1f} kW",
                    f"clip {PEAK_COOL_LOAD}", "OK" if cool_peak <= PEAK_COOL_LOAD + 1 else "WARN"))

    # 4. ele_load 峰值（应 ~250 kW，非空调公用电）
    ele_peak = df["ele_load(kW)"].max()
    checks.append(("ele_load 峰值", f"{ele_peak:.1f} kW",
                    "应 < 300", "OK" if ele_peak < 300 else "WARN"))

    # 5. 冷电比
    c2e = df["cool_load(kW)"].sum() / df["ele_load(kW)"].sum()
    checks.append(("冷电比 (cool/ele)", f"{c2e:.2f}",
                    "应 > 3", "OK" if c2e > 3 else "WARN"))

    # 6. 冷负荷非零小时数
    cool_nonzero_hours = np.sum(df["cool_load(kW)"] > 1.0)
    checks.append(("冷负荷非零小时", f"{cool_nonzero_hours}",
                    "应 < 5000", "OK" if cool_nonzero_hours < 5000 else "INFO"))

    # 7. 延时曲线 1811h 处
    cool_sorted = np.sort(df["cool_load(kW)"].values)[::-1]
    cool_at_1811 = cool_sorted[1810] if len(cool_sorted) > 1810 else 0
    checks.append(("延时曲线@1811h", f"{cool_at_1811:.1f} kW",
                    "PDF: 1269 kW", "INFO"))

    for name, actual, target, status in checks:
        icon = "OK  " if status == "OK" else ("INFO" if status == "INFO" else "WARN")
        print(f"  [{icon}] {name:25s} | {actual:18s} | {target}")
    print("=" * 60)


# ============================================================
# 6. 典型日聚类
# ============================================================

def run_clustering(data, n_clusters=14):
    try:
        from sklearn_extra.cluster import KMedoids
        from sklearn.preprocessing import StandardScaler

        feat_cols = ["ele_load(kW)", "heat_load(kW)", "cool_load(kW)",
                     "solarRadiation(W/m-2)", "temperature(C)"]
        feat_data = data[feat_cols].values.reshape(365, 24 * len(feat_cols))

        scaler = StandardScaler()
        daily_scaled = scaler.fit_transform(feat_data)

        kmedoids = KMedoids(n_clusters=n_clusters, random_state=42, method="pam")
        labels = kmedoids.fit_predict(daily_scaled)

        results = []
        for cid in range(n_clusters):
            members = np.where(labels == cid)[0] + 1
            results.append({
                "typicalDayId": int(kmedoids.medoid_indices_[cid] + 1),
                "weight": len(members),
                "days": ",".join(map(str, members)),
            })
        print("  [KMedoids/PAM] OK")
        return pd.DataFrame(results)
    except ImportError:
        print("  [sklearn_extra 不可用，退化为层次聚类]")
        return _run_clustering_hierarchical(data, n_clusters)


def _run_clustering_hierarchical(data, n_clusters=14):
    from scipy.cluster.hierarchy import fcluster, linkage

    feat_cols = ["ele_load(kW)", "heat_load(kW)", "cool_load(kW)",
                 "solarRadiation(W/m-2)", "temperature(C)"]
    feat_data = data[feat_cols].values.reshape(365, 24 * len(feat_cols))

    mean, std = feat_data.mean(0), feat_data.std(0)
    std[std < 1e-6] = 1.0
    daily_scaled = (feat_data - mean) / std

    Z = linkage(daily_scaled, method="ward")
    labels = fcluster(Z, t=n_clusters, criterion="maxclust") - 1

    results = []
    for cid in range(n_clusters):
        members = np.where(labels == cid)[0]
        cluster_data = daily_scaled[members]
        centroid = cluster_data.mean(0)
        dists = np.linalg.norm(cluster_data - centroid, axis=1)
        medoid = members[np.argmin(dists)] + 1
        results.append({
            "typicalDayId": int(medoid),
            "weight": len(members),
            "days": ",".join(map(str, members + 1)),
        })
    df = pd.DataFrame(results)
    assert df["weight"].sum() == 365
    return df


# ============================================================
# 7. 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="松山湖 8760h 数据生成器 (v3 XLS 源版)")
    parser.add_argument("--skip-clustering", action="store_true")
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--n-clusters", type=int, default=14)
    parser.add_argument("--xls", default=XLS_PATH, help="XLS 源数据路径")
    args = parser.parse_args()

    print("=" * 60)
    print("  松山湖数据生成器 v3（XLS 源数据版）")
    print("  - 冷/电负荷形状：来自项目方 XLS 典型日曲线")
    print("  - ele_load：仅公用电（69.59 万kWh/年）")
    print("  - cool_load：需求侧（291.15 万kWh/年）")
    print("  - 周末冷负荷 = 0（XLS 验证）")
    print("=" * 60)

    data_dir = os.path.join(PROJECT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, "songshan_lake_data.csv")
    xlsx_path = os.path.join(data_dir, "songshan_lake_typical.xlsx")

    if args.skip_generation:
        if not os.path.isfile(csv_path):
            print(f"错误：--skip-generation 需要已有 {csv_path}")
            sys.exit(1)
        df = pd.read_csv(csv_path)
        print(f"\n[加载] {csv_path} (shape={df.shape})")
    else:
        if not os.path.isfile(args.xls):
            print(f"错误：找不到 XLS 文件 {args.xls}")
            sys.exit(1)

        print(f"\n[1/2] 生成 8760h 数据...")
        df = generate_all(args.xls)

        df.to_csv(csv_path, index=False)
        print(f"\n  已保存: {csv_path}")
        for col in ["ele_load(kW)", "heat_load(kW)", "cool_load(kW)"]:
            s = df[col]
            print(f"  {col:20s}: {s.min():.0f} ~ {s.max():.0f} kW, "
                  f"年总 {s.sum()/1e4:.2f} 万kWh")

        sanity_check(df)

    if not args.skip_clustering:
        print(f"\n[2/2] 典型日聚类 ({args.n_clusters} 个)...")
        typical_df = run_clustering(df, n_clusters=args.n_clusters)
        typical_df.to_excel(xlsx_path, index=False)
        print(f"  已保存: {xlsx_path}")
        print(f"  权重之和: {typical_df['weight'].sum()}")

    print("\n" + "=" * 60)
    print("  完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
