# 最新研究架构

更新时间：2026-07-14

## 1. 当前统一主线

当前硕士论文不再采用“EQD → 卡诺电池 → 负荷预测”的旧三层结构，而改为：

> **以杨凌热约束型风—光—火系统为统一对象，先建立数据与物理模型，再用源荷匹配方法识别灵活性需求，进一步给出 BESS—熔盐 TES—Hybrid 的公平技术选择边界，最后用可审计的 Agentic 工作流把确定性模型转化为规划决策支持。**

研究递进是：

```text
统一对象与物理口径
→ 何时出现、多强的灵活性服务需求
→ 应由 BESS、TES 还是 Hybrid 提供
→ 如何把模型可靠地用于场景化决策支持
```

## 2. 论文载体分工

### 2.1 会议成果

当前会议成果彼此独立，不再强行组成大论文主线：

1. **源荷匹配会议稿**：保留 IEMI / EQD 方法的概念验证，可作为硕士论文第 3 章的方法来源；德国和松山湖只作辅助证据。
2. **负荷预测会议稿**：作为独立会议论文保留，不再承担硕士论文主章节，也不进入 TES/BESS SCI。
3. `风光火+熔盐储热/IEEE-conference-proceeding-Latex/` 中的旧同规格储能比较是早期探索稿，其数值不能自动继承为新 SCI 结论。

### 2.2 当前主 SCI

SCI 只研究：

- 杨凌 2×350 MW 抽凝 CHP；
- 签约风电、本地 PV、固定供热义务和公共并网点；
- 无储能 / BESS / 双用途熔盐 TES / Hybrid；
- 同服务 ε-约束下的最小年化成本；
- 热约束—通道紧张度和时长—相对成本选择边界；
- 代表周扫描与 8784 h 验证。

SCI 不加入负荷预测、随机优化、滚动调度或 Agentic。

### 2.3 硕士论文

硕士论文以杨凌为唯一主案例：

- **第 2 章**：系统、数据、统一模型与验证；
- **第 3 章**：基于源荷匹配的新能源接入规划与灵活性服务需求识别；
- **第 4 章**：BESS—熔盐 TES 的价值机理与适用边界，即主 SCI；
- **第 5 章**：可验证的 Agentic 规划决策支持；
- **第 6 章**：结论与展望。

第 3 章回答“在哪种规划状态下、何时以及多强地需要灵活性服务”，输出风光规模、ε、冲突时段和服务需求指标；第 4 章才联合优化“由哪一种储能、配多少功率/容量来提供”，第 5 章回答“如何安全、可追溯地调用前两章模型”。

## 3. 源荷匹配的保留方式

源荷匹配保留为第 3 章的方法，不再要求德国或松山湖成为大论文主题。推荐做法：

- 用 IEMI / EQD 或其简化指标识别杨凌的风—光—热致强迫发电失配；
- 输出风光接入规模、灵活性需求和关键冲突时段；
- 把这些典型规划状态传递给第 4 章；
- 德国 / 松山湖只用于方法迁移或放入附录。

因此，原 `run.py`、`cchp_gaproblem.py` 和德国/松山湖结果仍是研究资产，但不再控制当前 SCI 和硕士论文主线。

## 4. 负荷预测的处理

- 负荷预测不再写入硕士论文主线；
- 不再新建“预测—日前—实时”第 4 章；
- 已有预测工作可作为独立会议论文或展望；
- 当前 SCI 与硕士论文核心模型使用已知历史时序和确定性情景。

这避免为了章节完整性引入一个与核心科学问题弱耦合、且投稿竞争激烈的预测模块。

## 5. Agentic 的正确位置

Agentic 只属于硕士论文第 5 章的**可信决策支持层**：

```text
自然语言场景
→ 结构化 Scenario Schema
→ 单位、范围和完整性校验
→ 调用第 3 / 4 章确定性优化器
→ 独立物理与证据审计
→ 可追溯建议和报告
→ 人工确认
```

Agent 不直接生成容量答案，不替代 MILP，不擅自改变物理参数。只有在参数抽取、非法输入识别、调用成功率、结果复现、物理违规漏检和无证据建议率上完成对照实验，才可作为论文内容；否则降级为工具演示或展望。

## 6. 当前研究状态

- **文献与科学问题**：已完成高质量文献门槛筛选，当前主空白可辩护；
- **杨凌数据**：E0-B 正式构建已完成；保留 52,707 行源证据、52,704 点 canonical 网格和 8,784 h net/forward/zero-sensitivity 三口径。单位、老城单点哨兵、29 个东方双负、49 个仅流量为负、2,050 个居民负值与 5/85/226 三段全零均进入结构化质量合同；
- **机制原型**：已有 `_ch4_*` MILP、储能对照、敏感性和典型期脚本；
- **公平主模型**：E0-C fixed-capacity 四架构统一调度、真实热需求桥接及 E0-D-1–D-20 已闭合相应物理、寿命经济、证据资格、同 PCC 服务和四类非燃料成本证据门。E0-D-21 不猜项目价格，而将 D19 燃料空间与 D20 缺口连接成来源无关的影子成本稳健性边界；D22 导出同服务逐时 PCC；D23 建立联合双向极值，D26 以无量纲 cap、`1e-9` 严格容差和条件面证人重新发证，D27 再用固定支持方向与正负差值分解修正最大端：24 h 全局严格包络为 `26,010.171143–26,010.174929 MWh/a`。D28 的 `negated`/`alternating` 两个预注册种子均未改善 336 h 的 `36,382.462799 MWh/a` 可行下界且未达固定点；D29 用外送/余量与年化质量守恒将 336 h 上界收紧到 `845,052.030831 MWh/a`。D30 随后用 CHP/热平衡/TES 端口和辅机上界构造逐时 PCC 物理外包络，并经同年度 PCC 服务传播生成区间感知符号不等式；336 h 正向符号宽度平均收紧 `33.3107%`，最大严格区间再收紧为 `[36,382.462799,777,141.368858] MWh/a`，较 D29 改善 `8.0363%`，较 D26 累计改善 `42.9474%`，但仍未闭合。D31 保留完整单架构跨时段约束并放松全部整数域，完成 24/336 h 共 1440 个逐变量 OBBT LP；24 h 相对 D30 的正/负宽度再降 `51.9066%/41.1792%` 且精确门不变，但 336 h 仅降 `0.0329%/0.0864%`，低于全局求解资源门槛，因此未启动新 336 h probe，最新全局界仍为 D30。D24 将 12 个 TES 与 4 个非燃料账户合并为完整 TAC 证据路线：严格正式账户 `0/16`。D25 把四个项目运行账户转成 51 项可执行取证字段和隐私隔离模板，当前三账户缺失、CHP 仅 6/14，仍为 `0/4` 可进入正式复核。Energy 论文和 NREL/DLR/DOE 工程报告已分层登记，公开或本地可比工程资料均不能替代杨凌项目账本。固定平价严格抵消，但现有结果仍不是实际 VOM、碳成本、结算损失、全年 TAC 或技术赢家。TES 正式成本、项目账户、336 h 包络闭合、内生容量和结构化代表周继续阻断 E1–E6；
- **服务器**：OpenBayes 60 核 / 约 100 GB 内存已连通；E0-D-23 双窗口、D24 证据路线、D25 项目取证合同、D26–D31 数值证书与筛查均在远端执行，正式求解仅使用 HiGHS；
- **Agentic**：只完成研究定位，尚未实现与评价。

## 7. 权威入口

- SCI 逻辑：`docs/03_sci_paper/latest_logic_structure.md`
- SCI 模型实验：`docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
- E0 实现状态：`docs/03_sci_paper/e0_validation_status.md`
- E0 正式成本闭环：`docs/03_sci_paper/e0_formal_cost_closure_audit.md`
- TES 正式成本就绪度门禁：`docs/03_sci_paper/e0_tes_formal_cost_readiness_contract.md`
- TES 价格无关价值与盈亏平衡合同：`docs/03_sci_paper/e0_tes_break_even_contract.md`
- 年度结果适配与 24 h/两周探索状态：`docs/03_sci_paper/e0_tes_break_even_adapter_and_exploration_contract.md`
- E0 Rahman BESS 关联证据合同：`docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md`
- E0 同 PCC 服务与运行成本证据边界：`docs/03_sci_paper/e0_same_pcc_service_and_operating_cost_boundary_contract.md`
- E0 非燃料运行成本证据就绪度：`docs/03_sci_paper/e0_operating_cost_evidence_readiness_contract.md`
- E0 非燃料影子成本稳健性：`docs/03_sci_paper/e0_shadow_cost_robustness_contract.md`
- E0 逐时 PCC 与结算价差暴露：`docs/03_sci_paper/e0_pcc_settlement_exposure_contract.md`
- E0 替代可接受调度的结算暴露包络：`docs/03_sci_paper/e0_alternative_dispatch_settlement_envelope_contract.md`
- E0 完整 TAC 16 账户证据路线：`docs/03_sci_paper/e0_formal_tac_evidence_route_contract.md`
- E0 项目原始证据接收与隐私隔离：`docs/03_sci_paper/e0_project_primary_evidence_intake_contract.md`
- 硕士论文逻辑：`docs/04_master_thesis/latest_logic_structure.md`
- 第 4 章计划：`docs/04_master_thesis/chapter4_tes_ees_regime_boundary_plan.md`
- 第 5 章计划：`docs/04_master_thesis/chapter5_agentic_decision_support_plan.md`
- 文献证据包：`风光火+熔盐储热/research-sessions/2026-07-11-tes-ees-regime-boundary/`；成本闭环证据：`风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/`；BESS 三接缝闭合记录：`风光火+熔盐储热/research-sessions/2026-07-13-e0d14-bess-join-closure/`；TES 正式成本复核：`风光火+熔盐储热/research-sessions/2026-07-13-e0d15-tes-formal-cost-closure/`；同 PCC 服务边界：`风光火+熔盐储热/research-sessions/2026-07-13-e0d19-operating-cost-boundary/`；非燃料成本证据门控：`风光火+熔盐储热/research-sessions/2026-07-14-e0d20-operating-cost-evidence/`；影子成本稳健性：`风光火+熔盐储热/research-sessions/2026-07-14-e0d21-shadow-cost-robustness/`；逐时 PCC 结算暴露：`风光火+熔盐储热/research-sessions/2026-07-14-e0d22-pcc-settlement-exposure/`；替代调度包络：`风光火+熔盐储热/research-sessions/2026-07-14-e0d23-alternative-dispatch-envelope/`；完整 TAC 证据路线：`风光火+熔盐储热/research-sessions/2026-07-14-e0d24-formal-tac-evidence-route/`；项目原始证据接收：`风光火+熔盐储热/research-sessions/2026-07-14-e0d25-project-primary-evidence-intake/`
