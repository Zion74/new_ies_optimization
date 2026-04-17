# Scripts 目录说明

本目录存放三类脚本：

- 环境与服务器辅助脚本
- 实验运行与参数敏感性脚本
- 结果分析、作图与数据处理脚本

如果你是第一次接手这个仓库，建议按下面顺序理解：

1. 先看“环境与服务器辅助脚本”
2. 再看“实验运行脚本”
3. 最后按需要看“结果分析脚本”

## 1. 环境与服务器辅助脚本

### `openbayes_setup.sh`

用途：

- 在 OpenBayes 或 Linux 服务器上一键配置运行环境
- 自动安装 `uv`
- 根据 `.python-version` 安装 Python
- 执行 `uv sync`
- 尝试安装 `glpk`
- 打印求解器可用性
- 运行 `uv run python run.py --check`

最常用命令：

```bash
bash scripts/openbayes_setup.sh
```

常用环境变量：

```bash
IES_SKIP_RUN_CHECK=1 bash scripts/openbayes_setup.sh
IES_SKIP_GLPK_INSTALL=1 bash scripts/openbayes_setup.sh
```

### `rebuild_openbayes_env.sh`

用途：

- 在服务器环境损坏、换容器或需要强制重建 `.venv` 时使用
- 默认会删除项目 `.venv` 后重新调用 `openbayes_setup.sh`

最常用命令：

```bash
bash scripts/rebuild_openbayes_env.sh
```

如果还想顺便清掉本地 `uv` 缓存：

```bash
IES_PRUNE_UV_CACHE=1 bash scripts/rebuild_openbayes_env.sh
```

### `openbayes_run_experiments.sh`

用途：

- 面向 OpenBayes / Linux 服务器的一键实验总控脚本
- 支持：
  - 环境准备
  - 松山湖数据重建
  - 数据 sanity check
  - 顺序执行指定实验
  - 自动记录日志

适用场景：

- 你已经决定在服务器上批量跑实验，并希望把“环境准备 + 数据重建 + 正式运行”串成一次执行

### `archive_pre_rebuild_results.bat`

用途：

- Windows 下的本地辅助脚本
- 用于在重建数据或重跑实验前，归档旧结果

说明：

- 这是本地辅助脚本，不用于 OpenBayes Linux 容器

## 2. 实验运行与参数敏感性脚本

### `run_parameter_sensitivity.py`

用途：

- 一键执行参数敏感性分析
- 自动按多组 `(nind, maxgen)` 调用 `run.py`
- 自动识别新生成的结果目录
- 自动调用对比逻辑，输出 Markdown 报告

默认行为：

- 比较 `50x100`、`80x150`、`100x200`
- 默认用于论文实验 1 的参数规模敏感性分析

最常用命令：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

只看将执行什么命令：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28 --dry-run
```

自定义参数组：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28 --scales 50x100 70x120 90x180
```

### `run_exp4_sensitivity.py`

用途：

- 专门用于实验 4 风格的参数敏感性分析
- 默认固定：
  - `case = songshan_lake`
  - `carnot = on`
  - `methods = std euclidean`

推荐场景：

- 你怀疑 `exp4` 结果波动较大，想验证 `50/100` 是否足够

最常用命令：

```bash
uv run python scripts/run_exp4_sensitivity.py --workers 28
```

### `compare_parameter_scales.py`

用途：

- 对已经跑完的多组结果目录做离线比较
- 自动提取：
  - 最低成本
  - 最佳匹配度
  - Pareto 解数量
  - 可用时读取总耗时
- 输出 Markdown 对比表

最常用命令：

```bash
uv run python scripts/compare_parameter_scales.py \
  Results/<结果目录1> \
  Results/<结果目录2> \
  Results/<结果目录3>
```

## 3. 结果分析与论文图表脚本

### `post_analysis.py`

用途：

- 从 Pareto 解中筛方案
- 跑 8760h 或指定天数的调度分析
- 输出运行指标表

说明：

- 已经被 `run_pipeline.py` 集成
- 单独使用时适合对已有结果做后验分析

### `enhanced_analysis.py`

用途：

- 生成论文级对比图表
- 导出 LaTeX 表格
- 用于方法对比和预算增量等核心图

### `resilience_test.py`

用途：

- 做极端场景韧性测试
- 比较不同方案在故障或价格冲击下的表现

### `lambda_sensitivity.py`

用途：

- 做能质系数敏感性分析
- 对比不同 `lambda` 配置下的优化结果

### `run_existing_post_analysis.py`

用途：

- 针对已有实验结果补跑后验分析
- 适合“优化已完成，但还没做 Phase 2 分析”的场景

### `redraw_carnot_figures.py`

用途：

- 针对卡诺电池相关实验重绘图表
- 适合结果已在，但图风格或图注需要统一时使用

## 4. 数据生成与校验脚本

### `generate_songshan_data.py`

用途：

- 生成松山湖案例数据
- 是松山湖案例的重要数据入口脚本

### `check_songshan_data.py`

用途：

- 对松山湖数据做独立校验
- 常与数据重建流程配合使用

### `test_feasibility.py`

用途：

- 对模型可行性做快速测试
- 适合排查参数范围或新设备接入后的可行域问题

### `kmeans_clustering.py`

用途：

- 聚类相关脚本
- 一般用于典型日/负荷分类等预处理工作

### `kmeansClustering.m`

用途：

- `kmeans_clustering.py` 的 MATLAB 版本或历史对照版本

## 5. 图表、汇报与资料打包脚本

### `generate_conference_figures.py`

用途：

- 生成会议论文相关图表

### `generate_softcopyright_figures.py`

用途：

- 生成软著材料中的图表资源

### `generate_agency_softcopyright_package.py`

用途：

- 生成软著申报相关打包材料

### `create_q1_progress_pptx.py`

用途：

- 生成阶段性汇报 PPTX

### `export_ieee_conference_data.py`

用途：

- 导出会议论文或 IEEE 稿件使用的数据

### `archive_ieee_unit_lambda.py`

用途：

- 归档 IEEE / unit-lambda 相关实验结果或中间稿

## 6. 如何判断该用哪个脚本

如果你的目标是：

- 配服务器环境：用 `openbayes_setup.sh` / `rebuild_openbayes_env.sh`
- 跑正式实验：优先用 `run.py` 或 `run_pipeline.py`，必要时配合 `openbayes_run_experiments.sh`
- 做参数敏感性分析：用 `run_parameter_sensitivity.py`
- 只验证实验 4 的稳定性：用 `run_exp4_sensitivity.py`
- 只比较已完成结果：用 `compare_parameter_scales.py`
- 画论文图：用 `enhanced_analysis.py`
- 做后验分析：用 `post_analysis.py` 或 `run_existing_post_analysis.py`
- 重建松山湖数据：用 `generate_songshan_data.py`

## 7. 协作建议

给 AI 助手或新成员的最低建议是：

1. 先读本文件
2. 再看仓库根目录的 `OPENBAYES.md`
3. 明确自己要做的是“配环境 / 跑实验 / 做分析 / 画图”中的哪一种

如果要在服务器上接手运行，建议优先使用：

- `scripts/openbayes_setup.sh`
- `run.py`
- `scripts/run_parameter_sensitivity.py`

这三者已经覆盖了大多数日常实验需求。
