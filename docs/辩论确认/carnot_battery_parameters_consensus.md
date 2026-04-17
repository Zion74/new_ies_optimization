# 卡诺电池参数决策表（AI 辩论最终共识）

**形成时间**：2026-04-16  
**参与方**：Claude Code、Codex  
**状态**：已形成可执行共识；后续代码修改与论文写作默认以本文档为准。  

---

## 1. 研究对象与模型定位

本仓库中的卡诺电池不再表述为完整热力循环求解模型，而应明确表述为：

> An equivalent Carnot battery planning model based on a generic storage representation, using round-trip efficiency, self-discharge, and duration constraints, without explicitly resolving the internal HP-ORC thermodynamic cycle.

这一定义已达成共识，不再继续争论。

---

## 2. 已达成共识的参数与结构

### 2.1 往返效率

| 参数 | 基准值 | 敏感性范围 |
|---|---:|---:|
| `cb_rte` | `0.60` | `0.45 / 0.60 / 0.65` |

**依据**

- 组内论文 `Lin et al. (2026)` 的 TI-CB 结果显示，设计与偏工况下 `η_rt` 处于约 `45.8%–62.6%` 区间。
- 对容量规划层来说，`0.60` 作为等效往返效率基准值合理，但必须配合敏感性分析。

### 2.2 热损失率

| 参数 | 基准值 | 敏感性范围 |
|---|---:|---:|
| `cb_loss_rate` | `0.002 /h` | `0.001 / 0.002 / 0.003 /h` |

**共识说明**

- 原代码 `0.005 /h` 过高，不再作为基准。
- 由于当前研究对象更接近低中温 TI-CB，而非高温 Brayton/PTES，基准值取 `0.002 /h` 更稳妥。
- `0.003 /h` 保留为上界敏感性情景，而不是基准。

### 2.3 时长约束 E/P

| 约束 | 共识值 |
|---|---:|
| `cb_capacity / cb_power` 下界 | `4 h` |
| `cb_capacity / cb_power` 上界 | `8 h` |

**共识说明**

- 这是本轮辩论中最关键的新增发现。
- 当前代码缺少这一约束，优化器已能产生物理上不合理的极端解。
- 后续必须在优化问题中显式加入该约束或等效惩罚。

### 2.4 余热回收支路

| 当前实现 | 最终结论 |
|---|---|
| 独立 `cb heat recovery` Transformer | 删除 |

**共识说明**

- 当前实现并未与卡诺电池充电损失绑定，物理意义不成立。
- 对容量规划层研究而言，直接删除最稳妥。

### 2.5 充放电效率分配

| 参数 | 共识值 | 说明 |
|---|---:|---|
| 充电效率 | `sqrt(cb_rte)` | 规划层对称近似可接受 |
| 放电效率 | `sqrt(cb_rte)` | 不显式展开 HP/ORC 内部不对称性 |

**共识说明**

- 真实 TI-CB 中充放电链路并不对称。
- 但对外层容量配置优化而言，只要总 `RTE` 保持一致，对称分配可接受。

---

## 3. 成本参数：采用三情景，不再使用单一值

### 3.1 情景命名共识

成本参数不再争论“唯一正确值”，统一采用三情景表达：

1. `optimistic`
2. `reference-literature`
3. `intermediate`（可选）

其中：

- `reference-literature` 是最强文献锚点情景；
- `optimistic` 是未来规模化或商业成熟后的乐观情景；
- `intermediate` 是工程过渡情景，不是最强文献锚点。

### 3.2 德国案例建议值

| 情景 | `cb_invest_power` | `cb_invest_capacity` | 说明 |
|---|---:|---:|---|
| `optimistic` | `12–15 €/(kW·a)` | `2 €/(kWh·a)` | 偏乐观、适合未来成熟化情景 |
| `reference-literature` | `37 €/(kW·a)` | `2–3 €/(kWh·a)` | 文献锚定情景 |
| `intermediate` | `20–25 €/(kW·a)` | `3 €/(kWh·a)` | 过渡情景，可选 |

### 3.3 松山湖案例建议值

按近似换算 `1 € ≈ 7.5 ¥`：

| 情景 | `cb_invest_power` | `cb_invest_capacity` |
|---|---:|---:|
| `optimistic` | `90–110 ¥/(kW·a)` | `15 ¥/(kWh·a)` |
| `reference-literature` | `278 ¥/(kW·a)` | `15–22 ¥/(kWh·a)` |
| `intermediate` | `150–188 ¥/(kW·a)` | `22 ¥/(kWh·a)` |

### 3.4 对成本分歧的最终结论

本轮辩论的最后分歧点是：`reference` 情景的功率成本到底应以 `20–25` 还是 `37 €/(kW·a)` 表示。

最终共识如下：

- `37 €/(kW·a)` 可以作为 `reference-literature`，因为其对应的 `~400 €/kW` 有文献锚定；
- `20–25 €/(kW·a)` 可以保留，但只应命名为 `intermediate`，不应替代 `reference-literature`；
- 因此，这一分歧已经从“参数真伪争论”转化为“情景标签区分”，实质上已解决。

---

## 4. 后续代码修改优先级

| 优先级 | 文件 | 修改内容 |
|---|---|---|
| P1 | `cchp_gaproblem.py` | 增加 `4 h <= cb_capacity/cb_power <= 8 h` 约束 |
| P1 | `operation.py` | 删除 `cb heat recovery` 支路 |
| P1 | `case_config.py` | 将 `cb_loss_rate` 从 `0.005` 改为 `0.002` |
| P2 | `case_config.py` | 把成本参数改成情景化，至少在注释中保留三情景口径 |
| P2 | 论文文稿 | 明确使用 `equivalent Carnot battery planning model` 表述 |

---

## 5. 论文写作建议

建议在结果分析中按以下顺序表达：

1. 在 `optimistic` 情景下，卡诺电池是否进入 Pareto 前沿。
2. 在 `reference-literature` 情景下，卡诺电池何时退出或仅在匹配目标下保留。
3. 给出 `break-even` 成本区间，而不是只给单一经济结论。

---

## 6. 参考依据

- Frate, G. F., Ferrari, L., Desideri, U., et al. (2020). *Multi-Criteria Investigation of a Pumped Thermal Electricity Storage (PTES) System with Thermal Integration and Sensible Heat Storage*. Frontiers in Energy Research, 8, 53. https://doi.org/10.3389/fenrg.2020.00053
- Zhao, Y., et al. (2022). *Thermo-economic analysis of a pumped thermal electricity storage system*. Renewable Energy, 185, 1018-1029. https://doi.org/10.1016/j.renene.2022.01.017
- Lin et al. (2026). *Performance optimization of thermal integrated-Carnot battery for waste heat utilization in industrial integrated energy systems*. 组内论文。

**说明**

- `Wikipedia` 与 `ResearchGate` 不再作为正式参数依据写入共识文档。
- 若后续补充 DLR/RWTH 原始报告，可继续增强 `optimistic` 与 `reference-literature` 的文献锚定。
