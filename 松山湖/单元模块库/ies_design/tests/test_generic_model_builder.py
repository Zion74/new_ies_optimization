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


def test_generic_model_builder_includes_carnot_capacity_variables():
    spec = GenericModelBuilder.build(resolve("songshan_lake_carnot"), build_oemof=False)

    assert any(component["id"] == "carnot_battery" for component in spec["components"])
    assert any(item["device_id"] == "carnot_battery" and item["role"] == "primary_capacity" for item in spec["capacity_variables"])
    assert any(item["device_id"] == "carnot_battery" and item["role"] == "energy_capacity" for item in spec["capacity_variables"])


def test_generic_model_builder_carries_tobacco_conversion_summary():
    spec = GenericModelBuilder.build(resolve("tobacco_factory"), build_oemof=False)
    summary = spec["conversion_type_summary"]
    abstract_types = {item["abstract_type"] for item in summary["types"]}

    assert summary["type_count"] >= 8
    assert "fuel_to_steam" in abstract_types
    assert "recoverable_energy_to_heat" in abstract_types


def test_generic_model_builder_creates_standard_system_object_for_tobacco():
    spec = GenericModelBuilder.build(resolve("tobacco_factory"), build_oemof=False)

    system = spec["system_object"]

    assert system["schema_version"] == "generic_system_object.v1"
    assert system["scenario"]["id"] == "tobacco_factory_001"
    assert system["backend"]["name"] == "future_generic"
    assert any(bus["id"] == "steam" for bus in system["buses"])
    assert any(
        conn["component_id"] == "steam_boiler" and conn["carrier"] == "steam"
        for conn in system["connections"]
    )
    assert "typical_profiles.csv" in system["time_series_refs"]["load_file"]
    assert "steam_boiler" in system["parameters"]["devices"]
    assert system["conversion_type_summary"]["type_count"] >= 8


def test_generic_model_builder_capacity_variables_use_standard_schema():
    spec = GenericModelBuilder.build(resolve("songshan_lake"), build_oemof=False)

    pv = next(item for item in spec["capacity_variables"] if item["name"] == "pv.capacity_kw")

    assert pv["device_id"] == "pv"
    assert pv["parameter"] == "capacity_kw"
    assert pv["lb"] == 0.0
    assert pv["ub"] > 0
    assert pv["default_value"] == 0.0
    assert pv["is_fixed"] is False
    assert pv["source"] in {"scenario", "library_default", "acceptance_default", "user_input"}
    assert pv["variable_name"] == "capacity_kw"
    assert pv["lower_bound"] == pv["lb"]
    assert pv["upper_bound"] == pv["ub"]


def test_generic_model_builder_exports_standard_system_object():
    with tempfile.TemporaryDirectory() as tmp:
        outputs = GenericModelBuilder.export(resolve("tobacco_factory"), tmp)

        system_object = outputs["system_object"].read_text(encoding="utf-8")

    assert "generic_system_object.v1" in system_object
    assert "tobacco_factory_001" in system_object


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
