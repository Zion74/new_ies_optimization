# Linear Energy Hub Real-Solve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `future_generic` into a real linear Energy Hub solving backend and make the tobacco factory scenario reach Level 3 real-solve acceptance.

**Architecture:** Keep the existing scenario pipeline, then add unit normalization, data quality reports, generic multi-carrier dispatch spec generation, OEMOF solving, and capacity-search result exports. Existing Songshan Lake/German `current_cchp` behavior must remain unchanged.

**Tech Stack:** Python 3.8, existing lightweight YAML parser, CSV/JSON/Markdown outputs, openpyxl for workbooks, oemof.solph/pyomo for dispatch, existing script-style tests under `松山湖/单元模块库/ies_design/tests/`.

---

## File Structure

### New Files

- `松山湖/单元模块库/ies_design/carrier_units.py`: carrier unit rules and conversion API.
- `松山湖/单元模块库/ies_design/data_quality.py`: profile completeness and data-quality reports.
- `松山湖/单元模块库/ies_design/generic_energy_hub_inputs.py`: scenario-agnostic linear Energy Hub dispatch spec builder.
- `松山湖/单元模块库/ies_design/tests/test_carrier_units.py`: unit conversion tests.
- `松山湖/单元模块库/ies_design/tests/test_data_quality.py`: profile quality tests.
- `松山湖/单元模块库/ies_design/tests/test_generic_energy_hub_inputs.py`: tobacco profile/spec tests.
- `松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py`: tobacco Level 3 real-solve smoke tests.

### Modified Files

- `松山湖/单元模块库/ies_design/defaults/device_library.yaml`: add default parameters/bounds needed for acceptance mode.
- `松山湖/单元模块库/ies_design/defaults/system_templates.yaml`: mark tobacco generic backend as linear Energy Hub capable.
- `松山湖/单元模块库/ies_design/generic_oemof_factory.py`: support multi-carrier linear Energy Hub solving.
- `松山湖/单元模块库/ies_design/generic_dispatch_model.py`: add generic real-dispatch path.
- `松山湖/单元模块库/ies_design/generic_design_optimizer.py`: use real generic dispatch objective.
- `松山湖/单元模块库/ies_design/schema_validator.py`: expose readiness levels and unit/bound gaps.
- `松山湖/单元模块库/ies_design/result_exporter.py`: export Level 3 generic result artifacts.
- `design.py`: add CLI flags for generic real solve.
- `run_design_checks.py`: add optional tobacco Level 3 check.
- `松山湖/单元模块库/README.md`, `松山湖/单元模块库/ies_design/README.md`, `松山湖/单元模块库/烟厂场景接入评估与数据清洗记录.md`: update acceptance evidence.

---

## Task 1: Carrier Unit Registry

**Files:**
- Create: `松山湖/单元模块库/ies_design/carrier_units.py`
- Create: `松山湖/单元模块库/ies_design/tests/test_carrier_units.py`

- [ ] **Step 1: Write the failing unit tests**

Create `test_carrier_units.py`:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carrier_units import CarrierUnitRegistry, UnitConversionError


def test_steam_t_per_hour_converts_to_kw_th():
    registry = CarrierUnitRegistry.default()
    assert round(registry.convert_power(1.0, carrier="steam", from_unit="t/h"), 1) == 627.8


def test_steam_kg_per_hour_converts_to_kw_th():
    registry = CarrierUnitRegistry.default()
    assert round(registry.convert_power(1000.0, carrier="steam", from_unit="kg/h"), 1) == 627.8


def test_natural_gas_nm3_per_hour_converts_to_kw_fuel():
    registry = CarrierUnitRegistry.default()
    assert round(registry.convert_power(1.0, carrier="natural_gas", from_unit="Nm3/h"), 2) == 9.97


def test_direct_kw_carriers_are_unchanged():
    registry = CarrierUnitRegistry.default()
    assert registry.convert_power(123.4, carrier="electricity", from_unit="kW") == 123.4
    assert registry.convert_power(55.0, carrier="cooling", from_unit="kW") == 55.0


def test_missing_conversion_raises_clear_error():
    registry = CarrierUnitRegistry.default()
    try:
        registry.convert_power(1.0, carrier="hydrogen", from_unit="kg/h")
    except UnitConversionError as exc:
        assert "hydrogen" in str(exc)
        assert "kg/h" in str(exc)
    else:
        raise AssertionError("expected UnitConversionError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_carrier_units.py"
```

Expected: FAIL with `ModuleNotFoundError: No module named 'carrier_units'`.

- [ ] **Step 3: Implement `carrier_units.py`**

Create `carrier_units.py` with `UnitConversionError`, `CarrierUnitRule`, and `CarrierUnitRegistry.default()`. Required defaults:

```python
steam: t/h -> 627.8 kW_th, kg/h -> 0.6278 kW_th
natural_gas: Nm3/h -> 9.97 kW_fuel
electricity/heat/cooling/waste_heat: direct kW-compatible carriers
solar_resource: W/m2 metadata/resource carrier
temperature: degC metadata carrier
```

`convert_power(value, carrier, from_unit)` must return a float or raise `UnitConversionError` with carrier and unit in the message.

- [ ] **Step 4: Run test to verify it passes**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_carrier_units.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/carrier_units.py" "松山湖/单元模块库/ies_design/tests/test_carrier_units.py"
rtk git commit -m "feat: add carrier unit registry"
```

---

## Task 2: Data Quality Reporter

**Files:**
- Create: `松山湖/单元模块库/ies_design/data_quality.py`
- Create: `松山湖/单元模块库/ies_design/tests/test_data_quality.py`

- [ ] **Step 1: Write failing tests**

Create tests that verify:

```python
DataQualityReporter.check_monthly_typical_profiles(
    ROOT / "scenarios" / "tobacco_factory" / "typical_profiles.csv",
    required_profile_types=["electricity", "cooling", "steam"],
) returns status="ok", expected_rows=864, actual_rows=864, errors=[]
```

Also create temp CSV tests for:

```python
duplicate (month, hour, profile_type) -> status="blocked" and "duplicate" in errors
non-numeric value -> status="blocked" and "non-numeric" in errors
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_data_quality.py"
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement `data_quality.py`**

Implement `DataQualityReporter.check_monthly_typical_profiles(path, required_profile_types)`:

- read CSV with `utf-8-sig`,
- require columns `month`, `hour`, `profile_type`, `value`, `unit`,
- detect duplicate keys `(month, hour, profile_type)`,
- detect non-numeric `value`,
- compute `expected_rows = 12 * 24 * len(required_profile_types)`,
- compute missing combinations,
- return `{status, expected_rows, actual_rows, errors, warnings}`.

- [ ] **Step 4: Run test to verify it passes**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_data_quality.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/data_quality.py" "松山湖/单元模块库/ies_design/tests/test_data_quality.py"
rtk git commit -m "feat: add generic data quality reporter"
```

---

## Task 3: Tobacco Dispatch Profile Loader With Unit Normalization

**Files:**
- Create: `松山湖/单元模块库/ies_design/generic_energy_hub_inputs.py`
- Create: `松山湖/单元模块库/ies_design/tests/test_generic_energy_hub_inputs.py`

- [ ] **Step 1: Write failing tests**

Create tests for `GenericEnergyHubInputs`:

```python
loaded = GenericEnergyHubInputs.load_monthly_profiles(resolve_tobacco(), project_root=PROJECT_ROOT, month=1, periods=24)
assert len(loaded["demands"]["electricity"]) == 24
assert len(loaded["demands"]["cooling"]) == 24
assert len(loaded["demands"]["steam"]) == 24
assert loaded["units"]["steam"] == "kW_th"
assert max(loaded["demands"]["steam"]) > 1000
assert len(loaded["resources"]["solar_resource"]) == 24
assert len(loaded["resources"]["waste_heat"]) == 24
assert len(loaded["resources"]["temperature"]) == 24
```

Also test:

```python
spec = GenericEnergyHubInputs.build_dispatch_spec(resolve_tobacco(), project_root=PROJECT_ROOT, month=1, periods=24, capacity_assignment={}, accept_default_bounds=True)
buses = {item["id"] for item in spec["buses"]}
assert {"electricity", "cooling", "steam", "natural_gas", "waste_heat"}.issubset(buses)
assert any(item["id"] == "steam_demand" for item in spec["demand_sinks"])
assert any(item["id"] == "steam_boiler" for item in spec["components"])
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_energy_hub_inputs.py"
```

Expected: missing module.

- [ ] **Step 3: Implement profile loading**

Implement:

- `_resolve_data_path(resolved, project_root, key)` resolving relative paths from `_meta.source_path` before project root,
- `load_monthly_profiles(resolved, project_root, month, periods)`,
- parsing columns `month`, `hour`, `profile_type`, `value`, `unit`,
- demand normalization via `CarrierUnitRegistry.default()`,
- resource loading from `data.resource_file`,
- resource sparse handling by forward-fill in the requested month, and zeros with warning when absent.

Return:

```python
{
    "demands": {carrier: [values]},
    "resources": {carrier: [values]},
    "units": {carrier: internal_unit},
    "warnings": ["..."],
}
```

- [ ] **Step 4: Implement minimal dispatch spec generation**

`build_dispatch_spec(...)` creates:

- buses for demand, input, and resource carriers,
- demand sinks with fixed profiles,
- grid electricity source and natural gas source with prices,
- enabled device components with capacities from assignment or acceptance defaults.

- [ ] **Step 5: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_carrier_units.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_energy_hub_inputs.py"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/generic_energy_hub_inputs.py" "松山湖/单元模块库/ies_design/tests/test_generic_energy_hub_inputs.py"
rtk git commit -m "feat: build generic energy hub inputs"
```

---

## Task 4: Generic OEMOF Linear Energy Hub Solver Support

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_oemof_factory.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_generic_oemof_factory.py`

- [ ] **Step 1: Add test for multi-carrier solve**

Add a tiny feasible spec with buses `electricity`, `natural_gas`, `steam`; fixed electricity and steam demands; grid electricity source; natural gas source; and `steam_boiler` transformer. Assert:

```python
result = GenericOemofFactory.solve_dispatch(spec, periods=24, solver_names=["glpk"])
assert result["dispatch_solved"] is True
assert result["objective_value"] > 0
assert any(row["to"] == "steam" for row in result["dispatch_summary"]["flow_totals"])
```

- [ ] **Step 2: Run test to verify current behavior**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_oemof_factory.py"
```

If it already passes, keep the test and continue. If it fails, fix factory behavior in Step 3.

- [ ] **Step 3: Fix factory behavior**

Ensure:

- Source `fixed_profile` uses `fix` with `nominal_value=1` for already-scaled profiles.
- Transformer output capacity uses the output capacity variable.
- Multi-output transformer accepts conversion factors per output.
- Variable sink/spill works when capacity is provided.
- Build summary records skipped components clearly.

- [ ] **Step 4: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_oemof_factory.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_design_optimizer.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/generic_oemof_factory.py" "松山湖/单元模块库/ies_design/tests/test_generic_oemof_factory.py"
rtk git commit -m "feat: solve generic multi-carrier dispatch"
```

---

## Task 5: Connect Tobacco Generic Dispatch Evaluation

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_dispatch_model.py`
- Modify: `松山湖/单元模块库/ies_design/generic_design_optimizer.py`
- Create: `松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py`

- [ ] **Step 1: Write failing tobacco dispatch tests**

Create tests that:

```python
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
```

And:

```python
result = GenericDesignOptimizer(resolve_tobacco()).run_demo_search(
    levels=[1.0],
    project_root=PROJECT_ROOT,
    solve_generic_dispatch=True,
    dispatch_periods=24,
    dispatch_month=1,
    accept_default_bounds=True,
)
assert result["solutions"][0]["dispatch_solved"] is True
assert result["solutions"][0]["dispatch_objective"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
```

Expected: FAIL because new arguments are unsupported.

- [ ] **Step 3: Modify `GenericDispatchModel.evaluate()`**

Add parameters:

```python
solve_generic_dispatch: bool = False
dispatch_month: int = 1
accept_default_bounds: bool = False
```

If `solve_generic_dispatch=True`, call `GenericEnergyHubInputs.build_dispatch_spec(...)`, solve with `GenericOemofFactory.solve_dispatch(...)`, and return `scope="linear_energy_hub"`.

- [ ] **Step 4: Modify `GenericDesignOptimizer` APIs**

Add the same optional arguments to demo/random/DE paths and export classmethods. Penalize unsolved dispatch when generic dispatch is requested.

- [ ] **Step 5: Run targeted tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_design_optimizer.py"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/generic_dispatch_model.py" "松山湖/单元模块库/ies_design/generic_design_optimizer.py" "松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py"
rtk git commit -m "feat: solve tobacco generic dispatch"
```

---

## Task 6: Capacity Bound Defaults For Acceptance Mode

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_capacity_space.py`
- Modify: `松山湖/单元模块库/ies_design/defaults/device_library.yaml`
- Modify: `松山湖/单元模块库/ies_design/tests/test_generic_capacity_space.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py`

- [ ] **Step 1: Write tests for default-bound source tracking**

Assert tobacco capacity space includes all enabled optimized devices when acceptance defaults are enabled, including `steam_boiler` and `waste_heat_recovery`. Assert defaulted variables record source metadata such as `bound_source="library_default"` or `bound_source="acceptance_default"`.

- [ ] **Step 2: Implement default-bound policy**

Use this order:

1. user-provided scenario bound,
2. device-library default bound,
3. acceptance fallback only if `accept_default_bounds=True`.

Fallbacks:

- PV: peak electricity load or 5000 kW.
- CHP: peak electric load.
- electric chiller: peak cooling load.
- absorption chiller: peak cooling load.
- electric storage power: peak electric load.
- electric storage energy: 2h times storage power.
- cold storage power: peak cooling load.
- cold storage energy: 2h times storage power.
- steam boiler: peak steam load in normalized kW.
- heat storage power: peak steam/heat demand.
- heat storage energy: user-provided `energy_capacity_ub_kwh` if available, otherwise 2h times power.

- [ ] **Step 3: Ensure result metadata marks defaults**

Add bound source metadata to capacity variables or capacity assignment metadata.

- [ ] **Step 4: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_capacity_space.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/generic_capacity_space.py" "松山湖/单元模块库/ies_design/defaults/device_library.yaml" "松山湖/单元模块库/ies_design/tests/test_generic_capacity_space.py" "松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py"
rtk git commit -m "feat: support acceptance capacity defaults"
```

---

## Task 7: CLI For Generic Real Solve

**Files:**
- Modify: `design.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_design_cli.py`

- [ ] **Step 1: Write CLI tests**

Add a test for tobacco:

```python
result = run_cli(
    "--scenario", str(tobacco),
    "--run-generic-design",
    "--generic-search-levels", "1.0",
    "--solve-generic-dispatch",
    "--dispatch-month", "1",
    "--dispatch-periods", "24",
    "--accept-future",
    "--accept-default-bounds",
    "--output", tmp,
)
assert result.returncode == 0
assert '"scope": "linear_energy_hub"' in (Path(tmp) / "generic_design_solutions.json").read_text(encoding="utf-8")
assert '"dispatch_solved": true' in data
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_cli.py"
```

Expected: FAIL due to unsupported CLI flags.

- [ ] **Step 3: Add CLI flags**

In `design.py` add:

```python
parser.add_argument("--solve-generic-dispatch", action="store_true")
parser.add_argument("--dispatch-month", type=int, default=1)
parser.add_argument("--accept-default-bounds", action="store_true")
```

Pass them into `GenericDesignOptimizer.export_*` calls.

- [ ] **Step 4: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_cli.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- design.py "松山湖/单元模块库/ies_design/tests/test_design_cli.py"
rtk git commit -m "feat: add generic real solve CLI"
```

---

## Task 8: Result Exports For Level 3 Generic Runs

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_design_optimizer.py`
- Modify: `松山湖/单元模块库/ies_design/result_exporter.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_result_exporter.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py`

- [ ] **Step 1: Add artifact tests**

Add an export test that runs tobacco generic design into a temp directory and asserts existence of:

- `generic_design_solutions.json`
- `generic_design_solutions.csv`
- `generic_design_report.md`
- `capacity_solution.csv`
- `dispatch_summary.csv`
- `energy_flow_summary.csv`
- `conversion_type_summary.csv`

- [ ] **Step 2: Implement generic CSV outputs**

Extend generic design export methods to write:

- `capacity_solution.csv`: one row per solution/device/variable.
- `dispatch_summary.csv`: one row per flow total and storage row.
- `energy_flow_summary.csv`: normalized flow totals with solution ID.
- `conversion_type_summary.csv`: one row per abstract type.

- [ ] **Step 3: Add report section**

Update `generic_design_report.md` to state:

- backend: `future_generic / linear_energy_hub`,
- readiness: `Level 3` when at least one solution solved,
- dispatch solved count,
- defaulted bounds count.

- [ ] **Step 4: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_result_exporter.py"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/generic_design_optimizer.py" "松山湖/单元模块库/ies_design/result_exporter.py" "松山湖/单元模块库/ies_design/tests/test_result_exporter.py" "松山湖/单元模块库/ies_design/tests/test_tobacco_level3.py"
rtk git commit -m "feat: export generic level3 results"
```

---

## Task 9: Unified Level 0-3 Checks

**Files:**
- Modify: `run_design_checks.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_run_design_checks.py`

- [ ] **Step 1: Add checks test**

Add or update tests to assert `run_design_checks.py --include-tobacco-level3` calls tobacco CLI with:

- `--run-generic-design`
- `--solve-generic-dispatch`
- `--accept-future`
- `--accept-default-bounds`

- [ ] **Step 2: Modify `run_design_checks.py`**

Add:

```python
parser.add_argument("--include-tobacco-level3", action="store_true")
```

Default behavior remains fast. The new option runs tobacco Level 3 into `DesignResults/_check_tobacco_level3`.

- [ ] **Step 3: Run tests**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_run_design_checks.py"
rtk uv run python run_design_checks.py
```

Expected: default checks PASS and do not run tobacco Level 3 unless the option is passed.

- [ ] **Step 4: Commit**

```powershell
rtk git add -- run_design_checks.py "松山湖/单元模块库/ies_design/tests/test_run_design_checks.py"
rtk git commit -m "feat: add tobacco level3 design checks"
```

---

## Task 10: Documentation And Acceptance Evidence

**Files:**
- Modify: `松山湖/单元模块库/烟厂场景接入评估与数据清洗记录.md`
- Modify: `松山湖/单元模块库/README.md`
- Modify: `松山湖/单元模块库/ies_design/README.md`
- Optional modify: `项目索引目录.md` if command names or directory roles change materially.

- [ ] **Step 1: Run final tobacco evidence command**

```powershell
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\tobacco_factory\scenario.yaml" --run-generic-design --generic-search-levels 1.0 --solve-generic-dispatch --dispatch-month 1 --dispatch-periods 24 --accept-future --accept-default-bounds --output "DesignResults/tobacco_factory_level3_acceptance"
```

Expected:

- command exits 0,
- `generic_design_solutions.json` contains `"dispatch_solved": true`,
- report states `linear_energy_hub`,
- result directory contains Level 3 artifacts.

- [ ] **Step 2: Update docs**

Record:

- exact command,
- output directory,
- solved status,
- conversion type count,
- capacity variable count,
- objective value,
- assumptions: linear Energy Hub, fixed CHP factors, steam conversion factor, defaulted bounds.

- [ ] **Step 3: Run regression checks**

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_carrier_units.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_data_quality.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_energy_hub_inputs.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_cli.py"
rtk uv run python run_design_checks.py
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/烟厂场景接入评估与数据清洗记录.md" "松山湖/单元模块库/README.md" "松山湖/单元模块库/ies_design/README.md" "项目索引目录.md"
rtk git commit -m "docs: record tobacco level3 acceptance"
```

---

## Final Verification

Run:

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_carrier_units.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_data_quality.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_energy_hub_inputs.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_oemof_factory.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_dispatch_model.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_design_optimizer.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_cli.py"
rtk uv run python run_design_checks.py
rtk uv run python run_design_checks.py --include-tobacco-level3
```

Expected final state:

- Songshan Lake and German checks still pass.
- Tobacco validates as `future_supported` but also has an explicit Level 3 generic real-solve path.
- `DesignResults/tobacco_factory_level3_acceptance/` contains the real-solve evidence package.
- No unrelated user file deletions or raw data folders are staged.

## Self-Review

- Spec coverage: covers unit normalization, data quality, generic build, OEMOF solve, capacity search, CLI, exports, checks, and docs.
- Scope control: avoids nonlinear equipment physics, topology generation, and full NSGA-II in this milestone.
- Placeholder scan: no unresolved placeholders remain; each task has concrete files, commands, expected outcomes, and commits.
- Compatibility: existing electric-slice APIs remain in place while the new `solve_generic_dispatch` path is added.
- Commit discipline: every task ends with a path-scoped commit and avoids unrelated user changes.
