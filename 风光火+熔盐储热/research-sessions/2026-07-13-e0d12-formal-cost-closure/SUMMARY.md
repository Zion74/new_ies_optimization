# E0-D-12 正式成本证据闭环审计

日期：2026-07-13
工作流：Discovery / evidence audit
结论：**用户已批准 Rahman 关联证据包政策，BESS 来源层颁发一个正式候选证书；熔盐 TES/电加热器仍无正式候选，完整 TAC 与 E0 总门槛继续阻断。**

## 本轮新增

1. 找到 Guccione 与 Guédez 在 *Energy* 2023、2024 两篇论文中的真实电加热器报价：
   - 2023：熔盐电加热器 `140 EUR/kWe`，Table 4，脚注为真实报价；
   - 2024：电加热器电气项 `15 EUR/kW`、热力项 `125 EUR/kW`，Table 6，脚注说明报价来自 SOLARSCO2OL、SHARP-sCO2、Power2Power 项目框架。
2. 两篇论文只说明统一换汇采用 2021 年平均 `USD/EUR=0.84`，没有说明原始报价日期或价格基年。因此报价属于 `blocked_pending_quote_price_year`，不能直接换算到 `CNY_2024_real`。
3. *Energy* 2024 的熔盐 TES `18–23 EUR/kWh_th` 对应双罐显热系统，但底层依据是 NREL 工程报告与更早文献，不是作者报价或作者完成的同基年 bottom-up 成本核算，只能作为工程敏感性锚点。
4. *Applied Energy* 2025 的 LiB 分项表明确是 PNNL 对 2030 年技术的预测，不能升级成作者当前年正式成本。
5. Rahman et al. (*Applied Energy*, 2021) 的作者官方扩展来源已经取得：University of Alberta 博士论文明确说明 Chapter 3 已发表为该文章，并给出 2019 USD、完整 Li-ion/PCS/BoP/FOM/VOM 表、5–100 MW 场景分母、replacement 和退役排除边界。用户已批准该关联证据政策，该行升级为唯一 `formal_candidate=true`。
6. E0-D-13 已将 Rahman 证据包落为可执行对象：PCS、BoP、围护基础、battery/PCS FOM 和 contingency 直接映射；电芯 cycle-only replacement 与现有 calendar+throughput 退化接缝、VOM 吞吐侧及 5 MW PCS 规模曲线继续显式阻断。

## 审计判定

正式证书仍要求以下条件同时成立：

- `core_peer_reviewed`；
- 明确的原始价格基年，而非发表年、情景年或换汇年；
- 与本项目技术边界直接对应；
- 作者 bottom-up、作者规范化或可审计真实报价；
- 精确容量分母；
- FOM、replacement/augmentation、残值和退役成本互斥。

Guccione 电加热器仍至少缺少其中一项；Rahman BESS 来源资格与主要非电芯边界映射已经完成，但完整 BESS 生命周期 portfolio 仍有三个模型接缝。因此：

- 不修改 `cost_evidence.py` 的严格资格门；
- 仅为 `rahman2021_bess_component_package` 生成来源层 `FormalCostEvidenceCertificate`；
- 不把高等级论文对官方报告的转引包装成“Energy+ 正式数值”；
- 不启动 E1–E6 批量边界实验。

## 下一步可选路径

1. **闭合 BESS 三个接缝**：用现有高等级寿命证据处理 cell calendar+throughput 退化，预注册 PCS 常数/PWL 规模口径，并决定 VOM 使用 AC 放电侧还是暂时排除。
2. **保持 Guccione 严格门槛**：等待作者或项目方确认电加热器报价日期、原始币种、规模、边界和温度因子；等待期间只作宽敏感性。
3. **TES 后备复合证据路线（需另行批准）**：高等级论文负责技术机制、边界与同行评审背书；官方工程/项目报价提供数值，并通过宽敏感性和独立聚合锚点校准。

详细材料：

- `source-log.md`
- `claim-evidence-map.md`
- `formal-cost-candidate-matrix.csv`
- `access-log.json`
- `alternative-source-audit.md`
