# Third Scenario and GenericModelBuilder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third real computable scenario using the current CCHP backend and start the GenericModelBuilder path toward dynamic-variable double-layer optimization.

**Architecture:** The third scenario is a Songshan Lake Carnot-battery extension that reuses real Songshan Lake data and differs structurally from the base case by enabling Carnot storage. GenericModelBuilder consumes the existing generic component plan and builds an auditable OEMOF/Pyomo-ready component layer first; later work will connect its dynamic capacity variables to the outer capacity optimizer.

**Tech Stack:** Python, YAML, existing `current_cchp` optimizer, `oemof.solph` when available, JSON/Markdown/CSV reports.

---

### Task 1: Third Real Computable Scenario

**Files:**
- Create: `松山湖/单元模块库/ies_design/scenarios/songshan_lake_carnot/scenario.yaml`
- Create: `松山湖/单元模块库/ies_design/scenarios/songshan_lake_carnot/README.md`
- Modify: `松山湖/单元模块库/ies_design/tests/test_resolve_scenarios.py`
- Modify: `run_design_checks.py`

Steps:
- Copy Songshan Lake base scenario.
- Set `scenario.id: songshan_lake_carnot`.
- Set `system.template: cchp_ehc_carnot`.
- Enable `carnot_battery.enabled: true`.
- Assert validation is `runnable`.
- Add dry-run check to `run_design_checks.py`.
- Commit as `feat: add songshan lake carnot scenario`.

### Task 2: GenericModelBuilder First Stage

**Files:**
- Create: `松山湖/单元模块库/ies_design/generic_model_builder.py`
- Create: `松山湖/单元模块库/ies_design/tests/test_generic_model_builder.py`

Steps:
- Build from resolved scenario or generic component plan.
- Produce buses, component specs, capacity variables, build gaps, and optional OEMOF EnergySystem.
- Support `Source`, `Sink`, `Transformer`, `GenericStorage` specs.
- Do not solve yet.
- Commit as `feat: add generic model builder`.

### Task 3: CLI Export for Generic Model Build

**Files:**
- Modify: `design.py`
- Modify: `run_design_checks.py`
- Modify: `松山湖/单元模块库/ies_design/tests/test_design_cli.py`

Steps:
- Add `--build-generic-model`.
- Export `generic_model_components.json`, `generic_model_build_report.md`, and `generic_model_build_gaps.csv`.
- Allow this for `future_supported` with `--accept-future` and for runnable scenes.
- Commit as `feat: export generic model build artifacts`.

### Task 4: Verification and Documentation

**Files:**
- Modify: `松山湖/单元模块库/场景化系统设计接口使用说明书.md`
- Modify: `松山湖/单元模块库/第一版场景化系统设计接口闭环验证报告.md`
- Modify: `项目索引目录.md`

Steps:
- Run third scenario demo.
- Run `run_design_checks.py`.
- Document third scenario and GenericModelBuilder boundary.
- Commit as `docs: document third scenario and generic builder`.

