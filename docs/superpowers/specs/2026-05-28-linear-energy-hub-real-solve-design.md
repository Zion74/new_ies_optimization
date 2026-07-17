# Linear Energy Hub Real-Solve Generic Backend Design

## Goal

Build a real solving `future_generic` backend based on a linear Energy Hub model so the tobacco factory scenario can become the third computable acceptance scenario, and so future 15 or larger batches of scenarios can be connected with minimal Python changes.

## Confirmed Direction

- The third scenario must be genuinely solvable, not only mappable to a component plan.
- The generic backend is the priority path for future scenario expansion.
- The old CCHP research code remains available for Songshan Lake and German cases, but new industrial, steam, hydrogen, gas-demand, and resource-recovery scenarios should not be forced into `current_cchp`.
- Device modeling depth follows a linear Energy Hub abstraction first: input/output carriers, conversion efficiencies or COP, capacity limits, and storage SOC dynamics.
- New scenario onboarding should prefer configuration changes over Python code changes. Python changes are reserved for genuinely new abstract component types or solver capabilities.

## Acceptance Target

A scenario reaches real-solve acceptance when the pipeline can:

1. Parse Excel or YAML into a resolved scenario.
2. Validate carriers, units, devices, prices, capacity bounds, and time-series data.
3. Map every enabled device to a generic component type.
4. Normalize all carrier units into solver-compatible units.
5. Generate capacity variables with lower and upper bounds.
6. Given a capacity vector, solve a linear dispatch model for the selected typical-day or horizon.
7. Run an outer capacity search and return ranked capacity configurations.
8. Export capacity results, dispatch summaries, conversion-type summaries, and clear data/parameter gaps.

For the tobacco factory scenario, the first real-solve version uses monthly typical days and covers electricity, cooling, steam, natural gas, solar resource, and waste heat.

## Architecture

```text
Excel / YAML scenario
  -> ScenarioLoader / ExcelScenarioParser
  -> DefaultsResolver
  -> DataQualityReporter
  -> CarrierUnitRegistry / UnitNormalizer
  -> GenericBackendPlanner
  -> GenericModelBuilder
  -> GenericDispatchModel
  -> GenericDesignOptimizer
  -> ResultExporter
```

### Responsibilities

- `ScenarioLoader` and `ExcelScenarioParser` read user-provided files and create the standard scenario object.
- `DefaultsResolver` merges system templates, device-library defaults, and user overrides.
- `DataQualityReporter` checks profile completeness, duplicated records, missing hours, price format, and resource availability.
- `CarrierUnitRegistry` defines user-facing units, internal solver units, and conversion rules for each carrier.
- `UnitNormalizer` converts loads, resources, prices, and capacity bounds into solver-compatible units.
- `GenericBackendPlanner` maps enabled devices to abstract component types and reports conversion-type statistics.
- `GenericModelBuilder` builds a backend-neutral linear Energy Hub model specification.
- `GenericDispatchModel` applies a capacity vector and solves dispatch for a typical-day horizon.
- `GenericDesignOptimizer` generates capacity candidates and calls `GenericDispatchModel.evaluate()`.
- `ResultExporter` writes human-facing and machine-facing results.

## Scenario Readiness Levels

Every scenario is classified into one of four levels. This makes batch onboarding less error-prone.

| Level | Name | Meaning | Required output |
|---|---|---|---|
| 0 | Parsed | Excel/YAML can be read into the standard scenario object. | parse warnings and normalized scenario package |
| 1 | Mapped | All enabled devices map to abstract component types. | component plan and conversion-type summary |
| 2 | Buildable | Units, profiles, capacity variables, and model specification are valid. | model spec and build gaps |
| 3 | Solvable | Dispatch and capacity search run successfully. | capacity solution, dispatch summary, design report |

The tobacco factory scenario must reach Level 3 for the next acceptance milestone.

## Linear Energy Hub Model

The first real generic backend solves a linear model. It does not attempt nonlinear equipment physics or detailed off-design operation.

### Generic Sets

- Time steps: selected dispatch horizon, initially 24 hours per monthly typical day.
- Carriers: electricity, heat, cooling, steam, natural gas, hydrogen, waste heat, and scenario-specific carriers.
- Devices: enabled devices from the resolved scenario.
- Capacity variables: generated from device capacity metadata.

### Core Variables

- Device input flow per input carrier and time step.
- Device output flow per output carrier and time step.
- Storage charge, discharge, and state of charge.
- External purchase or curtailment flows where configured.
- Capacity variables supplied by the outer optimizer or fixed by user input.

### Core Constraints

- Carrier balance for every demand carrier and time step.
- External source upper bounds and purchase costs.
- Renewable output limited by capacity and resource profile.
- Transformer output equals input multiplied by efficiency or COP.
- CHP output uses fixed electricity and heat conversion factors in the first version.
- Waste heat recovery output is limited by waste heat resource profile and installed capacity.
- Storage SOC follows linear charge/discharge dynamics and capacity limits.
- Device dispatch flows are bounded by installed capacity.

### Objective

For dispatch evaluation, minimize operating cost for the given capacity vector:

```text
operating_cost = electricity_purchase_cost + fuel_purchase_cost + optional_emission_cost + unmet_load_penalty + curtailment_penalty
```

The outer capacity optimizer evaluates:

```text
total_cost = annualized_investment_cost + weighted_annual_operating_cost
```

A second objective can be added in a follow-up milestone for emissions, source-load matching, renewable utilization, or energy quality matching. The first Level 3 acceptance can remain single-objective if the output clearly reports that the generic backend is a real solving backend.

## Device Abstract Types

The first generic solver supports these abstract types:

| Abstract type | Solver behavior |
|---|---|
| `external_source` | Purchasable carrier source with price and optional upper bound. |
| `renewable_power` | Output equals capacity times normalized resource profile. |
| `renewable_heat` | Heat output limited by resource profile and capacity. |
| `power_to_heat` | Heat output equals electricity input times COP. |
| `power_to_cooling` | Cooling output equals electricity input times COP. |
| `heat_to_cooling` | Cooling output equals heat input times COP. |
| `fuel_to_heat` | Heat output equals fuel input times efficiency. |
| `fuel_to_steam` | Steam output equals fuel input times efficiency after unit normalization. |
| `cogeneration` | Fuel input produces fixed-ratio electricity and heat outputs. |
| `recoverable_energy_to_heat` | Waste heat resource is converted to heat or steam within capacity/resource limits. |
| `storage` | Same-carrier storage with charge/discharge efficiency and SOC state. |

Unsupported abstract types block Level 3 and produce explicit gaps.

## Unit Normalization

The generic solver operates on consistent internal units.

| Carrier | Common user unit | Internal solver unit | Rule |
|---|---|---|---|
| electricity | kW, kWh | kW, kWh | direct |
| heat | kW, kWh | kW, kWh | direct |
| cooling | kW, kWh | kW, kWh | direct |
| steam | t/h, kg/h, kW | kW_th, kWh_th | convert with configured steam enthalpy or default scenario assumption |
| natural_gas | Nm3/h, kWh, kW | kW_fuel, kWh_fuel | convert with lower heating value if volume-based |
| hydrogen | kg/h, kWh, kW | configured per scenario | require explicit conversion rule for Level 3 |
| waste_heat | kW | kW | direct resource limit |
| solar_resource | W/m2 or per-unit | normalized profile | converted by renewable model rule |
| temperature | degC | degC | metadata/profile input, not a balanced energy carrier |

If a required unit conversion is missing, the scenario can reach Level 2 but not Level 3.

## Tobacco Factory Real-Solve Scope

The first tobacco factory Level 3 model includes:

- Demands: `electricity`, `cooling`, `steam`.
- Inputs: `grid_electricity`, `natural_gas`.
- Resources: `solar_resource`, `waste_heat`, and optional `temperature` metadata.
- Devices: `pv`, `chp`, `electric_heat_pump`, `electric_chiller`, `absorption_chiller`, `electric_storage`, `heat_storage`, `cold_storage`, `steam_boiler`, `waste_heat_recovery`.

Steam is converted internally to `kW_th` for solving. The exported report preserves the original `t/h` values and shows the conversion assumption used.

Because some tobacco capacity upper bounds and economic parameters are still incomplete, the first implementation allows two paths:

1. Use user-provided bounds and costs when available.
2. Use clearly marked device-library defaults for missing bounds and costs when the user enables an acceptance/demo mode.

The result report marks which values came from user data and which came from defaults.

## Solver Adapter Choice

The first implementation should extend the existing OEMOF/Solph factory because the project already has smoke-tested `Source`, `Sink`, `Transformer`, and `GenericStorage` creation. A direct Pyomo adapter can be added later only if OEMOF cannot express a required generic constraint cleanly.

## Batch Scenario Onboarding

To make future 15 or larger scenario batches efficient, add a standard check command that runs readiness levels in order:

```text
parse -> validate -> map -> normalize -> build -> solve-smoke -> capacity-search-smoke
```

The command stops at the first blocking level and writes a concise gap report. This prevents users from seeing generic solver errors when the real problem is a missing unit, duplicated profile row, or missing capacity bound.

New scenario onboarding follows this policy:

- Add a scenario template if the topology is recurring.
- Add or update device-library entries for new equipment names.
- Map new equipment to an existing abstract type whenever possible.
- Add a new abstract type only when no existing linear input/output behavior fits.
- Add Python solver logic only for new abstract types or new objective terms.

## Outputs

A Level 3 generic design run writes:

- `resolved_scenario.json`
- `validation_report.md`
- `data_quality_report.md`
- `unit_normalization_report.md`
- `generic_component_plan.json`
- `generic_component_plan.md`
- `generic_model_components.json`
- `generic_design_solutions.json`
- `generic_design_solutions.csv`
- `generic_design_report.md`
- `capacity_solution.csv`
- `dispatch_summary.csv`
- `energy_flow_summary.csv`
- `conversion_type_summary.csv`
- `design_summary.xlsx`

The report states:

- scenario ID and name,
- backend name, such as `future_generic / linear_energy_hub`,
- readiness level,
- whether dispatch was actually solved,
- capacity variable count,
- conversion-type count,
- objective values,
- assumptions and defaulted parameters,
- remaining gaps.

## Error Handling

Errors are categorized before solving:

- `input_schema`: missing required fields or invalid YAML/Excel structure.
- `data_quality`: duplicated hours, missing hours, invalid numeric values, incomplete profiles.
- `unit_conversion`: missing or unsupported unit conversion.
- `component_mapping`: device has no generic abstract type mapping.
- `capacity_bounds`: optimized device lacks usable bounds and no default policy is enabled.
- `solver_build`: model specification cannot be transformed into solver nodes or constraints.
- `solver_runtime`: solver unavailable, infeasible, or time-limited.

Every error category is visible in a machine-readable JSON/CSV artifact and in a short Markdown report.

## Testing Strategy

Tests are layered by readiness level:

1. Unit tests for unit conversions, including steam `t/h` to `kW_th` and natural gas volume to energy.
2. Parser tests for cleaned tobacco Excel export.
3. Planner tests for tobacco conversion-type summary and component mapping.
4. Model-builder tests for generated balances, variables, and storage constraints.
5. Dispatch tests for a tiny synthetic multi-carrier scenario with known feasible solution.
6. Tobacco smoke test with one monthly typical day and small capacity candidate set.
7. CLI tests for Level 0 to Level 3 readiness reporting.
8. Regression tests for Songshan Lake and German current behavior.

## Implementation Order

1. Add carrier unit registry and unit normalization reports.
2. Add data quality reports for profile completeness and price profiles.
3. Build a backend-neutral linear model spec with balances and device constraints.
4. Extend the OEMOF/Solph solver adapter for the linear Energy Hub dispatch model.
5. Connect `GenericDispatchModel.evaluate()` to real dispatch results for generic scenarios.
6. Extend `GenericDesignOptimizer` so demo, random, and DE searches use the real dispatch objective.
7. Add tobacco Level 3 smoke command and checks.
8. Extend result exports with capacity, dispatch, energy-flow, and conversion summaries.
9. Update user-facing documentation and onboarding instructions.

## Non-Goals For First Real-Solve Version

- Nonlinear CHP off-design curves.
- Detailed steam thermodynamics beyond a documented conversion factor.
- Automatic topology generation from no structure at all.
- Full multi-objective NSGA-II in the first milestone.
- Perfect annual 8760 optimization before typical-day solving is stable.

These can be added after the tobacco factory Level 3 path is reliable.

## Review Notes

This design keeps the generic backend focused on a small, testable linear model. It avoids extending the old CCHP model for every new case, and it gives future scenario onboarding a clear staged readiness process. The main risk is unit conversion for steam and fuel; the mitigation is to make unit assumptions explicit, report them, and block Level 3 when a required conversion is missing.
