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


def test_oemof_factory_solves_minimal_electric_dispatch_with_glpk():
    spec = {
        "buses": [{"id": "electricity"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile": [10, 10, 10]}
        ],
        "components": [
            {
                "id": "grid",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100},
                "variable_costs": 1,
            }
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=3, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["termination_condition"] == "optimal"
    assert result["objective_value"] == 30
    flow_totals = {
        (item["from"], item["to"]): item
        for item in result["dispatch_summary"]["flow_totals"]
    }
    assert flow_totals[("grid", "electricity")]["sum"] == 30
    assert flow_totals[("electricity", "electricity_demand")]["max"] == 10


def test_oemof_factory_exports_storage_content_summary():
    spec = {
        "buses": [{"id": "electricity"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile": [5, 5, 5]}
        ],
        "components": [
            {
                "id": "grid",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100},
                "variable_costs": 1,
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
                "applied_capacities": {"power_kw": 10, "capacity_kwh": 20},
            },
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=3, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    storage = {
        item["storage"]: item
        for item in result["dispatch_summary"]["storage_content"]
    }
    assert storage["battery"]["max"] == 0


def test_oemof_factory_applies_transformer_conversion_factor():
    spec = {
        "buses": [{"id": "electricity"}, {"id": "heat"}],
        "demand_sinks": [
            {"id": "heat_demand", "input_carrier": "heat", "profile": [10, 10, 10]}
        ],
        "components": [
            {
                "id": "grid",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100},
                "variable_costs": 1,
            },
            {
                "id": "electric_heat_pump",
                "component_type": "Transformer",
                "input_carriers": ["electricity"],
                "output_carriers": ["heat"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 10},
                "conversion_factor": 2,
            },
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=3, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["objective_value"] == 15
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["electric_heat_pump"]["conversion_factor"] == 2


def test_oemof_factory_applies_multi_output_transformer_conversion_factors():
    spec = {
        "buses": [{"id": "natural_gas"}, {"id": "electricity"}, {"id": "heat"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile": [4, 4, 4]},
            {"id": "heat_demand", "input_carrier": "heat", "profile": [5, 5, 5]},
        ],
        "components": [
            {
                "id": "gas_source",
                "component_type": "Source",
                "output_carriers": ["natural_gas"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100},
                "variable_costs": 1,
            },
            {
                "id": "chp",
                "component_type": "Transformer",
                "input_carriers": ["natural_gas"],
                "output_carriers": ["electricity", "heat"],
                "capacity_variables": [{"variable_name": "electric_capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"electric_capacity_kw": 10},
                "conversion_factors": {"electricity": 0.4, "heat": 0.5},
            },
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=3, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["chp"]["conversion_factors"] == {"electricity": 0.4, "heat": 0.5}
    flow_totals = {
        (item["from"], item["to"]): item
        for item in result["dispatch_summary"]["flow_totals"]
    }
    assert flow_totals[("chp", "electricity")]["sum"] == 12
    assert flow_totals[("chp", "heat")]["sum"] == 15


def test_oemof_factory_uses_fixed_source_profile_before_costly_grid():
    spec = {
        "buses": [{"id": "electricity"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile": [10, 10, 10]}
        ],
        "components": [
            {
                "id": "pv",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "fixed_profile": [5, 5, 5],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 1},
                "variable_costs": 0,
            },
            {
                "id": "grid",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100},
                "variable_costs": 1,
            },
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=3, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["objective_value"] == 15
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["pv"]["outputs"]["electricity"]["fixed_profile"] == [5, 5, 5]


def test_oemof_factory_solves_multi_carrier_energy_hub():
    spec = {
        "buses": [{"id": "electricity"}, {"id": "natural_gas"}, {"id": "steam"}],
        "demand_sinks": [
            {"id": "electricity_demand", "input_carrier": "electricity", "profile": [10.0] * 24},
            {"id": "steam_demand", "input_carrier": "steam", "profile": [20.0] * 24},
        ],
        "components": [
            {
                "id": "grid_electricity",
                "component_type": "Source",
                "output_carriers": ["electricity"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100.0},
                "variable_costs": 1.0,
            },
            {
                "id": "natural_gas_source",
                "component_type": "Source",
                "output_carriers": ["natural_gas"],
                "capacity_variables": [{"variable_name": "capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"capacity_kw": 100.0},
                "variable_costs": 0.2,
            },
            {
                "id": "steam_boiler",
                "component_type": "Transformer",
                "input_carriers": ["natural_gas"],
                "output_carriers": ["steam"],
                "capacity_variables": [{"variable_name": "steam_capacity_kw", "role": "primary_capacity"}],
                "applied_capacities": {"steam_capacity_kw": 50.0},
                "conversion_factor": 0.9,
            },
        ],
    }

    result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["objective_value"] > 0
    assert any(row["to"] == "steam" for row in result["dispatch_summary"]["flow_totals"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
