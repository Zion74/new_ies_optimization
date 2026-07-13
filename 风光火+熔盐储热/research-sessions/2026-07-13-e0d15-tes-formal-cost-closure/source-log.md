# E0-D-15 source and access log

日期：2026-07-13

## 已核对来源

| 来源 | 访问路径 | 本轮用途 | 判定 |
|---|---|---|---|
| Trevisan et al. (2022), DOI `10.1016/j.enconman.2022.116362` | KTH/DiVA 官方作者全文 | Table 8 与底层参考文献逐项核对 | 混合 2011—2022 来源，无共同价格年；结构/分母可用，正式价格阻断 |
| Klasing et al. (2025), DOI `10.1016/j.apenergy.2024.124524` | Zenodo 官方记录与作者全文 | Tables 2/4、成本相关式与 refs. 19/21/42/48/49/63–66 | 仅气体处理相关式明确为 2023 EUR；核心 TES 表不能整体标为 2023 EUR |
| Dersch et al. (2021), DLR report 0324253 | [DLR 官方仓储](https://elib.dlr.de/141315/) | 追溯 Klasing 的 `21 EUR/kWh_th` 两罐锚点 | Figure 4 明确 `Base year 2020`；20–22 EUR/kWh_th 为两罐 Solar Salt 系统级工程锚点，不是正式三罐 HITEC 部件价格 |
| Guccione & Guédez (2023/2024) | Energy DOI/公开全文与既有询证记录 | 电加热器报价与温度修正式 | 报价年、原币、规模、包含项及公式缩放仍阻断 |
| Li et al. (2026), DOI `10.1016/j.energy.2026.141711` | 出版商页面/全文 | 部件函数与系统总投资 | 部件函数缺币种/基年；总投资只作聚合校准 |

## InstSci

使用本机 `instsci search` 对 Trevisan 与 Klasing 精确题名检索；Semantic Scholar 路由限流并返回空结果。该状态只记为访问失败，不构成“没有其他文献”的否定证据。正式全文判断来自上述 DOI 与机构官方版本。

## 临时文件边界

主线程为全文核对将 Trevisan、Klasing 与 DLR 公开 PDF/文本暂存于 `%TEMP%`。这些文件只用于本轮审计，未放入仓库、未提交 Git；完成后按精确路径删除。没有保存 Elsevier/CARSI cookie、机构凭据或访问令牌。
