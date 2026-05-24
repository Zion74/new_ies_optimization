# IES Design Interface V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the V2 scenario-driven IES design interface improvements for demo runs, configurable result roots, currency-correct reports, richer validation, enhanced Excel outputs, typical-day visualizations, unified checks, JSON Schema validation, and generic-backend readiness.

**Architecture:** Keep the current CCHP backend as the runnable solver while adding explicit backend capability status and a generic component-planning layer. Preserve current YAML/Excel input flow and result package formats, adding fields and worksheets rather than breaking existing CSV outputs.

**Tech Stack:** Python, YAML/JSON, openpyxl, matplotlib, optional jsonschema, existing geatpy/oemof optimization stack.

---

### Task 1: Add Demo Mode and Configurable Result Root

**Files:**
- Modify: `design.py`
- Modify: `松山湖/单元模块库/ies_design/defaults/optimization_defaults.yaml`
- Modify: `松山湖/单元模块库/ies_design/design_optimizer.py`
- Modify: `cchp_gasolution.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_design_cli.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_design_optimizer.py`

- [ ] **Step 1: Add failing tests**

Add tests asserting:

```python
def test_mode_demo_dry_run_uses_demo_defaults():
    result = run_design_cli(["--scenario", songshan_path, "--mode", "demo", "--dry-run"])
    assert result.returncode == 0
    assert "nind: 6" in result.stdout
    assert "maxgen: 3" in result.stdout
    assert "methods_to_run: ['euclidean']" in result.stdout
```

```python
def test_output_overrides_design_result_root(tmp_path):
    resolved = resolved_songshan_with_demo_mode()
    run_config = DesignOptimizer.build_run_config(resolved, project_root=PROJECT_ROOT, output_root=tmp_path)
    assert run_config["result_root"] == str(tmp_path)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_cli.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_design_optimizer.py"
```

Expected: demo mode and/or output root tests fail.

- [ ] **Step 3: Implement minimal code**

Changes:

- Add `demo` mode to `optimization_defaults.yaml`.
- Add `"demo"` to `design.py --mode` choices.
- Pass `args.output` into `DesignOptimizer.build_run_config()` / `DesignOptimizer.run()`.
- Add `output_root` / `result_root` to run config.
- Extend `run_comparative_study()` to accept `result_root=None`; default design calls use `DesignResults`.

- [ ] **Step 4: Run tests and verify pass**

Run the same two tests plus:

```powershell
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\songshan_lake\scenario.yaml" --mode demo --dry-run
```

Expected: all pass; dry-run prints demo defaults and `DesignResults` result root.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- design.py cchp_gasolution.py "松山湖/单元模块库/ies_design/defaults/optimization_defaults.yaml" "松山湖/单元模块库/ies_design/design_optimizer.py" "松山湖/单元模块库/ies_design/tests/test_design_cli.py" "松山湖/单元模块库/ies_design/tests/test_design_optimizer.py"
rtk git commit -m "feat: add demo mode and design result root"
```

### Task 2: Fix Currency Display in Comparison Reports

**Files:**
- Modify: `cchp_gasolution.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_design_optimizer.py` or new focused test file

- [ ] **Step 1: Add failing test**

Create a test that calls the comparison report writer with `case_config={"currency": "CNY"}` and asserts the report contains `CNY` and not a hard-coded `€` label.

- [ ] **Step 2: Run test and verify failure**

Run the focused test.

- [ ] **Step 3: Implement minimal code**

Introduce helper:

```python
def _currency_label(case_config):
    return case_config.get("currency") or "currency"
```

Use the helper in report labels and obvious generation logs.

- [ ] **Step 4: Run test and dry-run**

Run focused test and an existing design optimizer test.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- cchp_gasolution.py "松山湖/单元模块库/ies_design/tests"
rtk git commit -m "fix: use scenario currency in comparison reports"
```

### Task 3: Add Validation Status and Generic Backend Planner

**Files:**
- Create: `松山湖/单元模块库/ies_design/generic_backend_planner.py`
- Modify: `松山湖/单元模块库/ies_design/schema_validator.py`
- Modify: `design.py`
- Modify: `松山湖/单元模块库/ies_design/scenarios/third_placeholder/scenario.yaml`
- Test: `松山湖/单元模块库/ies_design/tests/test_third_placeholder.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_backend_planner.py`

- [ ] **Step 1: Add failing tests**

Tests should assert:

```python
assert validation.status == "future_supported"
assert validation.ok is True
assert validation.runnable is False
assert "electrolyzer" in validation.future_supported_devices
```

and:

```python
plan = GenericBackendPlanner.plan(resolved)
assert "hydrogen" in plan["buses"]
assert any(item["component_type"] == "Transformer" for item in plan["components"])
```

- [ ] **Step 2: Run tests and verify failure**

Run the two focused test files.

- [ ] **Step 3: Implement minimal code**

Implement a planner that reads resolved devices, `abstract_type`, `input_carriers`, `output_carriers`, and `component_mapping`. Extend `ValidationResult` with `status`, `backend`, `runnable`, `unsupported_devices`, and `future_supported_devices`.

- [ ] **Step 4: Update CLI behavior**

For `--validate-only`, print status and return success for `future_supported`. For actual optimization, return a clean nonzero code if status is not runnable.

- [ ] **Step 5: Run focused tests**

Run planner and third-placeholder tests.

- [ ] **Step 6: Commit**

```powershell
rtk git add -- design.py "松山湖/单元模块库/ies_design/generic_backend_planner.py" "松山湖/单元模块库/ies_design/schema_validator.py" "松山湖/单元模块库/ies_design/scenarios/third_placeholder/scenario.yaml" "松山湖/单元模块库/ies_design/tests/test_third_placeholder.py" "松山湖/单元模块库/ies_design/tests/test_generic_backend_planner.py"
rtk git commit -m "feat: add backend readiness validation"
```

### Task 4: Enhance Design Summary Workbook

**Files:**
- Modify: `松山湖/单元模块库/ies_design/result_exporter.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_result_exporter.py`

- [ ] **Step 1: Add failing test**

Assert `design_summary.xlsx` contains a `device_metadata` worksheet with columns:

```text
solution_label, device_id, device_name, device_type, input_carriers, output_carriers, capacity_value, unit, is_default_device, is_user_configured
```

- [ ] **Step 2: Run test and verify failure**

Run `test_result_exporter.py`.

- [ ] **Step 3: Implement workbook enhancement**

Build device metadata from `resolved["devices"]`, `resolved["system_template"]["default_devices"]`, and selected recommendation capacities.

- [ ] **Step 4: Run test and verify pass**

Run `test_result_exporter.py`.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/result_exporter.py" "松山湖/单元模块库/ies_design/tests/test_result_exporter.py"
rtk git commit -m "feat: add device metadata workbook sheet"
```

### Task 5: Add Typical-Day Report Visualizations

**Files:**
- Modify: `松山湖/单元模块库/ies_design/typical_day.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_typical_day.py`

- [ ] **Step 1: Add failing tests**

Assert monthly template and cluster generation produce `typical_day_weights.csv`; if `matplotlib` imports, assert `typical_day_weights.png` exists.

- [ ] **Step 2: Run test and verify failure**

Run `test_typical_day.py`.

- [ ] **Step 3: Implement outputs**

Write weights CSV and plot weight bars. For cluster mode, plot representative-day profiles if daily vectors are available.

- [ ] **Step 4: Run test and verify pass**

Run `test_typical_day.py`.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/typical_day.py" "松山湖/单元模块库/ies_design/tests/test_typical_day.py"
rtk git commit -m "feat: add typical day visualization outputs"
```

### Task 6: Add JSON Schema Validation

**Files:**
- Create: `松山湖/单元模块库/ies_design/schemas/scenario.schema.json`
- Create: `松山湖/单元模块库/ies_design/json_schema_validator.py`
- Modify: `松山湖/单元模块库/ies_design/schema_validator.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_json_schema_validator.py`

- [ ] **Step 1: Add failing tests**

Assert a minimal valid scenario passes and a scenario missing `scenario.id` fails with a schema error.

- [ ] **Step 2: Run test and verify failure**

Run `test_json_schema_validator.py`.

- [ ] **Step 3: Implement schema and optional validator**

Use `jsonschema` if available. If not available, implement a lightweight required-field check using the schema's `required` arrays.

- [ ] **Step 4: Run test and verify pass**

Run schema validator tests and `test_design_cli.py`.

- [ ] **Step 5: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/ies_design/schemas/scenario.schema.json" "松山湖/单元模块库/ies_design/json_schema_validator.py" "松山湖/单元模块库/ies_design/schema_validator.py" "松山湖/单元模块库/ies_design/tests/test_json_schema_validator.py"
rtk git commit -m "feat: add scenario json schema validation"
```

### Task 7: Add Unified Design Checks Script

**Files:**
- Create: `run_design_checks.py`
- Test: command-line execution

- [ ] **Step 1: Write script**

Script default checks:

```text
validate_default_configs.py
test_*.py
design.py --validate-only for songshan_lake and german
design.py --validate-only for third_placeholder
design.py --mode demo --dry-run for songshan_lake
```

`--run-demo` additionally runs one demo optimization for Songshan Lake.

- [ ] **Step 2: Run default checks**

Run:

```powershell
rtk uv run python run_design_checks.py
```

Expected: exits 0 without solving.

- [ ] **Step 3: Commit**

```powershell
rtk git add -- run_design_checks.py
rtk git commit -m "feat: add unified design checks"
```

### Task 8: Update Documentation and Indexes

**Files:**
- Modify: `松山湖/单元模块库/场景化系统设计接口使用说明书.md`
- Modify: `松山湖/单元模块库/第一版场景化系统设计接口设计开发复盘与优化建议.md`
- Modify: `松山湖/单元模块库/README.md`
- Modify: `项目索引目录.md`

- [ ] **Step 1: Document new commands**

Add `demo`, `--output`, validation statuses, design checks, and generic-backend readiness notes.

- [ ] **Step 2: Run docs smoke check**

Run `git diff --check`.

- [ ] **Step 3: Commit**

```powershell
rtk git add -- "松山湖/单元模块库/场景化系统设计接口使用说明书.md" "松山湖/单元模块库/第一版场景化系统设计接口设计开发复盘与优化建议.md" "松山湖/单元模块库/README.md" "项目索引目录.md"
rtk git commit -m "docs: update design interface v2 usage"
```

### Task 9: Final Verification

**Files:**
- No code changes expected.

- [ ] **Step 1: Run default check script**

```powershell
rtk uv run python run_design_checks.py
```

- [ ] **Step 2: Run demo dry-run commands manually**

```powershell
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\songshan_lake\scenario.yaml" --mode demo --dry-run
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\german\scenario.yaml" --mode demo --dry-run
```

- [ ] **Step 3: Inspect git status**

```powershell
rtk git status --short
```

Expected: clean worktree.

