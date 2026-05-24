import sys
import tempfile
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


def test_generic_backend_planner_exports_json_and_markdown():
    scenario = ScenarioLoader.load(ROOT / "scenarios" / "third_placeholder" / "scenario.yaml")
    resolved = DefaultsResolver(ROOT / "defaults").resolve(scenario)

    with tempfile.TemporaryDirectory() as tmp:
        outputs = GenericBackendPlanner.export(resolved, tmp)
        json_text = outputs["component_plan_json"].read_text(encoding="utf-8")
        markdown = outputs["component_plan_report"].read_text(encoding="utf-8")

    assert '"readiness_status": "planned_not_solved"' in json_text
    assert '"instance_id": "electrolyzer"' in json_text
    assert "通用后端组件映射计划" in markdown
    assert "electrolyzer" in markdown


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
