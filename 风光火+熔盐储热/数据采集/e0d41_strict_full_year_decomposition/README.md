# E0-D-41 Gate A 规范证据

状态：`gate_a_passed`

执行端：OpenBayes，Python 3.10.18，Pyomo 6.10.1；本阶段未创建求解器。

## 1. 结果摘要

| 架构 | 活动变量 | 原始二元 | R0 剩余二元 | R1 剩余二元 | 完整固定后未固定二元 | 加权小时 | 运行时间 / s | 峰值 RSS / GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BESS | 597,318 | 79,057 | 0 | 1 | 0 | 8,784 | 67.762 | 0.759 |
| TES | 650,052 | 87,840 | 0 | 0 | 0 | 8,784 | 76.311 | 0.865 |
| Hybrid | 685,194 | 96,625 | 0 | 1 | 0 | 8,784 | 81.217 | 0.907 |

R1 只保留时间不变的安装/端口拓扑二元。当前 TES 采用 D34 已冻结的连续零容量策略，没有时间不变安装二元；BESS 与 Hybrid 各保留一个 BESS 安装二元。三个模型都保留真实 8784 h、年度弃电/PCC 服务和单全年循环，`representative_period_input_used=false`、`solver_invoked=false`。

本结果只证明 D41 的二元变量全覆盖分类、R0/R1 域变换和完整固定接口可在正式全年模型上复现；它没有产生下界、上界、容量、成本、gap 或技术排序。

## 2. 代码与测试

- `e0d41_strict_full_year_decomposition.py` SHA-256：`c7f45f8c071bb92c6cf7576a76bed71b71e606b7239881cb8baac09b195d2f1e`；
- `test_e0d41_strict_full_year_decomposition.py` SHA-256：`cc5c7bee44eea158f8523a4f9d531e407f4004562c8d55735e4ae49d4fe84ddb`；
- Windows D40/D41 定向回归：`24 passed in 3.02s`；
- OpenBayes 完整回归：`478 passed in 34.20s`。

## 3. 规范文件 SHA-256

- `gate_a_bess.json`：`5d0609fad197977ab5c0dff4e355186c8452d34661036bd1c82a446bf02095e0`；
- `gate_a_tes.json`：`0448e6441574960b9f88b248687f54c438023261ca891192f527c38b20c8e6a3`；
- `gate_a_hybrid.json`：`59edc53cebd07d820e66a5910b2576589faa4b365a1095ad43e169cb099f9c61`；
- `gate_a_manifest.json`：`50240e7ae557afa5633b29904585f1c1297a527343e467ce76d7766ce0177937`；
- `gate_a_execution.json`：`b2d9778e927d3925c7c247ee9816732ed299df3c204fc6a6d746fbe29451b88b`。

三个架构的日志和 execution sidecar 也保留在本目录。`gate_a_compile.log` 为零字节，因为编译器成功时不向标准输出写文本；规范结果由 `gate_a_manifest.json` 与引用哈希确定。

首次远程包装命令仅在所有规范文件生成后，因 Windows here-string 的 CRLF 使最后一条 `sha256sum` glob 带入 `\r` 而返回非零。随后使用独立命令完成远端逐文件哈希，并下载到本地复核；该包装错误未改变任何 JSON、代码、模型或判定。
