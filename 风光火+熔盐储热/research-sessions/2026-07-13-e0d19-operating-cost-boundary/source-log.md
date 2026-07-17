# Source log

更新时间：2026-07-13

| 来源 | 访问入口 | 取得的证据 | 资格与用途 |
|---|---|---|---|
| 本地 `_assemble_kj3.py` | 仓库文件，第 75–78 行 | `SELL_BASE=0.3545`、`BUY_BASE=0.42`，并乘作者设置的 TOU 比率 | 直接证明统一数据集价格列是生成情景；禁止作为正式结算 |
| 陕西省发改委，2025 年电力市场化交易有关事项 | https://sndrc.shaanxi.gov.cn/zfxxgk/zc/fgwj/sfzggwwj/2024/202412/t20241211_3225896.html | 煤电高比例中长期签约；24 时段合同需明确分时电量、价格与结算参考点；价格市场形成 | 官方制度证据；证明需要项目合同/市场身份，不提供杨凌 2024 实际价格 |
| 生态环境部，国环规气候〔2024〕1号 | https://www.mee.gov.cn/xxgk2018/xxgk/xxgk03/202410/t20241021_1089750.html | 分机组预分配、调整、核定与清缴；CCER 抵销不超过应清缴配额 5% | 官方履约制度；证明总排放×碳价不是项目履约成本 |
| 上海环境能源交易所，2024 年全国碳市场年度概况 | https://overview.cneeex.com/c/2024-12-31/495878.shtml | 年成交量 188,646,053 t、成交额 18,113,576,584.23 CNY、最高/最低 106.02/69.67 CNY/t | 官方市场锚点；仅用于敏感性/外部性，不替代项目配额缺口 |
| Klasing et al., *Applied Energy* 2025 | DOI `10.1016/j.apenergy.2024.124524`；本地已登记 PDF 文本 | 聚合熔盐固定/变动 O&M 量级，边界继承 CSP 假设并调整定日镜场 | Energy+；只作聚合敏感性，不能认证本文双服务五路径 TES VOM |
| InstSci semantic search | 2026-07-13，关键词含 CHP-TES O&M、electricity settlement、carbon allowance | 返回 Liu et al., *Renewable and Sustainable Energy Reviews* 2021 等候选；未得到可直接映射杨凌同边界 VOM 的项目级参数 | 搜索审计；无正式数值接入 |

访问判定：未发现公开的杨凌 2024 发电侧逐时结算、机组配额清缴、CHP 可分摊 VOM 或双服务 TES 五路径 VOM。上述四项保持 BLOCKED。
