import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_design_optimizer import GenericDesignOptimizer
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_generic_design_optimizer_runs_variable_dimension_demo_search():
    optimizer = GenericDesignOptimizer(resolve("songshan_lake_carnot"))

    result = optimizer.run_demo_search(levels=[0.0, 0.5, 1.0])

    assert result["status"] == "build_only"
    assert result["scenario_id"] == "songshan_lake_carnot"
    assert result["capacity_variable_count"] == 10
    assert len(result["solutions"]) == 3
    assert result["solutions"][0]["solution_id"] == 0
    assert result["solutions"][0]["dispatch_solved"] is False
    assert result["solutions"][1]["generic_model"]["capacity_applied"] is True
    assert result["solutions"][1]["capacity_assignment"]["carnot_battery"]["power_kw"] == 250
    assert result["solutions"][2]["capacity_assignment"]["carnot_battery"]["capacity_kwh"] == 3000


def test_generic_design_optimizer_rejects_levels_outside_unit_interval():
    optimizer = GenericDesignOptimizer(resolve("songshan_lake_carnot"))

    try:
        optimizer.run_demo_search(levels=[-0.1])
    except ValueError as exc:
        assert "between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_generic_design_optimizer_can_include_real_electric_dispatch_status():
    optimizer = GenericDesignOptimizer(resolve("songshan_lake"))

    result = optimizer.run_demo_search(
        levels=[0.0],
        project_root=PROJECT_ROOT,
        solve_electric_dispatch=True,
        dispatch_periods=24,
    )

    dispatch = result["solutions"][0]["generic_model"]["real_dispatch"]
    assert dispatch["scope"] == "grid_electric"
    assert dispatch["dispatch_solved"] is True
    assert dispatch["objective_value"] > 0


def test_generic_design_optimizer_can_use_pv_capacity_in_real_electric_dispatch():
    optimizer = GenericDesignOptimizer(resolve("songshan_lake"))

    result = optimizer.run_demo_search(
        levels=[0.1],
        project_root=PROJECT_ROOT,
        solve_electric_dispatch=True,
        electric_dispatch_scope="grid_pv",
        dispatch_periods=24,
    )

    dispatch = result["solutions"][0]["generic_model"]["real_dispatch"]
    assert dispatch["scope"] == "grid_pv_electric"
    assert dispatch["dispatch_solved"] is True
    assert dispatch["pv_capacity_kw"] == 100


def test_generic_design_optimizer_can_use_storage_in_real_electric_dispatch():
    optimizer = GenericDesignOptimizer(resolve("songshan_lake"))

    result = optimizer.run_demo_search(
        levels=[0.5],
        project_root=PROJECT_ROOT,
        solve_electric_dispatch=True,
        electric_dispatch_scope="grid_pv_storage",
        dispatch_periods=24,
    )

    dispatch = result["solutions"][0]["generic_model"]["real_dispatch"]
    assert dispatch["scope"] == "grid_pv_storage_electric"
    assert dispatch["dispatch_solved"] is True
    assert dispatch["storage_power_kw"] == 1000
    assert dispatch["storage_capacity_kwh"] == 2000


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
