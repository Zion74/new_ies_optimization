import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver
from design_optimizer import DesignOptimizer


def resolve(name: str):
    scenario_path = ROOT / "scenarios" / name / "scenario.yaml"
    scenario = ScenarioLoader.load(scenario_path)
    return DefaultsResolver(ROOT / "defaults").resolve(scenario)


def test_build_run_config_uses_resolved_optimization_defaults():
    resolved = resolve("songshan_lake")

    run_config = DesignOptimizer.build_run_config(resolved, project_root=PROJECT_ROOT)

    assert run_config["nind"] == 10
    assert run_config["maxgen"] == 5
    assert run_config["pool_type"] == "Process"
    assert run_config["inherit_population"] is True
    assert run_config["methods_to_run"] == ["euclidean"]
    assert run_config["case_config"]["name"] == "songshan_lake"
    assert run_config["case_config"]["var_ub"][0] == 1000
    assert run_config["result_root"].endswith("DesignResults")


def test_build_run_config_accepts_output_root():
    resolved = resolve("songshan_lake")

    with tempfile.TemporaryDirectory() as tmp:
        run_config = DesignOptimizer.build_run_config(resolved, project_root=PROJECT_ROOT, output_root=tmp)

        assert run_config["result_root"] == str(Path(tmp))


def test_run_passes_current_cchp_arguments_to_injected_runner():
    resolved = resolve("german")
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {"euclidean": "ok"}, "Results/fake"

    result = DesignOptimizer.run(resolved, project_root=PROJECT_ROOT, runner=fake_runner)

    assert result["result_dir"] == "Results/fake"
    assert result["results"] == {"euclidean": "ok"}
    assert len(calls) == 1
    assert calls[0]["nind"] == 10
    assert calls[0]["maxgen"] == 5
    assert calls[0]["pool_type"] == "Process"
    assert calls[0]["inherit_population"] is True
    assert calls[0]["methods_to_run"] == ["euclidean"]
    assert calls[0]["case_config"]["name"] == "german"
    assert calls[0]["num_workers"] == 4
    assert calls[0]["result_root"].endswith("DesignResults")
    assert calls[0]["result_dir_name"].startswith("design__german__test")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
