import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DESIGN = PROJECT_ROOT / "design.py"
SONGSHAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "songshan_lake" / "scenario.yaml"
GERMAN = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "german" / "scenario.yaml"
CARNOT = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "songshan_lake_carnot" / "scenario.yaml"
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


def test_mode_demo_dry_run_uses_demo_defaults():
    result = run_cli("--scenario", str(SONGSHAN), "--mode", "demo", "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "nind: 6" in result.stdout
    assert "maxgen: 3" in result.stdout
    assert "methods_to_run: ['euclidean']" in result.stdout
    assert "num_workers: 2" in result.stdout
    assert "DesignResults" in result.stdout


def test_output_overrides_design_result_root():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli("--scenario", str(SONGSHAN), "--mode", "demo", "--dry-run", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        assert f"result_root: {tmp}" in result.stdout


def test_export_component_plan_for_future_supported_scenario():
    third = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "third_placeholder" / "scenario.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli("--scenario", str(third), "--export-component-plan", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Generic component plan exported" in result.stdout
        assert (Path(tmp) / "generic_component_plan.json").exists()
        assert (Path(tmp) / "generic_component_plan.md").exists()


def test_export_component_plan_for_current_cchp_scenario():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli("--scenario", str(SONGSHAN), "--export-component-plan", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        plan = (Path(tmp) / "generic_component_plan.json").read_text(encoding="utf-8")
        assert '"backend": "current_cchp"' in plan
        assert '"instance_id": "pv"' in plan


def test_build_generic_model_for_future_supported_scenario():
    third = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "third_placeholder" / "scenario.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli("--scenario", str(third), "--build-generic-model", "--accept-future", "--output", tmp)
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Generic model build artifacts exported" in result.stdout
        assert (Path(tmp) / "generic_model_components.json").exists()
        assert (Path(tmp) / "generic_model_build_report.md").exists()
        assert (Path(tmp) / "generic_model_build_gaps.csv").exists()


def test_build_generic_model_requires_accept_future():
    third = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "third_placeholder" / "scenario.yaml"
    result = run_cli("--scenario", str(third), "--build-generic-model")
    assert result.returncode == 3, result.stderr + result.stdout
    assert "--accept-future" in result.stdout


def test_run_generic_design_exports_build_only_search_results():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(CARNOT),
            "--run-generic-design",
            "--generic-search-levels", "0", "0.5", "1",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Generic design search artifacts exported" in result.stdout
        assert (Path(tmp) / "generic_design_solutions.json").exists()
        assert (Path(tmp) / "generic_design_solutions.csv").exists()
        assert (Path(tmp) / "generic_design_report.md").exists()
        report = (Path(tmp) / "generic_design_report.md").read_text(encoding="utf-8")
        assert "build_only" in report
        assert "songshan_lake_carnot" in report


def test_run_generic_design_can_export_real_electric_dispatch_status():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-levels", "0",
            "--solve-electric-dispatch",
            "--dispatch-periods", "24",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        report = (Path(tmp) / "generic_design_report.md").read_text(encoding="utf-8")
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        assert "grid_electric" in report
        assert '"dispatch_solved": true' in data


def test_run_generic_design_can_export_grid_pv_dispatch_status():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-levels", "0.1",
            "--solve-electric-dispatch",
            "--electric-dispatch-scope", "grid_pv",
            "--dispatch-periods", "24",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        assert "grid_pv_electric" in data
        assert '"pv_capacity_kw": 100.0' in data


def test_run_generic_design_can_export_grid_pv_storage_dispatch_status():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-levels", "0.5",
            "--solve-electric-dispatch",
            "--electric-dispatch-scope", "grid_pv_storage",
            "--dispatch-periods", "24",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        assert "grid_pv_storage_electric" in data
        assert '"storage_power_kw": 1000.0' in data
        assert '"storage_capacity_kwh": 2000.0' in data


def test_run_generic_design_can_export_grid_pv_storage_heat_cool_dispatch_status():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-levels", "1.0",
            "--solve-electric-dispatch",
            "--electric-dispatch-scope", "grid_pv_storage_heat_cool",
            "--dispatch-periods", "24",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        assert "grid_pv_storage_heat_cool" in data
        assert '"heat_pump_capacity_kw": 300.0' in data
        assert '"electric_chiller_capacity_kw": 5000.0' in data


def test_run_generic_design_can_export_grid_pv_storage_cchp_dispatch_status():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-levels", "1.0",
            "--solve-electric-dispatch",
            "--electric-dispatch-scope", "grid_pv_storage_cchp",
            "--dispatch-periods", "24",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        assert "grid_pv_storage_cchp" in data
        assert '"chp_capacity_kw": 800.0' in data
        assert '"absorption_chiller_capacity_kw": 1500.0' in data


def test_run_generic_design_can_export_random_capacity_search_results():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-strategy", "random",
            "--generic-candidates", "3",
            "--generic-random-seed", "11",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        report = (Path(tmp) / "generic_design_report.md").read_text(encoding="utf-8")
        assert '"status": "capacity_search"' in data
        assert '"candidate_count": 3' in data
        assert "random" in report


def test_run_generic_design_can_export_de_capacity_search_results():
    with tempfile.TemporaryDirectory() as tmp:
        result = run_cli(
            "--scenario", str(SONGSHAN),
            "--run-generic-design",
            "--generic-search-strategy", "de",
            "--generic-population", "4",
            "--generic-generations", "1",
            "--generic-random-seed", "13",
            "--output", tmp,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        data = (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
        report = (Path(tmp) / "generic_design_report.md").read_text(encoding="utf-8")
        assert '"search_strategy": "differential_evolution"' in data
        assert '"population_size": 4' in data
        assert "best_solution" in data
        assert "differential_evolution" in report


def test_future_supported_validate_only_requires_accept_future():
    third = PROJECT_ROOT / "松山湖" / "单元模块库" / "ies_design" / "scenarios" / "third_placeholder" / "scenario.yaml"
    result = run_cli("--scenario", str(third), "--validate-only")
    assert result.returncode == 3, result.stderr + result.stdout
    assert "--accept-future" in result.stdout

    accepted = run_cli("--scenario", str(third), "--validate-only", "--accept-future")
    assert accepted.returncode == 0, accepted.stderr + accepted.stdout
    assert "Validation status: future_supported" in accepted.stdout


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
