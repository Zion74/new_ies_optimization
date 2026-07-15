# E0-D-46 三架构全年可行上界与固定二元修复合同

状态：**第 1–11 节结果前合同已冻结；第 12 节源码/本地测试、第 13 节 OpenBayes Gate A 与第 14 节唯一正式总批次均已完成；三架构均无 candidate incumbent，D46 不得原样重跑**

适用范围：D47 已恢复 Hybrid R0 严格下界、BESS/TES/Hybrid 三架构均已有至少一个全年严格下界之后，为同一 2024 年 8784 h 原始 MILP 恢复第一组可审计可行解、容量与受控成本上界

日期：2026-07-15

## 1. 本关只回答什么

D46 只回答：在不改变 D40–D47 的真实全年输入、原始三架构 MILP、服务目标、容量边界和受控公开成本口径的前提下，能否通过“**最大容量可行性锚点—R0 连续引导—原 MILP 首个 incumbent—完整二元固定—全年 LP 修复**”，分别为 BESS、TES、Hybrid 形成至少一个通过独立残差审计的原 MILP 可行解与目标上界。

D46 的目标是先证明“可行上界存在并可复核”，不是求最优容量或直接比较技术。候选 MIP 找到第一个可审计 incumbent 后即停止，不继续追求更小目标；因此即使三架构都成功，也不能按上界大小宣布赢家。

## 2. 已闭合下界与仍未闭合的口径

- BESS 严格下界：`1,144,950,604.8368804 CNY`；
- TES R0/R1 严格下界：`254,860,566.61931588889075258309724606578637338890918249419801438224278086471875331 CNY`；
- Hybrid R0 严格下界：`232,011,577.83593156905560264049764989154935073609620115224488377919660126326832988 CNY`，并由可行域包含关系覆盖 Hybrid R1 与原 MILP；
- 三个下界来源、松弛强度和数值紧度不同，不能按大小排序；
- D24 的 TES 严格成本账户仍为 `0/16`，D25 项目运行账户仍为 `0/4`；因此 D46 的目标值仍属于 `controlled_public_cost_sensitivity_not_formal_project_tac`，不是杨凌项目正式 TAC。

D47 manifest 已给出 `d46_feasible_upper_bound_contract_permitted=true`。该权限只允许本结果前合同、独立实现/Gate A 和一次正式 D46，不允许回写历史下界、直接跑 E2–E4 或提前宣布技术边界。

## 3. 锁定输入与身份链

| 输入 | SHA-256 / 锁定值 |
|---|---|
| D47 formal manifest | `8b74c4044854d18d5dffa6c2759bfe747455631e0347293d6a89c16d35276101` |
| D47 formal execution | `ed978c3607f080456576e35dede75c57e017150514e24160462a62566bf9c330` |
| D40 full-year service | `1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95` |
| D40 Gate A manifest | `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577` |
| D41 Gate A manifest | `50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937` |
| D41 Gate B manifest | `bbc0638470859a58fe26a3166ec4825f455fd27671b7edf234b6e51557ee8aef` |
| D41 BESS R1 candidate guide（仅可作附加 warm-start 诊断） | `2d03ab0ae229583bbf46e3ebdd84ab0924627d7ac20e2af68dad42ff11de4614` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| D41 binary inventory/fixing module | `c7f45f8c071bb92c6cf7576a76bed71b71e606b7239881cb8baac09b195d2f1e` |

正式服务继续固定为：2024 年 `8784 h`、基线热负荷、PCC `700 MW`、年送出电量 `4,035,354.738554194 MWh` 的平均功率等式、最大弃电 `339,569.90645758656 MWh`（可用风光的 10%）。代表期不得进入正式 D46。

原始三架构模型身份必须逐项复现：

| 架构 | 活动变量 | 活动约束 | 原始二元 |
|---|---:|---:|---:|
| BESS | `597,318` | `527,053` | `79,057` |
| TES | `650,052` | `606,163` | `87,840` |
| Hybrid | `685,194` | `667,662` | `96,625` |

任一输入哈希、名称集合、模型规模、目标方向、服务或容量边界不一致即停止，不允许以新身份继续。

## 4. 冻结的容量可行性锚点

候选阶段不从代表周容量或事后试出的容量开始，而固定使用既有工程上界：

- BESS：能量 `2400 MWh`，充电、放电与共同 PCS 功率均为 `100 MW`，`bess.installed=1`；
- TES：HT/MT/LT 三个罐容量均为 `55,654.86255374656 t`，电加热、蒸汽至 HT、蒸汽至 MT、电输出和热输出端口均为 `300 MW`；
- Hybrid：同时使用上述 BESS 与 TES 锚点。

只固定对外设计变量；总盐量、服务盐量、逐时库存和全部调度变量仍由模型决定。锚点只用于提高“先找到可行 incumbent”的概率，不是推荐容量，也不允许写成现场设计值。

## 5. 冻结的候选—修复算法

每个架构独立执行以下阶段，顺序固定为 BESS→TES→Hybrid；一个架构失败不阻止另外两个架构留下独立证据。

### 5.1 R0 连续引导

在同一原始 Pyomo 模型上固定第 4 节容量锚点，把 D41 完整二元清单全部连续化，保留年送出等式、弃电上限、全年单循环、容量和成本约束，求解一次 R0 LP。只有返回有限 primal、全部变量有限、服务与独立残差审计通过时，才可生成 warm start。

二元 seed 的确定规则结果前固定：拓扑二元取锚点值；CHP 在线状态按 R0 在线值与 `0.5` 比较；燃料段先对 `fuel_segment_active` 取最小索引的最大值，再编码为合法 logarithmic code，禁止逐 bit 独立四舍五入产生非法段；BESS 与 TES 模式按对应充/放、接收/输出流的较大者确定，相等或双方均小于 `1e-9` 时固定取 0。所有非二元变量沿用有限 R0 值作为 MIP start，不把 R0 objective 当作上界。

D41 BESS R1 guide 只允许作为 BESS 的第二个预注册 seed：必须通过完整变量名和哈希准入；它不能替代新 R0 guide，也不能提供上界。正式 seed 顺序固定为“新 R0 seed→若 HiGHS 明确拒绝该 seed，才尝试 D41 BESS guide seed”；TES/Hybrid 不设置事后附加 seed。

### 5.2 原 MILP 首个 incumbent

恢复原始二元域，容量继续固定在第 4 节锚点，以原受控成本目标运行原 MILP。必须向 HiGHS 提交第 5.1 节完整 seed；只要 callback 返回一个全部列有限的 MIP incumbent，即请求软中断并完整归档变量值、原始二元快照、objective、solver info 与模型身份。

候选阶段不要求最优、dual bound 或相对 gap。没有 incumbent、只有 LP bound、只有分数解、callback 数组不完整或软中断后无法复现 incumbent，都按 `no_candidate_incumbent` 处理。

### 5.3 Repair A：固定容量与完整二元

从锁定输入重新构建原 MILP，使用 D41 `fix_binary_snapshot()` 按名称固定全部原始二元，并再次固定最大容量锚点。缺失、额外、分数、非有限或名称哈希不符一律拒绝。随后只求解连续 repair LP；只有 Repair A 通过第 6 节全部审计，才形成最低限度的原 MILP 可行上界资格。

### 5.4 Repair B：容量收缩（非成功必要条件）

Repair A 成功后，保持同一完整二元快照，释放连续容量变量到原始有限边界，重新求解一次 LP。Repair B 若同样通过全部审计且向上舍入目标不高于 Repair A，则选 Repair B；否则保留 Repair A。禁止因 Repair B 失败撤销 Repair A，也禁止增加第三种容量锚点或新 seed。

## 6. 可行性、目标与上界资格

每个候选必须在重建的原始模型上同时满足：

- HiGHS 返回有限 primal，`num_primal_infeasibilities=0`，报告最大 primal infeasibility 不超过 `1e-8`；
- 独立遍历全部活动变量边界和活动约束，最大绝对违反不超过 `1e-7`，并登记最坏组件名称；
- 全部原始二元值精确为 0/1、完整固定且名称集合 SHA-256 与 D41 Gate A 一致；
- 年送出平均功率等式残差不超过 `1e-8 MW`，弃电上限违反不超过 `1e-6 MWh`；
- BESS/TES 全年循环终端残差、CHP 转移/爬坡、逐时 PCC/热平衡、储能互斥、容量联动和 BESS 吞吐量约束分别通过；
- 所有容量有限、非负、在冻结边界内；目标各组成项逐项重算，和模型目标差不超过 `max(0.01 CNY, 1e-10×|objective|)`。

合格目标使用 `Decimal.from_float()`、80 位精度和 `ROUND_CEILING` 向上舍入，字段命名为 `audited_feasible_upper_bound_cny`。这里的“可行”是按上述冻结数值容差审计的工程优化可行性，不宣称有理数精确可行证书；manifest 必须保留该限定。D47 的拉格朗日包络上端点不得进入本节。

## 7. Gate A：正式 8784 h 之前必须证明什么

D46 源码与测试必须在任何正式引导、MIP 或 repair 前独立提交并与 OpenBayes 逐字节同哈希。Gate A 包括：

- 人工小 MILP 上验证 R0 seed、合法燃料段编码、模式 tie-break、首个 incumbent 捕获、完整二元固定和 Repair A/B 选择；
- 缺失/额外/分数二元、错误模型哈希、错误服务、错误容量锚点、篡改 incumbent、非有限值和残差超限全部拒绝；
- 24 h 三架构 Linux 集成实际调用 HiGHS，至少各形成一个经原模型重建审计的 toy upper bound；
- 正式 8784 h 只做 build-only 身份与锚点审计，不调用正式 R0/MIP/repair；
- 父进程硬墙钟、callback 软停止、心跳、资源门、进程组终止与活动残留为 0 的回归通过；
- D40–D47 与 D46 定向、全包回归、Ruff 和 py_compile 全部通过，OpenBayes 零失败、零跳过；
- Gate A manifest 绑定完整 Git commit、source/test SHA-256、正式输入哈希、测试计数和 `formal_optimization_invoked=false`。

Gate A 成功只开放一次正式 D46，不代表三架构已经可行。

## 8. 正式资源与单次执行合同

正式环境固定为 OpenBayes Linux、60 CPU、约 97 GiB、Python 3.10.18、Pyomo 6.10.1、highspy 1.15.1，仅使用 HiGHS。三架构严格顺序，每个求解 child 固定 12 个 HiGHS 线程；`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`。

- R0 guide：软墙钟 `900 s`、parent 硬墙钟 `1020 s`；
- 原 MILP 首 incumbent：软墙钟 `3600 s`、parent 硬墙钟 `3720 s`；
- Repair A：parent 硬墙钟 `1500 s`；
- Repair B：parent 硬墙钟 `1500 s`；
- 每架构总硬墙钟 `7200 s`，正式批次总硬墙钟 `21600 s`；
- 每个活动求解进程树 RSS 上限 `35 GiB`，父子聚合 RSS 上限 `45 GiB`，主机可用内存不得低于 `30 GiB`；
- 每 `5 s` 写 heartbeat；停止时先终止进程组、等待 `30 s` 后强杀，活动残留进程必须为 0。

正式 D46 只允许一个总批次。不得根据 BESS 结果修改 TES/Hybrid 的 seed、锚点、容差、墙钟或 solver 选项。

## 9. 输出、成功状态与后续权限

Gate A 固定输出：

`/root/e0-b-20260711-019f4f64/results/e0d46_gate_a/`

正式输出：

`/root/e0-b-20260711-019f4f64/results/e0d46_full_year_feasible_upper_bound_repair/`

目录事前必须不存在。每架构至少登记 guide、seed、MIP incumbent、binary snapshot、Repair A、可选 Repair B、独立残差审计、容量、成本分项、result/execution/log/heartbeat 和 SHA-256；总 manifest 必须绑定三架构下界、输入、源码、全部阶段状态和声明权限。

单架构成功状态为 `audited_feasible_upper_bound_recovered`；无 guide、无 incumbent 或 Repair A 不合格分别记为 `no_continuous_guide`、`no_candidate_incumbent`、`fixed_binary_repair_failed`。三架构都成功时总状态为 `all_architecture_upper_bounds_recovered`；否则为 `partial_or_no_upper_bound_recovery`，但已成功架构的上界仍保留。

只有三架构均成功，才允许在同一受控成本口径下分别报告“严格下界—审计可行上界”区间和保守 gap，并另立后续 gap 收缩合同。即便如此，`formal_project_tac_ready=false`、`technical_ranking_permitted=false`，E2–E4 与 699 次扫描仍不自动开放。

## 10. 主张边界与 Agentic 角色

D46 成功时允许的最强表述是：在同一 2024 年 8784 h 原始架构 MILP、服务与公开成本敏感性口径下，某个完整二元快照经原模型重建和冻结残差门验证，形成一个有限可行 incumbent、容量方案及目标上界。

D46 不得把首个 incumbent 称为最优解，不得用上界大小排序技术，不得把 Repair B 容量写成现场推荐，不得把受控成本写成项目 TAC，也不得从失败推出架构物理不可行。Agentic 只负责编排哈希、seed 顺序、callback 停止、固定快照、资源门、审计与主张权限；不生成物理规律、不替代 HiGHS、不决定技术赢家，也不作为 SCI 的独立算法贡献。

## 11. 禁止事项与停止规则

D46 禁止：修改 D40 服务或输入；重跑/覆盖 D41–D47；读取拉格朗日 upper interval 当作可行上界；使用代表期容量作为正式起点；事后新增容量锚点、seed 或 repair 阶段；只固定部分二元；忽略残差或 solver primal infeasibility；把 R0 objective、MIP dual bound 或无审计 incumbent 记为上界；因一个架构失败而把另一个架构宣布更优；在正式证据回传和三层文档提交前启动 gap 收缩、E2–E4 或技术排序。

合同、源码/测试提交和 OpenBayes 同哈希 Gate A 全部完成前，不允许正式 D46。正式 D46 完成后不得按结果原样重跑；任何增强必须另立新的结果前合同。

## 12. 实现与本地验证记录（结果后登记，不改写第 1–11 节）

D46 源码与测试已在本地提交 `fe3b669250c8071b24f5b8fb75bf4d3634720bdc`：

- `src/tes_bess_boundary/e0d46_full_year_feasible_upper_bound_repair.py`：实现工程容量锚点、R0 全列有限 seed、合法燃料段编码、BESS/TES 模式 tie-break、确定性压缩工件、HiGHS 首 incumbent callback、完整二元固定、Repair A/B、服务/容量/循环/全约束/目标/solver primal 审计和 10 位向上舍入工程数值上界；
- `src/tes_bess_boundary/e0d46_monitored_executor.py`：实现 BESS→TES→Hybrid 顺序、12-thread HiGHS、阶段/架构/总硬墙钟、`35/45/30 GiB` 资源门、5 s heartbeat、进程组清理、D47/D41/D40/输入/Gate A 哈希准入、一次性结果目录和总 manifest；
- BESS 新 R0 seed 被 HiGHS 日志明确拒绝时，执行器可立即中断该尝试，并且只允许读取哈希 `2d03ab0a...` 的 D41 BESS R1 guide 生成第二个合法 seed；TES/Hybrid 不存在第二 seed；
- Repair A 必须固定全部原始二元与最大容量锚点；Repair B 只释放连续容量，失败或目标更高均保留 Repair A；任何 R0 objective、未审计 incumbent 或 solver bound 均不能进入上界字段；
- 本地 D46 定向回归 `22 passed`，其中包含 24 h BESS/TES/Hybrid 原 planning model 重建—R0—首 incumbent—Repair A 集成、BESS 显式 seed 拒绝、D41 guide 哈希/重编码和资源门；
- 本地 D40–D47/规划兼容回归 `199 passed + 5 Linux-only skipped`，全包回归 `639 passed + 5 Linux-only skipped`；Ruff 与 `py_compile` 通过。

上述 24 h 结果仅为 Gate A toy upper bound，不是正式 8784 h D46 上界。当前仍为 `formal_project_tac_ready=false`、`technical_ranking_permitted=false`；在 OpenBayes 同提交 Gate A manifest 通过前，唯一正式 D46 总批次不得启动。

## 13. OpenBayes Gate A 记录（结果后登记，不改写第 1–11 节）

首次 8784 h BESS build-only 在求解器调用前由模型规模锁拒绝。审计确认 D40 三组变量/约束/二元计数没有漂移，原因是 D46 的 `EXPECTED_MODEL_SIZE` 漏写 `_linearity_audit()` 合法返回的 `nonlinear_component_count=0` 与空 `nonlinear_components` 两个字段，导致整字典比较必然失败。修复只补齐这两个已冻结零字段并将断言写入既有三架构 24 h Gate A 测试，不改变任何模型、服务、容量、seed、残差、求解器或资源合同；最终同哈希源码提交为 `4a18f4232563a187652e6c6d509441834bce1e7a`。

OpenBayes 使用 Python 3.10.18、Pyomo 6.10.1、highspy 1.15.1。最终 Gate A 结果为：

- D46 定向 `22 passed`；D40–D47 + planning/HiGHS 兼容集 `204 passed`；全包 `644 passed`；三者均为零失败、零错误、零跳过；Ruff 与 `py_compile` 通过；
- BESS 原模型 `597,318` 个活动变量、`527,053` 条活动约束、`79,057` 个活动二元；TES 为 `650,052 / 606,163 / 87,840`；Hybrid 为 `685,194 / 667,662 / 96,625`；三架构非线性计数均为 0，R0 后活动二元计数均为 0；
- 三个 build-only 工件均为 `gate_a_build_passed`、`solver_invoked=false`、`formal_optimization_invoked=false`；
- Gate A manifest/execution SHA-256 分别为 `098fc8bef7fe160cdad98d5d22675d82dcd9341e03e656792b357e7f29f1d176` / `2ca2f3cd22049ad75db51d8f07b4161a9a1414ab0bec01df1d51de31251c84df`，状态 `gate_a_passed`、`formal_run_permitted=true`；本地证据位于 `风光火+熔盐储热/数据采集/e0d46_gate_a/`。

Gate A 不产生正式可行上界、容量、项目 TAC 或 gap，且保持 `formal_project_tac_ready=false`、`technical_ranking_permitted=false`。它只开放合同规定的唯一一次 BESS→TES→Hybrid 正式总批次。

## 14. 唯一正式 8784 h 总批次记录（结果后登记，不改写第 1–11 节）

唯一正式总批次已在 OpenBayes 按冻结的 BESS→TES→Hybrid 顺序完成。正式输出位于 `/root/e0-b-20260711-019f4f64/results/e0d46_full_year_feasible_upper_bound_repair/`，本地完整副本位于 `风光火+熔盐储热/数据采集/e0d46_full_year_feasible_upper_bound_repair/`。总 manifest SHA-256 为 `8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9`；32 个远端正式文件全部回传，manifest 声明的产物为 0 缺失、0 哈希不匹配。总运行时间为 `8820.16162651591 s`，结束后活动残留进程为 0。

三个架构的 R0 guide 都达到最优并通过审计，但它们只用于构造 seed，不是原 MILP 可行上界：

- BESS：`1,157,063,561.813816 CNY`；
- TES：`386,559,421.67063665 CNY`；
- Hybrid：`1,186,678,269.235802 CNY`。

BESS 新 R0 seed 被 HiGHS 明确拒绝，合同允许的 D41 BESS guide 回退 seed 也没有产生 incumbent。TES 与 Hybrid 的结构化 seed 分别出现 `48,801` 与 `48,791` 条行不可行；固定离散值 LP 均被明确判为 infeasible，随后原始 MILP 各运行满 `3600 s`，Primal bound 仍为 `inf`，没有完整 incumbent。三个架构因此均为 `no_candidate_incumbent`，均未进入 Repair A/B，`repair_selection=null`。

总状态为 `partial_or_no_upper_bound_recovery`，`successful_architecture_count=0`。本次正式批次没有形成可行容量、`audited_feasible_upper_bound_cny`、保守 gap、项目 TAC 或技术排序；`formal_project_tac_ready=false`、`technical_ranking_permitted=false`、`engineering_numerical_feasibility_only=true`。该结果只否定冻结容量锚点与预注册确定性 seed 在本合同墙钟内恢复 incumbent 的能力，不证明三种架构的原物理模型不可行，也不允许用 guide objective、MILP dual bound 或来源不同的严格下界排序技术。D46 不得按结果原样重跑；任何增强必须另立新的结果前合同。
