# SCI 图表与表格计划

更新时间：2026-07-14

本文件只服务当前“BESS—熔盐 TES 技术选择边界”SCI。旧 EQD/Carnot 图表计划不再定义当前主稿。

## 1. 主图

| 编号 | 建议标签 | 目的 | 数据来源 | 主文 / 补充 | 状态 |
|---|---|---|---|---|---|
| Fig 1 | `fig:system_boundary` | 说明联营组合、单一 PCC、双机 CHP、BESS 与 HT/MT TES 边界 | E0 模型 | 主文 | 待绘制 |
| Fig 2 | `fig:chp_feasible_region` | 验证热负荷如何抬高 CHP 强迫电出力 | E0 校准 | 主文 | 台账凸包回归通过；热基准与煤耗面待确认 |
| Fig 3 | `fig:value_decomposition` | 区分电量时移、热替代和强迫出力释放 | E1 | 主文 | 待生成 |
| Fig 4 | `fig:epsilon_front` | 展示四架构同服务下的成本—弃风前沿 | E2 | 主文 | 待生成 |
| Fig 5 | `fig:physical_regime_map` | 给出 \(H^*\times G^*\) 的技术选择区域，按风电分面 | E3 | **主文核心图** | 待生成 |
| Fig 6 | `fig:duration_cost_map` | 给出共同服务时长 × TES 相对基准成本倍率的经济边界，按三类物理冲突分面 | E4 | **主文核心图** | 待生成 |
| Fig 7 | `fig:full_year_validation` | 证明代表周边界可被 8784 h 回代 | E5 | 主文 | 待生成 |
| Fig S1 | `fig:boundary_refinement` | 展示边界二分加密与无差异带 | E3/E4 | 补充 | 待生成 |
| Fig S2 | `fig:deterministic_sensitivity` | 展示成本、寿命、效率、碳价等造成的边界移动 | E6 | 补充 | 待生成 |
| Fig S3 | `fig:typical_weeks` | 展示 4 个聚类周、2 个强制极端周和年末 48 h 尾段 | E5 | 补充 | 待生成 |

## 2. 主表

| 编号 | 建议标签 | 目的 | 数据来源 | 状态 |
|---|---|---|---|---|
| Tab 1 | `tab:system_parameters` | 汇总 CHP、风光、PCC、价格和碳参数及来源 | E0 | 正式热量、双机 CHP 与 PCC 物理口径已闭合；项目级价格、碳履约和 VOM 仍 BLOCKED |
| Tab 2 | `tab:storage_parameters` | 分列 BESS 功率/可用电量与 TES 端口/盐量/罐容、效率、寿命、更换和运维 | E0 | BESS 已闭合；TES 12 个正式账户仍全部 BLOCKED；E0-D-18 的系统 EAC 区间不能填充本表部件价格，DLR 两罐值仍只作聚合校准 |
| Tab S-E0D18 | `tab:e0d18_screening` | 24 h 精确点与 336 h 有界窗口的燃煤、弃电、PCC、辅机、主目标界及全系统 EAC 区间 | E0 | 可放补充材料；必须标明旧 2019 风光、燃料单项、非全年，以及 336 h 0.48% 主 gap；不进入正式主结果表 |
| Tab S-E0D23 | `tab:e0d23_settlement_envelope` | D19 可接受调度集内 24 h/336 h PCC 重分配最小值、最大值、primal/dual 与 D22 可行证人 | E0 | 24 h 精确闭合；336 h 只报告严格宽区间。必须标明未赋实际价格、不是结算损失、完整 TAC 或技术赢家 |
| Tab S-E0D26 | `tab:e0d26_numerical_certificate` | 无量纲 cap、strict tolerance、D19 条件面与开放整数模式的最小/最大 primal/dual、有限界标志和证人支配审计 | E0 | 24 h 报告 D26 修正后的严格精确值；336 h 仅报告严格区间及条件面最大可行证人，不把 `optimal` 标签等同于完整证书 |
| Tab 3 | `tab:fairness_architectures` | 固定四架构与公平比较口径 | E1/E2 | 待整理 |
| Tab 4 | `tab:yangling_results` | 杨凌基准点四架构最优配置与年度结果 | E2 | 待生成 |
| Tab 5 | `tab:validation` | 代表周与 8784 h 的误差、后悔值和赢家一致性 | E5 | 待生成 |
| Tab S1 | `tab:solver_performance` | HiGHS MIP gap、时间、内存和失败重试 | E0-E6 | E0-D-18、D23 与 D26 已有 24 h/336 h 验收；D26 使用 60 核服务器分批并行、单任务显式线程上限，必须保留方向正确的 primal/dual、有限界标志和条件证人；E1-E6 批量性能待生成 |

## 3. 图表信息纪律

每张选择地图至少同时显示：

- 最优架构；
- 最优与次优的成本差；
- 5% 经济无差异带；
- 不可行区域；
- 杨凌真实点；
- 关键边界点的最优功率、能量和时长。

不能只画“赢家颜色”而隐藏差值，否则很容易把数值噪声误写成硬边界。

## 4. 结果产出顺序

1. Fig 1 / Fig 2 + Tab 1 / Tab 2：先锁物理与参数；
2. Fig 3：证明价值分解口径成立；
3. Fig 4 + Tab 3 / Tab 4：建立公平前沿；
4. Fig 5：形成物理适用域；
5. Fig 6：形成经济适用域；
6. Fig 7 + Tab 5：通过全年验证；
7. 最后补充 Fig S1-S3、Tab S-E0D18、Tab S-E0D23、Tab S-E0D26 与 Tab S1。

在 E0、E1 未通过前，不允许先跑大规模边界图。

## 5. 图注禁区

图注不得使用：

- “same-size fair comparison”；
- “TES always outperforms BESS”；
- “full-year”描述代表日或代表周结果；
- 未通过 E5 时使用“general boundary”；
- 用 TES 热 MWh 与 BESS 电 MWh 作直接等值比较。
