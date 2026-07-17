import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver
from current_cchp_adapter import CurrentCCHPAdapter
from case_config import get_case


def resolve(name: str):
    scenario_path = ROOT / "scenarios" / name / "scenario.yaml"
    scenario = ScenarioLoader.load(scenario_path)
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_songshan_adapter_matches_existing_case_config_core_fields():
    resolved = resolve("songshan_lake")
    config = CurrentCCHPAdapter.to_case_config(resolved, project_root=PROJECT_ROOT)
    expected = get_case("songshan_lake")

    assert config["name"] == "songshan_lake"
    assert config["currency"] == "¥"
    assert config["data_file"] == expected["data_file"]
    assert config["typical_day_file"] == expected["typical_day_file"]
    assert config["ele_price"] == expected["ele_price"]
    assert config["gas_price"] == expected["gas_price"]
    assert config["capacity_charge"] == expected["capacity_charge"]
    assert config["var_ub"] == expected["var_ub"]
    assert config["invest_coeff"] == expected["invest_coeff"]
    assert config["gt_eta_e"] == expected["gt_eta_e"]
    assert config["gt_eta_h"] == expected["gt_eta_h"]
    assert config["ec_cop"] == expected["ec_cop"]
    assert config["enable_carnot_battery"] is False
    assert round(config["lambda_h"], 6) == round(expected["lambda_h"], 6)


def test_german_adapter_matches_existing_case_config_core_fields():
    resolved = resolve("german")
    config = CurrentCCHPAdapter.to_case_config(resolved, project_root=PROJECT_ROOT)
    expected = get_case("german")

    assert config["name"] == "german"
    assert config["currency"] == "€"
    assert config["data_file"] == expected["data_file"]
    assert config["typical_day_file"] == expected["typical_day_file"]
    assert config["ele_price"] == expected["ele_price"]
    assert config["gas_price"] == expected["gas_price"]
    assert config["capacity_charge"] == expected["capacity_charge"]
    assert config["var_ub"] == expected["var_ub"]
    assert config["invest_coeff"] == expected["invest_coeff"]
    assert config["gt_eta_e"] == expected["gt_eta_e"]
    assert config["gt_eta_h"] == expected["gt_eta_h"]
    assert config["ehp_cop"] == expected["ehp_cop"]
    assert config["ec_cop"] == expected["ec_cop"]


def test_carnot_adapter_enables_extra_bounds_when_template_requests_it():
    resolved = resolve("songshan_lake")
    resolved["system"]["template"] = "cchp_ehc_carnot"
    resolved["system_template"] = DefaultsResolver(ROOT / "defaults")._expand_template(
        "cchp_ehc_carnot",
        DefaultsResolver(ROOT / "defaults").system_templates["templates"],
    )
    resolved["carnot_battery"]["enabled"] = True

    config = CurrentCCHPAdapter.to_case_config(resolved, project_root=PROJECT_ROOT)

    assert config["enable_carnot_battery"] is True
    assert config["cb_power_ub"] == 500
    assert config["cb_capacity_ub"] == 3000
    assert config["cb_rte"] == 0.60


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
