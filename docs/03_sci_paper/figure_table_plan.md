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
| Tab S-E0D27 | `tab:e0d27_direction_sign_certificate` | 固定方向 primal/dual、符号固定点、正负分解全局 primal/dual、L1 重算和严格残差 | E0 | 方向 dual 必须明确标为非全局；24 h 报告修正后精确最大值，336 h 报告收紧后严格区间和时限终止 |
| Tab S-E0D28 | `tab:e0d28_multistart_screening` | 两个预注册种子的初始 support 证人、primal/dual、返回轨迹 L1、符号变化、固定点和改善量 | E0 | 补充材料负筛查；必须标明单轮 1800 s、未达固定点、方向 dual 非全局，不能写成全正交域排除或全局最优证明 |
| Tab S-E0D29 | `tab:e0d29_export_linked_bound` | 逐时/聚合 cut 数、D27 参考区间、solver primal、轨迹重算 L1、finite global dual、上界改善与严格残差 | E0 | 补充材料数值证书；24 h 沿用 D27 精确点，336 h 报告收紧后宽区间；不得写成实际结算或 E1 结果 |
| Tab S-E0D30 | `tab:e0d30_physics_service_bound` | 静态 PCC 外包络宽度、年度服务传播、正反向符号宽度压缩、已知证人包含性、D29 参考区间、primal/轨迹重算/dual、数值钳制和严格残差 | E0 | 补充材料物理界紧化证书；24 h 保留精确点，336 h 上界收紧至 `777,141.368858 MWh/a`；不得写成闭合或实际结算 |
| Tab S-E0D31 | `tab:e0d31_intertemporal_obbt_screen` | 双窗口 LP 数/最优计数/进程分配、D30→D31 正负宽度、证人包含、24 h 等价门、336 h 1% 停止门槛与 retained D30 interval | E0 | 补充材料负筛查证书；重点报告 24 h 明显收紧但 336 h 增量不足 `0.1%`，未启动 336 h global probe；不得画成新 global bound |
| Tab S-E0D46 | `tab:e0d46_upper_bound_recovery` | 三架构 R0 guide、seed 行不可行数、候选墙钟、incumbent/Repair 状态、资源峰值与残留进程 | E0/E5 | 补充材料失败证据；必须明确三个 guide 都不是可行上界，三架构均为 `no_candidate_incumbent`、上界恢复数为 0，不能写成物理不可行或技术排序 |
| Tab S-E0D48 | `tab:e0d48_primal_recovery` | 三架构完整二元数、Hamming seed 身份、首 incumbent/工程 infeasible/未闭合状态、固定二元原成本 repair、残差、容量和上界资格 | E0/E5 | Gate A `1d894652...` 已通过；D48-R1 三架构均为 `no_primal_status_closure`，无 candidate/repair/上界，总 manifest `ca024880...`。Hamming objective、postmortem、Gate A 和阶段失败都不是上界 |
| Tab S-E0D49 | `tab:e0d49_fuel_projection_recovery` | 原始/投影/保留二元清单、燃料编码依赖、精确提升残差、候选与原成本 repair 资格 | E0/E5 | Gate A `11b283d6...` 已通过；正式 BESS 在 `3720.637 s` 无 candidate/repair，终态 `no_primal_status_closure`、formal manifest `0d66f06d...`。表中上界/容量/提升残差/repair 列必须留空并注明未进入相应阶段；Gate A 与 toy 不进入上界列 |
| Tab S-E0D50 | `tab:e0d50_block_relax_fix` | 53 个提交阶段、固定/整数前视/未来放松/燃料投影计数、首 incumbent、完整物理轨迹、精确提升和 clean repair 资格 | E0/E5 | 当前只存在结果前合同，不进入正文结果。只有 Gate A 与正式运行完成后才追加；部分阶段或投影 objective 不得进入上界、容量或 gap 列 |
| Tab 3 | `tab:fairness_architectures` | 固定四架构与公平比较口径 | E1/E2 | 待整理 |
| Tab 4 | `tab:yangling_results` | 杨凌基准点四架构最优配置与年度结果 | E2 | 待生成 |
| Tab 5 | `tab:validation` | 代表周与 8784 h 的误差、后悔值和赢家一致性 | E5 | 待生成 |
| Tab S1 | `tab:solver_performance` | HiGHS MIP gap、时间、内存和失败重试 | E0-E6 | E0-D-18、D23、D26–D31 已有 24 h/336 h 验收；必须保留方向正确的 primal/dual、有限界标志、证人、数值钳制、OBBT worker 重建和方向/全局语义；E1-E6 批量性能待生成 |

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
7. 最后补充 Fig S1-S3、Tab S-E0D18、Tab S-E0D23、Tab S-E0D26、Tab S-E0D27、Tab S-E0D28、Tab S-E0D29、Tab S-E0D30、Tab S-E0D31、Tab S-E0D46、Tab S-E0D48、Tab S-E0D49、Tab S-E0D50 与 Tab S1。

在 E0、E1 未通过前，不允许先跑大规模边界图。

## 5. 图注禁区

图注不得使用：

- “same-size fair comparison”；
- “TES always outperforms BESS”；
- “full-year”描述代表日或代表周结果；
- 未通过 E5 时使用“general boundary”；
- 用 TES 热 MWh 与 BESS 电 MWh 作直接等值比较。
