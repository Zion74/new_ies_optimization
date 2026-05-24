# -*- coding: utf-8 -*-
"""
2026-04-20 松山湖数据 + 设备参数重建前作废实验的归档脚本（Python 版）
======================================================================

commit b682cfc（2026-04-20）同时变更：
  1. 松山湖负荷数据（ele_load 166.64→69.59 万 kWh/a，冷电比 1.75→4.18）
  2. 松山湖设备效率（gt_eta_e 0.35→0.423，gt_eta_h 0.45→0.42，ec_cop 3.5→5.5）
  3. 用户额外提示："德国的卡诺电池好像之前改过，没事重新做吧"

两批 20260417 实验里以下实验作废，需归档：
  - exp2a / exp2b / exp3 / exp4

保留：
  - exp1 (DE_base, 5 方法)   德国数据 + 参数均未改动

归档目标：Results/服务器结果/_pre_device_rebuild_2026-04-20/

用法：
  python scripts/archive_pre_device_rebuild_2026-04-20.py --dry-run
  python scripts/archive_pre_device_rebuild_2026-04-20.py
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

BATCH_DIRS = [
    REPO_ROOT / "Results" / "服务器结果" / "paper-batch__exp-all__full__n80__g150__w28__20260417_105519",
    REPO_ROOT / "Results" / "服务器结果" / "paper-batch__exp-all__full__n80__g150__w28__20260417_170546",
]

STALE_PREFIXES = ("exp2a__", "exp2b__", "exp3__", "exp4__")

ARCHIVE_ROOT = REPO_ROOT / "Results" / "服务器结果" / "_pre_device_rebuild_2026-04-20"


README_CONTENT = """# 设备参数 + 松山湖数据重建前实验归档

**归档时间**：2026-04-20

**对应代码 commit**：`b682cfc feat(songshan): rebuild data from XLS source + correct device params`

**归档原因**：

本次 commit 同时变更了两类可能影响实验结果的要素：

1. **松山湖负荷数据重建**（从 XLS 源数据）
   - `ele_load`: 166.64 → 69.59 万 kWh/a（仅公用电，不含空调电）
   - 冷电比: 1.75 → 4.18（PDF 精确对齐）
   - 冷负荷峰值: 5797 → 3460 kW
   - 冷负荷形状: 12 月×24h 典型日（XLS Sheet 3 源数据）
   - 电负荷形状: 12 月×24h 典型日（XLS Sheet 4 源数据）

2. **松山湖设备效率修正**
   - `gt_eta_e`: 0.35 → 0.423（CAT G3512E 官方最大发电效率 42.3%）
   - `gt_eta_h`: 0.45 → 0.42
   - `ec_cop`: 3.5 → 5.5

3. **德国 Carnot 参数**（用户提示存疑）
   - 保守起见一并归档 `exp2b`（DE_carnot），新批次统一用修正后配置重跑

**归档内容**（两批 20260417 实验）：

- `exp2a__german__base__std+euclidean__*` (DE_base subset)
- `exp2b__german__carnot__std+euclidean__*` (DE_carnot)
- `exp3__songshan_lake__base__std+euclidean__*` (SL_base)
- `exp4__songshan_lake__carnot__std+euclidean__*` (SL_carnot)

**保留不归档**：

- `exp1__german__base__m5__*`（DE_base, 5 方法）
  - 德国数据 + 参数均未改动，exp1 结果仍有效

**下一步**：

- 服务器重跑 `exp2` + `exp3` + `exp4`，两批 n80×g150
- 新批次回来后，`method_scenario_matrix.py` / `pareto_hypervolume.py` / `pareto_overlay.py` 自动合并：旧 exp1 + 新 exp2/3/4

**历史背景**：

参见 `docs/辩论确认/2026-04-18_德国松山湖三大发现诊断报告.md`
"""


def find_stale_dirs():
    """返回 List[(src_path, dst_path)]"""
    pairs = []
    for batch_dir in BATCH_DIRS:
        if not batch_dir.is_dir():
            print(f"  [warn] 批次不存在，跳过整批：{batch_dir}")
            continue
        for sub in sorted(batch_dir.iterdir()):
            if not sub.is_dir():
                continue
            if not sub.name.startswith(STALE_PREFIXES):
                continue
            flat_name = f"{batch_dir.name}__{sub.name}"
            dst = ARCHIVE_ROOT / flat_name
            pairs.append((sub, dst))
    return pairs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="只打印要做什么，不实际移动")
    args = p.parse_args()

    print("=" * 70)
    print("  设备参数 + 松山湖数据重建前实验归档（2026-04-20）")
    print(f"  归档目标：{ARCHIVE_ROOT}")
    if args.dry_run:
        print("  模式：DRYRUN（只打印不实际移动）")
    print("=" * 70)

    pairs = find_stale_dirs()
    if not pairs:
        print("\n未发现任何 stale 实验目录，退出。")
        return

    print(f"\n发现 {len(pairs)} 个作废实验目录：\n")
    moved = 0
    for src, dst in pairs:
        rel = src.relative_to(REPO_ROOT)
        print(f"[{rel}]")
        print(f"  -> {dst.name}")
        if args.dry_run:
            print("  [DRY] move")
            continue
        try:
            ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print("  [OK] 已归档")
            moved += 1
        except Exception as e:
            print(f"  [ERROR] {e}")

    print("\n" + "=" * 70)
    if args.dry_run:
        print(f"  [DRY] 预计归档 {len(pairs)} 项")
    else:
        print(f"  归档完成：成功 {moved} / {len(pairs)} 项")
    print("=" * 70)

    if not args.dry_run and moved > 0:
        readme = ARCHIVE_ROOT / "README.md"
        readme.write_text(README_CONTENT, encoding="utf-8")
        print(f"\n归档说明已写入：{readme}")


if __name__ == "__main__":
    main()
