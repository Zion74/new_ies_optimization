from __future__ import annotations

import argparse
import runpy
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
IES_DIR = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design"
TEST_DIR = IES_DIR / "tests"
DESIGN = PROJECT_ROOT / "design.py"
SONGSHAN = IES_DIR / "scenarios" / "songshan_lake" / "scenario.yaml"
GERMAN = IES_DIR / "scenarios" / "german" / "scenario.yaml"
THIRD = IES_DIR / "scenarios" / "third_placeholder" / "scenario.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run scenario design interface checks")
    parser.add_argument("--run-demo", action="store_true", help="Run a real demo optimization after fast checks")
    args = parser.parse_args(argv)

    checks = [
        ("default config tests", lambda: _run_test_file(TEST_DIR / "validate_default_configs.py")),
        ("interface unit tests", _run_unit_tests),
        ("songshan validate", lambda: _run_cli("--scenario", str(SONGSHAN), "--validate-only")),
        ("german validate", lambda: _run_cli("--scenario", str(GERMAN), "--validate-only")),
        ("third placeholder validate", lambda: _run_cli("--scenario", str(THIRD), "--validate-only", "--accept-future")),
        ("third placeholder component plan", lambda: _run_cli("--scenario", str(THIRD), "--export-component-plan", "--output", str(PROJECT_ROOT / "DesignResults" / "_check_component_plan"))),
        ("songshan demo dry-run", lambda: _run_cli("--scenario", str(SONGSHAN), "--mode", "demo", "--dry-run")),
        ("german demo dry-run", lambda: _run_cli("--scenario", str(GERMAN), "--mode", "demo", "--dry-run")),
    ]
    if args.run_demo:
        checks.append(("songshan demo solve", lambda: _run_cli("--scenario", str(SONGSHAN), "--mode", "demo")))

    for name, check in checks:
        print(f"== {name} ==")
        check()
    print("ALL DESIGN CHECKS PASSED")
    return 0


def _run_unit_tests() -> None:
    for path in sorted(TEST_DIR.glob("test_*.py")):
        _run_test_file(path)


def _run_test_file(path: Path) -> None:
    runpy.run_path(str(path), run_name="__main__")


def _run_cli(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, str(DESIGN), *args],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
