# E0 数据、物理与 HiGHS 验证状态

更新时间：2026-07-15

状态：**E0-A 通过；E0-B 正式带标志数据集通过；E0-C 固定容量统一调度与正式热需求适配/真实双机 24 h 桥接通过；E0-D-1–D-32 已闭合相应数据、物理、经济边界、证据门和严格数值证书；E0-D-33/D34 已建立公开 TES 成本组合、共同 PCS BESS 与完整双机 CHP/PCC 内生容量接缝；E0-D-35 已完成结果前预注册的 TES 盐量+五端口材料性网格；E0-D-36 已冻结六个结构化代表周、52 周权重与年尾 24 h warm-up + 48 h 计分段；E0-D-37 已关闭共享容量下的七块 CHP/BESS/TES 独立循环状态边界。原 D38 高热状态物理失败；D38-R1 又在 baseline 出现代表期可行、真实 8784 h 不可行的反转，故代表周—全年预验证与正式经济门仍未通过。** 24 h 全局严格包络保持 `26,010.171143–26,010.174929 MWh/a`；最新 336 h 严格区间继续引用 D30 的 `[36,382.462799,777,141.368858] MWh/a`。D24 严格正式账户为 `0/16`；D25 当前 `ready_account_count=0/4`。D35 自然服务在 5%/10% 门下精确折叠为无储能；严格服务保留 TES，但全部 Hybrid 的 BESS 为零且 TES/Hybrid bounds 重叠。D36 冻结第 `4/5/8/29/39/48` 周及 `1/3/10/13/21/4` 权重；D37 规范结构 manifest 的双端 SHA-256 为 `1e460ef35921d670a23867ad39716302c7f4eecb90cfd225ee628ea7bbd0ddb6`。公开 TES 组合只允许 `public_sensitivity`，永久 `formal_project_eligible=false`；不产生杨凌正式 TAC、E2 正式经济前沿或项目技术赢家。

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
- `formal_bess_costs.py`：固化 Rahman 2019 USD 原值、Li-ion footprint 派生围护基础成本、PCS/BoP/FOM/contingency 非电芯账本，并实现三接缝策略、统一价格转换、完整 fixed-capacity BESS 年度经济和不绑定装机量的共同 PCS 规划系数；
- `sensitivity_cost_anchors.py`：加载 E0-D-11 NREL/OEDI 工作簿哈希包，保留 BESS `USD/kW_DC + USD/kWh_usable,DC` 双分母，闭合 4 h CAPEX/FOM，执行 2020 USD→2024 CNY 转换，并禁止含 augmentation 的源 FOM 与独立 replacement ledger 双计；
- E0-D-12 文献审计由 E0-D-13 更新：机器矩阵 13 个候选中 Rahman 为唯一 `formal_candidate=true`；Guccione、Ahmadi/PNNL 与其他 TES 来源保持原降级；
- `tes_cost_mapping.py`：将同一批盐、完整 LT→HT 显热库存、三罐和五端口转换为唯一 `kg / kWh_th / kW_el / kW_th` 容量账本；按部件温段检查文献温区，并把 bottom-up 成本安全绑定到寿命 portfolio；
- `formal_tes_costs.py`：要求盐、三罐/循环、两类充热、发电/供热放热、power-block retrofit、项目附加费和寿命项等 12 个账户逐项闭合；Klasing/Li/DLR 聚合锚点不能满足部件账户，多 DOI 复合路线需要另行批准；当前 12 账户全部阻断，不生成 TES 正式证书；
- `public_tes_costs.py`：建立 `aggregate_storage` 与 `component_ledger` 两套互斥成本账，登记来源等级、价格年状态、直接/聚合/相似部件映射和 12 账户覆盖；调用官方快照转换到 CNY2024，复用生命周期 EAC 核，并阻止 DLR 聚合包内部工程加成二次乘算；默认未确认作者假设时拒绝接入，确认后仍永久禁止正式项目用途；
- `capacity_planning.py`：建立 BESS 的名义能量、充放功率和共同 PCS 装机变量，执行 `0` 或 `5–100 MW` 来源域析取；建立 TES 盐质量/三罐/五端口容量、环境相关库存损失、固定比例伴热、五路径泵耗、2–24 h 服务、HT/MT 两条独立额定放能测试与充热可达性，并把公开 TES 组合映射为年度容量成本表达式；
- `planning_model.py`：复用 E0-C 双机 CHP、风光、有效供热、公共 PCC、年度权重与服务约束，停用固定储能块并接入 BESS/TES 内生容量块；四架构仍在 Python 构建期隔离，目标显式合并运行成本、容量 EAC、BESS 循环退化和 VOM，并返回 HiGHS primal/dual objective bounds 与实际相对 gap；
- `e0d34_endogenous_capacity_sample.py`：锁定正式 2024 热量、旧 2019 风光形状、Rahman BESS 和 D33 聚合公开 TES 基准，使用 D18 已验证的 logarithmic fuel segments / continuous transition envelope 运行 24 h/336 h 四架构受控样本；先由无储能两阶段搜索确定最小弃电上限及该上限下的燃料最小年度 PCC 外送，再把两项服务共同施加于四架构。早期只对齐弃电的 `/results/e0d34/` 结果因 PCC 外送不一致只保留为集成 smoke，不得用于经济比较；
- `e0d35_tes_materiality.py`：锁定旧 `1,200 MWhth / 13,913.716 t / 150 MW` 参考组合、`0/1%/5%/10%` 网格和自然/严格两组同服务；正比例时对盐量和五个启用端口分别施加 0-or-min 半连续域，并逐项审计安装二进制、服务残差和容量下限；比例 0 不增加二进制，保持 D34 连续模型；
- `e0d35_materiality_bundle.py`：验证 16 个预注册身份，强制自然服务 5%/10% 四案采用 gap=0 refined 证人，生成 LF 规范 CSV、自包含 manifest 与 execution 原始哈希侧车；
- `e0d36_representative_weeks.py`：按结果前合同将 8784 h 拆为 52 个完整周与 48 h 年尾，使用热负荷/风/光/气温 672 维标准化曲线执行确定性 PAM，强制热峰与高可再生/PCC 压力周，重新分配全部 52 周，并导出六周、年尾真实 24 h warm-up、1056 个计分行和 8784 加权小时；D36 不调用现有单循环优化模型；
- `e0d37_block_horizon.py`：默认逐字节校验 D36 period CSV，同时允许调用方提供另一套完整哈希/块/时段合同；D39 只通过显式八周合同接入。适配器生成允许块首零权重 warm-up 的显式年度分块时域；
- `e0d37_structural_audit.py`：使用正式 D36 输入和 D34 规划参数构建完整 Hybrid 模型，只审计共享容量、1087 个分块状态节点、CHP 首尾转移/爬坡、年尾权重和线性，不调用求解器；
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
- `d32_joint_block_envelope.py`：在两架构完整全时域路径、年度 PCC 服务和 D19 准入条件上，逐个保留 24 h 块内符号二元并放松主整数域，以有限 dual 构造块 L1 上界；可将块上界作为有效割加回 reopened 全局 MILP；
- `d32_screening_bundle.py`：验证 15 个块子问题的有限 dual、D22 分块证人、24 h reopened 等价门、336 h 结果前 1% 停止门和无 `336h.json` 事实，导出确定性 CSV、manifest 与非规范 execution sidecar；
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
- D35 已闭合 24 h 受控材料性网格，但它不能定义杨凌现场最小设备规模；D24 的 16 账户和 D25 项目记录仍未闭合，D33 公开组合不能生成杨凌正式 TAC；本地 `price_sell/price_buy` 仍只是作者生成情景；
- D38 原三状态合同已执行到真实全年无储能参考门；`H*=0.80/G*=0.70` 状态在最小弃电第一阶段即 `infeasible`。静态诊断给出 490 MW PCC 下最大供热 `766.076788 MWth`，冻结高热序列 36 h 超限且全部位于代表周 4。因此原 D38 不能关闭，尚未进入该状态的代表期规划、固定容量回代或全年重优化。
- D38-R1 静态诊断为 0 h 超限，但正式 baseline 链确认 D36/D37 代表期无储能在 10% 帽内 `complete`、真实 8784 h 同服务回放 `infeasible`。真实全年与代表期零燃料自然最小弃电分别为 `565,916.122/338,704.669 MWh`，低估 `227,211.453 MWh`；R1 三状态合同据此失败。

## 2. 测试证据

| 环境 | 范围 | 结果 |
|---|---|---|
| Windows `.venv-e0` | 全包；含 D33–D39 Gate A、严格 Gate B 接入、bundle auditor、周级失败诊断与 HiGHS | `454 passed in 83.92s`（关闭 pytest cache） |
| OpenBayes Python 3.10.18 隔离环境 | 全包；含正式数据、E0-D-17–D39 Gate A、严格 Gate B 接入、bundle auditor、周级失败诊断和 HiGHS | `454 passed in 34.19s`（关闭 pytest cache） |

D26–D37 使用 `Pyomo 6.10.1`、`highspy 1.15.1`，正式求解器仅为 HiGHS；D37 结构审计本身不调用求解器。OpenBayes 包路径为 `/root/e0-b-20260711-019f4f64/tes_bess_boundary`，正式数据合同仍为 `TES_BESS_E0B_FORMAL_DIR=/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024`。D27、D28、D29 的规范汇总位于 `/root/e0-b-20260711-019f4f64/数据采集/` 下同名目录；D30 bounds-only/全局原始探针与规范汇总位于 `e0d30_physics_service_bound_tightening/`；D31 双窗口 OBBT、24 h 等价探针与负筛查证书位于 `e0d31_intertemporal_obbt/`；D32 双窗口分块屏幕、24 h reopened 等价探针与负筛查证书位于 `e0d32_joint_block_envelope/`；D36 正式构造位于 `/root/e0-b-20260711-019f4f64/e0d36_representative_weeks/`；D37 结构审计位于 `/root/e0-b-20260711-019f4f64/e0d37_block_cyclic_boundaries/`。本轮只上传新增测试代码和既有授权范围内的锁定输入，未上传本地受限资料。

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

E0-D-28 本地/远端一致的源码/测试 SHA-256 为：`d28_multistart_direction.py` `4a61d7e0d13a401b18f3e43a990fc942069af0a016525bd8b40e254a6efa7a0a`、`d28_multistart_bundle.py` `54c9eee41ca2d5c6bdd2e40143025d76c9b2e7923ab3c2b77270e8851924a932`、`test_d28_multistart_direction.py` `8717f525e7710e85e937da9adf2b632e4fec38b847c5f8a51c61baf7337be7fb`、`test_d28_multistart_bundle.py` `98bdbfda50e405b4749ae7f2ee4d28d3972797fb5e6d71f35e913de8dc933e08`。schema v1 规范 CSV 为 `1172ee16c16353e68fc907fa698495a8195d8f211bead70be64d9a4d3e9a0330`、manifest 为 `0427ce8647f27a8b5ce74690673a4690be4a41849846aafba53ad942c61ff80c`、非规范 execution sidecar 为 `b3516a7ab26dda83ae7259aa506b6ada00992e8de0aff320d9ef2e0b26effefd`；两个原始探针为 `718bc50c74e45fd3242675670f6acd3b2a07014a6c0899fa7916346c34f82d85` 与 `63b7859d64a1890ae67acee2e776c598e439a43f3fe265df8f66f533555baddd`，下载后逐字节一致。OpenBayes 定向回归为 `8 passed in 0.10s`，完整回归为 `348 passed in 27.02s`；`support_dual_is_global_l1_upper_bound=false`、`global_l1_bound_generated=false`、`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-29 本地/远端一致的源码/测试 SHA-256 为：`d29_export_linked_bound_tightening.py` `40246e0141aaf59169abb0687e7547e86fab15eb0949e00bffcfa743bbb7d315`、`d29_certification_bundle.py` `64f114bd489b8ee7372f462f47d26a56f61591655ac8715191ef9f80728e224c`、`test_d29_export_linked_bound_tightening.py` `0a8730160d1c7ee0a775fb22ece49b0f6951276d37cc07d62d6b09e083f627b7`、`test_d29_certification_bundle.py` `fda241260c95c3bbbccd61bb1fa37e32bd6083db0ebac91cf2a1f8e43623e178`。schema v1 规范 CSV 为 `85fe459cebfd6f058d58e76f4358293630c80dfe3229cd5d6c8e366a78e26811`、manifest 为 `8c3924e49421a68e6179a2eef69eca699ac43392e895f07be357052bf821a11a`、非规范 execution sidecar 为 `311435314b89ee7f688d10f46c8141138b76c27574c999b91f9eeaf3d095c66e`；24 h/336 h 原始探针分别为 `c048bd314106459bd21ad5ee71dcba7696610b8be2ad409503e55a728e998398` 与 `7436273dd0fc2182487768f5b468e639dd335e7e338e9dcc7cbaff24cf36ee04`，下载后逐字节一致。OpenBayes 定向回归为 `6 passed in 0.53s`，完整回归为 `354 passed in 26.74s`；`feasible_set_changed_for_integer_solutions=false`、`primary_integer_patterns_reopened=true`、`sign_binaries_reopened=true`、`global_dual_is_valid_l1_upper_bound=true`、`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-30 本地/远端一致的源码/测试 SHA-256 为：`d30_physics_service_bound_tightening.py` `2484676d410a94323c93505fa9e930f360b26d9dbc8d89756e72253134b8eceb`、`d30_certification_bundle.py` `d60a5401462a3d4b6b8dd401850de453e3d3bb23b8cdcc1e6cc1fbe6ac0f777a`、`test_d30_physics_service_bound_tightening.py` `b12d38181d815408a7dcb61449ea8879f1d41f61839d98bbb12487c27d5fefe4`、`test_d30_certification_bundle.py` `2776be79b39d3a2bdd90c424ffa6d3ec1348a6a6dd9aa26750011e3886d8a5b4`。schema v1 规范 CSV 为 `32ca2a7171d35da1311c3316127b9285eb3ab2af5c9e8680741e7c5efc735e6c`、manifest 为 `c430fa852f3934c8466387a32f2ce67152764b8bd7fb1d228fc1fc416f08520e`、非规范 execution sidecar 为 `31235b956ea0e1497369e861aa5d5921a56cf295d8c6b46aa42bf45bc7eb8eec`；24 h/336 h 原始探针分别为 `13d4a9ca232beebab05e16d5b88534c3b3d0e40452d07bc39265a77495440ca0` 与 `c27abd940a66582cf541cb3cc6bffbf283d7e7cdf66d51e582266edf6e81fbf7`，bounds-only 筛查分别为 `e412e702f856e7576027380d17082f842a64f29b0b3c23a3149efc60ec907cf6` 与 `9b06d54073906fd3676aeb2ec03e4408331f942eb686828cc3dfc19a2d949f08`，本地/远端逐字节一致。OpenBayes D29+D30 定向回归为 `15 passed in 0.52s`，完整回归为 `363 passed in 26.75s`；336 h 正向/反向符号宽度平均收紧 `33.3107%/1.8659%`，global dual 为 `777,141.368858 MWh/a`，较 D29 改善 `8.0363%`。`known_witness_within_bounds=true`、`feasible_set_changed_for_integer_solutions=false`、`primary_integer_patterns_reopened=true`、`sign_binaries_reopened=true`、`global_dual_is_valid_l1_upper_bound=true`、`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

E0-D-31 本地/远端一致的源码/测试 SHA-256 为：`d31_intertemporal_obbt.py` `ee9da51267bfa4ac52b97fa25f19129f14574a232b8a06d86201b551f7ed651d`、`d31_screening_bundle.py` `f2989a26cf099014f4ee263dec2e8f50a2e480780a6ae5bda49e41f3d6512efa`、`test_d31_intertemporal_obbt.py` `ee64cb44b4bbcd1c902d46e50d8f15a7103410664cb4fcf094cb832e93b66a47`、`test_d31_screening_bundle.py` `5a598ae72b955a64927e7c6693db0c142bd3d61e7115d351c49c50afc25797b4`。schema v1 规范 CSV 为 `93cee79a930c32920f7eb0e89326ed3190fea5c5c3ca461cafe9a10200d3aad0`、manifest 为 `55bb55c9b26a11dc8ece3fc5f283e39a616736ac3f0737944f5a7997ad615821`、非规范 execution sidecar 为 `35ab773e13418d73ca550c461a978d57444d15e36c43b10ce4e61d27605404b6`；24 h/336 h OBBT 屏幕分别为 `acf2c49126485ad9d4d41e9d036ed45ec0487fdeeeab71958412d370c03f5836` 与 `1789b76b5589f890e14b9dcbece0cec0dfdea486baa89613f24284bc670f668e`，24 h 等价探针为 `32a0589b26cda583feff3d85d10ad60ab3b406ace88bf064ab5f73347389ac3e`，本地/远端逐字节一致。OpenBayes D31 定向回归为 `9 passed in 0.49s`，最终完整回归为 `372 passed in 26.73s`。24 h/336 h 分别完成 96/1344 个最优 LP；336 h 正/负平均符号宽度相对 D30 仅改善 `0.0329%/0.0864%`，`global_probe_336h_launched=false`，最新 336 h global dual 继续引用 D30。

E0-D-32 本地/远端一致的源码/测试 SHA-256 为：`d32_joint_block_envelope.py` `91daa633ef5b713d577f8ea2b00274b683385feb8da01cd25f3f75c0087c2a66`、`d32_screening_bundle.py` `82600cbf921d5bc740f5afb969ba3f616253821b6d957d8d93afa43ab6e3cc67`、`test_d32_joint_block_envelope.py` `d0fe8354d7d4ba16f2a2c4f0e3ca47ee22d88fdea34d7fc4ab420e37194c9b7e`、`test_d32_screening_bundle.py` `d07a6c1c2673b16fbd98a2a30ab5214b371c08b644d135bc7f5542b80ae1df24`。schema v1 规范 CSV 为 `47b273c511717cb4f9c19cf640d806df2c00250a929bd0936df4a4601a534939`、manifest 为 `bb425167c7eb781c1b91d0e31e98f83ac3e7de5ee94967dc4c9c22005ee6bdc8`、非规范 execution sidecar 为 `4eff8405d49f28bcded74c6b45b81355fb81e5181ff8451c3fac558b0551782e`；24 h/336 h 分块屏幕分别为 `721754d4c06423963e4273b13a43f36521a1af6b6b0857d113d7e43619e85f3e` 与 `bb3212c24852f8d0ef6655ff298e4bcf04f34c6ea0ef10e60d13566c51fced91`，24 h reopened 等价探针为 `f1ae9d076cc00547f8003df4c5adf161f38a6f3e9a78fedd01a5c39efc027968`，本地/远端逐字节一致。15 个块子问题全部返回有限 dual；336 h 为 4 个 `optimal`、10 个 `maxtimelimit`，受保护 dual 之和 `1,930,160.868929 MWh/a`，高于 D30，故 `global_probe_336h_launched=false`。

E0-D-33 本地/远端一致的源码/测试 SHA-256 为：`public_tes_costs.py` `ae28f6dfbec2d9f926b32a85ef43a2e4c794ca0e17760ce846b2dda0001894bc`、`capacity_planning.py` `5754ea51658703308c5190753c6de68ef683a240c9e0a45f9bc533568169290f`、`test_public_tes_costs.py` `37225482b4a8ec88b00939af49c8a2cfd8a03a00b5aedf89b25b7a080b44130e`、`test_capacity_planning.py` `29443c486c134968fb4a0424b4f4d0f8a50971040cb808fa4c4362753c1d6e64`。OpenBayes 新增定向回归为 `19 passed in 0.54s`，完整回归为 `396 passed in 27.27s`。价格快照解析按 `TES_BESS_PRICE_BASIS_DIR`、本地 `数据采集`、远端 `formal_data` 的显式顺序定位，但仍由同一 D4 manifest 与逐源 SHA 校验；不创建或上传临时价格副本。`public_sensitivity_ready` 需要显式确认作者假设，`formal_project_eligible=false`，`full_endogenous_planning_ready=false`。

E0-D-34 本地/远端一致的源码/测试 SHA-256 为：`capacity_planning.py` `41b8510769fad7ce951edc211bc77e5aa0b38bbb6c25e017874093ca6c921a0a`、`formal_bess_costs.py` `2ee3a09a41e5b0449b5d16f77616a4eb3c3da2c9f38586c710005c4f5b1f3b86`、`planning_model.py` `bcf44323ac3472013fb3ceff39d7a76eb655ed722dc6f987e67c8036c97cd7f2`、`e0d34_endogenous_capacity_sample.py` `05ae912ec2092b96beec9a755017fa681c2927d791fe8d91e6688fe9f9f48a32`、`test_capacity_planning.py` `4aa20ab49efaf561f498ba09c404ee4e745022f79dae3d3d9c4e5dc4c6f32c0c`、`test_formal_bess_costs.py` `fa47811c36b3c8be27bd9c1b21b56ab4edc02f60011c3c0bac589eedb1a3ad1e`、`test_planning_model.py` `85110601c2dfc30d06c4fc43161ac723fdfbb724900790e0e663e90047de093e`。定向回归为 `23 passed`，Windows/OpenBayes 完整回归分别为 `405 passed in 35.74s` 与 `405 passed in 27.33s`。远端首次全回归漏设 `TES_BESS_E0B_FORMAL_DIR` 导致 23 个数据路径失败；补齐正式数据与价格快照环境变量后全部通过，因此该次路径失败不计作代码回归。

D34 公平样本与 1% 严格 ε 初筛的远端 JSON SHA-256 为：24 h No storage `5254e0085f4ddc337b21d4696a9141385c40ac45dcc327578f22a575800a1ecb`、BESS `6d636a03d89dd8f10ef4a0d6d00ce4a251d390064a28d08611e34c98251b0727`、TES `ffe90d3de1c137354b2637958ea18133a90a1edcade959452fa2e1b82e895161`、Hybrid `12d60196aec0a114bb4646b3b8e5740a85762982986c1959f4077efcffd5952d`；336 h No storage `bbc218ce6e26839311be3192fffd13a1278ae680693dd16611d9e6c791c9d38f`、BESS `c8792f8f52bbb0789738af732478135ca09573c9de345209c9fe2318d8ef8f30`、TES warm-start `21b03407718c16a0d151260f2e5c2163b015f0ac0d2d4ccaa5c2a89d079e067d`、Hybrid warm-start `7486b44e156ed5fbbd28ec0280b52a9aefd57b739885e06fee6c46525a49fbd0`；严格 ε BESS bounded screen `90a29886b955b8970a3804ee37c5b5a2c5d52b12d46b0ee60a6eb3b3e94c6bb3`、TES `fa499767b5e0f21be13f31e1148f760cf98c4cca178021e2de8fac7ea8164aee`、Hybrid `566bbffd49d17bb4051c9d136e2b4ae6096d5b5b1c3746ea85988154cd99ced0`。336 h 热启动只改变 MIP 初值，不改变完整模型；其最终 gap 为 `0.0964%/0.0945%`。严格 ε BESS 当前为 `0.461%` 有界筛查，TES/Hybrid 分别为 `0.0997%/0.0774%`。

E0-D-35 本地/远端一致的最终源码/测试 SHA-256 为：`capacity_planning.py` `2183abda45d82e4407f785304d2b494b02fba8253c23a986e788dbc12fdcd642`、`planning_model.py` `e7ad61bed1315f072d935392d16c0bf903d7da19321ad8c98704e67c9c7e4e11`、`e0d34_endogenous_capacity_sample.py` `eb6aec050f1c65ec20ecd430fe4bed4ba507a780de29435a431dda76bbf0333c`、`e0d35_tes_materiality.py` `c3d8dee860f0c1754268bee3d85ce4dc17733664560d93170f6857e1422772cb`、`e0d35_materiality_bundle.py` `b09a1fe22866480018ba562e7bf3a1520fad321a5a0296e82480babb919674e3`、`test_capacity_planning.py` `127c576bf4ca62f44822039f6648ee8e28c91021af3b6f625f03a0343c09c70c`、`test_e0d35_tes_materiality.py` `6f6b9b0c2379ee79b6169ae55d5da260d6e6ff7259263965f5a22f1e6a4e30bc`。D35 定向回归为 `17 passed`，最终完整回归为 Windows/OpenBayes 各 `414 passed`。16 个主探针覆盖自然/严格两类服务、TES/Hybrid 两架构和 `0/1%/5%/10%` 四级门，另对自然服务 5%/10% 的四个零储能证人执行 gap=0 复算。规范 CSV、manifest 和 execution sidecar 的 SHA-256 分别为 `8a321001878a7d0b14f8441f96272cdd18303201fa5c9facbccd97825ea016d2`、`b722a6143ce25f8abc113ed3b51b3c09aa4008bab77973174c23c955481bc4a5`、`2bb893ccbfc9f19637201ee8487a224e089f2e9ac4b3aeaf113d49ba9d512c5d`，本地重建与远端逐字节一致。自然服务 5%/10% 精确折叠为无储能；1% 仅保留约 `139–142 t` heat-only TES，代理改善约 `0.03%–0.05%`，低于既定 5% 无差异带。严格服务保留 TES，但全部 Hybrid 的 BESS 为零且 TES/Hybrid objective bounds 在每级门下重叠，因此 D35 只关闭工程尺度敏感性解释缺口，不产生正式 TAC 或技术赢家。

E0-D-36 在任何代表周优化结果产生前锁定四通道 672 维特征、确定性 PAM、两个强制极端周、去重补位、52 周重分配和真实年尾段合同。最终代表周为第 `4/5/8/29/39/48` 周，权重为 `1/3/10/13/21/4`；第 4 周覆盖全年热峰，第 5 周覆盖最大累计可再生/PCC 正向压力。六个周块、24 h 年尾 warm-up 与 48 h 年尾计分段共 1080 个模型时段，其中 1056 行计分、年度加权小时严格为 8784。源码/测试 SHA-256 分别为 `17c3b0f9698b53fbc51a71ac3a4675738696ed587b0474370e1c58a61b71aee9` 与 `982aa3b518bf35f8806b065408a09116991290ea14084e6865594bac65eb8222`；D36 定向回归为双端各 `6 passed`，完整回归为 Windows/OpenBayes 各 `420 passed`。assignment CSV、period CSV 和 manifest 的 SHA-256 分别为 `31c7daae3faa5ffa91f3e5b31ad75fc666cf9f3952bac399352ec832607488a3`、`02b168d6b4169101c1d601a548c7a475d8aea8a8a280de5f52fcaaf6ec09aaa9` 与 `2c3818030277d146479245afdf278fa96f7562a1951b42641f5a5103d181a5f1`，Windows/OpenBayes 逐字节一致。描述性重构误差为热量 `+5.3531%`、风电可用量 `-8.9751%`、光伏可用量 `+2.6072%`、年均温偏差 `+1.0424 °C`；这些数值不触发事后调周，而作为 D38 回代风险信号。D36 没有把周块送入当前单循环模型，也没有生成储能容量或技术排序。

E0-D-37 已将 D36 数据包接入显式分块年度时域。旧 `AnnualHorizonSpec` 继续拒绝零权重；新 `BlockAnnualHorizonSpec` 只允许块首 warm-up 零权重，并拒绝无计分块、零权重尾段、乱序、重叠和缺口。七块共享一套 BESS/TES 容量变量，但 BESS 与 TES 各有 1087 个状态节点，使每块首、末状态相互独立；两台 CHP 各有 1080 条启停转移、1080 条上爬坡和 1080 条下爬坡约束，每块首小时引用本块末小时。完整 1080 时段 Hybrid 只建模审计含 84,306 个活动变量、16,201 个二元变量和 75,736 条活动约束，非线性组件为零且没有调用求解器。D37 适配器、审计器、定向测试和规范 manifest 的 SHA-256 分别为 `f15395f7288107fad561355695c730e016f75d5ca36325ac3a90d3f0174b6b57`、`55c79f4dbf91c3d14eaa434302dfd3524dc7a7cae3919399cc4acb0c20923136`、`487544d44619d7640d59fb00dfc500fd04f816c11b5240158d982a5ad0141cf9` 与 `1e460ef35921d670a23867ad39716302c7f4eecb90cfd225ee628ea7bbd0ddb6`；manifest 在 Windows/OpenBayes 逐字节一致。D37 定向回归双端各 `7 passed`，完整回归双端各 `427 passed`。D37 不运行 D38，不生成容量或技术排序。

E0-D-38 已实现完整容量快照、代表期/单块全年输入、同服务参考、可续跑案例入口和静态失败诊断；本地完整回归增至 `437 passed`。原高热紧 PCC 参考在 OpenBayes/HiGHS 上于最小弃电第一阶段返回 `infeasible`；规范失败 JSON 与静态诊断 SHA-256 分别为 `c96e5eaf3833c31596dfe6792a3b3ac4810438ac24d36ef78bd23878fa2baa2d` 和 `566bdd5666bce4b63a302585b285bd5682f4ad2dd4af043151365f7856a3c7b2`。36 个超限小时全部位于 D36 第 4 周，证明增加代表周不能修复此状态定义。原 D38 不得登记为通过；正式 E2/E3/E4 继续禁止启动。

E0-D-38-R1 在任何修订状态求解前冻结一次性 `H*=G*=0.70`：热量尺度 `1.5962316499799991`、P95 `613.2 MWth`、峰值 `724.03367951984 MWth`，相对 490 MW PCC 静态上限保留 `42.0431085050533 MWth`。R1 只修订热尺度，其余原合同规则不变，并禁止再次搜索 `H*`/`G*`；随后按该冻结合同执行 baseline 最小充分链。

E0-D-38-R1 执行后，静态必要条件仍通过，但 baseline 已在时间聚合门失败。当前代码生成的服务、代表期与全年案例 provenance 完全一致；混用 pre-R1 服务代码的首轮服务器产物已隔离。正式 baseline 服务/代表期/全年失败/周级诊断 SHA-256 分别为 `93f3d7b5c50312d08ea3dd78b1af70661facf880fcc882b1bb1ac32a783977b3`、`f8dcae636c35b7d7b9e476c3c974b6cffb0da403de13e6807808011212068fe5`、`ea266a9ab37922368e08a85c72be41a2c25e418953cff230e3577c2451ed5b49` 与 `3ea98ef46b72705617a3dc436c57b158f7819aa8e358c8d85448e66f5bc46329`。第 49/16 周分别低估 `20,547.320/20,063.702 MWh`。

E0-D-39 已在任何新数据或结果产生前把失败诊断转化为一次性、可审计修订：原六周加第 49/16 周，52 周沿用 D36 的 672 维距离重分配，年尾 72 h 与所有物理/服务/成本规则不变。Gate A 已在 Windows/OpenBayes 双端通过：最终代表周为第 `4/5/8/16/29/39/48/49` 周，权重为 `1/2/9/2/13/19/4/2`，1416 个模型时段、1392 行计分源记录及 8784 加权小时全部通过结构审计；assignment CSV、period CSV、manifest 和 execution sidecar 的 SHA-256 分别为 `7949d6f58d86787cf9ea8129dae3adc85ec20ffba8a157ad7e121395f2f5052e`、`fb7aa1e9d8815a2a22eee68b61af12b44c4485ba3ca464d21652480d9b75c2ac`、`dabb565087e9adb2e597d00ea7c12fcb30bf9e522517a7f8e6ed7ee73d9a16a9` 与 `572faa4ff34c6e6ad00322dbd4bf50674e0ced6849416ecb840296f639de5d78`，三个规范文件逐字节一致。首次 Gate B 命令在求解前被 D37 的 D36-only 哈希锁拒绝，未产生数值结果；严格接入后双端 `454 passed`。正式 Gate B 中，真实全年与八周自然最小弃电分别为 `565,916.122/390,148.306 MWh`，均超过 10% 帽，但弃电率误差 `5.1762` 个百分点超过 1 个百分点门，故 D39 失败。结果 JSON SHA-256 为 `47f33db2d3a00bbe5f70cd342198fd5daa1538663c49b8ec7d39641fd27b645b`；Gate C/D 未启动，不继续加周或放宽阈值。

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

1. D34 的 24 h/336 h 同服务样本、D35 的 24 h 材料性网格、D36 的结构化代表周数据包和 D37 的分块边界 manifest 均已按 SHA-256 冻结；D35 的 `0/1%/5%/10%` 为受控工程尺度敏感性，不得改写为现场最小设备规模。D36 原代表集及 D38/R1 失败记录永久保留；任何修订必须使用新合同、新文件和新哈希；
2. D35 已区分连续微容量与工程尺度响应：自然服务 5%/10% 精确回到无储能，1% heat-only TES 的微小代理改善落在 5% 无差异带内；严格服务保留 TES，但 Hybrid 不安装 BESS，且 TES/Hybrid bounds 重叠。该结论冻结为 E1 受控机制证据，不升级为 E2 杨凌经济赢家；
3. D39 Gate A 通过但 Gate B 定量保真失败，Gate C/D 已按合同停止；下一步必须另立新的时间表示方法与结果前验收合同，不能在 D39 名下继续加周、改权重或放宽阈值；
4. E0-D-25 项目证据与 D24 正式 TES 成本闭合继续并行推进：按空白模板索取合同结算、碳清缴、CHP 科目拆分和双服务 TES VOM，定向补蒸汽充热、对外供热和 power-block retrofit；材料先本地隔离，公开来源不得回填项目账本；
5. 继续争取杨凌一次网供回水温度、抽汽温压、换热器端差/UA、泵曲线、压降和运行记录；现场缺失不阻止公开敏感性，但作者 MT/泵耗情景不得升级为现场基线；
6. D30 继续作为最新 336 h 全局上界。D31/D32 已排除逐变量 OBBT 和可分离日块求和，近期停止同类数值紧化；只有出现保留跨块共同轨迹互斥性且能给出单一 global dual 的新证书思路时才重启；
7. 争取补充 DCS 点表、居民热量公式、热网日报、热平衡图和煤耗曲线年份，以缩小数据敏感性范围。

D36/D37 已关闭原结构化代表周的数据选择、权重和分块状态边界门；原 D38 的 `H*=0.80/G*=0.70` 状态物理失败，R1 baseline 又发生时间聚合可行性反转。杨凌正式 E2 经济结论继续等待 D24/D25 与新的有效时间聚合验证门。该门通过前禁止启动 699 次边界扫描；Agentic 只在第 3/4 章模型 API 和证据接口稳定后进入实现。
