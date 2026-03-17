# IES 源荷匹配优化规划

基于能质系数的综合能源系统（IES）源荷匹配度量化方法与容量配置优化研究。

## 1. 研究背景与问题

综合能源系统（Integrated Energy System, IES）同时涉及电、热、冷三种能源形式。在进行设备容量配置优化时，需要量化"源侧供能"与"荷侧需求"之间的匹配程度。

**核心问题**：电、热、冷三种能源的"品质"不同——1kWh电能可以完全转化为热或冷，但1kWh热能无法完全转化为电。传统方法直接将三种能源的功率数值相加或分别计算，忽略了这种品质差异，导致优化结果偏离实际最优。

**解决思路**：引入热力学中的能质系数（Exergy Quality Factor），基于卡诺因子将不同形式的能源折算到统一标尺（有效能/㶲），再计算源荷匹配度。

能质系数定义：
- λ_e = 1.0（电能，品质最高，完全可转化）
- λ_h = 1 - T₀/T_h ≈ 0.6（热能，70°C供热，部分可转化）
- λ_c = (T₀ - T_c)/T_c ≈ 0.5（冷能，7°C供冷，部分可转化）

## 2. 两个创新点

### 创新点1：能质耦合欧氏距离匹配度（方法创新）

提出三维能质耦合欧氏距离作为源荷匹配度指标：

```
M = (1/T) × Σ √[(λ_e × P_net_e)² + (λ_h × P_net_h)² + (λ_c × P_net_c)²]
```

其中 P_net = P_supply - P_demand 为各能源形式的净负荷（供需差），T=8760小时。

与现有方法的区别：
- 方案B（师兄方法）：σ(P_net_e) + σ(P_net_h) + σ(P_net_c)，三种能源独立计算标准差再相加，没有能质加权，也没有耦合
- 方案D（皮尔逊）：只看供需曲线的趋势相关性，不看绝对大小
- 方案E（自给率）：只看总量是否自给自足，不区分能源品质

### 创新点2：含卡诺电池的IES容量优化（模型创新）

卡诺电池（Carnot Battery）是一种新型长时储能技术，工作原理为"电→热储存→电"：
- 充电：用电驱动热泵，将电能转化为高温热能储存
- 放电：用热机（ORC）将热能转化回电能
- 往返效率（RTE）：约55-70%
- 副产品：充电过程中的余热可回收供热，体现能质梯级利用

在优化框架中增加2个决策变量（卡诺电池功率和容量），使优化器能自动决定是否配置卡诺电池及其最优容量。

## 3. 优化框架

### 3.1 两层优化结构

```
┌─────────────────────────────────────────────────┐
│  上层：NSGA-II 遗传算法                           │
│  决策变量：9~11个设备容量 (kW)                      │
│  目标：min(年化总成本) + min(源荷匹配度)             │
│  输出：Pareto最优解集                              │
│                                                   │
│  每个个体 → 调用下层求解                            │
│  ┌───────────────────────────────────────────┐   │
│  │  下层：OEMOF-SOLPH 线性规划                  │   │
│  │  给定设备容量，求解24h最优运行调度              │   │
│  │  14个典型日 × 加权 → 年化运行成本              │   │
│  │  输出：各设备逐时出力、购网电量、运行成本        │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 3.2 决策变量

| 索引 | 变量 | 含义 | 德国上界(kW) | 松山湖上界(kW) |
|------|------|------|-------------|---------------|
| 0 | ppv | 光伏容量 | 10000 | 1000 |
| 1 | pwt | 风电容量 | 10000 | 0（无风） |
| 2 | pgt | 燃气CHP容量 | 10000 | 800 |
| 3 | php | 电热泵容量 | 3000 | 300 |
| 4 | pec | 电制冷容量 | 1000 | 5000 |
| 5 | pac | 吸收式制冷容量 | 1000 | 1500 |
| 6 | pes | 电储能功率 | 20000 | 2000 |
| 7 | phs | 热储能功率 | 6000 | 500 |
| 8 | pcs | 冷储能功率 | 2000 | 3000 |
| 9* | cb_power | 卡诺电池功率 | 2000 | 500 |
| 10* | cb_capacity | 卡诺电池容量(kWh) | 10000 | 3000 |

*索引9-10仅在启用卡诺电池时存在

### 3.3 目标函数

**目标1：年化总成本**
```
Cost = Σ(invest_coeff_i × capacity_i)     # 设备年化投资
     + storage_fixed × (phs>0) + (pcs>0)  # 储能固定成本
     + capacity_charge × max_grid_power    # 容量电费（德国特有）
     + Σ(typical_day_OC × weight)          # 年化运行成本
     + cb_invest_power × cb_power          # 卡诺电池投资（可选）
     + cb_invest_capacity × cb_capacity
```

**目标2：源荷匹配度**（5种方法，越小越好）

| 方案 | 方法 | 公式 | 特点 |
|------|------|------|------|
| A | economic_only | 无（单目标） | 基准：纯经济最优 |
| B | std | σ(P_net_e) + σ(P_net_h) + σ(P_net_c) | 师兄方法：净负荷波动率 |
| C | euclidean | (1/T)Σ√[(λ_e·P_e)²+(λ_h·P_h)²+(λ_c·P_c)²] | 本文创新：能质耦合 |
| D | pearson | (1 - avg_corr) × 1000 | 只看趋势不看大小 |
| E | ssr | (1 - self_sufficiency) × 1000 | 只看总量不看能质 |

### 3.4 能源系统拓扑

```
                  input/output  ele_bus  heat_bus  cool_bus  gas_bus
                        |          |         |         |         |
 wt(风电)               |--------->|         |         |         |
 pv(光伏)               |--------->|         |         |         |
 grid(电网)             |--------->|         |         |         |
 gas(天然气)            |--------------------------------------->|
                        |          |         |         |         |
 gt(燃气CHP)            |<---------------------------------------|
                        |--------->|         |         |  (耗气发电)
                        |------------------->|         |  (余热供热)
                        |          |         |         |         |
 ehp(电热泵)            |<---------|         |         |  (耗电)
                        |------------------->|         |  (产热)
                        |          |         |         |         |
 ec(电制冷)             |<---------|         |         |  (耗电)
                        |----------------------------->|  (产冷)
                        |          |         |         |         |
 ac(吸收式制冷)          |<-------------------|         |  (耗热)
                        |----------------------------->|  (产冷)
                        |          |         |         |         |
 es(电储能)             |<-------->|         |         |  (充放电)
 hs(热储能)             |          |<------->|         |  (蓄放热)
 cs(冷储能)             |          |         |<------->|  (蓄放冷)
                        |          |         |         |         |
 carnot_battery*        |<-------->|         |         |  (电储能)
 cb_heat_recovery*      |--------->|--->---->|         |  (余热回收)
                        |          |         |         |         |
 ele_demand(电负荷)      |<---------|         |         |         |
 heat_demand(热负荷)     |          |<--------|         |         |
 cool_demand(冷负荷)     |          |         |<--------|         |

 *仅在启用卡诺电池时存在
```

### 3.5 典型日加速

全年8760小时直接优化计算量太大。使用K-Medoids聚类将365天压缩为14个典型日（336小时），加速约26倍。每个典型日有权重（代表的天数），加权求和得到年化值。

## 4. 两个案例对比

| 指标 | 德国案例 | 松山湖案例 |
|------|---------|-----------|
| 位置 | 德国（温带大陆性气候） | 东莞松山湖（亚热带季风气候） |
| 建筑类型 | 工业园区 | 科研产业综合体（A3/A4/A5栋） |
| 建筑面积 | — | 44,938 m² |
| 负荷特征 | 热主导 | 冷主导 |
| 年电负荷 | 1,758万kWh | 167万kWh |
| 年热负荷 | 512万kWh | 59万kWh（生活热水） |
| 年冷负荷 | 233万kWh | 291万kWh |
| 冷负荷峰值 | 356 kW | 5,797 kW |
| 冷/热比 | 0.46 | 4.96 |
| 温度范围 | -9 ~ 32°C | 6 ~ 38°C |
| 风速均值 | 4.9 m/s | 1.8 m/s（城区，不配风电） |
| 电价 | 0.0025 €/kWh + 114.29 €/(kW·a)容量费 | 0.6746 ¥/kWh 统一电价 |
| 气价 | 0.0286 €/kWh | 0.45 ¥/kWh |
| CHP效率 | η_e=0.33, η_h=0.50 | η_e=0.35, η_h=0.45 (CAT G3512E) |
| 电制冷COP | 2.87 | 3.5（高效离心机组） |
| 电热泵COP | 4.44 | 4.0 |
| 数据来源 | 师兄EI论文实测数据 | 松山湖示范方案PDF月度数据合成 |

两个案例形成"热主导 vs 冷主导"的对比，验证方法的普适性：
- 德国案例：能质系数中 λ_h=0.6 的热权重起主要作用
- 松山湖案例：能质系数中 λ_c=0.5 的冷权重起主要作用

## 5. 论文四组实验

| 实验 | 案例 | 方法 | 卡诺电池 | 目的 |
|------|------|------|---------|------|
| 1 | 德国 | A+B+C+D+E | 无 | 创新点1主实验：证明方案C优于其他方法 |
| 2 | 松山湖 | B+C | 无 | 普适性验证：不同负荷结构下方案C仍然更优 |
| 3 | 松山湖 | C | 无→有 | 创新点2：卡诺电池对匹配度和经济性的影响 |
| 4 | 松山湖 | B+C | 有 | 串联验证：含卡诺电池时能质耦合方法仍优于传统方法 |

```bash
# 测试模式（每组约1分钟，验证流程）
uv run python run.py --exp 1 --test-run
uv run python run.py --exp 2 --test-run
uv run python run.py --exp 3 --test-run
uv run python run.py --exp 4 --test-run
uv run python run.py --exp all --test-run   # 一次跑完

# 正式模式（每组约1-3小时，nind=50, maxgen=100）
uv run python run.py --exp 1
uv run python run.py --exp all
```

### 预期分析内容

1. **Pareto前沿对比**：5种方法的Pareto前沿画在同一张图，方案C应更靠近原点
2. **设备配置对比**：不同方法推荐的设备容量差异，方案C应更合理地平衡电热冷
3. **运行特性对比**：年购网电量、弃风弃光率、系统综合能效
4. **能质系数消融**：令λ=1,1,1去掉能质加权，验证能质系数的必要性
5. **卡诺电池效果**：有/无卡诺电池的匹配度和成本变化

## 6. 其他运行方式

```bash
# 预设模式
uv run python run.py --mode test     # nind=10, maxgen=5, 2种方法
uv run python run.py --mode quick    # nind=20, maxgen=20, 3种方法
uv run python run.py --mode full     # nind=50, maxgen=100, 5种方法

# 自定义模式
uv run python run.py --mode custom --nind 40 --maxgen 80 --methods std euclidean

# 指定案例和卡诺电池
uv run python run.py --case songshan_lake --mode test
uv run python run.py --case songshan_lake --carnot --mode test

# 环境检查
uv run python run.py --check
```

## 7. 环境配置

### 依赖

- Python 3.8+（项目使用 3.8）
- uv 包管理器
- Gurobi 求解器（主求解器，需许可证）或 GLPK（备用）
- 核心库：geatpy（遗传算法）、oemof.solph（能源系统建模）、pyomo（优化建模）
- 数据库：pandas、numpy、matplotlib、scipy

### 安装

```bash
# 1. 安装 uv（如果没有）
pip install uv

# 2. 安装项目依赖
uv sync

# 3. 配置 Gurobi 许可证
# 将 gurobi.lic 放到 C:\Users\ikun\gurobi.lic
# 或修改 run.py 和 cchp_gaproblem.py 中的路径

# 4. 验证环境
uv run python run.py --check
```

## 8. 项目结构

```
ies_optimization/
│
├── 核心代码（4个文件构成完整优化框架）
│   ├── run.py                  # 主入口：命令行解析、实验预设、环境检查
│   ├── case_config.py          # 案例配置：德国/松山湖的全部参数
│   ├── cchp_gaproblem.py       # 上层优化：NSGA-II问题定义、目标函数计算
│   ├── cchp_gasolution.py      # 实验编排：运行对比实验、保存结果、生成报告
│   └── operation.py            # 下层调度：OEMOF能源系统建模与求解
│
├── data/                       # 输入数据
│   ├── mergedData.csv                  # 德国案例 8760h×6列 负荷+气象数据
│   ├── typicalDayData.xlsx             # 德国案例 14个典型日聚类结果
│   ├── songshan_lake_data.csv          # 松山湖案例 8760h×6列（合成数据）
│   ├── songshan_lake_typical.xlsx      # 松山湖案例 14个典型日
│   └── optimizationData.xlsx           # 投资系数（旧格式，已迁移到case_config）
│
├── scripts/                    # 辅助脚本
│   ├── generate_songshan_data.py       # 松山湖负荷数据生成（基于PDF月度数据）
│   ├── kmeans_clustering.py            # K-Medoids典型日聚类算法
│   └── test_feasibility.py             # 环境检查和单次求解可行性测试
│
├── Results/                    # 实验结果（自动生成，git忽略）
│   └── CCHP_{case}_{timestamp}/
│       ├── Economic/Std/Euclidean/...  # 各方法的Pareto解集
│       ├── comparison_report.md        # 对比分析报告
│       └── Pareto_Comparison.png       # Pareto前沿对比图
│
├── 结果分析与展示脚本/           # 后处理
│   ├── cchp_result_analysis.py         # 结果深度分析（设备配置、运行特性）
│   ├── method_comparison.py            # 方法对比可视化
│   └── operationRunable.py             # 单方案运行调度可视化
│
├── 卡诺电池探索/                # 卡诺电池研究资料
│   ├── carnot_battery_module.py        # 卡诺电池完整模块（3种技术路线）
│   ├── operation_carnot_integration.py # OEMOF集成示例
│   └── *.md                            # 研究路线图和集成指南
│
├── 参考资料/                    # 参考文献
│   ├── 毕业论文-孔凡淇-终稿.pdf        # 师兄毕业论文（原始框架来源）
│   ├── 计及㶲效率的...pdf              # 㶲效率+IES规划参考论文
│   └── perplexity研究.md               # 文献调研笔记
│
├── 松山湖/                      # 松山湖项目资料
│   ├── 松山湖社区示范方案.pdf           # 核心数据来源（负荷、设备、电价）
│   ├── 23中芬国网配套项目代码库模块/    # 设备模块Python代码
│   └── 单元模块库/                     # 8类能源设备标准化模块
│
├── 系统参数/                    # 设备成本和参数PDF
├── 研究思路/                    # 研究笔记、论文撰写、创新点分析
├── 另外系统/                    # 简化版电-热系统（无冷，用于对比）
├── 测试/                        # 调试和验证脚本
│
├── CLAUDE.md                   # AI助手技术文档（新会话快速上手）
├── pyproject.toml              # 项目配置和依赖声明
└── uv.lock                     # 依赖锁定文件
```

## 9. 数据说明

### 负荷数据格式（mergedData.csv / songshan_lake_data.csv）

8760行（全年逐时）× 6列：

| 列名 | 含义 | 单位 |
|------|------|------|
| ele_load(kW) | 电负荷 | kW |
| heat_load(kW) | 热负荷 | kW |
| cool_load(kW) | 冷负荷 | kW |
| solarRadiation(W/m-2) | 太阳辐射 | W/m² |
| windSpeed(m/s) | 风速 | m/s |
| temperature(C) | 环境温度 | °C |

### 典型日数据格式（typicalDayData.xlsx）

14行 × 3列：

| 列名 | 含义 |
|------|------|
| typicalDayId | 典型日在365天中的编号（1-365） |
| weight | 该典型日代表的天数（14个权重之和=365） |
| days | 被代表的所有天的编号，逗号分隔 |

### 松山湖数据来源

松山湖负荷数据由 `scripts/generate_songshan_data.py` 合成，数据来源为松山湖示范方案PDF：
- 月度冷负荷总量：严格匹配PDF表4（误差<1%）
- 月度电负荷总量：非空调电(69.59万kWh/年) + 空调耗电(97.05万kWh/年)，按月分配
- 冷负荷峰值：5,797 kW（匹配PDF设计值）
- 年总电负荷：166.6万kWh（匹配PDF的166.64万kWh）
- 年总冷负荷：290.8万kWh（匹配PDF的291.15万kWh）
- 热负荷：生活热水为主，约58.7万kWh/年（PDF未给出具体数据，根据1万人估算）
- 气象数据：东莞典型气象年合成（年均温22.7°C，太阳辐射均值172W/m²）

## 10. 结果输出

每组实验输出到 `Results/CCHP_{case}_{timestamp}/` 目录：

```
CCHP_german_03-17-10-53/
├── Economic/
│   ├── ObjV_Economic.csv       # 目标值矩阵 [N×1]（单目标）
│   ├── Phen_Economic.csv       # 决策变量矩阵 [N×9]
│   ├── Chrom_Economic.csv      # 染色体矩阵
│   ├── FitnV_Economic.csv      # 适应度矩阵
│   └── Pareto_Economic.csv     # 完整Pareto表（目标+变量，带列名）
├── Std/                        # 同上结构
├── Euclidean/
├── Pearson/
├── SSR/
├── comparison_report.md        # Markdown格式对比报告
└── Pareto_Comparison.png       # 所有方法Pareto前沿对比图
```

Pareto CSV 列格式：
`Solution_ID, Economic_Cost, Matching_Index, PV, WT, GT, HP, EC, AC, ES, HS, CS [, CB_Power, CB_Capacity]`
