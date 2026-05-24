# ies_design 场景化系统设计接口

第一版接口层目录，用于把 `scenario.yaml` / Excel 场景表转换为当前 CCHP 优化代码可调用的配置。现阶段采用“接口层适配器”路线：先把场景化输入解析成标准 resolved scenario，再转换为现有 `case_config.py` 字典，后续再逐步替换为通用 Pyomo / oemof 组件库。

## 当前已完成

- `defaults/`: 默认设备库、系统模板、15 种场景目录、组件映射和优化默认参数。
- `scenarios/songshan_lake/scenario.yaml`: 松山湖场景配置草案，对齐现有 `SONGSHAN_LAKE_CASE`。
- `scenarios/german/scenario.yaml`: 德国场景配置草案，对齐现有 `GERMAN_CASE`。
- `simple_yaml.py`: 项目 YAML 子集读取器，避免第一版额外引入 PyYAML 依赖。
- `scenario_loader.py`: 场景配置读取。
- `defaults_resolver.py`: 默认值合并，生成 resolved scenario 字典。
- `schema_validator.py`: resolved scenario 轻量校验，检查路径、模板、设备、时间序列与当前 CCHP 后端适配边界。
- `current_cchp_adapter.py`: 将 resolved scenario 转换成现有 `case_config.py` 风格配置。
- `design_optimizer.py`: 封装现有 `run_comparative_study()` 调用参数，形成新接口到当前 CCHP 优化后端的执行适配层。
- `result_exporter.py`: 将现有 Pareto 输出汇总为标准设计结果文件：`pareto_solutions.csv`、`design_summary.csv`、`design_summary_wide.csv`、`design_report.md`、`resolved_scenario.json`、`validation_report.md`。
- `design.py`: 仓库根目录的第一版 CLI 原型，支持场景校验、打印适配后的 CCHP 配置摘要、查看优化执行参数、触发 `mode=test` 优化并导出设计结果包。
- `tests/`: 轻量配置校验与适配器回归脚本。

## CLI 用法

```bash
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --validate-only
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/german/scenario.yaml" --print-case-config
python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --mode test --dry-run
uv run python design.py --scenario "松山湖/单元模块库/ies_design/scenarios/songshan_lake/scenario.yaml" --mode test
```

其中 `--dry-run` 只打印本次会传给现有优化器的 `nind/maxgen/methods/case_config` 摘要，不实际求解；去掉 `--dry-run` 后会调用现有 `cchp_gasolution.run_comparative_study()`。
当前仓库的优化依赖建议通过 `uv run python ...` 进入项目环境；系统 Python 可能缺少 `geatpy`。

## 验证命令

```bash
python "松山湖/单元模块库/ies_design/tests/validate_default_configs.py"
python "松山湖/单元模块库/ies_design/tests/test_resolve_scenarios.py"
python "松山湖/单元模块库/ies_design/tests/test_current_cchp_adapter.py"
python "松山湖/单元模块库/ies_design/tests/test_design_optimizer.py"
python "松山湖/单元模块库/ies_design/tests/test_result_exporter.py"
python "松山湖/单元模块库/ies_design/tests/test_design_cli.py"
```

## 下一步

- 增强结果导出层，补充 Excel 展示文件和原始结果归档。
- 实际跑通德国 `--mode test`，确认同一接口跨场景复用。
- 增加第三个场景的占位样例，先走 schema 与模板校验，后续再接真实数据。
