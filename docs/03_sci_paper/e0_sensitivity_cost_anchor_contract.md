# E0-D-11 BESS 官方工程敏感性成本锚点合同

更新时间：2026-07-13
状态：**NREL 2022 ATB 的 4 h 公用事业级 BESS 成本已形成可哈希复核的功率—可用能量双分母台账，并完成 2020 USD → 2024 CNY 转换；该台账只用于敏感性和量级审计，不能颁发 Energy+ 正式基线证书。**

## 1. 研究用途

E0-D-11 解决的是“在正式同行评审成本组合尚未闭合时，是否可以先有一套不混淆证据等级、可复现且防重复计费的电站级 BESS 工程锚点”。答案是可以，但必须同时满足：

1. 官方工程来源与 Energy+ 核心论文分层保存；
2. 功率成本和可用能量成本分别保持 `USD/kW_DC`、`USD/kWh_usable,DC` 分母；
3. 原工作簿、提取 JSON 和 manifest 均以 SHA-256 锁定；
4. 含容量扩容的源 FOM 与独立 replacement ledger 不得同时启用；
5. 只进入 E4/E6 成本倍率、量级和边界移动敏感性，不决定正式 TAC 基准。

## 2. 原始证据与精确单元格

来源为 NREL/OEDI `2022 Annual Technology Baseline` v3 工作簿，数据集 DOI `10.25984/1871952`。代表系统为 60 MW_DC / 240 MWh_usable,DC，即 4 h；工作簿明确声明所有数值为 2020 USD。

| 项目 | 单元格 | 精确值 |
|---|---|---:|
| 价格基年 | `Utility-Scale Battery Storage!G9` | 2020 |
| 能量资本成本，2021 | `G20` | 309.3044998122252 USD/kWh_usable |
| 功率资本成本，2021 | `G26` | 238.23917543208495 USD/kW |
| 4 h 总资本成本，2021 | `G40` | 1475.4571746809856 USD/kW |
| 4 h FOM，2021 | `G59` | 36.88642936702464 USD/(kW·a) |

台账必须满足：

\[
C_{\mathrm{cap},/kW}=c_E D+c_P,
\qquad
C_{\mathrm{FOM},/kW\cdot a}=0.025C_{\mathrm{cap},/kW}.
\]

代入 4 h 后两式均与工作簿缓存值在 `1e-9` 以内闭合。60 MW / 240 MWh 的精确初始资本成本为 `88,527,430.480859 USD_2020`；NREL Q1 2021 报告将其约写为 9,000 万美元，差异属于报告取整，计算一律保留 ATB 工作簿精确值。

## 3. FOM 与 replacement 互斥

ATB 官方说明把所有运行成本放入 FOM；其中已按第 10 年和第 20 年各扩容 20% 来补偿退化，FOM 取 CAPEX 的 2.5%/a。因此：

- `use_source_fixed_om=True` 时，`has_separate_replacement_ledger` 必须为 `False`；
- 若研究者要使用独立电芯日历/EFC replacement ledger，必须关闭源 FOM，再另行提供不含扩容的 O&M 假设；
- 不允许把 2.5% FOM 与 `economics.py` 中的电芯更换现金流直接相加。

`SensitivityBESSCostLedger` 在构造时执行这项互斥检查，违规会以 `double count` 拒绝。

## 4. 价格转换与当前数值

E0-D-4 官方快照给出的 `USD_2020 → CNY_2024_real` 转换因子为：

\[
k=\frac{313.689}{258.811}\times 7.1217=8.631777441067033.
\]

因此 60 MW / 240 MWh 代表系统的敏感性锚点为：

- 初始资本成本：`764,149,077.34031 CNY_2024_real`；
- 含扩容源 FOM：`19,103,726.933508 CNY_2024_real/a`。

`SensitivityBESSCostConversion` 保留源台账和 `PriceBasisConversion`，只允许一次显式换算，不会把转换后的数值反写成 NREL 原值。

## 5. RTE 冲突的处理

修订版工作簿 4 h 行给出 RTE=0.85，而 ATB 网页文字给出 0.86。E0-D-11 是成本合同，不对该冲突做未经授权的选择：`round_trip_efficiency` 被登记为 `excluded_from_cost_anchor`，不能因为成本台账通过就顺带进入正式性能参数集。

## 6. 代码、数据与验证

- 加载与缩放：`src/tes_bess_boundary/sensitivity_cost_anchors.py`；
- 合同测试：`tests/test_sensitivity_cost_anchors.py`；
- 原工作簿、提取 JSON、manifest：`风光火+熔盐储热/数据采集/e0d11_sensitivity_cost_anchors/`；
- 上游证据门：`cost_evidence.py` 中的 `nrel2022_utility_bess`；其 `formal_blockers()` 仍包含 `venue_tier / allowed_use / source_provenance`。

SHA-256：

- 源码：`2f70b5e12275fc199bec54086ae9ad9004ab54c263ce35a8cdf2bc81e82c2b70`；
- 测试：`c42f0d2b432c652d04930d91c8a2f674bc139f84020d986fdfa4f1c762369dc9`；
- 工作簿：`5ad5e47373f0dea32991d5828831bb407550397f1956abda6870e6786134b87e`；
- 提取 JSON：`50e44ef95e1589e22818339a969056c0eaa1a3450985be1a3693b968bf7d0a30`；
- manifest：`c122e9e0d0d40afdf4c4705d277436ebb780e0096d967795c18f933b80f00437`。

本地 Python 3.11 全量结果为 `258 passed in 38.13s`；OpenBayes Python 3.10.18 / HiGHS 1.15.1 为 `258 passed in 21.36s`，新增源码、测试、工作簿、提取 JSON 与 manifest 的 SHA-256 均与本地一致。远端真实证据包加载重算得到 4 h、`88,527,430.480859 USD_2020` 初始资本成本、`2,213,185.762021 USD_2020/a` FOM、`formal_baseline_eligible=False`，并保留 RTE 排除标记。

## 7. 对 E0 总门槛的影响

E0-D-11 关闭了“没有可复现电站级 BESS 工程敏感性锚点”的缺口，但没有关闭以下正式门槛：

- Energy+ 同行评审层的 BESS `cell / PCS / BoP / construction / FOM / replacement` 共同价格年组合；
- TES 分项价格年、包含边界和煤电改造独立聚合校准；
- 正式 TAC、endogenous capacity、代表周和批量边界实验。

因此 E0 总门槛仍未通过，E1–E6 正式批量实验仍不启动。
