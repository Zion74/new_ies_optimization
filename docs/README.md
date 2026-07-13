# 文档中心

更新时间：2026-07-14

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
19. 使用 Rahman BESS 正式来源候选、2019 USD→2024 CNY、三接缝口径或完整 fixed-capacity BESS 生命周期账本时读 `docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md`
20. 使用 NREL BESS 工程敏感性成本、2020 USD→2024 CNY 换算或 FOM/replacement 互斥时读 `docs/03_sci_paper/e0_sensitivity_cost_anchor_contract.md`
21. 涉及三罐、双服务、五路径文献依据或创新边界时读 `docs/03_sci_paper/e0_tes_topology_evidence_contract.md`
22. 涉及 MT→LT 供热夹点、供回水温度来源、HITEC 液态裕量或可交付热量时读 `docs/03_sci_paper/e0_tes_heat_delivery_pinch_contract.md`
23. 涉及 MT 候选、发电—供热显热分割或候选来源身份时读 `docs/03_sci_paper/e0_tes_mt_scenario_contract.md`
24. 涉及杨凌原始数据或 CHP 口径时读 `docs/03_sci_paper/e0_original_source_evidence_audit.md`
25. 对应层级的实验 / 图表 / 代码映射文档
26. 若任务涉及其他模型定义 / 数据口径争议，再读 `docs/辩论确认/` 与相应 research session
27. 需要做清理或迁移时，再读 `docs/90_governance/`

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

