# Generic P0 System Object Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 generic system object, standardized capacity variable schema, and given-capacity dispatch API for external optimizer integration.

**Architecture:** Keep `GenericModelBuilder` as the artifact builder, add a focused `generic_system.py` consumer API, and preserve existing optimizer/report compatibility. Exports add `system_object.json`, `capacity_variables.json`, and `capacity_variables.csv` without removing current generic model artifacts.

**Tech Stack:** Python 3.12, existing `ies_design` modules, OEMOF/solph dispatch backend, CSV/JSON artifacts, direct script tests.

---

### Task 1: Standard System Object Export

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_model_builder.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `GenericModelBuilder.build(resolve("tobacco_factory"), build_oemof=False)` and assert:

```python
system = spec["system_object"]
assert system["schema_version"] == "generic_system_object.v1"
assert system["scenario"]["id"] == "tobacco_factory_001"
assert any(bus["id"] == "steam" for bus in system["buses"])
assert any(conn["component_id"] == "steam_boiler" and conn["carrier"] == "steam" for conn in system["connections"])
assert "typical_profiles.csv" in system["time_series_refs"]["load_file"]
assert "steam_boiler" in system["parameters"]["devices"]
```

Also update export test to expect `system_object.json`.

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_model_builder.py"
```

Expected: fail because `system_object` and `system_object.json` do not exist.

- [ ] **Step 3: Implement standard system object**

Add helper functions in `generic_model_builder.py`:

```python
def _system_object(resolved: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "generic_system_object.v1",
        "scenario": spec["scenario"],
        "backend": {"name": spec["backend"], "solve_status": spec["solve_status"]},
        "buses": spec["buses"],
        "components": spec["components"],
        "connections": _connections(spec["components"]),
        "time_series_refs": _time_series_refs(resolved),
        "parameters": {"devices": _device_parameters(resolved)},
        "capacity_variables": spec["capacity_variables"],
        "build_gaps": spec["build_gaps"],
        "conversion_type_summary": spec["conversion_type_summary"],
    }
```

Write `system_object.json` in `GenericModelBuilder.export()`.

- [ ] **Step 4: Run tests**

Run the same test file. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add -- "松山湖/单元模块库/ies_design/generic_model_builder.py" "松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py"
rtk git commit -m "feat: export generic system object"
```

### Task 2: Capacity Variable Schema Upgrade

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_model_builder.py`
- Modify: `松山湖/单元模块库/ies_design/generic_capacity_space.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_capacity_space.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py`

- [ ] **Step 1: Write failing tests**

Add assertions that a capacity variable contains both new and compatibility fields:

```python
pv = next(item for item in spec["capacity_variables"] if item["name"] == "pv.capacity_kw")
assert pv["parameter"] == "capacity_kw"
assert pv["lb"] == 0.0
assert pv["ub"] > 0
assert pv["default_value"] == 0.0
assert pv["is_fixed"] is False
assert pv["source"] in {"user_input", "library_default", "acceptance_default", "scenario"}
assert pv["variable_name"] == "capacity_kw"
assert pv["upper_bound"] == pv["ub"]
```

Add `GenericCapacitySpace.from_model_spec()` test that still returns names and upper bounds from upgraded fields.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_model_builder.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_capacity_space.py"
```

- [ ] **Step 3: Normalize variables in builder**

Add `_standard_capacity_variables(plan)` and use it in `GenericModelBuilder.build()`. It should preserve:

```python
{
    "name": f"{device_id}.{variable_name}",
    "device_id": device_id,
    "parameter": variable_name,
    "unit": unit,
    "lb": lower_bound,
    "ub": upper_bound,
    "default_value": 0.0,
    "is_fixed": False,
    "source": bound_source or "scenario",
    "role": role,
    "variable_name": variable_name,
    "lower_bound": lower_bound,
    "upper_bound": upper_bound,
    "bound_source": bound_source,
}
```

- [ ] **Step 4: Update `GenericCapacitySpace` fallback logic**

Make `from_model_spec()` and `from_dispatch_spec()` read `ub/lb/parameter/source` first and fall back to `upper_bound/lower_bound/variable_name/bound_source`.

- [ ] **Step 5: Run tests**

Run the two test files. Expected: pass.

- [ ] **Step 6: Commit**

```bash
rtk git add -- "松山湖/单元模块库/ies_design/generic_model_builder.py" "松山湖/单元模块库/ies_design/generic_capacity_space.py" "松山湖/单元模块库/ies_design/tests/test_generic_capacity_space.py" "松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py"
rtk git commit -m "feat: standardize generic capacity variables"
```

### Task 3: Given-Capacity Dispatch API

**Files:**
- Create: `松山湖/单元模块库/ies_design/generic_system.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_system.py`

- [ ] **Step 1: Write failing tests**

Create tests:

```python
system = GenericSystem.from_resolved(resolve("tobacco_factory"), project_root=PROJECT_ROOT)
defaults = system.default_capacity_assignment(level=1.0)
result = system.solve_dispatch(defaults, month=1, periods=24, accept_default_bounds=True)
assert result["dispatch_solved"] is True
assert result["termination_condition"] == "optimal"
assert result["capacity_assignment"]["pv"]["capacity_kw"] > 0
assert result["dispatch_summary"]["flow_totals"]
```

Also test invalid flat capacity:

```python
try:
    system.solve_dispatch({"not_a_device.capacity_kw": 1.0})
except ValueError as exc:
    assert "unknown capacity variable" in str(exc)
    assert "pv.capacity_kw" in str(exc)
```

- [ ] **Step 2: Run test and confirm failure**

```bash
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_system.py"
```

- [ ] **Step 3: Implement `GenericSystem`**

Implement:

```python
class GenericSystem:
    @classmethod
    def from_resolved(cls, resolved, project_root=None): ...
    def default_capacity_assignment(self, level=1.0): ...
    def solve_dispatch(self, capacities, month=1, periods=24, accept_default_bounds=False): ...
```

Normalize capacities from either flat `{"pv.capacity_kw": 1}` or nested `{"pv": {"capacity_kw": 1}}`. Internally call `GenericDispatchModel.evaluate()`.

- [ ] **Step 4: Run tests**

Run the new test. Expected: pass.

- [ ] **Step 5: Commit**

```bash
rtk git add -- "松山湖/单元模块库/ies_design/generic_system.py" "松山湖/单元模块库/ies_design/tests/test_generic_system.py"
rtk git commit -m "feat: add generic system dispatch api"
```

### Task 4: Capacity Artifact Export

**Files:**
- Modify: `松山湖/单元模块库/ies_design/generic_model_builder.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py`

- [ ] **Step 1: Write failing export tests**

Assert export returns and writes:

```python
assert outputs["system_object"].exists()
assert outputs["capacity_variables_json"].exists()
assert outputs["capacity_variables_csv"].exists()
```

Read CSV and assert columns include `name`, `device_id`, `parameter`, `unit`, `lb`, `ub`, `default_value`, `is_fixed`, `source`.

- [ ] **Step 2: Run test and confirm failure**

Run generic model builder tests.

- [ ] **Step 3: Implement artifact writers**

Add `_write_capacity_variables_csv()` and write `capacity_variables.json`.

- [ ] **Step 4: Run tests**

Run generic model builder tests. Expected: pass.

- [ ] **Step 5: Commit**

```bash
rtk git add -- "松山湖/单元模块库/ies_design/generic_model_builder.py" "松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py"
rtk git commit -m "feat: export generic capacity artifacts"
```

### Task 5: Documentation and Regression

**Files:**
- Modify: `松山湖/单元模块库/系统设计/中期后开发重点与路线图.md`
- Modify: `松山湖/单元模块库/系统设计/多能转换单元模块库使用说明书.md`
- Modify: `松山湖/单元模块库/ies_design/README.md`

- [ ] **Step 1: Document P0 interface**

Add a short section explaining the P0 cooperation boundary:

```text
system_object.json + capacity_variables.json/csv + GenericSystem.solve_dispatch(capacities)
```

- [ ] **Step 2: Run focused tests**

```bash
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_model_builder.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_capacity_space.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_generic_system.py"
rtk uv run python "松山湖\单元模块库\ies_design\tests\test_tobacco_level3.py"
```

- [ ] **Step 3: Run full design check**

```bash
rtk uv run python run_design_checks.py --include-tobacco-level3
```

Expected: `ALL DESIGN CHECKS PASSED`.

- [ ] **Step 4: Commit**

```bash
rtk git add -- "松山湖/单元模块库/系统设计/中期后开发重点与路线图.md" "松山湖/单元模块库/系统设计/多能转换单元模块库使用说明书.md" "松山湖/单元模块库/ies_design/README.md"
rtk git commit -m "docs: document generic p0 integration interface"
```
