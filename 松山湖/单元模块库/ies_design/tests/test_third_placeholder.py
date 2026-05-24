import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver
from schema_validator import SchemaValidator


def test_third_placeholder_is_reserved_but_not_current_cchp_runnable():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "third_placeholder" / "scenario.yaml")
    resolved = DefaultsResolver(ROOT / "defaults").resolve(scenario)
    validation = SchemaValidator.validate(resolved, project_root=PROJECT_ROOT)

    assert resolved["scenario"]["scenario_type"] == "highway_transport_green_energy"
    assert "hydrogen" in resolved["energy_carriers"]["demands"]
    assert validation.ok is False
    assert any("electrolyzer" in error and "current_cchp" in error for error in validation.errors)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
