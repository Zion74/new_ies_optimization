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
- 将"环境准备 → 松山湖数据重建 → sanity check → `run.py --exp ...` → Phase2 后验"串成一次执行
- 每个阶段日志单独落盘到 `logs/post_rebuild_<timestamp>/`，并生成 `SUMMARY.md`

最常用命令：

```bash
bash scripts/openbayes_run_experiments.sh                     # 全量正式跑
IES_TEST_RUN=1 bash scripts/openbayes_run_experiments.sh      # 10 分钟级烟测
IES_EXP="1 2" bash scripts/openbayes_run_experiments.sh       # 只跑部分实验
IES_SKIP_SETUP=1 IES_SKIP_DATA_REGEN=1 IES_SKIP_SANITY=1 \
  bash scripts/openbayes_run_experiments.sh                   # 跳过准备，只重跑实验
IES_WORKERS=28 bash scripts/openbayes_run_experiments.sh      # 改并行数
IES_STRICT_SANITY=1 bash scripts/openbayes_run_experiments.sh # sanity WARN 即中止
```

环境变量一览：

- `IES_EXP`：要跑的实验（`"1 2 3 4"` 或 `"all"`，默认 `all`）
- `IES_WORKERS`：并行 worker 数（默认由 `run.py` 自动取 CPU 核数）
- `IES_POST_MODE`：Phase2 后验模式（`test/quick/medium/full`，默认 `medium`）
- `IES_TEST_RUN`：1=用 `nind=10/maxgen=5` 烟测
- `IES_QUICK_RUN`：1=用 `nind=20/maxgen=20` 初步验证
- `IES_SKIP_SETUP` / `IES_SKIP_DATA_REGEN` / `IES_SKIP_SANITY`：跳过对应阶段
- `IES_STRICT_SANITY`：1=sanity 任一 WARN 即 exit 1
- `IES_RUN_TAG`：日志目录前缀（默认 `post_rebuild`）

### `archive_pre_rebuild_results.ps1`

用途：

- Windows 本地辅助脚本（PowerShell 5.1+，UTF-8 BOM，不用于 Linux 容器）
- 在 2026-04-17 松山湖数据口径重建之后，把不可比的旧结果搬到
  `Results/服务器结果/_pre_rebuild_2026-04-17/` 归档
- 只动松山湖相关子目录（exp2 / exp3a / exp3b / exp4），不碰德国 exp1

最常用命令：

```powershell
# 试跑（只打印不动文件）
pwsh -NoProfile -File scripts\archive_pre_rebuild_results.ps1 -DryRun

# 真归档
pwsh -NoProfile -File scripts\archive_pre_rebuild_results.ps1
```

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

- 被 `scripts/post_analysis_report.py` 中的 `run_post_analysis` 调用（方案选择 + 调度缓存 + 指标统计）
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

- 按 `docs/辩论确认/latest_松山湖数据与模型口径辩论共识.md` 的口径合成松山湖 8760h 负荷/气象
- 输出 `data/songshan_lake_data.csv` + `data/songshan_lake_typical.xlsx`（14 典型日）
- 内嵌 sanity check 打印年度总量、峰值、冷电比等关键指标
- **首次 clone 仓库或换机器必须跑一次**，否则拿到的是旧口径数据

关键口径（2026-04-17 重建版）：

- `ele_load` 只含非空调电（69.59 万 kWh/年），空调耗电由优化模型内生决定
- `cool_load` 月度对齐表 2（291.14 万 kW·h/年），峰值 clip 到 3460 kW
- `heat_load` 基于办公园区生活热水假设合成（35.9 万 kWh/年）
- 气象为合成数据，非 TMY 实测

常用命令：

```bash
# 默认：按共识重新合成 + 聚类
uv run python scripts/generate_songshan_data.py

# 将来有实测 8760h CSV：
uv run python scripts/generate_songshan_data.py --source measured --measured-csv <file>

# 只重聚类，不改 CSV：
uv run python scripts/generate_songshan_data.py --skip-generation

# 只合成 CSV，不聚类：
uv run python scripts/generate_songshan_data.py --skip-clustering
```

### `check_songshan_data.py`

用途：

- 独立的松山湖数据口径校验工具（不依赖重生成）
- 四类检查：年度总量 / 月度对齐 / 峰值与延时 / 日内形状
- 通过标准：**11 OK / 0 WARN**
- 带退出码：`--strict` 模式下任一 WARN 即 `exit 1`，便于接 CI / pre-commit

常用命令：

```bash
uv run python scripts/check_songshan_data.py                     # 打印报告，WARN 不中止
uv run python scripts/check_songshan_data.py --strict            # CI 模式
uv run python scripts/check_songshan_data.py --csv <other.csv>   # 校验任意 CSV
```

注：校验输出中的 "冷负荷延时 @ 1811h" 是 **INFO 参考值**，不计入 WARN。
原因见 `docs/辩论确认/latest_松山湖数据与模型口径辩论共识.md` §10.4：PDF 图 5 的
1811h=1269 kW 标注点与表 2 年总 291 万 kW·h 数学不相容。

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

- **服务器冷启动，一次性跑完所有正式实验**：用 `openbayes_run_experiments.sh`（首选）
- 配服务器环境（只装依赖）：用 `openbayes_setup.sh` / `rebuild_openbayes_env.sh`
- 跑单组实验：用 `run.py --exp N`
- 单组实验后自动接 Phase2：`run.py --exp N --post-analysis-mode medium`
- 对已有结果目录补跑 Phase2（自动推断 case/methods）：`scripts/run_existing_post_analysis.py <dir> --mode full`
- 做参数敏感性分析（本轮可跳过，已有历史报告）：用 `run_parameter_sensitivity.py`
- 只验证 exp4（松山湖+Carnot）稳定性：用 `run_exp4_sensitivity.py`
- 只比较已完成结果：用 `compare_parameter_scales.py`
- 画论文图：用 `enhanced_analysis.py` / `redraw_carnot_figures.py`
- 做后验分析：用 `post_analysis.py` 或 `run_existing_post_analysis.py`
- 重建松山湖数据：用 `generate_songshan_data.py`（**新仓库/新机器必做**）
- 独立校验松山湖数据口径：用 `check_songshan_data.py`
- 归档松山湖重建前的旧结果（Windows）：用 `archive_pre_rebuild_results.ps1`

## 7. 协作建议

给 AI 助手或新成员的最低建议是：

1. 先读本文件
2. 再看仓库根目录的 `OPENBAYES.md`
3. 明确自己要做的是"配环境 / 跑实验 / 做分析 / 画图"中的哪一种

服务器上的最短上手路径：

```bash
cd /openbayes/home/new_ies_optimization
git pull
bash scripts/openbayes_run_experiments.sh
```

这一条就覆盖了"配环境 + 重建数据 + 数据校验 + 四组实验 + Phase2 后验"。
