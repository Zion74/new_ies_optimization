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
    from excel_parser import ExcelScenarioParser
    from typical_day import TypicalDayGenerator
    from generic_backend_planner import GenericBackendPlanner
    from generic_model_builder import GenericModelBuilder
    from generic_design_optimizer import GenericDesignOptimizer

    return (
        ies_dir,
        ScenarioLoader,
        DefaultsResolver,
        SchemaValidator,
        CurrentCCHPAdapter,
        DesignOptimizer,
        ResultExporter,
        ExcelScenarioParser,
        TypicalDayGenerator,
        GenericBackendPlanner,
        GenericModelBuilder,
        GenericDesignOptimizer,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scenario-driven IES design interface")
    parser.add_argument("--scenario", help="Path to scenario.yaml")
    parser.add_argument("--excel", help="Path to collaborator Excel scenario template")
    parser.add_argument("--output", help="Output directory for exported scenario or generated files")
    parser.add_argument("--export-scenario", action="store_true", help="Export parsed Excel scenario package and exit")
    parser.add_argument("--validate-only", action="store_true", help="Validate resolved scenario and exit")
    parser.add_argument("--accept-future", action="store_true", help="Allow future_supported scenarios to pass validation-only checks")
    parser.add_argument("--strict-validation", action="store_true", help="Treat non-runnable validation statuses as failures")
    parser.add_argument("--export-component-plan", action="store_true", help="Export future generic backend component plan and exit")
    parser.add_argument("--build-generic-model", action="store_true", help="Build and export generic model component artifacts and exit")
    parser.add_argument("--run-generic-design", action="store_true", help="Run build-only generic capacity design search and export artifacts")
    parser.add_argument("--generic-search-levels", nargs="+", type=float, help="Unit interval levels for generic build-only design search")
    parser.add_argument("--solve-electric-dispatch", action="store_true", help="Also solve a minimal real-data grid-electric dispatch slice in generic design search")
    parser.add_argument("--electric-dispatch-scope", choices=["grid", "grid_pv", "grid_pv_storage", "grid_pv_storage_heat_cool"], default="grid", help="Optional real dispatch slice scope")
    parser.add_argument("--dispatch-periods", type=int, default=24, help="Number of hours for optional generic dispatch slice")
    parser.add_argument("--print-case-config", action="store_true", help="Print current CCHP case_config summary and exit")
    parser.add_argument("--mode", choices=["test", "demo", "quick", "full", "custom"], help="Override optimization mode")
    parser.add_argument("--nind", type=int, help="Override optimization population size")
    parser.add_argument("--maxgen", type=int, help="Override optimization generations")
    parser.add_argument("--workers", type=int, help="Override optimization worker count")
    parser.add_argument("--methods", nargs="+", help="Override optimization methods")
    parser.add_argument("--dry-run", action="store_true", help="Print optimizer run_config without solving")
    parser.add_argument(
        "--generate-typical-days",
        choices=["monthly_template", "cluster_from_8760"],
        help="Generate typical-day file and report, then exit",
    )
    parser.add_argument("--data-file", help="8760 CSV data file for cluster_from_8760")
    parser.add_argument("--columns", nargs="+", help="Columns used by cluster_from_8760")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.scenario and not args.excel and not args.generate_typical_days:
        parser.error("--scenario or --excel is required")

    root = _project_root()
    (
        ies_dir,
        ScenarioLoader,
        DefaultsResolver,
        SchemaValidator,
        CurrentCCHPAdapter,
        DesignOptimizer,
        ResultExporter,
        ExcelScenarioParser,
        TypicalDayGenerator,
        GenericBackendPlanner,
        GenericModelBuilder,
        GenericDesignOptimizer,
    ) = _load_pipeline(root)

    if args.generate_typical_days:
        output_dir = Path(args.output) if args.output else root / "DesignResults" / "typical_days"
        if args.generate_typical_days == "monthly_template":
            outputs = TypicalDayGenerator.generate_monthly_template(output_dir)
        else:
            if not args.data_file:
                parser.error("--data-file is required for cluster_from_8760")
            outputs = TypicalDayGenerator.cluster_from_8760(
                args.data_file,
                output_dir,
                columns=args.columns,
            )
        print("Typical days generated")
        for name, path in outputs.items():
            print(f"  - {name}: {path}")
        return 0

    if args.excel:
        parsed_excel = ExcelScenarioParser.parse(args.excel)
        output_dir = Path(args.output) if args.output else root / "DesignResults" / "excel_export"
        if args.export_scenario:
            outputs = parsed_excel.export(output_dir)
            print("Excel scenario exported")
            for warning in parsed_excel.warnings:
                print(f"WARNING: {warning}")
            for name, path in outputs.items():
                print(f"  - {name}: {path}")
            return 0
        scenario = parsed_excel.scenario
    else:
        scenario = ScenarioLoader.load(args.scenario)

    if args.mode:
        scenario["optimization"] = {"mode": args.mode}
    _apply_cli_overrides(scenario, args)
    resolved = DefaultsResolver(ies_dir / "defaults").resolve(scenario)
    validation = SchemaValidator.validate(resolved, project_root=root)

    scenario_id = resolved.get("scenario", {}).get("id", "<unknown>")
    template_id = resolved.get("system", {}).get("template", "<unknown>")

    if validation.ok:
        print(f"Validation passed: {scenario_id} ({template_id})")
    else:
        print(f"Validation failed: {scenario_id} ({template_id})")
    print(f"Validation status: {validation.status}")
    if getattr(validation, "backend", ""):
        print(f"Backend: {validation.backend}")
    if getattr(validation, "unsupported_devices", []):
        print(f"Unsupported devices: {validation.unsupported_devices}")
    if getattr(validation, "future_supported_devices", []):
        print(f"Future-supported devices: {validation.future_supported_devices}")
    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    for error in validation.errors:
        print(f"ERROR: {error}")
    if not validation.ok:
        return 2

    if args.export_component_plan:
        output_dir = Path(args.output) if args.output else root / "DesignResults" / "component_plans" / scenario_id
        outputs = GenericBackendPlanner.export(resolved, output_dir)
        print("Generic component plan exported:")
        for name, path in outputs.items():
            print(f"  - {name}: {path}")
        if args.build_generic_model:
            model_outputs = GenericModelBuilder.export(resolved, output_dir)
            print("Generic model build artifacts exported:")
            for name, path in model_outputs.items():
                print(f"  - {name}: {path}")
        return 0

    if args.build_generic_model:
        if validation.status == "future_supported" and not args.accept_future:
            print("Future-supported scenario requires --accept-future for generic model build.")
            return 3
        output_dir = Path(args.output) if args.output else root / "DesignResults" / "generic_models" / scenario_id
        outputs = GenericModelBuilder.export(resolved, output_dir)
        print("Generic model build artifacts exported:")
        for name, path in outputs.items():
            print(f"  - {name}: {path}")
        return 0

    if args.run_generic_design:
        if validation.status == "future_supported" and not args.accept_future:
            print("Future-supported scenario requires --accept-future for generic design search.")
            return 3
        output_dir = Path(args.output) if args.output else root / "DesignResults" / "generic_designs" / scenario_id
        try:
            outputs = GenericDesignOptimizer.export_demo_search(
                resolved,
                output_dir,
                levels=args.generic_search_levels,
                project_root=root,
                solve_electric_dispatch=args.solve_electric_dispatch,
                electric_dispatch_scope=args.electric_dispatch_scope,
                dispatch_periods=args.dispatch_periods,
            )
        except ValueError as exc:
            print(f"Generic design search failed: {exc}")
            return 3
        print("Generic design search artifacts exported:")
        for name, path in outputs.items():
            print(f"  - {name}: {path}")
        return 0

    if args.validate_only:
        if args.strict_validation and not validation.runnable:
            print(f"Strict validation failed: scenario status is {validation.status}, not runnable.")
            return 3
        if validation.status == "future_supported" and not args.accept_future:
            print("Future-supported scenario requires --accept-future for validation-only success.")
            return 3
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
        if not validation.runnable:
            print(
                f"Scenario '{scenario_id}' is {validation.status} and cannot be optimized by the current solver."
            )
            return 3
        run_config = DesignOptimizer.build_run_config(resolved, project_root=root, output_root=args.output)
        if args.dry_run:
            print("optimizer run_config summary")
            print(f"scenario: {run_config['case_config']['name']}")
            print(f"nind: {run_config['nind']}")
            print(f"maxgen: {run_config['maxgen']}")
            print(f"pool_type: {run_config['pool_type']}")
            print(f"inherit_population: {run_config['inherit_population']}")
            print(f"methods_to_run: {run_config['methods_to_run']}")
            print(f"num_workers: {run_config['num_workers']}")
            print(f"result_root: {run_config['result_root']}")
            print(f"result_dir_name: {run_config['result_dir_name']}")
            return 0

        print("Starting optimizer...")
        result = DesignOptimizer.run(resolved, project_root=root, output_root=args.output)
        print(f"Optimization completed: {result['result_dir']}")
        exported = ResultExporter.export(result["result_dir"], resolved, validation=validation)
        print("Design result package exported:")
        for name, path in exported.items():
            print(f"  - {name}: {path}")
        return 0

    print("No execution action selected. Use --validate-only or --print-case-config in this prototype.")
    return 0


def _apply_cli_overrides(scenario: dict, args: argparse.Namespace) -> None:
    optimization = scenario.setdefault("optimization", {})
    if args.nind is not None:
        optimization["nind"] = args.nind
    if args.maxgen is not None:
        optimization["maxgen"] = args.maxgen
    if args.workers is not None:
        optimization["workers"] = args.workers
    if args.methods:
        optimization["methods"] = args.methods


if __name__ == "__main__":
    raise SystemExit(main())
