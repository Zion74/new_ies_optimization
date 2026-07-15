# E0-D-39 服务感知代表周 Gate A/B 证据包

本目录保存 D39 结果前合同执行后的 Gate A 规范数据。D39 保留 D36 六周，并依据冻结的 D38-R1 baseline 周级诊断一次性加入第 49/16 周；全部 52 周仍按 D36 的 672 维输入特征距离重新分配。Gate A 不调用规划求解器，不产生储能容量、正式 TAC 或技术赢家。

## 文件

- `e0d39_week_assignments.csv`：52 周到八个代表周的唯一归属、距离、角色和重建权重；
- `e0d39_representative_periods.csv`：八个 168 h 周及年尾 24 h warm-up + 48 h 计分段，共 1416 行；
- `manifest.json`：D36/D38 输入、D36/D39 代码哈希、选周规则、结构审计和描述性重构误差；
- `execution.json`：OpenBayes Python、平台、运行时间和规范 manifest 哈希，属于非规范运行侧车；
- `gate_b_baseline_minimum_curtailment.json`：真实全年与 D39 八周的正式自然最小弃电求解、gate 判定和 provenance；
- `gate_b_decision.json`：冻结阈值、结果哈希、接入提交和停止决定；
- `gate_b_pre_adapter_rejection.log`：首次命令在求解前被 D36-only 锁拒绝的审计日志，不是数值结果。

## 冻结结果

| 源周 | 角色 | 权重（周） |
|---:|---|---:|
| 4 | D36 热峰强制周 | 1 |
| 5 | D36 高可再生压力强制周 | 2 |
| 8 | D36 PAM medoid | 9 |
| 16 | D38 baseline 低估排名第 2 | 2 |
| 29 | D36 PAM medoid | 13 |
| 39 | D36 PAM medoid | 19 |
| 48 | D36 PAM medoid | 4 |
| 49 | D38 baseline 低估排名第 1 | 2 |

权重之和为 52；模型时段 1416、计分源行 1392、加权计分小时 8784。年尾 72 h 的源时标、数值、计分标志和权重与 D36 逐字段一致。

描述性重构误差为：年供热量 `+4.8512%`、风电可用量 `-5.8068%`、光伏可用量 `+2.6222%`、年均气温 `+0.9442 °C`。这些值不是继续选周的调参目标。

## 跨平台复现

Windows 与 OpenBayes 使用锁定输入独立构造，三个规范文件逐字节一致：

- assignments：`7949d6f58d86787cf9ea8129dae3adc85ec20ffba8a157ad7e121395f2f5052e`；
- periods：`fb7aa1e9d8815a2a22eee68b61af12b44c4485ba3ca464d21652480d9b75c2ac`；
- manifest：`dabb565087e9adb2e597d00ea7c12fcb30bf9e522517a7f8e6ed7ee73d9a16a9`。

OpenBayes `execution.json` SHA-256 为 `572faa4ff34c6e6ad00322dbd4bf50674e0ced6849416ecb840296f639de5d78`，构造耗时约 0.92 s。

## Gate B 结论

真实全年和 D39 八周的自然最小弃电分别为 `565,916.122` 与 `390,148.306 MWh`，都超过 `339,569.906 MWh` 的 10% 帽，故可行性分类一致；但共同分母下的弃电率为 `16.6657%` 与 `11.4895%`，误差 `5.1762` 个百分点，大于预注册阈值 `1.0`。Gate B 因此失败，Gate C/D 未启动，也不得在 D39 名下继续加周或放宽阈值。

Gate B JSON SHA-256 为 `47f33db2d3a00bbe5f70cd342198fd5daa1538663c49b8ec7d39641fd27b645b`，停止决定 SHA-256 为 `366ae2650910a993bf95fe840621ec1ccbe7ed1dba7751fa657374deda3a8141`。完整合同与失败解释见 `docs/03_sci_paper/e0_d39_service_aware_representative_week_refinement_contract.md` 和 `docs/03_sci_paper/e0_d39_gate_b_quantitative_fidelity_failure.md`。
