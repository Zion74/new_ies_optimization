# E0-D-40 Gate A 正式证据包

状态：**Gate A 通过；Gate B BESS 正式案为 `monolithic_not_viable`；D40 全年单体路线未通过**

本目录保存 OpenBayes 规范目录 `/root/e0-b-20260711-019f4f64/results/e0d40_full_year_compute_gate/` 的本地证据副本。Gate A 使用真实 2024 年 8784 h 单循环块、D40 baseline 服务契约和四个独立 Python 构造进程，没有读取代表期输入或调用求解器；Gate B 的预检与正式 BESS 文件另列在后文。

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

## Gate B BESS 接入预检

结果前提交 `03ad51a` 冻结预检口径、提交 `887b5a6` 实现独立 Gate B 适配器后，OpenBayes 完整回归为 `469 passed in 33.93s`。唯一一次 BESS 60 s 接入预检随后完成：

- `preflight_bess.json` SHA-256：`96c0d7eb3031063444b8fb5513d242baaa7c01d1b5ba7f61f60dc56447c15497`；
- `preflight_bess_execution.json` SHA-256：`8dabc0d22c9b2a4740af7ffdb144ab1c2f3c60195a855d623c28fad08252a227`；
- `preflight_bess.log` SHA-256：`32759ea62f69c6f54a85a27fe81603a51c57377835c282af80989ab63d7b50db`。

预检确认 597,318 个活动变量、79,057 个二元变量和 527,053 条约束与 Gate A 完全一致，HiGHS 使用 12 线程并在 60 s 返回 `maxtimelimit` 和有限 dual bound `-110,674,644.2397 CNY`，但没有 incumbent。父进程完成 250 次采样，子进程峰值 RSS `2.913 GiB`、父子合计峰值 `2.936 GiB`、最低可用内存 `94.417 GiB`，资源门通过。

该结果永久标记 `mode=preflight`、`formal_gate_b_eligible=false` 和 `classification=preflight_only`。其 dual、无 incumbent 状态、目标值和运行时间均不得进入正式 Gate B 判定，也不得用于修改 3600 s、0.1%/0.5% 阈值、求解顺序或模型。

## Gate B BESS 正式案失败

正式 BESS 按冻结的真实 8784 h、12 线程、随机种子 0、HiGHS `3600 s` 选项和 `0.1%` 目标 gap 启动。父进程持续完成 8,995 次资源采样，子进程/父子合计峰值 RSS 为 `2.916/2.939 GiB`，最低可用内存为 `94.416 GiB`，资源门通过。但执行器只把 `3600 s` 传给 HiGHS，没有在父进程实现独立硬墙钟；子进程在启动后约 75 分钟仍未返回，也没有生成结果 JSON、有限 incumbent、有限 dual 或不可行证明。

为避免软时限无限延伸，在 `2026-07-15T09:10:55.137712624+00:00` 对子进程组发送与执行器内部资源停止相同的 `SIGTERM`。父进程随后写出 `runtime_seconds=4527.394684`、`return_code=-15`、`status=resource_or_process_failure` 和 `effective_classification=monolithic_not_viable`。该终止保护不是把正式预算放宽到 75 分钟；它只记录父进程缺少硬墙钟的执行缺陷。

- `gate_b_bess_execution.json` SHA-256：`1e0cffdec05f650f6d2d06fe12f0061ba12480264df91702891806b099dd115a`；
- `gate_b_bess.log` SHA-256：`3a58eb0fde0c040dc0510ced82d5bddda72511a46216dc183c71ae1c5f94ade9`；
- `gate_b_bess_parent.log` SHA-256：`6247d8e2ca082a09c1de3485ca5e6a7f1685f77d61f55a4ac09c93c24186ed03`；
- `gate_b_bess_parent.pid` SHA-256：`37a4ce3584dd349bf1bce650a018c41f1e98ea12318f8735c28cbe5a3ac242e3`；
- `gate_b_bess_wall_clock_intervention.json` SHA-256：`76b0ff3bcc41f246e1dfac1096cbb97abc2fc8cc710e8e28600cb796547568c5`。
- `gate_b_route_decision.json` SHA-256：`c455df496a0134e2af23122f71f7d31aaefc016f74bcd2ecf50761a8ae90aed1`。

本案只证明当前单体全年执行路线不能在预注册墙钟内产生可审计 BESS 结果。它不证明 BESS 物理不可行，不提供容量、成本或技术排序。根据最弱案例规则，D40 已不能通过；TES/Hybrid 不在这次失效执行器下继续消耗正式单次机会，下一步必须另立带父进程硬墙钟和严格全年上下界的求解强化/分解合同。
