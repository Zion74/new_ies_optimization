# D41 Gate B BESS 接入拒绝记录

状态：`pre_adapter_rejection`；不属于正式数值求解结果。

首次把结果前提交 `226f590` 的 Gate B 执行器接入真实 8784 h BESS 模型时，R0 在模型构造完成后的服务审计中访问了不存在的 `E0CTimeSeries.periods`，触发 `AttributeError`。正确接口是既有且已验证的 `E0CTimeSeries.period_count`。R0 的 `solver_invoked=false`、`formal_lower_bound_eligible=false`，没有产生 dual、容量、成本或技术排序。

原编排器把父进程正常退出误当作阶段通过，因此随后又构造了 R1；R1 在相同审计处被拒绝，仍为 `solver_invoked=false`。该缺陷已修为：服务审计读取 `period_count`，且任何阶段没有合法下界时立即停止后续松弛。新增两项回归直接覆盖真实接口与 R0 停止规则。

关键文件 SHA-256：

- `gate_b_bess_r0.json`：`993a4b8eb0dcb05c09e7bd83117012ae5599f1eaec0814106368817da683533f`；
- `gate_b_bess_r1.json`：`fe58f26fe44a1fd6b672673afdca3d1568910b9de4153d1528977f169f1b4893`；
- `gate_b_bess_manifest.json`：`cad5e0e09709f5c06ba1a3168d10d6f714baf5f2e8454540d1463ed750340e2b`；
- `gate_b_bess_execution.json`：`3e0c346d20f46c5834eefa097ccb9ba8dee282374ac47600d4fca15db361d460`；
- `gate_b_bess_command.log`：`c89e230925f9d012b0a04b804f8bb5f6ffb868c570d436d9720c09391b086153`。

远端与本地均保留在 `pre_adapter_rejection_period_count/`，不会覆盖或混入后续正式 Gate B 文件。
