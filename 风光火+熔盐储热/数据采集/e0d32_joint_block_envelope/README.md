# E0-D-32 联合分块 L1 包络负筛查

本目录包含：

- `screen_24h.json`：单个 24 h 块的完整路径松弛上界；
- `screen_336h.json`：14 个连续 24 h 块的完整路径松弛上界；
- `24h.json`：把块割加入 reopened 原整数模型后的 24 h 等价探针；
- `e0d32_joint_block_envelope_screening.csv`：两窗口规范汇总；
- `manifest.json`：输入、原始探针与规范 CSV 的哈希锁；
- `execution.json`：非规范运行时间、termination 与线程记录。

336 h 的 14 个受保护块上界之和为 `1,930,160.868929 MWh/a`，高于 D30 的 `777,141.368858 MWh/a`。结果前固定的 `1%` 材料性门未通过，因此本目录没有 `336h.json`，最新 336 h 严格区间仍引用 D30。

这些结果只用于数值证书筛查，不是实际价格暴露、正式 TAC、技术赢家或 E1 结果。
