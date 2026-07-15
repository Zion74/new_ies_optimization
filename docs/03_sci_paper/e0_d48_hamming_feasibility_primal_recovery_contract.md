# E0-D-48 全年 Hamming 可行性搜索与原成本上界恢复合同

状态：**第 1–11 节结果前合同已冻结；源码、Gate A 和正式批次均未启动**

适用范围：D46 唯一正式批次未获得任何原 MILP incumbent，且 D46 事后只读诊断已定位“逐变量取整不能形成一致离散轨迹”之后，在同一 2024 年 8784 h 原始 BESS、TES、Hybrid 规划 MILP 中恢复首个可审计 primal 状态。

日期：2026-07-15

## 1. 本关只回答什么

D48 只回答两个按顺序判定的问题：

1. 在不固定 D46 最大容量锚点、连续设计变量仍处于原模型既有边界内的条件下，能否通过完整二元轨迹的等权 Hamming 距离目标找到原 MILP 的第一个整数可行解；
2. 若找到，能否在重建的原模型中固定该完整二元轨迹、恢复原受控成本目标并自由优化全部连续变量，形成经独立残差审计的可行容量和工程数值上界。

D48 不求解技术排序，不改变任一物理、服务、成本或容量约束，不把 Hamming 目标解释为经济目标，也不把求解器超时解释为物理不可行。

## 2. D46 失败后的新证据

D46 正式总 manifest SHA-256 为 `8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9`，三架构状态均为 `no_candidate_incumbent`，上界恢复数为 0。事后只读诊断 bundle SHA-256 为 `c74a6943570690ace8573a0dee2f65aa763d0371854e01625337a46244a35b58`，没有调用求解器：

| 架构 | 约束违约数（`1e-7`） | 违约量之和 | 主要诊断 |
|---|---:|---:|---|
| BESS | 55,425 | 8,924.5576166 | CHP 燃料段编码、权重和启停轨迹不一致 |
| TES | 48,801 | 5,184,500.6698653 | HT 接收/送出模式主导违约幅值，CHP 轨迹主导条数 |
| Hybrid | 48,791 | 5,192,549.6563913 | 与 TES 相同 |

因此 D48 不再逐变量修补或扩大容量，而是让 MILP 在完整原可行域内共同决定一致的离散轨迹。D46 的固定最大容量锚点只是其候选子空间，不是原模型必须条件；D48 明确撤销这些固定，仅保留原模型已有容量边界。

## 3. 锁定输入、种子与模型身份

| 证据 | SHA-256 / 锁定值 |
|---|---|
| D40 full-year service | `1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95` |
| D40 Gate A manifest | `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577` |
| D41 Gate A manifest | `50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937` |
| D41 Gate B manifest | `bbc0638470859a58fe26a3166ec4825f455fd27671b7edf234b6e51557ee8aef` |
| D47 formal manifest | `8b74c4044854d18d5dffa6c2759bfe747455631e0347293d6a89c16d35276101` |
| D47 formal execution | `ed978c3607f080456576e35dede75c57e017150514e24160462a62566bf9c330` |
| D46 formal manifest | `8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9` |
| D46 BESS complete guide seed | `b69f4035deb5aa5f83a504e1e40347a23fa352b4104087bc017da6940c828b1f` |
| D46 TES complete guide seed | `d38004e6c3607cc2095c93def187de6d5300f5b9d9e97928872aaf6ce176e8e9` |
| D46 Hybrid complete guide seed | `9def0298195dbbebe477d9ff3b91f3b475082325eeea01dfc80c49930d532655` |
| D46 postmortem bundle | `c74a6943570690ace8573a0dee2f65aa763d0371854e01625337a46244a35b58` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| D41 binary inventory/fixing module | `c7f45f8c071bb92c6cf7576a76bed71b71e606b7239881cb8baac09b195d2f1e` |

正式服务继续固定为 2024 年 `8784 h`、基线热负荷、PCC `700 MW`、年送出电量 `4,035,354.738554194 MWh` 的平均功率等式和最大弃电 `339,569.90645758656 MWh`。代表期不得进入正式 D48。

原模型身份必须逐项复现：

| 架构 | 活动变量 | 活动约束 | 原始二元 | 二元名称 SHA-256 |
|---|---:|---:|---:|---|
| BESS | 597,318 | 527,053 | 79,057 | `ca8eb40a1859b80f4ed0c91ddad110dee7a28f55e8ce5bec475e7d12f85b3d92` |
| TES | 650,052 | 606,163 | 87,840 | `e092a5867b25d0b1effef7be1f48d27e4613fccf532bc0173347e06cba9ce628` |
| Hybrid | 685,194 | 667,662 | 96,625 | `7cb1636938cfcb26387e6739f009b73113aba1fbb5f91e0ead6f8c421decd3fb` |

任一输入哈希、变量/约束名称集、模型规模、二元清单、服务约束或原容量边界不一致即停止。D48 新增目标后只允许目标组件变化；原活动约束名称集合、行数和表达式哈希必须不变。

## 4. 可行性搜索的等权 Hamming 目标

对架构的完整 D41 原始二元清单记为 \(\mathcal B\)，D46 guide seed 中对应的精确 0/1 值记为 \(s_i\)。D48 暂时停用原成本目标，增加唯一目标

\[
\min H(z;s)=\sum_{i\in\mathcal B}|z_i-s_i|
=\sum_{i:s_i=0}z_i+\sum_{i:s_i=1}(1-z_i).
\]

该目标是线性的，所有二元变量等权，不添加辅助变量或新约束。三个 D46 guide 文件分别含 `79,057 / 87,840 / 96,625` 个 `original_binary` 行，值均精确为 0 或 1；同时保留其余有限连续值作为 MIP start。所有外部设计容量不再固定在 D46 最大锚点，而是在 `planning_model.py` 的原始有限边界内自由取值。

Hamming objective 仅用于提高首个一致整数轨迹的搜索概率。其值不是成本、上界、匹配度或论文性能指标。正式候选找到第一个全部列有限的 incumbent 后立即请求软中断；不继续优化 Hamming 距离。

## 5. 原成本修复与上界资格

若可行性搜索捕获 incumbent，则从锁定输入重新构建不含 Hamming 目标的原模型：

1. 按名称固定 D41 完整二元清单，要求无缺失、无额外、无分数值且名称 SHA-256 完全一致；
2. 不固定 D46 最大容量锚点，也不固定候选的连续容量；全部连续变量和容量在原边界内自由；
3. 恢复原受控成本最小化目标，求解一个固定二元的全年 LP；
4. 只有 solver primal、全变量/约束、服务、循环、容量、二元和目标分项审计全部通过，才形成 `audited_feasible_upper_bound_cny`。

该 LP 是 D48 唯一 repair。不得新增 Repair B、第二种容量锚点、局部分支或事后加权目标。合格目标沿用 D46 的 `Decimal.from_float()`、80 位精度与 `ROUND_CEILING` 向上舍入规则。它仍属于 `controlled_public_cost_sensitivity_not_formal_project_tac`，不是杨凌项目正式 TAC，也不是有理数精确证书。

## 6. 审计门

候选与 repair 必须分别归档，且 repair 同时满足：

- HiGHS 返回有限 primal，`num_primal_infeasibilities=0`，最大 primal infeasibility 不超过 `1e-8`；
- 独立遍历全部活动变量边界和活动约束，最大绝对违约不超过 `1e-7`，无非有限值；
- 完整原始二元精确为 0/1，固定值和候选快照逐名一致；
- 年送出平均功率等式残差不超过 `1e-8 MW`，弃电上限违约不超过 `1e-6 MWh`；
- 全年循环、CHP 转移/爬坡/燃料编码、逐时 PCC/热平衡、储能互斥、容量联动及 BESS 吞吐量约束通过；
- 全部容量有限、非负且处于原始边界；目标逐项重算与模型目标差不超过 `max(0.01 CNY, 1e-10×|objective|)`。

候选 incumbent 自身必须通过全变量有限、完整二元和原活动约束 `1e-7` 审计后才允许进入 repair；callback 存在不等于审计通过。

## 7. HiGHS 与资源合同

正式环境固定为 OpenBayes Linux、60 CPU、约 97 GiB、Python 3.10.18、Pyomo 6.10.1、highspy 1.15.1，仅使用 HiGHS。正式架构顺序为 BESS→TES→Hybrid，每案独立进程组：

- `threads=12`，`random_seed=0`，`mip_feasibility_tolerance=1e-8`；
- `mip_heuristic_effort=0.20`；
- 启用 feasibility jump、RENS、RINS、root reduced-cost、shifting、ZI round 和 symmetry；`presolve=choose`；
- Hamming 候选软时限 `3600 s`，父进程硬墙钟 `3720 s`；
- 固定二元原成本 repair 父进程硬墙钟 `1500 s`；
- 单架构总硬墙钟 `5400 s`，正式总批次硬墙钟 `16200 s`；
- 子进程树 RSS 上限 `35 GiB`，父子聚合 `45 GiB`，主机可用内存不得低于 `30 GiB`；每 `5 s` 心跳，停止时先终止进程组、等待最多 `30 s` 后强杀，残留必须为 0。

上述选项已在本地 highspy 1.15.1 完成名称、类型和值回读验证；Gate A 必须在 OpenBayes 再做同版本回读。不得使用 Gurobi。

## 8. 状态语义与后续权限

单架构只允许以下结果：

| 状态 | 含义 |
|---|---|
| `audited_feasible_upper_bound_recovered` | 首个整数候选与固定二元原成本 repair 均通过全部审计 |
| `candidate_found_but_repair_failed` | 候选合格，但原成本 repair 未形成合格上界；候选仍不得当上界 |
| `engineering_mip_infeasible_under_original_bounds` | HiGHS 对未修改约束、原容量边界的 Hamming MILP 完整返回 `Infeasible`，无中断、无超时、无资源停止、无未决节点、无 primal；这是浮点工程求解状态，不是物理或有理数不可行证明 |
| `no_primal_status_closure` | 超时、资源停止、异常或没有合格 incumbent，且未满足完整 infeasible 状态门 |

总批次只有在三架构均为“审计上界已恢复”或“原边界下工程 MIP infeasible”时，才可标记 `three_architecture_primal_status_closed=true`。只有三架构均恢复上界，才允许另立结果前 gap 收缩合同；任一 infeasible 或未闭合都继续阻断 E2–E4 技术排序。无论何种结果，`formal_project_tac_ready=false`、`technical_ranking_permitted=false`。

## 9. Gate A

任何正式 8784 h 求解前，源码和测试必须先独立提交并与 OpenBayes 逐字节同哈希。Gate A 至少包括：

- 人工小 MILP 验证 Hamming 代数、完整等权清单、原目标停用/恢复及首 incumbent 捕获；
- 缺失/额外/分数/非有限 seed、错误二元名称哈希、错误 guide SHA、错误模型身份和错误服务全部拒绝；
- 证明移除 D46 容量固定后，容量仅恢复原边界，原活动约束名称集、行数和表达式哈希不变；
- OpenBayes highspy 1.15.1 对第 7 节全部选项零错误回读；
- 24 h BESS/TES/Hybrid 三路径实际调用 HiGHS，至少各形成一个经原模型重建审计的 toy upper bound；
- 正式 8784 h 只做 build-only 身份、guide 哈希、二元精确值和原容量边界审计，不启动正式候选或 repair；
- 父进程硬墙钟、心跳、资源门、进程组终止、callback 软停止及活动残留为 0 的回归通过；
- D40–D48 定向回归、全包回归、Ruff 和 `py_compile` 零失败、零跳过；Gate A manifest 必须记录 `formal_optimization_invoked=false`。

Gate A 通过只开放第 10 节唯一正式批次，不产生正式容量、上界或排名。

## 10. 唯一正式批次与输出

Gate A 本地归档目录预注册为：

`风光火+熔盐储热/数据采集/e0d48_gate_a/`

OpenBayes 正式输出目录预注册为：

`/root/e0-b-20260711-019f4f64/results/e0d48_hamming_feasibility_primal_recovery/`

本地正式副本目录预注册为：

`风光火+熔盐储热/数据采集/e0d48_hamming_feasibility_primal_recovery/`

三个目录在对应阶段启动前必须不存在。正式 D48 只允许一次 BESS→TES→Hybrid 总批次；前一架构结果不得改变后一架构的 seed、权重、选项、容差或墙钟。每案保存 guide/seed 身份、Hamming 模型审计、solver log、heartbeat、execution、候选快照、二元快照、repair、全审计和 SHA-256；总 manifest 绑定 Git commit、Gate A、D40/D41/D46/D47、输入、模型、全部产物及声明权限。

## 11. 禁止事项与停止规则

D48 禁止：修改原约束或容量上界；重新固定 D46 最大容量锚点；按架构设置不同 Hamming 权重；新增第二 seed、第二目标、fallback、IIS 修补、局部分支或事后容量试探；把 Hamming objective、D46 guide objective、LP bound、未审计 callback 或 solver dual 当作上界；把超时写成不可行；把浮点 `Infeasible` 写成物理证明；从单架构成功推导技术赢家；在证据回传、逐文件哈希和三层文档提交前启动 gap、E2–E4 或排名。

合同、源码/测试提交和 OpenBayes 同哈希 Gate A 全部完成前，不允许正式 D48。唯一正式总批次完成后不得按结果原样重跑；任何增强必须另立新的结果前合同。
