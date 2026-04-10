# 会议论文：实验 / 图表 / 代码映射

更新时间：2026-04-10

## 1. 实验映射

| 编号 | 目的 | 实验设置 | 主要输出 | 主要落点 |
|---|---|---|---|---|
| C1 | 验证 IEMI 相比 `economic_only` 与 `std` 的规划差异 | 德国案例；方法 `economic_only / std / euclidean` | Pareto 前沿、候选容量配置 | `Results/...`、`论文撰写/会议/data/raw_pareto/` |
| C2 | 把规划优势落到全年运行指标上 | 从 Pareto 中选预算可比方案，跑 8760h 后验运行 | 峰值购电、年购电量、自给率、电网波动等 | `论文撰写/会议/data/conference_budget_path.csv` |
| C3 | 做附录级稳健检查，说明结果不依赖等权 λ 写法 | `unit-lambda` 烟测或归档实验 | 对照摘要表 | `论文撰写/会议/data/summary_conference_unit_lambda.csv` |

## 2. 图表映射

| 图 / 表 | 内容 | 数据来源 | 生成方式 | 当前落点 |
|---|---|---|---|---|
| Fig C1 | 规划层系统拓扑 / 方法示意图 | 系统模型与方法描述 | 手工绘制或 LaTeX 图 | 建议统一放 `论文撰写/会议/figures/` |
| Fig C2 | IEMI vs Std 归一化 Pareto 对比 | `summary_conference.csv` | `scripts/generate_conference_figures.py` | `论文撰写/会议/figures/pareto_normalized.png` |
| Fig C3 | 预算增量下运行指标对比 | `conference_budget_path.csv` | `scripts/generate_conference_figures.py` | `论文撰写/会议/figures/budget_sweep.png` |
| Tab C1 | 会议稿核心摘要表 | `summary_conference.csv` | `scripts/export_ieee_conference_data.py` | `论文撰写/会议/data/summary_conference.csv` |
| Tab C2 | 预算对齐方案的容量与运行指标表 | `conference_selected_capacities.csv`、`conference_budget_path.csv` | `scripts/generate_conference_figures.py` | `论文撰写/会议/data/` |

## 3. 代码映射

- `run_pipeline.py`：一键串起“优化 + 后验运行分析”，适合会议稿主结果再现。
- `run.py`：论文实验入口；会议稿主要消费实验 1 的结果，但通常只选三种方法入文。
- `case_config.py`：案例参数、温度参数与 carrier weights 来源。
- `cchp_gaproblem.py`：`euclidean` 方法的目标函数实现，是 IEMI / EQD 的代码源头。
- `operation.py`：24h 调度求解，支撑 14 个典型日与后验全年分析。
- `scripts/export_ieee_conference_data.py`：导出会议稿摘要表。
- `scripts/generate_conference_figures.py`：生成会议稿的 Pareto 图和预算图。
- `scripts/archive_ieee_unit_lambda.py`：归档等权 λ 烟测结果，防止活跃目录混乱。

## 4. 稿件分节对应

| 章节 | 源码文件 |
|---|---|
| Introduction | `论文撰写/会议/sections_conference/introduction.tex` |
| Matching index | `论文撰写/会议/sections_conference/matching_index.tex` |
| Optimization | `论文撰写/会议/sections_conference/optimization.tex` |
| Case studies | `论文撰写/会议/sections_conference/case_studies.tex` |
| Results | `论文撰写/会议/sections_conference/results.tex` |
| Conclusions | `论文撰写/会议/sections_conference/conclusions.tex` |

## 5. 更新提醒

只要会议稿的核心论点从“IEMI 概念验证”转向别的东西，必须先改 `latest_logic_structure.md`，再改本表；不要只在 LaTeX 里改而不回写 `docs/`。

