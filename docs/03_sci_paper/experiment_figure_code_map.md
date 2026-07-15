# SCI 论文：实验 / 图表 / 代码映射

更新时间：2026-07-15

## 1. 当前实验链

| 编号 | 目的 | 核心设置 | 主输出 | 代码状态 |
|---|---|---|---|---|
| E0 | 验证数据、物理与 MILP | 双机 CHP、BESS、HT/MT TES、PCC、寿命成本 | 可行域、能量守恒、现金流审计、TES 证据/成本门、BESS 正式账本、同 PCC 服务 EAC 上限、非燃料成本证书、影子成本稳健性、逐时 PCC、替代调度包络、严格数值证书、16 账户 TAC 路线、项目取证接口、公开敏感性成本账、完整内生容量接缝、工程材料性门、代表周数据门、分块循环状态边界、HiGHS 状态与求解误差 | D30 仍保留最新 336 h 全局上界 `777,141.368858 MWh/a`，D31/D32 为负筛查。D24/D25 仍为 `0/16` 与 `0/4`。D33–D37 已完成公开成本、完整容量、材料性、代表周和分块边界。D38 原高热状态物理失败；R1 baseline 发生代表期可行、真实 8784 h 不可行的反转，当前双端 `445 passed`。真实项目账户、有效时间聚合门、正式 TAC 和 336 h 外界闭合仍未完成 |
| E1 | 隔离价值机制 | No storage / BESS / P2H / TES-E / TES-H / dual TES；控制后恢复真实参数 | 电移峰、热替代、强迫出力释放 | D35 表明自然服务在 5%/10% 门下精确折叠为无储能，1% 仅保留约 `139–142 t` heat-only TES 且代理改善约 `0.03%–0.05%`；严格服务保留 TES，但所有 Hybrid 的 BESS 为零且 TES/Hybrid bounds 重叠。D36/D37 已冻结；原 D38 高热失败和 R1 baseline 时间聚合失败均已登记，下一步先冻结新的代表期修订合同，不能继续机制扫描；`_ch4_p1_milp_compare.py` 只保留为旧原型 |
| E2 | 建立公平成本—消纳前沿 | 四架构 × 5 个共同可行 ε 目标 | TAC—弃风前沿、容量、煤耗、碳排、启停 | 待实现综合 MILP |
| E3 | 识别物理选择边界 | 6 档 \(H^*\) × 5 档架构无关 \(G^*\) × 3 档风电 × 四架构 | BESS / TES / Hybrid / No storage / Indifferent / Infeasible 地图 | `_ch4_p4_sensitivity.py` 只能复用扫描经验 |
| E4 | 识别时长—成本边界 | 低/中/高 3 锚点 × 6 档服务时长 × 7 档 TES 成本倍率；边界二分加密 | 经济边界与边界移动量 | 待实现 |
| E5 | 验证代表周与真实点 | 原 6 周；D39 一次性增至 8 周；年末 48 h；三状态预验证；固定容量 8784 h；全年重优化 | 代表周误差、后悔值、全年赢家 | 原 D38 高热失败且非漏周；R1 baseline 发生时间聚合反转。D39 已结果前冻结原六周加第 49/16 周、重建全部权重及 baseline gate-first 的分类/1 个百分点门；尚无 D39 数据或结果；`_ch4_p3_typdays.py` 仅作旧原型 |
| E6 | 确定性稳健性 | 4 锚点 OAT：循环寿命、TES 效率、碳价、价差、退化口径和可比资源年 | 边界移动与结论稳定区间 | 待实现；不做随机分析 |

完整水平、算例预算与验收标准见：

- `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`

## 2. 主图 / 主表映射

| 编号 | 内容 | 对应实验 | 主要字段 | 状态 |
|---|---|---|---|---|
| Fig 1 | 联营组合、双机 CHP、PCC、BESS 与双品位 TES 拓扑 | E0 | 物理端口与边界 | 待绘制 |
| Fig 2 | CHP 热电可行域、热致最小电出力与模型校准 | E0 | `P/Q/fuel/u` | 待生成 |
| Fig 3 | BESS、TES-E、TES-H、dual TES 价值分解 | E1 | 电移峰、热替代、强迫出力释放、TAC | 待生成 |
| Fig 4 | 杨凌基准点四架构成本—弃风 ε 前沿 | E2 | `epsilon/TAC/curtailment/capacity` | 待生成 |
| Fig 5 | \(H^*\times G^*\) 技术选择地图，三档风电分面 | E3 | winner、次优差、不可行、容量、`I_HC`、`Gamma_C0` | 待生成；全文核心图 |
| Fig 6 | 时长 × TES 相对基准成本倍率，三类物理冲突分面 | E4 | `D/kappa_T/winner/regret` | 待生成；全文核心图 |
| Fig 7 | 边界点代表周与 8784 h 结果对比 | E5 | TAC、弃风、煤耗、容量、赢家 | 待生成 |
| Fig S1 | 边界二分加密与 5% 无差异带 | E3/E4 | refined grid、regret | 待生成 |
| Fig S2 | 参数变化引起的边界移动 | E6 | 边界位移和无差异带 | 待生成 |
| Fig S3 | 4 个 medoid 周、2 个极端周与年末 48 h | E5 | 周权重、覆盖和极端事件 | 待生成 |
| Tab 1 | 系统物理、价格与碳参数 | E0 | 来源、基准值、范围、等级证据 | 待核查 |
| Tab 2 | BESS 与 TES 功率、质量、效率、寿命和成本参数 | E0 | 技术特定参数、成本拆分、价格基年与证据等级 | BESS 正式账本已闭合并在 D34 转成共同 PCS 规划系数；D24 严格账户 `0/16`。D33 公开敏感性低/基准/高组合必须同时报告聚合/分项模式、作者价格年和代理账户；不得与杨凌正式参数混表 |
| Tab 3 | 公平比较口径与四架构定义 | E1/E2 | 服务约束、容量变量、成本项 | 待整理 |
| Tab 4 | 杨凌基准点最优配置与运行结果 | E2 | TAC、P/E/盐量、弃风、煤耗、碳排 | 待生成 |
| Tab 5 | 代表周—全年验收 | E5 | 误差、后悔值、MIP gap、运行时间 | 待生成 |
| Tab S1 | HiGHS 求解性能 | E0-E6 | gap、时间、RSS、失败重试 | 待生成 |

## 3. 现有代码的科学地位

| 文件 | 定位 | 是否可直接形成主结论 |
|---|---|---|
| `风光火+熔盐储热/_ch4_p1_milp_compare.py` | 固定容量的机制探索 | 否 |
| `风光火+熔盐储热/_ch4_milp.py` | 双机 + PCC + MILP 原型 | 否，需拆分 TES 端口并加入容量成本 |
| `风光火+熔盐储热/_ch4_p4_sensitivity.py` | 固定 TES 的一维敏感性 | 否 |
| `风光火+熔盐储热/_ch4_p3_typdays.py` | 典型期原型 | 否，需代表周与全年验证 |
| `风光火+熔盐储热/_ch4_p3_nsga.py` | 启发式容量搜索原型 | 否，核心改为综合 MILP |
| `风光火+熔盐储热/杨凌_合并逐时_2024_清洗.csv` | 旧 2024 年统一输入候选 | 否；仅保留历史探索，热数据以 E0-B 新产物为准 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/e0b_heat_source_ledger_2024.csv` | 52,707 行源证据台账 | 是；保留重复、非网格、原值、修复值与质量标志 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/e0b_heat_hourly_2024.csv` | 8,784 h net / forward / zero-sensitivity | 是；进入模型前仍须显式选择非负需求适配 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/manifest.json` | E0-B schema v2 构建合同 | 是；记录源 SHA、规则、计数、签名与输出 SHA |
| `风光火+熔盐储热/数据采集/e0c_heat_demand_adapter/` | 三份全年非负需求、六份窗口产品及真实双机桥接诊断 | 是；主口径/敏感性、修改审计、规范哈希和 runtime sidecar 分离 |
| `风光火+熔盐储热/杨凌机组数据/` | 机组台账、电功率与供热原始材料 | 核心工程证据，需脱敏和口径记录 |

## 4. 当前新代码映射

`风光火+熔盐储热/tes_bess_boundary/` 已建立，使用独立 `src/` 包和 Pyomo + HiGHS，不继续叠加 `_ch4_*` 单文件脚本：

| 模块 | 职责 | 对应实验 | 状态 |
|---|---|---|---|
| `src/tes_bess_boundary/data.py` | 单位、8784 h 完整性与恒等式校验 | E0/E5 | 已实现结构审计 |
| `src/tes_bess_boundary/raw_heat.py` | 原始 Excel A 列、源追溯、10 min 网格、重复与异常审计 | E0 | 已实现 |
| `src/tes_bess_boundary/heat_dataset.py` | 正式源台账、三口径小时数据、质量标志与 manifest | E0/E5 | E0-B 已实现并通过真实双构建 |
| `src/tes_bess_boundary/heat_adapter.py` | 正式全网格/manifest 校验、三口径非负消费规则、窗口与修改审计 | E0/E5 | 已实现；三份全年产品与六份窗口产品跨平台哈希一致 |
| `src/tes_bess_boundary/heat_bridge.py` | 两个正交窗口 × 三口径的真实双机 No-storage/HiGHS 桥接诊断 | E0 | 六案均 optimal、gap 0；规范结果与 runtime sidecar 分离 |
| `src/tes_bess_boundary/heat_bridge_cli.py` | 一键重建 E0-C 适配与桥接证据 | E0 | 已实现，本地/OpenBayes 复现一致 |
| `src/tes_bess_boundary/solver.py` | 确定性 `appsi_highs` 配置与求解元数据 | E0-E6 | 已实现最小版本 |
| `src/tes_bess_boundary/economics.py` | 项目 NPV/EAC、价格转换、分部件更换/残值/FOM、BESS 两锚点、防双计与年度计分合同 | E0/E2-E6 | E0-D-1–D-3 已实现；2024 CNY、转换审计和三角色成本分类通过独立金标准，正式数值待换算 |
| `src/tes_bess_boundary/price_basis.py` | 官方 CPI/HICP/汇率快照、逐源哈希与唯一转换构造 | E0/E2-E6 | E0-D-4 已实现；正式快照本地/OpenBayes 哈希一致 |
| `src/tes_bess_boundary/tes_cost_mapping.py` | 盐/显热/三罐/五端口容量基准、部件温区覆盖与寿命 portfolio 绑定 | E0/E2-E6 | E0-D-5 已实现；本地容量、端口和温区金标准通过，正式成本值待闭合 |
| `src/tes_bess_boundary/formal_tes_costs.py` | TES 12 账户正式来源就绪度、聚合锚点隔离与复合证据审批 | E0/E2-E6 | E0-D-15 已实现；当前全部账户阻断，不颁发 TES 正式证书 |
| `src/tes_bess_boundary/public_tes_costs.py` | 聚合包/分项台账互斥、Energy+ 来源等级、作者价格年、代理映射、CNY2024 EAC 与公开敏感性门 | E0/E1/E3-E4 | E0-D-33 已实现；显式确认后仅允许 `public_sensitivity`，永久 `formal_project_eligible=false` |
| `src/tes_bess_boundary/capacity_planning.py` | BESS 名义能量/充放功率/共同 PCS，TES 盐/罐/五端口、可变损失/辅机、2–24 h 服务、独立额定轨迹和充热可达性 | E0/E1-E4 | E0-D-34 已实现；全部新增约束和成本表达式保持线性 |
| `src/tes_bess_boundary/planning_model.py` | 把内生 BESS/TES 接入双机 CHP、风光、供热、公共 PCC、年度服务与总成本 | E0/E1-E6 | E0-D-34 已实现四架构构建期隔离，并返回 objective primal/dual bounds 与实际 gap |
| `src/tes_bess_boundary/e0d34_endogenous_capacity_sample.py` | 正式热量 + 旧风光双窗口四架构受控样本 | E0/E1 | 已实现；无储能两阶段冻结共同弃电/PCC 服务，24/336 h 基线和 1% 严格 ε 初筛已执行；其尺度疑问由 D35 接续闭合 |
| `src/tes_bess_boundary/e0d35_tes_materiality.py` | 锁定 `0/1%/5%/10%` 网格、盐量/五端口半连续门、同服务单探针与逐项审计 | E0/E1 | 已实现；16 个主探针全部通过，禁止解释为现场最小规模 |
| `src/tes_bess_boundary/e0d35_materiality_bundle.py`、`数据采集/e0d35_tes_materiality/` | 选择 4 个自然服务 gap=0 复算、生成 16 行规范 CSV/manifest/execution 和原始哈希证据 | E0/E1 | 已实现；自然 5%/10% 精确折叠无储能，严格 Hybrid 全部折叠 TES |
| `src/tes_bess_boundary/e0d36_representative_weeks.py`、`数据采集/e0d36_representative_weeks/` | 确定性 PAM、热峰/高可再生压力强制周、52 周归属、年尾 warm-up/计分和规范证据 | E0/E5 | 已实现；六周与权重已冻结，1080 行/8784 加权小时，三个规范文件跨平台逐字节一致；未运行优化 |
| `src/tes_bess_boundary/tes_break_even.py` | 同服务无罚值的全系统 TES EAC 上限、燃煤/弃电/PCC/辅机差值和四种容量分母视图 | E0/E1 | E0-D-16 已实现；当前只能形成探索性阈值，不分摊部件单价、不启动 E1 |
| `src/tes_bess_boundary/tes_break_even_adapter.py` | 实际 E0-C 年度解的可比性审计、TES 所有权成本剔除和成本范围缺口披露 | E0/E1 | E0-D-17 已实现；系统 VOM/碳/结算未闭合时强制探索性主张 |
| `src/tes_bess_boundary/e0d17_exploration.py` | 正式热量 + 旧风光形状的 24 h/两周固定容量级联 TES 探索与 canonical 导出 | E0 | E0-D-17 历史基线；24 h 零 gap 跨平台哈希一致，两周未在旧 formulation 下闭合 |
| `数据采集/e0d17_tes_break_even/` | 24 h 冬季典型日年化阈值 CSV、manifest 与运行时 sidecar | E0 | 仅燃料范围探索证据，不是全年结果或 E1 技术赢家 |
| `src/tes_bess_boundary/e0d18_performance.py` | 24 h 精确验收、336 h 有界验收、固定整数弃电次目标与 EAC 区间传播 | E0 | 24 h gap 0；336 h 主目标 gap 0.004800、次目标 gap 0；不把界区间压成点估计 |
| `数据采集/e0d18_tes_break_even_interval/` | 两窗口规范 CSV、自哈希 manifest 与非规范运行时 sidecar | E0 | 本地/OpenBayes canonical 哈希一致；336 h 为燃料范围探索性区间，不是 TES 价格、全年 TAC 或 E1 赢家 |
| `src/tes_bess_boundary/e0d19_same_pcc_service.py` | 无储能自然外送目标、严格同年度 PCC 服务、固定平价抵消、336 h 零偏差 warm start 与 EAC 区间 | E0 | 24 h 为 12.893 百万元/a 精确点；336 h 为 15.031–16.330 百万元/a、主 gap 0.2545%；仍非正式 TAC |
| `数据采集/e0d19_same_pcc_service/` | E0-D-19 双窗口 canonical、服务身份、primal/dual 与求解 sidecar | E0 | PCC 差为 0；Windows/OpenBayes CSV 与 manifest 逐字节一致 |
| `src/tes_bess_boundary/operating_cost_evidence.py` | 四类非燃料成本的项目范围、数值、边界、驱动和技术匹配门；杨凌 H 列重叠审计 | E0/E2-E6 | E0-D-20 已实现；`formal_portfolio_ready=false`，不生成 TAC 数值 |
| `数据采集/e0d20_operating_cost_evidence/` | 四账户证据、两机 H/J/M 原始观察、源哈希和就绪度 manifest | E0 | schema v1 规范产物；CSV 6 行，当前仅证明阻断边界 |
| `src/tes_bess_boundary/shadow_cost_robustness.py` | 哈希锁定 D19、联动 D20，并将四账户有符号影子成本或合计不利压力传播到燃料空间 | E0/E6 | E0-D-21 已实现；只输出 sensitivity 阈值与稳健性分区，`formal_tac=false` |
| `数据采集/e0d21_shadow_cost_robustness/` | 两窗口组合/单账户阈值、压力点和源锁定 manifest | E0 | thresholds/stress 各 10 行；24 h 阈值 12.893 百万元/a，336 h 翻转带 15.031–16.330 百万元/a |
| `src/tes_bess_boundary/pcc_settlement_exposure.py` | 重求解 D19、导出逐时 PCC、审计同年度交付，并计算固定平价恒等式与任意有界价格跨度包络 | E0/E6 | E0-D-22 已实现；24 h/336 h 重新分配 26.010/31.228 GWh/a，未指定实际价格，未证明连续解唯一 |
| `数据采集/e0d22_pcc_settlement_exposure/` | 360 行两架构逐时 PCC、2 行价差暴露汇总、D19 源锁和科学边界 manifest | E0 | schema v1 规范产物；`actual_price_path_assigned=false`、`trace_solution_uniqueness_proven=false`、`formal_tac=false` |
| `src/tes_bess_boundary/alternative_dispatch_envelope.py` | D19/D22 双源锁、两架构联合 MILP、主成本/弃电 cap、L1 双向极值、336 h D19 状态 warm start 与方向正确的 primal/dual | E0/E6 | E0-D-23 已实现；24 h 精确闭合，336 h 保留严格宽区间，`formal_tac=false` |
| `数据采集/e0d23_alternative_dispatch_envelope/` | 两窗口 solver 极值、服务/cap 审计、源锁 manifest 与 runtime sidecar | E0 | schema v1 规范产物；336 h 最大 solver incumbent 未支配 D22 外部可行证人，科学解释须合并两者 |
| `src/tes_bess_boundary/d26_numerical_certification.py` | 年度 cap 无量纲化、`1e-9` 严格容差、条件/开放整数范围、固定整数域移除、条件面 warm witness、PCC L1 重算与有限界标志 | E0/E6 | E0-D-26 已实现；24 h 全局严格包络 `26,010.171143–26,010.174918 MWh/a`；336 h 内界改善但外界仍宽，`formal_tac=false` |
| `src/tes_bess_boundary/d26_certification_bundle.py`、`数据采集/e0d26_numerical_certification/` | 8 个探针的身份/残差/证人支配验证、两窗口确定性 CSV、manifest 与非规范 execution sidecar | E0 | D26 规范汇总；`termination` 与 `bound_certificate_complete` 分离，条件面最大 incumbent 不冒充全局最优 |
| `src/tes_bess_boundary/d27_direction_generation.py` | 固定支持方向、符号固定点、轨迹 L1 重算、正负差值分解与全局有限界 | E0/E6 | 24 h 精确最大值 `26,010.174929 MWh/a`；336 h 严格最大区间 `[36,382.462799,1,081,649.139331] MWh/a`；方向 dual 不是全局界 |
| `src/tes_bess_boundary/d27_certification_bundle.py`、`数据采集/e0d27_direction_generation/` | 24 h 联合探针、336 h 方向/全局探针的科学边界、证人支配、严格残差和确定性汇总 | E0 | D27 规范汇总；明确拒绝将 support dual 提升为全局 L1 上界 |
| `src/tes_bess_boundary/d28_multistart_direction.py` | `negated`/`alternating`/循环移位符号种子、负 support 证人、返回轨迹 L1 重算与单步方向筛查 | E0/E6 | 336 h 两个预注册种子均未改善 D27 下界，均未达固定点；只生成全局可行下界，不生成全局上界 |
| `src/tes_bess_boundary/d28_multistart_bundle.py`、`数据采集/e0d28_multistart_direction/` | 两种子科学边界、严格残差、改善量与确定性 CSV/manifest/execution 汇总 | E0 | D28 规范汇总；`support_dual_is_global_l1_upper_bound=false`、`global_l1_bound_generated=false` |
| `src/tes_bess_boundary/d29_export_linked_bound_tightening.py` | D27 正负分解上的逐时外送/余量有效不等式、正负年化质量平衡、外送/余量总帽与 D27 区间合并 | E0/E6 | 24 h 保留精确点；336 h global dual `845,052.030831 MWh/a`，较 D27 改善 `21.8737%`；整数可行集不变 |
| `src/tes_bess_boundary/d29_certification_bundle.py`、`数据采集/e0d29_export_linked_bound_tightening/` | 双窗口 D27 源锁、cut audit、primal/轨迹重算/dual、严格区间与确定性汇总 | E0 | D29 规范汇总；全部主整数/符号二元开放，finite global dual 才进入上界 |
| `src/tes_bess_boundary/d30_physics_service_bound_tightening.py` | CHP/热平衡/TES 端口与辅机上界的静态 PCC 外包络、年度 PCC 服务传播、区间感知符号不等式和 reopened global probe | E0/E6 | 24 h 保留精确点；336 h 正向宽度平均收紧 `33.3107%`，global dual `777,141.368858 MWh/a`，较 D29 改善 `8.0363%` |
| `src/tes_bess_boundary/d30_certification_bundle.py`、`数据采集/e0d30_physics_service_bound_tightening/` | bounds-only 双窗口审计、D29 源锁、已知证人包含性、primal/轨迹重算/dual、数值钳制审计和确定性证书 | E0 | D30 规范汇总；全部主整数/符号二元开放，整数可行集不变，只有 finite global dual 进入上界 |
| `src/tes_bess_boundary/d31_intertemporal_obbt.py` | 完整 D19 单架构跨时段连续松弛、逐时 PCC min/max OBBT、并行 worker 重建审计和可选等价/global probe | E0/E6 | 24 h 96 LP、336 h 1344 LP 全部最优；24 h 等价门精确，336 h 宽度增量不足 `0.1%`，未启动全局 probe |
| `src/tes_bess_boundary/d31_screening_bundle.py`、`数据采集/e0d31_intertemporal_obbt/` | D30/D19/D22 源锁、双窗口 OBBT 屏幕、1% 资源门槛、24 h 等价性门和确定性负筛查证书 | E0 | 336 h 明确保留 D30 严格区间；门槛不是结果前预注册，不得误写成新上界或全局排除 |
| `src/tes_bess_boundary/d32_joint_block_envelope.py` | 两架构完整路径上的连续 24 h 块 L1 dual、主整数松弛、块内符号二元、有效块割与 reopened 等价探针 | E0/E6 | 24 h 全局等价门精确；336 h 14 个有限块 dual 之和高于 D30，结果前 1% 门未通过，不启动 336 h global probe |
| `src/tes_bess_boundary/d32_screening_bundle.py`、`数据采集/e0d32_joint_block_envelope/` | 双窗口块屏幕、D30/D31/D22 源锁、D22 分块证人、24 h 等价门、无 336 h probe 证明与确定性负筛查证书 | E0 | D32 排除可分离日块求和路线；最新 336 h 严格区间继续引用 D30，不产生实际价差、TAC 或技术赢家 |
| `src/tes_bess_boundary/formal_tac_evidence_route.py` | D15/D20 合并、16 账户路线、Energy+ / 官方工程 / 项目原始层级隔离、期刊指标审计与禁止用途 | E0/E2-E6 | E0-D-24 已实现；`strict_formal_account_count=0`、`layered_route_approved=false`、`formal_tac_ready=false` |
| `数据采集/e0d24_formal_tac_evidence_route/` | 16 行账户路线、5 条公开来源和自哈希 manifest | E0 | schema v1 规范产物；不包含成本估计，不产生技术赢家 |
| `src/tes_bess_boundary/project_primary_evidence_intake.py` | 四账户 51 字段要求、当前 coverage、接收证书语义和隐私隔离导出 | E0/E2-E6 | E0-D-25 已实现；`ready_account_count=0`、`formal_tac_ready=false`、`e1_ready=false` |
| `数据采集/e0d25_project_primary_evidence_intake/` | 字段合同、四账户覆盖、空白提交模板与自哈希 manifest | E0 | schema v1；不输出提交值或本地受限来源身份 |
| `src/tes_bess_boundary/tes_topology_evidence.py` | 五条 TES 路径的 Energy+ 证据等级、模块化合成与本文扩展披露 | E0/E2-E6 | E0-D-6 已实现；`MT→LT` 供热级联必须显式声明为 proposed extension |
| `src/tes_bess_boundary/tes_heat_delivery.py` | 温度来源身份、MT→LT 两端夹点、HITEC 温区、可交付热量与盐/水流量 | E0/E2-E6 | E0-D-7 已实现；120/70 °C 只作核心参考情景，MT 不由夹点唯一确定 |
| `src/tes_bess_boundary/tes_temperature_scenarios.py` | MT 归一化低品位焓占比、三点作者敏感性、来源身份与逐点认证 | E0/E6 | E0-D-8 已实现；232.5/285/337.5 °C 不得写成现场或论文直接值 |
| `src/tes_bess_boundary/tes_loss_auxiliary.py` | 库存—环境温差损失、固定伴热、五路径比泵耗、五路径累计吨位、参数身份与时间步复合 | E0/E2-E6 | E0-D-9A/9B-2 已实现；正式杨凌参数仍缺失 |
| `src/tes_bess_boundary/tes_loss_calibration.py` | Trevisan/Klasing 聚合锚点、低/基准/高损失—伴热作者集、三 MT 等留存反标定与聚合反推量审计 | E0/E6 | E0-D-9B-1 已实现；三 MT 的 24 h Pyomo/HiGHS 交叉验证通过 |
| `src/tes_bess_boundary/tes_pump_calibration.py` | Trevisan 液压锚点、Wang HITEC 物性、40/50/200 kPa 三档五路径泵耗、45 MWhth 标准循环与 3×3 确定性产物 | E0/E6 | E0-D-9B-2 已实现；结果是作者筛查，不是杨凌现场标定 |
| `src/tes_bess_boundary/cost_evidence.py` | 期刊层级、价格基年、容量分母、技术边界、底层出处和允许用途的正式成本认证门 | E0/E2-E6 | E0-D-15 扩展为 16 条记录并区分可审计一手报价；当前只认证 Rahman BESS，TES 继续阻断 |
| `src/tes_bess_boundary/formal_bess_costs.py` | Rahman 2019 USD 原值、边界拆分、三接缝策略、统一价格转换、fixed-capacity 账本和共同 PCS 规划系数 | E0/E2-E6 | E0-D-14 fixed-capacity 与 E0-D-34 endogenous planning 接缝均已实现；原始来源对象继续显式未决 |
| `src/tes_bess_boundary/sensitivity_cost_anchors.py` | NREL/OEDI 4 h BESS 工作簿哈希加载、功率/可用能量双分母 CAPEX、含 augmentation FOM 防双计与 2024 CNY 转换 | E0/E4/E6 | E0-D-11 已实现；仅作官方工程敏感性锚点，`formal_baseline_eligible=False` |
| `数据采集/e0d11_sensitivity_cost_anchors/` | NREL 2022 ATB v3 原工作簿、精确单元格提取 JSON 与 manifest | E0/E4/E6 | 本地/OpenBayes 哈希一致；RTE 0.85/0.86 冲突已排除，不随成本锚点入模 |
| `research-sessions/2026-07-13-e0d12-formal-cost-closure/` | Energy+ BESS/TES 来源日志、主张—证据图、访问日志和机器候选矩阵 | E0/E2-E6 | 13 个候选中 Rahman BESS 为唯一 `formal_candidate=true`；Guccione/TES 继续阻断 |
| `research-sessions/2026-07-13-e0d14-bess-join-closure/` | BESS 寿命所有权、AC 放电 VOM 与 PCS 5–100 MW 口径的证据—决策记录 | E0/E2-E6 | E0-D-14 已闭合 fixed-capacity BESS 三接缝；TES/系统 TAC 继续阻断 |
| `research-sessions/2026-07-13-e0d15-tes-formal-cost-closure/` | Trevisan/Klasing/Li/Guccione/DLR 逐源复核、访问日志与 TES 正式账户判定 | E0/E2-E6 | 严格路线未闭合；DLR 仅为 2020 EUR 两罐工程聚合锚点 |
| `research-sessions/2026-07-14-e0d20-operating-cost-evidence/` | 项目台账、官方公开来源、Energy+ 期刊筛选与四账户判定 | E0/E2-E6 | 分时结算、碳履约、CHP VOM、TES VOM 均未获正式证书 |
| `research-sessions/2026-07-14-e0d21-shadow-cost-robustness/` | D19→D20→D21 区间传播方法、结果备忘和禁止性主张 | E0/E6 | 来源无关风险预算已闭合；没有新增项目成本证书 |
| `research-sessions/2026-07-14-e0d22-pcc-settlement-exposure/` | 逐时 PCC、价差包络、D21 临界价差交叉解释和唯一性边界 | E0/E6 | 当前选择轨迹暴露已闭合；由 D23 继续检验替代调度 |
| `research-sessions/2026-07-14-e0d23-alternative-dispatch-envelope/` | 联合极值、D19 warm start、D22 可行证人和两窗口界值解释 | E0/E6 | 24 h 精确闭合；336 h 保留宽区间并禁止把 dual 当实际暴露 |
| `research-sessions/2026-07-14-e0d24-formal-tac-evidence-route/` | Energy+、NREL/DLR/DOE 来源日志、16 账户主张—证据图和访问失败边界 | E0/E2-E6 | 严格账户 `0/16`；公开来源不能替代项目账本或聚合反分摊 |
| `research-sessions/2026-07-14-e0d25-project-primary-evidence-intake/` | 杨凌工作簿覆盖复核、受限资料隔离边界和 51 字段取证映射 | E0/E2-E6 | 三账户 missing、CHP 6/14 partial；没有新增正式成本证书 |
| `docs/03_sci_paper/e0_formal_cost_closure_audit.md` | 严格证据门、关联证据政策及当前证书边界 | E0/E2-E6 | Rahman 来源层证书已颁发；完整 TAC 与 TES 证书未颁发 |
| `docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md` | Rahman 关联证据、2019 USD→2024 CNY、三接缝决策与 fixed-capacity BESS 账本 | E0/E2-E6 | E0-D-14 权威合同 |
| `src/tes_bess_boundary/components/chp.py` | 台账凸包、毛/净口径、显式低负荷规则、UC 与精确 PWL | E0-E6 | E0-D-18 新增精确对数段编码与可选连续启停包络；默认旧 formulation 保持兼容，二维燃料面与经济敏感性待补 |
| `src/tes_bess_boundary/components/bess.py` | 交流侧 SOC、能量口径与最小 Pyomo 组件 | E0-E6 | 已实现 E0-A；模型外退化经济核、年度 AC 吞吐成本及 EFC 接缝已完成；cell/PCS/BoP 候选证据与转换机制已建，正式指数快照待补 |
| `src/tes_bess_boundary/components/molten_salt.py` | HT/MT/LT 盐量、焓与最小 Pyomo 组件 | E0-E6 | E0-D-18 新增路径特定流量上界、紧 Big-M 与零容量模式固定；正式成本和现场数值校准待补 |
| `tests/` | 真实数据、本构、适配/桥接、线性、四架构、HiGHS、寿命、TES 温区/拓扑/夹点/MT/损失辅机、成本证据、BESS 正式账本、TES 正式就绪度、盈亏平衡、E0-D-17–D38-R1 回归 | E0 | Windows / OpenBayes 最新均为 `445 passed`；最终时间见 `e0_validation_status.md`；关闭 pytest cache；求解器仅 HiGHS |
| `src/tes_bess_boundary/model.py` | 统一 fixed-capacity Pyomo 模型、四架构开关、年度经济/弃电/PCC 服务审计、逐时 PCC 只读轨迹与 TES 五路径运行审计 | E0-E6 | fixed-capacity 权威基座；D34 由 `planning_model.py` 复用其双机 CHP/PCC/年度服务并替换储能块。完整 TAC 与 336 h 数值闭合仍待补 |
| `src/tes_bess_boundary/e0d36_representative_weeks.py` | 4 个 PAM medoid + 2 个强制极端周及年尾段 | E0/E3-E5 | D36 数据构造已实现；由 D37 适配器严格读取，不再直接进入旧单循环模型 |
| `src/tes_bess_boundary/e0d37_block_horizon.py` | D36 哈希/结构校验、七块时域和 1080 时段规划输入适配 | E0/E5 | 已实现；保持六周权重与 24 h warm-up + 48 h 计分段不变 |
| `src/tes_bess_boundary/e0d37_structural_audit.py` | 完整 Hybrid 分块边界只建模审计 | E0/E5 | 已实现；不调用求解器，规范 manifest 双端 SHA-256 为 `1e460ef35921d670a23867ad39716302c7f4eecb90cfd225ee628ea7bbd0ddb6` |
| `src/tes_bess_boundary/e0d38_prevalidation.py`、`planning_model.py` | 同服务参考、完整容量快照、代表期/全年可续跑任务和固定容量回放 | E0/E5 | 已实现；baseline 正式链确认代表期—全年可行性反转 |
| `src/tes_bess_boundary/e0d38_static_feasibility.py` | PCC—CHP 静态最大供热必要条件与逐时违规定位 | E0/E5 | 已实现；490 MW 下 `766.077 MWth`，36 h 超限且全在代表周 4 |
| `src/tes_bess_boundary/e0d38_audit.py` | 完整 D38 bundle 的 gap、服务、成本、弃电、燃煤、后悔值、容量与 provenance 审计 | E0/E5 | 已实现；拒绝陈旧代码/混合服务产物和可行性反转 |
| `src/tes_bess_boundary/e0d38_weekly_diagnostic.py` | 实际 52 周与冻结 D36 分配的零燃料最小弃电差异诊断 | E0/E5 | 已实现；第 49/16 周为最大两个单周低估，诊断不构成事后调参 |
| `docs/03_sci_paper/e0_d38_three_state_representative_full_year_prevalidation_contract.md`、`e0_d38_original_high_heat_state_failure.md` | 原三状态结果前合同及不覆盖合同的失败记录 | E0/E5 | 原合同不能关闭；不得删除失败状态后写成通过 |
| `docs/03_sci_paper/e0_d38r1_revised_high_heat_prevalidation_contract.md`、`e0_d38r1_baseline_temporal_aggregation_failure.md` | 一次性 `H*=G*=0.70` 修订、文件隔离、执行后 baseline 失败 | E0/E5 | R1 静态检查通过但 baseline 时间聚合门失败；新修订必须另立结果前合同 |
| `docs/03_sci_paper/e0_d39_service_aware_representative_week_refinement_contract.md` | 原六周 + 第 49/16 周、D36 距离重分配、独立文件和 gate-first 验收 | E0/E5 | 结果前合同已冻结；尚未生成 D39 数据或求解结果 |
| `scenarios.py` / `run_sweep.py` | 场景网格和并行断点续跑 | E2-E6 | 待实现 |
| `validate_full_year.py` / `postprocess.py` | 全年回代、边界和机理分解 | E1-E6 | 待实现 |

E0 当前状态详见 `docs/03_sci_paper/e0_validation_status.md`。

## 5. 服务器映射

- 平台：OpenBayes CPU-xxlarge；
- 已核对：60 CPU、约 97 GiB 可用内存、Python 3.10.18；
- 求解器：HiGHS，通过 `highspy`；
- 隔离环境：`/root/e0-b-20260711-019f4f64/tes_bess_boundary/.venv-e0`；
- 已验证：`Pyomo 6.10.1`、`highspy / HiGHS 1.15.1`，微型 MILP 状态 `optimal`；
- 完整 E0 当前回归见 `e0_validation_status.md`。D27 三探针、D28 两种子筛查、D29 双窗口上界探针、D30 双窗口 bounds-only/全局探针、D31 双窗口 OBBT、D32 双窗口联合分块屏幕与两轮 24 h 等价性探针及其确定性汇总均在服务器生成；D23–D32 既有规范产物保持锁定；
- 复现依赖：`风光火+熔盐储热/requirements-highs.txt`；
- 未安装且当前不需要：`oemof.solph`；
- 输出路径：`/output`；
- 初始并发：代表周 `20×2` 线程，8784 h 固定容量 `4×4`，全年重优化 `2×4`；再按峰值 RSS 调整，总 HiGHS 线程不超过 56；
- 凭据与密码禁止写入仓库、配置或日志。
- 最新版代码和最小必要杨凌原始数据位于 `/root/e0-b-20260711-019f4f64/`；D23、D24、D25 独立再生成件分别位于 `e0d23_alternative_dispatch_envelope_remote_v3/`、`e0d24_formal_tac_evidence_route_remote/`、`e0d25_project_primary_evidence_intake_remote/`。D25 只上传新增源码/测试并在远端生成空白取证产物，不上传本地受限资料、凭据或提交值。

## 6. 旧稿边界

原 `run.py --exp 1/2/3/4`、德国/松山湖、EQD/Carnot 和对应 `论文撰写/paper/` 文件属于旧独立稿，不再映射到当前 SCI。若未来继续投稿，应单独维护，不能把其结果混入本实验链。
