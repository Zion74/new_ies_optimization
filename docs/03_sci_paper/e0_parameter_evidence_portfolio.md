# E0-D-12 BESS—熔盐 TES 参数、温区、拓扑、夹点、MT 与成本证据

更新时间：2026-07-13
状态：证据组合 v1.2。E0-D-14 已把 Rahman 价格、Schmidt 非价格寿命、AC 放电侧 VOM 和 5–100 MW PCS 口径闭合为完整 fixed-capacity BESS 生命周期账本。E0-D-15 已把 TES 拆成 12 个正式成本账户，登记 DLR 2020 EUR 两罐工程聚合锚点并实现复合证据审批门；TES 正式候选仍为零，系统级完整 TAC 尚未闭合。

## 1. 目的与非结论

本阶段为 BESS、双用途熔盐 TES 与 Hybrid 的公平全寿命比较建立参数证据合同。它回答“每个成本和寿命参数来自哪里、如何换算、是否重复计费”，不提前回答哪种技术更优。

详细逐表提取、论文筛选和排除记录位于：

- `风光火+熔盐储热/research-sessions/2026-07-12-bess-tes-lifecycle-cost-parameters/parameter-evidence-matrix.md`
- `风光火+熔盐储热/research-sessions/2026-07-12-bess-tes-lifecycle-cost-parameters/cost-evidence-gap-matrix.csv`
- `风光火+熔盐储热/research-sessions/2026-07-12-bess-tes-lifecycle-cost-parameters/papers-reviewed.json`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/`
- `docs/03_sci_paper/e0_cost_evidence_gap_matrix.md`
- `docs/03_sci_paper/e0_sensitivity_cost_anchor_contract.md`
- `docs/03_sci_paper/e0_formal_cost_closure_audit.md`

## 2. 质量门槛

核心参数只接受 `Energy` 同等级或更高的同行评审论文。出版社页面在 2026-07-13 显示：`Energy` IF 9.4 / CiteScore 16.5、`Applied Energy` IF 11.0 / CiteScore 20.1、`Energy Conversion and Management` IF 10.9 / CiteScore 19.8；`Joule` 作为 Cell Press 综合能源期刊进入更高层级。`Energies`、普通会议、`Energy Procedia` 等不进入核心参数层。

核心证据层当前包括：

- `Joule`：Schmidt et al. (2019)，BESS 系统级成本、寿命和退化；
- `Energy`：Bahloul et al. (2022) 只用于 BESS 成本结构与转录风险审计，其 Table 9 数值不进入核心基线；Guccione & Guédez (2023/2024) 提供真实电加热器报价及双罐熔盐 TES 工程范围；Li et al. (2026) 用于煤电熔盐改造分项公式与聚合校准；
- `Applied Energy`：Rahman et al. (2021) 与同作者官方博士论文 Chapter 3 组成已批准的 BESS 正式来源候选；Klasing et al. (2025)，煤电熔盐改造；Wang et al. (2025)，盐成本与动态损失/辅机；He et al. (2020)，BESS 经济寿命敏感性；Ahmadi et al. (2025) 的 BESS 表只作为 PNNL 2030 预测敏感性；
- `Energy Conversion and Management`：Trevisan et al. (2022)，工业 P2H—熔盐 TES 分项成本和寿命；McTigue et al. (2022)，仅作 PTES 寿命、O&M 和安装因子敏感性。
- `Applied Energy`：Vecchi & Sciacovelli (2023) 只提供明确的 2020 USD 归一化方法和 TMES 成本函数敏感性，不作为 HITEC—CHP 直接基线；
- `Nature Communications`：Comello & Reichelstein (2019) 的 2019 美国住宅 Li-ion 价格只作市场层级敏感性；
- `NREL 2022 ATB`：单列为 `official_engineering_anchor`，用于电站级 BESS bottom-up 结构和价格年明确的工程锚定，不冒充 Energy+ 同行评审核心论文。

Yuan et al. (2016) 与 Yu et al. (2018) 的 `Energies` 论文已按用户门槛显式排除。

## 3. 证据分层

| 层级 | 含义 | 当前使用规则 |
|---|---|---|
| `direct_candidate` | 物理边界和容量口径可直接对应模型 | 仍需统一币种、价格基年和规模后方可入正式参数集 |
| `conversion_required` | 原值可靠，但容量口径、温区或价格年需要换算 | 保留原值与换算链，不允许只记录换算后结果 |
| `aggregate_anchor_only` | 整套系统或项目总成本 | 只校准分项 ledger 总量，不与其内部件成本叠加 |
| `sensitivity_only` | 拓扑不同或来自论文假设范围 | 仅进入低—中—高敏感性，不决定基线 |
| `methodology_only` | 价格归一化或工程成本函数透明，但技术边界不同 | 只借鉴方法，不迁移数值 |
| `official_engineering_anchor` | 官方实验室/政府 bottom-up 工程数据 | 与 Energy+ 核心论文分层保存，只锚定结构和敏感性 |
| `blocked_pending_price_base` | 原值可读但成本币值基年未闭合 | 不允许创建正式 `LifecycleCostSpec` |
| `blocked_pending_quote_price_year` | 论文明确说明真实报价，但未披露报价日期/原始币值年 | 只预注册为近正式敏感性候选，不执行币值换算 |
| `official_projection_sensitivity_only` | 高等级论文直接采用官方未来情景预测 | 保留原情景与分母，只作敏感性，不改写成作者当前成本 |
| `formal_candidate` | Energy+ 同行评审主来源与透明披露的同作者官方扩展材料共同闭合数值、基年和边界 | 可颁发来源层证书；仍须通过模型边界和防双计接缝 |
| `excluded` | 未通过期刊或证据门槛 | 不进入模型、表格或正文定量结论 |

## 4. 当前可用结论

1. BESS 已能建立 `cells & pack / PCS / BoP / construction / FOM` 的候选成本 ledger 结构，并以系统级总成本、日历寿命、EFC/DoD 和退化范围校准；但 Bahloul Table 9 数值追溯至 PNNL-28866 并经 `Energies` 二次整理，只作交叉检查，不进入核心基线。
2. TES 已能建立 `electric heater / tanks / salt / circulation / salt-to-steam generator / project adders / FOM` 的候选 ledger。
3. 当前多数 TES 成本及部分 BESS 输入没有论文内明确的统一价格基年，必须先完成币值转换审计；不得因为论文年份或表题中的 input year 已知而把它自动当成价格基年。
4. 聚合成本与分项成本只能二选一用于一个计算层：聚合成本做校准，分项成本做主 ledger。
5. replacement、FOM、退役成本和残值必须逐部件互斥；论文未报告残值时，只能把零残值写成模型假设。
6. `TESCapacityLedger` 已将盐质量、完整显热库存、三罐容量和五端口转换为唯一 `kg / kWh_th / kW_el / kW_th` 分母；部件文献温区未覆盖实际 LT→MT、MT→HT 或 LT→HT 温段时，正式 portfolio 绑定会被拒绝。
7. Energy 2025 三罐论文直接支持同一批盐的 `LT→MT→HT` 两阶段充热；Energy 2024 CHP 论文直接支持同一熔盐放热蒸汽在低压缸和供热网之间分配。当前超结构因此具有 Energy 级模块证据，但没有单篇论文完整验证。
8. 当前 `MT→LT` 专用于供热的品位分配属于本文提出的级联扩展，而不是文献事实；正式用例必须显式披露，并通过热网温度和夹点验证。
9. E0-D-7 原始表复核确认杨凌资料不含供回水温度或抽汽温压；`2353.6 kJ/kg` 是无温压/来源说明的流量换算常数，不能反推 MT。
10. Li et al. (*Energy*, 2026) 的 `120/70 °C` 仅注册为核心参考情景。显式 15 K 端差给出的 `T_MT_min=135 °C` 低于 HITEC 候选 `LT=180 °C`，故可证明供热品位可行但不能唯一识别 MT。
11. E0-D-8 定义 `φ_h=(MT-LT)/(HT-LT)`，并把 `φ_h=0.25/0.50/0.75` 注册为作者敏感性，对应 HITEC 180/390 °C 下的 MT=232.5/285/337.5 °C。端点来自 Applied Energy，三个 MT 不属于任何论文或杨凌现场直接值。
12. Trevisan 的库存/表面积相关 UA 损失、Klasing 的 99%/日循环系统锚点和 Wang 的动态泵耗/RTE 不能混写为同一个固定每小时损失率；损失与辅机单列 E0-D-9。
13. E0-D-10 逐来源审计确认：Schmidt 的非价格寿命/效率可用，但资本成本不能在“2015 input”与“US$2018 output”之间自行选择价格基年；Trevisan、Klasing、Wang、Li 的直接成本均仍有价格年或包含边界缺口。
14. 明确价格年的 McTigue、Vecchi、Comello 和 NREL 数据分别受 PTES/TMES 拓扑、住宅规模或非同行评审证据层限制，只能进入敏感性、方法或官方工程锚点，不能被拼成正式基线。
15. E0-D-11 已把 NREL ATB 60 MW / 240 MWh、2020 USD 工程锚点落成双分母可执行台账：2021 能量项 309.3045 USD/kWh_usable、功率项 238.2392 USD/kW，4 h 总额 1475.4572 USD/kW；2.5% FOM 已含第 10/20 年各 20% augmentation，故与独立 replacement ledger 互斥。该对象固定 `formal_baseline_eligible=False`。
16. NREL 修订版工作簿的 RTE=0.85，而网页文字为 0.86；本阶段只认证成本台账，RTE 被显式排除，不能借成本锚点绕过性能参数证据冲突。
17. E0-D-12 找到 *Energy* 2023 的熔盐电加热器真实报价 `140 EUR/kWe`；*Energy* 2024 又拆出 `15 EUR/kW` 电气项与 `125 EUR/kW` 热力项，并将报价关联到三个欧盟项目框架。两文只披露 2021 年平均换汇率，没有披露报价价格年，因此均不能直接换算到 2024 CNY。
18. *Energy* 2024 的双罐熔盐 TES `18–23 EUR/kWh_th` 分别对应约 275°C 与 98°C 温差，但底层来自 NREL/历史工程文献，不属于作者 bottom-up；只能校验 TES 能量成本量级，不能替代本项目三罐双服务 ledger。
19. Rahman et al. (*Applied Energy*, 2021) 与其 University of Alberta 官方博士论文 Chapter 3 已闭合 2019 USD、分项表、精确分母、replacement/FOM 与退役排除边界；用户批准后成为唯一 `formal_candidate=true`。Ahmadi et al. (*Applied Energy*, 2025) 仍因 PNNL 2030 projections 只进敏感性。
20. E0-D-14 已直接映射 PCS、BoP、围护基础、battery/PCS FOM 与 contingency，并预注册三接缝：Rahman cycle-only replacement 不进入正式基线，Schmidt 13 年/3250 EFC 驱动唯一 calendar+throughput 核；VOM 按 AC 放电；PCS 常数单价限 5–100 MW。来源层合格与 resolved fixed-capacity contract 仍是两个不同状态。
21. E0-D-15 追溯 DLR 2021 原报告后确认 Klasing 两罐中心值为 `21 EUR_2020/kWh_th-net`、范围 20–22，但该值仍是两罐 Solar Salt 官方工程聚合锚点。`formal_tes_costs.py` 要求 12 个账户逐项闭合，并拒绝 Klasing/Li/DLR 聚合锚点满足部件账户；Guccione 回复也只能关闭电加热器一项。

### E0-D-8 物理候选与禁用替代

- 首选物理候选为 Wang et al. (Applied Energy, 2025) 煤电案例中的 HITEC 53 wt% KNO3 / 40 wt% NaNO2 / 7 wt% NaNO3，`LT=180 °C`、`HT=390 °C`；
- `MT` 现场值尚未锁定；E0-D-8 的 232.5/285/337.5 °C 仅为归一化焓分配作者敏感性，不得写成论文或杨凌基准值；
- McTigue et al. 的硝酸盐 `0.5–1.3 USD_2020/kg` 只作盐价敏感性，不能冒充 HITEC 正式基线；
- Wang et al. 的 HITEC 约 `0.9 USD/kg` 因价格年不明只作交叉检查；
- Solar salt 的高熔点温区不能与 `LT=180 °C` 的 HITEC 基线混搭。

完整拓扑证据、InstSci/Elsevier 访问审计和剩余门槛见 `e0_tes_topology_evidence_contract.md`；夹点、材料温区与可交付热量接口见 `e0_tes_heat_delivery_pinch_contract.md`。

## 5. `power block` 成本口径修正

现有论文证据表明，煤电改造型 TES 通常复用既有汽轮机，新增的是盐—水/蒸汽发生与回送系统。因此在 E0-D-3 正式入模前，现有 `power block` 资产应完成以下分类审计：

- `salt_to_steam_generator / discharge_heat_exchanger`：新增盐—水/蒸汽换热系统；
- `existing_turbine_reuse`：既有汽轮机，不重复计初始资本成本；
- `new_power_block`：只在新增独立发电子系统的敏感性架构中启用。

代码已把三类角色固化到 `LifecycleAssetClass`：复用标记禁止初始/更换资本成本；一旦启用发电回路分类，portfolio 必须恰有一个盐—蒸汽发生系统，并在复用汽轮机与新增 power block 之间二选一；TES 电输出容量为正时，`E0CCase` 拒绝未分类的年度经济输入，也拒绝分类角色装机量为零的占位输入。该合同只防止边界错误，不会自动填入正式成本数值。

## 6. 统一价格基年合同

正式年度经济口径固定为 **2024 年不变价人民币（`CNY_2024_real`）**，与杨凌 2024 年 8784 h 运行边界和实折现率一致。源币种 (s)、源价格年 (y) 的换算为：

\[
C_{\mathrm{CNY},2024}=C_{s,y}\frac{I_s(2024)}{I_s(y)}FX^{2024}_{\mathrm{CNY}/s}.
\]

`PriceBasisConversion` 必须显式提供源/目标 ISO 4217 币种、源/目标价格年、同一指数序列的两个指数值、目标币/源币汇率和两条序列标识；`convert_lifecycle_cost_spec` 同时转换初始成本、更换成本和 FOM，并返回不可伪造的 `LifecycleCostConversion` 审计对象。`$` 等歧义币种被拒绝，同币种转换的汇率因子必须为 1；`AnnualEconomicsSpec` 只接受 2024 CNY 成本。

E0-D-4 已在 `风光火+熔盐储热/数据采集/e0d4_price_basis_2024/` 固化 BLS CPI-U、Eurostat EA20 HICP、国家统计局 CPI 链、ECB EUR/CNY 和国家统计局 USD/CNY 的最小快照。`load_price_basis_snapshot()` 通过 manifest 校验 snapshot 与逐源 SHA-256，再由 `OfficialPriceBasisSnapshot.to_conversion()` 生成唯一转换对象。当前登记因子包括：

- `EUR_2022→CNY_2024 = 8.404041836429`；
- `USD_2020→CNY_2024 = 8.631777441067`；
- `USD_2018→CNY_2024 = 8.896601653080`；
- `CNY_2020→CNY_2024 = 1.033300836720`。

BLS 官方 PDF 可由网页证据通道读取，但本机与 OpenBayes 的 BLS TLS/WAF 均阻止原 PDF 归档，因此仓库保存带官方 URL 的规范提取 JSON 并在 manifest 中哈希；其他 Eurostat、ECB 与国家统计局原始响应均已归档。CPI/HICP 是明确声明的一般价格代理，不冒充设备价格指数，后续需以设备价格指数敏感性检查其影响。缺失价格年时仍不得用发表年、数据年或预测年替代；无量纲 `%CAPEX/y`、replacement fraction 和 installation factor 不单独做币值转换，只作用于已经完成转换的成本基数。

E0-D-11 使用上述官方快照把 NREL 60 MW / 240 MWh 工程锚点换算为 `764,149,077.34031 CNY_2024_real` 初始资本成本和 `19,103,726.933508 CNY_2024_real/a` 源 FOM。该换算只服务敏感性和量级审计，不会把 NREL 官方数据升级为 Energy+ 同行评审正式参数。

## 7. 正式参数集验收门槛

- 每个资产都有原值、单位、币种、价格基年、容量基准、适用温区和规模；
- 所有换算保留汇率、通胀指数、基年和公式；
- BESS bottom-up 表的异常 variable O&M 已追溯至 PNNL 吞吐量口径并永久排除；**已完成**；
- TES 盐量、完整储热容量、三罐和五端口容量已与模型变量闭合；**已完成**；泵功和换热面积仍待闭合；
- FOM、replacement、decommission 和 residual value 无双计；**NREL 工程敏感性锚点的 FOM/replacement 互斥已完成，正式 Energy+ portfolio 待完成**；
- replacement cost/fraction、PCS/BoP 独立寿命及 residual value 若无合格文献值，必须显式登记为待证假设和敏感性，不能伪装为文献参数；
- 分项 ledger 与至少一个独立聚合项目成本完成总量校准；
- 逐来源的价格年、容量分母、技术边界和允许用途缺口矩阵；**E0-D-13 更新后 13 个候选中 Rahman BESS 为唯一 true**；
- 成本来源资格的可执行认证门、唯一 Rahman 正式候选及降级拒绝回归；**本地已完成，远端待同步**；
- TES 12 账户就绪度、聚合锚点隔离和复合证据审批门；**本地已完成，账户仍全部阻断，远端待同步**；
- NREL/OEDI 原工作簿、精确单元格提取、manifest、功率—可用能量双分母台账、2024 CNY 转换及 augmentation 防双计；**已完成，本地/OpenBayes 均 258 项通过**；
- `power block` 分类修正有测试保护；**已完成**；
- 价格转换机制、ISO 币种和 2024 CNY 年度口径有独立合成金标准；**已完成**；
- 官方快照、逐源哈希、重复序列和篡改拒绝有独立金标准；**已完成**；
- 低—中—高三档参数均能通过年度现金流审计。

上述剩余门槛未全部满足前，E0 保持“完整 fixed-capacity BESS 生命周期账本已闭合，但全部 TES 正式成本与系统级 TAC 未闭合”，E1 与批量边界扫描不启动。E0-D-16–D-23 增加了探索性全系统 TES EAC 上限、两窗口区间、同 PCC 服务、缺证成本风险预算以及逐时/替代调度结算暴露；E0-D-24 将证据缺口统一为 `0/16` 严格账户，但仍不把阈值写回正式参数表。当前完整回归为本地 `322 passed in 54.69s`、OpenBayes `322 passed in 26.55s`；各阶段 canonical 由对应 manifest 跨平台锁定。
