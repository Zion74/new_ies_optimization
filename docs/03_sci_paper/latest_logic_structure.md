# SCI 论文：最新逻辑结构

更新时间：2026-07-14

## 1. 定位

当前主 SCI 已从“EQD + 卡诺电池”调整为：

> **热约束型燃煤 CHP 中锂离子 BESS、双用途熔盐 TES 与混合储能的公平比较、价值机理和技术选择边界。**

建议题目方向：

> *Technology-selection boundaries between lithium-ion batteries and dual-service molten-salt thermal storage in heat-constrained CHP systems*

杨凌 2×350 MW 系统是工程验证对象；论文结论必须由可迁移的归一化边界与全年验证共同支撑，不能只报告一个案例下的弃风率。

## 2. 核心科学问题

1. 如何在不同能量载体、效率、寿命和端口结构下公平比较 BESS 与熔盐 TES？
2. 热负荷造成的 CHP 强迫电出力如何改变储能价值来源？
3. 供热强度、风电接入和公共并网点拥塞如何共同触发 BESS—TES—Hybrid 的排序反转？
4. 时长和相对成本怎样移动该物理边界？
5. 代表周得到的边界能否通过杨凌 2024 年 8784 h 时序验证？

## 3. 论文主张

本文不主张“熔盐普遍优于电池”。主张限定为：

> 在相同热负荷安全和新能源消纳目标下，热致强迫发电与公共并网点拥塞改变了两类储能的边际价值；由此可形成可解释的 BESS—TES—Hybrid 技术选择区域和经济无差异带。

三条贡献线：

1. **机理贡献**：将价值分为电量时移、热供给替代和 CHP 强迫出力释放。
2. **方法贡献**：采用技术特定的功率—能量—寿命成本联合 MILP，在同服务下比较最小年化成本，而不是同 MW/MWh。
3. **工程贡献**：以热约束 × 通道紧张度和时长 × 相对成本两张地图给出选择边界，并用杨凌真实双机全年数据回代。

## 4. 非协商模型边界

- 架构：无储能 / BESS / TES / BESS+TES；
- 求解：确定性容量—运行综合 MILP；
- 主求解器：HiGHS；
- 主公平口径：同供热安全、同弃风上限下的最小年化总成本；
- 对偶口径：同增量年化预算下的最低弃风率；
- BESS：独立充电功率、放电功率和电量容量，计退化、替换、残值与寿命；
- TES：高温/中温库存及电加热、抽汽充热、发电、级联和供热端口分别定容计费；
- CHP：两台机组分别建模，保留启停、爬坡、热电可行域、强迫出力和变煤耗；
- 数据：代表周用于扫描，8784 h 用于关键点验证。

完整模型、实验水平和验收标准见：

- `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
- 当前 E0 实现与阻断项见 `docs/03_sci_paper/e0_validation_status.md`

## 5. 推荐章节结构

1. `Introduction`：问题、质量筛选后的文献空白、贡献边界。
2. `System description and data`：杨凌双机、签约风电、本地光伏、供热义务和公共并网点。
3. `Technology-specific models`：CHP、BESS、双品位熔盐及成本寿命模型。
4. `Fair planning and boundary identification`：综合 MILP、ε-约束、公平口径、选择判据和机理指标。
5. `Experimental design`：代表周、网格、边界加密、全年回代和确定性敏感性。
6. `Results and discussion`：
   - 6.1 模型与杨凌基准验证；
   - 6.2 受控机理实验；
   - 6.3 同服务成本—消纳前沿；
   - 6.4 热约束—通道紧张度选择地图；
   - 6.5 时长—相对成本边界；
   - 6.6 8784 h 验证与确定性稳健性；
   - 6.7 适用范围、工程含义与限制。
7. `Conclusions`：只收束已验证的机制和边界，不外推到调频、黑启动或所有电力系统服务。

## 6. 主图逻辑

论文只保留两张真正承担结论的边界图：

1. **物理适用域**：归一化热约束 × 通道紧张度，按三档风电容量分面；颜色为 No storage / BESS / TES / Hybrid / Indifferent / Infeasible。
2. **经济适用域**：储能时长 × TES/BESS 相对年化成本，按低、中、高物理冲突分面。

其余图用于验证、解释和敏感性，不再堆积孤立的一维扫描。

## 7. 明确排除

本 SCI 不加入：

- 负荷预测；
- 随机或鲁棒优化；
- 蒙特卡洛概率边界；
- 滚动调度 / MPC；
- Agentic 或 LLM 决策支持；
- 德国与松山湖案例。

源荷匹配方法和德国/松山湖结果属于独立成果与硕士论文辅助方法证据，不进入本 SCI 主线。

## 8. 证据与代码状态

- 高质量文献证据包：`风光火+熔盐储热/research-sessions/2026-07-11-tes-ees-regime-boundary/`；
- 现有 `_ch4_*.py` 为探索原型，可复用数据与局部约束，但不足以支撑公平边界结论；
- 当前 `论文撰写/paper/` 仍是旧 EQD/Carnot 稿件源码，不视为新 SCI 正式稿；
- `风光火+熔盐储热/tes_bess_boundary/` 已建立独立 `Pyomo + highspy` 包；E0-D-5–D-18 已锁定 TES 物理/作者筛查、BESS 正式账本、TES 成本门、无罚值 EAC 内核与 336 h 有界求解。E0-D-19 增加严格年度 PCC 外送服务：24 h 同服务燃料 EAC 上限为 12.893 百万元/a，336 h 为 15.031–16.330 百万元/a，主 gap 0.2545%；固定平价结算严格抵消。与 E0-D-18 相比阈值收缩约 73%–77%，证明不同电交付量不能用于公平经济比较；
- E0-D-20 已完成四类非燃料运行成本的项目台账、官方来源和 Energy+ 文献复核，并建立可执行证书门：分时电力结算、碳配额履约、CHP VOM 和 TES VOM 均未获正式证书。尤其是原始台账 H18:H19 虽标为“运维成本”，但两机金额与发电量严格成比例，共同对应 `308.417119 CNY/MWh` 和 `385.107408 gce/kWh`；这只证明燃料重叠风险，不能把 H 列重新认定为燃料，也不能把它叠加为独立 CHP VOM；
- E0-D-21 在不填入任何项目成本估计的前提下，将四个阻断账户作为有符号影子成本区间传播。24 h 合计不利遗漏成本在 `12.893119760 million CNY/a` 达到精确盈亏平衡；336 h 在 `<15.031096496` 时燃料空间稳健为正、`15.031096496–16.330188393` 时包含零而不确定、`>16.330188393 million CNY/a` 时稳健为负。四个单账户阈值是“其他账户为零”的反事实风险预算，不能相加，也不是实际 VOM、碳成本或结算损失；
- E0-D-22 重新执行同一 D19 服务合同并导出两架构逐时 PCC。24 h/336 h 年化重新分配外送电量为 `26,010.174918/31,228.008145 MWh`，占共同交付 `0.558528%/0.731355%`；固定平价结算差为 0。对当前 HiGHS 选择轨迹，任意有界价格序列满足 `|ΔR|≤price_spread×redistributed_MWh`，因此 D21 结算单账户临界价格跨度为 24 h 的 `495.695235 CNY/MWh` 和 336 h 的 `481.333821–522.934038 CNY/MWh`。这些值不是杨凌实际价格，且 D22 本身尚未排除连续替代最优调度；
- E0-D-23 建立两架构联合 MILP；E0-D-26 将年度成本/弃电 cap 无量纲化，使用 `1e-9` 严格可行性容差，分开 D19 条件整数面与全部整数模式，并要求全局 incumbent 支配已知证人。E0-D-27 又用不含符号二元的固定支持方向产生可行 L1，并用正负差值分解取代 D23 的 `2M` 绝对值上界。24 h 全局严格包络修正为 `26,010.171143–26,010.174929 MWh/a`，D22 选择值仍几乎位于最大端。E0-D-28 随后用 `negated` 与 `alternating` 两个预注册单步种子筛查其他方向；两者均在时限结束、未达固定点，返回轨迹 L1 均未超过 `36,382.462799 MWh/a`。E0-D-29 保持全部主整数与符号二元开放，增加逐时外送/余量有效不等式及正负年化质量守恒，将 336 h 上界收紧到 `845,052.030831 MWh/a`。E0-D-30 再以不含跨时段状态的静态物理外松弛证明逐时 PCC 可达区间，用同年度 PCC 服务传播区间，并增加每时段 6 条区间感知符号不等式。336 h 正向符号宽度平均降低 `33.3107%`，global dual 降至 `777,141.368858 MWh/a`，较 D29 改善 `8.0363%`，较 D26 累计改善 `42.9474%`。E0-D-31 随后保留完整 CHP/TES 跨时段、年度服务与准入约束，放松全部整数域并完成 24/336 h 的 96/1344 个 PCC OBBT LP；24 h 正/负宽度相对 D30 再降 `51.9066%/41.1792%` 且精确门保持，但 336 h 仅降 `0.0329%/0.0864%`，低于全局 probe 资源门槛，因此不生成新 dual。D28 不能写成其他正交域排除，D29/D30 也不能写成数值闭合，D31 只能写成 scalar OBBT 负筛查；336 h 仍为 `[36,382.462799,777,141.368858] MWh/a` 宽区间，相对 gap `20.36033`；
- E0-D-24 将 D15 的 12 个 TES 所有权账户与 D20 的 4 个非燃料运行账户统一为完整 TAC 证据路线。机器审计为 `0/16` 严格正式账户：TES 中 8 个“直接候选不完整”、4 个“无直接候选”；4 个运行账户全部要求杨凌项目原始记录。Zhang et al. *Energy* 2024 满足期刊等级，且 *Energy* 官方页当前 IF 为 `9.4`，但可访问记录只支持煤电熔盐改造的聚合技术/成本锚点；NREL/DLR/DOE 报告继续停留在官方工程层，禁止期刊转引洗白。`layered_route_approved=false`，且测试证明审批本身不能生成缺失证据；
- E0-D-25 将四类项目原始记录冻结为 51 项接收字段、四账户覆盖表和空白提交模板，并用 `confidential_local_only`、`metadata_only` / `do_not_export` 隔离提交值与本地受限资料。当前电力结算、碳履约和 TES VOM 为 `missing`，CHP VOM 仅覆盖 6/14 项，故 `ready_account_count=0/4`；接收完整仍须回到 D20/D24 正式复核，不能直接生成 TAC；
- 原始证据审计确认杨凌表内没有供回水温度、抽汽温压或可直接识别三罐逐时损失/泵耗的设备参数。MT 继续使用 0.25/0.50/0.75 作者显热分割；E0-D-9B-1/2 数值均登记为作者敏感性。Guccione `140 EUR/kWe` 仍缺报价价格年，且罐、循环、三条换热/蒸汽发生路径、power-block retrofit、项目附加费和寿命项也未闭合；DLR `20–22 EUR_2020/kWh_th-net` 仅为两罐 Solar Salt 工程聚合锚点。本地 `price_sell/price_buy` 是脚本生成情景，不是杨凌结算；总排放乘碳价也不是配额履约成本。TES 正式来源、完整 TAC、endogenous capacity、结构化代表周和 336 h 替代调度包络闭合仍未完成；E0-D-19–D-31 仍不能形成技术赢家，因此不得进入 E1 或批量边界实验。合同见 `e0_tes_break_even_contract.md`、`e0_tes_break_even_adapter_and_exploration_contract.md`、`e0_tes_two_window_performance_and_interval_contract.md`、`e0_same_pcc_service_and_operating_cost_boundary_contract.md`、`e0_operating_cost_evidence_readiness_contract.md`、`e0_shadow_cost_robustness_contract.md`、`e0_pcc_settlement_exposure_contract.md`、`e0_alternative_dispatch_settlement_envelope_contract.md`、`e0_d26_numerical_certification_contract.md`、`e0_d27_direction_generation_and_sign_reformulation_contract.md`、`e0_d28_multistart_direction_screening_contract.md`、`e0_d29_export_linked_bound_tightening_contract.md`、`e0_d30_physics_service_bound_tightening_contract.md`、`e0_d31_intertemporal_relaxation_obbt_contract.md`、`e0_formal_tac_evidence_route_contract.md` 与 `e0_project_primary_evidence_intake_contract.md`。

## 9. 与旧 SCI 文档的关系

`docs/03_sci_paper/` 中 2026-04 的 EQD/Carnot 审稿、重设计、出图和服务器清单保留为独立旧稿的历史资产，但不再定义当前主 SCI。当前只以本文件、模型实验设计、实验映射和图表计划为权威。
