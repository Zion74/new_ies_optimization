# IES Design Interface V2 Design

## Goal

Build the second version of the scenario-driven IES design interface so it supports final 15-scenario expansion rather than only the first two CCHP examples. V2 keeps the existing `current_cchp` backend runnable for Songshan Lake and German cases, while adding interface features, richer validation, better reporting, and a generic-backend abstraction layer for future hydrogen, steam, gas-demand, and other non-CCHP scenarios.

## Confirmed Requirements

1. The third scenario acceptance target is a real computable scenario. The real Excel input will be provided later by the user after junior collaborators finish整理.
2. Add a `demo` optimization mode for very fast demonstrations and regression checks.
3. Fix legacy `comparison_report.md` currency display so it uses each scenario's currency instead of hard-coded `€`.
4. Make result root configurable: default design-interface runs should use `DesignResults/`, and `--output` should override the result root.
5. Extend `schema_validator.py` with a status that distinguishes runnable scenarios from scenarios that are future-backend-compatible but not currently runnable.
6. Add device Chinese name, device type, input/output carriers, and whether the device is default/new/custom to `design_summary.xlsx`.
7. Add typical-day clustering report charts and representative-day weight visualization.
8. Add a unified `run_design_checks.py` script.
9. Introduce formal JSON Schema or Pydantic validation. V2 uses JSON Schema first because user-facing inputs are YAML/JSON.
10. Prefer generic backend readiness for final 15-scenario expansion over short-term CCHP-only patches.

## Architecture

V2 keeps the first-version pipeline:

```text
scenario.yaml / Excel
  -> ScenarioLoader / ExcelScenarioParser
  -> DefaultsResolver
  -> SchemaValidator
  -> backend adapter
  -> optimizer
  -> ResultExporter
```

The key architectural change is to make backend capability explicit. `current_cchp` remains the only fully solving backend now. `future_generic` becomes a first-class validation target and is represented by a lightweight generic backend planner. The planner does not solve dispatch yet; it resolves carriers, buses, devices, component mappings, and backend readiness so hydrogen/steam/fuel-demand scenarios can be checked and prepared without pretending they already compute.

## Components

### 1. Optimization Modes and Result Roots

- `optimization_defaults.yaml` adds `demo`:
  - `nind: 6`
  - `maxgen: 3`
  - `methods: [euclidean]`
  - `workers: 2`
- `design.py --mode demo` becomes valid.
- `design.py --output <dir>` becomes the result root for optimization runs, not only Excel export or typical-day generation.
- Design-interface optimization runs default to `DesignResults/` rather than `Results/`.
- The current optimizer still creates a timestamped child directory such as `design__songshan_lake__demo__20260524_...`.

### 2. Currency-Correct Comparison Reports

`cchp_gasolution.py` should receive currency from `case_config["currency"]` and use it in:

- generation logs where practical,
- `comparison_report.md`,
- objective labels in report text.

This fixes Songshan Lake output without changing existing objective calculations.

### 3. Validation Status Model

`ValidationResult` is extended with:

- `status`: one of `runnable`, `future_supported`, `blocked`
- `backend`: template-supported backend, such as `current_cchp` or `future_generic`
- `unsupported_devices`: enabled devices that cannot run on the current backend
- `future_supported_devices`: enabled devices with generic component mappings

Rules:

- `runnable`: no blocking errors and selected backend can be executed now.
- `future_supported`: input is structurally valid and maps to generic components, but no solving backend is available yet.
- `blocked`: required fields are missing, files are missing when needed, unknown devices exist, or enabled devices cannot map to either current or generic backend.

The CLI should keep existing behavior for runnable scenarios. For `future_supported`, `--validate-only` succeeds with an explanatory message; optimization commands should not solve and should exit cleanly with a user-facing message.

### 4. Result Export Enhancements

`design_summary.xlsx` should become the main human-facing workbook. It should include at least:

- `summary_long`: existing long-form rows.
- `summary_wide`: existing wide-form recommendations.
- `device_metadata`: device ID, Chinese name, abstract type, input carriers, output carriers, capacity value, unit, whether it comes from the system template default list, and whether user explicitly configured it.

CSV outputs remain backward-compatible.

### 5. Typical-Day Visualization

Typical-day generation should output:

- existing typical-day CSV/XLSX files,
- Markdown report,
- `typical_day_weights.csv`,
- `typical_day_weights.png` if `matplotlib` is available,
- `representative_days.png` for cluster-from-8760 mode if source profiles are available.

If plotting dependencies are unavailable, generation still succeeds and records a warning in the report.

### 6. Unified Checks

Create `run_design_checks.py` at repo root. It should provide:

- default config checks,
- validation checks for Songshan Lake, German, and third placeholder,
- CLI dry-run checks for demo/quick mode,
- interface unit tests,
- optional `--run-demo` solving check.

The default mode must be safe and fast: no real optimization solve unless `--run-demo` is passed.

### 7. JSON Schema Validation

Add a schema file under `ies_design/schemas/scenario.schema.json` that covers the first-version user-facing fields:

- `schema_version`
- `scenario`
- `system`
- `energy_carriers`
- `data`
- `simulation`
- `typical_day`
- `prices`
- `devices`
- `optimization`

V2 should validate with JSON Schema when `jsonschema` is available, and fall back to the existing lightweight validator when it is not. This avoids forcing new dependencies while still documenting the formal input contract.

### 8. Generic Backend Readiness

Add a small generic backend planning layer:

- reads `component_mapping.yaml`,
- inspects resolved devices and energy carriers,
- produces a component plan with buses, devices, abstract types, input carriers, output carriers, and mapped backend component type,
- reports missing mappings clearly.
- exports `generic_component_plan.json` and `generic_component_plan.md` for `future_supported` scenarios so users can review the generic mapping before a solver backend exists.

This layer is not required to solve optimization in V2. Its purpose is to make the final 15-scenario expansion concrete and auditable, and to make third-scenario onboarding easier once the real Excel arrives.

## Data Flow

1. User provides YAML or Excel.
2. Loader/parser normalizes it to a scenario dictionary.
3. Defaults resolver merges scenario catalog, system template, optimization defaults, and device library.
4. JSON Schema validates the user-facing structure where available.
5. Schema validator determines `runnable`, `future_supported`, or `blocked`.
6. If runnable and a mode is requested, optimizer runs through the selected backend.
7. Result exporter writes standard report files and enhanced Excel workbook.
8. If typical-day generation is requested, generator writes files, report, and visualizations.

## Error Handling

- Missing required input fields are blocking errors.
- Unknown device library IDs are blocking errors.
- Current CCHP-incompatible devices under a CCHP template are blocking for solving.
- Future-generic templates are not errors during validation if every enabled device maps to a generic component.
- Optimization is blocked for `future_supported` scenarios until a real solver backend exists.
- Plot generation failure should be a warning, not a failed typical-day generation.

## Testing Strategy

- Unit tests for `demo` mode default resolution.
- CLI tests for `--mode demo --dry-run` and `--output`.
- Regression test for quick mode still using mode defaults.
- Test that comparison reports use `CNY`/`EUR` from scenario config.
- Test third placeholder status is `future_supported` once mapped to a future-generic template; if it still intentionally uses CCHP, it remains blocked with clear unsupported devices.
- Test Excel workbook contains `device_metadata`.
- Test typical-day generation writes weights CSV and at least attempts charts.
- Test JSON Schema catches missing `scenario.id`.
- Test `run_design_checks.py` default mode completes without solving.

## Delivery Scope

V2 is complete when:

- All nine user-confirmed improvements are implemented or represented by a concrete generic-backend skeleton where solving is intentionally deferred.
- Songshan Lake and German remain runnable.
- Third scenario validation communicates the real state honestly.
- Documentation, task list, tests, and commits exist for each completed task.
