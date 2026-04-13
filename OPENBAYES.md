# OpenBayes 运行手册

这份手册面向本仓库在 OpenBayes 上的运行与结果回传，目标是把第一次上云调试、后续提交任务、结果下载这三件事固定成同一套流程。

## 1. 先给结论

- 这套 IES 优化更像 `CPU + 求解器` 任务，不是 GPU 训练任务。
- 第一次上云建议先开 `工作空间` 调试，确认环境和求解器可用后，再切到 `提交任务` 跑 full 实验。
- 现阶段数据文件非常小，直接跟随仓库一起上传或 `git clone` 就够了，不需要额外做复杂的数据绑定。
- 结果目录默认会写到仓库下的 `Results/`，在 OpenBayes 上建议把仓库放到 `/openbayes/home/ies_optimization`。

当前仓库内置数据文件规模：

- `data/mergedData.csv`：约 0.46 MB
- `data/songshan_lake_data.csv`：约 0.93 MB
- `data/typicalDayData.xlsx` / `data/songshan_lake_typical.xlsx`：约 6 KB

## 2. 容器怎么选

### 镜像

优先选：

- `ubuntu 22.04-cpu`

不建议选 MATLAB、RStudio、VASP、OpenFOAM、Gromacs 之类的专业镜像，因为本项目核心依赖是 Python + `uv` + `pyomo/oemof/geatpy`。

### 接入方式

建议按阶段区分：

- 第一次调试：`工作空间`
- 跑正式长任务：`提交任务`

原因很简单：

- 工作空间适合交互式检查环境、看文件、试跑 `--check` 和 `--test-run`
- 提交任务更适合正式实验，不依赖你一直保持网页打开

### 资源规格

建议先保守一点：

- 调试：8 到 16 核 CPU
- 正式实验：16 到 32 核 CPU 起步，再根据 `--workers` 扩大

不要一开始就默认上 120 核，除非你已经确认：

- 代码能稳定跑通
- `--workers` 已经调高
- 求解器不会成为新的瓶颈

## 3. Jupyter 还是 SSH

如果是第一次进入 OpenBayes 工作空间，我建议：

- 优先用 `Jupyter`
- 在 Jupyter 里打开一个 Terminal，执行环境配置脚本

原因：

- 更容易确认当前目录是不是 `/openbayes/home`
- 更容易直接看文件、上传压缩包、检查 `Results/`
- 第一次调试时，图形化文件浏览比纯命令行省心

如果你已经很熟悉命令行，或者后面要做这些事情，则更适合用 `SSH`：

- 长时间 `tail -f` 日志
- 复制大段命令
- 从本地终端或编辑器远程操作

一句话建议：

- `第一次配置 -> Jupyter`
- `后续长时间跑命令 / 看日志 -> SSH`

## 4. 工作目录与数据目录

OpenBayes 常见目录可以这样理解：

- `/openbayes/home`：工作目录，适合放仓库代码和结果
- `/openbayes/input/input0` 到 `/openbayes/input/input4`：绑定数据目录，适合只读输入
- `/output`：等价于 `/openbayes/home`
- `/input0` 到 `/input4`：分别等价于 `/openbayes/input/input0` 到 `/openbayes/input/input4`

如果你是从 Jupyter 文件浏览器进入的，还可以再记一层：

- Jupyter 里看到的 `/home`，实际对应容器里的 `/openbayes/home`

对本仓库，推荐：

- 仓库代码放在 `/openbayes/home/ies_optimization`
- 结果也保存在这个目录下的 `Results/`

因为当前数据很小，所以前期可以不绑定任何数据集，直接把仓库放进工作目录。

## 5. 第一次进入工作空间后的标准流程

### 5.1 准备代码

如果你走 GitHub：

```bash
cd /openbayes/home
git clone <your_repo_url> ies_optimization
cd ies_optimization
```

如果你是本地上传 zip：

```bash
cd /openbayes/home
unzip ies_optimization.zip
cd ies_optimization
```

### 5.2 一键配置环境

仓库已经补了一个脚本：

- `scripts/openbayes_setup.sh`

进入仓库后直接运行：

```bash
bash scripts/openbayes_setup.sh
```

脚本会自动做这些事：

1. 检查并安装 `uv`
2. 按 `.python-version` 安装 Python 3.8
3. 根据 `uv.lock` / `pyproject.toml` 同步依赖
4. 如果容器允许且缺少 `glpsol`，尝试安装 `glpk-utils`
5. 检查 `gurobi_direct` / `highs` / `glpk` 的可见性
6. 执行 `uv run python run.py --check`

如果你只想装环境，不想在最后跑检查：

```bash
IES_SKIP_RUN_CHECK=1 bash scripts/openbayes_setup.sh
```

如果你不希望脚本尝试安装 GLPK 系统包：

```bash
IES_SKIP_GLPK_INSTALL=1 bash scripts/openbayes_setup.sh
```

## 6. 建议的验证顺序

不要一上来就跑 full，建议按下面顺序：

```bash
uv run python run.py --check
uv run python run.py --exp 1 --test-run --workers 4
uv run python run.py --exp 1 --workers 8
```

如果 `--exp 1 --test-run` 没问题，再扩大到：

```bash
uv run python run.py --exp all --workers 8
```

或者根据你当时拿到的 CPU 资源调大 `--workers`。

## 7. 后续切换到“提交任务”时怎么复用

当你已经在工作空间调通后，后续提交任务时只需要把同一套流程放进任务命令里：

```bash
cd /openbayes/home
git clone <your_repo_url> ies_optimization
cd ies_optimization
bash scripts/openbayes_setup.sh
uv run python run.py --exp 1 --workers 16
```

如果你改为 OpenBayes CLI 提交任务，建议先用 CLI 查看镜像对应的环境标识，再填到命令里：

```bash
bayes gear env
```

任务命令模板可以写成：

```bash
bayes gear run task \
  --resource cpu-xxlarge \
  --env <ubuntu_22_04_cpu_env_id> \
  --message "ies-exp1-full" \
  -- "bash -lc 'set -e; cd /openbayes/home; if [ ! -d ies_optimization ]; then git clone <your_repo_url> ies_optimization; fi; cd ies_optimization; bash scripts/openbayes_setup.sh; uv run python run.py --exp 1 --workers 16'"
```

上面有两个地方需要你替换：

- `<ubuntu_22_04_cpu_env_id>`
- `<your_repo_url>`

## 8. 数据怎么上传

### 当前推荐

因为数据很小，先不要折腾数据绑定，最简单的方式是：

- 直接把整个仓库 `git clone` 到 `/openbayes/home`
- 或者本地打包后上传到工作目录再解压

### 什么情况下才需要绑定数据集

只有在这些情况下再考虑 `/openbayes/input/input0`：

- 输入文件非常大
- 需要被多个任务复用
- 不希望每次任务都重新上传

## 9. 结果怎么传回本地

默认结果目录形如：

```text
/openbayes/home/ies_optimization/Results/CCHP_<case>_<timestamp>/
```

最简单的回传方式有两种：

### 方式 A：网页下载

- 在 OpenBayes 文件浏览器中定位到 `Results/`
- 下载整个结果目录或单个文件

### 方式 B：CLI 下载

```bash
bayes gear download <task_id> --target ./openbayes_results -u
```

如果只想下载某个结果子目录：

```bash
bayes gear download <task_id> \
  --from ies_optimization/Results/<result_folder> \
  --target ./openbayes_results \
  -u
```

## 10. 结果目录建议保留什么

正式实验至少保留：

- `Results/.../comparison_report.md`
- `Results/.../Pareto_Comparison.png`
- 各方法目录下的 `ObjV_*.csv`
- 各方法目录下的 `Phen_*.csv`
- 各方法目录下的 `Pareto_*.csv`

如果后面要把结果作为论文支撑材料统一归档，也建议保留你运行时的命令记录，例如：

```text
exp1_workers16_2026-04-13.txt
```

内容记录：

- 镜像
- CPU 规格
- `--workers`
- 运行命令
- 是否为 `--test-run`

## 11. 常见问题

### Q1：工作空间里能直接跑 full 吗？

可以，但不推荐长期依赖工作空间跑正式实验。第一次更适合用工作空间调通，正式跑建议切换到提交任务。

### Q2：要不要 GPU？

不用优先考虑 GPU。这套实验主要是 CPU、多进程和求解器负载。

### Q3：如果任务里不方便调试怎么办？

所以第一次一定要先在工作空间里把下面三件事跑通：

```bash
bash scripts/openbayes_setup.sh
uv run python run.py --check
uv run python run.py --exp 1 --test-run --workers 4
```

确认这三步都稳定后，再把同样命令迁移到提交任务。

### Q4：如果求解器检查失败怎么办？

先看 `scripts/openbayes_setup.sh` 打印出的求解器可见性：

- `gurobi_direct`
- `highs`
- `glpk`

只要至少有一个可用，`run.py --check` 理论上就能继续走下去。

如果 `glpk` 缺失而你又想保留开源兜底，可在容器里手动执行：

```bash
apt-get update -y
apt-get install -y --no-install-recommends glpk-utils
```

## 12. 当前推荐的最短路径

第一次上 OpenBayes 时，直接照这个做：

```bash
cd /openbayes/home
git clone <your_repo_url> ies_optimization
cd ies_optimization
bash scripts/openbayes_setup.sh
uv run python run.py --exp 1 --test-run --workers 4
```

如果这一步通过，再考虑更大的 CPU 规格和正式 full 实验。
