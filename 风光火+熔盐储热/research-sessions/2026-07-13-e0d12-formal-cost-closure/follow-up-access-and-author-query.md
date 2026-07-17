# E0-D-12 后续访问与作者询证包

日期：2026-07-13
状态：**合法访问路径已复核；两封询证邮件已由用户授权并发送，等待作者回复。**

## 1. 合法全文访问复核

目标论文：Rahman et al., *Applied Energy* 283 (2021) 116343，DOI `10.1016/j.apenergy.2020.116343`。

| 路径 | 结果 | 审计解释 |
|---|---|---|
| InstSci 精确题名检索 | `no_results`，同时出现 Semantic Scholar 限流重试 | 不是论文不存在的证据，也没有取得全文 |
| ScienceDirect 出版商页面 | 摘要和索引文本可见，完整数值表不可见 | 可确认 bottom-up 方法，不能提取正式成本数值 |
| ResearchGate | 仅提供 `Request full-text` | 没有公开 PDF |
| IDEAS/RePEc、EPA HERO、FES Forum | 只有元数据或摘要 | 没有成本表和价格基年 |
| University of Alberta 研究组页面与 ERA 仓储检索 | 找到作者/学位信息，未找到该论文的公开稿 | 不能把相关学位记录当作论文全文 |
| Unpaywall | 未调用 | API 要求用户真实邮箱；不得代填或使用占位邮箱 |
| InstSci 出版商代理 | 未给出闭源最终判定 | 尚未确定用户订阅机构；不能默认机构或虚构订阅访问 |

结论：目前只能维持 `blocked_pending_full_text`。若要继续自动化开放获取核查，需要用户提供一个用于 Unpaywall 的真实邮箱；若要尝试订阅访问，需要用户提供订阅机构名称，随后用可见浏览器验证。两者都不需要用户提供账户密码。

## 2. Guccione 报价溯源补充

- CORDIS 的 SOLARSCO2OL 项目记录显示：项目于 2020-10-01 开始；第二报告期覆盖 2022-04-01 至 2024-07-31，期间电加热器经历设计、分析、制造和采购活动。
- 该时间线只能限定“报价可能形成的项目阶段”，不能证明报价发生在 2021 年，也不能证明论文数值已做通胀归一化。
- CORDIS 的公开成果页没有披露电加热器成本明细或报价元数据。
- SHARP-sCO2 2024 年 7 月通讯说明中压电加热器此前已开发约 18 个月，但同样没有报价日期、币种、规模或成本边界。
- 因此 `140 EUR/kWe` 以及 `15 + 125 EUR/kW` 仍为 `blocked_pending_quote_price_year`；2024 论文 Table 6 中打印为 `16 1/°C` 的温度因子也继续标记为 `blocked_pending_formula_clarification`。

公开来源：

- SOLARSCO2OL CORDIS 项目报告：https://cordis.europa.eu/project/id/952953/reporting
- SOLARSCO2OL CORDIS 公开成果：https://cordis.europa.eu/project/id/952953/results
- SOLARSCO2OL 项目网站：https://www.solarsco2ol.eu/
- SHARP-sCO2 2024 年 7 月通讯：https://www.sharpsco2.eu/files/SHARP-sCO2_2_Newsletter_2407.pdf

## 3. 询证邮件 A：Rahman BESS 成本模型

建议收件人：Amit Kumar 教授（University of Alberta 官方目录公开联系方式）
主题：`Request for cost-table provenance and an author manuscript — Applied Energy 283 (2021) 116343`

> Dear Professor Kumar,
>
> I am conducting a graduate research study comparing battery energy storage with molten-salt thermal energy storage under a consistent annualized-cost boundary. I have read the abstract and indexed material for your paper, “The development of techno-economic models for the assessment of utility-scale electro-chemical battery storage systems” (*Applied Energy*, 283, 116343), but I have not been able to access the complete cost tables legally.
>
> Would you be willing to share an author-accepted manuscript or the relevant supplementary tables, if permitted? To use the data without misrepresenting your cost basis, I would also be grateful if you could clarify:
>
> 1. the original price year and currency of each battery, PCS, balance-of-plant and O&M input;
> 2. whether reported values are normalized to one common real-price year and, if so, the index used;
> 3. the exact denominator for each component (kW, kWh, or system-level capacity at a specified duration);
> 4. whether replacement or augmentation, fixed O&M, decommissioning and residual value are included, and how double counting is avoided; and
> 5. whether any tabulated values may be cited directly in a graduate thesis and journal article with attribution.
>
> I will use any material only for academic research and will cite the paper and any requested source precisely. Thank you for your time.
>
> Sincerely,
> [Name]
> [University / Programme]

公开联系依据：https://apps.ualberta.ca/directory/person/amitk

## 4. 询证邮件 B：熔盐电加热器报价与温度因子

建议收件人：Rafael Guédez 教授（KTH 官方页面公开联系方式）
可选抄送：SHARP-sCO2 项目公共邮箱 `info@sharpsco2.eu`
主题：`Clarification of electric-heater quotation basis in Energy 283 (2023) 128528 and Energy 312 (2024) 133500`

> Dear Professor Guédez,
>
> I am conducting a graduate research study on a consistent techno-economic comparison between battery storage and molten-salt thermal storage. Your 2023 and 2024 *Energy* papers provide unusually valuable quotation-based electric-heater costs, and I would like to avoid assigning an incorrect price year or scaling rule to them.
>
> Could you please clarify the following points, to the extent that the quotation confidentiality permits?
>
> 1. the quotation date or original price year for the `140 EUR/kWe` value in the 2023 paper and the `15 EUR/kW` electrical plus `125 EUR/kW` thermal components in the 2024 paper;
> 2. the original quotation currency and whether the published values are nominal quotations or normalized constant-year EUR values;
> 3. the quoted heater rating, voltage level and inclusion boundary (heater vessel/elements, power electronics, transformer/switchgear, controls, installation and contingency);
> 4. whether the three project quotations were combined, averaged or used as separate checks; and
> 5. the intended numerical scaling of the temperature correction factor printed as `16 1/°C` in Table 6 of the 2024 paper (for example, whether a decimal or percentage convention is implicit).
>
> I will cite the papers and any permitted project source precisely, and I am not requesting confidential vendor documentation. A short confirmation of the price year and formula convention would be sufficient for an auditable conversion.
>
> Sincerely,
> [Name]
> [University / Programme]

公开联系依据：https://www.energy.kth.se/heat-and-power-technology

## 5. 发送记录与后续检查

- 用户于 2026-07-13 明确授权发送，并提供署名：Haonan Zheng，Energy Engineering，Zhejiang University。
- 发件地址：`haonan.zheng@zju.edu.cn`。
- 2026-07-13 15:49（邮箱页面显示时间），邮件 A 已发送至 `amitk@ualberta.ca`，浙江大学邮件系统确认已发送至收件人服务器。
- 2026-07-13 15:50（邮箱页面显示时间），邮件 B 已发送至 `rafael.guedez@energy.kth.se`，浙江大学邮件系统确认已发送至收件人服务器。
- 未抄送 SHARP-sCO2 项目邮箱；未附带本地数据、代码、私钥或未公开项目文件。
- 发送不等于对方已阅读或同意披露。收到回复后应保存原始邮件时间、附件哈希和许可边界，再决定是否升级 `formal_candidate`。
