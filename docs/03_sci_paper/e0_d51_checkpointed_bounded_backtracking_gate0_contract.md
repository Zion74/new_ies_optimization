# E0-D-51 检查点化有界回退 Relax-and-Fix Gate 0 合同

状态：**结果前合同已冻结且 Gate 0 已验证通过；8784 h 正式优化仍未获准。**

冻结日期：2026-07-17。

## 1. 研究问题与当前权限

D50 在完整 8784 h 年度模型上以 `336 h` 整数前视、`168 h` 提交形成单一确定性路径。阶段 `0/1/2` 捕获 incumbent 并累计提交 `1,513` 个物理二元，阶段 `3` 在当前固定前缀下由 HiGHS 返回 `Infeasible`，最终状态为 `block_path_no_incumbent`。该结果只否定无回退单路径，不证明原 BESS MILP 或容量边界不可行。

D51 Gate 0 只回答一个实现与方法问题：

> 能否在不改变物理约束、容量边界和最终原成本修复口径的前提下，把 D50 的不可逆单路径控制器改造成可逐次落盘、可验证重放、失败时仅回退一个提交块并排除旧块模式的有界状态机？

本合同只授权缩短时域的单元、集成与故障注入验证。它不授权任何 8784 h optimize，不生成正式容量、上界、gap、TAC、E2–E4 扫描或技术排序。

## 2. D50 证据与不可重放缺口

D50 唯一正式总 manifest SHA-256 为 `3efdbba505ed2e34d14592e2384a67d074ae8ee08f35a32acdaa6b9639f10e91`。四个阶段文件证明前三段提交成功、第四段无 incumbent，但不能恢复前三段的实际 0/1 前缀：

1. `capture_first_original_cost_incumbent()` 曾在内存中返回完整 `variable_values`；
2. `solve_block_relax_and_fix_candidate()` 在写阶段 JSON 前执行 `capture.pop("variable_values", None)`；
3. `commit_audit` 只保留计数、名称哈希和最大整数残差，不保留值；
4. `write_physical_snapshot()` 只在全部提交块成功后调用；
5. 因此 D50 阶段 `0/1/2` 的完整 incumbent、容量和已提交二元值均未形成规范产物。

D51 不得声称精确续跑或复现 D50 死路。D50 原流水线不得原样重跑；D51 的所有数值只能来自新代码、新路径、新目录和新哈希。

## 3. 不变模型边界

Gate 0 原型必须复用 D50/D49 已验证的模型构建、物理二元分区、燃料编码投影、精确燃料提升和 clean 原成本 repair。除显式注册的候选搜索目标和 no-good cut 外，不得改变：

- 电热平衡、CHP 可行域、BESS SOC/模式/吞吐、PCC、弃电与循环约束；
- 连续容量变量及其原始上下界；
- 物理二元和燃料编码二元的名称、索引与完整清单；
- 最终 fixed-binary 原成本 repair 的目标、容差和独立审计；
- HiGHS 作为唯一求解器的要求。

Gate 0 的缩短时域案例只验证控制器，不构成年度服务、规划容量或技术优劣证据。

## 4. Gate 0 的冻结控制器

控制器状态固定为：

```text
ADVANCE -> STAGE_COMMITTED -> ADVANCE
ADVANCE -> STAGE_FAILED -> ROLLBACK_ONE_BLOCK -> ALTERNATIVE_ATTEMPT
ALTERNATIVE_ATTEMPT -> STAGE_COMMITTED -> ADVANCE
ALTERNATIVE_ATTEMPT -> STAGE_FAILED -> ROLLBACK_ONE_BLOCK / CLOSED_NO_PATH
最后一段通过 -> COMPLETE
```

Gate 0 固定以下机械规则：

1. 回退深度上限为一个已提交块；禁止跨两块或更深回溯。
2. 每个阶段最多 `3` 次尝试，即初始路径加至多 `2` 个替代块模式。
3. 每次失败只对将被撤销的当前提交块加入一个 binary no-good cut：

   \[
   \sum_{i:x_i^*=1}(1-x_i)+\sum_{i:x_i^*=0}x_i\ge 1.
   \]

4. no-good cut 只能排除一个已审计的完整块模式，不能排除容量、连续变量、前视块或更长前缀。
5. 阶段 `0` 无前序块可回退；若失败，控制器直接关闭。
6. 超过单阶段尝试上限、检查点损坏、回放不一致、域审计失败或无合法回退目标时，状态固定为 `closed_no_checkpointed_path`。
7. Gate 0 的总回退事件上限为 `4`；该数值只用于缩短时域验证，不自动成为未来正式参数。

## 5. 候选目标与主张边界

D50 的早期阶段使用原经济目标捕获首 incumbent。D51 Gate 0 显式测试“可行性优先”控制器：候选阶段临时使用常数零目标，只寻找满足当前固定/整数/放松域和全部活动约束的第一个完整有限 incumbent；找到后立即软中断。

目标替换必须被单独审计：原经济目标在进入候选控制器前记录身份，候选期间只有注册的零目标活动，进入精确提升和 clean repair 前恢复原目标。零目标、阶段 incumbent、块模式和缩短时域结果全部为 `candidate_only`，既不是原 MILP 上界也不是下界。

若零目标在 Gate 0 中无法稳定捕获并加载首 incumbent，不允许结果后改成 Hamming、成本混合、随机扰动或松弛罚项；必须关闭 Gate 0 或另立新合同。

## 6. 原子检查点与重放合同

每次获得阶段 incumbent 后、任何新 fixing 或下一次 optimize 前，必须写出一个不可覆盖的尝试检查点。检查点至少包含：

- schema、架构、阶段号、尝试号、父检查点 SHA-256 和状态机事件；
- 完整变量名称哈希、完整有限变量值及其压缩产物 SHA-256；
- 已提交物理二元、当前块模式、全局拓扑位和对应值；
- 连续容量变量名称和值；
- 原目标身份、候选目标身份、求解器状态、运行时间和报告 objective；
- 固定/活动整数/未来放松/燃料投影四类域审计；
- 约束身份、变量边界、整数残差和 incumbent 完整性审计；
- 当前活动 no-good cut 的规范表达及哈希。

产物必须先写临时文件、完成 fsync/关闭、计算 SHA-256，再以原子 rename 发布；已有规范路径禁止覆盖。重放时必须重新构建 clean 模型，只按检查点恢复注册值、fixing、域和 no-good cut，并逐项验证名称、值、父哈希和模型身份。任何缺项或不一致都必须拒绝，不能静默降级为 warm start。

## 7. Gate 0 验证矩阵

Gate 0 必须在不调用 8784 h optimize 的前提下完成：

1. 24 h 三块真实 Pyomo/HiGHS 集成链：检查点化推进、完整物理轨迹、燃料精确提升和 clean 原成本 repair 全部通过；
2. 故障注入链：在至少一个中间阶段强制首路径失败，证明控制器只回退一块、加入精确 no-good cut并通过第二或第三次尝试前进；
3. 关闭链：阶段 `0` 失败、三次尝试耗尽和四次总回退预算耗尽时均产生预注册关闭状态；
4. 重放链：clean 模型从检查点恢复后，固定值、域分区、no-good cut、变量/约束身份和父哈希全部一致；
5. 拒绝链：截断压缩文件、错误 SHA、错误父节点、缺变量、分数物理位、重复阶段/尝试路径、覆盖既有检查点和未注册 cut 必须失败；
6. 目标链：候选零目标与原经济目标严格互斥，clean repair 只能使用原经济目标；
7. 兼容回归：D49、D50、D40–D51 定向测试、全包测试、Ruff 和 `py_compile` 零失败；Linux Gate 0 不得跳过 D51 测试。

在上述测试通过后，可追加一个不超过 `840 h` 的性能诊断，但只能测量检查点体积、回放耗时、回退次数和首 incumbent 时间；不得据此报告年度容量、成本或技术结论，也不得用结果后调参。

## 8. Gate 0 通过与失败判据

只有同时满足以下条件，才能登记 `gate0_controller_validated`：

- 第 7 节强制测试全部通过；
- 至少一个故障注入案例由合法一步回退恢复；
- 每个成功尝试均存在完整原子检查点且可由 clean 模型重放；
- 约束身份未发生未注册变化；
- `formal_8784h_optimization_invoked=false`；
- 本地与 OpenBayes 同提交、同源码、同测试哈希闭合。

任一条件不满足均登记 `gate0_controller_not_validated`。Gate 0 通过只证明控制器机制可用，不证明 D51 全年路线可行；正式 8784 h BESS 运行仍须另行冻结方法、块长、前视、正式回退预算、线程、种子、容差、阶段/总墙钟、目录和终态。

## 9. Gate 0 目录与产物

本地 Gate 0 证据目录预留为：

`风光火+熔盐储热/数据采集/e0d51_checkpointed_bounded_backtracking_gate0/`

OpenBayes 目录只能在实现提交后按同名结果目录创建。规范产物至少包括：源码/测试哈希、定向/兼容/全包 JUnit、Ruff、pycompile、24 h 集成结果、故障注入与拒绝测试摘要、检查点 manifest、Gate 0 manifest、execution、日志和 `SHA256SUMS.txt`。

## 10. Agentic 边界

D51 状态机可作为硕士论文第 5 章 Agentic 编排的底层案例，但本 SCI 中仍只解释为确定性、预注册的求解控制器。Agentic 只可：

- 读取阶段状态与检查点；
- 校验哈希、域、资源、预算和主张资格；
- 按固定状态转移执行继续、一步回退或停止；
- 生成审计日志。

Agentic 不得选择二元值、改变 no-good cut 含义、修改容量/物理约束、动态调参、越过预算或把候选结果升级为技术结论。

## 11. 禁止项

- 禁止原样重跑 D50 或声称从 D50 阶段 `2` 续算；
- 禁止在 Gate 0 启动 8784 h optimize；
- 禁止两块以上回溯、无限尝试、随机多起点、结果后扩大 beam 或改变目标；
- 禁止添加物理松弛、服务松弛、局部循环、代表期权重或固定连续容量；
- 禁止把 checkpoint、部分轨迹、缩短时域容量或零目标 incumbent 写成正式上界；
- 禁止在同一规范路径覆盖或重写既有检查点；
- 禁止在 Gate 0 结果产生后反向修改第 1–11 节。

## 12. 登记规则

第 1–11 节必须先形成独立 Git 提交，之后才允许新增 D51 源码、测试或任何 Gate 0 数值产物。实现身份、测试结果、OpenBayes Gate 0 和后续正式权限只能按时间顺序追加在本节之后，不得反写冻结规则。

## 13. 实现登记

结果前合同提交为 `58f1069`；其后实现提交为 `baec96179728ccc8ad73e16d937d31e390f0f820`。实现没有增加 8784 h 命令，只暴露 `demonstration-24h` 和只读 `compile-gate0` 两个 Gate 0 入口。

同提交核心文件及 SHA-256 为：

- `e0d51_checkpointed_bounded_backtracking.py`：`1b50ed42ebc31fb845dc5a1498abd5dcac38899eb09682ee809850504ea4d447`；
- `e0d51_gate0_evidence.py`：`35b289bfb1bc38afe568cd37ece3c1e0ebad3276b1bfcbce23aa3cbbe00a5e13`；
- `test_e0d51_checkpointed_bounded_backtracking.py`：`e00fe64395cef3d1bc4712cca6adbba69b078f10f360e7d2a2802c5527330690`。

实现覆盖原子 gzip 变量快照、不可覆盖 JSON manifest、父节点和 cut 哈希链、容量/变量/域身份拒绝、clean 同阶段域重放、确定性一步回退状态机、零可行性目标的激活与原目标恢复、首 incumbent 捕获、精确燃料提升及 D50 clean 原成本 repair。入口对 `period_count > 840` 直接拒绝，因此 Gate 0 代码本身不能触发全年正式求解。

## 14. OpenBayes Gate 0 结果与权限

2026-07-17 在 OpenBayes `60 CPU / 97 GiB`、Python `3.10.18`、HiGHS `1.15.1` 环境以实现提交同哈希执行。Linux 证据为：

- D51 定向测试 `15 passed`，零失败、零错误、零跳过；
- D40–D51 兼容回归 `249 passed`，零失败、零错误、零跳过；
- 全包回归 `703 passed`，零失败、零错误、零跳过；
- Ruff 与 `py_compile` 均通过；
- 24 h 案例按三个 `8 h` 块完成候选搜索，三个原子检查点均由 clean 模型重放通过，固定值最大残差为 `0`；随后完成精确燃料提升和原成本 clean repair；
- demonstration 明确记录 `formal_8784h_optimization_invoked=false`、`formal_run_permitted=false` 和 `formal_upper_bound_eligible=false`。

Gate 0 manifest 状态为 `gate0_controller_validated`，SHA-256 为 `883d4c0bad9bb9e66011d769b5c7886bc09494f64fb68bcdf927ae65fb90d152`；execution SHA-256 为 `d5e084b65d713d817cb759415eb81361cb688b51a0c9461e27a125535c31a6bd`。远端证据根共 `30` 个文件并通过 `SHA256SUMS.txt` 逐项校验。原始远端完整归档 SHA-256 为 `01df6ae94640d9638e247998550700041861f437b3143a54056004b26f66f408`；为兼容 Windows 文件名生成的只读导出归档 SHA-256 为 `2fb84863999e15a5e89b20fccc420d034a060444ce45412bef948ac6a75a5c9d`。

首次调用 24 h 示范时，预先创建的空 `demonstration/` 目录触发不可覆盖保护，求解器未启动；该失败日志原样保留。规范示范随后只在全新 `demonstration_24h_run1/` 路径执行一次。早期 PowerShell 管道还使四个辅助日志名带尾随回车；原始归档保留精确文件名，Windows 导出仅把该字符显式映射为 `.__TRAILING_CR__`，没有改写规范 JSON、JUnit、检查点或求解结果。

据此，D51 只获得“检查点化有界回退控制器通过 Gate 0”的资格。它没有产生正式容量、年度可行上界、gap、TAC 或技术排序证据；`formal_run_permitted=false` 继续有效。下一步若要运行 8784 h BESS，必须另立并先提交结果前正式合同，重新冻结块长、前视、回退预算、尝试数、线程、容差、墙钟、目录和终态，不得把本节 24 h repair 升格为年度上界。
