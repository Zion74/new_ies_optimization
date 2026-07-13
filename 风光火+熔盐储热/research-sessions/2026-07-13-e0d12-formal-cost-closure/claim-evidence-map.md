# E0-D-12 主张—证据映射

| ID | 可发表/可审计主张 | 直接证据 | 限定语 | 状态 |
|---|---|---|---|---|
| C1 | 高等级论文中存在面向熔盐系统的真实电加热器报价 | Guccione & Guédez, *Energy* 2023 Table 4；*Energy* 2024 Table 6 及脚注 | 论文未披露报价日期或原始价格基年 | 支持，但不能进入正式 TAC |
| C2 | `140 EUR/kWe` 是当前最清晰的电加热器单一分母候选 | *Energy* 2023 Table 4 | 2021 是 USD/EUR 换汇年，不等于报价价格年 | `blocked_pending_quote_price_year` |
| C3 | *Energy* 2024 将电加热器拆成电气与热力成本并考虑温度影响 | Table 6 与附录电加热器公式 | Table 6 的温度因子 `16 1/°C` 与附录公式合用时缩放不清，不能直接编码 | `blocked_pending_formula_clarification` |
| C4 | 双罐熔盐 TES 的公开工程范围可取 `18–23 EUR/kWh_th` 做敏感性核验 | *Energy* 2023 Table 4；*Energy* 2024 Table 6/附录 | 底层来自 NREL 工程报告与更早文献，不是作者报价；且本项目为 CHP 三罐/双服务拓扑 | `official_engineering_sensitivity_anchor` |
| C5 | Rahman 2021 与其 University of Alberta 官方博士论文 Chapter 3 构成已批准的 BESS 关联证据包 | *Applied Energy* 论文 + 博士论文中的明确发表交叉说明、Table 3.1–3.6 | 同作者官方扩展材料不是另一篇独立同行评审论文，必须按关联证据包披露 | `formal_candidate` |
| C6 | Ahmadi 2025 的 LiB 分项表不能作为作者正式基线 | *Applied Energy* 2025 Section 4.1 / Table 4 | 原文明示为 PNNL 2030 projections | `official_projection_sensitivity_only` |
| C7 | BESS 来源资格与主要非电芯分项已闭合，但电芯寿命接缝、PCS 规模和 VOM 吞吐侧仍需模型决策；熔盐电加热器仍缺报价年/原币/边界 | `formal-cost-candidate-matrix.csv`、`alternative-source-audit.md` 与 `formal_bess_costs.py` | 来源正式候选不等于完整 TAC 已就绪 | 支持 |
| C8 | 当前只可颁发 Rahman BESS 来源层证书；TES 证书和完整 E0 总证书仍不应生成 | C1–C7 与 `cost_evidence.py` / `formal_bess_costs.py` | 不妨碍继续闭合 BESS 三个模型接缝或做敏感性验证 | 支持 |
| C9 | “高等级论文定边界 + 官方工程数据定数值”是可辩护的备选证据架构 | NREL/PNNL 工程数据与 Energy+ 技术论文的互补性 | 属于证据政策变更，必须明确披露并经用户批准，不能冒充单层 Energy+ 正式基线 | 待决策 |

## 禁止表述

- 禁止写“140 EUR/kWe 为 2021 EUR”——原文只报告 2021 平均换汇率。
- 禁止写“18–23 EUR/kWh_th 为作者实测成本”——底层来自 NREL/历史工程来源。
- 禁止写“Ahmadi 2025 提供作者 2025 LiB 成本”——它采用 PNNL 2030 预测。
- 禁止写“Rahman 博士论文是另一篇独立的 Energy+ 论文”——正确表述是它与 *Applied Energy* 论文组成同作者关联证据包。
- 禁止写“InstSci 无结果说明没有论文”——本轮搜索受 Semantic Scholar 限流，属于访问失败。
- 禁止把聚合项目成本与其内部部件账本叠加。
