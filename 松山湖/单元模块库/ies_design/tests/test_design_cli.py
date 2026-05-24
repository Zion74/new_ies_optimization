import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DESIGN = PROJECT_ROOT / "design.py"
SONGSHAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "songshan_lake" / "scenario.yaml"
GERMAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "german" / "scenario.yaml"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(DESIGN), *args],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def test_validate_only_songshan_succeeds():
    result = run_cli("--scenario", str(SONGSHAN), "--validate-only")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Validation passed" in result.stdout
    assert "songshan_lake" in result.stdout


def test_print_case_config_german_outputs_core_fields():
    result = run_cli("--scenario", str(GERMAN), "--print-case-config")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "case_config summary" in result.stdout
    assert "name: german" in result.stdout
    assert "var_ub:" in result.stdout
    assert "capacity_charge: 114.29" in result.stdout


def test_mode_test_dry_run_prints_optimizer_run_config():
    result = run_cli("--scenario", str(SONGSHAN), "--mode", "test", "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "optimizer run_config summary" in result.stdout
    assert "scenario: songshan_lake" in result.stdout
    assert "nind: 10" in result.stdout
    assert "maxgen: 5" in result.stdout
    assert "methods_to_run: ['euclidean']" in result.stdout


def test_missing_scenario_argument_fails_cleanly():
    result = run_cli("--validate-only")
    assert result.returncode != 0
    assert "--scenario is required" in (result.stderr + result.stdout)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
