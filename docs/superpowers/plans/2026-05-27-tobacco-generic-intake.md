# Tobacco Generic Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入烟厂作为第三个真实结构场景，使 Excel 清洗版能够导出 `future_generic` 场景、组件计划和通用模型构建材料。

**Architecture:** 保留 Excel 作为用户输入，解析器按 `scenario_type=tobacco_factory_multi_energy` 选择通用工业模板。解析结果继续输出 `scenario.yaml`、负荷曲线 CSV、资源曲线 CSV 和数据缺口表，并让通用后端读取 `steam`、`waste_heat`、热泵、热储能、蒸汽锅炉等组件。

**Tech Stack:** Python、openpyxl、PyYAML、pytest、现有 `design.py`、`ExcelScenarioParser`、`GenericBackendPlanner`、`GenericModelBuilder`。

---

### Task 1: 烟厂场景模板与目录映射

**Files:**
- Modify: `松山湖/单元模块库/ies_design/defaults/system_templates.yaml`
- Modify: `松山湖/单元模块库/ies_design/defaults/scenario_catalog.yaml`
- Test: `松山湖/单元模块库/ies_design/tests/test_excel_parser.py`

- [ ] Write failing test asserting `tobacco_factory_multi_energy` Excel import uses `tobacco_factory_multi_energy` template.
- [ ] Run targeted pytest and confirm failure.
- [ ] Add system template and scenario catalog entry.
- [ ] Update Excel template-selection logic.
- [ ] Run targeted pytest and commit.

### Task 2: Excel 解析增强

**Files:**
- Modify: `松山湖/单元模块库/ies_design/excel_parser.py`
- Test: `松山湖/单元模块库/ies_design/tests/test_excel_parser.py`

- [ ] Write failing tests for `energy_capacity_ub_kwh`, 24h TOU electricity price, and exported data file paths.
- [ ] Run targeted pytest and confirm failures.
- [ ] Preserve `energy_capacity_ub` from `06_候选设备配置`.
- [ ] Parse hourly electricity price rows as `type: tou_24h`.
- [ ] During export, write `data.load_file`, `data.resource_file`, and `typical_day.file` into `scenario.yaml`.
- [ ] Run targeted pytest and commit.

### Task 3: 烟厂场景样例目录

**Files:**
- Create: `松山湖/单元模块库/ies_design/scenarios/tobacco_factory/scenario.yaml`
- Create: `松山湖/单元模块库/ies_design/scenarios/tobacco_factory/README.md`
- Test: `松山湖/单元模块库/ies_design/tests/test_design_cli.py`

- [ ] Write failing CLI test that exports component plan for tobacco scenario with `--accept-future`.
- [ ] Generate or write scenario YAML from cleaned Excel with future generic template.
- [ ] Run CLI test and commit.

### Task 4: 通用后端烟厂组件计划验证

**Files:**
- Modify: `松山湖/单元模块库/ies_design/defaults/device_library.yaml`
- Modify if needed: `松山湖/单元模块库/ies_design/generic_backend_planner.py`
- Modify if needed: `松山湖/单元模块库/ies_design/generic_model_builder.py`
- Test: existing generic backend tests or new focused tests under `松山湖/单元模块库/ies_design/tests/`

- [ ] Write failing test that tobacco scenario component plan includes steam boiler, waste heat recovery, heat pump, heat storage, and conversion type summary.
- [ ] Add missing generic mappings or parameter requirements.
- [ ] Run tests and commit.

### Task 5: 文档与最终验证

**Files:**
- Modify: `松山湖/单元模块库/烟厂场景接入评估与数据清洗记录.md`
- Modify: `松山湖/单元模块库/README.md`

- [ ] Run smoke commands for Excel export, validation, component plan, and generic model build.
- [ ] Record commands and result files in documentation.
- [ ] Commit docs.
