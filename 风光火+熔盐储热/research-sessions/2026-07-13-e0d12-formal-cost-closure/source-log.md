# E0-D-12 来源日志

检索日期：2026-07-13
纳入门槛：核心定量证据原则上不低于 *Energy*；低于门槛的 *Energies* 论文不提取数值。
期刊指标：出版商页面在检索日显示 *Energy* IF 9.4 / CiteScore 16.5，*Applied Energy* IF 11.0 / CiteScore 20.1，*Energy Conversion and Management* IF 10.9 / CiteScore 19.8。

## A. 本轮全文核验来源

### A1. Guccione & Guédez, Energy 2023

- 题名：Techno-economic optimization of molten salt based CSP plants through integration of sCO2 cycles and hybridization with PV and electric heaters
- DOI：`10.1016/j.energy.2023.128528`
- 出版商页面：<https://www.sciencedirect.com/science/article/pii/S0360544223019229>
- 开放全文：<https://kth.diva-portal.org/smash/get/diva2%3A1907063/FULLTEXT01.pdf>
- PDF SHA-256：`83d181356f710161ad7af2c1b971c80d101633328eeba9d15f4dfb1476ed1f5b`
- 精确位置：Table 4，PDF 第 8 页。
- 可核验信息：熔盐电加热器 `140 EUR/kWe`，脚注为真实报价；成本假设统一换汇采用 2021 年平均 `USD/EUR=0.84`。
- 审计限制：论文没有披露报价发生年份、原始币种或通胀归一化链；2021 年只是换汇年，不能自动视为价格基年。
- 允许用途：`blocked_pending_quote_price_year`；可作电加热器低—中—高敏感性中心候选，不得进入正式 TAC。

### A2. Guccione & Guédez, Energy 2024

- 题名：Techno-economic analysis of power-to-heat-to-power plants: Mapping optimal combinations of thermal energy storage and power cycles
- DOI：`10.1016/j.energy.2024.133500`
- 出版商页面：<https://www.sciencedirect.com/science/article/pii/S0360544224032766>
- 开放全文：<https://kth.diva-portal.org/smash/get/diva2%3A1907145/FULLTEXT01.pdf>
- PDF SHA-256：`2e03c7ad60a07651bb6f1ee5d089e1208c5e8cfeb13defc039c25b2ed612e4cf`
- 精确位置：Table 6，PDF 第 8 页；附录 PDF 第 15 页。
- 可核验信息：
  - 电加热器电气项 `15 EUR/kW`；
  - 电加热器热力项 `125 EUR/kW`；
  - Table 6 的脚注说明来自 SOLARSCO2OL、SHARP-sCO2、Power2Power 项目框架下的真实报价；
  - 熔盐双罐 TES 为 `18–23 EUR/kWh_th`；附录将 `23 EUR/kWh_th` 对应 `ΔT=98°C`，将 `18 EUR/kWh_th` 对应 `ΔT=275°C`；
  - 成本假设统一换汇采用 2021 年平均 `USD/EUR=0.84`。
- 审计限制：
  - 真实报价没有披露价格年；
  - Table 6 中温度因子 1 显示为 `16 1/°C`，与附录对数公式合用时量纲/缩放异常，不能无解释实现；
  - 熔盐 TES 数值最终追溯到 NREL 2019/2011 工程报告和更早文献，不是作者的同基年 bottom-up 报价。
- 允许用途：电加热器为 `blocked_pending_quote_price_year_and_formula_scaling`；TES 为 `official_engineering_sensitivity_anchor`。

### A3. Ahmadi et al., Applied Energy 2025

- DOI：`10.1016/j.apenergy.2025.126706`
- PDF SHA-256：`439998c9b11bcac6c54584ddc75b07e89bf23d938f8674a457a369e0aa3d2c4b`
- 精确位置：Section 4.1 与 Table 4。
- 可核验信息：LiB 能量项 `189 USD/kWh`、PCS `211 USD/kW`、BoP `95 USD/kW`、construction `96 USD/kWh`、replacement `409.59 USD/kWh`、FOM `7.59 USD/kW-year`、VOM `2.31 USD/MWh`。
- 审计限制：原文明确这些值是 PNNL 对 2030 年 BSS 技术的预测，不是作者 bottom-up 当前成本；币值价格年也未由文章独立闭合。
- 允许用途：`official_projection_sensitivity_only`。

## B. BESS 关联证据包

### B1. Rahman et al., Applied Energy 2021 + University of Alberta 官方博士论文

- DOI：`10.1016/j.apenergy.2020.116343`
- 出版商页面：<https://www.sciencedirect.com/science/article/pii/S0306261920317256>
- 可核验信息：文章比较多种规模与应用，采用作者 bottom-up LCOS 框架，显式考虑储能本体、PCS、BoP、replacement 和 O&M；出版商摘要给出 Li-ion LCOS 约 `180–1032 USD/MWh` 的应用依赖范围。
- 官方扩展来源：University of Alberta Scholaris 博士论文记录 <https://ualberta.scholaris.ca/items/5b3bc21c-3493-4497-8b13-fa33ecd88a07>，DOI `10.7939/r3-jgnr-b764`。论文明确说明 Chapter 3 已发表为上述 *Applied Energy* 文章。
- 新增可核验信息：Chapter 3 给出 2019 USD 基年、20 年期、10% 名义贴现率、1.72% 通胀率，以及 Li-ion 电池 `216.27 USD/kWh`、FOM `10.35 USD/kW-year`、VOM `2.74 USD/MWh`、BoP `106.75 USD/kW`、PCS `206.81/243.31 USD/kW`、PCS FOM `2.63 USD/kW-year`；同时披露 replacement、contingency、退役排除和 5–100 MW 场景分母。
- 底层追溯：Li-ion 电池单价引用 NREL 2018 utility-scale PV-plus-storage benchmark（DOI `10.2172/1483474`），但 NREL 只作为官方工程追溯层。
- 允许用途：用户已批准“高等级论文 + 同作者官方扩展材料”的关联证据单元，现为唯一 `formal_candidate`。E0-D-13 已完成主要非电芯边界映射；完整 TAC 仍需闭合 cell calendar+throughput 接缝、PCS 规模曲线与 VOM 吞吐侧。

### B2. Killer et al., Applied Energy 2020

- DOI：`10.1016/j.apenergy.2019.114166`
- 用途：欧洲/中东/非洲大型 BESS 市场与商业环境背景。
- 限制：不是可直接映射本项目 cell/PCS/BoP/FOM/replacement 的共同价格年成本组合。
- 允许用途：`context_only`。

## C. 已审计但不能升级为正式数值的高等级来源

| 来源 | 主要问题 | 允许用途 |
|---|---|---|
| Schmidt et al., *Joule* 2019, `10.1016/j.joule.2018.12.008` | 2015 inputs 与 US$2018 输出口径之间缺完整转换链，且底层值混合引用 | 非价格参数直接候选；成本阻断 |
| Bahloul et al., *Energy* 2022, `10.1016/j.energy.2022.123229` | Table 9 数值回溯到 PNNL 并经低等级论文二次转录，VOM 单位还存在风险 | 结构审计，不提取正式数值 |
| Trevisan et al., *Energy Conversion and Management* 2022, `10.1016/j.enconman.2022.116362` | 分项来自混合年份来源，未归一到共同价格年 | TES ledger 结构与分母 |
| Vecchi & Sciacovelli, *Applied Energy* 2023, `10.1016/j.apenergy.2022.120628` | 2020 USD 归一化明确，但 TMES/PTES/TCES 拓扑和材料不匹配 | 方法与敏感性 |
| Xue et al., *Applied Energy* 2024, `10.1016/j.apenergy.2024.123021` | `74.28 USD/kWh` 为钢厂 135 MW 聚合调峰系统成本，边界和价格年不闭合 | 聚合校准锚点 |
| Klasing et al., *Applied Energy* 2025, `10.1016/j.apenergy.2024.124524` | 主要 TES 分项来自项目报告/混合文献；只有部分作者公式明确 2023 EUR | 分项阻断；聚合校准 |
| NREL 2022 ATB utility BESS | 2020 USD、60 MW/240 MWh、双分母清楚，但属于官方工程数据而非同行评审论文 | 官方工程敏感性锚点 |

## D. 显式排除

- Yuan et al. (2016), *Energies*, `10.3390/en9060474`：低于用户规定的期刊门槛。
- Yu et al. (2018), *Energies*, `10.3390/en11020263`：低于用户规定的期刊门槛。
