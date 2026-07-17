# E0-D-28 多方向启动筛查产物

本目录保存对 D27 336 h 最大端可行下界的两个预注册多启动筛查：

- `probes/336h_negated.json`：从 D19 轨迹相反符号启动；
- `probes/336h_alternating.json`：从逐时正负交替符号启动；
- `e0d28_multistart_screening.csv`：排除运行时间和完整符号串的确定性汇总；
- `manifest.json`：原始探针、上游输入、源码和 sidecar 的 SHA-256 锁；
- `execution.json`：包含线程、时限、运行时间和完整符号串的非规范 sidecar。

D28 只筛查更强可行 L1 证人。`support_dual_is_global_l1_upper_bound=false`、`global_l1_bound_generated=false`、`actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

两条 336 h 预注册筛查均未改善 D27 的 `36,382.462799 MWh/a` 可行下界，且都未在单轮内达到符号固定点；D27 的全局严格区间保持 `[36,382.462799,1,081,649.139331] MWh/a`。规范 CSV SHA-256 为 `1172ee16c16353e68fc907fa698495a8195d8f211bead70be64d9a4d3e9a0330`，manifest SHA-256 为 `0427ce8647f27a8b5ce74690673a4690be4a41849846aafba53ad942c61ff80c`。
