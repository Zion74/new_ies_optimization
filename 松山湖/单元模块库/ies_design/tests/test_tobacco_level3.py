import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from defaults_resolver import DefaultsResolver
from generic_design_optimizer import GenericDesignOptimizer
from generic_dispatch_model import GenericDispatchModel
from scenario_loader import ScenarioLoader

TOBACCO = ROOT / "scenarios" / "tobacco_factory" / "scenario.yaml"


def resolve_tobacco():
    scenario = ScenarioLoader.load(TOBACCO)
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_tobacco_generic_dispatch_solves_one_month_with_defaults():
    model = GenericDispatchModel(resolve_tobacco())
    vector = model.capacity_space.upper_bounds

    result = model.evaluate(
        vector,
        project_root=str(PROJECT_ROOT),
        solve_generic_dispatch=True,
        dispatch_periods=24,
        dispatch_month=1,
        accept_default_bounds=True,
    )

    dispatch = result["generic_model"]["real_dispatch"]
    assert result["dispatch_solved"] is True
    assert dispatch["scope"] == "linear_energy_hub"
    assert dispatch["objective_value"] > 0
    assert any(row["to"] == "steam" for row in dispatch["dispatch_summary"]["flow_totals"])


def test_tobacco_generic_design_search_uses_real_dispatch_objective():
    optimizer = GenericDesignOptimizer(resolve_tobacco())

    result = optimizer.run_demo_search(
        levels=[1.0],
        project_root=PROJECT_ROOT,
        solve_generic_dispatch=True,
        dispatch_periods=24,
        dispatch_month=1,
        accept_default_bounds=True,
    )

    solution = result["solutions"][0]
    assert solution["dispatch_solved"] is True
    assert solution["dispatch_objective"] > 0
    assert solution["total_objective"] >= solution["dispatch_objective"]


def test_tobacco_export_writes_level3_acceptance_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        outputs = GenericDesignOptimizer.export_demo_search(
            resolve_tobacco(),
            tmp,
            levels=[1.0],
            project_root=PROJECT_ROOT,
            solve_generic_dispatch=True,
            dispatch_periods=24,
            dispatch_month=1,
            accept_default_bounds=True,
        )

        expected = [
            "capacity_solution",
            "dispatch_summary",
            "energy_flow_summary",
            "conversion_type_summary",
        ]
        for key in expected:
            assert key in outputs
            assert outputs[key].exists()

        capacity_text = outputs["capacity_solution"].read_text(encoding="utf-8-sig")
        flow_text = outputs["energy_flow_summary"].read_text(encoding="utf-8-sig")
        conversion_text = outputs["conversion_type_summary"].read_text(encoding="utf-8-sig")
        report_text = outputs["generic_design_report"].read_text(encoding="utf-8")

        assert "steam_boiler" in capacity_text
        assert "steam" in flow_text
        assert "fuel_to_steam" in conversion_text
        assert "Level 3" in report_text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
