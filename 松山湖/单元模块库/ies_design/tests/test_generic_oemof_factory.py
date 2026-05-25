import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generic_oemof_factory import GenericOemofFactory


def test_oemof_factory_binds_applied_capacities_to_node_specs():
    spec = {
        "buses": [{"id": "electricity"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile_ref": "electricity_load"}
        ],
        "components": [
            {
                "id": "pv",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 42},
            },
            {
                "id": "battery",
                "component_type": "GenericStorage",
                "input_carriers": ["electricity"],
                "output_carriers": ["electricity"],
                "capacity_variables": [
                    {"variable_name": "power_kw", "role": "primary_capacity"},
                    {"variable_name": "capacity_kwh", "role": "energy_capacity"},
                ],
                "applied_capacities": {"power_kw": 5, "capacity_kwh": 20},
            },
        ],
    }

    result = GenericOemofFactory.build(spec, periods=3)

    assert result["created"] is True
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["pv"]["outputs"]["electricity"]["nominal_value"] == 42
    assert node_specs["battery"]["inputs"]["electricity"]["nominal_value"] == 5
    assert node_specs["battery"]["outputs"]["electricity"]["nominal_value"] == 5
    assert node_specs["battery"]["nominal_storage_capacity"] == 20
    assert result["energy_system"] is not None


def test_oemof_factory_reports_missing_oemof_without_raising(monkeypatch=None):
    spec = {"buses": [], "components": []}

    result = GenericOemofFactory.build(spec, periods=1)

    assert "created" in result
    assert "error" in result


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
