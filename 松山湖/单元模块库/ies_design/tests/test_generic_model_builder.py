import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_model_builder import GenericModelBuilder
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_generic_model_builder_creates_dynamic_capacity_specs():
    spec = GenericModelBuilder.build(resolve("third_placeholder"), build_oemof=False)

    assert spec["scenario"]["id"] == "third_placeholder_hydrogen_station"
    assert any(bus["id"] == "hydrogen" for bus in spec["buses"])
    assert any(component["id"] == "electrolyzer" for component in spec["components"])
    assert any(item["device_id"] == "electrolyzer" for item in spec["capacity_variables"])
    assert spec["next_step"].startswith("connect capacity_variables")


def test_generic_model_builder_exports_reports():
    with tempfile.TemporaryDirectory() as tmp:
        outputs = GenericModelBuilder.export(resolve("songshan_lake_carnot"), tmp)
        components = outputs["generic_model_components"].read_text(encoding="utf-8")
        report = outputs["generic_model_build_report"].read_text(encoding="utf-8")

    assert "songshan_lake_carnot" in components
    assert "capacity_variables" in components
    assert "GenericModelBuilder 构建报告" in report
    assert "动态容量变量" in report


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")

