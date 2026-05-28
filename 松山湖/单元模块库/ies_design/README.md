# ies_design 场景化系统设计接口

第一版接口层目录，用于把 `scenario.yaml` / Excel 场景表转换为当前 CCHP 优化代码可调用的配置。现阶段采用“接口层适配器”路线：先把场景化输入解析成标准 resolved scenario，再转换为现有 `case_config.py` 字典，后续再逐步替换为通用 Pyomo / oemof 组件库。

## 当前已完成

- `defaults/`: 默认设备库、系统模板、15 种场景目录、组件映射和优化默认参数。
- `scenarios/songshan_lake/scenario.yaml`: 松山湖场景配置草案，对齐现有 `SONGSHAN_LAKE_CASE`。
- `scenarios/german/scenario.yaml`: 德国场景配置草案，对齐现有 `GERMAN_CASE`。
- `scenarios/songshan_lake_carnot/scenario.yaml`: 松山湖卡诺电池扩展示例，复用松山湖数据并启用卡诺电池容量变量。
- `simple_yaml.py`: 项目 YAML 子集读取器，避免第一版额外引入 PyYAML 依赖。
- `scenario_loader.py`: 场景配置读取。
- `excel_parser.py`: 读取课题组 Excel 模板并导出标准场景包。
- `typical_day.py`: 生成每月典型日或从 8760 数据聚类生成典型日。
- `defaults_resolver.py`: 默认值合并，生成 resolved scenario 字典。
- `schema_validator.py`: resolved scenario 轻量校验，检查路径、模板、设备、时间序列与当前 CCHP 后端适配边界。
- `current_cchp_adapter.py`: 将 resolved scenario 转换成现有 `case_config.py` 风格配置。
- `design_optimizer.py`: 封装现有 `run_comparative_study()` 调用参数，形成新接口到当前 CCHP 优化后端的执行适配层。
- `generic_model_builder.py`: 将通用组件计划转成可审计的母线、负荷、组件、连接、标准系统对象和动态容量变量规格。
- 储能类设备已支持“功率容量 + 能量容量”双变量抽象；若场景未显式给出能量容量上界，则按设备库 `default_energy_duration_h` 从功率上界推导。
- `generic_dispatch_inputs.py`: 从 resolved scenario 和真实 CSV 负荷文件构造最小真实电力调度输入。
- `generic_oemof_factory.py`: 将已应用容量的通用组件规格转成 OEMOF 节点，并已通过最小电力调度求解 smoke test。
- `generic_capacity_space.py`: 将 `capacity_variables` 转成可变维度的容量优化变量空间。
- `generic_dispatch_model.py`: 当前 `build_only` 的通用调度评价接口，输出容量映射、写回 `applied_capacities` 的组件规格、投资成本近似和构建缺口。
- `generic_design_optimizer.py`: 通用容量设计搜索接口，支持 demo levels、可复现 random 候选搜索和轻量 DE 搜索，后续可扩展为多目标 NSGA-II/DE。
- `generic_system.py`: P0 标准系统对象运行接口，向合作课题组暴露 `capacity_space()`、`default_capacity_assignment()` 和 `solve_dispatch(capacities)`。
- `scenarios/tobacco_factory/`: 第三个真实场景（卷烟厂），已支持通用线性 Energy Hub 真实调度求解、动态容量变量、蒸汽单位换算和 Level 3 验收结果导出。
- `result_exporter.py`: 将现有 Pareto 输出汇总为标准设计结果文件：`pareto_solutions.csv`、`design_summary.csv`、`design_summary_wide.csv`、`design_summary.xlsx`、`design_report.md`、`resolved_scenario.json`、`validation_report.md`。
- `design.py`: 仓库根目录的第一版 CLI 原型，支持场景校验、Excel 导出、典型日生成、打印适配后的 CCHP 配置摘要、查看优化执行参数、触发 `mode=test` 优化并导出设计结果包。
- `tests/`: 轻量配置校验与适配器回归脚本。

## CLI 用法

```bash
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --validate-only
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/german/scenario.yaml" --print-case-config
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --mode test --dry-run
python design.py --generate-typical-days monthly_template --output tmp_typical_days
uv run python design.py --excel "松山湖/单元模块库/课题组场景整理/课题组场景整理模板.xlsx" --export-scenario --output tmp_excel_export
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake_carnot/scenario.yaml" --run-generic-design --generic-search-levels 0 0.5 1 --output tmp_generic_design
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --run-generic-design --generic-search-levels 0.5 --solve-electric-dispatch --electric-dispatch-scope grid_pv_storage --dispatch-periods 24 --output tmp_generic_design_electric
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --run-generic-design --generic-search-levels 1.0 --solve-electric-dispatch --electric-dispatch-scope grid_pv_storage_heat_cool --dispatch-periods 24 --output tmp_generic_design_ehc
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --run-generic-design --generic-search-levels 1.0 --solve-electric-dispatch --electric-dispatch-scope grid_pv_storage_cchp --dispatch-periods 24 --output tmp_generic_design_cchp
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --run-generic-design --generic-search-strategy random --generic-candidates 8 --generic-random-seed 1 --solve-electric-dispatch --electric-dispatch-scope grid_pv_storage_cchp --dispatch-periods 24 --output tmp_generic_design_random
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --run-generic-design --generic-search-strategy de --generic-population 12 --generic-generations 5 --generic-random-seed 1 --solve-electric-dispatch --electric-dispatch-scope grid_pv_storage_cchp --dispatch-periods 24 --output tmp_generic_design_de
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/tobacco_factory/scenario.yaml" --run-generic-design --generic-search-levels 1.0 --solve-generic-dispatch --dispatch-month 1 --dispatch-periods 24 --accept-future --accept-default-bounds --output "DesignResults/tobacco_factory_level3_acceptance"
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/tobacco_factory/scenario.yaml" --build-generic-model --accept-future --accept-default-bounds --output "DesignResults/tobacco_factory_p0_export"
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --mode test
```

其中 `--dry-run` 只打印本次会传给现有优化器的 `nind/maxgen/methods/case_config` 摘要，不实际求解；去掉 `--dry-run` 后会调用现有 `cchp_gasolution.run_comparative_study()`。
当前仓库的优化依赖建议通过 `uv run python ...` 进入项目环境；系统 Python 可能缺少 `geatpy`。

## P0 对接接口

当前 P0 的合作边界是“模块库 + 系统拓扑装配器 + 标准系统对象 + 给定容量调度 API”。容量优化器可以读取导出的工件，也可以直接调用 Python API。

`--build-generic-model` 会额外导出：

- `system_object.json`: 标准系统对象，包含场景、系统、后端状态、能源母线、组件、连接、时序引用、设备/价格/仿真参数、容量变量、构建缺口和转换类型统计。
- `capacity_variables.json`: 机器可读容量变量清单，字段包括 `name`、`device_id`、`parameter`、`unit`、`lb`、`ub`、`default_value`、`is_fixed`、`source`，并兼容旧字段 `variable_name`、`role`、`lower_bound`、`upper_bound`、`bound_source`。
- `capacity_variables.csv`: 表格版容量变量清单，方便导师、用户和合作课题组人工核查变量数量、单位、上下界和默认来源。

Python API 示例：

```python
from pathlib import Path

from defaults_resolver import DefaultsResolver
from generic_system import GenericSystem
from scenario_loader import ScenarioLoader

root = Path("松山湖/单元模块库/ies_design")
scenario = ScenarioLoader.load(root / "scenarios/tobacco_factory/scenario.yaml")
resolved = DefaultsResolver(root / "defaults").resolve(scenario)

system = GenericSystem.from_resolved(resolved, project_root=Path.cwd())
capacity_space = system.capacity_space(month=1, periods=24, accept_default_bounds=True)
capacities = system.default_capacity_assignment(level=1.0, accept_default_bounds=True)
result = system.solve_dispatch(capacities, month=1, periods=24, accept_default_bounds=True)
```

对外推荐约定：

- 我们负责定义容量变量、变量单位、上下界、默认值、固定变量标记和设备到通用组件的映射。
- 合作课题组负责上层容量优化算法，但应使用 `capacity_variables` 生成候选容量，并调用 `solve_dispatch(capacities)` 评价给定容量后的运行调度。
- `system_object.json` 是跨语言/跨工具对接材料；`GenericSystem` 是当前 Python 闭环验证入口。

## 验证命令

```bash
python "松山湖/单元模块库/ies_design/tests/validate_default_configs.py"
python "松山湖/单元模块库/ies_design/tests/test_resolve_scenarios.py"
python "松山湖/单元模块库/ies_design/tests/test_current_cchp_adapter.py"
python "松山湖/单元模块库/ies_design/tests/test_design_optimizer.py"
uv run python "松山湖/单元模块库/ies_design/tests/test_result_exporter.py"
uv run python "松山湖/单元模块库/ies_design/tests/test_excel_parser.py"
python "松山湖/单元模块库/ies_design/tests/test_typical_day.py"
python "松山湖/单元模块库/ies_design/tests/test_third_placeholder.py"
python "松山湖/单元模块库/ies_design/tests/test_design_cli.py"
python "松山湖/单元模块库/ies_design/tests/test_generic_design_optimizer.py"
uv run python run_design_checks.py
uv run python run_design_checks.py --include-tobacco-level3
```

## Level 3 烟厂验收输出

烟厂场景不走旧版 `current_cchp`，而是通过 `future_generic` 的通用线性 Energy Hub 后端求解。验收命令会在 `DesignResults/tobacco_factory_level3_acceptance/` 下生成：

- `generic_design_solutions.json` / `generic_design_solutions.csv`：候选容量方案、调度求解状态、投资成本、调度目标和总目标。
- `generic_design_report.md`：标记 `Level 3`、`scope=linear_energy_hub` 和通用后端来源。
- `capacity_solution.csv`：设备容量结果，包含验收默认补齐的 `steam_boiler`、`pv`、`chp`、储能等动态容量变量。
- `dispatch_summary.csv`：调度求解摘要，包含求解器、终止状态、目标函数值和月份。
- `energy_flow_summary.csv`：电、热、冷、蒸汽、天然气、余热等能流汇总。
- `conversion_type_summary.csv`：多能转换类型数量、设备实例、输入/输出能源载体统计。
- `system_object.json` / `capacity_variables.json` / `capacity_variables.csv`：P0 标准系统对象和容量变量接口工件。

## 下一步

- 将当前 `grid + pv + electric_storage + chp + electric_heat_pump + electric_chiller + absorption_chiller + electric/heat/cooling_load` 真实调度切片继续扩展到冷热储能、卡诺电池和更多 15 场景设备。
- 将当前单目标轻量 DE 扩展为多目标 NSGA-II/DE，并补齐全年/典型日调度指标。
- 将 `GenericSystem` 的下层调度接口扩展到 12 个月典型日加权，并和上层多目标容量优化器形成更完整的双层优化闭环。
