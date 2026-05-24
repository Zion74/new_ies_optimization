import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DESIGN = PROJECT_ROOT / "design.py"
SONGSHAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "songshan_lake" / "scenario.yaml"
GERMAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "german" / "scenario.yaml"
EXCEL_TEMPLATE = PROJECT_ROOT / "松山湖" / "单元模块库" / "课题组场景整理模板.xlsx"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(DESIGN), *args],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def run_cli_uv(*args):
    return subprocess.run(
        ["uv", "run", "python", str(DESIGN), *args],
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


def test_mode_quick_uses_mode_default_methods_when_methods_not_overridden():
    result = run_cli("--scenario", str(SONGSHAN), "--mode", "quick", "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nind: 20" in result.stdout
    assert "maxgen: 20" in result.stdout
    assert "methods_to_run: ['std', 'euclidean']" in result.stdout


def test_mode_dry_run_accepts_optimizer_overrides():
    result = run_cli(
        "--scenario", str(SONGSHAN),
        "--mode", "custom",
        "--nind", "12",
        "--maxgen", "7",
        "--workers", "2",
        "--methods", "std", "euclidean",
        "--dry-run",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nind: 12" in result.stdout
    assert "maxgen: 7" in result.stdout
    assert "methods_to_run: ['std', 'euclidean']" in result.stdout
    assert "num_workers: 2" in result.stdout


def test_excel_export_scenario_writes_intermediate_files():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli_uv("--excel", str(EXCEL_TEMPLATE), "--export-scenario", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Excel scenario exported" in result.stdout
        assert (Path(tmp) / "scenario.yaml").exists()
        assert (Path(tmp) / "typical_profiles.csv").exists()
        assert (Path(tmp) / "input_resource_profiles.csv").exists()
        assert (Path(tmp) / "data_gaps.csv").exists()


def test_generate_typical_days_monthly_template():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli("--generate-typical-days", "monthly_template", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Typical days generated" in result.stdout
        assert (Path(tmp) / "typical_days.csv").exists()
        assert (Path(tmp) / "typical_day_report.md").exists()


def test_missing_scenario_argument_fails_cleanly():
    result = run_cli("--validate-only")
    assert result.returncode != 0
    assert "--scenario or --excel is required" in (result.stderr + result.stdout)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
