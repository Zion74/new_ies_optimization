# SCI 论文：实验 / 图表 / 代码映射

更新时间：2026-04-10

## 1. 核心实验映射

| 编号 | 研究层 | 目的 | 实验设置 | 代码入口 |
|---|---|---|---|---|
| S1 | 规划层 | 建立 EQD 相对 5 种方法的主优势 | 德国案例 × `economic_only / std / euclidean / pearson / ssr` | `run.py --exp 1` |
| S2 | 规划层 | 验证跨案例普适性 | 松山湖案例 × `std / euclidean` | `run.py --exp 2` |
| S3 | 设备层 | 验证卡诺电池的配置价值 | 松山湖案例 × `euclidean`，无卡诺 vs 有卡诺 | `run.py --exp 3` |
| S4 | 设备层 | 验证有卡诺条件下 `std vs EQD` 的差异 | 松山湖 + Carnot × `std / euclidean` | `run.py --exp 4` |
| S5 | 强证据链 | 证明规划结果在全年运行上可兑现 | 8760h 后验运行指标分析 | `run_pipeline.py`、`scripts/post_analysis.py`、`scripts/enhanced_analysis.py` |
| S6 | 强证据链 | 证明㶲权重不是随便调参 | λ 敏感性 / 消融实验 | `scripts/lambda_sensitivity.py` |
| S7 | 强证据链 | 证明高匹配方案在极端场景下更稳 | 电价、气价、负荷、可再生波动情景 | `scripts/resilience_test.py` |

## 2. 图表清单与落点建议

> SCI 图表统一落到 `论文撰写/paper/figures/`。当前图表槽位已明确，但很多图仍需统一出图，不再把“最新结构说明”写在 LaTeX 目录里。

| 图 / 表 | 内容 | 主要数据来源 | 生成方式 / 责任脚本 | 当前状态 |
|---|---|---|---|---|
| Fig S1 | 德国案例 5 方法 Pareto 对比 | 实验 1 结果 | `run.py --exp 1` + 统一绘图脚本 | 待统一出图 |
| Fig S2 | 德国案例预算对齐后验运行指标 | S5 输出 | `scripts/enhanced_analysis.py` | 待统一出图 |
| Fig S3 | 松山湖 `std vs EQD` Pareto 对比 | 实验 2 结果 | `run.py --exp 2` + 统一绘图脚本 | 待统一出图 |
| Fig S4 | 无卡诺 vs 有卡诺 Pareto / 配置价值对比 | 实验 3 结果 | `run.py --exp 3` + 后处理 | 待统一出图 |
| Fig S5 | 有卡诺条件下 `std vs EQD` 对比 | 实验 4 结果 | `run.py --exp 4` + 后处理 | 待统一出图 |
| Fig S6 | λ 敏感性 / 消融图 | S6 输出 | `scripts/lambda_sensitivity.py` | 待统一出图 |
| Fig S7 | 韧性 / 极端场景成本退化图 | S7 输出 | `scripts/resilience_test.py` | 待统一出图 |
| Tab S1 | 两案例参数与温度参数表 | `case_config.py` | 手工整理 / LaTeX 表 | 待整理 |
| Tab S2 | 关键方案容量配置对比表 | S1-S4 的 Pareto 与折中解 | 后处理脚本 + 手工筛选 | 待整理 |
| Tab S3 | 全年运行指标对比表 | S5 输出 | `scripts/post_analysis.py` / `scripts/enhanced_analysis.py` | 待整理 |

## 3. 代码映射

- **规划核心**：`run.py`、`run_pipeline.py`、`cchp_gasolution.py`、`cchp_gaproblem.py`
- **案例与参数**：`case_config.py`
- **调度求解**：`operation.py`
- **后验运行分析**：`scripts/post_analysis.py`、`scripts/enhanced_analysis.py`
- **松山湖案例数据**：`scripts/generate_songshan_data.py`
- **敏感性 / 消融**：`scripts/lambda_sensitivity.py`
- **韧性 / 极端场景**：`scripts/resilience_test.py`

## 4. 稿件分节对应

| 章节 | 源码文件 |
|---|---|
| Introduction | `论文撰写/paper/sections/introduction.tex` |
| System modeling | `论文撰写/paper/sections/system_modeling.tex` |
| Matching index | `论文撰写/paper/sections/matching_index.tex` |
| Optimization | `论文撰写/paper/sections/optimization.tex` |
| Case studies | `论文撰写/paper/sections/case_studies.tex` |
| Results and discussion | `论文撰写/paper/sections/results.tex` |
| Conclusions | `论文撰写/paper/sections/conclusions.tex` |

## 5. 更新提醒

如果 SCI 主线从“规划层 + 设备层”变成别的结构，先改 `latest_logic_structure.md`，再改本映射表；不要只修改 `main.tex` 和 `sections/`。

## 6. 配套执行文档

- 服务器 full 实验清单：`docs/03_sci_paper/server_full_run_checklist.md`
- 图表与表格计划：`docs/03_sci_paper/figure_table_plan.md`

