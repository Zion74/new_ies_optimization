# OpenBayes 与服务器运行手册

这份文档是本仓库在 OpenBayes / Linux 服务器上的统一运行说明。

它现在合并了原来的：

- `OPENBAYES.md`
- `OPENBAYES_TASK_COMMANDS.md`

以后优先维护这一份，不再在仓库根目录保留两份并行操作手册。

## 1. 先给结论

- 这个项目本质上是 `CPU + 求解器` 任务，不是 GPU 训练任务。
- 如果只是跑优化，优先看 CPU 核数、内存和求解器可用性，不要把 GPU 当成主要加速手段。
- **2026-04-17 之后推荐的最省事流程**（松山湖数据口径已重建、实验编号已重排）：
  1. `git clone` / `git pull` 拿到最新代码
  2. 直接跑 `bash scripts/openbayes_run_experiments.sh`——它内部串起"环境准备 → 松山湖数据重生 → sanity check → 四组实验 → Phase2 后验"
  3. 日志会落在 `logs/post_rebuild_<ts>/`，结果落在 `Results/CCHP_*`
- 如果需要更细粒度的手工控制，再按第 3-4 节分步走。

## 2. 仓库在服务器上的推荐落点

推荐把仓库放在：

```bash
/openbayes/home/new_ies_optimization
```

说明：

- `/openbayes/home` 等价于 `/output`
- 在 Jupyter 文件浏览器中你通常会看到 `/home`，它实际对应容器中的 `/openbayes/home`

## 3. 第一次进入新服务器后的标准步骤

### 3.1 获取代码

如果 GitHub 可以正常拉取：

```bash
cd /openbayes/home
git clone https://github.com/Zion74/new_ies_optimization.git
cd new_ies_optimization
```

如果 `git clone` 网络不稳，可以先尝试浅克隆：

```bash
cd /openbayes/home
rm -rf new_ies_optimization
git clone --depth 1 https://github.com/Zion74/new_ies_optimization.git
cd new_ies_optimization
```

如果 GitHub 拉取始终失败，就改用本地打包上传 zip 再解压。

### 3.2 设置运行环境标识

```bash
export IES_RUNTIME_ENV=cloud
```

### 3.3 赋予脚本权限

```bash
chmod +x scripts/openbayes_setup.sh scripts/rebuild_openbayes_env.sh scripts/openbayes_run_experiments.sh
```

### 3.4 **一键完成 setup + 数据重建 + 四组实验**（推荐）

```bash
bash scripts/openbayes_run_experiments.sh
```

这条命令依次做：

1. 跑 `scripts/openbayes_setup.sh`（装 uv / Python / 依赖 / glpk）
2. 跑 `uv run python scripts/generate_songshan_data.py`（按 2026-04-17 重建版合成松山湖 8760h 数据）
3. 跑 `uv run python scripts/check_songshan_data.py`（独立口径校验，11 OK / 0 WARN 为正常）
4. 顺序跑 `uv run python run.py --exp 1/2/3/4`
5. 每组实验后接 Phase2 后验（`--post-analysis-mode medium`）
6. 全部日志落到 `logs/post_rebuild_<timestamp>/`，内含 `SUMMARY.md`

**常用环境变量**（全部可选）：

```bash
# 烟测：10 分钟级全链路跑一遍
IES_TEST_RUN=1 bash scripts/openbayes_run_experiments.sh

# 只跑其中几组
IES_EXP="1 2" bash scripts/openbayes_run_experiments.sh

# 环境已好、数据已生成，只想重跑实验
IES_SKIP_SETUP=1 IES_SKIP_DATA_REGEN=1 IES_SKIP_SANITY=1 \
  bash scripts/openbayes_run_experiments.sh

# 改并行数
IES_WORKERS=28 bash scripts/openbayes_run_experiments.sh

# sanity WARN 即阻止（用于 CI）
IES_STRICT_SANITY=1 bash scripts/openbayes_run_experiments.sh
```

### 3.5 手动分步（排障时用）

环境准备：

```bash
bash scripts/openbayes_setup.sh
# 或强制重建：bash scripts/rebuild_openbayes_env.sh
```

松山湖数据重生 + 校验（**首次拉代码后必须做一次**，否则 `data/songshan_lake_data.csv` 和 `data/songshan_lake_typical.xlsx` 是旧口径）：

```bash
uv run python scripts/generate_songshan_data.py
uv run python scripts/check_songshan_data.py
```

自检：

```bash
uv run python run.py --check
```

## 4. 交互空间里最常用的运行命令

### 4.1 论文四组实验（2026-04-17 重排后含义）

| 编号 | 案例 | 卡诺电池 | 方法 | 作用 |
|---|---|---|---|---|
| `--exp 1` | 德国 | 无 | 5 方法全跑 | 创新点 1：EQD vs std/pearson/ssr/economic 对比 |
| `--exp 2` | 德国 | **both**（先无 → 再有） | std + euclidean | 创新点 2 核心证据：卡诺电池有/无对比 |
| `--exp 3` | 松山湖 | 无 | std + euclidean | 普适性验证 |
| `--exp 4` | 松山湖 | 有 | std + euclidean | 普适性延伸 + 串联两创新点 |
| `--exp all` | — | — | — | 顺序跑 1/2/3/4 |

注：**旧 exp2 / exp3（松山湖 × 5 方法 / 松山湖 Carnot 有无）已下线**，旧结果已归档到
`Results/服务器结果/_pre_rebuild_2026-04-17/`，不再引用。

实验 1 烟测：

```bash
uv run python run.py --exp 1 --test-run --workers 4
```

单组实验正式参数：

```bash
uv run python run.py --exp 2 --workers 28
```

全部四组 + Phase2 后验（最常见的正式跑法）：

```bash
uv run python run.py --exp all --workers 28 --post-analysis-mode medium
```

### 4.2 参数敏感性分析（本轮可跳过，但正式参数已调升）

2026-04-14 敏感性实验结论（数据源
`Results/服务器结果/第二次实验/parameter_scale_comparison_fixed.md`）：

| 方法 | 50→100 成本波动 | 匹配度波动 | 稳定性判断 |
|---|---|---|---|
| `economic_only` / `pearson` / `std` | <1.9% | <0.4% | 稳定 |
| **`euclidean`**（EQD 核心创新） | **2.13%** | 0.33% | **中度波动，建议补充复现** |
| **`ssr`** | 1.55% | **76.22%** | **波动大，建议增大参数** |

80/150 → 100/200 的边际收益：`euclidean` -0.80%、`ssr` 匹配度 -0.93%、`std` -0.73%，
**80/150 是收敛拐点**，继续往上性价比很低。

**结论**：

- **正式参数已从 `50/100` 调升到 `80/150`**（`run.py` `PRESETS['full']` + `_run_experiments` 默认）
- 全部四组实验 + Phase2 后验的耗时从 ~4h20m 增加到 ~5h40m，`euclidean` / `ssr` 从 "中度 / 严重波动" 变为 "收敛"
- 相关共识见 `docs/辩论确认/2026-04-16_Codex对Claude_Phase2回应.md` §4

本轮松山湖数据重建只改输入层，不影响算法收敛特性，**不需要再跑一次敏感性分析**，
沿用 `80/150` 即可。论文里简单一句"参数 80×150 已满足收敛"并引用报告。

若确需重跑（如改 GA 算子、增加决策变量）：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

### 4.3 比较已有结果目录

```bash
uv run python scripts/compare_parameter_scales.py \
  Results/<结果目录1> \
  Results/<结果目录2> \
  Results/<结果目录3>
```

## 5. 长时间运行建议

### 5.1 前台运行

适合：

- 想实时盯日志
- 还在排错

例子：

```bash
uv run python run.py --exp all --workers 28 2>&1 | tee exp_all_full_w28.log
```

### 5.2 后台运行

适合：

- 长时间正式实验
- 不想一直开着终端

例子：

```bash
nohup uv run python run.py --exp all --workers 28 > exp_all_full_w28.log 2>&1 &
```

查看日志：

```bash
tail -f exp_all_full_w28.log
```

## 6. 新版批量实验结果里会多出什么

新版 `run.py` 已支持批量实验计时汇总。

例如运行：

```bash
uv run python run.py --exp all --workers 28
```

批量根目录中会自动生成：

```text
batch_timing_summary.md
```

其中包含：

- 每个子实验开始时间
- 每个子实验结束时间
- 每个子实验总耗时
- 每个方法的耗时
- 每个方法的最低成本、最佳匹配度、Pareto 解数

## 7. 结果目录命名规则

新版目录命名更强调“可读性”。

批量实验父目录示例：

```text
paper-batch__exp-all__full__n50__g100__w28__20260414_062000
```

其中：

- `exp-all` 表示论文四组实验全跑
- `full` 表示正式参数
- `n80` 表示 `nind=80`（2026-04-17 之前的结果目录会出现 `n50`，属于旧正式参数）
- `g150` 表示 `maxgen=150`
- `w28` 表示 `workers=28`

子实验目录示例：

```text
exp4__songshan_lake__carnot__std+euclidean__n50__g100__20260414_073933
```

这样可以直接看出：

- 是哪个实验
- 是哪个案例
- 是否启用卡诺电池
- 运行了哪些方法
- 参数规模是多少

## 8. 服务器上如何继续后续工作

当你已经在服务器上跑出结果后，后续通常有三类操作。

### 8.1 继续跑新的实验

最推荐（一键）：

```bash
cd /openbayes/home/new_ies_optimization
git pull
export IES_RUNTIME_ENV=cloud
bash scripts/openbayes_run_experiments.sh
```

手动模式（已经在 3.4 一键流程里跑过、只想重跑部分实验）：

```bash
cd /openbayes/home/new_ies_optimization
export IES_RUNTIME_ENV=cloud
uv run python run.py --exp all --workers 28 --post-analysis-mode medium
```

### 8.2 跑参数敏感性分析（本轮不需要）

如前述 4.3 节所说，本轮数据口径重建不影响收敛特性，沿用前版结论即可。
如果确实要重跑：

```bash
cd /openbayes/home/new_ies_optimization
export IES_RUNTIME_ENV=cloud
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

（`scripts/run_exp4_sensitivity.py` 是旧实验编号残留，对应"松山湖+Carnot × std+euclidean"
即新 exp4，仍可直接用。）

### 8.3 对已有结果做分析

```bash
cd /openbayes/home/new_ies_optimization
uv run python scripts/compare_parameter_scales.py \
  Results/<结果目录1> \
  Results/<结果目录2> \
  Results/<结果目录3>
```

对已有结果目录补跑 Phase2 后验分析（自动推断 case 和 methods）：

```bash
uv run python scripts/run_existing_post_analysis.py Results/<已有目录> --mode full
```

## 9. Task 模式说明

本项目曾尝试通过 `bayes gear run task` 直接从工作空间派生 task，但在部分组织/镜像组合下会遇到“镜像类型不一致”的平台限制。

因此当前更推荐两条路：

1. 直接在交互空间里跑正式实验
2. 单独新建脚本执行型 task，再上传代码包和启动脚本

如果后续平台环境更稳定，再恢复 CLI 直接派发 task 的工作流。

## 10. 服务器常见问题

### Q1：`run.py --check` 通过，但日志里出现 `Glyph missing from current font`

这是 matplotlib 中文字体警告，不影响优化结果，只影响图片里的中文显示。

如果需要服务器端直接生成可用中文图，可以安装字体：

```bash
apt-get update -y
apt-get install -y fonts-noto-cjk
fc-cache -fv
```

### Q2：为什么 `git clone` 失败后后续命令都找不到目录

因为仓库没有真正拉下来，后面的 `cd new_ies_optimization` 自然会失败。先重新 clone 成功，再继续。

### Q3：为什么 `rebuild_openbayes_env.sh` 报 `Permission denied`

通常是脚本执行位丢了。先执行：

```bash
chmod +x scripts/openbayes_setup.sh scripts/rebuild_openbayes_env.sh
```

### Q4：为什么这次实验比上次快很多

先看 `batch_timing_summary.md` 里的 `status` 是否全部为 `success`，再看方法级耗时是否完整。如果都完整，往往说明这次确实更快，而不是漏跑。

### Q5：为什么正式参数是 80/150 而不是 50/100 或 100/200

2026-04-14 那轮在 `Results/服务器结果/第二次实验/` 跑了 `50×100 / 80×150 / 100×200` 三个规模。关键发现：

- `euclidean`（EQD 核心创新）在 50×100 下成本波动 2.1%，有 "换参数就换结论" 的风险
- `ssr` 在 50×100 下匹配度波动 76%，明显未收敛
- 80×150 → 100×200 的边际收益 <1%，耗时却翻倍

结论：**80×150 是性价比拐点**，已在 `docs/辩论确认/2026-04-16_Codex对Claude_Phase2回应.md` 共识 4 中定形，
并于 2026-04-17 写进 `run.py` 默认值。

若以后结构有变动（改 GA 算子 / 新增决策变量）再跑一次：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

## 11. 结果回传

结果默认写在：

```text
/openbayes/home/new_ies_optimization/Results/
```

最简单的方式：

- 在 OpenBayes 文件浏览器里直接下载结果目录

如果你用 CLI：

```bash
bayes gear download <task_id> --target ./openbayes_results -u
```

## 12. 和 scripts/README.md 的关系

- `OPENBAYES.md`：告诉你“服务器上怎么做”
- `scripts/README.md`：告诉你“scripts 里的脚本分别干什么”

如果你只想赶紧把实验跑起来，先看本文件。
如果你想知道某个分析脚本是否该用，再去看 `scripts/README.md`。
