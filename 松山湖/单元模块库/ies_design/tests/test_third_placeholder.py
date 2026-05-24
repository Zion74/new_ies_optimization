import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver
from schema_validator import SchemaValidator


def test_third_placeholder_is_future_supported_but_not_currently_runnable():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "third_placeholder" / "scenario.yaml")
    resolved = DefaultsResolver(ROOT / "defaults").resolve(scenario)
    validation = SchemaValidator.validate(resolved, project_root=PROJECT_ROOT)

    assert resolved["scenario"]["scenario_type"] == "highway_transport_green_energy"
    assert "hydrogen" in resolved["energy_carriers"]["demands"]
    assert validation.ok is True
    assert validation.status == "future_supported"
    assert validation.runnable is False
    assert "electrolyzer" in validation.future_supported_devices


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
