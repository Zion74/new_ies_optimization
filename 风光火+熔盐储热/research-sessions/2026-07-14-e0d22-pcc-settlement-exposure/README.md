# E0-D-22 逐时 PCC 与结算暴露会话

日期：2026-07-14

目标：在不假设杨凌实际电价的前提下，把 E0-D-19 从年度 PCC 总量升级为两架构逐时外送轨迹，并量化分时结算对价格跨度的最大暴露。

结论：

- 24 h 年化重新分配 `26,010.174918 MWh`，占共同交付 `0.558528%`；
- 336 h 年化重新分配 `31,228.008145 MWh`，占共同交付 `0.731355%`；
- 固定平价结算严格抵消；任意有界价格序列对当前所选轨迹的结算差绝对值不超过“价格跨度 × 重新分配电量”；
- 当前轨迹是 HiGHS 主成本 + 固定整数弃电次目标选出的可复现解，连续替代最优解尚未排除；
- 真实分时结算、完整 TAC 和 E1–E6 仍关闭。

产出：

- `docs/03_sci_paper/e0_pcc_settlement_exposure_contract.md`；
- `tes_bess_boundary/src/tes_bess_boundary/pcc_settlement_exposure.py`；
- `tes_bess_boundary/tests/test_pcc_settlement_exposure.py`；
- `数据采集/e0d22_pcc_settlement_exposure/`。

复现：本地 `308 passed in 66.43s`；OpenBayes `308 passed in 26.43s`。双窗口正式作业约 333.7 s。
