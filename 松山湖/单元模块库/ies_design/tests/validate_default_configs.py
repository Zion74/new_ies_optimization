from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "defaults"

REQUIRED_FILES = [
    "device_library.yaml",
    "system_templates.yaml",
    "scenario_catalog.yaml",
    "component_mapping.yaml",
    "optimization_defaults.yaml",
]


def read(name: str) -> str:
    path = DEFAULTS / name
    assert path.exists(), f"missing default config: {path}"
    text = path.read_text(encoding="utf-8")
    assert "schema_version" in text, f"{name} missing schema_version"
    return text


def test_default_files_exist_and_are_versioned():
    for name in REQUIRED_FILES:
        read(name)


def test_device_library_contains_current_cchp_devices_and_reserved_future_devices():
    text = read("device_library.yaml")
    for device in [
        "pv_standard",
        "wind_turbine",
        "chp_gas_turbine",
        "electric_heat_pump",
        "electric_chiller",
        "absorption_chiller",
        "electric_storage",
        "heat_storage",
        "cold_storage",
        "carnot_battery",
    ]:
        assert device in text, f"device_library missing implemented device {device}"
    for reserved in ["electrolyzer", "hydrogen_storage", "steam_boiler", "waste_heat_recovery"]:
        assert reserved in text, f"device_library missing reserved device {reserved}"
    assert "backend: current_cchp" in text
    assert "status: reserved" in text


def test_system_templates_include_cchp_and_future_templates():
    text = read("system_templates.yaml")
    for template in [
        "cchp_ehc_base",
        "cchp_ehc_carnot",
        "electric_heat_base",
        "electric_cooling_base",
        "electric_hydrogen_station",
        "industrial_steam_hydrogen_base",
    ]:
        assert template in text, f"system_templates missing {template}"
    assert "decision_variable_order" in text


def test_scenario_catalog_reserves_15_scenarios():
    text = read("scenario_catalog.yaml")
    entries = [line for line in text.splitlines() if line.startswith("  ") and line.rstrip().endswith(":")]
    # Exclude nested keys by checking 2-space indentation only.
    scenario_keys = [line.strip()[:-1] for line in entries if not line.startswith("    ")]
    assert len(scenario_keys) >= 15, f"expected at least 15 scenario types, got {len(scenario_keys)}"
    for key in ["industrial_park_pv_geothermal_waste_heat", "steel_multi_energy", "highway_transport_green_energy"]:
        assert key in text


def test_component_mapping_covers_core_abstract_types():
    text = read("component_mapping.yaml")
    for abstract_type in [
        "external_source",
        "fixed_load",
        "renewable_power",
        "cogeneration",
        "power_to_heat",
        "power_to_cooling",
        "heat_to_cooling",
        "storage",
        "power_to_fuel",
    ]:
        assert abstract_type in text, f"component_mapping missing {abstract_type}"


def test_optimization_defaults_define_modes():
    text = read("optimization_defaults.yaml")
    for mode in ["test", "quick", "full", "custom"]:
        assert f"{mode}:" in text, f"optimization_defaults missing mode {mode}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
