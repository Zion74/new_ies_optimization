# E0-D-12 BESS—TES 成本证据缺口矩阵

更新时间：2026-07-13
状态：**E0-D-14 已闭合完整 fixed-capacity BESS 生命周期账本；E0-D-15 已把 TES 拆成 12 个正式成本账户并隔离聚合工程锚点。TES 正式候选仍为零，系统级完整 TAC 尚未闭合。**

## 1. 本轮解决的问题

寿命经济核和 `CNY_2024_real` 转换接口已经实现，但“代码能换算”不等于“文献值有资格换算”。本矩阵在数值进入 `LifecycleCostSpec` 前增加一道人工证据门：

1. 同行评审核心证据继续执行 `Energy` 同等级或更高门槛；
2. 官方实验室/政府工程数据单列为 `official_engineering_anchor`，不得冒充同行评审核心证据；
3. 发表年、情景年、数据年和图中结果币值年均不得自动替代原始成本的价格基年；
4. 聚合项目成本只校准 bottom-up ledger，不与被其包含的部件成本叠加；
5. 技术拓扑、温区、规模或市场层级不同的来源只进入方法、结构或敏感性层。

机器可读原表与本轮闭环审计位于：

- `风光火+熔盐储热/research-sessions/2026-07-12-bess-tes-lifecycle-cost-parameters/cost-evidence-gap-matrix.csv`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/formal-cost-candidate-matrix.csv`
- `docs/03_sci_paper/e0_formal_cost_closure_audit.md`

可执行合同与测试位于：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/cost_evidence.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_cost_evidence.py`
- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/sensitivity_cost_anchors.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_sensitivity_cost_anchors.py`
- `docs/03_sci_paper/e0_sensitivity_cost_anchor_contract.md`
- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/formal_bess_costs.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_formal_bess_costs.py`
- `docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md`

`build_e0d10_reference_cost_audit()` 仍执行相同严格条件，但在用户批准关联证据政策后只返回一个 `formal_candidate_id`：`rahman2021_bess_component_package`。该证书证明来源资格，不绕过 `formal_bess_costs.py` 的模型边界接缝。

## 2. 允许用途

| 标签 | 含义 | 是否可直接进入正式 TAC |
|---|---|---|
| `direct_nonprice_parameter` | 寿命、循环、效率等非价格参数，技术边界可对应 | 可，但仍需按模型口径映射 |
| `blocked_pending_price_base` | 原值和分母可读，但价格基年没有被原文明确闭合 | 否 |
| `aggregate_anchor_only` | 整套系统或项目总成本 | 否，只校准 bottom-up 总量 |
| `official_engineering_anchor` | 官方实验室/政府 bottom-up 工程来源 | 不作为 Energy+ 核心论文值；可独立锚定结构和敏感性 |
| `sensitivity_only` | 拓扑、规模、温区或市场层级不同 | 否 |
| `methodology_only` | 只借鉴价格归一化或成本函数方法 | 否 |
| `excluded` | 未通过期刊或来源门槛 | 否 |
| `formal_candidate` | Energy+ 主来源 + 同作者官方扩展材料闭合基年、分母和边界 | 来源层可；完整 TAC 仍须通过模型接缝 |

## 3. 来源判定矩阵

| 来源 | 原始信息 | 价格基年审计 | 技术/分母审计 | 当前用途 | 阻断项 |
|---|---|---|---|---|---|
| Schmidt et al., *Joule* (2019), DOI `10.1016/j.joule.2018.12.008`, Table S4 | Li-ion：678 USD/kW、802 USD/kWh、10 USD/kW-y、3 USD/MWh；RTE 86%、3250 cycles、shelf life 13 y | Table S4 标题和方法称“2015 input parameters”，但结果图统一写 `US$2018`，原文没有给出把表内裸 `$` 唯一解释成哪一价格币值的完整转换链 | 技术级 power/energy 拆分，不等同于本项目 cell/PCS/BoP 拆分 | 寿命/效率为 `direct_nonprice_parameter`；资本成本为 `blocked_pending_price_base` | 资本成本币值基年与成本边界未闭合 |
| Rahman et al., *Applied Energy* (2021), DOI `10.1016/j.apenergy.2020.116343` + UAlberta dissertation DOI `10.7939/r3-jgnr-b764` | Chapter 3 明确对应该文章；2019 USD；battery 216.27 USD/kWh、PCS 206.81 USD/kW、BoP 106.75 USD/kW、两类 FOM、VOM、footprint、contingency 与 replacement 边界 | 原基年、表格和分母阻断已关闭 | 5–100 MW 电站级 BESS；与 Schmidt 13 年/3250 EFC、AC 放电 VOM 共同进入 resolved contract | `formal_candidate` | 来源无阻断；fixed-capacity BESS 子账本已闭合，TES/系统 TAC 仍阻断 |
| Guccione & Guédez, *Energy* (2023), DOI `10.1016/j.energy.2023.128528`, Table 4 | 熔盐电加热器 140 EUR/kWe，脚注为真实报价 | 论文只给出 2021 年平均 USD/EUR=0.84 的换汇口径，未披露报价日期、原始币种或通胀链 | 电加热器组件和 kWe 分母可直接映射 | `blocked_pending_quote_price_year` | 2021 换汇年不能代替报价价格年 |
| Guccione & Guédez, *Energy* (2024), DOI `10.1016/j.energy.2024.133500`, Table 6 / Appendix | 电加热器电气项 15 EUR/kW、热力项 125 EUR/kW，报价来自 SOLARSCO2OL、SHARP-sCO2、Power2Power 项目框架 | 同样只报告 2021 平均换汇率，没有报价价格年 | 组件直接；但温度因子 1 显示为 16 1/°C，与附录对数公式的缩放不清 | `blocked_pending_quote_price_year_and_formula_scaling` | 报价价格年与温度修正公式未闭合 |
| 同一 *Energy* (2024) 论文的 molten-salt TES | 双罐 TES 18–23 EUR/kWhth；23 对应 ΔT=98°C，18 对应 ΔT=275°C | 论文换汇年明确，但底层 NREL/历史成本价格年混合 | 双罐 CSP 显热 TES 与本项目 CHP 三罐双服务拓扑不完全相同 | `official_engineering_sensitivity_anchor` | 非作者 bottom-up；底层工程来源与拓扑边界限制 |
| Ahmadi et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2025.126706`, Table 4 | LiB 189 USD/kWh、PCS 211 USD/kW、BoP 95 USD/kW、construction 96 USD/kWh、replacement 409.59 USD/kWh、FOM 7.59 USD/kW-y、VOM 2.31 USD/MWh | 2030 为技术情景年，不自动等于价格基年 | 分母细，但原文明示来自 PNNL 2030 projection | `official_projection_sensitivity_only` | 非作者 bottom-up，且价格基年未独立闭合 |
| Trevisan et al., *Energy Conversion and Management* (2022), DOI `10.1016/j.enconman.2022.116362`, Table 8 | 变压器 30 EUR/kWel、EH 50 EUR/kWel、罐 30 EUR/kWhth、循环 25 EUR/kWhth、蒸汽发生器 120 EUR/kWth、盐 1 EUR/kg | 分项继承 2011–2022 的混合底层来源，论文未统一归一到一个明确价格年 | 工业 P2H、约 170–450°C；分母可映射，但循环固定单价与 10% CAPEX 口径只能二选一 | `blocked_pending_price_base` | 每项底层价格年、规模和项目附加项未闭合 |
| Klasing et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2024.124524`, Tables 4–5 | EH 100/115 EUR/kWel、steam generator 46/51 EUR/kWth、two-tank 21 EUR/kWhth；系统级 MS/Li-ion 成本 | 压力容器等作者相关式明确为 2023 EUR，但 EH、储罐和蒸汽发生器主要输入仍来自混合年份文献，不能把 2023 或发表年套给全系统 | 煤电改造拓扑接近；21 EUR/kWhth 已含盐、罐、基础及电气/管阀份额 | 分项 `blocked_pending_price_base`；系统总价 `aggregate_anchor_only` | 关键分项共同价格年与包含边界未闭合 |
| Klasing 同文的 closed gas-handling system | 压力容器、压缩机、空冷器和气体电加热器作者相关式 | 明确为 2023 EUR | 服务 620°C 封闭气体管理；当前约 390°C HITEC 三温区拓扑不含该子系统 | `sensitivity_only` | 只有该子系统可称 EUR_2023，不能外推至整张 TES 成本表 |
| Dersch et al., DLR 2021 report 0324253 | 两罐 Solar Salt 整套储热 20–22 EUR/kWhth，中心值 21 | Figure 4 明确 `Base year 2020` | 290–560°C、净热容量分母、两罐 CSP；系统边界包含多个部件和 markups | `official_engineering_anchor` / 聚合校准 | 非 Energy+ 同行评议，且拓扑/盐种不同；不能满足三罐 HITEC 部件账户 |
| Wang et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2025.126876` | HITEC 53/40/7、180/390°C、约 0.9 USD/kg | 价格年未注明 | 材料与温区直接相关；盐价为质量分母 | 物理参数可用；盐价 `sensitivity_only` | HITEC 采购价格年、规模与来源链未闭合 |
| Li et al., *Energy* (2026), DOI `10.1016/j.energy.2026.141711`, Table 5 / p.14 | 罐、泵、换热器工程相关式；改造总投资约 54.19/55.205 million CNY | 公式与总投资均未明确统一价格基年 | 350 MW CHP 级联改造；总投资含多个项目项 | 相关式 `blocked_pending_price_base`；总投资 `aggregate_anchor_only` | 价格年、相关式适用范围及总投资包含边界未闭合 |
| McTigue et al., *Energy Conversion and Management* (2022), DOI `10.1016/j.enconman.2021.115016` | 硝酸盐 0.5–1.3 USD/kg；PTES 安装因子、寿命、O&M 和系统成本 | 明确为 2020 USD | PTES 含压缩机/膨胀机，与既有 CHP 双用途熔盐 TES 不同 | `sensitivity_only` | 拓扑差异，不能作为直接 TES 基线 |
| Vecchi & Sciacovelli, *Applied Energy* (2023), DOI `10.1016/j.apenergy.2022.120628`, §2.2 / Table 3 | 压缩机、透平、换热器、罐、压力容器和介质的 bottom-up 成本函数 | 明确使用 CEPCI 和年均汇率统一为 2020 USD；Table 3 原始函数为 2017 kEUR；初步估算精度约 ±30% | TMES/PTES/TCES 方法，非 HITEC—CHP 改造 | `methodology_only` + `sensitivity_only` | 拓扑、材料和设备边界不同 |
| Comello & Reichelstein, *Nature Communications* (2019), DOI `10.1038/s41467-019-09988-z` | 美国小型住宅 Li-ion：171 USD/kWh、970 USD/kW | 原文明确为 2019 当前美国市场价格 | 住宅规模，且含固定安装成本结构 | `sensitivity_only` | 市场层级和规模与电站级 BESS 不同 |
| NREL 2022 ATB, Utility-Scale Battery Storage | 60 MW、2–10 h Li-ion bottom-up；pack/inverter/BOS/安装/软成本分解；2021 benchmark | 明确为 2020 USD | 电站级 BESS，功率/能量分母清晰；FOM 内含 10、20 年各 20% augmentation | `official_engineering_anchor` | 非 Energy+ 同行评审论文；replacement 不得再与含 augmentation 的 FOM 双计 |
| Yuan et al. (2016) 与 Yu et al. (2018), *Energies* | 不提取参数 | 不适用 | 不适用 | `excluded` | 低于用户指定的 Energy 级期刊门槛 |

## 4. 当前可以确定的建模选择

1. **BESS 正式价格与寿命所有权已锁定。** Rahman 负责 2019 USD 的 battery/PCS/BoP/footprint/FOM/contingency/VOM；Schmidt *Joule* 负责 13 年/3250 EFC，replacement 只由 calendar+AC-throughput 核生成。
2. **NREL 继续只作独立工程敏感性。** 60 MW / 240 MWh、2020 USD 双分母账本不与 Rahman 分项叠加，只用于量级和边界稳健性检查。
3. **TES 主账本继续采用分项结构，但不填伪精确数值。** Trevisan 提供分母和组件结构；Klasing、Li 提供煤电改造聚合锚点；Wang 提供 HITEC 材料与温区；DLR 2020 EUR 只提供两罐 Solar Salt 工程总量锚点。它们不能拼成所谓“同一基年参数表”。
4. **明确价格年的异拓扑来源只进入敏感性。** McTigue 和 Vecchi 的 2020 USD 可以直接换算为 `CNY_2024_real`，但只能形成 PTES/TMES 方法或范围锚点，不能升级为杨凌双用途熔盐 TES 基线。
5. **电加热器出现近正式报价，但不能跨过价格年门槛。** `140 EUR/kWe` 是目前最清晰的单一分母候选；在作者或项目方确认报价价格年前，只能预注册为敏感性中心候选。
6. **高等级论文转引官方数据不会改变证据层级。** Guccione TES 与 Ahmadi BESS 数值即使发表在 *Energy*/*Applied Energy*，仍分别属于 NREL 工程锚点和 PNNL 2030 预测。
7. **正式 TES 门禁按 12 个账户逐项验收。** 高/中温蒸汽充热、对外供热和 power-block retrofit 当前没有满足严格门槛的直接候选；Guccione 回复只能关闭电加热器账户。多来源组合还需要单独批准 `composite_route_approved`。

## 5. 下一门槛

正式 TAC 参数集必须同时完成：

- 已关闭的 BESS 接缝不得回退：cell lifetime/degradation 使用 Schmidt + 唯一退化核，PCS 常数单价限 5–100 MW，VOM 使用 AC 放电侧；
- TES 每个分项的底层价格年、规模、温区和包含边界；
- bottom-up 总额与一个独立煤电改造聚合锚点的误差带校准；
- FOM、augmentation/replacement、残值和退役成本的逐项互斥；
- 所有最终数值及转换链进入不可变参数清单后，再接入 `LifecycleCostSpec`。
- Guccione 报价需补齐日期、原始币种/币值基年，并澄清 2024 温度因子缩放。

在这些条件满足前，E0 仍不通过，E1–E6 批量实验不启动。

E0-D-15 已新增 `formal_tes_costs.py`、聚合锚点隔离和复合证据审批门。E0-D-16/17 新增盈亏平衡内核、实际结果适配和 24 h 探索阈值，但均不提升来源等级或填充 TES 部件价格。当前完整回归为本地 `284 passed in 76.16s`、OpenBayes `284 passed in 21.37s`。E0-D-12 历史机器 CSV 仍为 13 行且 Rahman 为唯一 true；当前代码参考审计为 16 条记录，正式候选仍只有 Rahman BESS。
