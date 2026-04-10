# SCI 服务器 Full 实验执行清单

更新时间：2026-04-10

本清单用于把当前 SCI 稿件从“结构已就位、结果待补齐”推进到“可按最终结果回填的正式版本”。

## 1. 当前结果状态

### 可先占位的结果

- 德国旧 full：`Results/pipeline_german_50x100_5methods_20260320_214813`
  - 可先占德国主实验与 8760h 后验分析的位置。
  - 原因：该结果已经包含 `comparison_report.md`、`post_analysis_results.csv`、`post_analysis_budget.csv`。
- 当前代码 quick 全套：`Results/quick_all_20x20_20260410_144724`
  - 可先验证实验结构、卡诺电池逻辑和图表槽位是否成立。
  - 不用于终稿定量结论，只用于 sanity check 和占位。

### 不能直接进终稿的结果

- 松山湖旧 full：`Results/pipeline_songshan_lake_50x100_5methods_20260322_115539`
  - 该结果中的 Songshan Lake 能质系数与当前代码不一致，不能直接作为终稿数据。
- 被打断的半成品目录：
  - `Results/pipeline_german_50x100_5methods_20260410_155234`
  - `Results/pipeline_songshan_lake_20x20_3methods_20260410_184955`

## 2. 服务器必须跑的 full 清单

### P0: 德国主实验 + 8760h 后验分析

命令：

```bash
uv run python run_pipeline.py --full --case german
```

用途：

- SCI `Results` 的 Experiment 1 主结果
- 德国 8760h 后验运行指标对比
- 德国 Pareto 宽度、预算增量、设备配置演化

稿件落点：

- `论文撰写/paper/sections/results.tex` 的 `Experiment 1`
- `Figure/Table Plan` 中的 Fig S2 / Tab S1 / Tab S2

### P0: 松山湖主实验 + 8760h 后验分析

命令：

```bash
uv run python run_pipeline.py --full --case songshan_lake
```

用途：

- SCI `Results` 的 Experiment 2
- 当前代码与当前 Songshan Lake 能质系数下的跨气候验证

稿件落点：

- `论文撰写/paper/sections/results.tex` 的 `Experiment 2`
- `Figure/Table Plan` 中的 Fig S3 / Tab S3

### P0: Experiment 3 - Carnot battery ablation

命令：

```bash
uv run python run.py --exp 3
```

用途：

- 比较 Songshan Lake 下 `EQD without Carnot` vs `EQD with Carnot`
- 补齐 SCI 第二贡献的第一半闭环

稿件落点：

- `论文撰写/paper/sections/results.tex` 的 `Experiment 3`
- `Figure/Table Plan` 中的 Fig S4 / Tab S4

### P0: Experiment 4 - Joint validation under Carnot integration

命令：

```bash
uv run python run.py --exp 4
```

用途：

- 比较 Songshan Lake + Carnot 下 `Std vs EQD`
- 验证卡诺电池条件下匹配度指标是否仍然决定设备识别能力

稿件落点：

- `论文撰写/paper/sections/results.tex` 的 `Experiment 4`
- `Figure/Table Plan` 中的 Fig S5 / Tab S5

## 3. 推荐补强实验

### P1: λ 敏感性 / 消融实验

```bash
uv run python scripts/lambda_sensitivity.py --case german --mode full
```

用途：

- 作为 SCI discussion 的强证据链
- 不属于主实验 1-4，但很适合放 discussion 或 appendix

### P1: 韧性 / 极端场景测试

在拿到 full 结果目录后运行：

```bash
uv run python scripts/resilience_test.py --result-dir <full_result_dir>
```

用途：

- 若最终保留“强证据链”表达，可放入 discussion 或 supplementary

## 4. 推荐执行顺序

为了尽快形成可回填的论文结果，建议服务器按下面顺序跑：

1. `uv run python run_pipeline.py --full --case german`
2. `uv run python run_pipeline.py --full --case songshan_lake`
3. `uv run python run.py --exp 3`
4. `uv run python run.py --exp 4`
5. `uv run python scripts/lambda_sensitivity.py --case german --mode full`（可选）
6. `uv run python scripts/resilience_test.py --result-dir <full_result_dir>`（可选）

## 5. 每个任务跑完后的最小检查

### 对 `run_pipeline.py` 结果目录

至少检查：

- `comparison_report.md`
- `Pareto_Comparison.png`
- `post_analysis_results.csv`
- `post_analysis_budget.csv`
- 各方法文件夹中的 `Pareto_*.csv`

### 对 `run.py --exp 3/4` 结果目录

至少检查：

- `comparison_report.md`
- `Pareto_Comparison.png`
- 各方法文件夹中的 `Pareto_*.csv`

## 6. 回传给论文的最小文件集

服务器结果回到本地后，至少需要把下面这些路径交给 SCI 稿件回填：

- 德国 full pipeline 结果目录
- Songshan Lake full pipeline 结果目录
- `exp3` 结果目录
- `exp4` 结果目录
- 若已跑消融 / 韧性，则对应输出目录

## 7. 本地电脑建议

- 本地只跑 quick，用于验证结构和脚本是否正常。
- 本地不再跑 full。
- 在服务器 full 结果回来之前，论文可以使用：
  - 德国旧 full 结果占位
  - 当前 quick 结果验证 Exp3 / Exp4 逻辑

## 8. 和稿件文件的对应关系

- 结果章节骨架：`论文撰写/paper/sections/results.tex`
- 图表规划：`docs/03_sci_paper/figure_table_plan.md`
- 实验 / 图表 / 代码总映射：`docs/03_sci_paper/experiment_figure_code_map.md`
