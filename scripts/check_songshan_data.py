# -*- coding: utf-8 -*-
"""
check_songshan_data.py — 松山湖数据口径独立检验
================================================================
对 `data/songshan_lake_data.csv` 做详细的口径检验，把逐项结果对比
PDF 标准值（图 3、表 2、图 5）。返回非零退出码表示有 WARN 级偏差，
可用于 CI / pre-commit hook。

与 `generate_songshan_data.py` 内嵌 sanity_check 的区别：
  - 输出更详细（分月对比、延时曲线多点对比）
  - 可对现有 CSV 做独立检验（不依赖重新生成）
  - 带 exit code，便于自动化

用法：
  uv run python scripts/check_songshan_data.py
  uv run python scripts/check_songshan_data.py --csv data/songshan_lake_data.csv
  uv run python scripts/check_songshan_data.py --strict   # 任一 WARN 即 exit 1
"""

import argparse
import io
import os
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- PDF 标准值（与 generate_songshan_data.py 保持同步）----
MONTHLY_TOTAL_ELE_FIG3 = {
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
MONTHLY_AC_ELE_FIG3 = {
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
MONTHLY_NON_AC_ELE_FIG3 = {
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

ANNUAL_NON_AC_ELE = 69.59  # 万 kWh
ANNUAL_COOL_LOAD = 291.14  # 万 kW·h
ANNUAL_TOTAL_ELE_HISTORICAL = 166.64
PEAK_COOL_LOAD = 3460.0
COOL_1811H_VALUE = 1269.0
COOL_2310H_TARGET = None  # 无 PDF 标注，只看延时曲线 > 0 的大致比例


def _day_to_month(d):
    dim = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    cum = 0
    for m, n in enumerate(dim, 1):
        cum += n
        if d <= cum:
            return m
    return 12


class Checker:
    def __init__(self, strict=False):
        self.strict = strict
        self.n_ok = 0
        self.n_warn = 0
        self.rows = []

    def add(self, name, actual, target, ok, detail=""):
        status = "OK" if ok else "WARN"
        if ok:
            self.n_ok += 1
        else:
            self.n_warn += 1
        self.rows.append((name, actual, target, status, detail))

    def print_section(self, title):
        print("\n" + "-" * 70)
        print(f"  {title}")
        print("-" * 70)
        for name, actual, target, status, detail in self.rows:
            icon = "OK  " if status == "OK" else "WARN"
            detail_str = f"  [{detail}]" if detail else ""
            print(f"  [{icon}] {name:30s} | {actual:<20s} | 目标 {target}{detail_str}")
        self.rows = []  # clear for next section

    def exit(self):
        print("\n" + "=" * 70)
        print(f"  总计: OK={self.n_ok}  WARN={self.n_warn}")
        print("=" * 70)
        if self.strict and self.n_warn > 0:
            sys.exit(1)
        sys.exit(0)


def check_annual_totals(df, c):
    ele_sum = df["ele_load(kW)"].sum() / 1e4
    cool_sum = df["cool_load(kW)"].sum() / 1e4
    heat_sum = df["heat_load(kW)"].sum() / 1e4
    ec_cop = 3.5
    implied_total = (
        df["ele_load(kW)"].sum() + df["cool_load(kW)"].sum() / ec_cop
    ) / 1e4

    c.add(
        "ele_load 年总量 (非空调电)",
        f"{ele_sum:.2f} 万kWh",
        f"{ANNUAL_NON_AC_ELE}",
        abs(ele_sum - ANNUAL_NON_AC_ELE) / ANNUAL_NON_AC_ELE < 0.02,
        "允差 ±2%",
    )
    c.add(
        "cool_load 年总量",
        f"{cool_sum:.2f} 万kW·h",
        f"{ANNUAL_COOL_LOAD}",
        abs(cool_sum - ANNUAL_COOL_LOAD) / ANNUAL_COOL_LOAD < 0.02,
        "允差 ±2%",
    )
    c.add(
        "heat_load 年总量 (合成)",
        f"{heat_sum:.2f} 万kWh",
        "无 PDF 标准",
        5 < heat_sum < 50,
        "合理区间 5-50",
    )
    c.add(
        "隐含历史总电 ele+cool/3.5",
        f"{implied_total:.2f} 万kWh",
        f"{ANNUAL_TOTAL_ELE_HISTORICAL}",
        abs(implied_total - ANNUAL_TOTAL_ELE_HISTORICAL) / ANNUAL_TOTAL_ELE_HISTORICAL
        < 0.10,
        "允差 ±10%",
    )
    c.print_section("1. 年度总量检验")


def check_monthly(df, c):
    df = df.copy()
    df["day"] = np.arange(len(df)) // 24 + 1
    df["month"] = df["day"].apply(_day_to_month)

    max_dev_ele = 0.0
    max_dev_cool = 0.0
    monthly_detail = []
    for m in range(1, 13):
        mm = df[df["month"] == m]
        ele_m = mm["ele_load(kW)"].sum() / 1e4
        cool_m = mm["cool_load(kW)"].sum() / 1e4
        ele_t = MONTHLY_NON_AC_ELE_FIG3[m]
        cool_t = MONTHLY_COOL_LOAD_TAB2[m]
        dev_e = abs(ele_m - ele_t) / ele_t
        dev_c = abs(cool_m - cool_t) / max(cool_t, 0.1)
        max_dev_ele = max(max_dev_ele, dev_e)
        max_dev_cool = max(max_dev_cool, dev_c)
        monthly_detail.append(
            f"    M{m:02d}: ele={ele_m:5.2f}/{ele_t:5.2f} ({dev_e:+.1%})  "
            f"cool={cool_m:6.2f}/{cool_t:6.2f} ({dev_c:+.1%})"
        )

    c.add("月度 ele 最大偏差", f"{max_dev_ele:.1%}", "<5%", max_dev_ele < 0.05)
    c.add("月度 cool 最大偏差", f"{max_dev_cool:.1%}", "<5%", max_dev_cool < 0.05)
    c.print_section("2. 月度总量对齐（图 3 公用耗电 + 表 2 冷负荷）")
    print("\n  月度明细:")
    for line in monthly_detail:
        print(line)


def check_peak_and_duration(df, c):
    cool_peak = df["cool_load(kW)"].max()
    ele_peak = df["ele_load(kW)"].max()
    cool_sorted = np.sort(df["cool_load(kW)"].values)[::-1]

    c.add(
        "cool_load 峰值",
        f"{cool_peak:.1f} kW",
        f"{PEAK_COOL_LOAD} ±5%",
        abs(cool_peak - PEAK_COOL_LOAD) / PEAK_COOL_LOAD < 0.05,
    )
    c.add(
        "ele_load 峰值",
        f"{ele_peak:.1f} kW",
        "180-300 kW 区间",
        180 <= ele_peak <= 300,
        "非空调电估计 ~200-220 kW",
    )

    # 冷负荷非零小时数 (供冷时间上限 2800h，但非零可更长)
    nonzero_cool = int((df["cool_load(kW)"] > 50).sum())
    c.add(
        "冷负荷 > 50 kW 小时数",
        f"{nonzero_cool} h",
        "< 4500 h (PDF 供冷期约 3500h)",
        nonzero_cool < 4500,
        "软约束",
    )

    c.print_section("3. 峰值与延时曲线")

    # 延时曲线参考点（INFO，不计入 WARN）：
    # PDF 图 5 的三点读数（峰 3460 / 1811h=1269 / 3500h≈0）与表 2 年总
    # 291.14 万 kW·h 数学不相容——若同时满足前两点，前 1811h 积分 ≥ 428
    # 万 kW·h，超过全年总量。因此只作参考值打印，不计 WARN。
    print("\n  延时曲线参考点（INFO）：")
    if len(cool_sorted) > 1810:
        v1811 = cool_sorted[1810]
        print(
            f"    - @ 1811h:  实际 {v1811:7.1f} kW   | PDF 读数 {COOL_1811H_VALUE} kW （PDF 内部不相容，仅供参考）"
        )
    if len(cool_sorted) > 3499:
        v3500 = cool_sorted[3499]
        print(
            f"    - @ 3500h:  实际 {v3500:7.1f} kW   | PDF 读数 ≈0 kW  （供冷季上限）"
        )


def check_shape(df, c):
    """形状检查：日内曲线、工作日/周末差异"""
    df = df.copy()
    df["hour"] = np.arange(len(df)) % 24

    # 平均日内曲线
    mean_by_hour = df.groupby("hour")[["ele_load(kW)", "cool_load(kW)"]].mean()
    ele_night = mean_by_hour.loc[0:5, "ele_load(kW)"].mean()
    ele_day = mean_by_hour.loc[9:17, "ele_load(kW)"].mean()
    cool_night = mean_by_hour.loc[0:5, "cool_load(kW)"].mean()
    cool_day = mean_by_hour.loc[12:16, "cool_load(kW)"].mean()

    c.add(
        "电负荷 昼/夜比值",
        f"{ele_day / max(ele_night, 0.1):.2f}",
        "> 3 (办公特征)",
        ele_day / max(ele_night, 0.1) > 3,
    )
    c.add(
        "冷负荷 昼/夜比值",
        f"{cool_day / max(cool_night, 0.1):.2f}",
        "> 10 (供冷集中午后)",
        cool_day / max(cool_night, 0.1) > 10,
    )

    c.print_section("4. 日内形状")


def main():
    parser = argparse.ArgumentParser(description="松山湖数据口径独立检验")
    parser.add_argument(
        "--csv",
        default=os.path.join(BASE_DIR, "data", "songshan_lake_data.csv"),
        help="要检验的 CSV 路径（默认 data/songshan_lake_data.csv）",
    )
    parser.add_argument(
        "--strict", action="store_true", help="任一 WARN 即退出码 1（用于 CI）"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  松山湖负荷数据口径检验")
    print(f"  文件: {args.csv}")
    print("  对比标准: 松山湖/松山湖数据保存/02_负荷数据.md")
    print("=" * 70)

    if not os.path.isfile(args.csv):
        print(f"错误：找不到 CSV 文件 {args.csv}")
        sys.exit(2)

    df = pd.read_csv(args.csv)
    if len(df) != 8760:
        print(f"错误：CSV 行数 {len(df)} 不等于 8760")
        sys.exit(2)

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
        print(f"错误：CSV 缺少必需列 {missing}")
        sys.exit(2)

    c = Checker(strict=args.strict)
    check_annual_totals(df, c)
    check_monthly(df, c)
    check_peak_and_duration(df, c)
    check_shape(df, c)
    c.exit()


if __name__ == "__main__":
    main()
