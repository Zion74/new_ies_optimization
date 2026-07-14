# E0-D-27 方向生成与符号重构产物

本目录保存 D27 对 D23/D26 替代调度 L1 最大端的严格数值加固：

- `probes/24h_final.json`：24 h 固定方向和正负分解全局证书；
- `probes/336h_support_final.json`：336 h 固定方向、符号固定点与可行 L1 证人；
- `probes/336h_global.json`：336 h 正负分解全局 primal/dual；
- `e0d27_numerical_certificate.csv`：排除运行时间后的两窗口最大端规范汇总；
- `manifest.json`：原始探针、上游输入、源码与非规范 sidecar 的 SHA-256 锁；
- `execution.json`：含线程、时限和运行时间的非规范 sidecar。

固定方向 dual 只界定该方向，不是全局 L1 上界。正负分解在所有主整数与符号模式开放时返回的有限 dual 才是全局外界。

这些产物只证明价格无关的 PCC 年化 L1 重分配范围。`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。
