# E0 数据、物理与 HiGHS 验证状态

更新时间：2026-07-14

状态：**E0-A 通过；E0-B 正式带标志数据集通过；E0-C 固定容量统一调度与正式热需求适配/真实双机 24 h 桥接通过；E0-D-1–D-20 已闭合相应数据、物理、成本门、同 PCC 燃料空间和非燃料成本证据审计；E0-D-21 已闭合来源无关的影子成本区间传播与翻转阈值；E0-D-22 已闭合选择轨迹的逐时 PCC 与价差暴露；E0-D-23 已完成替代可接受调度的联合双向极值；E0-D-24 已建立 16 账户统一证据路线；E0-D-25 已建立项目原始证据接收与隐私隔离门；E0-D-26 已完成约束缩放、严格容差、条件面证人和有限界分离；E0-D-27 已完成固定支持方向与等价正负符号重构。E0 总门槛仍未通过。** D27 将 24 h 全局严格包络修正为 `26,010.171143–26,010.174929 MWh/a`，并将 336 h 最大严格区间收紧为 `[36,382.462799,1,081,649.139331] MWh/a`，但外界仍宽。D24 严格正式账户为 `0/16`；D25 当前三类运行账户 `missing`、CHP 为 6/14 字段的 `partial`，因此 `ready_account_count=0/4`。D25–D27 均不指定项目价格、不产生正式 TAC 或技术赢家；内生容量及 E1–E6 仍不得启动。

## 1. 已实现代码

独立包位于：

- `风光火+熔盐储热/tes_bess_boundary/`

当前已实现：

- `data.py`：8784 h 时间覆盖、数值范围、电功率和热量恒等式审计；
- `raw_heat.py`：只读取原始供热 Excel 第一工作表 A 列，保留源路径、SHA、工作表、行号和原始单元格，并严格检查 10 min 网格、重复点和异常值；
- `heat_dataset.py`：锁定两份源文件 SHA，输出完整源行台账、52,704 点 canonical 网格、8,784 小时三口径热数据和 manifest v2；
- `heat_adapter.py`：先校验完整 8,784 h 网格、三候选列、每小时六样本、八类质量计数及 manifest v2/源 SHA，再显式生成 `net_clipped` 主口径和 forward/zero 两个敏感性口径；支持半开窗口、全年/窗口双修改审计与跨平台确定性 CSV/JSON；
- `heat_bridge.py` / `heat_bridge_cli.py`：生成三份全年适配产品，运行两个正交 24 h 窗口 × 三口径的六个真实杨凌双机 No-storage/HiGHS 桥接诊断；规范结果与运行时间 sidecar 分离；
- `economics.py`：统一项目 NPV/EAC、计划更换、末年残值、FOM、BESS 日历—AC 放电吞吐两锚点、固定寿命敏感性、多部件 portfolio、币种/基年/项目期同质性和结构性电芯防双计；E0-D-3 又增加显式价格指数+汇率转换审计、2024 CNY 年度口径，以及 `salt_to_steam_generator / existing_turbine_reuse / new_power_block` 三类成本角色；
- `price_basis.py`：加载 E0-D-4 官方价格快照，校验 manifest、snapshot 与逐源 SHA-256，拒绝篡改和同币种重复序列，并生成唯一 `PriceBasisConversion`；
- `cost_evidence.py`：按期刊层级、价格基年、容量分母、技术边界、底层出处和允许用途执行正式成本资格门，并验证同作者官方扩展 crosswalk；E0-D-15 将可审计一手报价与作者 bottom-up 区分，登记 Guccione 两个电加热器阻断候选、Klasing 2023 EUR 气体处理异拓扑项和 DLR 2020 EUR 两罐系统工程锚点；当前 16 条参考记录仍只为 Rahman BESS 颁发一个来源层证书；
- `formal_bess_costs.py`：固化 Rahman 2019 USD 原值、Li-ion footprint 派生围护基础成本、PCS/BoP/FOM/contingency 非电芯账本，并实现三接缝策略、统一价格转换和完整 fixed-capacity BESS 年度经济构建；
- `sensitivity_cost_anchors.py`：加载 E0-D-11 NREL/OEDI 工作簿哈希包，保留 BESS `USD/kW_DC + USD/kWh_usable,DC` 双分母，闭合 4 h CAPEX/FOM，执行 2020 USD→2024 CNY 转换，并禁止含 augmentation 的源 FOM 与独立 replacement ledger 双计；
- E0-D-12 文献审计由 E0-D-13 更新：机器矩阵 13 个候选中 Rahman 为唯一 `formal_candidate=true`；Guccione、Ahmadi/PNNL 与其他 TES 来源保持原降级；
- `tes_cost_mapping.py`：将同一批盐、完整 LT→HT 显热库存、三罐和五端口转换为唯一 `kg / kWh_th / kW_el / kW_th` 容量账本；按部件温段检查文献温区，并把 bottom-up 成本安全绑定到寿命 portfolio；
- `formal_tes_costs.py`：要求盐、三罐/循环、两类充热、发电/供热放热、power-block retrofit、项目附加费和寿命项等 12 个账户逐项闭合；Klasing/Li/DLR 聚合锚点不能满足部件账户，多 DOI 复合路线需要另行批准；当前 12 账户全部阻断，不生成 TES 正式证书；
- `tes_break_even.py`：在同一情景、服务、8,784 h 时域和成本范围下比较无 TES 架构与 TES/HYBRID，剔除全部 TES 所有权成本后计算全系统最大 EAC 上限，并报告燃煤、弃电、PCC 外送和 TES 辅机差值；拒绝人工弃电罚值、缺热、非最优结果、零容量 TES 和跨口径比较；四个容量归一化只重构同一系统上限，不反解部件单价；
- `tes_break_even_adapter.py`：把实际 E0-C 年度解保守适配到 E0-D-16；要求显式弃电服务、零罚值、最优 HiGHS 与平衡/循环残差通过，并剔除全部 TES 资产类别；当前系统 VOM、碳、电力结算与 TES VOM 未闭合，故强制探索性主张；
- `e0d17_exploration.py`：哈希锁定正式热输入和旧 2019 风光形状，使用成本主目标、固定主目标整数 incumbent 后的弃电次目标，保留 E0-D-17 的 24 h 零 gap 历史基线；
- `e0d18_performance.py`：为 CHP PWL、启停和 TES Big-M 提供显式紧化 formulation；24 h 零 gap 回归，336 h 候选按 0.5% 主 gap 合同求解，并从 primal/dual cost bound 导出保守 EAC 区间；
- `e0d19_same_pcc_service.py`：从无储能自然基线派生年度 PCC 外送目标，在同供热与同弃电上限下强制比较架构和 TES 候选交付同一年度电量；固定平价结算严格抵消。336 h 先求零平均功率偏差可行解并 warm start 未改动的燃料目标，继续报告 primal/dual EAC 区间；
- `operating_cost_evidence.py`：覆盖分时电力结算、碳配额履约、CHP VOM、TES VOM 四个非燃料账户，逐项审计项目范围、数值输入、成本边界、变动驱动和技术映射；哈希锁定杨凌 H/J/M 原始单元格并诊断燃料重叠风险，只有四账户全部通过才允许颁发正式组合证书；输出确定性 CSV/manifest，不生成 TAC 数值；
- `shadow_cost_robustness.py`：哈希锁定 E0-D-19 schema v2 canonical，联动 E0-D-20 四账户门控，将有符号账户区间或未分配合计不利成本传播到燃料空间；按调整后上下界判定稳健为正、跨零不确定、精确盈亏平衡或稳健为负，并导出只允许 sensitivity 的 LF 规范 CSV/manifest；
- `pcc_settlement_exposure.py`：从 D19 同服务重求解导出的逐时 PCC 轨迹计算年化重新分配电量、固定平价恒等式、显式价格序列结算差和任意有界价格跨度包络；写出器哈希锁定 D19 canonical 并拒绝聚合结果漂移，明确当前轨迹未证明连续解唯一；
- `alternative_dispatch_envelope.py`：哈希锁定 D19/D22，将两架构嵌入同一联合 MILP，在主成本/弃电 cap 内重新开放整数模式并极小化/极大化 PCC 年化 L1 重分配；336 h 复现 D19 三阶段状态作为纯 warm start，按目标方向保留 primal/dual；
- `d26_numerical_certification.py`：把年度成本/弃电准入行无量纲化，统一使用 `1e-9` 可行性容差，分开 D19 条件整数面与开放整数模式；移除已固定变量的冗余 integrality，以条件面极值回灌全局 warm start，并强制全局 incumbent 支配已知子集证人；`termination` 与有限界证书分离，PCC L1 从时序独立重算；
- `d26_certification_bundle.py`：校验 8 个 D26 探针的身份、严格残差、科学边界和条件面证人，导出两窗口确定性 CSV、manifest 与非规范 execution sidecar；
- `d27_direction_generation.py`：对固定符号方向移除绝对值符号二元并重新开放主整数模式，从返回轨迹重算可行 L1；全局最大化使用正负差值分解与单符号二元，并严格分离方向 dual 与全局 dual；
- `d27_certification_bundle.py`：校验 24 h 联合探针和 336 h 方向/全局探针的身份、严格残差、证人支配和科学边界，导出两窗口最大端确定性 CSV、manifest 与非规范 execution sidecar；
- `formal_tac_evidence_route.py`：连接 D15 的 12 个 TES 与 D20 的 4 个非燃料账户；分别记录严格候选阻断、项目原始数据要求、Energy+ 与官方工程层级、期刊指标和禁止用途，并确定性导出 16 行账户路线、5 条公开来源和自哈希 manifest；
- `project_primary_evidence_intake.py`：把 D20/D24 的四个项目运行账户转为 51 项字段要求、四账户当前 coverage、空白提交模板和隐私 manifest；现有杨凌工作簿只以不透明 ID、哈希和最小单元格元数据登记，不导出金额；接收证书显式保留 `formal_validation_required=true`；
- `tes_topology_evidence.py`：逐条登记五个 TES 活跃路径的 Energy+ 直接证据、降阶映射、模块化合成或本文扩展；阻塞路径拒绝正式认证，`MT→LT` 供热级联必须显式披露为 proposed extension；
- `tes_heat_delivery.py`：区分杨凌现场、核心参考情景和作者敏感性温度来源，审计 MT→LT 两端夹点、HITEC 液态/材料上限、库存—端口双重热功率上限及盐/水流量；
- `tes_temperature_scenarios.py`：将 MT 转写为低品位显热占比，预注册 25%/50%/75% 三点作者敏感性，阻止来源误标，并逐点调用夹点合同认证；
- `tes_loss_auxiliary.py`：登记损失/辅机参数身份，以库存和每期环境温差构造任意步长下的线性复合损失，区分固定伴热补偿与净库存降级，并按五条盐路径计算泵辅助电功率；
- `tes_loss_calibration.py`：保存 Trevisan/Klasing 系统级锚点，注册低/基准/高作者情景，按 232.5/285/337.5 °C 三个 MT 分别反求 24 h 等留存损失率；聚合泵耗只保留为“聚合反推统一系数”审计量，不再充当物理标定；
- `tes_pump_calibration.py`：以 Trevisan 的 200 kPa、回路压损 20%、单个主动部件压损 5% 和泵效率 90% 构造 40/50/200 kPa 作者情景，以 Wang HITEC 密度/比热关联式生成五路径 `kWh_e/t`，并输出 45 MWhth、365 次/年标准双服务循环的 3×3 确定性校准产物；
- `components/chp.py`：台账顶点凸包、毛/净电口径、三种显式 98–105 MW 规则、非凸煤耗相邻段 PWL 和证据受限 UC；保留 one-hot/二进制启停历史默认，并为 E0-D-18 提供精确对数 PWL 与连续启停包络；
- `components/bess.py`：PCC 交流侧充放电、SOC 和可交付电量；
- `components/molten_salt.py`：HT/MT/LT 盐量守恒、两段非重叠焓、充热输入能量、分罐模式，以及原始损失/伴热补偿/净降级/泵耗的线性表达；支持由端口反算的路径流量上界和零容量路径模式固定；
- `solver.py`：只使用 `appsi_highs` 的确定性求解配置；
- `model.py`：No-storage / BESS / TES / Hybrid 构建期隔离、统一 PCC 与有效热边界、TES 五端口上限、显式 CHP 初末状态和 fixed-capacity 求解；TES 伴热与泵耗只在 PCC 扣除一次，并按调度时域或年度典型时段权重公开五路径吨位、原始/补偿/净热损失及泵耗/伴热 MWh 审计；年度分支公开可用新能源、弃电与 PCC 外送服务，按平均功率缩放严格年度外送等式，并记录零偏差可行性 warm start、主问题 bounds 与固定整数弃电次目标；TES 电输出端口为正时仍必须提供完整且互斥的发电回路成本分类；
- Pyomo 的 CHP、BESS、TES 小模型、四架构机制回归、线性表达和两种 HiGHS 接口检查。

未实现：

- 闭合 Rahman BESS 的 cell cycle-only replacement 与现有 calendar+AC-throughput 退化合同、VOM 吞吐侧和 5 MW PCS 模块/95% multiplicity 规模曲线；来源价格与主要非电芯账本已经闭合，不得再写成“Rahman 全文缺失”；
- 闭合 TES 12 账户正式成本寿命 portfolio；Guccione 电加热器真实报价仍缺报价价格年，但它不是唯一阻塞，罐/循环、两条蒸汽充热、盐—蒸汽发生、供热换热、power-block retrofit、项目附加费和寿命项也未闭合；DLR `20–22 EUR_2020/kWh_th-net` 只作两罐 Solar Salt 工程聚合校准；
- E0-D-9B-2 作者级筛查已闭合，但没有杨凌正式损失率、伴热比例、管网压降、泵曲线或五路径现场比泵耗；当前 40/50/200 kPa 与标准循环只能用于敏感性和量级审计，仍不能写成杨凌正式损失价值；
- 正式 endogenous capacity、将已实现的寿命现金流核按真实参数 portfolio 接入完整 TAC，以及低负荷煤耗规则敏感性；E0-D-24 已证明 16 账户均未严格闭合，D25 已把四个项目账户变成可交付请求但尚未收到正式记录，D21 只给出风险预算，D22/D23 只闭合暴露边界；本地 `price_sell/price_buy` 仍只是作者生成情景；
- 代表周、场景网格、全年回代和批量执行。

## 2. 测试证据

| 环境 | 范围 | 结果 |
|---|---|---|
| OpenBayes Python 3.10.18 隔离环境 | 原始热 Excel、正式构建/适配、真实双机桥接、CHP/储能物理、UC/PWL、四架构、寿命/年度经济、TES 证据与成本门、E0-D-17–D-27、严格数值证书及项目取证隐私门 | `340 passed in 26.74s`（关闭 pytest cache） |

D26/D27 使用 `Pyomo 6.10.1`、`highspy 1.15.1`，求解器仅为 HiGHS。OpenBayes 包路径为 `/root/e0-b-20260711-019f4f64/tes_bess_boundary`，正式数据合同仍为 `TES_BESS_E0B_FORMAL_DIR=/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024`。D27 原始运行位于 `/root/e0-b-20260711-019f4f64/e0d27_direction_generation/`，规范汇总位于 `/root/e0-b-20260711-019f4f64/数据采集/e0d27_direction_generation/`；本轮未上传本地受限资料。

E0-D-1 历史同步快照的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/economics.py`：`913717909e76f64e2cd3426c9dd339fe7ea7dd9f631671fe234ac1a2cd76a95d`；
- `tests/test_economics.py`：`9132219a632b1f6c1496d235d5b420c5b33bff5a440bc419a46c3be07bb7783e`。

E0-D-2 已同步源码的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/economics.py`：`6bff1c0f879a35cdb8ad01525f736af53e58be10553f8caf6199a826f77c0625`；
- `src/tes_bess_boundary/model.py`：`635d4125c1e3cb92cfd80728fe17838e6d10e58fcb3f62f7e86812b670ad7508`。

已上传且本地/远端匹配的更新测试 SHA-256 为：

- `tests/test_annual_economics.py`：`387fb036798be15a8c3d6233560c4b39cf70224f4d6c534bb8e173b068c60885`；
- `tests/test_heat_bridge.py`：`c2d0724cf1bee0673d593bdef8e21a2310228c0de777c39b54769e442831443d`。

E0-D-3 当前同步文件的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/economics.py`：`aa44a2b1ea9488871fe3abee66e931d059895c06861b6dac9861968c4b2a6e40`；
- `src/tes_bess_boundary/model.py`：`b471f8c4edc215c42821fb7ca6df16cadcf10f72a59312218a724e173fba9c01`；
- `tests/test_economics.py`：`70a15d86f9ec7d03d6df6dbdfe70c9984e0561722669bad14259a900273714`；
- `tests/test_annual_economics.py`：`776ff833d39ae54be4328939225e17534549e30277e1603136dc52c5ebef044f`。

E0-D-4 当前同步文件与正式快照的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/price_basis.py`：`086b13dbc41c2862a8f91f092e360fc3967139e027bbd468f02f6e5bd53a4798`；
- `tests/test_price_basis.py`：`de790691a4073fd187892f30af7801c1c05825eb96272b3ce935db9cb1b67ef8`；
- `formal_data/e0d4_price_basis_2024/manifest.json`：`b18105db898afa49dfb9e76d0c652d9479115359c64bfc36548046e5fbf1e69b`；
- `formal_data/e0d4_price_basis_2024/price_basis_snapshot.json`：`5667aab931cdee997d0e67281a4cbff9dfb9db0f864c5d1953d865cea18744a8`。

E0-D-5 当前同步文件的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/tes_cost_mapping.py`：`9a95e988191f8b6cfbada5d733226c594eb36dd6cfffe6f80e160d6b0f4022e7`；
- `tests/test_tes_cost_mapping.py`：`365d711cfe56c455a756b9616f5bb5b06633e20d9c77281ea9fd6ba0c46b942c`。

E0-D-6 当前同步文件的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/tes_topology_evidence.py`：`8b75fbf094efcdb8e40becac74a0baf1ff43c53789bd585382425168d491ad9c`；
- `tests/test_tes_topology_evidence.py`：`120747936d19c19270727363bc3f3747179126d5d01acacb7dffd88fa6fdbb37`。

E0-D-7 当前同步文件的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/tes_heat_delivery.py`：`b50fadddbe23757620282f72e8c3c95fa6ac1b8298cb803aa112f46faf19592b`；
- `tests/test_tes_heat_delivery.py`：`fcfce3bad881d42961e2b2dd05e9c723e62df07b5f248440db963f900f16ad67`。

E0-D-8 当前同步文件的本地/远端 SHA-256 为：

- `src/tes_bess_boundary/tes_temperature_scenarios.py`：`724252cf6c89fa5508a4a28d07e15099048dcf69e0932d63531a1b86869e960b`；
- `tests/test_tes_temperature_scenarios.py`：`485be545e60d64836fe4beb5814bd7508e532ee7965b9e0b8f9a70ea6cf1afe5`。

E0-D-9A/9B-1/9B-2 文件的本地/远端 SHA-256 见 `e0_tes_loss_auxiliary_contract.md`；E0-D-11 公开工作簿证据包哈希见 `e0_sensitivity_cost_anchor_contract.md`，本地/远端一致。E0-D-14 本地 SHA-256 为：`economics.py` `db0198ae5f29398e616b4986fb1370aee916e47d94f1f099ab1bcd7fe03392bf`、`formal_bess_costs.py` `37e132a684fa58736e93212caea0a1b44d0c91f7da7303c0eef7d75859cacaa3`、`model.py` `29cb4ef86c6f606bd38c65d17da93616529bab85f727fe1c318be5f375e7e568`、`test_annual_economics.py` `d432d27c529c2350a6259bd0cab01bec742cb0a62056fdd1cfbc0e5b28f9db7e`、`test_formal_bess_costs.py` `d66610b280c7b941f940dbc675211fb32795067ae6e23e4a7e6c61e921cb474b`。

E0-D-15 本地 SHA-256 为：`cost_evidence.py` `85797bb4479f1f3110826a349b0bc94165036fa241c19da4d2ea65397f101024`、`formal_tes_costs.py` `38effbf57694c1147c19010878b5eb01f0ee8f21d0f288faf026cc2909df79f8`、`test_cost_evidence.py` `9350d82145ab4644da0f541bd9264f15219178c0cb9ab1ed3e478aae2fe04836`、`test_formal_tes_costs.py` `de35ebaeeb6415e3168bb5a1405a630d6129c70eedcc1e00953013a06f00ae45`。本地完整回归为 `273 passed in 30.31s`（关闭 pytest cache）；远端尚未同步 E0-D-14/15 代码。

E0-D-16 历史快照 SHA-256 为：`tes_break_even.py` `28bcf21d679093d979b90d2a2d10ca37ca13687e9e3ad4f0f06c79d49ee2ab79`、`test_tes_break_even.py` `9bac9305f253a3ea3c91f1d05b1c98198dd7a69589e3598395ac0ce9149d9a2e`；当时本地回归为 `279 passed in 31.57s`。当前同步状态与测试基线以以下 E0-D-17 记录为准。

E0-D-17 SHA-256 为：`model.py` `1eee8aca7208a872c71f45475723a5853e9e5fec97d22d38c2948a790c4e93fa`、`tes_break_even_adapter.py` `d036ee89b7f836b5491fe6832353e631ffb39b899b146289e695345f5bbb8318`、`e0d17_exploration.py` `45b27180a9421f6273119adfdfd386d7349b38c183b1b6f87313425b9b416421`、`test_tes_break_even_adapter.py` `2e44a7d43e2576eb7ba4e6a01298e6f4f6ecd875e666fbf84c72f42834aa3ec7`。24 h 产物 `e0d17_tes_break_even.csv` 为 `ab2dbd3e77068826e41785f585ffe4e70c8ae4c72baaedde054428f265b780f3`，`manifest.json` 为 `5cec9f0c436bf3c5ea44e8d4cd170939c4fd4dc168c9f31e414feb92ca79a1e5`；本地/远端逐字节一致。

E0-D-18 当前 SHA-256 为：`components/chp.py` `6e16cedb711631fa03f7c647db6559c5a5f37eef46b2576a293fee968ff45b32`、`components/molten_salt.py` `7843c16d5ab42b229720b72258e2948c44eb508b05e6f9794547a0adb8f1068b`、`model.py` `647e412226ad936ab421fa5f153027107c431b4ce2b4f4d0315d43bd14b81cf0`、`e0d18_performance.py` `ebc6b8c9e277d3b30ddead1c2aab8bcc21b08d2c85813268402705cd3cab0d66`。双窗口产物 `e0d18_tes_break_even_interval.csv` 为 `2d99fdc742bf1f23ca26e9149dcbbf906d47057e0ecfd7d1155aa60c7e3c506d`，`manifest.json` 为 `2f70b67d9a04cde88b25630e1ab4e5e1e793887a4a47694e9001011d7b945fe4`；本地/远端逐字节一致。

E0-D-19 本地/远端 SHA-256 一致：`model.py` `f1a22c3e8e67e81483a78b17c88a6342ff5138637c148a784211f7dfc80adb70`、`e0d19_same_pcc_service.py` `dae128181193a10969cc35f566996590afbcd7fc18aae689db5b6b66611e42f0`、`test_annual_economics.py` `b13445b763c2e41546296dc4038d4d23ed2fb56ec0a1f825a0acdcf17982b393`、`test_e0d19_same_pcc_service.py` `9caf245c0795426ee7cdb9b49e868e98140eb5e3d9fac075b0cbb804e46db252`。schema v2 规范产物 `e0d19_same_pcc_service.csv` 为 `4b07e91b010fa9d5aa525f196037bbf0c93bae16ac74035f6ca32292e36cf786`，`manifest.json` 为 `c112c210aa9a86edfcb116f614c1f4a5da14f314a128e31ee329fbefd65aab63`；Windows/OpenBayes 逐字节一致。

E0-D-20 本地/远端 SHA-256 一致：`operating_cost_evidence.py` `539359ef6da639d2e634a35bd235b2787e5d8d278d61ef931d0fb11942ea63ca`、`test_operating_cost_evidence.py` `5c7c7b6d483cf1d7d2f799c3f0ab3606ad2107751c5d9224b7ef8e25f7a07614`。schema v1 规范产物 `e0d20_operating_cost_evidence.csv` 为 `0b67c3535dfc1321ff6a6eae9772677e5fa4b187ba0d803ad766ff11abb24f5b`，`manifest.json` 为 `f78d1c61ef89ae3ab8051b4d1dd16642eb3c32d78d214ba3afe2c4f72af06b4d`；Windows/OpenBayes 逐字节一致。源工作簿锁定为 `72d71cfeed7d8c3f3d564e00ca8bfdd47ee48228bf58ab3de5c9605added8fcf`，四账户 `formal_portfolio_ready=false`。

E0-D-21 本地/远端 SHA-256 一致：`shadow_cost_robustness.py` `1a56f3b7d8c0d8e457b3b3e5bff2d4f32a548de86c68f39c1fad0a279ba5ee95`、`test_shadow_cost_robustness.py` `c6d32bc7f726e2fac0b5102686e8e3e678ecdcd098909a63b506a2e2f1745a20`。schema v1 规范产物 `e0d21_shadow_cost_thresholds.csv`（10 行）为 `e56e1ee00925237f9b9137eed160662986a62f225065181630229daf42930ae9`、`e0d21_shadow_cost_stress.csv`（10 行）为 `6c17825508a50d4eb351776f3ef410cb9ac1859d45f983acef96233e76572334`、`manifest.json` 为 `b7f6e32507a697543a789ef92fa53f9a06969d970ae4f83783b450a5117b6a21`；全部强制 `allowed_use=sensitivity_only`、`formal_tac=false`。

E0-D-22 本地/远端源码与测试 SHA-256 一致：`model.py` `4a1dfe24a2242681862ab6f5dd2879f94abd23f49ac654ddc64e72613404d260`、`e0d19_same_pcc_service.py` `2a3bc7305f24dff595906c24c665c87e62990e635b4d11e9ec91eecd42861382`、`pcc_settlement_exposure.py` `bff1aaa6b2f871a560a800a5938d27ef95d395cefba172bf09be148d5fa1e800`、两份测试 `cb232b69fc2b5a39a938bb45aa80c0a5c02696ed59d064421ce42e79d3ca5ce0` / `d61a79942d7e88d68d3367f5948bd870bdf45023b98cd78ee753f7cf58925fa7`。schema v1 规范产物逐时轨迹（360 行）为 `ad196e3bce2c1f02287de74d42a61c91dd98f8703c753172f5acc014b655ccc2`、暴露汇总（2 行）为 `3f84d3b0ee4ef03c9edb4ccf395bedc2291262f2cb5e82746a001bcdce5a319f`、manifest 为 `74ed9edb644a40af1ca9ede489958a25e430fa3b87f8760e6bf6b358692b2f87`；`actual_price_path_assigned=false`、`trace_solution_uniqueness_proven=false`、`formal_tac=false`。

E0-D-23 最终源码/测试 SHA-256 为 `alternative_dispatch_envelope.py` `92fc66a4b6ba84bbeccc332f53adab68b3be40b4d11a4f7aa66e148394cea787`、`test_alternative_dispatch_envelope.py` `918a22fdbdd36ca0846e2ed464fc32978de8cd393a3f2852bd3989bf3d7cd172`。schema v1 规范产物极值 CSV 为 `7711d894e947ee9bc942606a0936e01b4bc5c3e7015cde9e65a7f5021dac4fbd`、manifest 为 `81e1b40c1e375791c3b57b7412dcc655280d1d9b54191c156320d452cd453448`，非规范 execution sidecar 为 `1157de7c8b9ac49d04b60f3ca0b9833cc422dbba0dd65d0b5674b0b771018a35`；`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-24 本地/远端一致的源码/测试 SHA-256 为 `formal_tac_evidence_route.py` `d598bf962ae16270c457f50e2bc4b1a9bc70fef544f662de5222b9a906d35f57`、`test_formal_tac_evidence_route.py` `75f0263c9494ac7d80e9af334f0be9f13a9fafd5051b4375a75461dfa6e1d33b`。两端独立生成的 schema v1 规范账户 CSV 均为 `643850ead0c71c70bbe405130b8f234a69c631b25bac11cbe68a368b4bac0180`、公开来源 CSV 均为 `162a7e4fdd82db87f3729c371122ec86efddac4f47ce2643e9d9025ded7659c1`、manifest 均为 `c153b11cc59067a911c1cdc24a3b3cf4d1456d19051786ccf4c9f22832ccec86`；`strict_formal_account_count=0`、`layered_route_approved=false`、`formal_tac_ready=false`、`e1_ready=false`。

E0-D-25 本地/远端一致的源码/测试 SHA-256 为 `project_primary_evidence_intake.py` `a05a85549e859b64aea7b8c7b43f45b9440455cf2f2f684da4d6687a211d1af8`、`test_project_primary_evidence_intake.py` `86e7b7cfb4c66477022d467cab9c7646686d1e195534295b0b4bcfd5bb77355b`。两端独立生成的 schema v1 字段 CSV 为 `877923986fe6d689e75e5a8c7225bff6b8775a02d46a3fa31a35674884c7a347`、coverage CSV 为 `f0134129f5db358c1cadb89d1c25a8b4524594200a15994d4f48a8c26db00263`、空白模板为 `f7b4157e996ec45a2837045f3c5105e9727cfad7177b0ac0494b6fc0f8b0d0c6`、manifest 为 `f98b8925b40be066e132a0bfda449d30d927ecc835cfe0690cddc5217aa1b74c`；`ready_account_count=0`、`raw_confidential_sources_exported=false`、`formal_tac_ready=false`、`e1_ready=false`。

E0-D-26 本地/远端一致的源码/测试 SHA-256 为：`d26_numerical_certification.py` `d5498b933260914152619d25e64011ff4fcce9bb8b14b8a5e9c60ec0a9d0b5b9`、`d26_certification_bundle.py` `15f25c7c1cd51c6aefdfe44d9c5518027f3c485c62c1b57a89bd8c676e51e240`、`test_alternative_dispatch_envelope.py` `8395f27a2e12d9bd780bece22740909e23fce8c96ba3f7a5056c183639152444`、`test_d26_certification_bundle.py` `9d54fb2aacd30de7cd702b425dea6f6f8c32096ec775eae212e4a895c6d9e056`。schema v1 规范 CSV 为 `7006e43c110967affe8633f4e0913a121e349e153b505e010e6a9b87830d54ea`、manifest 为 `63dcb72346af58a3cb5e2052b891b51441b37f0b1ab6b3c9880295310caa15ff`、非规范 execution sidecar 为 `75c55e092762cb004a763713707db9398adb4629ae2750687edbdced97e93b18`；8 个原始探针的逐文件哈希由 manifest 锁定且下载后逐字节一致。OpenBayes 完整回归为 `334 passed in 27.26s`；`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-27 本地/远端一致的源码/测试 SHA-256 为：`d27_direction_generation.py` `123ddd38d65a5f8dac09b5bebf9e02adc612db19012666200b99f0a96638fd9d`、`d27_certification_bundle.py` `ab386684a1e4a36146a1fb41841b9dbc1aaa0a0a322b202ee51ff024219b8954`、`test_alternative_dispatch_envelope.py` `67eba0e51643b29ff9667d968bfddbbc455bf7a88e12886b4e779f02475e340c`、`test_d27_certification_bundle.py` `84f734c4ce3d18287b6d66d5c4660ae702b04715be2eda56aa6855f1caacbd37`。schema v1 规范 CSV 为 `f3f8b0756fad1bf806aa631c7a6e72e1f83285fa5e45d0ac01307da5e37ee894`、manifest 为 `2f926e1f0d6b91d395538fe85eb2a3a11ae4f342783e974ef720ecd8fd96b8ab`、非规范 execution sidecar 为 `349decf0fe351141549b48a52a8a01b48bdb9814a522068d7586e28cf580c405`；三个原始探针分别为 `ffd15055bd37980a221a130391ac408e1768cdd403defada35ccb2ae8686b063`、`a3c3fcaa1694eae6fc2abb9b7a382541bdc984fd3f6e36be6c5f9a0325971187`、`1dfa94e360525d73f045ade9e79886d5431aec21a5b6db1ff1350674f38862e8`，下载后均逐字节一致。OpenBayes 定向回归为 `18 passed in 0.59s`，完整回归为 `340 passed in 26.74s`；`support_dual_is_global_l1_upper_bound=false`、`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-9B-2 确定性产物位于 `风光火+熔盐储热/数据采集/e0d9b2_tes_pump_calibration/`，远端上传件与独立再生成件逐字节一致：

- `e0d9b2_pump_calibration.csv`：9 行，SHA-256 `0ae6bfe10853c6f654a515fd3213673d9f998479f265bfbce1b330463bf269e8`；
- `manifest.json`：SHA-256 `6acd37583923d79b58455a97cff0e05814093ab8f7da66a982c835db8dc08806`。

规范桥接结果的 SHA-256 为：

- `e0c_heat_bridge_diagnostics_2024.csv`：`502a72db115eb50c69077f0b458d4726034b4d00b5226a373c99e8113edd6ed6`；
- `e0c_heat_bridge_diagnostics_2024.manifest.json`：`6fc0d94dc6f20eb9322237e0f3cc5a300beb7604f1832d99130ba76dc2eb7f33`。

## 3. 数据审计结论

两份当前逐时 CSV 在结构层通过：

- 2024 年 8784 个整点完整，无缺时和重复；
- `P_total=P1+P2`；
- `heat_total_MW=(居民供热+东方专业+老城区)/3.6`；
- 规划输入中的风光容量因子和价格列可解析。

但旧 `_combine.py` 会扫描 Excel 同行所有非空单元格。上半年工作表 J:P 的辅助统计单元格使 16 个合法 10 min 样本被跳过；两个 `23:59:59` 边界点又被错误并入小时平均，导致 7 个小时不是六点均值，最大热功率偏差为 1.5843 MWth。

新 A 列解析器确认：

- 严格 10 min 网格共有 52,704 点，即 `8784×6`；
- 半年文件之间有 1 个数值完全一致的重复点，可安全去重；
- 有 2 个非 10 min 的 `23:59:59` 边界点，应排除；
- 排除和去重后每小时恰好 6 点。

原始工作簿进一步确认：

- 上半年 `J9:L9=GJ/h`、`M9:N9=t/h`，且 `P10=SUM(J10:L10)×1000/3600`，因此三路热量之和除以 3.6 得 MW 的单位换算可关闭；
- 老城区 `2024-09-30 18:00` 的 `-1e7 GJ/h` 与 `-1e10 t/h` 是单点无效哨兵，前后 10 min 正常，可预注册为相邻有效点线性插值；
- 东方专业 29 个负热量点全部伴随负流量，正负区间 `heat/flow` 中位比约为 3.047 和 3.045，属于方向相关的有符号信号，不是普通缺测；
- 反向命题不成立：另有 49 个“东方流量为负、热量非负”点，且分布在多个日期簇；因此只能陈述“29 个负热量均与负流量共现”，不能由负流量单独推断反向供热；
- 居民供热 2,050 个负点中多数为采暖启停期近零负漂，但仍有 410 点低于 `-10 GJ/h` 和一个 `-293.51 GJ/h` 孤立点，不能全部无条件截零；
- 最长全五信号零段来自源文件 `2024-10-10 19:30—2024-10-12 09:00` 的 226 个连续 10 min 点。它不是缺行，同期 #1 机仍发电；真实停供与采集共同置零仍无法仅靠现有文件区分。
- 两份供热工作簿和机组台账均没有一次网供/回水温度或抽汽蒸汽温压。上半年 `G29:H30` 的“焓差 2353.6 kJ/kg”缺少温压、性质来源和测点说明，只能解释既有 GJ/h→t/h 辅助换算，不能反推蒸汽状态或 MT。

正式重建已经保留 `source_duplicate / non_grid_excluded / sentinel_interpolated / signed_reverse_flow / dongfang_sign_mismatch / resident_negative / all_signal_zero / zero_segment_imputed` 逐点标志。主净热不截零；forward 敏感性在 10 min 分支级截零；zero-sensitivity 只改写最长 226 点零段，按五字段 `t±7/±14 d` 四供体中位数插补。

本地正式产物位于 `风光火+熔盐储热/数据采集/e0b_formal_2024/`：

- `e0b_heat_source_ledger_2024.csv`：52,707 行，SHA-256 `d7ab93a80a3d83288785c0851b64211138f45a2318203d3a357a4ce320794423`；
- `e0b_heat_hourly_2024.csv`：8,784 行，SHA-256 `a89d3654600eac53768529ad9ef6d304b7d756783359fc1f1db95fd2bd4c709e`；
- `manifest.json`：schema v2，SHA-256 `5d37134c1ae7807f22357bc747b0ecc1aa3390617c864b2fd99e92c00e644702`。

修复后净热、forward 和 zero-sensitivity 年能量分别为 `5,024,409.853333`、`5,026,386.438333`、`5,034,702.163333 GJ`。主净热仍有一个负小时：`2024-05-27 02:00`，`-1.195370 MW`。正式数据构造已通过，但 E0-C 接入时仍须显式选择非负需求适配规则。

旧 `杨凌_合并逐时_2024_清洗.csv` 仍只可用于历史探索；新的 E0-B 三文件才是后续热数据权威入口。它们已经通过真实源双独立构建、三文件逐字节一致和 CSV 年能量回算，但尚不能替代未完成的经济与损失模型门槛。

E0-C 已把三口径注册为显式消费规则：

- 主口径 `net_clipped=max(heat_net_mw,0)`，全年 `1,395,670.599074074 MWhth`，仅修改 `2024-05-27 02:00` 的 `-1.195370 MWth`；
- `forward` 为 10 min 分支正向化敏感性，全年 `1,396,218.455092593 MWhth`；
- `zero_sensitivity_clipped` 为注册 226 点零段敏感性并在模型边界截负，全年 `1,398,529.574074074 MWhth`。

两个 24 h 窗口分别验证负小时处理和最长零段口径，不能互相替代。六个 No-storage 真实双机算例均为 `optimal`、MIP gap 0、最大电热平衡残差不超过 `1e-8`。该结果只证明输入—物理桥闭合，不是 E1，也不构成储能技术优劣结论。

## 4. CHP 审计结论

单机在线台账凸包锁定为：

\[
(P^{gross},Q)=(98,0),(350,0),(286,438),(98,83)
\]

其热致最小毛出力为：

\[
P_{\min}(Q)=
\begin{cases}
98,&0\le Q\le83\\
54.0451+0.529577Q,&83<Q\le438
\end{cases}
\]

回归测试已复现：

- \(Q=\{0,83,200,438\}\) MWth 时，单机最小毛出力约为 \(\{98,98,159.961,286\}\) MW；
- 两台固定在线、全厂供热 454 MWth 时，最小毛出力约 348.52 MW，接近 DCS 下包络 354.46 MW。

旧 `ExtractionTurbineCHP` 在 98 MW 时允许约 150 MWth，而台账只允许 83 MWth，会明显低估热致强迫出力，禁止直接复用。

原始台账进一步确认：

- `煤电机组经济性指标!L18:L19` 给出 #1/#2 的 2024 年厂用电率 `4.601393% / 4.652364%`；
- 运行 CSV 信号明确为发电机有功功率，故台账 \(P\) 按毛出力；
- `煤电机组基本信息!O2:V2` 明确为供电煤耗，即净供电分母，采用 \(P^{net}=(1-a_i)P^{gross}\) 转成毛出力模型的燃煤质量流量；
- 严格网格三路有符号外供热积分为 5,024,377.9 GJ，台账两机年供热量合计 4,982,343.0 GJ，仅差 `+0.844%`。因此当前模型把台账 \(Q\) 锁定为厂界有效供热，证据等级为 `primary-record inference`，不再额外乘直接供热换热效率。

仍需披露而不再阻止 E0-C 编码：厂用电率是否包含供热厂用电、煤耗曲线 `30%–100%出力` 的毛/净横轴定义与年份、\(P,Q\) 二维燃料面的构造假设，以及 3.5 h 启停时长不能直接改写成最小开机和停机时间各 4 h。

E0-C 已实现的一维总燃料流量曲线使用精确相邻段二进制，禁止所有 knot 的自由凸组合；#1 机固定 140 MW 回归为 `49.570778790 tce/h`，不会得到虚假的 `47.244945576`。98–105 MW 缺口保留“总流量外推 / 30% 比煤耗钳位 / 最低出力升至 105 MW”三种显式规则。默认不把 3.5 h 写成最小启停约束，也不把 `300,000 CNY/次` 静默拆成启动/停机成本。

## 5. 下一道门槛

下一步按以下顺序推进：

1. E0-D-8 已注册 MT 归一化三点作者敏感性；继续争取杨凌一次网供回水温度、抽汽温压、换热器端差或 UA，但不得用现场缺失阻止敏感性验证，也不得把三点冒充现场值；
2. E0-D-9B-2 已完成三档底层液压泵耗、标准循环及统一模型五路径/损失/辅机审计；后续正式算例直接复用该审计接口，继续争取杨凌泵曲线、压降和运行记录，但不得把作者情景升级为现场基线；
3. E0-D-25 已把四个运行账户转为 51 项项目数据请求。优先按空白模板索取杨凌合同结算、碳清缴、CHP 科目拆分和双服务 TES VOM；材料先本地隔离登记，接收完整后按 D20/D24 重新发证，不上传原文或提交值；
4. E0-D-24 的 12 个 TES 所有权账户仍为 8 个候选不完整、4 个无直接候选。继续补齐 Guccione 报价年/边界，并定向检索蒸汽充热、对外供热和 power-block retrofit；Energy+ 聚合值与官方工程锚点只能映射/校准，不能反向分摊或回填 D25；
5. 同范围成本、TES 正式 portfolio 与正式风光输入闭合后，再把 fixed-capacity 模型升级为 endogenous capacity，并用真实参数完成四架构样本验证，锁定 98–105 MW 低负荷煤耗规则敏感性；
6. 为 E5 单独建立代表周块、显式 warm-up/计分角色和跨块状态边界；当前 `AnnualHorizonSpec` 不接受裸零权重；
7. 争取补充 DCS 点表、居民热量公式、热网日报、热平衡图和煤耗曲线年份，以缩小数据敏感性范围。

上述剩余 E0 门槛通过后才进入 E1；禁止现在启动 699 次边界扫描。
