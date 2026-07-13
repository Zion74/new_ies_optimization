# E0 数据、物理与 HiGHS 验证状态

更新时间：2026-07-13

状态：**E0-A 通过；E0-B 正式带标志数据集通过；E0-C 固定容量统一调度与正式热需求适配/真实双机 24 h 桥接通过；E0-D-1–D-11 通过；E0-D-12 正式成本闭环审计完成；E0-D-13 建立 Rahman 唯一 BESS 正式来源候选；E0-D-14 已闭合完整 fixed-capacity BESS 生命周期账本；E0-D-15 已建立 TES 12 账户正式成本就绪度门禁；E0-D-16 已建立 TES 全系统 EAC 上限内核；E0-D-17 已实现年度结果适配并闭合一个跨平台可复现的 24 h 探索窗口，但两周性能门未通过。E0 总门槛仍未通过。** 当前 24 h 结果只是燃料单项、旧 2019 风光形状的冬季典型日年化筛查；TES 正式来源仍为零，系统级完整 TAC、内生容量及 E1–E6 正式实验不得启动。

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
- `e0d17_exploration.py`：哈希锁定正式热输入和旧 2019 风光形状，使用成本主目标、固定主目标整数 incumbent 后的弃电次目标，运行 24 h/两周窗口并导出 6 位小数 canonical CSV/manifest；24 h 已闭合，两周尚未形成可接受结果；
- `tes_topology_evidence.py`：逐条登记五个 TES 活跃路径的 Energy+ 直接证据、降阶映射、模块化合成或本文扩展；阻塞路径拒绝正式认证，`MT→LT` 供热级联必须显式披露为 proposed extension；
- `tes_heat_delivery.py`：区分杨凌现场、核心参考情景和作者敏感性温度来源，审计 MT→LT 两端夹点、HITEC 液态/材料上限、库存—端口双重热功率上限及盐/水流量；
- `tes_temperature_scenarios.py`：将 MT 转写为低品位显热占比，预注册 25%/50%/75% 三点作者敏感性，阻止来源误标，并逐点调用夹点合同认证；
- `tes_loss_auxiliary.py`：登记损失/辅机参数身份，以库存和每期环境温差构造任意步长下的线性复合损失，区分固定伴热补偿与净库存降级，并按五条盐路径计算泵辅助电功率；
- `tes_loss_calibration.py`：保存 Trevisan/Klasing 系统级锚点，注册低/基准/高作者情景，按 232.5/285/337.5 °C 三个 MT 分别反求 24 h 等留存损失率；聚合泵耗只保留为“聚合反推统一系数”审计量，不再充当物理标定；
- `tes_pump_calibration.py`：以 Trevisan 的 200 kPa、回路压损 20%、单个主动部件压损 5% 和泵效率 90% 构造 40/50/200 kPa 作者情景，以 Wang HITEC 密度/比热关联式生成五路径 `kWh_e/t`，并输出 45 MWhth、365 次/年标准双服务循环的 3×3 确定性校准产物；
- `components/chp.py`：台账顶点凸包、毛/净电口径、三种显式 98–105 MW 规则、非凸煤耗相邻段 PWL 和证据受限 UC；
- `components/bess.py`：PCC 交流侧充放电、SOC 和可交付电量；
- `components/molten_salt.py`：HT/MT/LT 盐量守恒、两段非重叠焓、充热输入能量、分罐模式，以及原始损失/伴热补偿/净降级/泵耗的线性表达；
- `solver.py`：只使用 `appsi_highs` 的确定性求解配置；
- `model.py`：No-storage / BESS / TES / Hybrid 构建期隔离、统一 PCC 与有效热边界、TES 五端口上限、显式 CHP 初末状态和 fixed-capacity 求解；TES 伴热与泵耗只在 PCC 扣除一次，并按调度时域或年度典型时段权重公开五路径吨位、原始/补偿/净热损失及泵耗/伴热 MWh 审计；年度分支新增可用新能源、PCC 外送和弃电服务审计，以及固定主目标整数 incumbent 的无罚值弃电次目标；TES 电输出端口为正时仍必须提供完整且互斥的发电回路成本分类；
- Pyomo 的 CHP、BESS、TES 小模型、四架构机制回归、线性表达和两种 HiGHS 接口检查。

未实现：

- 闭合 Rahman BESS 的 cell cycle-only replacement 与现有 calendar+AC-throughput 退化合同、VOM 吞吐侧和 5 MW PCS 模块/95% multiplicity 规模曲线；来源价格与主要非电芯账本已经闭合，不得再写成“Rahman 全文缺失”；
- 闭合 TES 12 账户正式成本寿命 portfolio；Guccione 电加热器真实报价仍缺报价价格年，但它不是唯一阻塞，罐/循环、两条蒸汽充热、盐—蒸汽发生、供热换热、power-block retrofit、项目附加费和寿命项也未闭合；DLR `20–22 EUR_2020/kWh_th-net` 只作两罐 Solar Salt 工程聚合校准；
- E0-D-9B-2 作者级筛查已闭合，但没有杨凌正式损失率、伴热比例、管网压降、泵曲线或五路径现场比泵耗；当前 40/50/200 kPa 与标准循环只能用于敏感性和量级审计，仍不能写成杨凌正式损失价值；
- 正式 endogenous capacity、将已实现的寿命现金流核按真实参数 portfolio 接入完整 TAC、VOM/碳价/结算价格与低负荷煤耗规则敏感性；
- 代表周、场景网格、全年回代和批量执行。
- 336 h 全级联 TES + 双机 UC 的两周性能门；当前本地 10 min、OpenBayes 15 min 受控预算均未形成可接受双窗口结果，不能据此作经济性判断。

## 2. 测试证据

| 环境 | 范围 | 结果 |
|---|---|---|
| 本地独立 Python 3.11 环境 | 原始热 Excel、正式构建/适配、真实双机桥接、CHP/储能物理、UC/PWL、四架构、寿命/年度经济、TES 证据与成本门、E0-D-17 适配和探索导出 | `284 passed in 76.16s`（关闭 pytest cache，无警告） |
| OpenBayes Python 3.10.18 隔离环境 | 已同步 E0-D-17 源码、测试与授权数据，显式注入正式 E0-B 数据目录；24 h canonical 与本地逐字节一致 | `284 passed in 21.37s` |

本地与远端基线均使用 `Pyomo 6.10.1`、`highspy 1.15.1`。OpenBayes 包路径为 `/root/e0-b-20260711-019f4f64/tes_bess_boundary`，正式 E0-B 数据位于 `/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024/`。远端显式数据合同为 `TES_BESS_E0B_FORMAL_DIR=/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024`。E0-D-14–D-17 已同步远端；`economics=None` 的既有 canonical CSV/manifest 仍锁定。

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
3. E0-D-15 已把 TES 缺口拆成 12 个非可选账户；下一步优先补齐 Guccione 报价年/边界，同时分别检索或询证罐/循环、两条蒸汽充热、盐—蒸汽发生、供热换热、power-block retrofit、项目附加费和寿命项。DLR/Klasing/Li 聚合锚点只能校准，不能与被其包含的分项成本叠加；
4. E0-D-17 已闭合 24 h 实际结果适配；下一步 E0-D-18 先强化 TES 流量 Big-M、可达状态和 UC/TES 联合 formulation，闭合两周性能门，同时补齐 VOM/碳/电力结算等非 TES 年度成本。24 h 年化阈值不得转写成全年 CAPEX 或 E1 赢家；
5. 两周门通过后，再把 fixed-capacity 模型升级为正式 endogenous capacity，并用真实参数完成四架构样本验证，锁定 98–105 MW 低负荷煤耗规则敏感性；
6. 为 E5 单独建立代表周块、显式 warm-up/计分角色和跨块状态边界；当前 `AnnualHorizonSpec` 不接受裸零权重；
7. 争取补充 DCS 点表、居民热量公式、热网日报、热平衡图和煤耗曲线年份，以缩小数据敏感性范围。

上述剩余 E0 门槛通过后才进入 E1；禁止现在启动 699 次边界扫描。
