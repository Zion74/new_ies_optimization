# E0-D-44 fork 并行 80 位拉格朗日证书合同

状态：**第 1–10 节结果前合同已冻结；尚未实现 D44，尚未执行正式 D44**

适用范围：D43 两个冻结 TES R0 对偶快照均通过准入，但单核 80 位 Decimal 证书计算在每个 child 的 1800 s 硬墙钟前未完成之后的数学等价并行恢复

日期：2026-07-15

## 1. 本关只回答什么

D44 只回答：在不重建模型、不调用优化器或原生求解器、不修改 D42 LP、D42 row dual 和拉格朗日下界公式的前提下，能否把逐列 80 位向外舍入计算按冻结分区并行化，从至少一个 D42 TES R0 快照形成有限、方向正确、可复核的严格下界。

D44 不是新的 LP/MILP 求解，不生成可行上界、容量、项目 TAC、gap 或技术排序。D44 形成的是一份新的分块向外舍入证书；它不声称逐位复现 D42/D43 的串行 Decimal 中间舍入端点，但必须证明每个分块和最终合并区间都包含同一冻结拉格朗日值。

## 2. 不可覆盖的既有结果

- D41/D42 的 BESS 严格下界为 `1,144,950,604.8368804 CNY`，只属于受控公开成本敏感性，不是原 MILP 可行解、容量方案或项目 TAC；
- D42 TES R0 presolve LP 为 `439,018 × 509,289`、`1,806,011` 个非零元；IPX 与 simplex 第 1 段 solution 归档都含完整 row dual，`dual_valid=true`；
- D43 已按冻结合同执行唯一一次正式离线复算。两个单核 child 均运行约 `1800.49 s` 后被硬墙钟终止，没有 result/certificate；总 manifest SHA-256 为 `c7b7e42973c30778efb791e2369ec5dc60dd4c70c75db333bfb5d3e1ac8f4526`；
- D43 状态永久保持 `no_strict_certificate`，不得重跑、延时或改变 D43 设置；
- 当前没有 TES/Hybrid 合法下界，也没有三架构可比的上界、容量、gap 或技术赢家。

D44 若成功，只新增来源明确的并行严格证书，不修改 D41–D43 的历史终态。

## 3. 锁定输入与身份链

D44 只读使用 D43 已核验的 D42 正式证据：

| 输入 | SHA-256 / 锁定值 |
|---|---|
| `case_manifest.json` | `cacd6cc2e32e2b8849398db4b75afa835a4796310e404e3301099c3942261944` |
| `case_execution.json` | `49e2e21445c67a233ed2bc205a8266351ae800b566d0f89cbfa7883a059efc51` |
| `lp_manifest.json` | `23b10bd00abde649924f8f80901292188c60bf3a54d5dd2547ed60a44209fd84` |
| `lp_execution.json` | `621bc909b9fe6d7af759c96e4e83ea92c4a4f67ffd6a4255825ea8ace08c2fe7` |
| `presolved_lp.bin.gz` | `dd362f179fd00052ecbca4c25d5d8d285811fbdd5700fa2d4adb49a2f7626776` |
| presolve LP fingerprint | `c2049cac42c4fa2198613dfe4807c5c17a8489420f90d27f4e97b8fa6b43dcc6` |
| IPX solution / execution | `d56109dabfc599ff996771924bc78f11b85c90f1dec001fd90edc9766fa5bfc6` / `43bd8bb93120b917cf4a62433b2ab99ea349df7dfe5664c54ca9822febd4a206` |
| simplex 1 solution / execution | `bec595dfbc6b878659f588ed100d08c7368e55e4d89f91bafa22e49a9163b58b` / `c872fbd63a72fc0f6b733220b86a57a9e2f75fbfe4e46204ef8586899317a7c1` |
| D42 BESS reuse result | `ae30997a4dcf4fb3ed599ff17b9f5bb1238d66ad4eda677312e91a69bd4f5d36` |
| D42 structure manifest | `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1` |
| D43 formal manifest | `c7b7e42973c30778efb791e2369ec5dc60dd4c70c75db333bfb5d3e1ac8f4526` |

D42 原证书器 SHA-256 `3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298` 和归档执行器 SHA-256 `c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51` 继续只读。D44 新模块和测试必须在正式输入读取前独立提交，并与 OpenBayes 逐字节同哈希。

## 4. 冻结数学算法

对每个快照分别执行以下固定步骤：

1. 完整复用 D43 的元数据、LP 指纹、数组集合/维度、`dual_valid=true` 与 finite row dual 准入；
2. 使用 `Decimal.from_float()` 精确接收所有 binary64 输入，固定 `precision=80`、下界 `ROUND_FLOOR`、上界 `ROUND_CEILING`；
3. 行乘子投影规则与 D42 完全相同：自由行置零；仅有有限下界的行拒绝负乘子；仅有有限上界的行拒绝正乘子；
4. 行界项仍按 D42 原顺序串行累加，得到共同的 `row_total_lower/upper`；
5. `509,289` 列固定切为 `24` 个按列号连续分块。第 `k` 块使用半开区间 `floor(k*n/24):floor((k+1)*n/24)`，`k=0..23`；不得按正式 dual 或运行时间动态重分区；
6. 每个 worker 在块内严格按升序列号执行 D42 的活动区间、残差区间、有限/无穷端点和列贡献规则，并从 Decimal 零开始累加块级 lower/upper；
7. 父进程等待全部 24 块成功，按 `chunk_id=0..23` 固定顺序，以同一 80 位向外舍入把块级区间加到行界区间；
8. 任一块异常、缺失、重复、重叠、越界或出现需要的无穷列端点时，该快照不合格；不允许只汇总已完成块；
9. 两个快照均必须尝试。至少一个合格时，按 Decimal 下界数值取较大者；完全相等时固定选择 IPX。两者都不合格时状态为 `no_strict_certificate`。

分块改变了舍入结合次序，因此 D44 不要求与 D42/D43 产生相同的最后一位；资格来自每次乘法、加减、块内累加和块间合并均向外舍入，且 24 块无缝覆盖全部列。

## 5. 实现与等价性 Gate A

正式 D44 前必须通过：

- 合成小 LP 上，D44 分块区间包含用 `fractions.Fraction` 对所有 binary64 输入计算的精确拉格朗日值；
- 同一合成输入在 `1/2/3/24` 块下都合格、区间相交且主张一致；
- D42 串行证书与 D44 分块证书在有界、单边无穷、自由行、投影、非法无穷端点和非有限 dual 案例上资格分类一致；
- 分区必须覆盖 `[0, num_col)` 且无缺口/重叠；完成顺序扰动不得改变规范 certificate；
- worker 异常、缺失块、重复块、错误 chunk id、父进程硬墙钟和资源停止均被拒绝；
- OpenBayes 必须确认 `fork` start method、24 worker 合成 smoke、进程树终止和输出哈希链；Windows 测试只验证纯核与编排逻辑，不把 Windows spawn 当作正式等价环境；
- 本地/OpenBayes 定向与全包回归通过，源码/测试同哈希并先提交。

Gate A 只使用人工 LP/dual，不读取两个正式 D42 solution，不生成正式 TES 数值。

## 6. 冻结执行与资源合同

正式环境固定为 OpenBayes Linux、Python 3.10.18、`Pyomo 6.10.1 + highspy 1.15.1`；不增加数值库或求解器依赖。执行固定为：

- IPX 与 simplex 两个 phase parent 并行；
- 每个 phase parent 使用 Linux `fork` 创建 `24` 个列块 worker，共 `48` 个计算 worker；
- `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`；
- 每个 phase 硬墙钟 `900 s`，总父进程硬墙钟 `1080 s`；每 `5 s` 写心跳和已完成块数；
- 每个 phase 进程树 RSS 上限 `20 GiB`，父子总 RSS 上限 `45 GiB`，主机可用内存不得低于 `30 GiB`；
- 触发停止时先终止整个 phase 进程组，等待 `30 s` 后才强杀；任何残留 worker 都使执行失败；
- D44 只允许一次正式执行，不因结果调整 worker 数、分块、精度、墙钟、快照集合或选择规则。

## 7. 输出与确定性

正式输出固定写入：

`/root/e0-b-20260711-019f4f64/results/e0d44_fork_parallel_lagrangian_certificate/`

每个 phase 输出规范 `certificate.json`、`result.json` 和 24 块的确定性审计摘要；运行时间、RSS、PID、完成时序和心跳只进入 execution sidecar。规范 certificate 固定按 chunk id 排序，登记每块列范围、非零元数、lower/upper、非法列数和内容 SHA-256。总 manifest 登记全部 D42/D43 输入、D42/D44 源码、phase certificate/result/execution 哈希和选择结果。输出目录必须事前不存在，编排器拒绝覆盖非空目录。

## 8. Gate B 资格与权限

- 至少一个 phase 的 24 块全部完成，形成有限 lower/upper、非负区间宽度且 `invalid_column_endpoint_count=0`：状态 `tes_lower_bound_recovered`；
- 两个 phase 都未形成完整合法证书：状态 `no_strict_certificate`；
- D42 structure manifest 已证明 TES R0/R1 的原始和 presolve LP 指纹相同，成功证书可覆盖 TES R1，但 D44 必须再次核验该 manifest；
- D44 成功只关闭 TES 下界缺口。Hybrid 仍需另立结果前合同，不得在 D44 名下启动；
- D44 失败后不得重跑。后续只能另立新的精确 dyadic/MPFR、数值缩放/对偶修复或严格分解合同。

## 9. 主张边界

无论 D44 成败，`optimization_invoked=false`、`native_solver_invoked=false`、`technical_ranking_permitted=false`。D44 不能生成或支持：原 MILP 可行上界、容量方案、项目 TAC、三架构 gap、TES 可行/不可行结论、BESS/TES/Hybrid 技术排序。

成功时允许的最强表述是：某个哈希锁定的 D42 TES R0 row dual，在同一冻结 presolve LP 上通过 24 块、80 位向外舍入拉格朗日审计，形成有限合法下界。失败时只能表述该并行证书路线在冻结资源合同内未形成严格证书。

## 10. 禁止事项与停止规则

D44 禁止：重跑 D42/D43、调用 HiGHS optimize、修改 row dual、读取日志 objective 代替证书、降低精度、按正式结果调分块或 worker 数、只汇总部分块、忽略失败 worker、启动 Hybrid、生成容量或技术赢家。

只有 Gate A 独立提交且 OpenBayes 同哈希通过后，才允许唯一一次 Gate B。Gate B 输出下载并逐文件哈希核对、三层文档同步和本地提交前，不进入任何 D45 或 Hybrid 路线。
