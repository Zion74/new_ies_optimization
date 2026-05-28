# 单元模块库文档索引

本目录现在按“代码 / 系统设计 / 场景整理 / 统一建模 / 原始资料”分区，根目录只保留总入口和少量历史代码文件，避免验收材料、Excel 模板和建模资料混在一起。

## 推荐阅读顺序

1. `系统设计/三场景全流程验收报告.md`：验收时先看，包含松山湖、德国、烟厂三场景跑通证据，以及烟厂轻量双层优化 test 验证。
2. `系统设计/多能转换单元模块库使用说明书.md`：给导师、合作组和师弟看的使用说明，解释输入、命令、输出和新增场景流程。
3. `课题组场景整理/烟厂场景接入评估与数据清洗记录.md`：第三场景数据来源、清洗、容量边界和 Level 3 求解记录。
4. `ies_design/README.md`：开发者入口，查看代码结构、CLI 命令和测试脚本。
5. `统一建模/源荷储转设备库统一建模接口规范.md`：理解设备库抽象、EMS 对接和源荷储转统一建模边界。

## 目录分区

| 路径 | 作用 |
|---|---|
| `ies_design/` | 场景化系统设计接口代码：默认库、场景 YAML、Excel 解析、校验、通用组件计划、通用模型构建、容量搜索、调度求解和测试。 |
| `系统设计/` | 当前项目接口设计、验收报告、使用说明、责任边界、第一版任务清单和开发复盘。 |
| `课题组场景整理/` | 发给师弟或合作方填写的 Excel 模板、15 场景参考表、烟厂清洗版 Excel 和数据清洗记录。 |
| `统一建模/` | 源荷储转设备库统一建模、EMS 对接、设备按类型抽象建模、松山湖场景梳理等背景资料。 |
| `单元模块库代码/` | 多能转换设备模块库代码及归档版本。 |
| `烟厂场景/` | 烟厂项目原始资料和外部模型数据，作为第三场景溯源资料。 |
| `assets/` | 文档图片资源。 |

## 关键验收材料

| 文档 | 简介 |
|---|---|
| `系统设计/三场景全流程验收报告.md` | 记录松山湖、德国、烟厂三个场景从标准输入、模块库调用、模型装配、求解到结果导出的全流程验收证据。 |
| `系统设计/多能转换单元模块库使用说明书.md` | 面向导师、合作者和师弟的使用说明，解释最小输入、标准 YAML/Excel、运行命令、结果文件和新增场景流程。 |
| `系统设计/项目责任边界与对接架构讨论记录.md` | 明确导师项目与个人论文实验边界，沉淀模块库、拓扑装配器、标准系统对象、优化器对接和中期验收口径。 |
| `课题组场景整理/烟厂场景接入评估与数据清洗记录.md` | 评估卷烟厂第三真实结构场景，记录 Excel 清洗、原始数据核查、结题材料容量约束、future_generic 接入和 Level 3 求解。 |
| `课题组场景整理/课题组场景整理模板.xlsx` | 发给师弟整理新场景的空白 Excel 模板。 |
| `课题组场景整理/课题组场景整理模板_烟厂_清洗版.xlsx` | 烟厂场景清洗副本，修复负荷重复/错位问题，扩展资源曲线并补充容量约束。 |

## 常用命令

```bash
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\songshan_lake\scenario.yaml" --mode demo --output "DesignResults\three_scenario_acceptance\songshan_lake_demo"
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\german\scenario.yaml" --mode demo --output "DesignResults\three_scenario_acceptance\german_demo"
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\tobacco_factory\scenario.yaml" --run-generic-design --generic-search-levels 1.0 --solve-generic-dispatch --dispatch-month 1 --dispatch-periods 24 --accept-future --accept-default-bounds --output "DesignResults\three_scenario_acceptance\tobacco_factory_level3"
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\tobacco_factory\scenario.yaml" --run-generic-design --generic-search-strategy de --generic-population 4 --generic-generations 1 --generic-random-seed 1 --solve-generic-dispatch --dispatch-month 1 --dispatch-periods 24 --accept-future --accept-default-bounds --output "DesignResults\tobacco_factory_bilevel_test"
rtk uv run python run_design_checks.py --include-tobacco-level3
```
