# E0-D-20 证据备忘录

## 判定

`formal_portfolio_ready=false`。

| 账户 | 形式阻断项 |
|---|---|
| 分时电力结算 | `allowed_use`、`project_scope`、`numerical_input`、`variable_driver` |
| 碳配额履约 | `allowed_use`、`numerical_input`、`variable_driver` |
| CHP VOM | `allowed_use`、`cost_boundary`、`variable_driver`；台账复核另标 `fuel_overlap_risk` |
| TES VOM | `allowed_use`、`project_scope`、`cost_boundary`、`variable_driver`、`technology_boundary` |

## H 列复核

- #1：`49711.5347728162 万元/年 ÷ 161182.8 万kWh = 308.417118779524 元/MWh`；
- #2：`44489.7862181839 万元/年 ÷ 144252 万kWh = 308.417118779524 元/MWh`；
- 按共同煤价 `800.86 元/tce` 折算，两者均为 `385.107408010793 gce/kWh`。

这是一项重叠风险诊断，不是将 H 列重新认定为燃料费。原标签、原数值和源文件哈希均保留。

## 后续取证优先级

1. 杨凌 2024 年中长期合同、现货/偏差/辅助服务逐时结算或可审计价格快照；
2. 2024 核定排放、免费配额、持仓/购入/CCER 和履约成本；
3. H 列科目表以及检修、材料、人工、环保耗材按固定/变动和驱动量拆分；
4. 与当前 TES 路径直接对应的泵耗、换热维护、盐品补充、停机检修等项目记录。

在这些材料到位前，只推进预注册影子成本敏感性，不启动正式 TAC 或 E1–E6 批量实验。
