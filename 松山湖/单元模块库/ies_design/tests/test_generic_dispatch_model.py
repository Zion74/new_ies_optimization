import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_dispatch_model import GenericDispatchModel
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_dispatch_model_evaluates_capacity_vector_with_dynamic_assignment():
    model = GenericDispatchModel(resolve("songshan_lake_carnot"))
    vector = [ub * 0.1 for ub in model.capacity_space.upper_bounds]

    result = model.evaluate(vector)

    assert result["status"] == "build_only"
    assert result["dispatch_solved"] is False
    assert result["capacity_assignment"]["carnot_battery"]["power_kw"] == 50
    assert result["capacity_assignment"]["carnot_battery"]["capacity_kwh"] == 300
    assert result["investment_cost"] > 0
    assert "generic_model" in result


def test_dispatch_model_applies_capacity_vector_to_component_specs():
    model = GenericDispatchModel(resolve("songshan_lake_carnot"))
    vector = [ub * 0.5 for ub in model.capacity_space.upper_bounds]

    result = model.evaluate(vector)

    components = {
        item["id"]: item
        for item in result["generic_model"]["components"]
    }
    assert result["generic_model"]["capacity_applied"] is True
    assert components["pv"]["applied_capacities"]["capacity_kw"] == 500
    assert components["chp"]["applied_capacities"]["electric_capacity_kw"] == 400
    assert components["carnot_battery"]["applied_capacities"]["power_kw"] == 250
    assert components["carnot_battery"]["applied_capacities"]["capacity_kwh"] == 1500


def test_dispatch_model_builds_oemof_nodes_from_applied_capacities():
    model = GenericDispatchModel(resolve("songshan_lake_carnot"))
    vector = [ub * 0.5 for ub in model.capacity_space.upper_bounds]

    result = model.evaluate(vector)

    oemof = result["generic_model"]["oemof"]
    assert oemof["created"] is True
    assert oemof["node_count"] > 0
    node_specs = {item["id"]: item for item in oemof["node_specs"]}
    assert node_specs["pv"]["outputs"]["electricity"]["nominal_value"] == 500


def test_dispatch_model_rejects_wrong_vector_length():
    model = GenericDispatchModel(resolve("songshan_lake_carnot"))

    try:
        model.evaluate([])
    except ValueError as exc:
        assert "expected" in str(exc)
    else:
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
