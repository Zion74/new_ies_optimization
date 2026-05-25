import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_capacity_space import GenericCapacitySpace
from generic_model_builder import GenericModelBuilder
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_capacity_space_uses_dynamic_variable_count_for_carnot_scene():
    spec = GenericModelBuilder.build(resolve("songshan_lake_carnot"), build_oemof=False)

    space = GenericCapacitySpace.from_model_spec(spec)

    assert len(space.variables) == 10
    assert space.names[-2:] == ["carnot_battery.power_kw", "carnot_battery.capacity_kwh"]
    assert space.upper_bounds[-2:] == [500.0, 3000.0]


def test_capacity_space_maps_vector_to_device_capacities():
    spec = {
        "capacity_variables": [
            {"device_id": "pv", "variable_name": "capacity_kw", "role": "primary_capacity", "unit": "kW", "upper_bound": 100},
            {"device_id": "battery", "variable_name": "power_kw", "role": "primary_capacity", "unit": "kW", "upper_bound": 50},
            {"device_id": "battery", "variable_name": "capacity_kwh", "role": "energy_capacity", "unit": "kWh", "upper_bound": 200},
        ]
    }

    space = GenericCapacitySpace.from_model_spec(spec)
    assignment = space.vector_to_assignment([10, 20, 30])

    assert assignment["pv"]["capacity_kw"] == 10
    assert assignment["battery"]["power_kw"] == 20
    assert assignment["battery"]["capacity_kwh"] == 30


def test_capacity_space_rejects_wrong_vector_length():
    spec = {"capacity_variables": [{"device_id": "pv", "variable_name": "capacity_kw", "upper_bound": 100}]}
    space = GenericCapacitySpace.from_model_spec(spec)

    try:
        space.vector_to_assignment([])
    except ValueError as exc:
        assert "expected 1 capacity values" in str(exc)
    else:
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
