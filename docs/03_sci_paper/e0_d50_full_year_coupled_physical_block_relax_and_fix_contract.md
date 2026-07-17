# E0-D-50 全年耦合物理分块 Relax-and-Fix—原成本上界恢复合同

状态：**结果前方法合同、实现与 Gate A 已闭合；仅允许一次正式 BESS 流水线，尚无任何 D50 正式数值结果。**

冻结日期：2026-07-16。

## 1. 研究问题与唯一准入范围

D49 把 BESS 原模型的 `52,704` 个 CHP 燃料编码位投影为连续域后，仍需一次性搜索 `26,353` 个物理二元；唯一正式候选阶段在 `3720.637 s` 内没有 incumbent。D50 只回答一个更窄的方法问题：

> 在完整 8784 h 年度模型、年度 PCC 外送目标、弃电上限和单全年循环始终保留的前提下，只让连续 336 h 前视带内的物理二元保持整数、每次固定其中前 168 h，能否逐步形成一个完整物理二元轨迹，并经 D49 的燃料编码精确提升和 clean 原成本模型修复恢复 BESS 可行上界？

D50 首次正式范围仍只允许 BESS。它不是滚动调度、代表周或局部窗口模型；每一步都在同一个完整 8784 h 年度可行域上求解。TES/Hybrid、E2–E4、699 点扫描、项目 TAC 和技术排序均不在本合同权限内。

## 2. 与 D41、D46、D48 和 D49 的区别

1. D41 第 7 节曾预注册 `336 h` 规划窗口和 `168 h` 提交步长，但因当时 Gate B 最弱案例失败，Gate C/D 从未实现或执行。D50 不复活 D41：三架构严格下界现已由 D44/D47 闭合，D50 只处理 BESS primal；并且不构造独立短时域子问题，而是在完整全年模型中逐步改变物理二元域。
2. D46 固定最大容量锚点并尝试一次性原 MILP seed；D50 不固定连续容量，不复用 D46 最大容量锚点，也不新增确定性取整 seed。
3. D48/D49 对全部未固定物理二元做一次性 Hamming 搜索；D50 不使用 Hamming 目标，不同时开放全年 `26,353` 个物理二元。
4. D38–D39 已证明代表期不能提供正式容量规划证据；D50 不读取代表周、典型日或聚类权重。
5. D50 的任何中间阶段、部分轨迹或投影模型 objective 都是 `candidate_only`；只有第 7 节 clean 原成本修复通过后才形成上界。

## 3. 方法依据与采用边界

D50 复用 D41 已完成的高质量文献审计，不新增低等级来源：

| 文献 | 期刊 | 对 D50 的方法依据 | 本文不直接继承的主张 |
|---|---|---|---|
| Baumgärtner et al., *DeLoop*, DOI `10.1016/j.energy.2020.117272` | Energy 198 (2020) | 长时域耦合系统可用分解生成候选，但最终上界必须回到原问题复核 | 不把固定设计运行问题的界直接外推到内生容量规划 |
| Wakui et al., DOI `10.1016/j.energy.2021.122066` | Energy 239 (2022) | shrinking/receding horizon 可逐步确定长期运行离散轨迹，并需显式处理储能跨期状态 | 不采用局部终端状态替代本项目真实年循环 |
| Zhang and Wakui, DOI `10.1016/j.energy.2025.137358` | Energy 335 (2025) | 短时域整数轨迹 finalization 与全局协调可分开设计 | D50 不宣称复现其完整列生成或近最优性证明 |
| Moradi-Sepahvand and Amraee, DOI `10.1016/j.apenergy.2021.117137` | Applied Energy 298 (2021) | 容量规划分解必须保留共享投资变量和 chronological operation 的严格协调 | 不照搬其电网扩展 Benders 结构 |

上述文献只支持方法方向。D50 的上界资格完全来自“最终完整二元快照在未修改原始全年模型中可行”这一模型包含关系与独立审计，不来自文献权威。

## 4. 冻结输入、代码身份与上游证据

| 对象 | 锁定值 |
|---|---|
| D40 Gate A manifest | `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577` |
| D40 年度服务合同 | `1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95` |
| D41 Gate A manifest | `50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937` |
| D41 BESS R1 guide | `2d03ab0ae229583bbf46e3ebdd84ab0924627d7ac20e2af68dad42ff11de4614`；只作输入身份与可选连续初值，不构成 seed 或上界 |
| D46 formal / postmortem | `8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9` / `c74a6943570690ace8573a0dee2f65aa763d0371854e01625337a46244a35b58` |
| D48-R1 formal manifest | `ca0248805ce72d1b25dd69a0cf20c5c68dee8b60a5d0a2d575a192f3e8455165` |
| D49 Gate A / formal manifest | `11b283d6825cd5fcc5b41a09b8400bdb6116bb11e830b1dd1bc42b9417e789dd` / `0d66f06defcc8ecabe247bc7eb38c3f9e7f457d41dac82927295f54b0ad62a14` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| D49 核心 | `9d2dd610a2d7e59e9b8d9631e676277b0d36077c7a40d3448889defc041b3b14` |
| 原始 BESS 模型规模 | `597,318` 个活动变量、`527,053` 条活动约束、`79,057` 个二元 |

D50 继续逐字节复用 D40 的 2024 年 8784 h 输入、10% 绝对弃电上限 `339,569.90645758656 MWh`、年度 PCC 外送目标 `4,035,354.738554194 MWh`、容量边界、成本函数、BESS 寿命约束和单全年循环。D50 源码与测试的 SHA-256 只能在结果前合同提交后的 Gate A 记录中追加，不得反写本节。

## 5. 二元分区与全年耦合模型

BESS 原始二元清单保持 D49 分区：

| 类别 | 组件 | 数量 |
|---|---|---:|
| 投影燃料编码位 | 两台 CHP 的 `fuel_code_bit` | `52,704` |
| 逐时物理位 | 两台 CHP 的 `online` + BESS `charge_mode` | `26,352` |
| 拓扑物理位 | `bess.installed` | `1` |
| 合计 | 原始完整二元 | `79,057` |

候选模型从 clean 原始 BESS MILP 构建，并满足：

- 所有连续容量保持原始有限边界内自由，禁止固定 D46 容量锚点；
- `bess.installed` 在第一个阶段保持 Binary，首阶段通过后与首提交块一起固定；
- 全部 `fuel_code_bit` 在候选全过程保持 `[0,1]` 连续域；变量、约束和索引不删除；
- 唯一经济目标保持原始成本表达式。由于燃料编码被投影，各阶段 objective 只作搜索排序，不是原 MILP 上界或下界；
- 8784 个真实小时、年度 PCC 等式、弃电上限、BESS 年吞吐约束、CHP 跨时转移/爬坡、BESS SOC 递推和真实年首尾循环在每个阶段都保持活动；
- 不新增局部服务配额、块首尾循环、终端库存目标、罚松弛或代表期权重。

## 6. 冻结的 `336 h` 前视—`168 h` 提交规则

真实年份按原顺序分为 `53` 个提交块：前 `52` 块各 `168 h`，最后一块为真实年尾 `48 h`。块序、时标和尾段不得重排或环回生成额外小时。

对第 `k` 个阶段：

1. 已提交块中的 `online` 和 `charge_mode` 按前一合格 incumbent 固定；首阶段通过后 `bess.installed` 也固定。
2. 当前提交块与其后一个真实块构成整数前视带，逐时物理位恢复 Binary；因此常规阶段最多开放 `336×3=1,008` 个逐时物理二元，首阶段另含一个 `installed` 二元。
3. 前视带之后尚未处理的逐时物理位保持 `[0,1]`；全部燃料编码位继续投影。
4. 采用同一完整全年模型和原成本搜索目标，HiGHS 捕获第一个全部列有限、当前整数带完整为 0/1 且全年约束具有可加载 primal 的 incumbent 后立即软中断。
5. 只固定当前提交块，不固定前视块；下一阶段将前视块变为当前块，并加入再下一个块作为新前视。
6. 前一阶段的连续变量值，以及其中仍为合法 0/1 的物理位，可在接口支持时作为下一阶段的部分初值；新进入整数带而仍为分数的物理位必须留空，不得人工取整。若接口不支持部分初值，则该阶段不使用 warm start；不得生成替代 seed。求解器是否接受初值必须写入阶段 manifest，但不是成功资格。
7. 每阶段必须记录固定、活动整数、未来放松和燃料投影四类变量的计数及名称 SHA-256，并证明并集等于原始 `79,057` 位清单。

阶段成功只说明“当前固定轨迹仍存在一个全年投影可行延拓”。任何阶段无 incumbent、被证明在当前已固定路径下不可行、触发墙钟或审计失败，都立即终止 D50；不回退已提交块、不扩大前视、不改变块长、不增加手工修复。

最后 `48 h` 阶段完成后，全部 `26,353` 个物理二元必须形成完整 0/1 快照。此时仍因燃料编码投影而不是原 MILP 可行上界。

## 7. 燃料精确提升、clean repair 与上界资格

最终物理轨迹只允许调用 D49 第 5 节已经 Gate A 验证的确定性提升：按每台 CHP、每个小时的 `online` 与 `power_gross` 选择唯一相邻燃料段，内部 knot 取低编号段，恢复 one-hot segment、fraction、`fuel_code_bit` 和 `fuel_tce_per_hour`。提升规则、`1e-9 MW` 端点容差和禁止改写非燃料变量的要求完全不变。

提升后必须先在候选模型上证明：

- 全部 `79,057` 位原始二元严格为 0/1；
- 活动约束最大绝对违反不超过 `1e-7`；
- 年度 PCC 等式残差不超过 `1e-8 MW`；
- 年度弃电、循环、容量、CHP 编码、BESS 模式与吞吐审计全部通过。

随后在 clean process 中重新构建未投影、未改目标的原始 BESS MILP，恢复全部燃料编码位为 Binary，固定完整 `79,057` 位二元快照，保持连续容量在原始边界内自由，以原始经济目标求解固定二元 LP，父级硬墙钟为 `1500 s`。

只有 HiGHS `num_primal_infeasibilities=0`、独立全约束最大绝对违反 `≤1e-7`、年度 PCC 残差 `≤1e-8 MW`、全部循环/边界/容量/服务/目标分项审计通过，才可按 D46–D49 同一 80 位向上舍入规则登记 `audited_feasible_upper_bound_cny`。中间阶段 objective、最终投影 candidate objective 和提升前容量均不得登记为上界。

## 8. Gate A：正式 8784 h 优化前的准入门

Gate A 必须在不调用 8784 h optimize 的情况下完成：

1. clean BESS build-only 精确命中 D40/D49 模型规模、输入、服务、原容量边界和二元名称哈希；
2. 53 个提交块恰好覆盖 `8784=52×168+48`，无遗漏、重复、排序变化或年首环回前视；
3. 对首段、中间段、倒数第二段和 48 h 尾段执行域审计，验证固定/整数前视/未来放松/燃料投影的计数和并集；
4. 证明各阶段活动约束集合、年度 PCC、弃电帽、吞吐约束和单全年循环与原模型一致，唯一变化只有变量域与已提交物理位 fixing；
5. 至少一个缩短时域的三块集成模型完整执行“前两块整数前视→提交首块→移动前视→尾块→精确提升→clean repair”；
6. 对故意缺块、重复块、回退 fixing、局部循环、服务删失、额外 seed、分数快照、错误燃料提升和 repair 漏固定进行拒绝测试；
7. D49、D40–D50 定向回归、全包测试、Ruff 与 `py_compile` 在 OpenBayes Linux ASCII 路径零失败、零错误、零跳过；
8. Gate A manifest 明确 `formal_optimization_invoked=false`，并完成本地—远端源码、测试和产物哈希闭合。

Gate A 可以使用缩短时域小模型求解验证流程，但不得用其结果选择块长、时限、目标、seed 或终态解释。

## 9. 唯一正式 BESS 执行与资源合同

Gate A 通过并形成独立提交后，才允许一次正式 BESS 流水线：

- 求解器仅 HiGHS；随机种子 `0`；每阶段 `12` 线程；primal/dual/MIP feasibility tolerance 均为 `1e-7`；
- 每个 relax-and-fix 阶段求解器软时限 `360 s`、父级硬墙钟 `390 s`；找到首个合格 incumbent 时立即停止该阶段；
- 53 阶段候选总父级硬墙钟 `21,600 s`，不能把未使用的阶段预算转给 repair；
- clean 原成本 repair 父级硬墙钟 `1,500 s`；单架构总父级硬墙钟 `23,400 s`；
- 候选模型在一个 clean child 中构造一次；若求解接口不能安全保持阶段域/固定更新与完整审计，Gate A 失败，不允许正式阶段改成 53 次不受控重建；
- 每 `30 s` 写 heartbeat，记录阶段号、提交范围、整数前视范围、PID/child、CPU、进程树 RSS、聚合 RSS、主机可用内存、incumbent 捕获和最新产物；
- RSS warning/stop 为 `35/45 GiB`，主机可用内存 stop 为 `30 GiB`；不与其他正式大算例并发；终止后活动残留必须为 0。

规范目录冻结为：

- 远端：`/root/e0-b-20260711-019f4f64/results/e0d50_full_year_coupled_physical_block_relax_and_fix/`；
- 本地：`风光火+熔盐储热/数据采集/e0d50_full_year_coupled_physical_block_relax_and_fix/`。

规范产物至少包含 Gate A manifest、53 阶段域/进程/首 incumbent 审计、完整物理快照、精确提升审计、完整二元快照、repair result、formal manifest、execution/heartbeat、日志与 SHA256SUMS。

## 10. 预注册终态与权限

只允许以下科学终态：

- `audited_feasible_upper_bound_recovered`：53 阶段、精确提升和 clean repair 全部通过；只恢复 BESS 一个受控公开成本口径的工程数值上界；
- `block_path_no_incumbent`：某阶段没有合格 incumbent 或在当前已固定路径下数值不可行；只否定该冻结 relax-and-fix 路径，不证明原 BESS MILP 不可行；
- `final_exact_lift_failed`：完整物理轨迹存在，但燃料提升或提升后审计失败；无上界；
- `fixed_binary_repair_failed`：提升通过，但 clean 原成本 LP 或独立审计失败；无上界；
- `no_primal_status_closure`：墙钟、进程、资源或无法形成完整状态；不能写成物理不可行。

成功时可将 D50 上界与 D41 BESS 严格下界放在同一受控成本口径下报告 BESS gap，但首个可行轨迹不称为最优容量。成功不自动开放 TES/Hybrid、项目 TAC、技术排序或 E2–E4；后续权限必须另立结果前合同。失败时 D50 关闭且不得通过延长阶段、回退块或改 seed 原样重跑，只能另立 D51。

## 11. 禁止项与 Agentic 边界

- 不改变数据、年份、服务、成本、容量边界、循环、求解容差或原物理约束；
- 不建立独立 336 h 局部模型，不分摊年度 PCC/弃电服务，不设置块级循环或终端罚值；
- 不固定连续容量，不使用 D46 最大容量锚点，不人工取整新进入整数带的变量；
- 不使用 Hamming 目标、额外权重、第二 seed、回溯、可变块长、扩大前视或结果后调参；
- 不把部分固定轨迹、阶段 incumbent、投影 objective、R1 guide、Gate A 小模型或 solver 文本状态写成原 MILP 可行解；
- 不在 Gate A 与同哈希提交完成前启动正式 8784 h 流水线；
- Agentic 只可校验哈希、阶段域、时间表、资源门、产物完整性与主张资格，不决定物理位、容量或技术结论。

## 12. 结果登记规则

第 1–11 节形成独立提交后，才能新增 D50 源码、测试或数值产物。实现、Gate A 和唯一正式终态只能顺序追加在本节之后，不得反向改写块长、预算、solver 选项、判据或权限。

## 13. 实现登记（2026-07-16）

D50 已在独立提交 `04e17643ea06efe67b60804202e18fca7e2ce2f5` 完成实现：

- 核心 `e0d50_full_year_coupled_physical_block_relax_and_fix.py` SHA-256 为 `3fa1a3e4e2934a8b8ce763841e13a2d37c3945fa9803aed7c1aebd6b70bb2934`；
- 父级执行器 `e0d50_monitored_executor.py` SHA-256 为 `9b16c431be0fa57cb2b871410348241753c8f4e6fd2b83ae1de4910fb275c0a1`；
- 核心/执行器测试 SHA-256 分别为 `c1cc425a87ac2f0082889c90fe6767b3cb6260179fe5df172702cdb35f6309b6` / `b2410f05946d7cbd61c11c9a9dcd72cfbb101758ef1e505f56e5f68e0e2dfe68`。

实现保持一个 clean candidate child 和一份全年模型：模型只构造一次，53 阶段在同一 Pyomo 对象上依次更新固定/整数/连续域；父进程读取子进程阶段进度，分别强制每阶段 `390 s` 与候选总 `21,600 s` 硬墙钟。各阶段关闭 warm start；D41 BESS R1 guide 只读取三类标签和完整变量身份，`values_applied_to_model=false`、`binary_seed_applied=false`。本地缩短 24 h 三块链已完整通过候选、物理快照、燃料精确提升和 clean repair。Windows 定向为 `15 passed`，D40–D50 兼容为 `239 passed + 5 Linux-only skipped`，全包为 `683 passed + 5 skipped`，零失败。

## 14. OpenBayes Gate A 登记（2026-07-16）

Gate A 已在提交 `04e17643...` 的同哈希源码上通过，未调用正式全年优化：

- build-only 证据：`gate_a_build_bess.json` SHA-256 `196c5fd15b5ce0c530a70905839622b3aa2ca02aef21f95d3c08cc632f790be1`，运行 `282.213 s`，`solver_invoked=false`、`formal_optimization_invoked=false`；
- 精确证明 `53` 块覆盖 `8784=52×168+48`，并对阶段 `0/26/51/52` 完成域、约束身份和原经济目标身份审计；D41 guide 命中 `2d03ab0a...` 且未写入模型；
- OpenBayes Linux 定向/兼容/全包分别为 `15/244/688 passed`，失败、错误、跳过均为 `0`；Ruff 与 `py_compile` 哨兵通过；
- Gate A manifest / execution SHA-256 分别为 `d74891b9c9d8499918f0bdddfd25cf4badf0af09ad76504898fc97aaa199eef7` / `35827275786f11aaaf6038f1d9cbbdff2141e3f144458df39d761b05e055cca0`；
- `SHA256SUMS.txt` 排除自身后覆盖 12 个规范文件，SHA-256 `6b1c3e06babe4823e6d662cfa6abd945749220f1514b3951784cfff4c62cc09d`，远端—本地逐文件 `0` 不一致；
- 远端证据为 `results/e0d50_gate_a_work_04e1764/` 与 `results/e0d50_gate_a_04e1764/`，本地镜像位于 `风光火+熔盐储热/数据采集/` 同名目录。

Gate A 只把唯一 BESS 正式流水线置为 `formal_run_permitted=true`，没有产生候选、容量、上界或 gap；TES/Hybrid 仍未获准。唯一正式目录、53 阶段顺序、预算与终态解释继续按第 9–10 节执行。

## 15. 唯一正式 BESS 启动与阶段 01 检查点（2026-07-17）

唯一正式流水线已于 `2026-07-17T05:47:39Z` 在冻结提交、输入、guide、顺序和预算下启动。`2026-07-17T05:59:38Z` 检查点显示父/候选进程均存活，阶段 `0/1` 已提交，阶段 `2` 正在运行；两个已提交阶段均捕获完整 `597,318` 变量 incumbent，域分区、固定值、整数残差和约束/目标身份审计通过，累计固定物理二元 `1,009` 个。阶段文件 SHA-256 为 `26f17de7...` / `cdc16ad1...`，聚合 RSS `2.856 GiB`、可用内存 `94.492 GiB`，未触发资源门。

本检查点只证明分块执行链正常推进。阶段 incumbent、已固定部分轨迹和 `Interrupted by user` 的阶段求解器状态均 `formal_upper_bound_eligible=false`；在 53 阶段、精确燃料提升与 clean 原成本 repair 全部闭合前，仍无正式候选、容量、上界、gap、TAC 或技术排序资格。
