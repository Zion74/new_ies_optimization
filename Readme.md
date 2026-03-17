# IES 源荷匹配优化规划

基于能质系数的综合能源系统（IES）源荷匹配度量化方法与容量配置优化研究。

## 研究背景

综合能源系统中电、热、冷三种能源形式的"品质"不同（电能品质最高，热能次之，冷能最低），传统的源荷匹配度量化方法只看功率数值大小，忽略了能源品质差异。本研究引入热力学中的能质系数（基于卡诺因子），将不同形式的能源折算到统一标尺，提出"能质耦合欧氏距离"匹配度指标，用于指导IES容量配置优化。

## 两个创新点

1. **能质耦合欧氏距离匹配度**（方法创新）：用能质系数 λ_e=1.0, λ_h=0.6, λ_c=0.5 加权三维净负荷，计算欧氏距离作为源荷匹配度
2. **含卡诺电池的IES容量优化**（模型创新）：将卡诺电池（电→热储存→电）作为新型储能设备集成到优化框架中

## 优化框架

两层优化结构：
- **上层**：NSGA-II 遗传算法搜索设备容量组合（9~11个决策变量）
- **下层**：OEMOF-SOLPH 线性规划求解每个方案的最优运行调度
- **双目标**：最小化年化总成本 + 最小化源荷匹配度指标

5种匹配度量化方法对比：
- 方案A (economic_only)：单目标经济最优（基准）
- 方案B (std)：净负荷波动率（师兄方法）
- 方案C (euclidean)：能质耦合欧氏距离（本文核心创新）
- 方案D (pearson)：皮尔逊相关系数
- 方案E (ssr)：供需重叠度/自给自足率

## 两个案例

| 特征 | 德国案例 | 松山湖案例 |
|------|---------|-----------|
| 气候 | 温带，冬季供暖为主 | 亚热带，夏季制冷为主 |
| 负荷类型 | 热主导（热/电=0.29） | 冷主导（冷/电=1.75） |
| 年电负荷 | 1758万kWh | 167万kWh |
| 年冷负荷 | 233万kWh | 291万kWh |
| 电价结构 | 两部制（低电价+高容量费） | 统一电价0.6746¥/kWh |
| 风电 | 有（均值4.9m/s） | 无（城区风速低） |

## 论文四组实验

```bash
uv run python run.py --exp 1              # 德国×5种方法（创新点1主实验）
uv run python run.py --exp 2              # 松山湖×方案B+C（普适性验证）
uv run python run.py --exp 3              # 松山湖×方案C 有/无卡诺电池（创新点2）
uv run python run.py --exp 4              # 松山湖+卡诺×方案B vs C（串联创新点）
uv run python run.py --exp all            # 全部4组实验
uv run python run.py --exp 1 --test-run   # 测试参数快速验证（nind=10, maxgen=5）
```

## 其他运行方式

```bash
uv run python run.py --mode test                        # 测试模式
uv run python run.py --mode full                        # 正式模式（5种方法）
uv run python run.py --mode custom --nind 40 --maxgen 80 --methods std euclidean
uv run python run.py --case songshan_lake --mode test   # 松山湖案例
uv run python run.py --case songshan_lake --carnot --mode test  # 松山湖+卡诺电池
uv run python run.py --check                            # 仅环境检查
```

## 环境要求

- Python 3.8+
- uv 包管理器
- Gurobi 求解器（需要许可证，路径 `C:\Users\ikun\gurobi.lic`）
- 依赖：geatpy, oemof.solph, pyomo, pandas, numpy, matplotlib

```bash
uv sync          # 安装依赖
uv run python run.py --check  # 验证环境
```

## 项目结构

```
ies_optimization/
├── run.py                  # 主入口（实验启动器）
├── case_config.py          # 案例配置（德国/松山湖参数）
├── cchp_gaproblem.py       # 优化问题定义（NSGA-II上层）
├── cchp_gasolution.py      # 实验编排（运行对比、保存结果）
├── operation.py            # 运行调度模型（OEMOF下层）
├── data/                   # 数据文件
│   ├── mergedData.csv              # 德国案例8760h负荷数据
│   ├── typicalDayData.xlsx         # 德国案例14个典型日
│   ├── songshan_lake_data.csv      # 松山湖案例8760h负荷数据
│   ├── songshan_lake_typical.xlsx  # 松山湖案例14个典型日
│   └── optimizationData.xlsx       # 投资系数（旧格式，已迁移到case_config）
├── scripts/                # 辅助脚本
│   ├── generate_songshan_data.py   # 松山湖负荷数据生成器
│   ├── kmeans_clustering.py        # K-Medoids典型日聚类
│   └── test_feasibility.py         # 环境和可行性测试
├── Results/                # 实验结果输出目录
├── 结果分析与展示脚本/      # 后处理和可视化
├── 卡诺电池探索/            # 卡诺电池模块和研究资料
├── 参考资料/                # 参考论文PDF
├── 松山湖/                  # 松山湖项目资料和设备模块库
├── 系统参数/                # 设备参数和成本PDF
├── 研究思路/                # 研究笔记和论文撰写
├── 另外系统/                # 简化版电-热系统（无冷）
└── 测试/                    # 调试和验证脚本
```
