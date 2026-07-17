# E0-D-26 数值证书产物

本目录保存 D23 替代调度包络的严格数值加固产物：

- `probes/`：24 h/336 h × D19 条件整数面/全部整数模式开放 × 最小/最大共 8 个原始 JSON 探针；
- `e0d26_numerical_certification.csv`：排除运行时间后的两窗口规范汇总；
- `manifest.json`：8 个原始探针、非规范 sidecar、上游输入与源码的 SHA-256 锁，以及数值合同和科学边界；
- `execution.json`：含线程、时限和运行时间的非规范 sidecar。

这些产物只证明价格无关的 PCC 年化 L1 重分配数值范围。`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。
