from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _ies_design_dir(root: Path) -> Path:
    return root / "松山湖" / "单元模块库" / "ies_design"


def _load_pipeline(root: Path):
    ies_dir = _ies_design_dir(root)
    sys.path.insert(0, str(ies_dir))
    from scenario_loader import ScenarioLoader
    from defaults_resolver import DefaultsResolver
    from schema_validator import SchemaValidator
    from current_cchp_adapter import CurrentCCHPAdapter
    from design_optimizer import DesignOptimizer
    from result_exporter import ResultExporter

    return ies_dir, ScenarioLoader, DefaultsResolver, SchemaValidator, CurrentCCHPAdapter, DesignOptimizer, ResultExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scenario-driven IES design interface")
    parser.add_argument("--scenario", help="Path to scenario.yaml")
    parser.add_argument("--validate-only", action="store_true", help="Validate resolved scenario and exit")
    parser.add_argument("--print-case-config", action="store_true", help="Print current CCHP case_config summary and exit")
    parser.add_argument("--mode", choices=["test", "quick", "full", "custom"], help="Override optimization mode")
    parser.add_argument("--dry-run", action="store_true", help="Print optimizer run_config without solving")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.scenario:
        parser.error("--scenario is required for this first design.py prototype")

    root = _project_root()
    (
        ies_dir,
        ScenarioLoader,
        DefaultsResolver,
        SchemaValidator,
        CurrentCCHPAdapter,
        DesignOptimizer,
        ResultExporter,
    ) = _load_pipeline(root)

    scenario = ScenarioLoader.load(args.scenario)
    if args.mode:
        scenario.setdefault("optimization", {})["mode"] = args.mode
    resolved = DefaultsResolver(ies_dir / "defaults").resolve(scenario)
    validation = SchemaValidator.validate(resolved, project_root=root)

    scenario_id = resolved.get("scenario", {}).get("id", "<unknown>")
    template_id = resolved.get("system", {}).get("template", "<unknown>")

    if validation.ok:
        print(f"Validation passed: {scenario_id} ({template_id})")
    else:
        print(f"Validation failed: {scenario_id} ({template_id})")
    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    for error in validation.errors:
        print(f"ERROR: {error}")
    if not validation.ok:
        return 2

    if args.validate_only:
        return 0

    if args.print_case_config:
        config = CurrentCCHPAdapter.to_case_config(resolved, project_root=root)
        print("case_config summary")
        print(f"name: {config['name']}")
        print(f"currency: {config['currency']}")
        print(f"data_file: {config['data_file']}")
        print(f"typical_day_file: {config['typical_day_file']}")
        print(f"var_ub: {config['var_ub']}")
        print(f"invest_coeff: {config['invest_coeff']}")
        print(f"capacity_charge: {config['capacity_charge']}")
        print(f"enable_carnot_battery: {config['enable_carnot_battery']}")
        return 0

    if args.mode:
        run_config = DesignOptimizer.build_run_config(resolved, project_root=root)
        if args.dry_run:
            print("optimizer run_config summary")
            print(f"scenario: {run_config['case_config']['name']}")
            print(f"nind: {run_config['nind']}")
            print(f"maxgen: {run_config['maxgen']}")
            print(f"pool_type: {run_config['pool_type']}")
            print(f"inherit_population: {run_config['inherit_population']}")
            print(f"methods_to_run: {run_config['methods_to_run']}")
            print(f"num_workers: {run_config['num_workers']}")
            print(f"result_dir_name: {run_config['result_dir_name']}")
            return 0

        print("Starting optimizer...")
        result = DesignOptimizer.run(resolved, project_root=root)
        print(f"Optimization completed: {result['result_dir']}")
        exported = ResultExporter.export(result["result_dir"], resolved, validation=validation)
        print("Design result package exported:")
        for name, path in exported.items():
            print(f"  - {name}: {path}")
        return 0

    print("No execution action selected. Use --validate-only or --print-case-config in this prototype.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
