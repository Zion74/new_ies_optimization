# E0-D-46 唯一正式全年可行上界修复证据

本目录是 OpenBayes 上唯一一次 E0-D-46 正式总批次的完整本地副本。正式运行按结果前合同固定的 `BESS -> TES -> Hybrid` 顺序执行，使用 2024 年 `8784 h` 原始模型、HiGHS、每阶段 12 线程及冻结的容量、seed、容差和资源门。

## 最终状态

- 总状态：`partial_or_no_upper_bound_recovery`；
- 成功恢复审计可行上界的架构数：`0`；
- BESS、TES、Hybrid 均为 `no_candidate_incumbent`；
- 三架构均未进入 Repair A/B，`repair_selection=null`；
- 未形成正式可行容量、审计可行上界、保守 gap、项目 TAC 或技术排序；
- `formal_project_tac_ready=false`，`technical_ranking_permitted=false`；
- 正式批次结束后活动残留进程为 0。

连续 guide 仅用于构造候选 seed，不是可行上界：

- BESS R0 guide：`1,157,063,561.813816 CNY`；
- TES R0 guide：`386,559,421.67063665 CNY`；
- Hybrid R0 guide：`1,186,678,269.235802 CNY`。

TES 与 Hybrid 的结构化 seed 分别有 `48,801` 和 `48,791` 条行不可行，HiGHS 对固定离散值的 LP 明确判为 infeasible；随后原始 MILP 均跑满 `3600 s`，Primal bound 仍为 `inf`，没有完整 incumbent。BESS 的新 R0 seed也被明确拒绝，合同允许的 D41 BESS 回退 seed仍未产生 incumbent。

## 完整性

- 远端与本地 `formal_manifest.json` SHA-256：`8693722ad362b2f604f08b3ebd2bfa2c45f085e42c2ece6cf334c097db80afa9`；
- 清单声明的全部产物哈希：0 个缺失、0 个不匹配；
- 正式目录原始文件数：32；本 README 为本地归档说明，不属于远端正式 manifest；
- 正式总运行时间：`8820.16162651591 s`。

## 解释边界

本次结果证明的是：冻结的最大容量锚点与预注册确定性 seed 路线没有在正式时间预算内恢复任何原 MILP 可行 incumbent。它不能证明三种架构的物理模型不可行，也不能用三个连续 guide、MILP dual bound 或既有严格下界对技术进行排序。任何后续增强必须另立结果前合同，D46 不得按结果原样重跑。
