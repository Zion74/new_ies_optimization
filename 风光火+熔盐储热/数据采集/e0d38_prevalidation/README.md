# E0-D-38 / D38-R1 预验证产物

本目录保存 D38 结果前合同及 R1 修订合同执行产生的规范证据。最终状态为：**D38-R1 在 baseline 时间聚合门失败**，不是正式 TAC，也不是 BESS/TES 技术赢家结果。

## 两类失败必须分开解释

1. 原 D38 `high_heat_tight_pcc` 在真实 8784 h 无储能最小弃电阶段物理不可行。490 MW PCC 下静态最大供热为 `766.076788 MWth`，原高热序列有 36 h 超限且全部位于 D36 代表周 4；这不是漏选代表周。
2. R1 将高热状态一次性修订为 `H*=G*=0.70` 后，静态检查为 0 个超限小时；但当前代码、同一 baseline 服务与同一输入哈希下，D36 代表期无储能在 10% 弃电帽内可行，而真实 8784 h 固定容量回放不可行。由于 baseline 已发生可行性反转，R1 三状态合同整体失败，无须等待其余架构或状态形成结论。

## 当前规范文件

- `service_high_heat_tight_pcc.json`：原 D38 高热状态在最小弃电阶段失败；
- `high_heat_static_pcc_diagnostic.json`：原高热状态的 36 h 静态超限诊断；
- `high_heat_r1_static_pcc_diagnostic.json`：R1 峰值 `724.034 MWth`，低于静态上限，0 h 超限；
- `service_baseline.json`：当前代码生成的真实 8784 h baseline 同服务合同；自然最小弃电 `565,916.122 MWh`，10% 帽 `339,569.906 MWh`，PCC 目标 `4,035,354.739 MWh`；
- `case_baseline_representative_planning_no_storage.json`：D36/D37 代表期无储能完成，弃电 `338,777.027 MWh`，对实际可用量比例 `9.9767%`，PCC 残差 `4.19e-9 MWh`；
- `case_baseline_full_year_fixed_no_storage.json`：同一服务和输入哈希下真实 8784 h 回放 `infeasible`；
- `baseline_weekly_failure_diagnostic.json`：实际全年自然最小弃电比代表期加权值高 `227,211.453 MWh`。第 49 周和第 16 周是最大两个单周低估，分别低估 `20,547.320` 与 `20,063.702 MWh`；
- `formal_baseline_chain.log`：服务代码哈希守卫、代表期成功和全年失败的最小执行日志；
- `manifest.json`：合同、提交、文件哈希、有效性和主张边界。

服务器上首轮 baseline 服务与后续案例使用了不同版本的 `e0d38_prevalidation.py`。该批次已移入 `stale_pre_r1_code/`，永久排除在正式证据之外；当前目录中的 baseline 三件套使用完全一致的代码与输入 provenance。

下一步只能先冻结新的结果前合同，再修订代表期方法。不得覆盖 D36、原 D38 或 R1 失败，也不得直接启动 E2/E3/E4 批量赢家扫描。
