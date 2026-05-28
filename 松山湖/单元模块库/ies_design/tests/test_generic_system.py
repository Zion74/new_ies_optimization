import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_system import GenericSystem
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_generic_system_solves_tobacco_dispatch_with_capacity_assignment():
    system = GenericSystem.from_resolved(resolve("tobacco_factory"), project_root=PROJECT_ROOT)
    capacities = system.default_capacity_assignment(level=1.0, month=1, periods=24, accept_default_bounds=True)

    result = system.solve_dispatch(
        capacities=capacities,
        month=1,
        periods=24,
        accept_default_bounds=True,
    )

    assert result["dispatch_solved"] is True
    assert result["termination_condition"] == "optimal"
    assert result["objective_value"] > 0
    assert result["capacity_assignment"]["pv"]["capacity_kw"] > 0
    assert result["dispatch_summary"]["flow_totals"]
    assert result["energy_flow_summary"] == result["dispatch_summary"]["flow_totals"]


def test_generic_system_accepts_nested_capacity_assignment():
    system = GenericSystem.from_resolved(resolve("songshan_lake"), project_root=PROJECT_ROOT)

    result = system.solve_dispatch(
        capacities={"pv": {"capacity_kw": 100.0}},
        month=1,
        periods=24,
        accept_default_bounds=False,
    )

    assert result["capacity_assignment"]["pv"]["capacity_kw"] == 100
    assert result["dispatch_solved"] is True
    assert result["termination_condition"] == "optimal"


def test_generic_system_rejects_unknown_capacity_variable():
    system = GenericSystem.from_resolved(resolve("tobacco_factory"), project_root=PROJECT_ROOT)

    try:
        system.solve_dispatch({"not_a_device.capacity_kw": 1.0}, accept_default_bounds=True)
    except ValueError as exc:
        assert "unknown capacity variable" in str(exc)
        assert "pv.capacity_kw" in str(exc)
    else:
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
