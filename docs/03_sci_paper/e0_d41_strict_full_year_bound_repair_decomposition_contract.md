# E0-D-41 严格全年界—修复分解合同

状态：**第 1–10 节结果前合同已冻结；Gate A 已通过；Gate B–D 尚未执行**

适用范围：D40 真实全年单体 MILP 路线失败后的严格证书路线

日期：2026-07-15

## 1. 本关回答的问题

D41 只回答：在 D40 已锁定的真实 2024 年 8784 h 输入、baseline 物理状态、绝对弃电上限和年度 PCC 外送目标下，能否通过“合法全年下界 + 候选离散轨迹 + 原始全年可行修复”得到 BESS、TES 与 Hybrid 三种内生容量架构的有限、可审计最优性区间。

设架构 \(a\in\{\mathrm{BESS},\mathrm{TES},\mathrm{Hybrid}\}\) 的原始全年容量—运行 MILP 为 \(P_a\)，最优值为 \(z_a^*\)。D41 只有在同时得到合法下界 \(L_a\le z_a^*\) 与经原始全年模型审计的可行上界 \(U_a\ge z_a^*\) 后，才计算

\[
g_a=\frac{U_a-L_a}{\max(|U_a|,10^{-9})}.
\]

D41 是求解方法与证据资格关，不是 E2/E3/E4，不生成杨凌正式 TAC，也不宣布技术赢家。所有成本结果继续标记 `controlled_public_cost_sensitivity_not_formal_project_tac` 与 `formal_project_tac_ready=false`。

## 2. 不可覆盖的既有结论

- D38-R1 已证明原六周代表期可造成服务可行性反转；
- D39 增加第 49/16 周后，弃电率误差仍为 `5.17618942467652` 个百分点，超过结果前冻结的 1 个百分点门；
- D40 Gate A 已证明四架构真实 8784 h 模型可在线性与内存门内构造；
- D40 正式 BESS 单体求解在 `4527.394684 s` 后仍无结果 JSON、有限 incumbent/dual 或不可行证明，分类为 `monolithic_not_viable`；该结果只否定当时的单体执行路线，不证明 BESS 物理不可行。

D41 不得把 D38-R1、D39 或 D40 改写为通过。代表周、聚类日或缩减时域不得提供 D41 的正式目标值、容量、服务量、上下界或技术排序。

## 3. 高质量方法依据与采用边界

截至 2026-07-15，Elsevier 期刊页面显示 `Energy` Impact Factor 为 `9.4`、`Applied Energy` Impact Factor 为 `11.0`。本合同只用这一级别的正式同行评议论文定锚，不使用 `Energies` 等低于用户设定门槛的来源。

| 文献 | 期刊 | 对 D41 的可用依据 | 不可直接照搬之处 |
|---|---|---|---|
| Baumgärtner et al., *DeLoop: Decomposition-based Long-term operational optimization of energy systems with time-coupling constraints*, DOI `10.1016/j.energy.2020.117272` | Energy 198 (2020) 117272 | 分块生成可行解、在原问题重组上界、用 LP 松弛评估下界，并逐步收紧界 | 原文聚焦固定设计下的运行优化；不能自动证明本项目内生容量规划的全局 gap |
| Wakui, Akai and Yokoyama, *Shrinking and receding horizon approaches for long-term operational planning of energy storage and supply systems*, DOI `10.1016/j.energy.2021.122066` | Energy 239 (2022) 122066 | 全年简化问题给下界，短时域原始二元模型给可行轨迹，使用储能终端状态衔接 | 仍以运行规划为主；滚动拼接必须回到本项目原始全年容量模型复核 |
| Zhang and Wakui, *A near-optimal solution method for year-round operational planning of energy supply-storage systems utilizing time-domain decomposition*, DOI `10.1016/j.energy.2025.137358` | Energy 335 (2025) 137358 | 短时域子问题、处理跨期约束的主问题、列生成下界和二元轨迹 finalization | D41 第一版不宣称复现其完整列生成算法；未实现的算法不得写成贡献 |
| Moradi-Sepahvand and Amraee, *Integrated expansion planning of electric energy generation, transmission, and storage for handling high shares of wind and solar power generation*, DOI `10.1016/j.apenergy.2021.117137` | Applied Energy 298 (2021) 117137 | 容量规划与运行子问题分解时，共享投资变量和 chronological operation 必须留在严格协调框架中 | 其电网扩展 Benders 结构与本项目 CHP—PCC—TES 结构不同，只提供规划分解原则 |
| Gonzato, Bruninx and Delarue, *Long term storage in generation expansion planning models with a reduced temporal scope*, DOI `10.1016/j.apenergy.2021.117168` | Applied Energy 298 (2021) 117168 | 时间序列近似良好不代表容量规划解近似良好，长期储能可能出现超过 2 倍的过度或不足投资 | 该文支持禁止把代表期恢复为正式证据，不提供 D41 的数值参数 |

上述文献共同支持“全年耦合不可丢失、上下界必须有数学资格、分块只能服务于协调或候选生成”。D41 的具体证书仍由下述原始模型包含关系和可行性审计建立，而不是由文献权威替代证明。

## 4. 锁定输入、模型与服务

D41 逐字节复用 D40 的以下规范证据，不重新搜索服务值或容量边界：

- `e0d40_full_year_service.json` SHA-256：`1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95`；
- D40 Gate A manifest SHA-256：`23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577`；
- 8784 h 热需求、风光、气温和价格输入及其 D40 已登记哈希；
- 实际全年可再生可用量 `3,395,699.0645758654 MWh`；
- 10% 绝对弃电上限 `339,569.90645758656 MWh`；
- 年度 PCC 外送目标 `4,035,354.738554194 MWh`；
- D40 的 BESS/TES/Hybrid 完整内生容量边界、CHP 约束、BESS 寿命账、TES 三温区/五端口/损失/伴热/泵耗和公开成本敏感性口径。

原始 \(P_a\) 始终是单个真实 8784 h 循环块，全部小时权重为 1。CHP 首尾状态、BESS 能量和 HT/MT/LT 三层 TES 库存只允许在真实年首尾闭合。任何子问题边界、LP 引导状态或滚动窗口都不得改写 \(P_a\)。

## 5. Gate A：证书实现与包含关系审计

Gate A 不求解正式案例，只实现并在小样本/构造模式验证以下四类模型变换：

1. `R0` 全连续松弛：把 \(P_a\) 的所有二元变量域改为 `[0,1]`，不删除任何小时、全年服务、容量上界、库存递推或单全年循环约束；因此 `feasible(P_a) subset feasible(R0_a)`；
2. `R1` 拓扑整数松弛：保留 BESS/TES 安装及 TES 端口等时间不变设计二元，放松全部逐时 CHP、燃料段、BESS/TES 模式二元；其可行域仍包含 \(P_a\)；
3. 离散轨迹提取器：能够完整枚举并固定 CHP `online/startup/shutdown`、燃料段编码、BESS `charge_mode`、TES `ht_receiving_mode/mt_direct_charge_mode` 及全部安装/端口二元，禁止遗漏仍自由的二元变量；
4. 全年修复模型：从未经删时或分块的 \(P_a\) 重建，固定候选离散轨迹后保留全部连续容量、逐时功率/热量/库存、年度服务和真实年首尾循环约束。

Gate A 必须自动证明模型期数 `8784`、加权小时 `8784`、代表期输入未使用、`R0/R1` 非线性计数为零、二元变量分类无遗漏、所有连续容量仍有 D40 锁定的有限界。小样本还必须验证：松弛后的最优值不高于原 MILP，任一经全年修复和原约束审计的目标值是合法上界，故意遗漏二元或破坏全年服务时审计器拒绝产物。

Gate A 失败只能修复实现/审计缺陷，不得改变第 4 节科学输入、服务、模型或第 9 节判定门。修复前失败日志永久保留。

## 6. Gate B：严格全年下界

三个架构按 BESS → TES → Hybrid 串行执行。每个架构先求解 `R0`，再求解 `R1`：

- 求解器仅 HiGHS，随机种子 `0`，全年度模型每次 `12` 线程；
- `R0` 求解器软时限 `600 s`，父进程硬墙钟 `720 s`；
- `R1` 求解器软时限 `1200 s`，父进程硬墙钟 `1320 s`；
- primal/dual feasibility tolerance 均为 `1e-7`，MIP feasibility tolerance 为 `1e-7`；
- 仅 HiGHS 报告的有限、方向正确且与模型目标尺度一致的 dual bound 可进入证书；达到最优时使用最优目标，否则使用终止时的有限 dual bound；
- 最终合法下界为全部通过审计的 `R0/R1` 下界最大值，记为 \(L_a\)。

若 `R0` 被 HiGHS 全局证明不可行，则因其可行域包含 \(P_a\)，可以登记 \(P_a\) 全局不可行；任何超时、进程终止、无有限 dual 或仅某个固定拓扑/子问题不可行都不能冒充原问题不可行。

`R0/R1` 结果必须保存变量域审计、模型规模、有限 bound、终止状态、运行时间、服务约束存在性、输入/代码哈希和原始 HiGHS 日志。下界阶段不得输出技术赢家。

## 7. Gate C：候选离散轨迹生成

Gate C 只为 Gate D 生成候选，不产生正式上下界。它使用 `R1` 的容量、库存和逐时分数解作为引导，在连续真实时序上构造带前视的原始二元子问题：

- 核心提交步长 `168 h`，规划窗口 `336 h`；年尾不足窗口按真实时间顺序环回年初提供前视，但只提交尚未覆盖的年尾小时；
- 子问题保留原始 CHP、燃料段、BESS/TES 模式二元和物理约束，不使用代表周权重；
- 初始库存与 CHP 状态来自已提交轨迹，未提交窗口末端以 `R1` 全年轨迹作为软引导，不设置局部循环来替代真实年循环；
- 容量候选按 `R1` 连续容量依次使用冻结倍率 `1.00/1.10/1.25/1.50`，并受 D40 原上界约束；最后一个预注册回退候选直接使用相应架构全部容量上界和全部允许端口安装；
- 每个 336 h 子问题软时限 `120 s`、父进程硬墙钟 `150 s`、HiGHS `4` 线程；同一时刻最多 `8` 个独立候选任务，总 HiGHS 线程不超过 `32`；
- 候选选择先按“能够完成全部 8784 h 离散轨迹”，再按原始目标值，最后按容量候选序号确定；不得按技术相对排名改变倍率、窗口或回退规则。

局部求解目标、局部 bound、拼接容量和拼接服务量全部标记 `candidate_only=true`。即使所有子问题最优，其拼接结果仍不是 D41 上界；只有 Gate D 在原始全年模型中的可行修复可把它升级为证据。

## 8. Gate D：原始全年可行修复与上界

对 Gate C 产生的每个完整离散轨迹，重新构造原始 \(P_a\)，逐个固定第 5 节列出的全部二元变量，只保留连续容量与全年运行变量。该模型必须仍含 8784 个真实小时、单全年循环、年度弃电帽、PCC 目标、BESS 年吞吐寿命约束和 TES 全部损失/辅机约束。

固定离散轨迹后的全年修复模型使用 HiGHS `12` 线程、随机种子 `0`、软时限 `1200 s`、父进程硬墙钟 `1320 s`。任何有限可行解都必须回写原始 \(P_a\) 并通过：

- 年度 PCC 目标绝对残差 `≤1e-3 MWh`；
- 弃电帽松弛 `≥-1e-3 MWh`；
- 电、热、CHP 转移、BESS 能量与 TES 三层库存等式最大绝对残差 `≤1e-5`；
- 全部活动约束最大归一化违反量 `≤1e-6`；
- 全部待固定二元恰为 `0/1` 且没有漏网自由二元；
- 模型目标与保存的上界相对差 `≤1e-8`，容量、成本、燃料、弃电、PCC 与吞吐快照全部有限；
- 初末 CHP 状态、BESS 能量和 HT/MT/LT 库存满足原始单全年循环，而不是块级近似循环。

通过者的最小目标值记为 \(U_a\)。固定轨迹修复不可行只否定该候选，不证明 \(P_a\) 不可行。若所有冻结候选均失败，分类为 `no_strict_certificate`，必须另立新合同；不得临时增加容量倍率、代表周或手工修改二元轨迹。

## 9. 执行、资源与硬墙钟

所有求解子进程均由独立父进程监控，父进程硬墙钟是非协商上限，不能只依赖 HiGHS 软时限。达到硬墙钟后对完整子进程组发送 `SIGTERM`，最多等待 `30 s`，仍未退出则 `SIGKILL`，并保存 execution sidecar。

执行器必须：

- 使用非缓冲日志，至少每 `5 s` 写入 phase、PID、elapsed、子进程 RSS、父子合计 RSS、主机可用内存和最近心跳；
- 全年单进程 RSS 不超过 `35 GiB`，D41 任务聚合 RSS 不超过 `75 GiB`，主机可用内存不得低于 `15 GiB`；
- 任何阶段触发资源门都停止新增任务并安全终止超限进程，分类不得伪装为不可行；
- 不与其他正式大算例并发；OpenBayes 为规范执行端，本地只做单元和小样本回归；
- 每个正式架构只执行一次完整 D41 流水线。纯接入缺陷允许在正式运行前用独立、永久不合格的 BESS 小样本预检发现，但预检不得提供容量、成本或参数调整依据。

每个架构的总父进程硬墙钟为 `7200 s`。单阶段和总墙钟同时生效，任何超限都必须产生日志和明确分类。

## 10. 预注册判定与后续权限

三个架构分别分类，D41 总判定仍取最弱一档：

| 等级 | 单架构要求 | 后续权限 |
|---|---|---|
| `certified_full_year` | 有合法有限 \(L_a\) 和经原始全年审计的有限 \(U_a\)，且 \(g_a\le0.1\%\)；或 `R0` 对原问题完成全局不可行性证明 | 三架构全部达到该级后，才可另立 E2 受控成本边界合同 |
| `bounded_full_year_not_qualified` | 上下界和全部审计有效，但 `0.1% < g_a ≤ 0.5%` | 只可报告有界区间和方法性能；不得技术排序或进入正式 E2–E4 |
| `certificate_too_wide` | 上下界有效，但 `g_a > 0.5%` | 保留严格区间，另立有效不等式、列生成或更强主问题合同 |
| `no_strict_certificate` | 缺少有限合法下界、缺少全年可行上界、审计失败、硬墙钟/资源失败，或仅有候选拼接结果 | D41 路线未通过；不得用代表期或候选轨迹替代正式证据 |

即使某架构 \(U_a\) 明显较低，也不改变判定。若三个架构都形成有效区间但区间重叠，技术排序仍不成立；若区间不重叠，也只能说明冻结公开成本敏感性下的排序可能被证书区间分离，正式项目经济结论仍等待 D24/D25 成本账户闭合与新的 E2 合同。

## 11. Agentic 定位

D41 可作为硕士论文 Agentic 决策支持层的受限案例：agent 读取冻结合同、核验哈希、编排下界—候选—修复阶段、监控硬墙钟与内存、拒绝无数学资格的 bound，并按第 10 节自动停止或路由。agent 不选择物理状态、不修改容量倍率、服务、成本、gap 或困难架构，也不把候选拼接包装成可行上界。

## 12. 结果登记规则

本文件和权威结构文档形成独立结果前提交后，才允许新增 D41 代码、测试或数值产物。任何结果只能追加在本节之后或写入独立通过/失败记录，不得反向修改第 1–10 节。

规范证据目录固定为：

- 本地：`风光火+熔盐储热/数据采集/e0d41_strict_full_year_decomposition/`；
- OpenBayes：`/root/e0-b-20260711-019f4f64/results/e0d41_strict_full_year_decomposition/`。

首次实现顺序固定为 Gate A 包含关系与审计器 → Gate B 全年下界 → Gate C 候选生成 → Gate D 全年修复。任一前置 Gate 失败时，后续 Gate 不启动。

## 13. Gate A 实现与结果登记

结果前提交 `d7a1929` 之后才新增 `e0d41_strict_full_year_decomposition.py` 和 9 项测试。实现逐个枚举活动二元变量，用完整变量名锁定原 MILP 清单，并按父组件把 `bess.installed`、`tes.installed` 与 `tes.port_installed` 识别为时间不变拓扑二元；全部其余二元归入逐时运行类。R0 把锁定清单全部改为 `[0,1]`，R1 只放松运行类；域变换前后核验变量名、计数、边界与 SHA-256。离散轨迹接口拒绝缺键、额外键、非有限值和分数值，并要求原始二元全部固定后未固定计数为零。

源码与测试 SHA-256 分别为 `c7f45f8c071bb92c6cf7576a76bed71b71e606b7239881cb8baac09b195d2f1e` 与 `cc5c7bee44eea158f8523a4f9d531e407f4004562c8d55735e4ae49d4fe84ddb`。Windows 新增测试为 `9 passed in 2.15s`，D40/D41 合并定向回归为 `24 passed in 3.02s`；OpenBayes 完整回归为 `478 passed in 34.20s`。

正式 Gate A 在 OpenBayes 逐架构 clean process 中执行，未创建求解器：

| 架构 | 活动变量 | 原始二元 | R0 剩余二元 | R1 拓扑二元 | 完整固定后未固定二元 | 运行时间 / s | 峰值 RSS / GiB | 架构 manifest SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BESS | 597,318 | 79,057 | 0 | 1 | 0 | 67.762 | 0.759 | `5d0609fad197977ab5c0dff4e355186c8452d34661036bd1c82a446bf02095e0` |
| TES | 650,052 | 87,840 | 0 | 0 | 0 | 76.311 | 0.865 | `0448e6441574960b9f88b248687f54c438023261ca891192f527c38b20c8e6a3` |
| Hybrid | 685,194 | 96,625 | 0 | 1 | 0 | 81.217 | 0.907 | `59edc53cebd07d820e66a5910b2576589faa4b365a1095ad43e169cb099f9c61` |

三个模型的加权小时均为 `8784`，服务约束与单全年循环均存在，非线性计数为零，`representative_period_input_used=false`、`solver_invoked=false`。TES 的 R1 拓扑二元为零是 D34 已冻结的连续零容量策略所致，不是审计遗漏；BESS 与 Hybrid 各保留一个 BESS 安装二元。完整 fixing audit 对三案均为零遗漏。

Gate A 汇总 manifest SHA-256 为 `50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937`，execution SHA-256 为 `b2d9778e927d3925c7c247ee9816732ed299df3c204fc6a6d746fbe29451b88b`。服务器与本地副本逐文件同哈希，规范目录已固定。首次远程包装命令只在所有 JSON 生成之后，因 Windows here-string CRLF 使最后一条 `sha256sum` glob 带入回车而返回非零；独立验哈确认所有规范产物完整，该包装缺陷未改变代码、模型或判定。

Gate A 因此登记为 `gate_a_passed`。该结果只关闭包含关系、二元覆盖与全年修复接口门，仍没有合法数值下界、可行上界、容量、成本、gap 或技术排序；下一步只允许实现第 6 节的 Gate B 全年严格下界与硬墙钟执行器。

## 14. Gate B 结果前执行器登记

在任何 D41 Gate B 全年求解启动前，已新增 `e0d41_gate_b_lower_bound.py` 与 8 项测试。执行器逐架构串行执行 `R0→R1`，把 HiGHS 软时限与父进程硬墙钟分离，使用独立进程组、`5 s` 非缓冲心跳、进程树/父子合计 RSS 和主机可用内存监控；达到硬墙钟后先发 `SIGTERM`，最多等待 `30 s` 后再发 `SIGKILL`。只有完整通过 Gate A 哈希锁、域审计、8784 h 服务审计、线性审计、最小化目标身份和 finite dual 方向审计的数值才标记为 `formal_lower_bound_eligible=true`。R1 可加载 primal 时把全部变量写入确定性 `csv.gz`，但永久标记 `candidate_only=true`、`formal_bound_eligible=false`。

源码与测试 SHA-256 分别为 `cd532a31d1712a2237e3fe46ccfd395443c16c97a1be6502f2a72861461f1e70` 与 `5ce44ef3c895eb909f23882938b7b737d52145abbcf317ef8ca0ad8abc1aacd3`。新增测试 `8 passed in 2.39s`，D40/D41 定向回归 `24 passed in 2.46s`，Windows 完整回归 `486 passed in 68.78s`，Ruff 检查通过。上述均为小模型和回归测试；尚未启动正式 8784 h Gate B，因而没有合法数值下界、容量、成本、gap 或技术排序。

## 15. Gate B 首次接入拒绝与实现修复

结果前实现提交 `226f590` 同步到 OpenBayes 后，首次 BESS R0 在模型构造完成后的服务审计访问了不存在的 `E0CTimeSeries.periods`，触发 `AttributeError`；正确既有接口为 `period_count`。R0 的 `solver_invoked=false`、`formal_lower_bound_eligible=false`，没有调用 HiGHS。编排器随后错误地把“子进程正常写出 build failure”当作可继续条件而启动 R1；R1 在同一审计处拒绝，同样没有调用 HiGHS。整次运行 `62.698 s`，只构成接入失败，不消耗或替代正式数值证据。

失败产物永久隔离到 `pre_adapter_rejection_period_count/`。R0/R1/汇总 manifest/execution SHA-256 分别为 `993a4b8eb0dcb05c09e7bd83117012ae5599f1eaec0814106368817da683533f`、`fe58f26fe44a1fd6b672673afdca3d1568910b9de4153d1528977f169f1b4893`、`cad5e0e09709f5c06ba1a3168d10d6f714baf5f2e8454540d1463ed750340e2b` 与 `3e0c346d20f46c5834eefa097ccb9ba8dee282374ac47600d4fca15db361d460`。

修复仅把服务小时数读取改为 `case.timeseries.period_count`，并在任一阶段没有 `formal_lower_bound_eligible=true` 时停止后续松弛；没有改动第 1–10 节科学输入、服务、模型、软/硬时限、资源门或判定阈值。修复后源码/测试 SHA-256 为 `2dc3c654367b3a5d0d32e7937d1fe6b21e69c1599faa406be145ee5e60481217` 与 `053b490b4267d676acef50b1168b4d474ea23ac1513cdb357bfb37a55bf5f28a`；新增测试 `10 passed`、D40/D41 定向回归 `26 passed in 3.61s`、Windows 完整回归 `488 passed in 48.92s`，Ruff 通过。修复代码尚待服务器同哈希回归后才能重新启动 BESS。

## 16. Gate B 总证据汇编器登记

正式 Gate B 总判定继续逐字执行第 6、10 和 12 节已经冻结的规则：架构顺序固定为 BESS → TES → Hybrid；首个未通过架构之后不得再启动后续架构；只有三架构全部具有合法有限下界时才允许进入 Gate C。为避免人工摘录改变这些规则，新增只读后处理模块 `e0d41_gate_b_bundle.py`。该模块只读取 Gate A manifest 与逐架构 Gate B manifest，复核 schema、架构身份、Gate A 哈希、代表期禁用标志、技术排序禁用标志、下界数值资格和串行停止规则，并确定性写出 `gate_b_manifest.json` 与 `gate_b_execution.json`。

汇编器不构造模型、不调用求解器、不修改任何已有架构产物，也不生成容量、上界、gap 或技术赢家。源码与测试 SHA-256 分别为 `77084f736eaceb1220198ed1f2043b24ba0be6604352ee383f6e8229f76c29c3` 与 `6bdae782a194d1f4fdefd5dc40121871cab59070bd2cd911d29d85282f9ff867`；新增 3 项测试覆盖“BESS 通过/TES 失败/Hybrid 停止”、失败后仍启动后续架构时拒绝，以及三架构全通过前不得开放 Gate C。D40/D41 合并定向回归为 `29 passed in 4.67s`，Windows 完整回归为 `491 passed in 87.37s`，Ruff 通过。截至本登记，汇编器尚未对正式 Gate B 证据运行；其正式输出只能在本登记形成独立提交后生成并追加记录。
