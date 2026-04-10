# -*- coding: utf-8 -*-
"""
将一次带 --unit-lambda 的 Results 子目录中的三份 Pareto 复制到
论文撰写/会议/data/raw_pareto_unit_lambda/，并生成 summary_conference_unit_lambda.csv。

用法（仓库根目录）:
  uv run python scripts/archive_ieee_unit_lambda.py --result-dir Results/custom_german_unitlambda_10x5_3methods_YYYYMMDD_HHMMSS
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
IEEE_DATA = BASE / "论文撰写/会议/data"
PAIRS = [
    ("Economic_only/Pareto_Economic_only.csv", "Pareto_Economic_only.csv"),
    ("Std/Pareto_Std.csv", "Pareto_Std.csv"),
    ("Euclidean/Pareto_Euclidean.csv", "Pareto_Euclidean.csv"),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--result-dir",
        type=Path,
        required=True,
        help="含 Economic_only / Std / Euclidean 子目录的 Results 路径",
    )
    args = p.parse_args()
    src_root = (BASE / args.result_dir).resolve() if not args.result_dir.is_absolute() else args.result_dir
    if not src_root.is_dir():
        sys.exit(f"目录不存在: {src_root}")

    dest_dir = IEEE_DATA / "raw_pareto_unit_lambda"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel, name in PAIRS:
        s = src_root / rel
        if not s.is_file():
            sys.exit(f"缺少文件: {s}")
        shutil.copy2(s, dest_dir / name)
        print("copied", s.name, "->", dest_dir / name)

    out_sum = IEEE_DATA / "summary_conference_unit_lambda.csv"
    exp = BASE / "scripts/export_ieee_conference_data.py"
    subprocess.check_call(
        [
            sys.executable,
            str(exp),
            "--pareto-dir",
            str(dest_dir),
            "-o",
            str(out_sum),
            "--feasible-max-cost",
            "5000000",
        ],
        cwd=str(BASE),
    )
    print("Wrote", out_sum)


if __name__ == "__main__":
    main()
