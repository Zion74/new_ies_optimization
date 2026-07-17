import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from json_schema_validator import JsonSchemaValidator
from scenario_loader import ScenarioLoader


def test_json_schema_accepts_songshan_scenario():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "songshan_lake" / "scenario.yaml")

    errors = JsonSchemaValidator.validate(scenario)

    assert errors == []


def test_json_schema_rejects_missing_scenario_id():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "songshan_lake" / "scenario.yaml")
    broken = copy.deepcopy(scenario)
    del broken["scenario"]["id"]

    errors = JsonSchemaValidator.validate(broken)

    assert any("scenario.id" in error or "'id' is a required property" in error for error in errors)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")

