# E0-D-43 冻结 HiGHS 快照离线对偶证书恢复合同

状态：**第 1–10 节结果前合同已冻结；Gate A 双端通过；唯一一次正式 Gate B 已结束，结果为 `no_strict_certificate`**

适用范围：D42 已保存 TES R0 原生 solution 快照、但 80 位拉格朗日证书未在父进程硬墙钟内落盘之后的只读恢复

日期：2026-07-15

## 1. 本关只回答什么

D43 只回答：能否在不重建模型、不调用优化器、不改变 D42 LP 或对偶向量的前提下，从已经哈希锁定的 IPX 与 dual simplex solution 快照中离线恢复至少一个有限、方向正确、可复核的 TES R0 拉格朗日严格下界。

D43 不是新一轮求解，不生成原 MILP 可行上界、容量、项目 TAC、gap 或技术排序。它只把 D42 已经落盘、但来不及完成证书复算的冻结对偶快照送入同一 80 位定向舍入证书器。

## 2. 不可覆盖的既有结果

- D41/D42 已复核 BESS 严格下界 `1,144,950,604.8368804 CNY`；该数值不是原 MILP 可行解、容量方案或项目 TAC；
- D42 TES R0 的原始 LP 为 `606,163 × 650,052`、`2,521,170` 个非零元，presolve LP 为 `439,018 × 509,289`、`1,806,011` 个非零元；
- D42 IPX 与 simplex 第 1 段均已由 HiGHS 返回，solution 归档均完整落盘且 `dual_valid=true`，但证书和 basis 没有在冻结硬墙钟内落盘；
- D42 因 `no_strict_certificate` 已结束，simplex 2–4、TES R1 与 Hybrid 未启动；
- D42 失败不证明 TES 不可行，不证明 BESS 优于 TES，也不允许启动全年可行上界或技术排序。

D43 不修改、补写或替换任何 D42 文件。D42 的终态永久保持 `no_strict_certificate`；D43 若成功，只能形成一份新的、来源明确的离线证书。

## 3. 锁定输入与代码身份

D43 只读使用本地和 OpenBayes 已逐文件同哈希的 D42 TES R0 证据：

| 输入 | SHA-256 / 锁定值 |
|---|---|
| `case_manifest.json` | `cacd6cc2e32e2b8849398db4b75afa835a4796310e404e3301099c3942261944` |
| `case_execution.json` | `49e2e21445c67a233ed2bc205a8266351ae800b566d0f89cbfa7883a059efc51` |
| `lp_manifest.json` | `23b10bd00abde649924f8f80901292188c60bf3a54d5dd2547ed60a44209fd84` |
| `lp_execution.json` | `621bc909b9fe6d7af759c96e4e83ea92c4a4f67ffd6a4255825ea8ace08c2fe7` |
| `presolved_lp.bin.gz` | `dd362f179fd00052ecbca4c25d5d8d285811fbdd5700fa2d4adb49a2f7626776` |
| presolve LP 指纹 | `c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5` |
| `phase_ipx_solution.bin.gz` | `d56109dabfc599ff996771924bc78f11b85c90f1dec001fd90edc9766fa5bfc6` |
| `phase_ipx_execution.json` | `43bd8bb93120b917cf4a62433b2ab99ea349df7dfe5664c54ca9822febd4a206` |
| `phase_simplex_1_solution.bin.gz` | `bec595dfbc6b878659f588ed100d08c7368e55e4d89f91bafa22e49a9163b58b` |
| `phase_simplex_1_execution.json` | `c872fbd63a72fc0f6b733220b86a57a9e2f75fbfe4e46204ef8586899317a7c1` |
| D42 BESS reuse result | `ae30997a4dcf4fb3ed599ff17b9f5bb1238d66ad4eda677312e91a69bd4f5d36` |
| D42 Gate A structure manifest | `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1` |

证书公式继续使用 SHA-256 为 `3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298` 的 `e0d42_native_highs_certificate.py`，二进制归档格式继续使用 SHA-256 为 `c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51` 的 `e0d42_gate_b_executor.py`。D43 不修改这两个文件；新增只读编排器和测试必须在任何正式离线复算前独立提交并与 OpenBayes 逐字节同哈希。

## 4. 快照准入门

每个 solution 快照必须独立通过以下全部检查后才可进入证书器：

1. 文件 SHA-256 与第 3 节一致，且被对应 phase execution 和 `lp_execution.json` 的哈希链引用；
2. schema 严格为 `tes_bess_boundary.e0d42_solution_archive.v1`，LP 指纹严格等于冻结 presolve LP；
3. 数组集合只能为 `col_value / col_dual / row_value / row_dual`，长度分别为 `509,289 / 509,289 / 439,018 / 439,018`；
4. `dual_valid=true`，全部 row dual 为有限 IEEE-754 双精度数；
5. LP 归档 round-trip 指纹、目标方向、offset、边界、矩阵布局和连续域审计全部通过；
6. 快照只读加载，不调用 `Highs.run()`、`presolve()`、simplex、IPX、crossover 或任何模型构造入口。

任一快照准入失败时，该快照登记为 `snapshot_ineligible`，不得修补数组、重新缩放或从 solver log 重建对偶量。另一快照仍按冻结规则独立审查。

## 5. 冻结证书算法

每个准入快照都把原始 `row_dual` 逐值送入既有 `certify_lagrangian_lower_bound()`，并固定：

- `precision=80`；
- 最小化方向、同一 presolve LP 指纹和原始 objective offset；
- 对单边无穷行只执行 D42 已冻结的符号投影；
- 逐列计算 (c-A^Ty) 的向外舍入区间，并在冻结列边界上取严格下界；
- 任一需要的无穷列端点导致该快照 `nonfinite_required_column_endpoint`；
- 不使用 primal objective、solver log、HiGHS internal bound 或浮点容差替代该证书。

两个快照均必须尝试。若至少一个证书满足 `formal_lower_bound_eligible=true`、下界和区间宽度均有限且区间宽度非负，则 D43 用 Decimal 数值最大的合法下界作为 TES R0 的 D43 下界；选择规则在结果前固定，不按技术排序或预期大小挑选快照。若两个快照都无合法证书，D43 状态为 `no_strict_certificate`。

## 6. 执行与资源合同

正式环境固定为 OpenBayes Python 3.10.18、`Pyomo 6.10.1 + highspy 1.15.1`。离线证书器不调用 HiGHS 优化，但为避免两个单线程 Decimal 复算串行浪费墙钟，父进程固定并行宽度为 2，各自运行 IPX 与 simplex 快照：

- 每个 clean child 硬墙钟 `1,800 s`，父进程总硬墙钟 `2,100 s`；
- `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`；
- 每个子进程树 RSS 上限 `8 GiB`，父子合计 RSS 上限 `20 GiB`，主机可用内存不得低于 `20 GiB`；
- 父进程每 `5 s` 写一次心跳和 RSS/可用内存；触发停止时先 `SIGTERM`，等待 `30 s` 后才可 `SIGKILL`；
- 两个 child 的完成顺序不影响输出顺序，manifest 固定按 `ipx`、`simplex_1` 排列；
- D43 只允许这一次正式离线复算，不因结果调整精度、墙钟、并行度、快照集合或选择规则。

## 7. 输出与哈希链

新产物只写入：

- 本地：`风光火+熔盐储热/数据采集/e0d43_offline_dual_certificate_recovery/`；
- OpenBayes：`/root/e0-b-20260711-019f4f64/results/e0d43_offline_dual_certificate_recovery/`。

固定输出为每个快照的 `certificate.json`、`execution.json`、心跳文件，以及总 `manifest.json`、`execution.json` 和 `README.md`。所有 JSON 使用确定性键序与分隔符；运行时间和资源采样只进入 execution sidecar，不进入规范 manifest。编排器拒绝覆盖非空正式目录，并在总 manifest 中登记全部输入、源码、证书和 execution SHA-256。

## 8. 验收与科学资格

D43 分两道门：

- **Gate A — 实现门**：新增编排器必须覆盖归档篡改、LP 指纹不符、数组错长、非有限 dual、`dual_valid=false`、双快照一成一败、Decimal 最大值选择、硬墙钟和资源停止测试；本地/OpenBayes 定向及全包回归通过，源码/测试同哈希并先提交。Gate A 不读取正式 row dual，也不生成正式下界；
- **Gate B — 正式离线证书门**：只在 Gate A 提交后读取第 3 节冻结产物。至少一个快照形成有限合法证书时，状态为 `tes_lower_bound_recovered`；否则为 `no_strict_certificate`。

TES R0 与 R1 的原始和 presolve LP 指纹已由 D42 Gate A 证明完全相同，因此合法 TES R0 证书可覆盖 TES R1；该传播必须再次核验 D42 structure manifest。即使 Gate B 通过，D43 也只关闭 TES 下界缺口，Hybrid 下界仍为空，技术排序仍禁止。

## 9. 后续权限与停止规则

- Gate A 失败：修复实现并重新独立提交，正式快照不得读取；
- Gate B 两个快照均无合法证书：D43 失败并停止，Hybrid 不启动；后续只能另立新的数值缩放、对偶修复或严格主问题分解合同；
- Gate B 至少一个快照通过：可另立 Hybrid 全年严格下界结果前合同，但不得在 D43 名下调用 Hybrid 求解器；
- 只有 BESS、TES、Hybrid 三架构下界全部闭合后，才可另立原始全年可行上界修复合同；
- D24/D25 正式账户未闭合前，任何数值仍只属于公开成本敏感性，不得写成杨凌项目 TAC。

## 10. 禁止事项与主张边界

D43 禁止：重跑 D42 TES 求解、延长 D42 墙钟、修改 D42 证书公式、从日志摘录 objective、修补或平滑 dual、搜索缩放参数、恢复代表期、启动 Hybrid、生成容量或技术赢家。

允许的最强表述只有：某个哈希锁定的 D42 TES R0 对偶快照，在同一冻结 presolve LP 上通过 80 位向外舍入拉格朗日审计，形成一个合法有限下界。若未通过，只能表述离线证书恢复失败。两种情况都不能推出 TES 物理不可行或 BESS 相对更优。

## 11. Gate A 本地实现登记（不改写第 1–10 节）

结果前提交候选已新增 `e0d43_offline_dual_certificate.py` 与 `test_e0d43_offline_dual_certificate.py`，SHA-256 分别为 `684385d5a33a531a9034f52ad755b7655adc2e58690ca689ad4e2f08eb889791` 与 `50c5e819f206e87aaba3f27254e401529140f4f6d6fa8660d5bc901afb691933`。D42 证书器和执行器没有修改；D43 正式入口会在启动 child 前重新核验其第 3 节锁定源码哈希。

实现已覆盖：case/lp/phase execution、BESS reuse、structure manifest 与 solution 的完整哈希引用链；schema、LP 指纹、四数组集合与维度、`dual_valid` 和 finite row dual 准入；未修改的 80 位证书调用；两个 clean child 的固定并行编排；父进程硬墙钟、RSS、可用内存、5 s 心跳和停止优先级；Decimal 最大合法下界选择与 tie 时 IPX 优先；只读总 manifest/execution/README；非空输出拒绝。所有正式结果字段固定 `optimization_invoked=false`、`native_solver_invoked=false`、`technical_ranking_permitted=false`。

本地新增测试 `15 passed in 1.03s`，D40–D43 定向回归 `80 passed in 5.81s`，完整回归 `534 passed in 62.51s`，Ruff 通过。结果前实现已提交为 `78e30ee`。OpenBayes 上源码/测试与本地逐字节同哈希，`py_compile`、D40–D43 定向 `80 passed in 0.75s`、完整回归 `534 passed in 34.18s`；在 Gate A 提交时正式输出目录仍不存在。两端测试都只使用合成小 LP 和人工 solution 归档，没有读取 D42 正式 row dual，也没有调用 D43 正式入口。Gate A 至此关闭；本节状态提交后才允许执行唯一一次正式 D43。

## 12. Gate B 正式结果登记（不改写第 1–10 节）

唯一一次正式 D43 已在 OpenBayes 按第 6 节冻结设置执行。两个 D42 solution 归档均通过完整元数据、LP 指纹、数组维度、`dual_valid=true` 和 finite row dual 准入；两个 clean child 并行读取各自完整 `439,018` 维 row dual，未重建模型、未调用优化器或原生求解器，也未修改 80 位证书函数。

IPX child 运行 `1800.4872665889561 s`，simplex child 运行 `1800.4875770630315 s`；二者均在证书计算尚未完成时因冻结 child 硬墙钟被父进程终止，返回码均为 `-15`。两个 child 都没有生成 result 或 certificate，因此没有有限 Decimal 下界可供选择。总运行时间为 `1800.489843642339 s`，峰值父子合计 RSS 为 `0.7346572875976562 GiB`，最低可用内存为 `96.6288833618164 GiB`；内存门未触发，失败不能归因于内存不足。

规范总 manifest SHA-256 为 `c7b7e42973c30778efb791e2369ec5dc60dd4c70c75db333bfb5d3e1ac8f4526`，总 execution SHA-256 为 `ef431921d46369d44cbe83ab593685c71349868a3be603b392d40e4d68fca109`。IPX/simplex execution SHA-256 分别为 `1691096160ab961efcc51b61de749672cad6e8caaf0f6750ae019a5ee1840a0e` 与 `957f7660904e82462c209402e08d573d40cbb95d031dbe7b48eb520c79353870`。服务器规范输出已下载至 `风光火+熔盐储热/数据采集/e0d43_offline_dual_certificate_recovery/`，9 个规范文件逐文件 SHA-256 与服务器一致，启动日志另存为 `launcher.log`。

Gate B 最终状态为 `no_strict_certificate`，`formal_lower_bound_eligible=false`、`selected_phase=null`、`hybrid_lower_bound_contract_permitted=false`、`technical_ranking_permitted=false`。该失败只说明两个冻结 dual 都未在既定 1800 s 内完成不变的高精度认证；它不证明 TES 不可行，不证明 BESS 更优，也不产生可行上界、容量、项目 TAC 或技术排序。D43 不得重跑或事后改变精度、时限、并行度和选择规则。若继续数值证书路线，必须另立新的结果前合同，例如数学等价但更快的严格证书算法、数值缩放/对偶修复，或新的严格分解路线；Hybrid 仍不得启动。
