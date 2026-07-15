# E0-D-41 严格全年证据

状态：Gate A `gate_a_passed`；Gate B `no_strict_certificate`；Gate C/D 未执行

执行端：OpenBayes，Python 3.10.18，Pyomo 6.10.1，HiGHS 1.15.1。Gate A 未创建求解器；Gate B 正式调用 HiGHS；总汇编阶段未调用求解器。

## 1. 结果摘要

| 架构 | 活动变量 | 原始二元 | R0 剩余二元 | R1 剩余二元 | 完整固定后未固定二元 | 加权小时 | 运行时间 / s | 峰值 RSS / GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BESS | 597,318 | 79,057 | 0 | 1 | 0 | 8,784 | 67.762 | 0.759 |
| TES | 650,052 | 87,840 | 0 | 0 | 0 | 8,784 | 76.311 | 0.865 |
| Hybrid | 685,194 | 96,625 | 0 | 1 | 0 | 8,784 | 81.217 | 0.907 |

R1 只保留时间不变的安装/端口拓扑二元。当前 TES 采用 D34 已冻结的连续零容量策略，没有时间不变安装二元；BESS 与 Hybrid 各保留一个 BESS 安装二元。三个模型都保留真实 8784 h、年度弃电/PCC 服务和单全年循环，`representative_period_input_used=false`、`solver_invoked=false`。

本结果只证明 D41 的二元变量全覆盖分类、R0/R1 域变换和完整固定接口可在正式全年模型上复现；它没有产生下界、上界、容量、成本、gap 或技术排序。

## 2. Gate A 代码与测试

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

## 4. Gate B 接入拒绝记录

`pre_adapter_rejection_period_count/` 保存首次 BESS Gate B 接入失败。R0/R1 都在服务审计阶段因错误访问 `E0CTimeSeries.periods` 被拒绝，`solver_invoked=false`，没有产生数值下界；原编排器错误继续 R1 的问题也已登记。修复改用真实 `period_count` 接口，并规定 R0 无合法下界时不再启动 R1。该子目录永久与后续正式结果隔离。

## 5. Gate B 正式结果

结果前汇编器提交 `0fb9346` 后，OpenBayes 完整回归为 `491 passed in 33.89s`。正式串行结果为：

- BESS R0/R1 均达到最优并通过全部审计，严格下界取 `1,144,950,604.8368804 CNY`；R1 的 597,318 行引导文件只允许作为 `candidate_only`；
- TES R0 在 `720.462 s` 触发父进程硬墙钟，未返回结果 JSON、有限合法 dual 或不可行证明；峰值子进程树 RSS `2.389 GiB`、最低可用内存 `94.939 GiB`，不是内存耗尽；
- TES R1 和 Hybrid 按串行停止规则未启动；Gate C/D 未启动；
- 总判定为 `no_strict_certificate`，`technical_ranking_permitted=false`。该结果不能证明 TES 物理不可行，也不能证明 BESS 为技术赢家。

核心 SHA-256：

- BESS manifest/execution：`ed4fcf7d08ab236b678f787c777903d7905197b1262d820371c93f9aef76cfc7` / `b743baa1d87ce54fd5d110b844cb8f9933941ac091f10ad161c2217357aa456f`；
- TES manifest/execution：`c69bc1d46de78f3734441bea70302e9e823f5132db7570fb5e91b6d2ee4cba43` / `338fd155914ca85c92b834f32e9436fb2c14b6bc9e4def986151a033b1e34f02`；
- Gate B 总 manifest/execution：`bbc0638470859a58fe26a3166ec4825f455fd27671b7edf234b6e51557ee8aef` / `0b71fc77d7aa4faaad3b84f294faddd035dc8ea66df744df1ba27164c247af19`；
- 汇编器：`77084f736eaceb1220198ed1f2043b24ba0be6604352ee383f6e8229f76c29c3`，汇编阶段 `solver_invoked=false`。

正式 JSON、HiGHS 日志、父进程心跳、execution sidecar、PID 和 BESS R1 压缩引导文件均保留在本目录。后续只能另立 D42 结果前合同处理 TES 全年 LP 的收敛、可中断终止与合法 dual 提取，不得在 D41 名下延长时限或启动后续 Gate。
