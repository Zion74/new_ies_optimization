# E0-D-36 结构化代表周证据包

本目录保存 2026-07-15 在 OpenBayes 上由锁定的 2024 年正式热负荷和旧 2019 风光形状生成的代表周数据。D36 只冻结选周、归属、权重、年尾 warm-up 和源时标映射，不运行储能容量优化，不形成杨凌正式 TAC 或技术赢家。

## 文件

- `e0d36_week_assignments.csv`：52 个完整周到六个代表周的唯一归属、距离、角色与权重；
- `e0d36_representative_periods.csv`：六个 168 h 代表周，加年尾 24 h 不计分 warm-up 与 48 h 计分段，共 1080 行；
- `manifest.json`：输入哈希、特征标准化、确定性 medoid/极端周合同、结构审计和描述性聚合误差；
- `execution.json`：OpenBayes Python/平台、运行时间、源路径和规范 manifest 哈希。它是非规范运行侧车。

## 冻结结果

| 源周 | 日期 | 角色 | 权重（周） |
|---:|---|---|---:|
| 4 | 2024-01-22—01-28 | 峰值热负荷 / 低风强制极端 | 1 |
| 5 | 2024-01-29—02-04 | 高可再生压力 / 低吸纳强制极端 | 3 |
| 8 | 2024-02-19—02-25 | PAM medoid | 10 |
| 29 | 2024-07-15—07-21 | PAM medoid | 13 |
| 39 | 2024-09-23—09-29 | PAM medoid | 21 |
| 48 | 2024-11-25—12-01 | PAM medoid | 4 |

六个权重之和为 52。代表周计分行 1008 个，年尾计分行 48 个，warm-up 24 个；年度加权计分小时为 8784 h。年尾 warm-up 使用真实的 2024-12-29 逐时值，年尾计分段为 2024-12-30 00:00 至 2024-12-31 23:00。

## 描述性重构诊断

- 年供热量：`+5.3531%`；
- 风电可用量：`-8.9751%`；
- 光伏可用量：`+2.6072%`；
- 年均气温：`+1.0424 °C`。

这些量不是 D36 的事后调参目标。它们已冻结为 D38 代表周规划—8784 h 回代的风险信号；若 D38 不通过，只能新建版本并按合同增加误差贡献最大的真实周，不能覆盖本包。

## 跨平台复现

OpenBayes Python 3.10.18 与 Windows `.venv-e0` 使用相同源文件独立构造，三个规范文件逐字节一致：

- `e0d36_week_assignments.csv`：`31c7daae3faa5ffa91f3e5b31ad75fc666cf9f3952bac399352ec832607488a3`；
- `e0d36_representative_periods.csv`：`02b168d6b4169101c1d601a548c7a475d8aea8a8a280de5f52fcaaf6ec09aaa9`；
- `manifest.json`：`2c3818030277d146479245afdf278fa96f7562a1951b42641f5a5103d181a5f1`。

OpenBayes `execution.json` 的 SHA-256 为 `fa6d29d21ebddacb32dbcd17d2c32b67606715568bb8ee2d9c7891c146fb48cf`，构造耗时约 0.80 s。详细预注册规则和 D37 边界交接见 `docs/03_sci_paper/e0_d36_representative_week_construction_contract.md`。
