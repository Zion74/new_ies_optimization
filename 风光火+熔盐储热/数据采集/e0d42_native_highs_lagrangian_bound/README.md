# E0-D-42 Gate A 全年 LP 结构证据

状态：`gate_a_structure_passed`

日期：2026-07-15

本目录保存 D42 正式 Gate A 的 5 个 clean-process build-only 案例、汇总 manifest 与 execution sidecar。所有案例均复用 D40/D41 的真实 8784 h 输入、服务、容量边界和公开成本敏感性口径，只执行模型构造、D41 域松弛、Pyomo→原生 `HighsLp` 翻译、完整矩阵指纹和一次显式 HiGHS presolve；`optimization_invoked=false`。

## 核心判定

- TES R0/R1 原始 LP 指纹均为 `c479a3bc96e4431534ada769e1aef209573f1e83192e07f24a38858efcce3a17`；
- TES R0/R1 presolve LP 指纹均为 `c2049cacd4b32aef3206998d2d47e792c4ad024aa72c80eaba9722b312fa5da5`；
- Hybrid R1 唯一拓扑变量为 `bess.installed`，固定值 `0/1` 两支均通过且均为纯 LP；
- 五个原始/预求解模型的非连续列计数均为 0；
- `structure_manifest.json` SHA-256 为 `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1`；
- 本地下载件与 OpenBayes 逐文件同哈希，本地只读重新汇编与规范 manifest 完全相等。

因此 `formal_gate_b_permitted=true`，但 `technical_ranking_permitted=false`。固定墙钟/心跳/证书执行器与正式顺序驱动器已由提交 `271d473`、`60b1fdb`、`23bf966` 完成，并在 Windows/OpenBayes 达到同哈希 `519 passed`。本目录仍没有 LP 下界、MILP 可行上界、容量方案、项目 TAC、gap 或技术赢家；下一步只先执行 BESS R0 build-only 复核，通过后才允许启动 TES R0。

## 文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `structure_tes_r0.json` | `4e65f31f1736ba6e089373c948758bda065063aebeade672ca4ef4efea877995` |
| `structure_tes_r1.json` | `6593646c0750af1707fdf549a9818894486084f3befb6da6ee7c714c937dfa1c` |
| `structure_hybrid_r0.json` | `0923ae65d123e29691ff794828dfa9f2228ea81fbc93608bde0ccd914c23315b` |
| `structure_hybrid_r1_bess0.json` | `5bf41e2e91a3d7fa42cd6609cab7059625bf9e9ece829ca17980a58bd05068aa` |
| `structure_hybrid_r1_bess1.json` | `bfa701131670ac3eeabfd5dbc403d56f54556ac7891520ef70769a42253196d3` |
| `structure_manifest.json` | `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1` |
| `structure_execution.json` | `694c794a7a6fa1bb3228d5ee8714120efc7ef0aa6ff74a48eefe197161eef6ab` |
