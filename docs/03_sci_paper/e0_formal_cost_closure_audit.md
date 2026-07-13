# E0-D-12 正式成本证据闭环审计

更新时间：2026-07-13
状态：**用户已批准 Rahman 关联证据政策；BESS 来源证书与三个 fixed-capacity 模型接缝均已闭合。E0-D-15 已将 TES 正式成本拆成 12 个账户并建立可执行门禁，但账户仍全部阻断，系统级完整 TAC 与 E0 总门槛继续阻断。**

## 1. 审计问题

E0-D-12 不再问“能否找到一个看起来合理的单价”，而是检查是否存在一组能够直接支撑 BESS—熔盐 TES 公平 TAC 比较的证据组合。正式数值必须同时满足：

1. `Energy` 同等级或更高同行评审；
2. 原始价格基年明确；
3. 技术、规模和容量分母直接对应；
4. 作者 bottom-up/规范化成本或可审计真实报价；
5. FOM、replacement/augmentation、残值和退役成本互斥。

仅有高等级期刊外壳不够。若论文数值来自 NREL/PNNL/项目报告，它仍属于官方工程或项目证据层，不能被转引自动升级为作者正式数值。

## 2. 新证据与判定

| 来源 | 新信息 | 判定 |
|---|---|---|
| Guccione & Guédez, *Energy* (2023), DOI `10.1016/j.energy.2023.128528` | 熔盐电加热器 `140 EUR/kWe`，Table 4，真实报价 | 直接组件和分母合格；报价价格年缺失，`blocked_pending_quote_price_year` |
| Guccione & Guédez, *Energy* (2024), DOI `10.1016/j.energy.2024.133500` | 电加热器 `15 EUR/kW` 电气项 + `125 EUR/kW` 热力项；报价来自三个欧盟项目框架 | 报价价格年缺失；温度因子缩放还需作者澄清，不编码 |
| 同一 *Energy* (2024) 论文 | 双罐熔盐 TES `18–23 EUR/kWh_th`，对应 `ΔT=275–98°C` | 底层来自 NREL/历史工程来源；仅为工程敏感性锚点 |
| Rahman et al., *Applied Energy* (2021), DOI `10.1016/j.apenergy.2020.116343` + University of Alberta 官方博士论文，DOI `10.7939/r3-jgnr-b764` | 博士论文明确说明 Chapter 3 已发表为该 *Applied Energy* 文章；扩展章节给出 2019 USD、完整分项、容量分母、replacement/FOM 与退役排除边界 | 用户已批准关联证据政策；`formal_candidate=true`，三接缝 resolved contract 已实现；TES/系统 TAC 仍阻断 |
| Ahmadi et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2025.126706` | LiB 细分到 energy/PCS/BoP/construction/replacement/FOM/VOM | 原文明示为 PNNL 2030 projections，只作官方预测敏感性 |

两篇 Guccione 论文报告的 2021 年平均 `USD/EUR=0.84` 只是换汇口径，不足以说明报价发生于 2021 年，也不能据此执行 2021 EUR→2024 CNY 换算。

## 3. 当前证书结果

截至 2026-07-13，E0-D-12 历史机器矩阵 13 行中 Rahman BESS 为唯一 `formal_candidate=true`；E0-D-15 代码参考审计扩展为 16 条记录后，正式候选仍只有 Rahman。因此：

- `cost_evidence.py` 的严格资格维度保持不变，并新增同作者官方扩展 crosswalk；
- 为 `rahman2021_bess_component_package` 创建一个来源层 `FormalCostEvidenceCertificate`；
- NREL 2022 ATB BESS 继续只作 `official_engineering_anchor`；
- Guccione 电加热器报价注册为近正式但阻断候选；
- Guccione 熔盐 TES 范围、Ahmadi/PNNL 2030 BESS 表只进入敏感性；
- 不创建 TES 或整套 BESS—TES `FormalCostEvidenceCertificate`，E1–E6 不启动。

E0-D-15 进一步新增 `TESFormalCostPortfolioCertificate` 的前置门禁：盐、储罐、循环、电气接入、电加热器、两条蒸汽充热、盐—蒸汽发生、供热换热、power-block retrofit、项目附加费和寿命项必须全部具有唯一可认证候选。Klasing/Li/DLR 系统聚合锚点在构造阶段被禁止满足部件账户；若未来采用多个 DOI 拼接，还需用户另行批准复合证据路线。当前 12 个账户全部 `blocked`，所以不会颁发 TES 证书。

## 4. 后续闭环路径

下一步仍执行严格模型门槛：

1. 向 Guccione/Guédez 或相关项目方确认报价日期、原始币种和是否已做通胀归一化，并澄清 2024 温度因子公式缩放；
2. Rahman 的 PCS、BoP、围护基础、battery/PCS FOM 和 contingency 已完成互斥映射；E0-D-14 又锁定 Schmidt 13 年/3250 EFC 唯一退化核、AC 放电 VOM 与 5–100 MW PCS 常数单价，后续不得叠加 Rahman cycle-only replacement 或伪造 95% PWL；
3. TES 如仍无法形成单层正式组合，是否采用复合证据路线需另行批准，不能由本次 BESS 关联证据批准自动扩张。

DLR 2021 官方报告已关闭一个较窄的访问问题：Klasing 的两罐中心值可追溯为 `21 EUR_2020/kWh_th-net`，报告范围为 20–22。但该值是非同行评议、两罐 Solar Salt 系统聚合成本，只能作为未来 bottom-up 总量校准，不能解除任何三罐 HITEC 部件账户。

2026-07-13 的进一步复核改变了 Rahman 行的访问判定：University of Alberta Scholaris 官方仓储公开了作者博士论文，且论文明确将 Chapter 3 与 Rahman et al. (2021, *Applied Energy*) 交叉对应；该章已恢复完整数值表、2019 USD 基年、容量分母和成本边界。Guccione 行没有同样闭合：KTH 全文与 CORDIS/SHARP-sCO2 公开材料仍未公开报价日期、原币、规模和完整成本边界，也没有公开勘误能够解释温度因子 `16` 的缩放。同日，两封作者询证邮件已由用户授权并通过浙江大学邮箱发送；Rahman 邮件回复可用于再确认，Guccione/Guédez 回复仍是解除电加热器阻断的关键。Unpaywall 仍需用户提供真实邮箱。

同日用户批准 Rahman 关联证据政策，E0-D-13 新增 `formal_bess_costs.py` 与测试：`USD_2019→CNY_2024_real` 因子为 `8.73826631502364`，主要非电芯规格已可审计生成。E0-D-14 保留原始来源对象 `formal_portfolio_ready=false`，同时新增 `formal_fixed_capacity_ready=true` 的 resolved contract；完整 BESS 年度经济账本已可构造。E0-D-15 新增 TES 正式就绪度门禁；E0-D-16 新增探索性全系统 EAC 上限内核，但不改变 TES 正式候选为零的判定。本地完整回归为 `279 passed in 31.57s`（关闭 pytest cache），远端尚未同步 E0-D-14–D-16 代码。

机器证据与访问日志位于：

- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/formal-cost-candidate-matrix.csv`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/claim-evidence-map.md`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/source-log.md`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/access-log.json`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/follow-up-access-and-author-query.md`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/follow-up-access-log.json`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/alternative-source-audit.md`
- `风光火+熔盐储热/research-sessions/2026-07-13-e0d15-tes-formal-cost-closure/evidence-memo.md`
