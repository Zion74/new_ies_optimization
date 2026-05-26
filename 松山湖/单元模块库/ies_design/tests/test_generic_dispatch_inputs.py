import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_dispatch_inputs import GenericDispatchInputs
from generic_oemof_factory import GenericOemofFactory
from scenario_loader import ScenarioLoader


def resolve(name: str):
    scenario = ScenarioLoader.load(ROOT / "scenarios" / name / "scenario.yaml")
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_builds_grid_electric_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
    )

    profile = spec["demand_sinks"][0]["profile"]
    grid = spec["components"][0]

    assert spec["buses"] == [{"id": "electricity"}]
    assert len(profile) == 24
    assert profile[0] > 0
    assert grid["id"] == "grid_electricity"
    assert grid["applied_capacities"]["capacity_kw"] >= max(profile)
    assert grid["variable_costs"] == 0.6746


def test_songshan_grid_electric_dispatch_solves_with_real_profile():
    spec = GenericDispatchInputs.build_grid_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
    )

    result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    assert result["termination_condition"] == "optimal"
    assert result["objective_value"] > 0


def test_builds_grid_pv_electric_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_pv_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=100,
    )

    components = {item["id"]: item for item in spec["components"]}
    pv_profile = components["pv"]["fixed_profile"]

    assert "electricity_spill" in [item["id"] for item in spec["demand_sinks"]]
    assert len(pv_profile) == 24
    assert max(pv_profile) > 0
    assert components["pv"]["applied_capacities"]["capacity_kw"] == 100
    assert components["grid_electricity"]["variable_costs"] == 0.6746


def test_songshan_grid_pv_dispatch_reduces_grid_purchase_cost():
    resolved = resolve("songshan_lake")
    grid_only = GenericDispatchInputs.build_grid_electric_spec(
        resolved,
        project_root=PROJECT_ROOT,
        periods=24,
    )
    with_pv = GenericDispatchInputs.build_grid_pv_electric_spec(
        resolved,
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=100,
    )

    grid_result = GenericOemofFactory.solve_dispatch(grid_only, periods=24, solver_names=["glpk"])
    pv_result = GenericOemofFactory.solve_dispatch(with_pv, periods=24, solver_names=["glpk"])

    assert grid_result["dispatch_solved"] is True
    assert pv_result["dispatch_solved"] is True
    assert pv_result["objective_value"] < grid_result["objective_value"]


def test_builds_grid_pv_storage_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_pv_storage_electric_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=100,
        storage_power_kw=10,
        storage_capacity_kwh=20,
    )

    components = {item["id"]: item for item in spec["components"]}
    storage = components["electric_storage"]

    assert components["electricity_spill"]["component_type"] == "Sink"
    assert storage["component_type"] == "GenericStorage"
    assert storage["applied_capacities"]["power_kw"] == 10
    assert storage["applied_capacities"]["capacity_kwh"] == 20
    assert storage["charge_efficiency"] == 0.95
    assert storage["discharge_efficiency"] == 0.95


def test_songshan_grid_pv_storage_dispatch_solves_with_storage_capacity():
    resolved = resolve("songshan_lake")
    with_storage = GenericDispatchInputs.build_grid_pv_storage_electric_spec(
        resolved,
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=1000,
        storage_power_kw=100,
        storage_capacity_kwh=200,
    )

    result = GenericOemofFactory.solve_dispatch(with_storage, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["electric_storage"]["nominal_storage_capacity"] == 200


def test_builds_grid_pv_storage_heat_cool_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_pv_storage_heat_cool_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=100,
        storage_power_kw=10,
        storage_capacity_kwh=20,
        heat_pump_capacity_kw=300,
        electric_chiller_capacity_kw=5000,
    )

    buses = [item["id"] for item in spec["buses"]]
    demands = {item["id"]: item for item in spec["demand_sinks"]}
    components = {item["id"]: item for item in spec["components"]}

    assert "heat" in buses
    assert "cooling" in buses
    assert len(demands["heat_demand"]["profile"]) == 24
    assert len(demands["cooling_demand"]["profile"]) == 24
    assert components["electric_heat_pump"]["conversion_factor"] == 4.0
    assert components["electric_chiller"]["conversion_factor"] == 5.5


def test_songshan_grid_pv_storage_heat_cool_dispatch_solves():
    spec = GenericDispatchInputs.build_grid_pv_storage_heat_cool_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=1000,
        storage_power_kw=100,
        storage_capacity_kwh=200,
        heat_pump_capacity_kw=300,
        electric_chiller_capacity_kw=5000,
    )

    result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    flow_totals = {
        (item["from"], item["to"]): item
        for item in result["dispatch_summary"]["flow_totals"]
    }
    assert ("electric_heat_pump", "heat") in flow_totals
    assert ("electric_chiller", "cooling") in flow_totals


def test_builds_grid_pv_storage_cchp_dispatch_spec_from_songshan_real_data():
    spec = GenericDispatchInputs.build_grid_pv_storage_cchp_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=100,
        storage_power_kw=10,
        storage_capacity_kwh=20,
        heat_pump_capacity_kw=300,
        electric_chiller_capacity_kw=5000,
        chp_capacity_kw=800,
        absorption_chiller_capacity_kw=1500,
    )

    buses = [item["id"] for item in spec["buses"]]
    components = {item["id"]: item for item in spec["components"]}

    assert "natural_gas" in buses
    assert components["natural_gas_source"]["variable_costs"] == 0.45
    assert components["chp"]["conversion_factors"] == {"electricity": 0.423, "heat": 0.42}
    assert components["absorption_chiller"]["conversion_factor"] == 0.70


def test_songshan_grid_pv_storage_cchp_dispatch_solves():
    spec = GenericDispatchInputs.build_grid_pv_storage_cchp_spec(
        resolve("songshan_lake"),
        project_root=PROJECT_ROOT,
        periods=24,
        pv_capacity_kw=1000,
        storage_power_kw=100,
        storage_capacity_kwh=200,
        heat_pump_capacity_kw=300,
        electric_chiller_capacity_kw=5000,
        chp_capacity_kw=800,
        absorption_chiller_capacity_kw=1500,
    )

    result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])

    assert result["dispatch_solved"] is True
    node_specs = {item["id"]: item for item in result["node_specs"]}
    assert node_specs["chp"]["conversion_factors"]["electricity"] == 0.423
    assert node_specs["absorption_chiller"]["conversion_factor"] == 0.70


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
