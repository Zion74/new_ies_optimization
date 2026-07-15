# E0-D-40 Gate A 正式证据包

状态：**Gate A 通过；Gate B 尚未实现或启动**

本目录是 OpenBayes 规范目录 `/root/e0-b-20260711-019f4f64/results/e0d40_full_year_compute_gate/` 的本地逐字节副本。正式执行使用真实 2024 年 8784 h 单循环块、D40 baseline 服务契约和四个独立 Python 构造进程；没有读取代表期输入，也没有创建或调用求解器。

## 文件说明

- `e0d40_full_year_service.json`：无代表期依赖的冻结服务契约；
- `service_execution.json`：服务文件生成侧车；
- `build_{no_storage,bess,tes,hybrid}.json`：四架构规范 build-only manifest；
- `build_*_execution.json`：平台、运行时间、峰值 RSS 和构造后可用内存侧车；
- `gate_a_manifest.json`：四架构结构、线性、资源和规模排序的规范汇总；
- `gate_a_execution.json`：Gate A 汇总侧车；
- `*.log`：对应命令的原始标准输出记录。

## 关键哈希

| 文件 | SHA-256 |
|---|---|
| `e0d40_full_year_service.json` | `1752dd232bc309592d165199a90a0c10fe56ac526cf91762e45139193aca6c95` |
| `service_execution.json` | `0008fe574a49c2b5a6a2f2696deebae22b7bbaa4794e155c7e638816fd6809a9` |
| `build_no_storage.json` | `535d75358dd20ada888ee56f687ab7ecf31132bea28fd7ec82601a6c45a7f3b9` |
| `build_no_storage_execution.json` | `618aaabc7b4d52dc4ef417981f3be2cf8879fac8b4660f827a2ff23e29a31166` |
| `build_bess.json` | `1c1f775a9bb7d00968e2186ac78c77ecd4109800db4fd8e6b041e7ca4c411baf` |
| `build_bess_execution.json` | `4b82c192bb966b62e605ceb244bcf9a459b7fa165ee5dbbdbb35a14366da5358` |
| `build_tes.json` | `2f12564fb9b261b27f10ca3a859ffc317923b2f41d80027062bc5862df952816` |
| `build_tes_execution.json` | `4d71cf63162365d5c528734f19a842a6e450560ab1e73c36e2dc354d6fc4a9b8` |
| `build_hybrid.json` | `063a8081d9bce3f675d00e2c094df6e4c2e25371b1e44ce10d8e21c265b7b4f9` |
| `build_hybrid_execution.json` | `b551958a76372cc9b6974afce4454d63adfdb6fc7349b037b7ca27680d38331b` |
| `gate_a_manifest.json` | `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577` |
| `gate_a_execution.json` | `30dceb1aa52acbc051ae735c287c5506334aeda268de50671cce90268e86c223` |

## 验收摘要

| 架构 | 活动变量 | 二元变量 | 活动约束 | 非线性组件 | 峰值 RSS / GiB | 构造后可用内存 / GiB |
|---|---:|---:|---:|---:|---:|---:|
| No storage | 562,176 | 70,272 | 465,554 | 0 | 0.482 | 96.863 |
| BESS | 597,318 | 79,057 | 527,053 | 0 | 0.518 | 96.833 |
| TES | 650,052 | 87,840 | 606,163 | 0 | 0.610 | 96.735 |
| Hybrid | 685,194 | 96,625 | 667,662 | 0 | 0.645 | 96.705 |

四案均满足 20 GiB 单进程峰值 RSS 上限、40 GiB 构造后最低可用内存、8784 h 单全年循环、有限容量边界、容量联动和零非线性要求。OpenBayes 完整回归为 `462 passed in 33.82s`。本地下载后已逐文件与远端验哈，并重新检查 manifest—execution—服务引用链。

首轮构造因审计器把连续零容量 TES 误判为必须含安装二元而停止。该轮模型、日志和拒绝证据保留在服务器目录 `/root/e0-b-20260711-019f4f64/results/e0d40_full_year_compute_gate_pre_audit_fix_20260715/`，不进入本正式证据包。审计修订没有改变物理模型、服务、成本、容量边界或资源阈值。

本包只能证明全年模型可构造且资源门通过。`solver_invoked=false`，不得从中推导容量、成本、MIP gap、技术排序或杨凌项目技术赢家。
