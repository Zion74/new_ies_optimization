# E0-D 寿命经济合同

更新时间：2026-07-13

状态：**现金流与年化计算核、固定容量年度接缝、2024 CNY 转换/成本分类、官方价格快照、TES 容量/温区映射、损失/辅助用电作者筛查、成本来源认证门、E0-D-14 完整 fixed-capacity BESS 生命周期账本，以及 E0-D-16 TES 全系统 EAC 上限内核均已实现；TES 正式参数表、系统级 TAC 项和内生容量仍待完成。** 本文件只锁定核算方法，不构成技术优劣结论。

## 1. 目的与边界

本合同解决三个会破坏 BESS—TES 公平比较的问题：

1. 不同寿命部件如何在同一项目期内处理更换和残值；
2. BESS 初始电芯、日历老化和循环老化如何在线性目标中只计一次；
3. 盐、罐、端口、泵和功率电子如何保持独立寿命账本，而不是统一套用一个 20 年寿命。

实现与测试位于：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/economics.py`
- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/model.py`
- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/tes_cost_mapping.py`
- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/tes_break_even.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_economics.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_annual_economics.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_tes_cost_mapping.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_tes_break_even.py`

E0-D-2 已在 `model.py` 增加可选年度分支：只有显式提供 `AnnualEconomicsSpec` 时，运行项才按逐期权重与 `dt` 年化，并叠加一次固定 EAC 和 BESS AC 放电吞吐成本；`economics=None` 继续走独立的 E0-C 单时域验证目标。该接缝仍是 fixed-capacity 年度化验证目标，不是正式 TAC。

## 2. 统一项目现金流

对项目期 \(N\) 和实折现率 \(r\)：

\[
d_t=(1+r)^{-t}
\]

\[
PVA_N=
\begin{cases}
\dfrac{1-(1+r)^{-N}}{r},&r>0\\
N,&r=0
\end{cases},
\qquad
CRF_N=PVA_N^{-1}
\]

代码使用 `log1p/expm1` 的数值稳定形式计算极小正折现率。所有组件必须使用同一项目期、实折现率、币种和价格基年。

对组件 \(j\) 的单位容量、质量或功率：

\[
PV_j^{cap}=c_{j,0}
+\sum_{kL_j<N}c_{j,rep}(1+r)^{-kL_j}
-S_{j,N}(1+r)^{-N}
\]

更换只发生在 \(kL_j<N\)；若寿命恰好在项目末结束，不在项目末再购置设备。最后一个在役 vintage 的直线剩余寿命比例及残值为：

\[
u_j=\max\left(0,\frac{t_j^{last}+L_j-N}{L_j}\right)
\]

\[
S_{j,N}=\rho_j u_j c_j^{last},\qquad \rho_j\in[0,1]
\]

固定运维按每年年末支付：

\[
PV_j^{FOM}=f_jPVA_N
\]

\[
C_j^{ann}=CRF_NPV_j^{cap}+f_j
\]

因此，已经是“元/年”的 FOM 不再乘第二次 CRF。初始、替换、残值和 FOM 在审计表中分别报告，但进入目标时只使用一次全包年化系数。

## 3. BESS 电芯两锚点校准

电芯经济容量基准固定为内部名义电量 \(E_B\)，单位必须是 `MWh_internal`。交流侧可交付比例为：

\[
q_B=\eta_d(SOC^{max}-SOC^{min})
\]

年度吞吐量只使用 PCC 交流侧放电：

\[
\Theta_B=\sum_t\omega_tP_t^{B,dis,AC}\Delta t
\]

不能再对 \(\Theta_B\) 乘除放电效率，也不能改用充电量、SOC 变化或充放电之和。

设日历寿命为 \(L_{cal}\)，交流侧等效循环寿命为 \(N_{cyc}\)，预注册参考循环强度为 \(\nu_{ref}\)：

\[
\delta(\nu)=\frac{1}{L_{cal}}+\frac{\nu}{N_{cyc}},
\qquad
L_{eff}(\nu)=\delta(\nu)^{-1}
\]

先用完整项目现金流分别计算：

- \(A_0=A(L_{cal})\)：零循环、仅日历寿命下的电芯资本 EAC；
- \(A_1=A(L_{eff}(\nu_{ref}))\)：参考循环强度下的电芯资本 EAC。

两者均包含初始电芯、计划更换和项目末残值。BESS FOM 按 SCI 公式中的独立 \(C_B^{FOM}\) 另建非电芯账本，禁止放入这两个锚点。

\[
c_E^{cal}=A_0
\]

\[
c_E^{cyc}=\frac{A_1-A_0}{\nu_{ref}q_B}
\]

\[
C_{cell}^{ann}=c_E^{cal}E_B+c_E^{cyc}\Theta_B
\]

\[
\Theta_B\le\nu_{ref}q_BE_B
\]

该合同保证零吞吐时仍回收完整的零循环电芯现金流，在参考吞吐时严格回收参考锚点现金流。循环系数只支付循环导致的提前更换和残值变化；电芯不得再进入通用 replacement portfolio。固定寿命敏感性使用 \(c_E^{cyc}=0\)，但电芯更换仍只在其唯一寿命账本中出现。

## 4. 非电芯组件 portfolio

每个 `asset_id` 只有一个 canonical ledger，容量缩放后同时公开：

- 初始投资 PV；
- 更换投资 PV；
- 残值抵扣 PV；
- FOM PV；
- 资本净 NPV 与总 NPV；
- 年化资本、年化 FOM 与总 EAC。

目标 portfolio 至少分别包括：

- BESS：充电功率电子、放电功率电子、独立 FOM 和辅助系统；
- TES：盐、HT/MT/LT 三类罐容、电加热器、高品位蒸汽换热器、中品位蒸汽换热器、盐—水/蒸汽发生与回送系统、供热换热器和泵。既有汽轮机复用不重复计初始资本成本；只有新增独立发电子系统的敏感性架构才登记 `new_power_block`。

不同组件允许不同寿命、替换成本、FOM 和残值，但不允许不同项目期、折现率、币种或价格基年。`BESS_CELL` 是结构性资产类型：generic portfolio 永久拒绝该类型，也拒绝与已校准电芯相同的 `asset_id`。所有 portfolio ledger 会在接受前重算并核对，避免伪造负成本或修改冻结对象后改变技术赢家。

当前泵尚无可审计的独立安装容量驱动，故方法核支持其独立账本，但正式参数 portfolio 不得在辅助用电和工程基准明确前凭空映射到盐量或任一端口。

## 5. 独立合成金标准

这些数字只用于验证公式，不代表真实设备参数。

### 5.1 部件更换、残值与 FOM

20 年、10% 实折现率，初始成本 1000，寿命 7 年，更换成本 800，FOM 20/年，直线残值全回收：

- 更换年份：7、14；
- 第 20 年剩余寿命：\(1/7\)；
- 资本 EAC：`188.4291593547`；
- FOM EAC：`20.0000000000`；
- 总 EAC：`208.4291593547`。

### 5.2 BESS 两锚点

20 年、10%，单位电芯成本 100，\(L_{cal}=10\) 年，\(N_{cyc}=1000\) EFC，\(\nu_{ref}=100\) EFC/年，\(q_B=1\)：

- \(A_0=16.2745394883\)；
- \(A_1=26.3797480795\)；
- \(c_E^{cyc}=0.1010520859\) CNY/MWh_AC。

当 \(q_B=0.8\) 时，两个锚点不变，循环系数变为 `0.1263151074 CNY/MWh_AC`；2 MWh 内部名义容量的年度 AC 吞吐上限为 160 MWh，达到该上限时年成本仍严格等于 \(2A_1\)。该非单位效率算例专门防止 AC 因子被漏乘或重复乘。

## 6. 参数证据状态

E0-D-8 已形成可审计证据组合 v0.6、官方价格快照、TES 容量/温区、五路径拓扑、MT→LT 夹点和 MT 归一化三点候选合同，但当前仓库仍不能直接提供完整的正式参数表：

- 旧 `_ch4_*` 使用统一 `8%/20年` 和聚合 TES 功率/能量成本，没有 FOM、替换、残值及分部件寿命，禁止复用为正式合同；
- 王滩 `30184 万元 / 480 MWh` 是聚合工程投资锚点，约为 `629 元/kWh`，不能再与盐、罐、泵、换热器分项成本叠加；旧代码中的约 `438 元/kWh` 来自欠定拆分和外推，不是原始项目数据；
- 高等级文献已给出罐/盐/循环/电加热/蒸汽发生系统的分项成本、项目寿命和 FOM 范围，但多项未报告统一价格基年，尚需完成体积、密度、扬程、换热面积、温区和币值转换；
- BESS 已核验 cell & pack、PCS、BoP、施工、FOM、日历/循环寿命和退化候选；Bahloul Table 9 数值追溯至 PNNL-28866 并经 `Energies` 二次整理，降为交叉检查，其 VOM 单位冲突已永久排除；
- Schmidt/Joule 与 Klasing/Applied Energy 等系统级成本只作聚合校准，不得与其内部件成本叠加；
- 原模糊 `power block` 成本项已在代码中修正为 `salt_to_steam_generator / existing_turbine_reuse / new_power_block` 三类结构角色；正式数值仍待证据换算。

因此，本切片仍不设置“看似真实”的默认成本。参数检索继续遵循用户指定的 Energy 及以上等级门槛，正式引用检索使用 `$instsci`；详细证据层级见 `e0_parameter_evidence_portfolio.md`。

## 7. 已实现的 E0-D-3 价格与成本分类合同

统一价格基年固定为 2024 年不变价人民币。`PriceBasisConversion` 只接受大写 ISO 4217 币种、正的明确价格年、同一价格指数序列的源/目标值、目标币/源币汇率，以及价格指数和汇率序列标识。`convert_lifecycle_cost_spec` 采用：

\[
K=\frac{I_s(2024)}{I_s(y)}FX^{2024}_{\mathrm{CNY}/s}
\]

同时转换 `initial_cost_per_unit`、显式 `replacement_cost_per_unit` 和 `fixed_om_per_unit_year`，寿命、残值比例和容量单位不变。返回的 `LifecycleCostConversion` 会重算并拒绝被篡改的 converted spec。年度 `AnnualEconomicsSpec` 进一步只接受 `CNY / price_base_year=2024`；它不调用网络，也不把发表年或预测年自动解释为价格年。

TES 发电回路使用三类 `LifecycleAssetClass`：

- `SALT_TO_STEAM_GENERATOR`：新增盐—水/蒸汽发生和回送系统；
- `EXISTING_TURBINE_REUSE`：既有汽轮机复用，初始与更换资本成本必须为零，允许证据支持的增量 FOM；
- `NEW_POWER_BLOCK`：新增独立发电子系统，仅用于相应敏感性架构。

只要 portfolio 使用任一上述角色，就必须恰有一个盐—蒸汽发生系统，并在复用汽轮机和新增 power block 之间恰选一个。TES 电输出端口大于零时，`E0CCase` 不仅拒绝缺失该分类的年度经济输入，还要求分类涉及的盐—蒸汽发生系统与复用/新建动力系统装机量都严格大于零，防止用零容量占位规避成本；热侧-only TES 不强制构造虚假的发电回路成本。

## 8. 已实现的 E0-D-4 官方快照合同

`风光火+熔盐储热/数据采集/e0d4_price_basis_2024/` 保存规范 snapshot、manifest 和可归档的一手响应。`load_price_basis_snapshot()` 校验 snapshot 与逐源 SHA-256，拒绝篡改、目录逃逸、未登记来源和同币种重复指数序列；`OfficialPriceBasisSnapshot.to_conversion()` 只对已登记的币种和价格年生成 `PriceBasisConversion`。当前最小快照使用 BLS CPI-U、Eurostat EA20 HICP、国家统计局 CPI/年度人民币汇率和 ECB EUR/CNY 年均参考汇率。CPI/HICP 作为明确声明的一般价格代理，后续必须补设备价格指数敏感性；未知价格年仍为阻断条件。

Bahloul Table 9 的 `0.3 cent/kW-yr` 已由 PNNL-28866 原文核查为错误转录/表头口径：PNNL 汇总表登记的是按放电吞吐量归一的 `0.03 cents/kWh`，且正文自身保留 `0.3` 与 `0.03` 的不一致讨论。两者均不作为 Energy+ 核心 VOM 参数，Bahloul 值永久排除。

## 9. 已实现的 E0-D-2 接口

年度计分时域合同为：

```text
AnnualHorizonSpec
├── period_weights
└── expected_annual_hours = 8784
```

`period_weights` 只表示当前单块模型中的计分时段，必须是严格正数，并与 `dt` 严格闭合到 8784 h；不得静默归一化或改报 8760 h。E5 所需的不计分预热段不能用裸零权重伪装，后续必须由 `representative_weeks` 的显式 period-role / warm-up 与状态边界合同实现。

模型外已校准的线性项按下式接入 Pyomo：

\[
C^{storage}=C^{fixed,ann}+c_E^{cyc}\Theta_B
\]

其中固定年化成本只加一次，年度吞吐只使用 PCC 交流侧放电并按每期自身的 \(\omega_t\) 与 `dt` 加权；EFC 上限使用同一 \(q_B=\eta_d(SOC^{max}-SOC^{min})\) 基准。固定寿命敏感性必须从主两锚点校准对象派生，因此只把循环单价置零，不得改变 EFC 可行域。年度模式强制 CHP 初末状态闭合，并强制启用的 BESS/TES 循环闭合。

`E0CResult.annual_economics` 公开年度燃料、弃电、BESS AC 吞吐/上限、运行成本、非电芯固定成本、电芯日历成本、循环成本和总成本；原 `fuel_tce / curtailment_mwh / pcc_export_mwh` 继续表示建模时域统计。`economics=None` 不创建任何 `annual_*` 组件，现有 E0-C 目标、调度和 canonical CSV/manifest 哈希保持不变。

E0-D-11 后本地完整回归为 `258 passed in 38.13s`，OpenBayes 为 `258 passed in 21.36s`。MT 三点仍是作者敏感性，`MT→LT` 仍是 proposed extension；库存—环境温差损失、固定伴热、五路径泵耗、PCC 防双计、三 MT 损失标定、三档底层液压泵耗、统一运行审计和成本证据认证门已经实现。NREL 2022 ATB 的 4 h utility BESS 已形成可复现的 2020 USD 双分母敏感性账本，并禁止含 augmentation 的 FOM 与第二套 replacement ledger 重复计费；但该工程锚点 `formal_baseline_eligible=False`，不能关闭 Energy+ 正式成本缺口。杨凌正式温压/泵系统数值及正式成本仍未闭合；年度目标仍需补齐合格的明确价格年真实成本、VOM、碳价和电力结算后才能称为正式 TAC。

E0-D-14 当前更新：Rahman 负责 2019 USD 电芯与非电芯价格，Schmidt *Joule* 负责 13 年/3250 EFC 非价格寿命参数；replacement 只由 calendar+AC-throughput 核生成。`2.74 USD_2019/MWh` 按 AC 放电侧转换并与退化 cycle cost 分列，PCS 常数单价只允许 5–100 MW。代码现可构造完整 fixed-capacity BESS `AnnualEconomicsSpec`；加入 E0-D-15 TES 正式成本门禁后的本地完整回归为 `273 passed in 30.31s`（关闭 pytest cache）。这只关闭 BESS 生命周期子账本，不等于 TES 与系统级正式 TAC 已闭合；OpenBayes 尚未同步 E0-D-14/15 代码。

E0-D-16 当前更新：`tes_break_even.py` 在剔除全部 TES 所有权成本后，按同情景、同服务、同 8,784 h 时域和同 2024 CNY 已知成本范围，计算全系统 TES 最大 EAC 上限；人工弃电罚值不得计入运行价值，容量归一化不得反解部件价格。当前 TES 正式 portfolio 与非 TES 系统成本范围均未闭合，因此只允许探索性阈值，不改变正式 TAC 门槛。本地完整回归为 `279 passed in 31.57s`，OpenBayes 尚未同步 E0-D-14–D-16 代码。
