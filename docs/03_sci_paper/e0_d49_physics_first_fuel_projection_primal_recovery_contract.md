# E0-D-49 物理优先燃料投影—原成本可行上界恢复合同

状态：**结果前合同、实现、OpenBayes Gate A 与唯一 BESS 正式方法门均已闭合；终态为 `no_primal_status_closure`，D49 不得原样重跑。**

冻结日期：2026-07-16。

## 1. 研究问题与唯一准入范围

D46 与 D48-R1 都没有为 BESS、TES 或 Hybrid 恢复原 MILP incumbent。D49 只回答一个更窄的问题：在不固定容量、不改变物理约束和服务约束的前提下，先从候选搜索中投影掉只负责 CHP 燃料分段编码的二元位，能否为 **BESS** 找到一个可被确定性精确提升、并在原始成本模型中通过固定二元 LP 修复的全年可行点。

D49 的首次正式方法门只允许运行 BESS。BESS 成功也不自动授权 TES/Hybrid 正式运行；后两者必须沿用同一已提交实现，另立结果前执行补充合同。BESS 失败则转入 D50 的 336 h/168 h 物理分块 relax-and-fix 设计，不延长本合同墙钟，不更换 seed，也不在 D49 内增加第二套算法。

## 2. 冻结输入、代码与既有证据

以下对象是 D49 的只读上游：

| 对象 | SHA-256 / 锁定值 |
|---|---|
| D40 Gate A manifest | `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577` |
| D41 Gate A manifest | `50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937` |
| D46 Gate A manifest | `098fc8bef7fe160cdad98d5d22675d82dcd9341e03e656792b357e7f29f1d176` |
| D46 formal manifest | `8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9` |
| D46 postmortem bundle | `c74a6943570690ace8573a0dee2f65aa763d0371854e01625337a46244a35b58` |
| D46 BESS guide CSV.GZ | `b69f4035deb5aa5f83a504e1e40347a23fa352b4104087bc017da6940c828b1f` |
| D48 Gate A manifest | `1d894652bfb91f9995f428c8f36fc7ad555675496e42c1dbec4c6673c14c8bfe` |
| D48-R1 formal manifest | `ca0248805ce72d1b25dd69a0cf20c5c68dee8b60a5d0a2d575a192f3e8455165` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| `e0d41_strict_full_year_decomposition.py` | `c7f45f8c071bb92c6cf7576a76bed71b71e606b7239881cb8baac09b195d2f1e` |
| 原始 BESS 活动规模 | `597,318` 个变量、`527,053` 条约束、`79,057` 个二元变量 |

本合同不锁定尚未产生的 D49 源码 SHA。源码、测试、Gate A 产物和提交号必须在正式 BESS 求解前另行写入 Gate A manifest；正式运行只能使用该同哈希提交。

## 3. 二元变量的结果前分区

BESS 的 D41 完整二元清单固定分成：

| 分区 | 组件 | 数量 |
|---|---|---:|
| 投影燃料编码位 | `chp[0].fuel_code_bit`、`chp[1].fuel_code_bit` | `52,704` |
| 保留物理二元位 | 完整清单减去上述燃料编码位 | `26,353` |
| 合计 | D41 完整清单 | `79,057` |

保留分区包含两台 CHP 的 `online`、BESS `installed` 与 `charge_mode`；不得投影启停状态、储能模式、安装状态、TES 模式或任何未来新增物理二元位。Gate A 必须按变量全名重新计算两个分区的计数和名称 SHA-256，并证明二者不交、并集等于 D41 完整清单。任何计数漂移都停止正式运行。

TES/Hybrid 只用于 Gate A 的通用性构建与小样本测试。其燃料编码位同为 `52,704`；对应保留物理二元数必须为 `35,136` 和 `43,921`，但本合同不授权其正式求解。

## 4. 候选模型：只改候选搜索域和目标

1. 从锁定的原始 8784 h BESS MILP 构建候选模型，连续容量变量保持原始上下界并保持自由；不得施加 D46 工程容量锚点。
2. 读取锁定的 D46 BESS guide，并沿用其中完整变量 warm start 与完整二元 seed。不得重新取整、改变阈值或生成第二个 seed。
3. 只把第 3 节列出的 `fuel_code_bit` 的域从 `Binary` 改为 `[0,1]` 连续域；变量、索引及全部原始约束均保留。其余原始二元变量继续为 Binary。
4. 停用唯一原始经济目标，建立对 `26,353` 个保留物理二元位的等权 Hamming 距离目标。燃料编码位不进入 Hamming 目标；不得增加权重、惩罚项、容量偏好或二级目标。
5. 候选搜索使用 HiGHS、12 线程、随机种子 0、D48 已冻结的 feasibility heuristic 选项、`3600 s` 求解器软时限和 `3720 s` 父级硬墙钟；捕获第一个完整 incumbent 后立即停止。
6. 候选模型的连续燃料段混合不是原 MILP 可行点，也不是成本上界。只有第 5–7 节全部通过后才能形成工程数值上界。

## 5. 燃料段的确定性精确提升

对每台 CHP、每个真实小时，使用 `CHPCommitmentSpec.fuel_flow_knots()` 返回的锁定相邻结点执行以下唯一映射：

1. 若 `online=0`，要求 `power_gross` 在独立容差内为 0，并将全部 `fuel_segment_active`、`fuel_segment_fraction`、`fuel_code_bit` 和 `fuel_tce_per_hour` 精确置零；否则提升失败。
2. 若 `online=1`，`power_gross` 必须位于首末燃料结点闭区间内。选择第一个满足 `power_gross <= upper_knot + 1e-9 MW` 的相邻段；因此内部结点固定选择较低编号段，最大结点选择最后一段。
3. 只允许在 `1e-9 MW` 范围内将功率钳到端点；超出范围直接失败。所选段的 fraction 由相邻结点线性反解，只有 `[-1e-9,1+1e-9]` 内的数值可钳到 `[0,1]`。
4. `fuel_segment_active` 置为严格 one-hot，未选段 fraction 为 0；`fuel_code_bit` 写入所选段编号的二进制码；`fuel_tce_per_hour` 按同一相邻段精确插值。
5. 提升不得改写 `power_gross` 以外的任何候选物理/容量变量；功率只允许上述端点数值钳制。提升前后非燃料变量向量必须以名称和值审计。

Gate A 必须证明：燃料编码位只直接参与 `fuel_code` 定义；燃料段活动量、fraction 与燃料流量可对任意满足 online 与功率范围的候选点按上述规则恢复；`fuel_tce_per_hour` 不出现在改变物理可行域的燃料上限、排放上限或非目标耦合约束中。只要依赖审计发现例外，D49 自动停止，不能靠扩大允许清单继续。

## 6. 提升后候选审计

提升后必须在候选模型上同时满足：

- 全部 `79,057` 个原始二元变量均为严格 0/1，并形成完整名称—值快照；
- 所有活动约束的独立最大绝对违反不超过 `1e-7`；
- 年度 PCC 服务等式残差不超过 `1e-8 MW`；
- 全部变量上下界、循环状态、容量—运行耦合、CHP 编码与分段插值审计通过；
- 候选回调值、提升前物理向量、提升后完整向量和完整二元快照均落盘并计算 SHA-256；
- 不得以 Pyomo/HiGHS 的 termination 字符串代替上述数值审计。

任一项失败时状态为 `candidate_found_but_exact_lift_failed`，不得进入原成本修复，也不得登记上界。

## 7. 原始成本模型修复与上界资格

若第 6 节通过，必须在 clean process 中重新构建未投影、未改目标的原始 BESS MILP，恢复全部燃料编码位为 Binary，固定提升后的完整 `79,057` 位二元快照，保持所有连续容量在原始边界内自由，以原始经济目标求解连续 LP。修复硬墙钟固定为 `1500 s`。

只有同时满足以下条件，才可登记 `audited_feasible_upper_bound_cny`：

- HiGHS 报告 `num_primal_infeasibilities=0`；
- 独立全部约束最大绝对违反不超过 `1e-7`；
- 年度 PCC 服务等式残差不超过 `1e-8 MW`；
- 固定二元、边界、循环、容量、服务和目标分项审计全部通过；
- 报告值按 D46/D48 同一 80 位向上舍入规则形成。

首 incumbent 只用于恢复一个可行上界，不代表全局最优。BESS 的严格下界仍来自 D41；只有上下界均具备后才可报告同一架构的受控 gap。该 gap 仍是公开成本敏感性口径，不是项目正式 TAC。

## 8. Gate A：正式求解前必须全部通过

Gate A 不得调用 8784 h 正式 optimize，且 manifest 必须写明 `formal_optimization_invoked=false`。最低验收项为：

1. BESS/TES/Hybrid 8784 h build-only 命中 D40/D41 锁定规模、原容量边界与约束身份；
2. 三架构二元分区计数、名称哈希、覆盖与不交审计通过；
3. 燃料编码依赖审计通过，未发现燃料/排放上限等物理耦合；
4. 对每台机组的每个燃料段、所有结点、内部结点 tie-break、最大结点、online/offline 和非法越界输入执行单元测试；
5. 至少一个实际 24 h BESS、TES 和 Hybrid 小模型依次完成候选求解、精确提升、完整二元固定和原成本修复；
6. 候选前后约束身份不变，除 `fuel_code_bit` 域和唯一目标外没有模型漂移；
7. D40–D49 定向回归、全包测试、Ruff 与 `py_compile` 全部通过；
8. 本地与 OpenBayes 的源码、测试和 Gate A 产物逐文件同哈希。

## 9. 正式 BESS 执行、资源门与产物

正式目录冻结为：

- 远端：`/root/e0-b-20260711-019f4f64/results/e0d49_physics_first_fuel_projection_primal_recovery/`
- 本地：`风光火+熔盐储热/数据采集/e0d49_physics_first_fuel_projection_primal_recovery/`

启动前远端目录必须不存在。候选与修复由受监控 clean child 顺序执行；每 60 s 写 heartbeat，并记录 launcher/child PID、CPU、RSS、系统可用内存、阶段文件和退出码。资源门固定为：RSS warning `35 GiB`、stop `45 GiB`、系统可用内存 stop `30 GiB`。架构总硬墙钟为 `5400 s`，不得因为前一阶段提前结束而转移墙钟预算。

规范产物至少包括候选原始回调、提升审计、完整二元快照、repair result、架构 manifest、formal manifest、execution sidecar、heartbeat 和 SHA256SUMS。停止后必须确认残留进程为 0，并将远端证据全部下载、逐文件核对哈希后再写论文状态。

## 10. 预注册终态与后续权限

只允许以下科学终态：

- `audited_feasible_upper_bound_recovered`：精确提升和原成本修复全部通过；只恢复 BESS 一个工程数值可行上界；
- `candidate_found_but_exact_lift_failed`：候选存在，但不能精确提升；无上界；
- `candidate_found_but_repair_failed`：提升通过，但原成本修复或独立审计失败；无上界；
- `engineering_mip_infeasible_under_projection`：只有 solver 返回相应工程数值状态且执行/资源审计完整时可记；仍不是有理数不可行证明，也不得外推 TES/Hybrid；
- `no_primal_status_closure`：墙钟、受控终止、进程/资源失败或无完整 incumbent；不能写成 BESS 物理不可行。

成功只开放另立 TES/Hybrid 同方法执行补充合同，不自动开放 E2–E4、699 点扫描、项目 TAC 或技术排序。失败只开放 D50 结果前方法设计，不授权 D49 原样重跑。

## 11. 禁止项与主张边界

- 不改变原始数据、年份、服务目标、循环边界、容量上下界、成本函数或求解容差；
- 不固定容量，不使用 D46 工程容量锚点；
- 不放松燃料编码位以外的二元变量，不删除燃料变量/约束；
- 不增加第二 seed、第二随机种子、权重 Hamming、窗口法、局部分支、容量偏好或 fallback；
- 不延长墙钟，不因结果不理想改变 tie-break、钳制容差、架构顺序或终态解释；
- 不把候选模型、精确提升前点、Hamming 值、24 h toy、Gate A、连续 guide、严格下界或 solver 文本状态写成原 MILP 可行容量或项目 TAC；
- Agentic 仅可编排哈希、资源门、资格审计与停止规则，不替代物理模型、提升证明或 HiGHS。

## 12. 冻结后的实现记录（不改写第 1–11 节）

D49 核心、BESS-only 监控执行器与两份定向测试已由提交 `86a8b80e18e4858e32aac208152bb7796530753c` 固定：

| 文件 | SHA-256 |
|---|---|
| `e0d49_physics_first_fuel_projection_primal_recovery.py` | `9d2dd610a2d7e59e9b8d9631e676277b0d36077c7a40d3448889defc041b3b14` |
| `e0d49_monitored_executor.py` | `57597be318a1d0bf3fa153ac144f027958c675a1ed9a1c4c36b2d9a47128311d` |
| `test_e0d49_physics_first_fuel_projection_primal_recovery.py` | `3bceaa97a186158b6039eff6b3f47cfb4c0a2047f3f635dd1402e120c1356dff` |
| `test_e0d49_monitored_executor.py` | `10cf492a5fb74af01ef02530362d6929e8f288107babfbd32a7b1e99a3e3444f` |

实现包含：原始二元分区、燃料编码/燃料流直接依赖审计、只连续化注册编码位的物理 Hamming 目标、每台机组全部结点/分段的静态提升证明、逐时确定性精确提升、完整二元域恢复、候选独立残差审计、D48 clean 原成本修复复用，以及只允许 BESS 的父级硬墙钟/资源门编排。

本地 D49 定向测试 `14 passed`，Ruff、format check 和 `py_compile` 通过。D40–D49 兼容回归为 `210 passed / 5 skipped / 3 failed`，本地全包为 `665 passed / 5 skipped / 3 failed`；两者的同一 3 个失败都来自既有 D42 测试在 Windows 中文长路径下调用 HiGHS `writeBasis` 返回 `kError`，没有 D49 栈帧或新增失败类型。该环境差异不被豁免为正式 Gate A 通过：必须在 OpenBayes Linux ASCII 路径上以同哈希提交重新执行 D49 定向、D40–D49 兼容与全包测试，要求零失败、零错误、零跳过，并完成三架构 8784 h build-only 后才允许正式 BESS。

## 13. OpenBayes Gate A 记录（不改写第 1–11 节）

OpenBayes Gate A 已使用实现提交 `86a8b80e...` 的同哈希源码/测试和文档记录提交 `865cc97b0428f12bb3592c931db27bfd5ed0e223` 编译通过：

- D49 定向、D40–D49 兼容与全包分别为 `14/219/673 passed`，全部零失败、零错误、零跳过；Ruff 与 `py_compile` sentinel 均通过；
- BESS/TES/Hybrid 的 8784 h build-only 原始规模分别为 `597,318/650,052/685,194` 个活动变量、`79,057/87,840/96,625` 个原始二元和 `527,053/606,163/667,662` 条活动约束；
- 三架构均投影 `52,704` 个 CHP 燃料编码位，分别保留 `26,353/35,136/43,921` 个物理二元；分区覆盖、不交、依赖边界、约束身份、原容量边界和全部注册燃料段/结点静态提升证明均通过；
- 三份构建均记录 `solver_invoked=false` 与 `formal_optimization_invoked=false`；Gate A 明确只允许 BESS，TES/Hybrid 正式权限为 `false`；
- Gate A manifest/execution SHA-256 为 `11b283d6825cd5fcc5b41a09b8400bdb6116bb11e830b1dd1bc42b9417e789dd` / `2fd4a89660ff6b8443832eb29891e8dec689601bf54ca6bd041387502c60792b`；远端 19 个工作产物和 2 个 Gate A 产物已回传，checksum 复核零不一致；
- 首次 build CLI 误把 D46 摘要 `bess_guide.json` 接入 guide 参数，被预注册哈希门在任何 solver 调用前拒绝；拒绝日志完整保留。通过版本使用原锁定 `*_guide.csv.gz` 快照，未改变代码、模型、种子、选项、容差或墙钟。

Gate A 仅关闭正式执行准入门，不产生 candidate、repair、容量、上界、gap、项目 TAC、不可行证明或技术排序。下一步只能启动第 9 节冻结路径的一次 BESS 正式方法门。

## 14. 唯一正式 BESS 方法门终态（不改写第 1–11 节）

唯一正式 BESS 方法门已在冻结远端目录完成，formal manifest SHA-256 为 `0d66f06defcc8ecabe247bc7eb38c3f9e7f457d41dac82927295f54b0ad62a14`。候选阶段父级硬墙钟在 `3720.637203153223 s` 触发，child 收到 `SIGTERM`、返回码 `-15`；没有 `bess_candidate.csv.gz`、`bess_candidate.json`、exact-lift 产物或 repair，故 `candidate_status=null`、`repair_status=null`、`audited_feasible_upper_bound_cny=null`。

执行资源事实为：峰值 child process-tree RSS `3.137737274169922 GiB`，峰值父子聚合 RSS `3.1623153686523438 GiB`，最低可用内存 `94.17270278930664 GiB`，活动残留进程数 0。`resource_gate_passed=false` 来自父级硬墙钟受控停止，不是 35/45 GiB RSS 或 30 GiB 主机可用内存阈值越界。TES/Hybrid 未执行，成功架构数为 0。

按第 10 节预注册规则，BESS 科学终态只能登记为 `no_primal_status_closure`。这不证明 BESS 物理不可行、工程 MIP 不可行或有理数不可行，也不产生可行容量、原 MILP 上界、gap、项目 TAC 或技术排序。规范远端 5 个产物和 formal manifest 声明的 4 个 artifact 已全部回传并零哈希不一致；本地证据目录为 `风光火+熔盐储热/数据采集/e0d49_physics_first_fuel_projection_primal_recovery/`。

D49 由此关闭且不得原样重跑。下一步仅允许另立 D50 结果前方法设计；不开放 TES/Hybrid 同方法正式执行、E2–E4、699 点扫描或技术排序。
