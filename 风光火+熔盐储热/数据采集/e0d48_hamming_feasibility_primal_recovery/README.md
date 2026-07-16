# E0-D-48-R1 正式批次阶段证据

更新时间：2026-07-16

远端正式目录：

`/root/e0-b-20260711-019f4f64/results/e0d48_hamming_feasibility_primal_recovery/`

本目录目前是仍在运行的 D48-R1 唯一正式总批次的**阶段性本地副本**。截至本次同步，BESS/TES 候选阶段已经结束，Hybrid 候选阶段仍在运行，远端尚无 `formal_manifest.json`。批次完成后必须继续下载 Hybrid 和总 manifest，并重新生成完整逐文件哈希清单。

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

## 主张权限

本阶段不产生候选解、repair、容量、可行上界、gap、项目 TAC 或技术排序。`formal_project_tac_ready=false`、`technical_ranking_permitted=false`。在总批次和 `formal_manifest.json` 完成前，本目录不能当作 D48 最终证据包。

BESS/TES 各四个阶段文件与远端逐文件 SHA-256 一致，见 `SHA256SUMS.txt`。两个 0 字节 solver log 均由清单哈希记录；Git 不单独保存空文件。
