# OpenBayes 与服务器运行手册

这份文档是本仓库在 OpenBayes / Linux 服务器上的统一运行说明。

它现在合并了原来的：

- `OPENBAYES.md`
- `OPENBAYES_TASK_COMMANDS.md`

以后优先维护这一份，不再在仓库根目录保留两份并行操作手册。

## 1. 先给结论

- 这个项目本质上是 `CPU + 求解器` 任务，不是 GPU 训练任务。
- 如果只是跑优化，优先看 CPU 核数、内存和求解器可用性，不要把 GPU 当成主要加速手段。
- 当前最稳的流程是：
  1. 在 OpenBayes 交互空间里把环境调通
  2. 运行 `run.py --check`
  3. 再跑 `run.py --exp ...` 或敏感性分析脚本

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

### 3.3 赋予脚本权限并配置环境

```bash
chmod +x scripts/openbayes_setup.sh scripts/rebuild_openbayes_env.sh
bash scripts/openbayes_setup.sh
```

如果环境损坏或需要强制重建：

```bash
bash scripts/rebuild_openbayes_env.sh
```

### 3.4 做一次自检

```bash
uv run python run.py --check
```

## 4. 交互空间里最常用的运行命令

### 4.1 论文预设实验

实验 1 测试参数：

```bash
uv run python run.py --exp 1 --test-run --workers 4
```

实验 1 正式参数：

```bash
uv run python run.py --exp 1 --workers 28
```

全部四组实验正式参数：

```bash
uv run python run.py --exp all --workers 28
```

### 4.2 pipeline 一键流程

德国案例正式模式：

```bash
uv run python run_pipeline.py --full --case german --workers 28
```

松山湖案例正式模式：

```bash
uv run python run_pipeline.py --full --case songshan_lake --workers 28
```

### 4.3 参数敏感性分析

通用敏感性分析：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

只查看将执行的命令：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28 --dry-run
```

自定义参数组：

```bash
uv run python scripts/run_parameter_sensitivity.py --workers 28 --scales 50x100 80x150 100x200
```

### 4.4 只做 exp4 敏感性分析

```bash
uv run python scripts/run_exp4_sensitivity.py --workers 28
```

这条命令默认等价于：

- `case = songshan_lake`
- `carnot = on`
- `methods = std euclidean`
- 参数组默认比较 `50x100 / 80x150 / 100x200`

### 4.5 比较已有结果目录

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
- `n50` 表示 `nind=50`
- `g100` 表示 `maxgen=100`
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

```bash
cd /openbayes/home/new_ies_optimization
export IES_RUNTIME_ENV=cloud
uv run python run.py --exp all --workers 28
```

### 8.2 跑参数敏感性分析

```bash
cd /openbayes/home/new_ies_optimization
export IES_RUNTIME_ENV=cloud
uv run python scripts/run_parameter_sensitivity.py --workers 28
```

或者：

```bash
uv run python scripts/run_exp4_sensitivity.py --workers 28
```

### 8.3 对已有结果做分析

```bash
cd /openbayes/home/new_ies_optimization
uv run python scripts/compare_parameter_scales.py \
  Results/<结果目录1> \
  Results/<结果目录2> \
  Results/<结果目录3>
```

如果是 pipeline 后验分析：

```bash
uv run python run_pipeline.py --skip-optimize --result-dir Results/<已有目录> --full
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

### Q5：`nind=50, maxgen=100` 会不会太少

对这个问题最稳的做法不是猜，而是补参数敏感性分析。推荐直接跑：

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
