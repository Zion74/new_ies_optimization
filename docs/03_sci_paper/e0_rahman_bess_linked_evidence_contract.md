# E0-D-14 Rahman BESS 关联证据与模型接缝合同

更新时间：2026-07-13
状态：**关联证据政策、三个模型接缝与 fixed-capacity BESS 生命周期账本均已闭合；TES 正式成本、系统级完整 TAC、内生容量与 E1–E6 仍未闭合。**

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

## 5. 三个接缝的预注册结论

### 5.1 电芯 replacement 与退化

Rahman 在 80% DOD 下使用：

\[
N_{cycle}=2731.7DOD^{-0.679}\exp[1.614(1-DOD)]
=4389.6022.
\]

按 365 次/年得到约 12.03 年 replacement interval。该逻辑只有 cycle damage；当前模型已经采用 calendar + AC-throughput 双锚点。如果直接同时导入 12.03 年 replacement，会双计退化。

E0-D-14 预注册并实现第二种口径：Rahman **只负责 cell CAPEX**；Schmidt et al., *Joule*（DOI `10.1016/j.joule.2018.12.008`）提供 13 年 shelf life 与 3250 full-equivalent cycles 两个非价格参数；所有 replacement timing 只由现有 `BESSCellDegradationSpec → BESSCellCostCalibration` 核生成。Rahman 的 4389.60 cycle-only 更换周期不进入正式基线，只可作为独立敏感性，因此不存在第二套 replacement 账。

### 5.2 VOM 吞吐侧

Rahman Table 3.5 的 `2.74 USD/MWh` 转引自 Zakeri & Syri, *Renewable and Sustainable Energy Reviews* 42 (2015) 569–596（DOI `10.1016/j.rser.2014.10.011`）。Rahman 的 LCOS 方法把 `Eout` 定义为每循环放电电量；底层工程定义也把 battery variable O&M 表述为与 discharged electrical energy 成比例。故 E0-D-14 披露并预注册 `AC_discharge` 口径。

该项经同一价格桥转换为 `23.9428497032 CNY_2024/MWh_ac_discharge`。模型新增 `annual_bess_variable_om_cost_cny`，与 cell degradation cycle cost 共用唯一的 `annual_bess_ac_discharge_throughput_mwh`，但二者是不同物理含义的系数并分别列账，各计一次。

### 5.3 PCS 规模曲线

Rahman 使用 5 MW PCS 模块，并对并联模块使用 95% multiplicity learning；EPRI-DOE Handbook 1001834 给出单模块尺度关系和 multiplicity 概念，但没有给出可唯一复现的 95% 并联公式。为避免伪造 PWL，E0-D-14 预注册 `constant_unit_cost_within_source_range`：

- `206.81 USD/kW` 只允许用于 Rahman 研究覆盖的 5–100 MW；
- `<5 MW` 或 `>100 MW` 的正式构建直接拒绝；
- 精确 multiplicity PWL 标记为“不受当前来源支持”，仅在获得唯一公式后进入 E6 尺度敏感性。

## 6. 当前门槛

- `formal_source_qualified=True`：是；
- 来源对象 `formal_portfolio_ready=False`：仍为是，因为它只表示“尚未选择模型口径”的原始证据层；
- `RahmanBESSResolvedJoinContract.formal_fixed_capacity_ready=True`：是，表示三个接缝已按预注册口径闭合；
- BESS 来源层正式候选数：1；
- TES/电加热器正式候选数：0；
- fixed-capacity BESS 生命周期子账本：可完整构造；
- 系统级完整 TAC：未闭合，阻断项已转移为 TES 正式成本、碳/电力结算与后续容量规划接口；
- E1–E6：仍不启动。

## 7. 代码与测试

- `src/tes_bess_boundary/cost_evidence.py`：支持并验证同作者官方扩展材料，参考审计只提升 Rahman；
- `src/tes_bess_boundary/formal_bess_costs.py`：Rahman 数值、边界、三接缝策略、完整 fixed-capacity BESS `AnnualEconomicsSpec` 构建与 5–100 MW 拒绝门；
- `src/tes_bess_boundary/economics.py`：AC 放电侧 `BESSVariableOMSpec`、价格转换及年度经济合同；
- `src/tes_bess_boundary/model.py`：退化成本与 VOM 分列，并在年度总成本中各计一次；
- `tests/test_cost_evidence.py`：关联证据资格、精确分母与降级拒绝；
- `tests/test_formal_bess_costs.py` 与 `tests/test_annual_economics.py`：寿命所有权、VOM 分母、PCS 范围、完整构建和 HiGHS 年度目标回归；
- 本地完整回归：`268 passed in 32.53s`，仅保留既有 `.pytest_cache` 写权限警告；
- OpenBayes：尚未同步本轮 E0-D-14，远端最近基线仍为 `258 passed in 21.36s`。
