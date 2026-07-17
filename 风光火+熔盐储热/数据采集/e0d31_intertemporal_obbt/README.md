# E0-D-31 规范产物

本目录保存跨时段连续松弛 OBBT 的双窗口屏幕和 24 h 等价性探针：

- `screen_24h.json`：96 个逐时 PCC LP；
- `screen_336h.json`：1344 个逐时 PCC LP；
- `24h.json`：D31 区间切面的 24 h 精确等价性门；
- `e0d31_intertemporal_obbt_screening.csv`：2 行规范筛查证书；
- `manifest.json`：上游/源码/产物哈希、连续松弛合同和停止门槛；
- `execution.json`：非规范运行时间、进程分配和 336 h worker 重建记录。

336 h 正/负平均符号宽度相对 D30 仅再改善 `0.0329%/0.0864%`，低于在任何 336 h 全局探针前采用的 `1%` 资源门槛，因此未生成 `336h.json`，最新 336 h 全局界继续引用 D30。目录不包含实际价格、正式 TAC 或 E1 结论。
