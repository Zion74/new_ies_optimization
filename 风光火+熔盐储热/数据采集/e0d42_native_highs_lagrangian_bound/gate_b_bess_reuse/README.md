# E0-D-42 Gate B：BESS R0 build-only 复核

状态：`bess_d41_bound_reuse_passed`

本阶段只重建 BESS R0、复核 D40/D41 输入和完整二元域、生成原始/预求解 LP 指纹，并独立重汇编 D41 BESS manifest；没有调用优化器。

- 原始 LP：`527,053 × 597,318`，`2,187,237` 非零元，SHA-256 `ccd2600e8050e7b702a9badb610de64f37420620161411d486913d8d3346a9f0`；
- presolve LP：`390,252 × 451,527`，`1,592,820` 非零元，SHA-256 `ea9e0d34f4b7c1c0aa49c4dcd5b86f89b26a95542b589220f0783d4d70191286`；
- 原始二元 `79,057` 个，R0 后剩余 `0` 个；
- D41 BESS manifest 重汇编完全相等，SHA-256 `ed4fcf7d08ab236b678f787c777903d7905197b1262d820371c93f9aef76cfc7`；
- 复用严格下界：`1,144,950,604.8368804 CNY`；
- 父进程墙钟 `121.434 s`，峰值子进程树/父子合计 RSS `1.917/1.939 GiB`，最低可用内存 `95.405 GiB`，资源门通过。

规范 result/execution SHA-256 为 `ae30997a4dcf4fb3ed599ff17b9f5bb1238d66ad4eda677312e91a69bd4f5d36` / `280f9b4ed194af82029b2e43c1a3f7d96f96428efe29a9f18fa836cba739a3b4`；本地/远端五个原始产物逐文件同哈希，本地父进程前置证据重审通过。

该结果只证明 D42 可沿用 D41 的 BESS 松弛下界，不是容量、可行上界、项目 TAC、gap 或技术赢家。下一步按合同启动 TES R0；TES 没有有限合法证书时不得启动 Hybrid。
