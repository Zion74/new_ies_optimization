# 三层映射表

更新时间：2026-04-10

## 1. 载体层 -> 研究层映射总表

| 载体层 | 这篇文档要完成的任务 | 主要承接的研究层 | 主实验 | 关键图表 | 主要代码文件 | 稿件目录 | 权威文档入口 |
|---|---|---|---|---|---|---|---|
| 会议论文 | 把一个核心概念讲清、讲硬，完成规划层 concept validation | 规划层（IEMI 几何表达） | 德国案例下 `economic_only / std / euclidean`；预算对齐的 8760h 后验验证 | `论文撰写/会议/figures/pareto_normalized.png`、`论文撰写/会议/figures/budget_sweep.png`、系统拓扑图 | `run_pipeline.py`、`run.py`、`cchp_gaproblem.py`、`operation.py`、`scripts/export_ieee_conference_data.py`、`scripts/generate_conference_figures.py` | `论文撰写/会议/` | `docs/02_conference_paper/` |
| SCI 论文 | 把核心创新扩展成完整论文故事，形成更强证据链 | 规划层（EQD 正式展开） + 设备层（卡诺电池配置价值） | 实验 1-4；外加 8760h 后验分析、λ 敏感性、韧性 / 极端场景支撑 | 五方法 Pareto、双案例对比、无 / 有卡诺对比、卡诺下 `std vs EQD`、运行指标与敏感性图组 | `run.py`、`run_pipeline.py`、`case_config.py`、`cchp_gaproblem.py`、`operation.py`、`scripts/post_analysis.py`、`scripts/enhanced_analysis.py`、`scripts/lambda_sensitivity.py`、`scripts/resilience_test.py` | `论文撰写/paper/` | `docs/03_sci_paper/` |
| 硕士论文 | 把会议与 SCI 纳入规划-设备-运行闭环，形成章节递进 | 第 2 章规划层 + 第 3 章设备层 + 第 4 章运行层 | 规划层沿用实验 1 / 2；设备层沿用实验 3 / 4；运行层新增负荷预测、日前调度、鲁棒性实验 | 第 2 章 Pareto / 后验 / 敏感性图组；第 3 章卡诺电池价值图组；第 4 章预测架构、预测精度、日前 / 实时对比与鲁棒性图组 | 当前已落地代码 + `scripts/resilience_test.py`；预测与日前调度模块待新增 | 硕士论文正式稿待统一落地 | `docs/04_master_thesis/` |

## 2. 研究层 -> 载体层分工表

| 研究层 | 会议论文 | SCI 论文 | 硕士论文 |
|---|---|---|---|
| 规划层 | **核心承载**：只保留 IEMI 这一条主线，强调 concept validation | **核心承载**：升级为 EQD，补足㶲权重与两案例证据链 | **第 2 章**：系统化收束规划层理论、实验与讨论 |
| 设备层 | 不作为会议主线，只能轻量作为 journal extension 提及 | **核心扩展**：卡诺电池集成、无 / 有卡诺对比、配置价值分析 | **第 3 章**：独立成章，做设备层闭环验证 |
| 运行层 | 不承担 | 只保留后验运行指标、敏感性和韧性作为强证据，不展开完整预测章节 | **第 4 章**：负荷预测、日前调度、鲁棒性验证完整展开 |

## 3. 未来同步更新的最小动作

当任何一层发生变化时，默认执行下面动作：

1. 先判断变化属于会议、SCI、硕士论文哪一层。
2. 更新对应层级的 `latest_logic_structure.md`。
3. 更新对应层级的实验 / 图表 / 代码映射文档。
4. 如果改变了三层之间的边界，再同步更新本文件和 `latest_research_architecture.md`。

