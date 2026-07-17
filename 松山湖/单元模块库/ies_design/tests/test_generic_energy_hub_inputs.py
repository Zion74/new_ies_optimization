import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_energy_hub_inputs import GenericEnergyHubInputs
from scenario_loader import ScenarioLoader

TOBACCO = ROOT / "scenarios" / "tobacco_factory" / "scenario.yaml"


def resolve_tobacco():
    scenario = ScenarioLoader.load(TOBACCO)
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_tobacco_profiles_load_one_month_with_steam_normalized():
    loaded = GenericEnergyHubInputs.load_monthly_profiles(
        resolve_tobacco(),
        project_root=PROJECT_ROOT,
        month=1,
        periods=24,
    )

    assert len(loaded["demands"]["electricity"]) == 24
    assert len(loaded["demands"]["cooling"]) == 24
    assert len(loaded["demands"]["steam"]) == 24
    assert loaded["units"]["steam"] == "kW_th"
    assert max(loaded["demands"]["steam"]) > 1000


def test_tobacco_resource_profiles_are_loaded_or_synthesized():
    loaded = GenericEnergyHubInputs.load_monthly_profiles(
        resolve_tobacco(),
        project_root=PROJECT_ROOT,
        month=1,
        periods=24,
    )

    assert len(loaded["resources"]["solar_resource"]) == 24
    assert len(loaded["resources"]["waste_heat"]) == 24
    assert len(loaded["resources"]["temperature"]) == 24


def test_tobacco_dispatch_spec_contains_required_buses():
    spec = GenericEnergyHubInputs.build_dispatch_spec(
        resolve_tobacco(),
        project_root=PROJECT_ROOT,
        month=1,
        periods=24,
        capacity_assignment={},
        accept_default_bounds=True,
    )
    buses = {item["id"] for item in spec["buses"]}

    assert {"electricity", "cooling", "steam", "natural_gas", "waste_heat"}.issubset(buses)
    assert any(item["id"] == "steam_demand" for item in spec["demand_sinks"])
    assert any(item["id"] == "steam_boiler" for item in spec["components"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
