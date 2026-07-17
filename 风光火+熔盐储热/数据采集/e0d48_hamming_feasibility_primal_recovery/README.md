# E0-D-48-R1 正式批次阶段证据

更新时间：2026-07-16

远端正式目录：

`/root/e0-b-20260711-019f4f64/results/e0d48_hamming_feasibility_primal_recovery/`

本目录是 D48-R1 唯一正式正确路径总批次的**完整本地证据副本**。BESS→TES→Hybrid 已按冻结顺序全部结束，远端 launcher 和候选子进程均已退出，三个架构的活动残留进程数均为 0；`formal_manifest.json` 已回传并通过逐文件哈希复核。

## BESS 阶段事实

- 候选父级硬墙钟在 `3720.1756297620013 s` 触发，子进程以 `SIGTERM`、返回码 `-15` 受控结束；
- `bess_candidate.log` 为 0 字节，没有 `bess_candidate.csv.gz` 或 `bess_candidate.json`；
- `candidate_status=null`、`repair_status=null`、`audited_feasible_upper_bound_cny=null`；
- 峰值子进程树 RSS 为 `3.171466827392578 GiB`，峰值父子聚合 RSS 为 `3.195880889892578 GiB`，最低可用内存为 `94.14612579345703 GiB`；没有越过 35/45 GiB RSS 或 30 GiB 主机内存保留阈值；
- 执行记录因硬墙钟终止将 `resource_gate_passed` 记为 `false`，但没有发生 RSS 或可用内存门槛越界；
- BESS 活动残留进程数为 0，编排器随后按预注册顺序启动 TES；
- 架构 manifest 原始状态为 `candidate_process_or_resource_failure`。按 D48 合同第 8 节，其科学状态只能登记为 `no_primal_status_closure`，不能写成 BESS 不可行或工程 MIP infeasible。

## TES 阶段事实

- 候选父级硬墙钟在 `3720.5810301834717 s` 触发，子进程以 `SIGTERM`、返回码 `-15` 受控结束；
- `tes_candidate.log` 为 0 字节，没有 `tes_candidate.csv.gz` 或 `tes_candidate.json`；
- `candidate_status=null`、`repair_status=null`、`audited_feasible_upper_bound_cny=null`；
- 峰值子进程树 RSS 为 `4.5804290771484375 GiB`，峰值父子聚合 RSS 为 `4.6058349609375 GiB`，最低可用内存为 `92.7331771850586 GiB`；没有越过 35/45 GiB RSS 或 30 GiB 主机内存保留阈值；
- 执行记录因硬墙钟终止将 `resource_gate_passed` 记为 `false`，但没有发生 RSS 或可用内存门槛越界；
- TES 活动残留进程数为 0，编排器随后按预注册顺序启动 Hybrid；
- 架构 manifest 原始状态为 `candidate_process_or_resource_failure`。按 D48 合同第 8 节，其科学状态只能登记为 `no_primal_status_closure`，不能写成 TES 不可行或工程 MIP infeasible。

## Hybrid 阶段事实

- 候选父级硬墙钟在 `3720.8029388338327 s` 触发，子进程以 `SIGTERM`、返回码 `-15` 受控结束；
- `hybrid_candidate.log` 为 0 字节，没有 `hybrid_candidate.csv.gz` 或 `hybrid_candidate.json`；
- `candidate_status=null`、`repair_status=null`、`audited_feasible_upper_bound_cny=null`；
- 峰值子进程树 RSS 为 `5.578643798828125 GiB`，峰值父子聚合 RSS 为 `5.6042327880859375 GiB`，最低可用内存为 `91.7314567565918 GiB`；没有越过 35/45 GiB RSS 或 30 GiB 主机内存保留阈值；
- 执行记录因硬墙钟终止将 `resource_gate_passed` 记为 `false`，但没有发生 RSS 或可用内存门槛越界；
- Hybrid 活动残留进程数为 0；
- 架构 manifest 原始状态为 `candidate_process_or_resource_failure`。按 D48 合同第 8 节，其科学状态只能登记为 `no_primal_status_closure`，不能写成 Hybrid 不可行或工程 MIP infeasible。

## 总批次事实

- `formal_manifest.json` 状态为 `partial_or_no_upper_bound_recovery`，总运行时间 `11161.583798717707 s`；
- `successful_architecture_count=0`，三架构均无 candidate、repair 或 `audited_feasible_upper_bound_cny`；
- `rational_exact_feasibility_certificate=false`、`formal_project_tac_ready=false`、`technical_ranking_permitted=false`；
- architecture order、Gate A、正式输入及 12 个阶段文件哈希均由总 manifest 锁定；
- 总 manifest SHA-256 为 `ca0248805ce72d1b25dd69a0cf20c5c68dee8b60a5d0a2d575a192f3e8455165`。

## 主张权限

D48-R1 不产生候选解、repair、容量、可行上界、gap、项目 TAC 或技术排序。三架构只能分别登记 `no_primal_status_closure`；总批次状态不得改写为物理不可行、工程 MIP 不可行或技术平局。后续增强必须另立结果前合同，D48-R1 不得原样重跑。

远端目录的 13 个文件与本地逐文件 SHA-256 一致，见 `SHA256SUMS.txt`。三个 0 字节 solver log 均由清单哈希记录；Git 不单独保存空文件。
