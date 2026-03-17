# IES 优化框架技术文档

本文档供 AI 助手（Claude/Copilot）在新会话中快速理解本仓库，无需逐文件阅读。

## 1. 核心架构

```
run.py  →  cchp_gasolution.py  →  cchp_gaproblem.py  →  operation.py
(入口)      (实验编排)              (GA优化问题)           (OEMOF调度)
                                        ↑
                                  case_config.py
                                  (案例参数)
```

### 数据流

1. `run.py` 解析命令行参数，加载 `case_config.py` 中的案例配置
2. `cchp_gasolution.py` 的 `run_comparative_study()` 按方法列表依次调用 `run_single_experiment()`
3. 每个实验创建 `CCHPProblem`（继承 geatpy.Problem），运行 NSGA-II 或 DE 算法
4. 每代每个个体调用 `sub_aim_func_cchp()`，内部创建 `OperationModel` 求解24h调度
5. 14个典型日加权求和得到年化目标值
6. 结果保存到 `Results/CCHP_{case_name}_{timestamp}/`

## 2. 核心文件详解

### case_config.py — 案例配置

两个字典 `GERMAN_CASE` 和 `SONGSHAN_LAKE_CASE`，包含：
- `data_file` / `typical_day_file`：数据文件路径（绝对路径，用 `_os.path.join(_BASE, "data", ...)` 构建）
- `ele_price` / `gas_price`：24小时电价/气价列表
- `capacity_charge`：容量电费（德国114.29€/(kW·a)，松山湖0）
- `var_ub`：9个决策变量上界 [ppv, pwt, pgt, php, pec, pac, pes, phs, pcs]
- `invest_coeff`：9个年化投资系数
- 设备效率：`gt_eta_e`, `gt_eta_h`, `ac_cop`, `ehp_cop`, `ec_cop` 等
- 能质系数：`lambda_e=1.0`, `lambda_h=0.6`, `lambda_c=0.5`
- 卡诺电池参数：`enable_carnot_battery`, `cb_power_ub`, `cb_capacity_ub`, `cb_rte` 等

关键函数：
- `get_case(name)` → 返回配置的深拷贝
- `enable_carnot_battery(config)` → 设置 `config["enable_carnot_battery"] = True`

### cchp_gaproblem.py — 优化问题

`CCHPProblem(ea.Problem)`:
- `__init__(PoolType, method, case_config)` — 从配置加载数据，设置决策变量维度（9或11）
- `aimFunc(pop)` — 并行评估种群，调用 `sub_aim_func_cchp()`

`sub_aim_func_cchp(args)` — 核心评估函数（在子进程中运行）：
- 解析9+2个决策变量
- 遍历14个典型日，每天创建 `OperationModel` 求解
- 计算两个目标：
  - 目标1（经济性）= Σ(invest_coeff × capacity) + capacity_charge × max_grid + 运行成本
  - 目标2（匹配度）= 根据method计算（euclidean/std/pearson/ssr）
- 匹配度计算中使用 `config["lambda_e/h/c"]` 能质系数

5种匹配度方法：
- `euclidean`：√[Σ(λ_e·|P_net_e|)² + (λ_h·|P_net_h|)² + (λ_c·|P_net_c|)²] / 8760
- `std`：σ(P_net_e) + σ(P_net_h) + σ(P_net_c)
- `pearson`：(1 - avg_correlation) × 1000
- `ssr`：(1 - self_sufficiency_rate) × 1000
- `economic_only`：单目标，无匹配度

### operation.py — OEMOF 调度模型

`OperationModel.__init__()` 参数：
- 前16个参数与原始代码一致（向后兼容）
- `config=None`：案例配置字典，None时使用硬编码默认值
- `cb_power=0, cb_capacity=0`：卡诺电池参数

能源拓扑（4条母线）：
```
ele_bus:  grid → | ← wt, pv, gt | → ele_demand, ec, ehp, es, [carnot_battery]
heat_bus: gt →   | ← ehp        | → heat_demand, ac, hs, [cb_heat_recovery]
cool_bus: ac →   | ← ec         | → cool_demand, cs
gas_bus:  gas →  |               | → gt
```

卡诺电池建模（当 cb_power > 0）：
- `GenericStorage` 连接 ele_bus（充放电效率 = rte^0.5 ≈ 0.775）
- `Transformer` "cb heat recovery" 连接 ele_bus → heat_bus（余热回收）

关键方法：
- `optimise()` — 求解（先试Gurobi，失败用GLPK）
- `get_objective_value()` — 返回运行成本
- `get_complementary_results()` — 返回各设备出力时序

### cchp_gasolution.py — 实验编排

`run_comparative_study(nind, maxgen, pool_type, inherit_population, methods_to_run, case_config)`:
- 按方法列表依次运行实验
- 种群继承：euclidean 继承 std 的最终种群
- 保存结果到 `Results/CCHP_{case_name}_{timestamp}/`
- 生成 `comparison_report.md` 和 `Pareto_Comparison.png`

`run_single_experiment(method, nind, maxgen, pool_type, initial_population, case_config)`:
- 创建 `CCHPProblem`
- 双目标用 `MyNSGA2`，单目标用 `MySGA`（DE算法）
- 返回 `{algorithm, BestIndi, population, time}`

### run.py — 入口

两种运行方式：
1. `--mode test/quick/full/custom` — 原有模式
2. `--exp 1/2/3/4/all [--test-run]` — 论文四组实验

论文实验定义在 `EXPERIMENTS` 字典中：
- 实验1：german × 5种方法
- 实验2：songshan_lake × std + euclidean
- 实验3：songshan_lake × euclidean（无卡诺 + 有卡诺）
- 实验4：songshan_lake + carnot × std + euclidean

`--test-run` 用 nind=10, maxgen=5 快速验证；不加则用 nind=50, maxgen=100。

## 3. 数据文件

### data/mergedData.csv（德国案例）
8760行×6列：`ele_load(kW), heat_load(kW), cool_load(kW), solarRadiation(W/m-2), windSpeed(m/s), temperature(C)`

### data/songshan_lake_data.csv（松山湖案例）
同上格式。由 `scripts/generate_songshan_data.py` 生成，基于松山湖PDF月度数据合成。
关键指标：年电负荷166.6万kWh，年冷负荷291万kWh，冷负荷峰值5797kW。

### data/typicalDayData.xlsx / songshan_lake_typical.xlsx
14行×3列：`typicalDayId, weight, days`
- typicalDayId：典型日在365天中的编号
- weight：该典型日代表的天数
- days：被代表的所有天的编号（逗号分隔）

## 4. 决策变量

| 索引 | 变量 | 含义 | 德国上界 | 松山湖上界 |
|------|------|------|---------|-----------|
| 0 | ppv | 光伏容量(kW) | 10000 | 1000 |
| 1 | pwt | 风电容量(kW) | 10000 | 0 |
| 2 | pgt | CHP容量(kW) | 10000 | 800 |
| 3 | php | 电热泵容量(kW) | 3000 | 300 |
| 4 | pec | 电制冷容量(kW) | 1000 | 5000 |
| 5 | pac | 吸收式制冷容量(kW) | 1000 | 1500 |
| 6 | pes | 电储能功率(kW) | 20000 | 2000 |
| 7 | phs | 热储能功率(kW) | 6000 | 500 |
| 8 | pcs | 冷储能功率(kW) | 2000 | 3000 |
| 9* | cb_power | 卡诺电池功率(kW) | 2000 | 500 |
| 10* | cb_capacity | 卡诺电池容量(kWh) | 10000 | 3000 |

*仅当 `enable_carnot_battery=True` 时存在

## 5. 结果目录结构

```
Results/CCHP_{case}_{timestamp}/
├── Economic/           # 方案A结果
│   ├── ObjV_Economic.csv
│   ├── Phen_Economic.csv
│   └── Pareto_Economic.csv
├── Std/                # 方案B结果
├── Euclidean/          # 方案C结果
├── Pearson/            # 方案D结果
├── SSR/                # 方案E结果
├── comparison_report.md
└── Pareto_Comparison.png
```

Pareto CSV 列：`Solution_ID, Economic_Cost, Matching_Index, PV, WT, GT, HP, EC, AC, ES, HS, CS [, CB_Power, CB_Capacity]`

## 6. 常见修改场景

### 添加新的匹配度方法
1. `cchp_gaproblem.py` 的 `sub_aim_func_cchp()` 中添加计算逻辑
2. `run.py` 的 `ALL_METHODS` 和 `METHOD_DESC` 中注册
3. `cchp_gasolution.py` 的 `method_info` 中添加名称和文件夹名

### 添加新案例
1. `case_config.py` 中添加新的配置字典
2. `get_case()` 中注册
3. 准备对应的 `data/xxx_data.csv` 和 `data/xxx_typical.xlsx`
4. `run.py` 的 `--case` choices 中添加

### 添加新设备
1. `operation.py` 的 `OperationModel.__init__()` 中添加 OEMOF 组件
2. `cchp_gaproblem.py` 中增加决策变量（修改 Dim、ub、变量解析）
3. `case_config.py` 中添加对应的上界和投资系数
4. `cchp_gasolution.py` 的 `save_method_results()` 中更新 var_names

### 修改能质系数
直接修改 `case_config.py` 中的 `lambda_e`, `lambda_h`, `lambda_c`。
消融实验：设为 1.0, 1.0, 1.0 即可去掉能质加权。

## 7. 已知限制

- Gurobi 许可证路径硬编码为 `C:\Users\ikun\gurobi.lic`（在 run.py 和 cchp_gaproblem.py 中）
- 报告中货币符号统一用 €，松山湖案例实际是 ¥（待修复）
- Thread 模式下 Gurobi 不可用（signal 限制），必须用 Process 模式
- 松山湖负荷数据是合成的（基于PDF月度总量+气候模型），非实测逐时数据
