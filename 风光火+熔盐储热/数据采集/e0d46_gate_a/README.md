# E0-D-46 OpenBayes Gate A 证据

- 状态：`gate_a_passed`
- 源码提交：`4a18f4232563a187652e6c6d509441834bce1e7a`
- Gate A manifest SHA-256：`098fc8bef7fe160cdad98d5d22675d82dcd9341e03e656792b357e7f29f1d176`
- Gate A execution SHA-256：`2ca2f3cd22049ad75db51d8f07b4161a9a1414ab0bec01df1d51de31251c84df`
- Linux 测试：D46 `22 passed`；D40–D47 + planning/HiGHS `204 passed`；全包 `644 passed`；均为零失败、零错误、零跳过。
- 三架构 8784 h 原模型均通过 build-only 审计，非线性计数为零，`solver_invoked=false`、`formal_optimization_invoked=false`。
- Gate A 只开放唯一正式 D46 总批次；当前仍无正式可行容量、上界、项目 TAC、gap 或技术排序。

本目录保存最终 Gate A manifest/execution、三架构构建审计、JUnit、测试日志及 Ruff/`py_compile` 证据。结果前首次构建曾因 D46 规模锁字典漏写两个合法非线性零字段而在求解器调用前停止；该诊断留在服务器独立目录，不属于本最终通过包。
