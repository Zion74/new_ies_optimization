# 第三场景占位：交通加氢站

该场景用于验证第一版接口对 15 类应用场景的扩展能力。

当前状态：

- 包含 `hydrogen` 用户需求。
- 启用 `electrolyzer` 和 `hydrogen_storage` 两类预留设备。
- 故意使用 `cchp_ehc_base` / `current_cchp` 后端，因此校验阶段应提示当前后端不支持氢设备。

该场景暂不用于真实优化。后续接入真实数据并实现通用 oemof/Pyomo 组件映射后，可切换到未来通用后端。
