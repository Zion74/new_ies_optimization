# 文档中心

更新时间：2026-07-16

`docs/` 是本仓库研究架构、论文逻辑、实验映射与文档治理的唯一权威入口。凡是涉及会议论文、SCI 论文、硕士论文的主线、章节、实验、图表、代码映射与归档判断，先看这里，而不是回到散落旧笔记中重新猜。

## 1. 目录说明

- `01_overview/`：总览层，回答“整个研究现在讲什么、三层怎么映射、项目代码与结果结构怎么快速看”。
- `02_conference_paper/`：源荷匹配会议稿的逻辑与映射；负荷预测作为另一篇独立会议成果，不再进入大论文主线。
- `03_sci_paper/`：当前 TES/BESS/Hybrid 技术选择边界 SCI 的逻辑、完整模型实验设计与映射；旧 EQD/Carnot 材料仅作历史资产。
- `04_master_thesis/`：硕士论文最新结构、第 2—5 章映射、第 4 章储能边界计划与第 5 章 Agentic 决策支持计划。
- `辩论确认/`：多 AI 对实验结论、论文结构、闭环性的分歧与共识沉淀。
- `90_governance/`：文档维护规则与归档规则。
- `99_archive/`：被替代的历史笔记、旧结构稿、旧会议草稿归档。

## 2. 推荐阅读顺序

1. `项目索引目录.md`
2. `docs/01_overview/latest_research_architecture.md`
3. `docs/01_overview/three_layer_mapping.md`
4. 对应层级的 `latest_logic_structure.md`
5. 当前 SCI 任务还必须读 `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
6. 当前 E0 实现或实验任务再读 `docs/03_sci_paper/e0_validation_status.md`
7. 涉及寿命成本、替换/残值或 BESS 退化时读 `docs/03_sci_paper/e0_lifetime_economics_contract.md`
8. 涉及 BESS/TES 真实成本参数、价格基年或证据等级时读 `docs/03_sci_paper/e0_parameter_evidence_portfolio.md`
9. 判断某个成本值能否进入正式 TAC 时读 `docs/03_sci_paper/e0_cost_evidence_gap_matrix.md`
10. 判断 TES 哪些账户仍阻断、聚合锚点能否进入部件账本或是否需要复合证据审批时读 `docs/03_sci_paper/e0_tes_formal_cost_readiness_contract.md`
11. 在 TES 正式价格缺失时计算允许的全系统年化成本上限、物理价值差值或判断阈值能否进入主结果时读 `docs/03_sci_paper/e0_tes_break_even_contract.md`
12. 将 E0-C 年度解接入盈亏平衡内核、复现 E0-D-17 的 24 h 探索阈值时读 `docs/03_sci_paper/e0_tes_break_even_adapter_and_exploration_contract.md`
13. 复现 E0-D-18 的 336 h 性能紧化、0.5% gap 合同或 primal/dual 阈值区间时读 `docs/03_sci_paper/e0_tes_two_window_performance_and_interval_contract.md`
14. 复现 E0-D-19 的同年度 PCC 外送、固定平价抵消、336 h 零偏差 warm start 或审计电力结算/碳/VOM 证据时读 `docs/03_sci_paper/e0_same_pcc_service_and_operating_cost_boundary_contract.md`
15. 判断四类非燃料运行成本是否可进入正式 TAC、复核杨凌 H 列燃料重叠风险或复现 E0-D-20 证据门控时读 `docs/03_sci_paper/e0_operating_cost_evidence_readiness_contract.md`
16. 将 E0-D-19 燃料空间与四类缺证成本连接、复现遗漏成本阈值或审计区间稳健性时读 `docs/03_sci_paper/e0_shadow_cost_robustness_contract.md`
17. 审计同年度 PCC 下的逐时外送轨迹、固定平价恒等式、价格跨度结算包络或 D21 结算单账户临界价差时读 `docs/03_sci_paper/e0_pcc_settlement_exposure_contract.md`
18. 在 D19 可接受调度集内复现 PCC 重分配双向极值、审计 24 h 精确包络或解释 336 h primal/dual 宽区间时读 `docs/03_sci_paper/e0_alternative_dispatch_settlement_envelope_contract.md`
19. 审计 D23/D26 的约束尺度、严格容差、条件整数面证人、有限界标志或 D26 历史双窗口数值时读 `docs/03_sci_paper/e0_d26_numerical_certification_contract.md`
20. 审计 D27 固定支持方向、符号固定点、正负差值分解、方向 dual/全局 dual 语义或最新最大端数值时读 `docs/03_sci_paper/e0_d27_direction_generation_and_sign_reformulation_contract.md`
21. 复现 D28 的 `negated`/`alternating` 一步多起点筛查、解释负 support primal 或审计“局部 dual 非全局界”时读 `docs/03_sci_paper/e0_d28_multistart_direction_screening_contract.md`
22. 复现 D29 的外送/余量有效不等式、正负年化质量平衡、24 h 等价性门或审计 D29 历史 336 h global dual 时读 `docs/03_sci_paper/e0_d29_export_linked_bound_tightening_contract.md`
23. 复现 D30 的静态物理 PCC 外包络、年度服务区间传播、区间感知符号不等式、数值钳制审计或读取最新 336 h global dual 时读 `docs/03_sci_paper/e0_d30_physics_service_bound_tightening_contract.md`
24. 复现 D31 的完整跨时段连续松弛 OBBT、并行 worker 重建、24 h 等价性门或审计 336 h 负筛查/停止门槛时读 `docs/03_sci_paper/e0_d31_intertemporal_relaxation_obbt_contract.md`
25. 合并审计 12 个 TES 与 4 个非燃料账户、判断公开来源能否替代项目账本或复现 E0-D-24 的证据分层时读 `docs/03_sci_paper/e0_formal_tac_evidence_route_contract.md`
26. 向项目方索取结算、碳、CHP/TES VOM 数据，复核字段缺口、空白提交模板或隐私隔离规则时读 `docs/03_sci_paper/e0_project_primary_evidence_intake_contract.md`
27. 使用 Rahman BESS 正式来源候选、2019 USD→2024 CNY、三接缝口径或完整 fixed-capacity BESS 生命周期账本时读 `docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md`
28. 使用 NREL BESS 工程敏感性成本、2020 USD→2024 CNY 换算或 FOM/replacement 互斥时读 `docs/03_sci_paper/e0_sensitivity_cost_anchor_contract.md`
29. 使用公开聚合/分项 TES 成本组合、审计作者价格年/代理账户或独立容量核时读 `docs/03_sci_paper/e0_public_tes_cost_portfolio_and_capacity_gate_contract.md`
30. 使用完整内生容量模型、共同 PCS、TES 可变损失/辅机、独立额定放能认证或 D34 双窗口样本时读 `docs/03_sci_paper/e0_d34_endogenous_capacity_full_model_contract.md`
31. 涉及三罐、双服务、五路径文献依据或创新边界时读 `docs/03_sci_paper/e0_tes_topology_evidence_contract.md`
32. 涉及 MT→LT 供热夹点、供回水温度来源、HITEC 液态裕量或可交付热量时读 `docs/03_sci_paper/e0_tes_heat_delivery_pinch_contract.md`
33. 涉及 MT 候选、发电—供热显热分割或候选来源身份时读 `docs/03_sci_paper/e0_tes_mt_scenario_contract.md`
34. 涉及杨凌原始数据或 CHP 口径时读 `docs/03_sci_paper/e0_original_source_evidence_audit.md`
35. 运行三个预注册物理状态的代表周规划、8784 h 固定容量回代或全年容量重优化时读 `docs/03_sci_paper/e0_d38_three_state_representative_full_year_prevalidation_contract.md`
36. 解释原 `H*=0.80/G*=0.70` 状态为什么在时间聚合比较前失败时读 `docs/03_sci_paper/e0_d38_original_high_heat_state_failure.md`
37. 执行一次性 `H*=G*=0.70` 修订状态时读 `docs/03_sci_paper/e0_d38r1_revised_high_heat_prevalidation_contract.md`
38. 解释服务感知八周修订为何只修复分类、未修复定量保真时读 `docs/03_sci_paper/e0_d39_service_aware_representative_week_refinement_contract.md` 与 `docs/03_sci_paper/e0_d39_gate_b_quantitative_fidelity_failure.md`
39. 构造或求解真实 8784 h 全年优先模型、判断单体 HiGHS 路线能否成为正式证据时读 `docs/03_sci_paper/e0_d40_full_year_first_compute_evidence_gate_contract.md`
40. 在 D40 单体路线失败后实现合法全年下界、候选离散轨迹、原始全年可行修复与硬墙钟证书时读 `docs/03_sci_paper/e0_d41_strict_full_year_bound_repair_decomposition_contract.md`
41. 在 D41 TES R0 无法返回合法下界后实现原生 HiGHS 可中断求解、基解检查点与独立拉格朗日下界时读 `docs/03_sci_paper/e0_d42_native_highs_interruptible_lagrangian_bound_contract.md`
42. 从 D42 冻结 row dual 只读恢复串行 80 位证书、理解 D43 正式超时终态时读 `docs/03_sci_paper/e0_d43_frozen_snapshot_offline_dual_certificate_contract.md`
43. 查看 D43 单核认证超时后的 24 块/快照、48-worker 数学等价并行证书合同、Gate A 与 TES 下界恢复终态时读 `docs/03_sci_paper/e0_d44_fork_parallel_lagrangian_certificate_contract.md`
44. 在 TES 下界恢复后，为 Hybrid R0 分离原生双快照与 fork 严格证书、闭合三架构下界时读 `docs/03_sci_paper/e0_d45_hybrid_r0_strict_lower_bound_contract.md`
45. 在 D45 双快照已有但 24 块证书触发墙钟后，以 56 个加权持久块只读恢复 Hybrid 严格下界时读 `docs/03_sci_paper/e0_d47_hybrid_weighted_persistent_certificate_contract.md`
46. 在三架构严格下界闭合后，以工程容量锚点、R0 seed、首 incumbent 和固定二元 Repair A/B 恢复首组原 MILP 可行上界时读 `docs/03_sci_paper/e0_d46_full_year_feasible_upper_bound_repair_contract.md`
47. 在 D46 没有任何 incumbent 后，以原容量边界、完整二元等权 Hamming 搜索和固定二元原成本 LP 恢复 primal 时读 `docs/03_sci_paper/e0_d48_hamming_feasibility_primal_recovery_contract.md`
48. 审计 D48 错误输出路径、唯一正确路径替代启动及 D48-R1 BESS/TES/Hybrid 阶段结果时读 `docs/03_sci_paper/e0_d48_r1_administrative_path_correction_contract.md`
49. 在 D48-R1 无 primal 状态闭合后，以物理二元 Hamming、CHP 燃料编码投影、确定性精确提升和原成本 LP 恢复 BESS 上界时读 `docs/03_sci_paper/e0_d49_physics_first_fuel_projection_primal_recovery_contract.md`
50. 对应层级的实验 / 图表 / 代码映射文档
51. 若任务涉及其他模型定义 / 数据口径争议，再读 `docs/辩论确认/` 与相应 research session
52. 需要做清理或迁移时，再读 `docs/90_governance/`

## 3. 与稿件源码目录的分工

- `论文撰写/会议/`：只保留会议稿正式源码、图表、数据、README 与编译产物。
- `论文撰写/paper/`：当前保留旧 EQD/Carnot SCI 正式源码；新 TES/BESS SCI 尚未开始重写。目录内只放正式源码、图表、参考文献、README 与编译产物。
- `论文撰写/reports/`：给导师或阶段汇报材料。
- `论文撰写/support/`：写作支持、审稿备忘、会议辅助材料、历史审查记录。
- `研究思路/`：临时想法入口；正式结构说明不得再落回这里。

## 4. 非协商规则

1. 同一主题只允许有一份活跃的“latest”结构文档。
2. 只要论文逻辑、章节边界、核心实验链或关键图表清单变化，就必须同步更新 `docs/`。
3. 只要代码入口、`scripts/` 结构、结果目录命名规则或 `docs/` 目录结构变化，也必须同步更新 `项目索引目录.md`。
4. 被替代的结构笔记不要留在活跃目录，统一移动到 `docs/99_archive/`。
5. 稿件源码目录不再存放结构草稿、评审备忘、旧会议归档等支持性材料。

