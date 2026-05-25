import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_dispatch_inputs import GenericDispatchInputs
from generic_oemof_factory import GenericOemofFactory
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_builds_grid_electric_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
    )

    profile = spec["demand_sinks"][0]["profile"]
    grid = spec["components"][0]

    assert spec["buses"] == [{"id": "electricity"}]
    assert len(profile) == 24
    assert profile[0] > 0
    assert grid["id"] == "grid_electricity"
    assert grid["applied_capacities"]["capacity_kw"] >= max(profile)
    assert grid["variable_costs"] == 0.6746


def test_songshan_grid_electric_dispatch_solves_with_real_profile():
    spec = GenericDispatchInputs.build_grid_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
    )

    result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["termination_condition"] == "optimal"
    assert result["objective_value"] > 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
