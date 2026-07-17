# E0-D-35 TES 材料性网格证据包

本目录保存 2026-07-15 在 OpenBayes / HiGHS 上完成的 24 h TES 工程材料性敏感性。它使用 D34 的同弃电上限、同年度 PCC 服务和公开代理成本，不是杨凌正式 TAC 或真实项目最小规模。

## 文件

- `e0d35_tes_materiality_grid.csv`：16 行规范汇总；
- `manifest.json`：预注册网格、两组服务、参考切片、规范 CSV 哈希和主张边界；
- `execution.json`：16 个被选中原始探针的文件、SHA-256、运行时间和 solver 设置；
- `raw/`：首轮 16 个 `0.1%` gap 探针；
- `raw/refined/`：自然服务 5%/10% × TES/Hybrid 的 4 个 gap=0 复算。规范汇总对这四个身份选用 refined 结果，避免把提前停止的较差零容量 incumbent 误写成成本变化。

## 锁定材料性网格

参考切片为 `1,200 MWhth / 13,913.715638 t / 150 MW`。比例为 `0 / 1% / 5% / 10%`；正比例下安装盐量和每个启用端口分别执行“0 或比例阈值以上”，比例 0 保持 D34 连续容量模型。

## 核心结果

- 自然服务：连续模型仍出现约 `0.9 t` 微型 TES；1% 门下形成 `139.137–141.600 t` 的 heat-only TES；5% 和 10% 门下 TES/Hybrid 均精确折叠为无储能，gap=0，总成本统一为 `544.847466606 million CNY/a`。1% 解相对无储能的公开代理成本改善仅约 `0.154–0.275 million CNY/a`，不足以形成项目级经济赢家主张；
- 严格服务：全部比例都需要 TES；1%/5%/10% 下 TES 盐量约为 `174–186 / 871 / 1,742 t`。由于电输出端口启用后还受 2 h 额定放能认证约束，实际盐量可高于名义材料性盐量；
- 所有 Hybrid 的 BESS PCS 与能量容量均为零，因此在本切片内折叠为 TES；
- TES 与 Hybrid 的 objective bounds 在每个严格材料性水平都重叠，不允许排序；
- 5%/10% 严格解主动把弃电压到上限以下，属于同一个“弃电不超过 ε”的服务集合，不能把实际弃电差隐藏掉。

## 哈希

- `e0d35_tes_materiality_grid.csv`：`8a321001878a7d0b14f8441f96272cdd18303201fa5c9facbccd97825ea016d2`；
- `manifest.json`：`b722a6143ce25f8abc113ed3b51b3c09aa4008bab77973174c23c955481bc4a5`；
- `execution.json`：`2bb893ccbfc9f19637201ee8487a224e089f2e9ac4b3aeaf113d49ba9d512c5d`。

详细模型、网格和禁止性主张见 `docs/03_sci_paper/e0_d35_tes_materiality_gate_contract.md`。
