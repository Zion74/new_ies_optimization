import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_backend_planner import GenericBackendPlanner
from scenario_loader import ScenarioLoader


def test_generic_backend_planner_maps_hydrogen_placeholder():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "third_placeholder" / "scenario.yaml")
    resolved = DefaultsResolver(ROOT / "defaults").resolve(scenario)

    plan = GenericBackendPlanner.plan(resolved)

    assert "hydrogen" in plan["buses"]
    assert "electricity" in plan["buses"]
    assert plan["missing_mappings"] == []
    assert any(component["instance_id"] == "electrolyzer" for component in plan["components"])
    assert any(component["component_type"] == "Transformer" for component in plan["components"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")

