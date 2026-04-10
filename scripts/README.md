# 结果分析脚本使用指南

本目录包含一套完整的结果分析与可视化脚本，用于生成论文级图表和统计分析。

## 脚本概览

### 1. 核心分析脚本

#### `post_analysis.py` - 后验运行指标分析
**功能**：从 Pareto 前沿选取方案，跑 8760h 调度，计算实际运行指标
**用法**：
```bash
python scripts/post_analysis.py --result-dir Results/pipeline_xxx --methods std euclidean
```
**输出**：
- `post_analysis_results.csv` - 运行指标数据
- 峰值购电、年购电量、自给自足率、电网波动等指标

**已集成到 `run_pipeline.py`**，无需单独运行。

---

#### `enhanced_analysis.py` - 增强版论文级可视化 ⭐
**功能**：生成论文核心图表和 LaTeX 表格
**用法**：
```bash
# 基础分析
python scripts/enhanced_analysis.py --result-dir Results/pipeline_xxx

# 生成 LaTeX 表格
python scripts/enhanced_analysis.py --result-dir Results/pipeline_xxx --latex

# 指定分析方法
python scripts/enhanced_analysis.py --result-dir Results/pipeline_xxx --methods Std Euclidean Pearson
```

**输出图表**：
1. **预算增量对比图** - 展示"低预算差距小、高预算差距大"的核心论点
2. **Pareto 前沿宽度对比** - 证明 Std 方法搜索空间受限
3. **设备配置演化趋势** - 展示优化器如何调整设备配置
4. **LaTeX 表格** - 直接用于论文的表格代码

**论文用途**：核心对比图表，必跑！

---

#### `resilience_test.py` - 极端场景韧性测试 ⭐
**功能**：测试系统在极端场景下的韧性
**用法**：
```bash
# 全部场景
python scripts/resilience_test.py --result-dir Results/pipeline_xxx

# 指定场景
python scripts/resilience_test.py --result-dir Results/pipeline_xxx --scenarios grid_failure gas_surge
```

**测试场景**：
- `grid_failure` - 电网故障（电价×3）
- `gas_surge` - 气价飙升（气价×2）
- `renewable_drop` - 极端天气（可再生能源-50%）
- `load_surge` - 负荷激增（负荷+30%）

**输出**：
- 成本增长率对比图
- 调度成功率对比图
- 韧性测试报告

**论文用途**：证明"匹配度高的系统在极端场景下韧性更强"

---

#### `lambda_sensitivity.py` - 能质系数敏感性分析（消融实验） ⭐
**功能**：对比不同能质系数配置的优化结果
**用法**：
```bash
# 快速测试
python scripts/lambda_sensitivity.py --case german --mode quick

# 正式实验
python scripts/lambda_sensitivity.py --case german --mode full
```

**实验配置**：
- `no_quality` - 无能质区分（λ=[1,1,1]）
- `carnot` - 纯卡诺㶲系数（λ=[1.0, 0.131, 0.064]）
- `empirical` - 经验值（λ=[1.0, 0.6, 0.5]）

**输出**：
- Pareto 前沿对比图
- 设备配置对比图
- 敏感性分析报告

**论文用途**：证明能质系数的必要性和合理性

---

### 2. 单方法深度分析

#### `cchp_result_analysis.py` - 单方法详细分析
**功能**：对单个方法进行深度分析
**用法**：
```bash
python 结果分析与展示脚本/cchp_result_analysis.py
```
（自动查找最新结果目录）

**输出**：
- 图4-10：25个规划方案容量配置柱状图
- 图4-11~4-13：系统#1与#25的调度对比图
- 图4-14：年化投资和维护成本
- 图4-15~4-17：负荷增长敏感性分析

**论文用途**：单方法详细展示，可选

---

#### `method_comparison.py` - 多方法对比分析
**功能**：对比 Std 和 Euclidean 两种方法
**用法**：
```bash
python 结果分析与展示脚本/method_comparison.py
```

**输出**：
- Pareto 前沿对比图（原始+归一化）
- 极端解对比（最优经济 vs 最优匹配）
- 典型日调度对比
- 超体积、Spread、覆盖率等量化指标
- KPI 综合指标（PER、㶲效率、SSR）

**论文用途**：方法对比详细分析

---

#### `operationRunable.py` - 单方案调度模拟
**功能**：对单个方案运行完整调度模拟
**用法**：
```bash
python 结果分析与展示脚本/operationRunable.py
```
（自动读取最新 Pareto_Front.csv）

**输出**：
- 调度结果日志
- 典型日调度图
- 净负荷标准差

**论文用途**：调试和验证用

---

## 推荐工作流

### 论文核心图表生成流程

```bash
# 1. 运行完整实验（德国案例）
uv run python run_pipeline.py --full --case german

# 等待完成（约2-4小时）...

# 2. 生成增强版分析图表（必做）
uv run python scripts/enhanced_analysis.py \
    --result-dir Results/pipeline_german_50x100_5methods_xxx \
    --latex

# 3. 极端场景韧性测试（必做）
uv run python scripts/resilience_test.py \
    --result-dir Results/pipeline_german_50x100_5methods_xxx

# 4. 能质系数敏感性分析（必做）
uv run python scripts/lambda_sensitivity.py \
    --case german --mode full

# 5. 松山湖案例验证（可选）
uv run python run_pipeline.py --full --case songshan_lake
uv run python scripts/enhanced_analysis.py \
    --result-dir Results/pipeline_songshan_lake_50x100_5methods_xxx
```

### 快速验证流程

```bash
# 1. 快速实验
uv run python run_pipeline.py --quick --case german

# 2. 快速分析
uv run python scripts/enhanced_analysis.py \
    --result-dir Results/pipeline_german_20x20_3methods_xxx
```

---

## 输出文件说明

### `enhanced_analysis/` 目录
```
enhanced_analysis/
├── Fig_Budget_Increment_Comparison.png      # 预算增量对比（4子图）
├── Fig_Pareto_Width_Comparison.png          # Pareto 前沿宽度对比
├── Fig_Capacity_Evolution_Euclidean.png     # 设备配置演化趋势
├── latex_tables.tex                          # LaTeX 表格代码
└── statistical_test.md                       # 统计显著性检验报告
```

### `resilience_test/` 目录
```
resilience_test/
├── Fig_Resilience_Cost_Comparison.png       # 极端场景成本对比
├── Fig_Resilience_Success_Rate.png          # 调度成功率对比
└── resilience_test_report.md                 # 韧性测试报告
```

### `lambda_sensitivity_xxx/` 目录
```
lambda_sensitivity_german_full_xxx/
├── no_quality/
│   └── Pareto_no_quality.csv
├── carnot/
│   └── Pareto_carnot.csv
├── empirical/
│   └── Pareto_empirical.csv
├── Fig_Lambda_Sensitivity_Pareto.png        # Pareto 前沿对比
├── Fig_Lambda_Sensitivity_Capacity.png      # 设备配置对比
└── lambda_sensitivity_report.md             # 敏感性分析报告
```

---

## 论文图表清单

### 必需图表（核心论点）

1. **预算增量对比图** (`enhanced_analysis`)
   - 展示 Euclidean 在高预算下优势爆发
   - 4个子图：峰值购电、年购电量、自给自足率、电网波动

2. **Pareto 前沿宽度对比** (`enhanced_analysis`)
   - 证明 Std 方法搜索空间受限
   - 柱状图，直观展示前沿宽度差异

3. **极端场景韧性对比** (`resilience_test`)
   - 证明匹配度高的系统韧性更强
   - 成本增长率 + 调度成功率

4. **能质系数敏感性分析** (`lambda_sensitivity`)
   - 证明能质系数的必要性
   - Pareto 前沿对比 + 设备配置对比

### 可选图表（补充说明）

5. **设备配置演化趋势** (`enhanced_analysis`)
   - 展示优化器如何调整配置
   - 9个子图，每个设备一个

6. **方法对比详细分析** (`method_comparison`)
   - 超体积、Spread、覆盖率
   - 典型日调度对比

---

## 常见问题

### Q1: 脚本运行失败怎么办？
**A**: 检查以下几点：
1. 确保 `result-dir` 路径正确
2. 确保结果目录包含 Pareto CSV 文件
3. 检查 Python 环境和依赖包

### Q2: 如何修改图表样式？
**A**: 编辑脚本中的 `plt.rcParams` 和颜色配置：
```python
plt.rcParams['font.size'] = 12
plt.rcParams['figure.dpi'] = 300
```

### Q3: 如何添加新的分析指标？
**A**: 在 `post_analysis.py` 的 `run_operation_simulation()` 中添加：
```python
# 计算新指标
new_metric = ...
metrics['new_metric'] = new_metric
```

### Q4: LaTeX 表格如何使用？
**A**:
1. 运行 `enhanced_analysis.py --latex`
2. 打开 `latex_tables.tex`
3. 复制代码到论文 `.tex` 文件
4. 确保导言区有 `\usepackage{booktabs, multirow}`

### Q5: 如何自定义测试场景？
**A**: 在 `resilience_test.py` 的 `scenario_configs` 中添加：
```python
'custom_scenario': {
    'name': '自定义场景',
    'params': {
        'ele_price_multiplier': 2.0,
        'load_multiplier': 1.2
    }
}
```

---

## 脚本依赖

所有脚本依赖项已在 `pyproject.toml` 中定义：
- pandas, numpy - 数据处理
- matplotlib - 绘图
- scipy - 统计分析
- tqdm - 进度条
- openpyxl - Excel 读取

安装：
```bash
uv sync
```

---

## 更新日志

### 2026-03-22
- 新增 `enhanced_analysis.py` - 论文级可视化
- 新增 `resilience_test.py` - 极端场景测试
- 新增 `lambda_sensitivity.py` - 能质系数敏感性分析
- 更新 `post_analysis.py` - 集成预算增量对齐模式

### 2026-03-19
- 初始版本
- `post_analysis.py` - 后验分析
- `cchp_result_analysis.py` - 单方法分析
- `method_comparison.py` - 方法对比

---

## 联系方式

如有问题或建议，请在项目 Issues 中提出。
