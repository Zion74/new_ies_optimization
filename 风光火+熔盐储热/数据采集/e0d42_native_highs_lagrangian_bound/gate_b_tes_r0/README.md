# E0-D-42 Gate B TES R0 正式证据

状态：`no_strict_certificate`

日期：2026-07-15

本目录保存 D42 唯一一次正式 TES R0 全年执行的完整证据。远端 20 个文件已全部下载，并与 OpenBayes 逐文件通过 SHA-256 核验。该执行复用 D40/D41 的 2024 年 8784 h 输入、服务、容量边界和公开成本敏感性口径；没有改变模型、容差、缩放、presolve 或墙钟。

## 结构与准备

- 原始 LP：`606,163 × 650,052`，`2,521,170` 个非零元，SHA-256 `c479a3bc96e4431534ada769e1aef209573f1e83192e07f24a38858efcce3a17`；
- presolve LP：`439,018 × 509,289`，`1,806,011` 个非零元，SHA-256 `c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5`；
- R0 已放松全部 `87,840` 个原始二元，剩余非连续列为 0；
- 压缩 LP 归档 SHA-256：`dd362f179fd00052ecbca4c25d5d8d285811fbdd5700fa2d4adb49a2f7626776`；
- 准备阶段运行 `146.307 s`，峰值子进程树/父子合计 RSS 为 `2.167/2.190 GiB`，最低可用内存 `95.157 GiB`，资源门通过。

## 正式阶段结果

- IPX 在软中断时完成 31 次 IPM 迭代；求解器返回后开始生成 80 位严格证书，但未在 `1020.418 s` 父进程硬墙钟内完成。没有落盘 result、certificate 或 basis，仅保留通过哈希审计的 solution 快照；
- dual simplex 第 1 段在软中断时完成 `315,298` 次迭代；求解器返回后同样进入证书计算，但未在 `720.313 s` 父进程硬墙钟内完成。没有落盘 result、certificate 或 basis；
- 因第 1 段没有合法 basis，simplex 2–4 按合同未启动；
- 两阶段峰值子进程树 RSS 分别仅 `0.706/0.914 GiB`，最低可用内存分别为 `96.596/96.390 GiB`。失败不是内存耗尽，而是合法证书未在冻结硬墙钟内生成；
- 案例总运行 `1894.218 s`，最终 `formal_lower_bound_eligible=false`、`technical_ranking_permitted=false`。

## 结论边界与停止决定

D42 在 TES R0 处失败并停止，Hybrid 未启动。当前只保留 D41/D42 已复核的 BESS 严格下界 `1,144,950,604.8368804 CNY`；TES 和 Hybrid 没有有限合法下界。因此本结果不证明 TES 不可行，不证明 BESS 优于 TES，也不生成原 MILP 可行解、容量、项目 TAC、gap 或技术排序。任何后续恢复只能另立结果前合同，不能在 D42 名下延长墙钟或事后改变数值规则。

## 文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `case_execution.json` | `49e2e21445c67a233ed2bc205a8266351ae800b566d0f89cbfa7883a059efc51` |
| `case_manifest.json` | `cacd6cc2e32e2b8849398db4b75afa835a4796310e404e3301099c3942261944` |
| `lp_execution.json` | `621bc909b9fe6d7af759c96e4e83ea92c4a4f67ffd6a4255825ea8ace08c2fe7` |
| `lp_manifest.json` | `23b10bd00abde649924f8f80901292188c60bf3a54d5dd2547ed60a44209fd84` |
| `phase_ipx_execution.json` | `43bd8bb93120b917cf4a62433b2ab99ea349df7dfe5664c54ca9822febd4a206` |
| `phase_ipx_heartbeat.ndjson` | `33f9385026c5fec0fa5cd46b6bc2c0bdae796561e1b7099f9e9f5275b877521b` |
| `phase_ipx_progress.json` | `015f3e7253058e6c31e9dc60189413041822ceee11014077b5f1ddbb67c5adc5` |
| `phase_ipx_solution.bin.gz` | `d56109dabfc599ff996771924bc78f11b85c90f1dec001fd90edc9766fa5bfc6` |
| `phase_ipx_solver.log` | `3c6ee5a69a5f4fbb4590f3b6b99b7c6329c6322073d2479fa46a791da73ed175` |
| `phase_simplex_1_execution.json` | `c872fbd63a72fc0f6b733220b86a57a9e2f75fbfe4e46204ef8586899317a7c1` |
| `phase_simplex_1_heartbeat.ndjson` | `fa000cd3b7cc5a8563e559893a0b5d666d51d07adb7e50232a553ab7c3a53aab` |
| `phase_simplex_1_progress.json` | `fea224b538e5a349297dcedb03a3b40f84755a1a2a20dd19de4dc09cba6f3acc` |
| `phase_simplex_1_solution.bin.gz` | `bec595dfbc6b878659f588ed100d08c7368e55e4d89f91bafa22e49a9163b58b` |
| `phase_simplex_1_solver.log` | `da62c06847db4063fcbdac74be13fb7760e8e2c570da23ff554acb1c3ecbebde` |
| `prepare.log` | `1a65086ee753b65530f81231975d0937893a8a8eb93387efd0daa85f3faa400e` |
| `prepare_execution.json` | `8f6a7e222ea7f38a95461654936da705f9927e16b4b599be6e7e69156fb7983c` |
| `prepare_heartbeat.ndjson` | `8d3dad0dbfd3cd71fdc6fa1364b45abbd44c215a3bae739bbeb872c344a4663d` |
| `prepare_progress.json` | `7fa63bd1f1123caf8dbb67148296b1265f3cf3e04dac4eb1cfdb72e5af761db6` |
| `prepare_result.json` | `387f32ac3cff2ead6c5296073d5d51ee409e955093ba52717f5451cc0ceebe43` |
| `presolved_lp.bin.gz` | `dd362f179fd00052ecbca4c25d5d8d285811fbdd5700fa2d4adb49a2f7626776` |
