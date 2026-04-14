#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run a parameter-scale sensitivity study end to end:
1. Launch multiple optimization runs with different (nind, maxgen).
2. Automatically collect the newly created result directories.
3. Generate a markdown comparison report.

Default use case:
    Compare 50/100, 80/150, 100/200 for paper experiment 1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from compare_parameter_scales import build_markdown, load_run_summary


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = REPO_ROOT / "Results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run and analyze parameter-scale sensitivity experiments."
    )
    parser.add_argument(
        "--scales",
        nargs="+",
        default=["50x100", "80x150", "100x200"],
        help="Population/generation scales like 50x100 80x150 100x200.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker count passed through to run.py.",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Pass --skip-check to run.py to avoid repeated preflight checks.",
    )
    parser.add_argument(
        "--quick-run",
        action="store_true",
        help="Use --quick-run for --exp mode instead of full parameters.",
    )
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Use --test-run for --exp mode instead of full parameters.",
    )
    parser.add_argument(
        "--exp",
        choices=["1", "2", "3", "4", "all"],
        default="1",
        help="Paper experiment preset to run for each scale. Default: exp 1.",
    )
    parser.add_argument(
        "--mode",
        choices=["custom", "test", "quick", "full"],
        help="Use run.py --mode instead of --exp. If omitted, --exp is used.",
    )
    parser.add_argument(
        "--case",
        choices=["german", "songshan_lake"],
        default="german",
        help="Case used for --mode custom/full/quick/test.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=["economic_only", "std", "euclidean", "pearson", "ssr"],
        help="Methods for --mode custom runs.",
    )
    parser.add_argument(
        "--carnot",
        action="store_true",
        help="Pass --carnot to run.py for mode-based runs.",
    )
    parser.add_argument(
        "--unit-lambda",
        action="store_true",
        help="Pass --unit-lambda to run.py.",
    )
    parser.add_argument(
        "--output",
        help="Optional markdown output path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them.",
    )
    return parser.parse_args()


def parse_scale(text: str) -> Tuple[int, int]:
    try:
        nind_text, maxgen_text = text.lower().split("x", 1)
        return int(nind_text), int(maxgen_text)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid scale '{text}', expected format like 50x100") from exc


def list_result_dirs() -> dict[str, float]:
    RESULTS_ROOT.mkdir(exist_ok=True)
    items = {}
    for path in RESULTS_ROOT.iterdir():
        if path.is_dir():
            items[str(path.resolve())] = path.stat().st_mtime
    return items


def detect_new_result_dir(before: dict[str, float], after: dict[str, float]) -> Path:
    created = [Path(p) for p in after if p not in before]
    if created:
        return max(created, key=lambda p: p.stat().st_mtime)

    changed = [Path(p) for p, ts in after.items() if before.get(p) != ts]
    if changed:
        return max(changed, key=lambda p: p.stat().st_mtime)

    raise RuntimeError("Could not detect a newly created result directory.")


def build_run_command(args: argparse.Namespace, nind: int, maxgen: int) -> List[str]:
    cmd: List[str] = [sys.executable, "run.py"]

    if args.mode:
        cmd.extend(["--mode", args.mode])
        cmd.extend(["--case", args.case])
        if args.mode == "custom":
            cmd.extend(["--nind", str(nind), "--maxgen", str(maxgen), "--methods", *args.methods])
        elif args.mode in {"test", "quick", "full"}:
            # these modes ignore nind/maxgen and use preset values
            pass
    else:
        cmd.extend(["--exp", args.exp])
        if args.test_run:
            cmd.append("--test-run")
        elif args.quick_run:
            cmd.append("--quick-run")

    if args.mode is None:
        # For preset paper experiments we need custom scales, so use custom mode if
        # the requested scale differs from the preset. We map exp presets to custom
        # runs only for exp 1 to keep behavior explicit.
        if args.exp != "1":
            raise ValueError(
                "Scale overrides are currently supported for --exp 1 only. "
                "Use --mode custom for other sensitivity studies."
            )
        if not args.test_run and not args.quick_run:
            cmd = [
                sys.executable,
                "run.py",
                "--mode",
                "custom",
                "--case",
                "german",
                "--nind",
                str(nind),
                "--maxgen",
                str(maxgen),
                "--methods",
                "economic_only",
                "std",
                "euclidean",
                "pearson",
                "ssr",
            ]

    if args.carnot:
        cmd.append("--carnot")
    if args.unit_lambda:
        cmd.append("--unit-lambda")
    if args.skip_check:
        cmd.append("--skip-check")
    if args.workers is not None:
        cmd.extend(["--workers", str(args.workers)])

    return cmd


def run_single_command(cmd: Sequence[str], dry_run: bool = False) -> Path | None:
    print("\n" + "=" * 80)
    print("Running:", " ".join(cmd))
    print("=" * 80)

    if dry_run:
        return None

    before = list_result_dirs()
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    after = list_result_dirs()
    result_dir = detect_new_result_dir(before, after)
    print(f"Detected result directory: {result_dir}")
    return result_dir


def build_driver_report(
    output_path: Path,
    result_dirs: Sequence[Path],
    commands: Sequence[Sequence[str]],
) -> None:
    runs = [load_run_summary(str(path)) for path in result_dirs]
    body = build_markdown(runs)

    header: List[str] = []
    header.append("# 参数敏感性实验总控报告\n\n")
    header.append(f"- 生成时间: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    header.append(f"- 结果组数: {len(result_dirs)}\n\n")
    header.append("## 实际执行命令\n\n")
    for idx, cmd in enumerate(commands, 1):
        header.append(f"{idx}. `{ ' '.join(cmd) }`\n")
    header.append("\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(header) + body, encoding="utf-8")


def main() -> None:
    args = parse_args()
    scales = [parse_scale(text) for text in args.scales]

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = (
            RESULTS_ROOT / f"parameter_sensitivity_report__{timestamp}.md"
        ).resolve()

    commands: List[List[str]] = []
    result_dirs: List[Path] = []

    for nind, maxgen in scales:
        cmd = build_run_command(args, nind=nind, maxgen=maxgen)
        commands.append(cmd)
        result_dir = run_single_command(cmd, dry_run=args.dry_run)
        if result_dir is not None:
            result_dirs.append(result_dir)

    if args.dry_run:
        print("\nDry run completed.")
        return

    if not result_dirs:
        raise RuntimeError("No result directories were produced.")

    build_driver_report(output_path, result_dirs, commands)
    print(f"\nSensitivity report written to: {output_path}")


if __name__ == "__main__":
    main()
