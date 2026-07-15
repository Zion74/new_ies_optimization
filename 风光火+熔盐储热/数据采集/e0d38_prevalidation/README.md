# E0-D-38 预验证产物

本目录保存 D38 结果前合同执行产生的规范证据。当前原合同已在 `high_heat_tight_pcc` 的真实 8784 h 无储能最小弃电阶段失败，因此这些文件是负结果与失败诊断，不是正式 TAC 或技术赢家结果。

## 当前规范文件

- `service_high_heat_tight_pcc.json`：状态为 `infeasible`，失败阶段为 `minimum_curtailment_search`；
- `high_heat_static_pcc_diagnostic.json`：490 MW PCC 下静态最大供热 `766.076788 MWth`，冻结高热序列有 36 h 超限，全部位于 D36 代表周 4；
- `manifest.json`：文件哈希、合同和主张边界。

baseline 服务参考仍可继续作为部分诊断；无论其结果如何，原三状态 D38 都不能因删除失败状态而被登记为通过。任何修订状态必须进入新的结果前合同和新文件名。
