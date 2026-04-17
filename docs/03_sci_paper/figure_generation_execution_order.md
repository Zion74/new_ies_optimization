# SCI 图表生成执行顺序

更新时间：2026-04-14

## 1. 这份清单解决什么问题

`results_analysis_expansion_plan.md` 已经回答了“该分析什么”，本清单继续回答：

- 先出哪几张图
- 每张图用哪一批结果
- 具体调用哪个脚本
- 脚本执行顺序是什么
- 脚本跑完后，到哪个目录找图

原则：

- `先复用现有 full 结果补图`
- `再对缺口实验做 full / pipeline 重跑`
- `先主图，后补强图`

## 2. 当前可直接使用的结果目录

### 当前主结果根目录

```text
Results/服务器结果/full_all_50x100_20260413_134312/full_all_50x100_20260413_134312
```

### 子实验目录

```text
exp1_german_50x100_5methods_20260413_134312
exp2_songshan_lake_50x100_std+euclidean_20260413_153358
exp3a_songshan_lake_50x100_euclidean_20260413_161721
exp3b_songshan_lake_carnot_50x100_euclidean_20260413_163925
exp4_songshan_lake_carnot_50x100_std+euclidean_20260413_170421
```

建议先在 PowerShell 中定义这些变量：

```powershell
$root = "D:\OneDrive\研究生\我的成果\小论文\源荷匹配的分布式电热综合能源系统优化规划\代码探索\ies_optimization\Results\服务器结果\full_all_50x100_20260413_134312\full_all_50x100_20260413_134312"
$exp1 = Join-Path $root "exp1_german_50x100_5methods_20260413_134312"
$exp2 = Join-Path $root "exp2_songshan_lake_50x100_std+euclidean_20260413_153358"
$exp3a = Join-Path $root "exp3a_songshan_lake_50x100_euclidean_20260413_161721"
$exp3b = Join-Path $root "exp3b_songshan_lake_carnot_50x100_euclidean_20260413_163925"
$exp4 = Join-Path $root "exp4_songshan_lake_carnot_50x100_std+euclidean_20260413_170421"
```

## 3. 主图优先级

建议正文主图按这个顺序出：

1. `Fig S2` 德国 Pareto 主图
2. `Fig S3` 德国 `8760h` 预算对齐运行图
3. `Fig S4` 松山湖跨案例图
4. `Fig S5` 卡诺电池消融图
5. `Fig S6` 有卡诺条件下 `Std vs EQD` 图
6. `Fig S7` λ 敏感性图
7. `Fig S8` 韧性图

原因：

- 先把正文最核心的规划层与设备层闭环补齐
- 再补 discussion / appendix 的强证据链

## 4. 每张图的来源、命令与输出

## 4.1 Fig S2 德国 Pareto 主图

### 目标

- 展示德国案例五方法 Pareto 前沿
- 后续正文只讲“裁剪后可接受预算区间”

### 第一步：对现有 `exp1` 做后验分析

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp1" --mode full
```

作用：

- 生成 `post_analysis_results.csv`
- 生成 `post_analysis_budget.csv`

### 第二步：生成增强分析图

```powershell
uv run python scripts/enhanced_analysis.py --result-dir "$exp1" --methods Std Euclidean Pearson SSR --latex
```

重点输出：

```text
$exp1\enhanced_analysis\Fig_Pareto_Width_Comparison.png
$exp1\enhanced_analysis\Fig_Capacity_Evolution_Std.png
$exp1\enhanced_analysis\Fig_Capacity_Evolution_Euclidean.png
$exp1\enhanced_analysis\latex_tables.tex
```

### 可直接引用的现有图

```text
$exp1\Pareto_Comparison.png
```

### 论文落点建议

- 主图：`Pareto_Comparison.png` 或统一重绘后的裁剪版
- 辅图：`Fig_Pareto_Width_Comparison.png`

## 4.2 Fig S3 德国预算对齐后的 8760h 运行图

### 命令

在完成上一步 `run_existing_post_analysis.py` 后执行：

```powershell
uv run python scripts/enhanced_analysis.py --result-dir "$exp1" --methods Std Euclidean Pearson SSR --latex
```

### 重点输出

```text
$exp1\enhanced_analysis\Fig_Budget_Increment_Comparison.png
$exp1\post_analysis_results.csv
$exp1\post_analysis_budget.csv
```

### 论文落点建议

- 主图：`Fig_Budget_Increment_Comparison.png`
- 主表：从 `post_analysis_budget.csv` 和 `latex_tables.tex` 整理 `Tab S2`

## 4.3 Fig S4 松山湖跨案例验证图

### 第一步：对现有 `exp2` 做后验分析

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp2" --mode full
```

### 第二步：增强分析

```powershell
uv run python scripts/enhanced_analysis.py --result-dir "$exp2" --methods Std Euclidean --latex
```

### 重点输出

```text
$exp2\Pareto_Comparison.png
$exp2\enhanced_analysis\Fig_Budget_Increment_Comparison.png
$exp2\enhanced_analysis\Fig_Capacity_Evolution_Std.png
$exp2\enhanced_analysis\Fig_Capacity_Evolution_Euclidean.png
```

### 论文落点建议

- 主图优先：`Pareto_Comparison.png`
- 若要强化设备机制：补 `Fig_Capacity_Evolution_Euclidean.png`

## 4.4 Fig S5 卡诺电池消融图

### 当前结果结构

- `exp3a`：Songshan Lake，无卡诺，`Euclidean`
- `exp3b`：Songshan Lake，有卡诺，`Euclidean`

### 推荐做法

这组图优先使用：

- 两个目录中的 `comparison_report.md`
- 两个目录中的 `Pareto_Euclidean.csv`
- 两个目录中的现成 `Pareto_Comparison.png`

### 如果要补后验运行图

分别运行：

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp3a" --mode full
uv run python scripts/run_existing_post_analysis.py "$exp3b" --mode full
```

再分别运行：

```powershell
uv run python scripts/enhanced_analysis.py --result-dir "$exp3a" --methods Euclidean --latex
uv run python scripts/enhanced_analysis.py --result-dir "$exp3b" --methods Euclidean --latex
```

### 当前最有用的输出

```text
$exp3a\comparison_report.md
$exp3b\comparison_report.md
$exp3a\Euclidean\Pareto_Euclidean.csv
$exp3b\Euclidean\Pareto_Euclidean.csv
```

### 论文落点建议

- 主图：建议后续统一绘制“无卡诺 vs 有卡诺”的成本-匹配对比图
- 主表：直接从 `comparison_report.md` 和 `Pareto_Euclidean.csv` 提炼 `Tab S4`

### 统一重绘脚本

在 `exp3a / exp3b` 后验分析完成后，运行：

```powershell
uv run python scripts/redraw_carnot_figures.py --exp3a-dir "C:\codex_tmp\exp3a" --exp3b-dir "C:\codex_tmp\exp3b" --exp4-dir "C:\codex_tmp\exp4"
```

输出：

```text
C:\codex_tmp\carnot_redraw\Fig_Exp3_Carnot_Ablation_Pareto.png
C:\codex_tmp\carnot_redraw\Fig_Exp3_Carnot_Ablation_Budget.png
```

## 4.5 Fig S6 有卡诺条件下 `Std vs EQD`

### 第一步：对现有 `exp4` 做后验分析

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp4" --mode full
```

### 第二步：增强分析

```powershell
uv run python scripts/enhanced_analysis.py --result-dir "$exp4" --methods Std Euclidean --latex
```

### 重点输出

```text
$exp4\Pareto_Comparison.png
$exp4\enhanced_analysis\Fig_Budget_Increment_Comparison.png
$exp4\enhanced_analysis\Fig_Capacity_Evolution_Std.png
$exp4\enhanced_analysis\Fig_Capacity_Evolution_Euclidean.png
```

### 论文落点建议

- 主图：`Pareto_Comparison.png`
- 辅图：`Fig_Capacity_Evolution_Euclidean.png`
- 主表：从 `comparison_report.md` + `post_analysis_results.csv` 整理 `Tab S5`

### 统一重绘脚本

同样由下面的统一脚本输出：

```powershell
uv run python scripts/redraw_carnot_figures.py --exp3a-dir "C:\codex_tmp\exp3a" --exp3b-dir "C:\codex_tmp\exp3b" --exp4-dir "C:\codex_tmp\exp4"
```

输出：

```text
C:\codex_tmp\carnot_redraw\Fig_Exp4_Carnot_Joint_Pareto.png
C:\codex_tmp\carnot_redraw\Fig_Exp4_Carnot_Joint_Budget.png
```

## 4.6 Fig S7 λ 敏感性图

### 命令

```powershell
uv run python scripts/lambda_sensitivity.py --case german --mode full
```

如果本地先做验证：

```powershell
uv run python scripts/lambda_sensitivity.py --case german --mode quick
```

### 输出目录格式

```text
Results/lambda_sensitivity_german_full_<timestamp>/
```

### 重点输出

```text
Fig_Lambda_Sensitivity_Pareto.png
Fig_Lambda_Sensitivity_Capacity.png
lambda_sensitivity_report.md
```

## 4.7 Fig S8 极端场景韧性图

### 推荐先基于德国主实验结果运行

若已经拿到 German pipeline full 目录：

```powershell
uv run python scripts/resilience_test.py --result-dir "<german_pipeline_full_dir>" --case german
```

如果先用现有 `exp1` 验证结构，也可以：

```powershell
uv run python scripts/resilience_test.py --result-dir "$exp1" --case german
```

### 重点输出

```text
<result_dir>\resilience_test\Fig_Resilience_Cost_Comparison.png
<result_dir>\resilience_test\Fig_Resilience_Success_Rate.png
<result_dir>\resilience_test\resilience_test_report.md
```

## 5. 建议的实际执行顺序

下面这组顺序最适合你当前状态。

## Phase A：立刻可做

### A1 德国主图

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp1" --mode full
uv run python scripts/enhanced_analysis.py --result-dir "$exp1" --methods Std Euclidean Pearson SSR --latex
```

### A2 松山湖跨案例图

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp2" --mode full
uv run python scripts/enhanced_analysis.py --result-dir "$exp2" --methods Std Euclidean --latex
```

### A3 有卡诺联合验证图

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp4" --mode full
uv run python scripts/enhanced_analysis.py --result-dir "$exp4" --methods Std Euclidean --latex
```

### A4 卡诺消融表

```powershell
uv run python scripts/run_existing_post_analysis.py "$exp3a" --mode full
uv run python scripts/run_existing_post_analysis.py "$exp3b" --mode full
```

说明：

- `exp3a / exp3b` 主要先产出后验表和运行指标
- 图形可后面统一重绘

## Phase B：补强图

### B1 λ 敏感性

```powershell
uv run python scripts/lambda_sensitivity.py --case german --mode full
```

### B2 韧性图

```powershell
uv run python scripts/resilience_test.py --result-dir "$exp1" --case german
```

## 6. 每一步跑完后该检查什么

## 6.1 对 `run_existing_post_analysis.py`

检查：

```text
post_analysis_results.csv
post_analysis_budget.csv
```

如果没有这两个文件，后续 `enhanced_analysis.py` 不能正常形成预算对齐图。

## 6.2 对 `enhanced_analysis.py`

检查目录：

```text
<result_dir>\enhanced_analysis\
```

至少应有：

```text
Fig_Budget_Increment_Comparison.png
Fig_Pareto_Width_Comparison.png
Fig_Capacity_Evolution_*.png
latex_tables.tex
statistical_test.md
```

## 6.3 对 `lambda_sensitivity.py`

至少应有：

```text
Fig_Lambda_Sensitivity_Pareto.png
Fig_Lambda_Sensitivity_Capacity.png
lambda_sensitivity_report.md
```

## 6.4 对 `resilience_test.py`

至少应有：

```text
Fig_Resilience_Cost_Comparison.png
Fig_Resilience_Success_Rate.png
resilience_test_report.md
```

## 7. 图表落到论文目录时的建议命名

建议最终统一复制到：

```text
论文撰写/paper/figures/
```

建议命名：

- `fig_s2_german_pareto.png`
- `fig_s3_german_budget_8760h.png`
- `fig_s4_songshan_pareto.png`
- `fig_s5_carnot_ablation.png`
- `fig_s6_carnot_joint_validation.png`
- `fig_s7_lambda_sensitivity.png`
- `fig_s8_resilience.png`

## 8. 最稳的出图节奏

如果只想先把正文主图补齐，不要一次把所有脚本都跑完。最稳的节奏是：

1. `exp1` 的 `run_existing_post_analysis`
2. `exp1` 的 `enhanced_analysis`
3. `exp2` 的 `run_existing_post_analysis`
4. `exp2` 的 `enhanced_analysis`
5. `exp4` 的 `run_existing_post_analysis`
6. `exp4` 的 `enhanced_analysis`
7. 再补 `exp3a/exp3b`
8. 最后再跑 `lambda_sensitivity` 和 `resilience`

这样可以最快把正文 `Fig S2 ~ Fig S6` 先补出来。
