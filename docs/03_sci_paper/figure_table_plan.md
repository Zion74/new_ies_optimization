# SCI 图表与表格计划

更新时间：2026-04-10

本文件用于把 SCI 的主图、主表、数据来源、脚本来源和当前状态统一下来，避免结果回来后临时拼凑。

## 1. 主图计划

| 编号 | 建议标签 | 位置 | 目的 | 数据来源 | 当前状态 | 最终来源 |
|---|---|---|---|---|---|---|
| Fig S1 | `fig:topology` | System modeling | 展示 CCHP + Carnot battery 拓扑 | 手工绘制 / 系统模型 | 缺图 | 正式出图后放入 `论文撰写/paper/figures/` |
| Fig S2 | `fig:german_pareto` | Results / Exp1 | 展示德国 5 方法 Pareto 前沿与宽度差异 | 德国 full pipeline | 德国旧 full 可先占位 | 德国 current-code full |
| Fig S3 | `fig:german_budget` | Results / Exp1 | 展示德国预算增量下 8760h 运行指标变化 | 德国 full pipeline `post_analysis_budget.csv` | 德国旧 full 可先占位 | 德国 current-code full |
| Fig S4 | `fig:songshan_pareto` | Results / Exp2 | 展示松山湖 `Std vs EQD` 的跨气候验证 | Songshan full pipeline | 旧 full 仅供结构参考 | Songshan current-code full |
| Fig S5 | `fig:exp3_carnot_ablation` | Results / Exp3 | 展示 `EQD no-CB vs EQD with-CB` | `run.py --exp 3` | quick 可验证逻辑 | Exp3 full |
| Fig S6 | `fig:exp4_carnot_joint` | Results / Exp4 | 展示 `Std vs EQD` under Carnot | `run.py --exp 4` | quick 可验证逻辑 | Exp4 full |
| Fig S7 | `fig:lambda_sensitivity` | Discussion / Appendix | 展示 λ 消融或敏感性 | `scripts/lambda_sensitivity.py` | 待跑 | German λ full |
| Fig S8 | `fig:resilience` | Discussion / Appendix | 展示极端场景 / 韧性退化 | `scripts/resilience_test.py` | 待跑 | full result + resilience |

## 2. 主表计划

| 编号 | 建议标签 | 位置 | 目的 | 数据来源 | 当前状态 | 最终来源 |
|---|---|---|---|---|---|---|
| Tab S1 | `tab:exp1_pareto` | Results / Exp1 | 德国 5 方法 Pareto 特征汇总 | 德国 full pipeline | 德国旧 full 可先占位 | 德国 current-code full |
| Tab S2 | `tab:german_budget` | Results / Exp1 | 德国预算增量下运行指标对比 | 德国 `post_analysis_budget.csv` | 德国旧 full 可先占位 | 德国 current-code full |
| Tab S3 | `tab:songshan_budget` | Results / Exp2 | 松山湖 `Std vs EQD` 的关键指标与 trade-off | Songshan full pipeline | 旧 full 仅供结构参考 | Songshan current-code full |
| Tab S4 | `tab:exp3_carnot` | Results / Exp3 | 无卡诺 / 有卡诺的成本、匹配度、容量对比 | `run.py --exp 3` | quick 可占位 | Exp3 full |
| Tab S5 | `tab:exp4_carnot_joint` | Results / Exp4 | 有卡诺条件下 `Std vs EQD` 对比 | `run.py --exp 4` | quick 可占位 | Exp4 full |

## 3. 图表产出顺序

建议按这个顺序出图，和论文修改顺序一致：

1. Fig S2 + Tab S1（德国 Pareto）
2. Fig S3 + Tab S2（德国 8760h 后验）
3. Fig S4 + Tab S3（松山湖跨案例）
4. Fig S5 + Tab S4（Exp3 卡诺消融）
5. Fig S6 + Tab S5（Exp4 串联验证）
6. Fig S1（系统拓扑图）
7. Fig S7 / Fig S8（如保留补强证据链）

## 4. 各图表对应脚本

- 德国 / Songshan pipeline 结果：
  - `run_pipeline.py`
  - `scripts/post_analysis.py`
  - `scripts/enhanced_analysis.py`
- Exp3 / Exp4：
  - `run.py --exp 3`
  - `run.py --exp 4`
- λ 敏感性：
  - `scripts/lambda_sensitivity.py`
- 韧性：
  - `scripts/resilience_test.py`

## 5. 图表文字风格提醒

- 主图正文用“planning advantage”, “operational validation”, “cross-climate validation”, “Carnot battery value”, “joint validation”这一套固定措辞。
- 对 Songshan Lake 的图表说明必须明确 trade-off：EQD 不是所有指标都绝对占优，而是“更低外部购电 / 更高自给率 vs 更高 curtailment”。
- Exp3 / Exp4 的图注必须服务于“第二贡献闭环”，不要把卡诺电池写成独立论文主题。

## 6. 当前占位来源

在服务器 full 结果回来前，可先用以下来源占位结构：

- 德国主实验：`Results/pipeline_german_50x100_5methods_20260320_214813`
- 当前 sanity check：`Results/quick_all_20x20_20260410_144724`

但正式终稿只接受 current-code full 结果。
