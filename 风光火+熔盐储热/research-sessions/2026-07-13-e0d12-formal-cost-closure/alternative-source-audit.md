# E0-D-12 替代来源审计：BESS 与熔盐电加热器

检索日期：2026-07-13
判定原则：核心机理和成本模型仍由 `Energy` 同等级或更高同行评审论文承载；作者官方学位论文、大学仓储和欧盟项目资料只能与对应高等级论文组成可追溯证据包，不能单独伪装成高等级期刊证据。

## 1. 结论

- **Rahman BESS：关键缺失字段可从其他来源补齐。** University of Alberta 官方博士论文是 Rahman et al. (2021, *Applied Energy*) 的作者扩展来源；论文前置说明明确指出第 3 章已经以该 *Applied Energy* 文章发表。第 3 章提供了原文章索引文本中缺失的成本表、2019 USD 基年、功率/能量分母、PCS 与 BoP 边界、FOM/VOM、replacement 和排除项。
- **Guccione 熔盐电加热器：只能部分补齐。** KTH 正式全文和欧盟项目页面能确认数值、公式写法、技术对象和项目背景，但没有公开供应商报价日期、原始币种、报价规模及完整商业边界；也没有公开更正能够证明温度因子 `16` 应缩放为 `0.16` 或其他数值。因此这些字段仍需作者/供应商回复。

## 2. Rahman BESS：可闭合的关联证据包

### 2.1 来源链

1. 同行评审核心：Rahman, Oni, Gemechu and Kumar, “The development of techno-economic models for the assessment of utility-scale electro-chemical battery storage systems,” *Applied Energy* 283 (2021) 116343, DOI `10.1016/j.apenergy.2020.116343`。
2. 作者官方扩展来源：Md Mustafizur Rahman, *Economic and environmental assessment of large-scale electro-chemical and flywheel energy storage systems for stationary applications*, University of Alberta doctoral dissertation (2022), DOI `10.7939/r3-jgnr-b764`，官方记录：<https://ualberta.scholaris.ca/items/5b3bc21c-3493-4497-8b13-fa33ecd88a07>。
3. 论文—学位论文交叉确认：学位论文明确写明其 Chapter 3 已发表为上述 *Applied Energy* 论文，因此第 3 章可作为同一研究的扩展表格与假设来源，而不是无关的二次文献。
4. Li-ion 电芯成本的底层工程来源：NREL 2018 utility-scale PV-plus-storage benchmark，DOI `10.2172/1483474`，官方报告：<https://docs.nrel.gov/docs/fy19osti/71714.pdf>。它用于底层追溯，不能单独替代 *Applied Energy* 的同行评审层级。

### 2.2 已补齐字段

| 字段 | 官方扩展来源中的信息 | 审计解释 |
|---|---|---|
| 价格基年 | 除非另有说明，全部成本为 **2019 USD** | 原价格基年闭合 |
| 项目期与金融口径 | 20 年；名义贴现率 10%；加拿大 2010–2018 平均通胀率 1.72% | 可独立重算 CRF/现值 |
| Li-ion 电池能量项 | `216.27 USD/kWh` | 能量容量分母明确 |
| Li-ion 固定 O&M | `10.35 USD/kW-year` | 功率分母与年度口径明确 |
| Li-ion 可变 O&M | `2.74 USD/MWh` | 吞吐量分母明确 |
| Li-ion BoP | `106.75 USD/kW` | 功率分母明确 |
| PCS 资本成本 | `206.81 USD/kW`（S1–S3）；`243.31 USD/kW`（S4） | 5 MW 模块；方程已调整为 2019 USD |
| PCS 固定 O&M | `2.63 USD/kW-year` | 与电池 FOM 分列，避免重复 |
| 围护与基础 | `282.96 USD/m²`，按储能占地计算 | 不应再次并入 BoP 后重复计算 |
| 应急费 | Li-ion 为系统资本成本的 10% | 投资边界明确 |
| replacement | 若发生，按电池资本成本计；常规电池的更换时点按 DOD—循环寿命计算 | 不能再叠加一个未说明的 augmentation 比例 |
| 退役/回收 | 因数据不足而**未计入** | 后续模型要么同样排除，要么单列敏感性，不能默认为已包含 |
| 系统组成 | storage section（电池、围护和基础）+ PCS + BoP + contingency | PCS 包括变压器、变流器、控制器、隔离与断路保护；BoP 包括 HVAC、并网、监控、安装等 |

场景容量也可恢复：S1 为 50 MW/250 MWh 基准，S2 为 10 MW/50 MWh，S3 为 50 MW/12.5 MWh，S4 为 15 MW/3.75 MWh；论文考察的功率范围覆盖约 5–100 MW，因应用而异。

### 2.3 资格建议

用户已批准关联证据政策，Rahman 由 `blocked_pending_full_text_numeric_table_and_price_base` 改为 **`formal_candidate`**：

- *Applied Energy* 论文负责同行评审资格和模型主张；
- 同一作者的官方博士论文第 3 章负责展开表格、价格基年、分母和边界；
- NREL 仅作为 Li-ion 底层数值的官方工程追溯来源。

该来源层证书已经颁发。E0-D-13 进一步把 PCS、BoP、围护基础、battery/PCS FOM 和 contingency 映射为互斥非电芯账本；电芯 cycle-only replacement 与本项目 calendar+throughput 退化合同、VOM 吞吐侧和 5 MW PCS 规模曲线仍显式阻断，因此不得把“来源合格”写成“完整 TAC 已闭合”。

## 3. Guccione 电加热器：公开替代来源的边界

### 3.1 能确认的内容

- Guccione & Guédez (2023, *Energy*) KTH 开放全文：<https://kth.diva-portal.org/smash/get/diva2%3A1907063/FULLTEXT01.pdf>。Table 4 给出 `140 EUR/kWe`，脚注称基于真实报价。
- Guccione & Guédez (2024, *Energy*) KTH 开放全文：<https://kth.diva-portal.org/smash/get/diva2%3A1907145/FULLTEXT01.pdf>。Table 6 给出 `15 EUR/kW_electrical + 125 EUR/kW_thermal`；附录写出 `c_EH = c_EH,el + c_EH,th × f_T,EH` 和 `f_T,EH = c1 × log(Tmax[°C]) − c2`，表中 `c1=16 1/°C`、`c2=0.2`。
- 论文报告 2021 平均 `USD/EUR=0.84` 用于统一换汇；这只能确认论文的换汇口径，不能证明供应商报价发生于 2021 年。
- 欧盟 SOLARSCO2OL、SHARP-sCO2 等项目资料可确认电加热器/高温储热开发背景，但公开交付件元数据没有提供该熔盐电加热器报价的商业明细。

### 3.2 仍不能从公开来源确认的内容

| 缺失字段 | 公开检索判定 |
|---|---|
| 报价日期/价格年 | 未找到；2021 是换汇年，不是报价年 |
| 报价原始币种 | 未找到 |
| 报价对应设备规模 | 未找到 |
| 报价是否含安装、控制、电气接入、换热器或其他 BoP | 未找到完整边界 |
| 温度因子 `16` 是否存在漏印小数或缩放 | 未找到勘误或其他一手文件；KTH 正式全文确实显示为 `16`，不能擅自改成 `0.16` |

补充审计风险：2024 论文的一条 POWDER2POWER 项目 DOI/编号指向了名称相近但技术领域不同的欧盟项目，而真正的 POWDER2POWER 项目编号另有其号。因此不能仅靠项目名反推该报价来自哪个采购包，仍应由作者确认。

### 3.3 资格建议

- `140 EUR/kWe` 和 `15+125 EUR/kW` 可保留为 **近正式敏感性锚点**；
- 正式矩阵继续保持 `blocked_pending_quote_price_year` / `blocked_pending_quote_price_year_and_formula_scaling`；
- 在作者回复前，不对温度因子做未经证实的缩放，不把 2021 换汇年当作价格基年，也不把项目立项年份当作报价年份。

## 4. 对 E0 的直接影响

1. BESS 侧已不再受“找不到完整表格”或证据资格政策阻断；现在只剩三个可明确求解的模型接缝。
2. 熔盐电加热器侧仍有真实阻断，等待已发送的作者询证邮件回复最稳妥。
3. 在 Guccione 回复前，可以先构建两层实验参数：Rahman 关联证据包作为 BESS 条件正式候选；Guccione 报价仅进入宽敏感性，不触发正式 TAC 证书。
