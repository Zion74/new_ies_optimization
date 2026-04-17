# SCI 服务器 Full 实验执行清单

更新时间：2026-04-17（松山湖数据口径重建 + 实验编号重排后）

本清单用于把当前 SCI 稿件从"结构已就位、结果待补齐"推进到"可按最终结果回填的正式版本"。

如果只关心图表生成流程，先看：

- `docs/03_sci_paper/figure_generation_execution_order.md`

如果要在 OpenBayes / Linux 服务器上**一键跑完全流程**（含环境准备、数据重建、实验、Phase2 后验），看：

- `OPENBAYES.md` 第 3.4 节
- 命令：`bash scripts/openbayes_run_experiments.sh`

## 1. 当前结果状态

### 2026-04-17 之后：全部松山湖旧结果已归档

归档位置：`Results/服务器结果/_pre_rebuild_2026-04-17/`

原因：`ele_load` 从 166.64 → 69.59 万 kWh/年、冷峰值 5797 → 3460 kW、月度对齐表 2，
旧结果已不与当前 `data/songshan_lake_data.csv` 可比，不能与重建后实验混用。

### 可继续占位的结果

- 德国旧 full：`Results/pipeline_german_50x100_5methods_20260320_214813`
  - 德国案例数据源 `data/mergedData.csv` 未变，结果仍可占位。
  - 注意：旧 `run_pipeline.py` 生成的目录命名带 `pipeline_` 前缀；新框架会用 `exp1__german__base__...` 命名。

## 2. 服务器必须跑的 full 清单（2026-04-17 重排后）

### 最省事：一键全量

```bash
cd /openbayes/home/new_ies_optimization
git pull
bash scripts/openbayes_run_experiments.sh
```

日志落到 `logs/post_rebuild_<ts>/`；结果目录按 `run.py` 规则生成。

### P0：逐组手动（排障时用）

新实验编号映射：

| 新编号 | 内容 | 代码入口 | 稿件落点 |
|---|---|---|---|
| `exp1` | 德国 × 5 方法（创新点 1：EQD 方法对比） | `run.py --exp 1 --post-analysis-mode full` | `results.tex` Experiment 1；Fig S2 / Tab S1 / Tab S2 |
| `exp2` | 德国 × Carnot 有/无 × std+euclidean（创新点 2 核心证据） | `run.py --exp 2 --post-analysis-mode full` | `results.tex` Experiment 2；Fig S3 / Tab S3 |
| `exp3` | 松山湖 × std+euclidean（普适性验证） | `run.py --exp 3 --post-analysis-mode full` | `results.tex` Experiment 3；Fig S4 / Tab S4 |
| `exp4` | 松山湖 + Carnot × std+euclidean（普适性延伸 + 串联创新点） | `run.py --exp 4 --post-analysis-mode full` | `results.tex` Experiment 4；Fig S5 / Tab S5 |

说明：

- 每组实验**跑优化 + Phase2 后验**一条命令搞定，不再分 `run.py` 和 `run_pipeline.py`。
- Phase2 后验由 `scripts/post_analysis_report.py` 提供，自动输出 `post_analysis_results.csv`、`post_analysis_budget.csv`。
- 旧 `exp2 / exp3`（松山湖无 Carnot 方法对比 / 松山湖 Carnot 消融）已下线，不再跑。

## 3. 推荐补强实验

### P1：λ 敏感性 / 消融实验

```bash
uv run python scripts/lambda_sensitivity.py --case german --mode full
```

用途：作为 SCI discussion 的强证据链，不属于主实验 1-4，放 discussion 或 appendix。

### P1：韧性 / 极端场景测试

在拿到 full 结果目录后运行：

```bash
uv run python scripts/resilience_test.py --result-dir <full_result_dir>
```

用途：若最终保留"强证据链"表达，放入 discussion 或 supplementary。

### 参数敏感性分析：本轮跳过，但正式参数已从 50/100 调升到 80/150

前一版本已跑过 `50x100 / 80x150 / 100x200`（见
`Results/服务器结果/第二次实验/parameter_scale_comparison_fixed.md`），发现：

- `50/100` 对 `euclidean` 成本波动 2.1%、`ssr` 匹配度波动 76%，**不够稳**
- `80/150 → 100/200` 边际收益 <1%，**80/150 是性价比拐点**

结论已在 `docs/辩论确认/2026-04-16_Codex对Claude_Phase2回应.md` 共识 4 中定形，
`run.py` 于 2026-04-17 把正式参数默认值改为 `80/150`。本轮数据重建只改输入层，
不影响收敛特性，沿用该结论即可。

## 4. 推荐执行顺序

一键方式（首选）：

```bash
bash scripts/openbayes_run_experiments.sh
```

或分步：

1. `bash scripts/openbayes_setup.sh`
2. `uv run python scripts/generate_songshan_data.py`
3. `uv run python scripts/check_songshan_data.py`
4. `uv run python run.py --exp 1 --post-analysis-mode full`
5. `uv run python run.py --exp 2 --post-analysis-mode full`
6. `uv run python run.py --exp 3 --post-analysis-mode full`
7. `uv run python run.py --exp 4 --post-analysis-mode full`
8. `uv run python scripts/lambda_sensitivity.py --case german --mode full`（可选）
9. `uv run python scripts/resilience_test.py --result-dir <full_result_dir>`（可选）

## 5. 每个任务跑完后的最小检查

### 对 `run.py --exp N --post-analysis-mode full` 结果目录

至少检查：

- `comparison_report.md`
- `Pareto_Comparison.png`
- `post_analysis_results.csv`
- `post_analysis_budget.csv`
- 各方法文件夹中的 `Pareto_*.csv`

### 对 `run.py --exp 2` 目录（德国 Carnot both）

会产生两个子目录 `exp2a_` / `exp2b_`（无 / 有 Carnot），分别按上条检查。

## 6. 回传给论文的最小文件集

服务器结果回到本地后，至少需要把下面这些路径交给 SCI 稿件回填：

- `exp1` 德国主实验目录（5 方法 + Phase2 后验）
- `exp2a` / `exp2b` 德国 Carnot 有/无
- `exp3` 松山湖普适性
- `exp4` 松山湖 + Carnot
- λ 敏感性和韧性分析（如跑了）
