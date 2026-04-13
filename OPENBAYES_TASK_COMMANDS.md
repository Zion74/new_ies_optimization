# OpenBayes Task 启动命令手册

这份文档专门给 OpenBayes 的“提交任务 / 脚本执行模式”使用。

适用前提：

- 你已经把代码精简到一个任务目录，例如 `/openbayes/home/ies_task_min`
- 任务目录中已经包含通用启动脚本 `run_openbayes_task.sh`
- 你准备在 Task 页面里填写“启动命令”

推荐资源：

- `cpu-xxlarge` = 60 核 CPU / 100 GB 内存
- 首次建议 `--workers 36`
- 稳定后可尝试 `--workers 44`
- 不建议一上来直接 `--workers 60`

## 1. 通用启动脚本

建议把下面这个脚本放在任务目录根部：

路径：

```bash
/openbayes/home/ies_task_min/run_openbayes_task.sh
```

内容：

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

cd /openbayes/home/ies_task_min
export IES_RUNTIME_ENV=cloud

bash scripts/openbayes_setup.sh

uv run python "$@"
```

这样后面的 Task 启动命令都统一写成：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh <python_script> <args...>
```

## 2. 基础检查命令

环境检查：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --check
```

只做 pipeline 快速自检：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --test --case german --workers 36
```

## 3. run.py 模式命令

### 3.1 通用模式 `--mode`

测试模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode test --workers 36
```

快速模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode quick --workers 36
```

正式模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode full --workers 48
```

自定义模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode custom --nind 40 --maxgen 80 --methods std euclidean --workers 36
```

### 3.2 论文实验 `--exp`

实验 1 测试参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --test-run --workers 36
```

实验 1 快速参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --quick-run --workers 36
```

实验 1 正式参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --workers 36
```

实验 2 测试参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 2 --test-run --workers 36
```

实验 2 正式参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 2 --workers 36
```

实验 3 测试参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 3 --test-run --workers 36
```

实验 3 正式参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 3 --workers 36
```

实验 4 测试参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 4 --test-run --workers 36
```

实验 4 正式参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 4 --workers 36
```

全部四组实验测试参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp all --test-run --workers 36
```

全部四组实验快速参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp all --quick-run --workers 36
```

全部四组实验正式参数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp all --workers 36
```

## 4. run.py 常用附加参数

德国案例：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode quick --case german --workers 36
```

松山湖案例：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode quick --case songshan_lake --workers 36
```

启用卡诺电池：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode quick --case songshan_lake --carnot --workers 36
```

欧氏匹配度使用单位能质系数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --mode custom --methods euclidean --unit-lambda --nind 20 --maxgen 20 --workers 36
```

关闭种群继承：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --no-inherit --workers 36
```

跳过运行前检查：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --skip-check --workers 36
```

## 5. run_pipeline.py 模式命令

### 5.1 一键流水线

测试模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --test --case german --workers 36
```

快速模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --quick --case german --workers 36
```

中等模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --medium --case german --workers 36
```

正式模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --full --case german --workers 36
```

松山湖案例正式模式：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --full --case songshan_lake --workers 36
```

### 5.2 只做后验分析

对已有结果做快速后验分析：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --skip-optimize --result-dir Results/your_result_dir --quick
```

对已有结果做正式后验分析：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --skip-optimize --result-dir Results/your_result_dir --full
```

指定成本水平数：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run_pipeline.py --full --case german --workers 36 --cost-levels 5
```

## 6. 推荐执行顺序

第一次上 Task：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --check
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --test-run --workers 36
```

确认无误后：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp 1 --workers 36
```

最后再考虑：

```bash
bash /openbayes/home/ies_task_min/run_openbayes_task.sh run.py --exp all --workers 36
```

## 7. 如果要提高并行度

`cpu-xxlarge` 为 60 核，建议按下面顺序逐步提高：

- 保守：`--workers 36`
- 中等：`--workers 44`
- 激进：`--workers 48`

除非你已经验证过内存、日志和求解器都稳定，否则不建议直接用 `--workers 60`。
