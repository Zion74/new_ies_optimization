import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver


def resolve(name: str):
    scenario_path = ROOT / "scenarios" / name / "scenario.yaml"
    scenario = ScenarioLoader.load(scenario_path)
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_resolves_songshan_lake_with_default_devices_and_prices():
    resolved = resolve("songshan_lake")
    assert resolved["schema_version"] == "1.0"
    assert resolved["scenario"]["id"] == "songshan_lake"
    assert resolved["system"]["template"] == "cchp_ehc_base"
    assert resolved["devices"]["pv"]["library_id"] == "pv_standard"
    assert resolved["devices"]["pv"]["input_carriers"] == ["solar_resource", "temperature"]
    assert resolved["devices"]["wind"]["enabled"] is False
    assert resolved["prices"]["capacity_charge"]["value"] == 0
    assert resolved["optimization"]["nind"] == 10


def test_resolves_german_with_wind_and_capacity_charge():
    resolved = resolve("german")
    assert resolved["scenario"]["id"] == "german"
    assert resolved["scenario"]["currency"] == "EUR"
    assert resolved["devices"]["wind"]["enabled"] is True
    assert resolved["devices"]["wind"]["capacity_ub_kw"] == 10000
    assert resolved["prices"]["capacity_charge"]["value"] == 114.29
    assert resolved["data"]["load_file"].endswith("data/mergedData.csv")


def test_resolves_songshan_lake_carnot_as_third_computable_scenario():
    resolved = resolve("songshan_lake_carnot")
    assert resolved["scenario"]["id"] == "songshan_lake_carnot"
    assert resolved["system"]["template"] == "cchp_ehc_carnot"
    assert resolved["system_template"]["supported_backend"] == "current_cchp"
    assert resolved["carnot_battery"]["enabled"] is True
    assert resolved["carnot_battery"]["power_ub_kw"] == 500
    assert "carnot_battery" in resolved["system_template"]["default_devices"]


def test_reserved_device_metadata_is_available_but_not_enabled_for_cchp():
    resolved = resolve("songshan_lake")
    assert "electrolyzer" in resolved["device_library"]["devices"]
    assert resolved["device_library"]["devices"]["electrolyzer"]["implementation"]["status"] == "reserved"
    assert "electrolyzer" not in resolved["devices"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
