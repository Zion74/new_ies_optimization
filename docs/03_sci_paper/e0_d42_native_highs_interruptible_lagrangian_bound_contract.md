# E0-D-42 原生 HiGHS 可中断全年 LP 与拉格朗日下界证书合同

状态：**第 1–11 节结果前合同已冻结；Gate A、Gate B 执行器实现门和 BESS R0 build-only 复核均已通过，TES R0 尚未启动**

适用范围：D41 Gate B 的 TES R0 收敛、终止与合法下界提取失败之后的严格下界恢复

日期：2026-07-15

## 1. 本关只回答什么

D42 只回答：在不改变 D40/D41 的真实 2024 年 8784 h 输入、物理模型、服务目标、容量边界和成本敏感性口径的前提下，能否使用原生 `highspy` 的可中断求解、基解检查点和独立拉格朗日审计，为 TES 与 Hybrid 全年松弛得到有限、方向正确、可复核的严格下界。

D42 不生成原 MILP 的可行上界，不执行容量排序，不恢复代表期，不宣布 BESS、TES 或 Hybrid 的技术赢家。即使三架构下界全部闭合，也只能允许另立新的全年可行修复合同；D41 Gate C/D 不会在 D41 名下重新开启。

## 2. 不可覆盖的既有结果

- D39 的代表期弃电率绝对误差为 `5.17618942467652` 个百分点，正式时间聚合路线未通过；
- D40 的单体 BESS 全年 MILP 在失效执行器下分类为 `monolithic_not_viable`，不等于物理不可行；
- D41 Gate A 已证明 BESS/TES/Hybrid 的 R0 原始二元均全部放松，R1 只剩 `1/0/1` 个拓扑二元，完整离散固定无遗漏；
- D41 BESS R0/R1 已形成合法下界，取 `1,144,950,604.8368804 CNY`；它不是原 MILP 可行上界、容量方案或项目 TAC；
- D41 TES R0 已把 `606,163 × 650,052`、`2,521,170` 非零元的 LP 预求解为 `439,018 × 509,289`、`1,806,011` 非零元，并进入 dual simplex；`720.462 s` 硬墙钟前没有完成求解器返回，内存不是瓶颈；
- D41 TES 日志中的中间 simplex objective 和 `Du` 信息没有经过求解完成、矩阵身份与独立证书审计，不得直接登记为下界；
- D41 的 TES R1、Hybrid、Gate C/D 均未启动，总状态保持 `no_strict_certificate`。

D42 不在 D39–D41 名下加周、改权重、放宽服务、延长旧墙钟或补跑旧 Gate。

## 3. 锁定输入、软件与模型身份

D42 逐字节复用 D40/D41 的规范输入和服务：

- `e0d40_full_year_service.json` SHA-256：`1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95`；
- D40 Gate A manifest SHA-256：`23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577`；
- D41 Gate A manifest SHA-256：`50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937`；
- D41 Gate B 总 manifest SHA-256：`bbc0638470859a58fe26a3166ec4825f455fd27671b7edf234b6e51557ee8aef`；
- 8784 h 真实热需求、风光、气温、价格、10% 绝对弃电上限 `339,569.90645758656 MWh` 与年度 PCC 外送目标 `4,035,354.738554194 MWh`；
- D41 使用的 `planning_model.py`、CHP/BESS/TES 组件、成本账本和 R0/R1 域变换。除新增 D42 适配器、证书器和测试外，上述模型构造源码不得改变。

规范执行端锁定为 OpenBayes 的 Python `3.10.18`、Pyomo `6.10.1`、`highspy / HiGHS 1.15.1`。求解器仍只有 HiGHS。正式结果必须记录 wheel 版本、HiGHS git hash、平台、输入/代码哈希和全部原生选项。

原始 LP 和显式预求解 LP 均使用确定性矩阵指纹。指纹至少覆盖目标方向与 offset、列成本、列上下界、列类型、行上下界以及 CSC 矩阵的 `start/index/value` 数组；数组的数据类型、长度和字节序也进入 SHA-256。任一检查点只有在预求解 LP 指纹逐字节一致时才允许加载基解。

## 4. 原生 HiGHS 能力采用边界

HiGHS 官方文档确认：

- simplex 和 IPM interrupt callback 可以把 `user_interrupt` 传回求解器，使其受控返回；
- `highspy` 可以读取 `HighsSolution`、`HighsBasis`、`HighsInfo`、原始/预求解 LP，并可设置基解继续 simplex；
- IPX/IPM 可以求解 LP，simplex 总会形成基解，IPM 可通过 crossover 形成基解；
- PDLP 当前不产生基解，官方同时提示一阶 LP 求解的精度与 KKT 风险。

因此 D42 正式路线只使用 `solver=ipx` 和 `solver=simplex`。`pdlp`、`hipdlp`、缺少 `highspy-extras` 时回退到 simplex 的 `hipo`、Pyomo Appsi 的 return-only bound 以及从日志文本摘录 objective 均不得生成正式证书。

技术依据：

- <https://ergo-code.github.io/HiGHS/dev/callbacks/>
- <https://ergo-code.github.io/HiGHS/dev/solvers/>
- <https://ergo-code.github.io/HiGHS/dev/guide/kkt/>
- <https://ergo-code.github.io/HiGHS/dev/options/definitions/>
- <https://ergo-code.github.io/HiGHS/dev/interfaces/python/>

D41 第 3 节的 Energy / Applied Energy 分解文献边界继续有效；D42 本身没有新增论文级技术主张，因此不新增低等级期刊来源。

## 5. 独立拉格朗日下界资格

对显式冻结的连续 LP：

\[
z^*=\min_x\{c^Tx+o:\; l\le x\le u,\; L\le Ax\le U\},
\]

从原生 HiGHS 状态取得任意有限行乘子向量 (y)。为避免无穷行界造成无效项，先确定性修复：

- 只有有限下界的行取 \(\bar y_i=\max(y_i,0)\)；
- 只有有限上界的行取 \(\bar y_i=\min(y_i,0)\)；
- 两侧均无限的行取 0；
- 两侧均有限的区间行和等式行保留原值。

令

\[
r=c-A^T\bar y.
\]

则以下值是原 LP 的拉格朗日下界：

\[
L(\bar y)=o
+\sum_i\min(\bar y_iL_i,\bar y_iU_i)
+\sum_j\min(r_jl_j,r_ju_j).
\]

含无穷界时只使用与乘子/残差符号相容的有限端点；若某一列所需端点仍为无穷，则该快照不产生有限证书。该公式直接对冻结矩阵、目标和上下界复算，不要求原始 primal 已可行，也不把 `solution.value_valid` 等同于 primal feasibility。

正式证书针对显式 `getPresolvedLp()` 返回的 LP 计算；D42 把版本锁定的 HiGHS presolve 作为与 D41 相同等级的受信求解器等价变换，要求其状态、原始/预求解指纹、目标方向和 offset 全部落盘，不允许任何作者自定义删行、聚合或近似。若 presolve 报错、状态不明或预求解 LP 无法通过结构审计，则不得把其下界传播回原 LP。

正式计算采用不少于 80 位十进制定向舍入区间。所有 double 输入先按其精确二进制浮点值转换，乘法、加法和 (A^T\bar y) 分别向下/向上扩张；证书只取最终区间的下端点。普通 double 重算只作交叉诊断，不决定资格。原生 `dual_valid`、`dual_solution_status`、KKT 指标和 solver objective 必须保存，但不能替代上述独立计算。

正式证书还必须同时通过：

- LP 指纹、目标方向和 offset 一致；
- (y) 长度等于行数且全部有限；
- 输出区间有限、下端不大于上端；
- 最优终止时，拉格朗日下端不超过 primal objective，且两者差异与保存的 KKT/舍入区间相容；
- 人工破坏矩阵、目标、行乘子长度、无穷端点或哈希时审计器拒绝。

任何只满足 HiGHS `1e-7` 容差、但不能通过定向舍入复算的数值，只能标记 `native_state_without_certificate`。

## 6. Gate A：实现、包含关系与中断测试

Gate A 不求解正式 8784 h 案例，只完成：

1. Pyomo → 原生 `HighsLp` 的确定性适配、变量/约束映射和矩阵指纹；
2. 显式 `presolve()`、`getPresolvedLp()` 与第二个 `Highs` 实例的隔离求解；正式求解实例必须设置 `presolve=off`，避免二次预求解改变证书矩阵；
3. simplex/IPM callback 的受控中断、结果落盘和父进程硬墙钟；
4. simplex 基解保存、同指纹恢复和继续迭代；
5. 第 5 节拉格朗日证书器及定向舍入实现；
6. 原模型、预求解模型、solver state、basis、certificate 与 execution sidecar 的哈希链。

构造测试至少覆盖：

- 最优 LP 的证书不超过已知最优值；
- dual simplex 在 primal 仍不可行时中断，仍可形成不超过已知最优值的有限下界；
- IPX 中断状态只能由独立公式决定接受或拒绝；
- 等式、双边行、单边行、自由行、固定列、单边列、objective offset 和无穷端点；
- 故意加入符号不相容乘子、非有限值、损坏指纹和错误 objective 时拒绝；
- 同一预求解矩阵的 simplex 检查点恢复有效，异指纹基解拒绝；
- 原始 LP 与预求解 LP 在一组有解析解的小模型上最优值一致。

Gate A 还必须对 D41 的结构锁做 build-only 复核：TES 的 R0 与 R1 均为纯 LP 且矩阵指纹一致；Hybrid R1 恰有一个 BESS 安装二元，可由固定为 0/1 的两个 LP 完整覆盖。任一结构断言不成立即停止，不得临时修改算法。

Gate A 的源码、测试、规范结果必须先独立提交，之后才允许正式 Gate B。

## 7. Gate B：单个全年 LP 的固定算法

每个待求 LP 只构造一次原始矩阵，显式预求解一次，并冻结预求解 LP 指纹。算法顺序固定如下。

### B1：IPX 路线

- `solver=ipx`；
- `presolve=off`；
- `run_crossover=on`；
- `threads=12`，随机种子 `0`；
- primal/dual feasibility tolerance、residual tolerance 和 optimality tolerance 均为 `1e-7`；
- 内部/回调软墙钟 `900 s`，父进程硬墙钟 `1020 s`；
- `user_objective_scale=0`、`user_bound_scale=0`，不在 D42 中搜索缩放参数。

IPX 若达到最优，仍须通过第 5 节证书器。若未达到最优但返回有限行乘子，也只按独立拉格朗日下端登记；没有有限证书则进入 B2。IPX 达到经独立审计的最优时，B2 可停止，因为该 LP 已闭合。

### B2：可恢复 dual simplex 路线

- `solver=simplex`、`simplex_strategy=1`；
- `presolve=off`，`simplex_scale_strategy=2`；
- `threads=12`，随机种子 `0`；
- 同一组 `1e-7` 容差；
- 最多四个连续检查点，每段 callback 软墙钟 `600 s`、父进程硬墙钟 `720 s`；
- 第二至第四段只加载上一段同指纹的有效 basis；每段均重新导出行乘子、basis、KKT 和独立证书；
- 只有经审计的最优状态允许提前停止；否则四段全部执行，不根据 objective 走势临时加段、减段或换策略。

若 IPX 未最优但产生有效 basis，则 B2 只在 basis 指纹和有效性审计通过时使用该 basis；否则从 simplex 默认基开始。所有通过审计的证书取最大值作为该 LP 的正式下界。父进程硬杀导致当前快照缺失时，只能保留此前已落盘且通过哈希审计的检查点。

单个 LP 的总父进程墙钟上限为 `4500 s`，包括构造、显式预求解、B1、B2 和证书复算；达到总上限后不得继续。

## 8. 正式架构顺序与 R1 处理

正式顺序固定为：

1. build-only 重建 BESS R0，复核 D40/D41 输入、模型构造源码、域、规模和新矩阵指纹；全部锁一致时复用 D41 的 `1,144,950,604.8368804 CNY`，不重复正式求解；
2. TES R0 按 Gate B 求解；Gate A 证明 TES R0/R1 指纹一致后，同一证书同时覆盖两者；
3. 只有 TES 得到有限合法下界后才启动 Hybrid；先求 Hybrid R0；
4. Hybrid R1 的唯一拓扑二元固定为 0 和 1，分别形成 LP。只有两支都有有限合法下界，或某支得到全局不可行证明时，才用两支下界的最小值作为 R1 下界；Hybrid 最终取 R0 与合格 R1 下界的最大值。

R0 是原 MILP 的合法松弛。因此 Hybrid R1 分支失败不会撤销已通过的 R0 下界，但失败分支不得贡献 R1 下界。TES 没有证书时按最弱案例规则停止，不启动 Hybrid。

## 9. 执行、资源和产物

- OpenBayes 是规范执行端，本地只做单元/小型构造回归；
- 不与其他正式大算例并发；
- 每 `5 s` 保存 phase、PID、elapsed、求解器状态、迭代数、进程树 RSS、父子合计 RSS、主机可用内存与最近有效检查点；
- 单求解进程树 RSS 不超过 `35 GiB`，D42 聚合 RSS 不超过 `75 GiB`，主机可用内存不得低于 `15 GiB`；
- callback 软中断后最多给 `120 s` 完成原生返回和证书落盘；父进程达到硬墙钟时先 `SIGTERM`，等待 `30 s` 后仍未退出再 `SIGKILL`；
- 原始大矩阵只保留一个规范二进制/压缩副本；日志、basis、solution、certificate、manifest 和 execution 均单独哈希；
- 凭据、密码和本地受限原始资料不得写入产物。

规范证据目录固定为：

- 本地：`风光火+熔盐储热/数据采集/e0d42_native_highs_lagrangian_bound/`；
- OpenBayes：`/root/e0-b-20260711-019f4f64/results/e0d42_native_highs_lagrangian_bound/`。

## 10. 预注册分类与后续权限

单 LP 分类：

| 分类 | 要求 |
|---|---|
| `certified_optimal_relaxation` | HiGHS 最优、primal/KKT 合格，且独立拉格朗日证书与最优目标相容 |
| `certified_finite_lower_bound` | 未证明最优，但至少一个中断快照形成有限、哈希一致、定向舍入合格的下界 |
| `native_state_without_certificate` | 有 solution/basis/log/KKT 状态，但第 5 节证书失败 |
| `no_strict_certificate` | 构造、资源、硬墙钟、哈希或数值失败，且没有此前有效检查点 |

架构下界只接受前两类。D42 总状态取 BESS、TES、Hybrid 的最弱一档。

- 三架构均至少达到 `certified_finite_lower_bound`：只允许另立 D43 原始全年可行轨迹与上界修复合同；仍不得技术排序或启动 E2–E4；
- 任一架构没有有限合法下界：D42 失败并停止，下一步只能另立数值缩放、对偶修复或具有严格主问题下界的分解合同；
- 原始 R0 被全局证明不可行时，才可按包含关系登记原 MILP 不可行；IPX/simplex 中断、某个 Hybrid 固定分支不可行或证书失败均不等于原问题不可行。

## 11. 禁止的结果依赖调整与 Agentic 边界

D42 正式结果产生后，不得在本合同名下：

- 更换 B1/B2 顺序、追加检查点、延长墙钟或按 objective 走势调参；
- 改用 PDLP、代表周、聚类日或删减真实小时；
- 改服务目标、容量边界、成本、容差、内部缩放或 presolve 规则；
- 把日志 objective、primal 不可行的 basis objective、`value_valid`、`dual_valid` 或 Appsi `lower_bound` 单独当证书；
- 把有限下界写成可行方案、容量、项目 TAC、最优解或技术赢家。

Agentic 只可核验哈希、选择已冻结的下一状态、监控资源、保存检查点、调用独立证书器并执行停止规则；不能修改模型、求解策略、时限、证书公式或判定阈值。

任何正式结果只能追加在第 11 节之后或写入独立结果记录，不得反向修改第 1–11 节。

## 12. Gate A 核心实现证据（不改写第 1–11 节）

2026-07-15 已实现 `e0d42_native_highs_certificate.py`、`e0d42_full_year_structure_gate.py` 及对应两份测试。四个文件 SHA-256 依次为 `3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298`、`6ed295cb5a7c577a6bc04182f6c199671e80ba178184afd478d3dcb9f6544718`、`b56cd5a3c524d18c4bdea2c59fea5209e3b39cb0eca22aeb8ed63e13ab2c9a8c` 与 `f0ed8ad3c148a3098e348f4d5954439098df318d8458189d0559feb006388ff1`，Windows 与 OpenBayes 副本逐字节一致。结构审计器在正式结果前由提交 `80b5b5c` 固定，并由提交 `781db23` 把价格合同改为 D40 同口径的目录树哈希。

本阶段已经关闭以下实现级风险：完整 `HighsLp` 数值指纹；NaN/倒置边界拒绝；Pyomo 6.10.1 到原生 HiGHS 1.15.1 的版本锁定翻译；显式一次 presolve；不少于 80 位 Decimal 定向舍入拉格朗日区间；单边无穷行乘子投影；所需列端点无穷时拒证；IPX/simplex callback 中断；同指纹 basis 恢复和异指纹提前拒绝；五案例标签/松弛/分支/D41 结构锁汇编。测试还暴露并修复了 HiGHS 进程级全局线程调度器复用问题：每个顺序阶段现在先阻塞重置调度器、逐项检查锁定选项，且 `HighsStatus.kError` 不得被包装为快照或证书。

测试证据为：Windows D42 定向 `17 passed`、D40–D42 定向 `54 passed in 4.22s`、全包 `508 passed in 66.17s`，Ruff 通过；OpenBayes D40–D42 定向 `54 passed in 0.65s`、全包 `508 passed in 34.22s`。这些测试只证明适配器、证书器和结构汇编器在解析/合成 LP 上方向正确，不是正式全年数值结果。

在正式结构结果产生前，TES R0/R1 的原始与预求解 LP 指纹一致性、Hybrid R1 唯一拓扑二元及 0/1 两支完整覆盖仍未闭合，因此当时不得启动 Gate B。该结果前状态由提交 `c238456` 固定；后续正式结果只追加在下节。

## 13. 正式 Gate A 全年结构结果

OpenBayes 按 TES R0、TES R1、Hybrid R0、Hybrid R1 `bess.installed=0`、Hybrid R1 `bess.installed=1` 的固定顺序独立重建五个 8784 h 案例。五案均通过 D40/D41 输入、模型规模、完整二元清单、线性、版本和原始/预求解 LP 审计；只调用显式 presolve，`optimization_invoked=false`。

- TES R0/R1 原始 LP 均为 `606,163 × 650,052`、`2,521,170` 非零元，指纹均为 `c479a3bc96e4431534ada769e1aef209573f1e83192e07f24a38858efcce3a17`；
- TES R0/R1 presolve LP 均为 `439,018 × 509,289`、`1,806,011` 非零元，指纹均为 `c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5`；
- Hybrid R0 原始 LP 为 `667,662 × 685,194`、`2,688,087` 非零元，presolve 后为 `495,630 × 539,546`、`1,985,956` 非零元；
- Hybrid R1 唯一拓扑变量严格为 `bess.installed`，固定为 0 与 1 的两支均通过，原始和 presolve 的非连续列计数均为 0；
- 五案进程峰值 RSS 为 `2.288–2.407 GiB`，案例结束后可用内存均约 `95.8 GiB`，资源门无压力。

五个案例 JSON、汇总 manifest 与 execution sidecar 已同步到 `风光火+熔盐储热/数据采集/e0d42_native_highs_lagrangian_bound/`。`structure_manifest.json` / `structure_execution.json` SHA-256 为 `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1` / `694c794a7a6fa1bb3228d5ee8714120efc7ef0aa6ff74a48eefe197161eef6ab`；本地/远端逐文件同哈希，本地只读重汇编与规范 manifest 完全相等。

Gate A 总状态为 `gate_a_structure_passed`，`formal_gate_b_permitted=true`、`technical_ranking_permitted=false`。这只允许实现、回归并独立提交第 7–9 节的正式父进程执行器；当前仍没有 D42 下界、容量、成本、gap 或技术排序，Gate B 不得在执行器提交前启动。

## 14. Gate B 执行器实现门

正式数值结果产生前，提交 `271d473` 固定模型无关的父进程执行器，提交 `60b1fdb` 将其绑定到 D40/D41 全年模型与正式架构顺序，提交 `23bf966` 只修复双端证据路径测试。新增源码与测试 SHA-256 为：

- `e0d42_gate_b_executor.py`：`c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51`；
- `e0d42_gate_b_formal.py`：`a2ba832e51a227b3ad9e3c3484ffe958ca1df39442555dfd397a4330666ca53e`；
- `test_e0d42_gate_b_executor.py`：`6e745b9965b8aa9c3cac9b2fa65da92a53af1eecb6595521d4e0314361b483de`；
- `test_e0d42_gate_b_formal.py`：`804685d3907fc51151eff7ac1a2a098fa75544dd39c69bffe11cc198468254bd`。

四个文件本地/OpenBayes 逐字节一致。执行器现已固定：确定性压缩 LP/solution 归档、IPX 加四段 simplex 计划、12 线程与全部 `1e-7` 容差、80 位证书、同指纹 basis、5 s 心跳、父进程硬墙钟、30 s 终止宽限、进程树/聚合 RSS 与主机内存门、单 LP 4500 s 总墙钟、逐产物哈希复审及最强合法证书选择。正式驱动器固定 BESS R0 build-only 复核、TES R0、Hybrid R0、Hybrid R1 `bess.installed=0/1` 的准入顺序，并按“分支取最小、R0/R1 取最大”汇编 Hybrid 下界。

Windows D40–D42 定向回归为 `58 passed in 5.48s`，全包为 `519 passed in 92.69s`；OpenBayes 定向回归为 `58 passed in 0.74s`，全包为 `519 passed in 34.55s`，Ruff 通过。上述结果只证明执行基础设施与准入逻辑，不是正式全年数值结果。当前仍没有 D42 有限下界、容量、成本、gap 或技术排序；下一步只允许先执行 BESS R0 build-only 与 D41 下界复核，通过后才可启动 TES R0 的 B1/B2。

## 15. Gate B BESS R0 build-only 与下界复核

OpenBayes 在独立子进程中重建 BESS R0，复核 D40/D41 输入、`597,318` 个活动变量、`527,053` 条约束和 `79,057` 个原始二元；R0 后剩余二元为 0。原始 LP 为 `527,053 × 597,318`、`2,187,237` 非零元，指纹 `ccd2600e8050e7b702a9badb610de64f37420620161411d486913d8d3346a9f0`；presolve LP 为 `390,252 × 451,527`、`1,592,820` 非零元，指纹 `ea9e0d34f4b7c1c0aa49c4dcd5b86f89b26a95542b589220f0783d4d70191286`。

D41 BESS manifest 独立重汇编与规范文件完全相等，SHA-256 为 `ed4fcf7d08ab236b678f787c777903d7905197b1262d820371c93f9aef76cfc7`，因此按第 8 节复用严格下界 `1,144,950,604.8368804 CNY`。本阶段 `optimization_invoked=false`；父进程运行 `121.434 s`，峰值子进程树/父子合计 RSS 为 `1.917/1.939 GiB`，最低可用内存 `95.405 GiB`。

规范 result/execution SHA-256 为 `ae30997a4dcf4fb3ed599ff17b9f5bb1238d66ad4eda677312e91a69bd4f5d36` / `280f9b4ed194af82029b2e43c1a3f7d96f96428efe29a9f18fa836cba739a3b4`，本地/远端逐文件同哈希，本地父进程前置证据重审通过。该结果只关闭 BESS 前置复核，不产生容量、可行上界、项目 TAC、gap 或技术排序；下一步只允许启动 TES R0，TES 没有有限合法证书时不得启动 Hybrid。
