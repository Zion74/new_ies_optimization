# E0-D-52 全年检查点化有界回退 Relax-and-Fix—BESS 原成本上界恢复合同

状态：**结果前合同已冻结；尚未实现、尚未通过 Gate A、尚未启动 8784 h 正式优化。**

冻结日期：2026-07-17。

## 1. 研究问题与准入范围

D50 在完整 8784 h 年度模型上以 `336 h` 整数前视、`168 h` 提交形成无回退单路径，阶段 `0/1/2` 成功提交 `1,513` 个物理二元，阶段 `3` 在该固定前缀下无 incumbent。D51 随后只在 24 h 缩短时域验证了原子检查点、clean 重放、一步回退、精确 no-good cut、燃料提升和原成本 repair，Gate 0 manifest 为 `gate0_controller_validated`，但明确不授权全年运行。

D52 只回答一个正式数值问题：

> 在不改变 D50 原始 8784 h BESS 物理模型、容量边界、年度服务、燃料精确提升和原成本 clean repair 的前提下，D51 已验证的检查点化一步回退控制器能否形成第一条可审计的全年 BESS 原 MILP 可行轨迹与工程数值上界？

首次正式范围只允许 BESS。TES、Hybrid、E2–E4、699 点扫描、项目 TAC 和技术排序均不在本合同权限内。D52 不是代表期、滚动调度或局部窗口模型；所有阶段始终保留同一个真实 8784 h 年度可行域。

## 2. 方法沿革与文献边界

D52 不新增低等级来源，继续复用 D50 已审计的 Energy / Applied Energy 方法依据：

- Baumgärtner et al., *Energy* 198 (2020), DOI `10.1016/j.energy.2020.117272`：分解候选最终必须回到原问题复核；
- Wakui et al., *Energy* 239 (2022), DOI `10.1016/j.energy.2021.122066`：长时域离散轨迹可逐步确定，但必须显式保留储能跨期状态；
- Zhang and Wakui, *Energy* 335 (2025), DOI `10.1016/j.energy.2025.137358`：短时域整数 finalization 与全局协调可分开设计；
- Moradi-Sepahvand and Amraee, *Applied Energy* 298 (2021), DOI `10.1016/j.apenergy.2021.117137`：容量规划分解必须保留共享投资变量和 chronological operation 的严格协调。

文献只支持方法方向。D52 的上界资格仍只来自“完整二元快照在未修改原始全年模型中经 clean 原成本 repair 与独立审计可行”，不来自文献权威、阶段状态或缩短时域结果。

## 3. 冻结输入、代码与上游证据

| 对象 | 锁定值 |
|---|---|
| D50 唯一正式 manifest | `3efdbba505ed2e34d14592e2384a67d074ae8ee08f35a32acdaa6b9639f10e91` |
| D51 Gate 0 manifest | `883d4c0bad9bb9e66011d769b5c7886bc09494f64fb68bcdf927ae65fb90d152` |
| D51 实现提交 | `baec96179728ccc8ad73e16d937d31e390f0f820` |
| D51 控制器核心 | `1b50ed42ebc31fb845dc5a1498abd5dcac38899eb09682ee809850504ea4d447` |
| D51 Gate 0 证据编译器 | `35b289bfb1bc38afe568cd37ece3c1e0ebad3276b1bfcbce23aa3cbbe00a5e13` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| D40 年度服务合同 | `1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95` |
| D41 BESS R1 guide | `2d03ab0ae229583bbf46e3ebdd84ab0924627d7ac20e2af68dad42ff11de4614`；只锁定身份，不把数值加载为 seed |
| 原始 BESS 模型规模 | `597,318` 个活动变量、`527,053` 条活动约束、`79,057` 个二元 |

D52 逐字节复用 D50 的正式热数据、VRE、价格树、2024 年 `8,784 h` 时标、10% 绝对弃电上限 `339,569.90645758656 MWh`、年度 PCC 外送目标 `4,035,354.738554194 MWh`、容量边界、成本函数、BESS 寿命/吞吐和单全年循环。D51 Gate 0 核心文件保持不改；正式逻辑必须进入新的 D52 核心、执行器和测试文件，避免把 840 h 防火墙或非正式 schema 原地改写成正式权限。

D52 新源码、测试和 Gate A 哈希只能在本合同形成独立 Git 提交之后追加，不得反写本节。

## 4. 不变的全年模型与二元分区

BESS 二元分区继续固定为：

| 类别 | 数量 | 候选阶段域 |
|---|---:|---|
| 两台 CHP `fuel_code_bit` | `52,704` | 全过程 `[0,1]` 连续投影 |
| 两台 CHP `online` + BESS `charge_mode` | `26,352` | 按固定/整数前视/未来放松三类更新 |
| `bess.installed` | `1` | 阶段 0 为 Binary，首个检查点后固定 |
| 原始完整二元 | `79,057` | 最终精确提升后全部恢复 Binary |

所有连续容量始终在原始有限边界内自由，禁止使用 D46 工程容量锚点。8784 个真实小时、年度 PCC 等式、弃电上限、CHP 跨时转移与爬坡、BESS SOC 递推、吞吐和真实年首尾循环始终活动。禁止增加块级服务配额、局部循环、终端库存罚值、代表期权重、物理松弛或服务松弛。

## 5. 冻结的分块、目标与 incumbent 规则

1. 真实年份按原顺序分成 `53` 个提交块：前 `52` 块各 `168 h`，最后一块为真实年尾 `48 h`。
2. 每个常规阶段的当前块和下一真实块组成 `336 h` 整数前视；只提交当前块，尾段不环回年首。
3. 已提交物理位固定，当前与前视块恢复 Binary，未来块保持 `[0,1]`，全部燃料编码位保持投影。
4. 候选阶段只激活注册的常数零可行性目标。原经济目标身份先冻结并停用，不使用 Hamming、成本混合、扰动或罚项。
5. HiGHS 捕获第一个全部列有限、当前整数带完整为 0/1 且可加载的全年投影 incumbent 后立即软中断；warm start 固定为关闭，D41 guide 数值不加载到模型。
6. 每个 incumbent 在任何新 fixing、下一次 optimize 或回退动作前，必须先发布不可覆盖的原子检查点。
7. 最后一个阶段完成后先恢复原经济目标，再执行燃料精确提升和 clean 原成本 repair。

阶段 incumbent、零目标值、投影候选和检查点均不是原 MILP 上界。

## 6. 正式检查点与分支哈希链

每个成功的 `stage_index / attempt_index` 组合必须写出一组不可覆盖产物：完整有限变量 gzip、JSON manifest、父检查点 SHA-256 和可选 rollback-source SHA-256。manifest 至少包含：

- 完整变量名称/边界身份及压缩产物 SHA-256；
- 已提交物理位、当前块模式、全局拓扑位和连续容量快照；
- 固定/活动整数/未来放松/燃料投影四类域审计；
- 原目标、零目标和活动约束身份；
- 当前全部 no-good cut 的规范表达、顺序和哈希；
- solver 状态、首 incumbent 来源、完整变量映射、整数残差和资源摘要。

文件先写同目录临时文件，完成 flush、fsync、关闭和 SHA-256 后原子 rename；已有路径禁止覆盖。被拒绝的检查点、失败尝试和旧分支永久保留，不能把替代分支伪装成原线性历史。

## 7. 冻结的一步回退与 no-good cut

正式控制器参数固定为：

| 参数 | 冻结值 |
|---|---:|
| 回退深度 | `1` 个提交块 |
| 每阶段块模式尝试上限 | `3`（attempt `0/1/2`） |
| 全年总回退事件上限 | `8` |
| 基础阶段数 | `53` |
| 最多求解尝试数 | `53 + 2×8 = 69` |

当阶段 `k>0` 没有合格 incumbent 时，只允许回退到阶段 `k-1`：

1. 将阶段 `k-1` 最近已提交块模式登记为 rejected record；
2. 对该块全部逐时物理二元加入一个精确 binary no-good cut，排除且只排除这一完整块模式；cut 不包含容量、连续变量、全局 `installed`、前视块或更长前缀；
3. 从阶段 `k-2` 的已接受父检查点（`k=1` 时从空前缀）clean 重建完整 8784 h 模型，核验输入、变量、约束和目标身份，重放父前缀与所有已注册 cuts；禁止在已污染模型上静默继续；
4. 重新求解阶段 `k-1` 的下一 attempt，成功检查点化后再重试阶段 `k`；
5. 同一阶段的不同 rejected pattern 各形成独立 cut，cuts 按首次登记顺序持续有效且不得删除或重排。

阶段 `0` 无 incumbent 时直接关闭。替代阶段自身在相同 cuts 下无 incumbent 时不得无变化重试；因为没有新的模式可排除，直接关闭。单阶段三个模式耗尽、全年八次回退耗尽、父检查点缺失或 clean 重放不一致时均停止，不扩大 beam、不加深回溯、不改变块长、前视或目标。

八次预算允许至多八个 rejected pattern；每次回退最多增加“替代前一块 + 重试失败前沿”两个求解尝试，因此 69 次是机械上限，不是期望运行次数。该预算在任何正式结果产生前冻结，不得根据阶段进展上调。

## 8. 燃料精确提升、clean repair 与上界资格

完整 `26,353` 位物理快照形成后，只允许调用 D49/D50 已验证的确定性燃料提升：按每台 CHP、每小时的 `online` 与 `power_gross` 选择唯一相邻燃料段，内部 knot 取低编号段，端点容差 `1e-9 MW`，禁止改写非燃料变量。

提升后必须证明：

- 全部 `79,057` 位原始二元严格为 0/1；
- 活动约束最大绝对违反 `≤1e-7`；
- 年度 PCC 等式残差 `≤1e-8 MW`；
- 年度弃电、循环、容量、CHP 编码、BESS 模式和吞吐审计全部通过。

随后在独立 clean process 中重建未投影、未改目标的原始 BESS MILP，恢复全部燃料编码位为 Binary，固定完整 `79,057` 位二元快照，连续容量保持原边界内自由，以原经济目标求解固定二元 LP。

只有 HiGHS `num_primal_infeasibilities=0`、独立约束审计、年度服务、循环、边界、容量和目标分项全部通过，才可按既有 80 位向上舍入规则登记 `audited_feasible_upper_bound_cny`。中间容量、候选目标和提升前轨迹没有上界资格。

## 9. Gate A：正式优化前准入门

D52 实现提交后，必须先在 OpenBayes 同一 Linux/HiGHS 环境完成不调用 8784 h optimize 的 Gate A：

1. 新建独立 D52 核心、BESS-only 监控执行器和测试；D51 Gate 0 核心 SHA-256 保持不变；
2. clean BESS build-only 精确命中 `597,318 / 527,053 / 79,057` 模型规模、正式输入、服务和名称哈希；
3. 证明 53 块覆盖、四类域分区、零目标替换/原目标恢复和 69 次尝试上限；
4. 在缩短时域真实 Pyomo/HiGHS 案例覆盖正常前进、至少一次 clean 一步回退恢复、同阶段第二替代模式、总预算耗尽和各预注册关闭状态；
5. 对损坏 gzip、错误父哈希、错误 rollback-source、缺变量、分数物理位、重复路径、覆盖检查点、未注册/全局/容量 cut、非 clean 回放和结果后参数变化进行拒绝测试；
6. build-only 全年模型证明 rollback replay 会重新构造 clean 模型并复现输入/变量/约束/目标身份，不调用正式 solver optimize；
7. D51 定向、D40–D52 兼容、全包测试、Ruff 与 `py_compile` 在 Linux 零失败、零错误、零跳过；
8. Gate A manifest 绑定合同提交、实现提交、D50/D51 manifest、源码、测试与输入哈希，并明确 `formal_8784h_optimization_invoked=false`；
9. 正式入口必须拒绝缺失/失败 Gate A、非 BESS、路径已存在、哈希漂移、参数漂移和同机已有正式大算例。

Gate A 通过并形成独立提交后，才可把 `formal_run_permitted` 置为 true。Gate A 的 24 h 结果和全年 build-only 结构都不是正式容量或上界。

## 10. 唯一正式 BESS 执行与资源合同

Gate A 通过后只允许一次新目录、同提交、同哈希的 BESS 正式流水线：

| 项目 | 冻结值 |
|---|---:|
| 求解器 | HiGHS only |
| 随机种子 | `0` |
| 每次求解线程 | `12` |
| primal / dual / MIP feasibility tolerance | `1e-7` |
| MIP relative gap | `0`；只捕获首个 incumbent |
| 单次 stage/attempt solver 软时限 | `360 s` |
| 单次 stage/attempt 父级硬墙钟 | `390 s` |
| 初始或回退 clean rebuild/replay 父级硬墙钟 | `390 s` |
| 候选控制器总父级硬墙钟 | `30,600 s` |
| clean 原成本 repair 父级硬墙钟 | `1,500 s` |
| 单架构总父级硬墙钟 | `32,400 s` |
| heartbeat 间隔 | `30 s` |
| 进程树 RSS warning / 聚合 RSS stop | `35 / 45 GiB` |
| 主机可用内存 stop | `30 GiB` |

`30,600 s` 候选墙钟覆盖最多 `69×390 s` 求解尝试、初始 clean build 和最多 8 次 rollback clean replay 的有界预算；未使用预算不能转给 repair。候选阶段正常向前时可复用同一个 clean 模型；发生任何 rollback 时必须按第 7 节重新构建，不得以性能理由降级为 in-place 回退。

正式作业不得与其他大算例并发。父进程必须记录 launcher/child、当前 stage/attempt、回退源、最新检查点、CPU、进程树/聚合 RSS、可用内存、solver 状态和最新 heartbeat；停止后活动残留必须为 0。SSH 断开不构成重启权限；进程或主机失败后不得自动以同一正式身份续跑。

## 11. 规范目录与产物

正式目录冻结为：

- 远端：`/root/e0-b-20260711-019f4f64/results/e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery/`；
- 本地：`风光火+熔盐储热/数据采集/e0d52_full_year_checkpointed_bounded_backtracking_primal_recovery/`。

Gate A 使用带实现短提交号的新目录，不得与正式目录混用。正式目录一旦存在即禁止覆盖或重启。

规范产物至少包括：Gate A manifest/execution、每个 attempt 的完整原子检查点、分支/父/rollback-source/cut 哈希图、逐 attempt 域与 solver 审计、progress、heartbeat、资源记录、完整物理快照、燃料提升审计、完整二元快照、repair result、BESS manifest、formal manifest、launcher、solver 日志和 `SHA256SUMS.txt`。正式 manifest 必须列出全部 rejected、accepted 和 failure 产物，不得只保留成功分支。

## 12. 预注册终态与主张权限

只允许以下终态：

- `audited_feasible_upper_bound_recovered`：53 个最终接受阶段、燃料提升和 clean repair 全部通过；只恢复 BESS 受控公开成本口径的工程数值上界；
- `closed_no_checkpointed_path`：阶段 0 无 incumbent、替代阶段无 incumbent、单阶段三模式耗尽或八次总回退预算耗尽；只关闭该有界搜索树，不证明原 BESS MILP 不可行；
- `checkpoint_integrity_failure`：检查点、父链、cut、变量/模型身份或 clean replay 不一致；无上界，不能改用内存状态继续；
- `final_exact_lift_failed`：完整物理轨迹存在，但燃料提升或提升后审计失败；无上界；
- `fixed_binary_repair_failed`：提升通过，但 clean 原成本 LP 或独立审计失败；无上界；
- `no_primal_status_closure`：候选总墙钟、单次硬墙钟、进程、资源、主机或无法形成完整状态；不能写成物理不可行。

只有成功终态可与 D41 BESS 严格下界 `1,144,950,604.8368804 CNY` 在同一受控成本口径下形成数值 gap。首条可行轨迹不称为最优容量，也不自动开放 TES/Hybrid、项目 TAC、技术排序或 E2–E4。所有失败终态都关闭 D52；不得延长预算、增加 attempt、改目标或原样重跑。

## 13. Agentic 边界

Agentic 只可读取检查点与 heartbeat、校验哈希/域/资源/预算、按冻结状态机执行继续/clean 一步回退/停止、生成审计记录和判断主张资格。它不得：

- 选择或修改二元模式、容量和 no-good cut 内容；
- 改变块长、前视、回退深度、attempt 或墙钟；
- 生成替代 seed、动态调参或绕过 clean replay；
- 把部分轨迹、零目标 incumbent 或缩短时域结果升级为正式结论。

在 SCI 中 D52 仍是确定性预注册优化控制器，不作为 Agentic 创新点；Agentic 工作流只在硕士论文第 5 章讨论。

## 14. 禁止项

- 禁止原样重跑 D50，或声称从 D50 阶段 `2` 精确续算；
- 禁止修改 D51 Gate 0 产物或把其 24 h repair 当作正式 seed/上界；
- 禁止两块以上回溯、beam search、随机多起点、Hamming/成本混合目标和结果后扩大搜索；
- 禁止固定连续容量、增加局部循环/终端罚值、分摊年度服务或放松物理约束；
- 禁止保留损坏检查点后在内存中继续，或覆盖旧 attempt 产物；
- 禁止在合同提交、实现提交和同哈希 Gate A 完成前启动 8784 h optimize；
- 禁止在正式结果产生后反向修改第 1–14 节。

## 15. 登记规则

第 1–14 节必须先形成独立 Git 提交。之后才能新增 D52 源码、测试或 Gate A 数值产物；实现身份与测试结果按时间顺序追加。Gate A 通过后再形成独立提交，才允许创建唯一正式目录。正式终态只能追加在本节之后，不得反向改写方法、参数、预算、目录、终态或权限。
