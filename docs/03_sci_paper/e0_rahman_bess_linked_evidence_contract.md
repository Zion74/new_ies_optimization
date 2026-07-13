# E0-D-13 Rahman BESS 关联证据与成本边界合同

更新时间：2026-07-13
状态：**关联证据政策已获用户批准；BESS 来源层唯一正式候选已建立，主要非电芯成本映射通过；完整 BESS 生命周期 portfolio 尚有三个模型接缝。**

## 1. 证据资格

证据单元由两层组成：

1. Rahman et al., *Applied Energy* 283 (2021) 116343，DOI `10.1016/j.apenergy.2020.116343`，负责同行评审资格和模型主张；
2. Rahman, University of Alberta doctoral dissertation (2022)，DOI `10.7939/r3-jgnr-b764`，Chapter 3 负责展开表格、2019 USD 基年、场景分母和包含/排除边界。

学位论文明确说明 Chapter 3 已发表为上述 *Applied Energy* 论文。因此本合同把两者登记为 `same_author_dissertation_chapter_expansion`，而不是把博士论文冒充第二篇 Energy+ 论文。用户已批准该透明披露方式；`cost_evidence.py` 为 `rahman2021_bess_component_package` 颁发唯一来源层 `FormalCostEvidenceCertificate`。

## 2. 原始边界

Rahman 的系统边界为：

```text
storage section = battery + enclosure/foundation
+ PCS
+ BOP
+ contingency
```

- PCS 包括变压器、变流器、控制器、并网隔离和断路保护；
- BoP 包括 HVAC、并网、监控、安装等不属于 PCS 或 storage section 的项目；
- 发电源与外部电网不在成本边界内；
- 退役/回收因数据不足而排除；
- replacement 若发生，按电池资本成本计算，不能再对 PCS、BoP、围护或 contingency 重复计 replacement；
- 零残值是本项目为与来源排除口径一致而采用的显式假设，不得写成论文报告值。

## 3. 数值与直接映射

全部原值为 `USD_2019`。

| 项目 | 原值 | 本模型容量基准 | 映射 |
|---|---:|---|---|
| Li-ion battery CAPEX | 216.27 USD/kWh | `MWh_internal` | 直接成本输入，但生命周期接缝见第 5 节 |
| Battery FOM | 10.35 USD/kW-year | `MW_ac-year` | 单列非电芯固定 O&M |
| PCS CAPEX，S1–S3 | 206.81 USD/kW | `MW_ac` | 直接非电芯输入；规模口径见第 5 节 |
| PCS FOM | 2.63 USD/kW-year | `MW_ac-year` | 与 battery FOM 分列 |
| BoP CAPEX | 106.75 USD/kW | `MW_ac` | 直接非电芯输入 |
| Li-ion footprint | 0.017 m²/kWh | `MWh_internal` | 与 282.96 USD/m² 相乘 |
| Enclosure/foundation | 4.81032 USD/kWh | `MWh_internal` | 作者表格的确定性派生值 |
| Contingency | 10% system capital | 功率项和能量项分别线性分摊 | replacement cost 设为 0，避免二次计入 |

由于 contingency 对资本总额线性作用，可以保持模型的双分母：

\[
c^{cont}_{P}=0.1(206.81+106.75)=31.356\;\mathrm{USD/kW},
\]

\[
c^{cont}_{E}=0.1(216.27+4.81032)=22.108032\;\mathrm{USD/kWh}.
\]

`formal_bess_costs.py` 生成六个互斥非电芯 `LifecycleCostSpec`：PCS、BoP、围护基础、battery FOM、功率 contingency 和能量 contingency。电芯 CAPEX 不进入通用非电芯 portfolio，结构上避免与 `BESSCellCostCalibration` 双计。

## 4. 2019 USD 到 2024 CNY

沿用 E0-D-4 官方快照：BLS CPI-U 2019/2024 为 255.657/313.689，2024 年人民币兑美元年均汇率为 7.1217 CNY/USD。因此：

\[
f_{USD2019\rightarrow CNY2024}
=\frac{313.689}{255.657}\times 7.1217
=8.73826631502364.
\]

可审计换算结果包括：

| 项目 | `CNY_2024_real` |
|---|---:|
| Battery CAPEX 参考值 | 1,889,824.855950 CNY/MWh_internal |
| PCS CAPEX | 1,807,160.856610 CNY/MW_ac |
| BoP CAPEX | 932,809.929129 CNY/MW_ac |
| Enclosure/foundation | 42,033.857220 CNY/MWh_internal |
| Battery FOM | 90,441.056360 CNY/MW_ac-year |
| PCS FOM | 22,981.640409 CNY/MW_ac-year |
| Power contingency | 273,997.078574 CNY/MW_ac |
| Energy contingency | 193,185.871317 CNY/MWh_internal |

这些数值只通过 `PriceBasisConversion` 生成，不在代码中另建第二套手算转换链。

## 5. 三个剩余接缝

### 5.1 电芯 replacement 与退化

Rahman 在 80% DOD 下使用：

\[
N_{cycle}=2731.7DOD^{-0.679}\exp[1.614(1-DOD)]
=4389.6022.
\]

按 365 次/年得到约 12.03 年 replacement interval。该逻辑只有 cycle damage；当前模型已经采用 calendar + AC-throughput 双锚点。如果直接同时导入 12.03 年 replacement，会双计退化。下一步必须二选一并预注册：

1. Rahman cycle-only replacement 作为独立敏感性；或
2. Rahman 只提供 cell CAPEX，由现有 Energy+ 日历/循环寿命证据驱动正式双锚点。

推荐第 2 种，Rahman 负责价格，He/Schmidt 等高等级来源负责寿命与退化参数。

### 5.2 VOM 吞吐侧

`2.74 USD/MWh` 的表格单位没有明确是充电、放电还是其他吞吐口径。本模型只接受明确的 PCC AC 放电侧 VOM。作者回复或底层原始来源闭合前，正式基线先不计该项，并在敏感性中测试；不得自行选择分母。

### 5.3 PCS 规模曲线

Rahman 使用 5 MW PCS 模块，并对并联模块使用 95% multiplicity learning。`206.81 USD/kW` 是 S1–S3 的基准单价，不应无说明地外推到任意 endogenous capacity。下一步需在以下口径中预注册一个：

- 主模型使用常数单价，范围限制在论文 5–100 MW 并做规模敏感性；或
- 将模块/学习曲线线性化为 PWL 成本。

推荐先用常数单价完成 E0 样本验证，再在 E6 比较 PWL 规模修正，避免过早增加整数复杂度。

## 6. 当前门槛

- `formal_source_qualified=True`：是；
- `formal_portfolio_ready=False`：是，因为三个接缝仍存在；
- BESS 来源层正式候选数：1；
- TES/电加热器正式候选数：0；
- 完整 TAC：未闭合；
- E1–E6：仍不启动。

## 7. 代码与测试

- `src/tes_bess_boundary/cost_evidence.py`：支持并验证同作者官方扩展材料，参考审计只提升 Rahman；
- `src/tes_bess_boundary/formal_bess_costs.py`：Rahman 数值、边界、非电芯生命周期规格和统一价格转换；
- `tests/test_cost_evidence.py`：关联证据资格、精确分母与降级拒绝；
- `tests/test_formal_bess_costs.py`：原值、派生值、双计防护、2019 USD→2024 CNY 和阻断接缝；
- 本地完整回归：`263 passed in 34.57s`，仅保留既有 `.pytest_cache` 写权限警告；
- OpenBayes：尚未同步本轮 E0-D-13，远端最近基线仍为 `258 passed in 21.36s`。
