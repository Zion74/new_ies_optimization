# E0-D-5 TES 成本容量与温区映射合同

更新时间：2026-07-12

状态：**物理容量账本、部件—容量基准、三状态罐完整库存认证、温区覆盖和生命周期 portfolio 绑定已经实现；E0-D-15 增加 12 账户 TES 正式成本就绪度门禁；E0-D-16/17 只选取完整显热、电加热输入、电输出和有效热输出四个容量基准展示同一全系统 EAC 上限，不向部件反分摊。当前本地/远端均 284 项通过；TES 正式成本数值仍未闭合。**

## 1. 目的

本合同解决熔盐 TES 文献成本最容易造成的四类错误：

1. 把同一批在 HT/MT/LT 三罐间迁移的盐重复计价；
2. 把 `kWel` 净电输出、`kWth` 换热负荷和五个端口上限混为同一功率；
3. 把 `€/kWhth` 聚合系统成本与盐、罐、泵、换热器分项成本叠加；
4. 不检查文献温区便把中温设备成本外推到更高 HT 温度。

代码与测试位于：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/tes_cost_mapping.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_tes_cost_mapping.py`

## 2. 唯一物理容量账本

对安装盐质量 (M_s)、比热 (c_p) 和三温区 (T_{HT}>T_{MT}>T_{LT})，允许的主要计价分母为：

\[
M_{salt,kg}=1000M_s,
\qquad
E_{full,kWh_{th}}=1000M_sc_p(T_{HT}-T_{LT}).
\]

其中 $E_{full}$ 是同一批盐从 LT 到 HT 的完整显热库存。只有 HT、MT、LT 三个状态罐都能分别容纳整批安装盐时，才允许认证该完整容量；否则合同拒绝用理论焓冒充可交付 `kWhth`。HT→MT 与 MT→LT 是两个连续服务级，不得把两段盐质量或三罐库存再次相加计费。HT、MT、LT 罐体若按质量/容积报价，则分别使用各自安装罐容。

五端口与设备计价基准固定为：

| 文献/设备项 | 模型计价量 | 单位 |
|---|---|---|
| 盐 | 安装总盐质量 | `kg` |
| 两/三罐系统、按储热量报价的循环系统 | 完整 LT→HT 显热库存 | `kWh_th` |
| HT/MT/LT 单罐 | 对应罐体质量容量 | `tonne_tank_capacity` |
| 变压器、电加热器 | 交流输入端口上限 | `kW_el` |
| 高品位抽汽换热器 | `steam_to_ht_reference_input_mw` | `kW_th` |
| 中品位抽汽换热器 | `steam_to_mt_reference_input_mw` | `kW_th` |
| 盐—蒸汽发生器 | `electric_output_mw / power_block_efficiency` | `kW_th` |
| 新建独立发电子系统 | 净电输出端口上限 | `kW_el` |
| 供热换热器 | `heat_output_mw / heat_exchanger_efficiency` | `kW_th` |
| 既有汽轮机复用标记 | 1 套，初始/更换 CAPEX 必须为零 | `system` |

因此，文献按 `kWth` 报价的蒸汽发生器不能直接乘模型的净 `kWel` 输出；模型必须先恢复盐侧热输入负荷。供热换热器同理，按换热设备输入负荷计价时不能直接使用用户侧有效供热输出。

## 3. 温区覆盖合同

每个分项成本必须登记文献参考温区。只要求覆盖该部件实际经历的温段：

- 盐、罐、循环、电加热器、高品位充热换热器：LT→HT；
- 中品位充热换热器、供热换热器：LT→MT；
- 盐—蒸汽发生器和新增发电子系统：MT→HT；
- HT/MT/LT 单罐：分别检查对应温度点；
- 既有汽轮机复用和系统级 FOM 标记不伪造熔盐参考温区。

参考温区未覆盖模型部件温段时，`bind_tes_cost_portfolio()` 拒绝绑定。此时该成本只能降为外推敏感性或继续检索证据，不能进入正式基线。

## 4. 当前高等级文献映射结论

### Trevisan et al. (Energy Conversion and Management, 2022)

Table 8 的候选分项映射为：变压器 `30 €/kWe` 与电加热器 `50 €/kWe` 对应电加热交流输入；罐 `30 €/kWhth` 与循环 `25 €/kWhth` 对应完整显热库存；蒸汽发生器 `120 €/kWth` 对应换热侧热负荷；盐 `1 €/kg` 对应安装总盐质量。循环系统脚注又称其约为直接 CAPEX 的 10%，因此固定 `€/kWhth` 与百分比口径只能二选一。该研究工作温区约为 170–450 °C，不能直接支持高于 450 °C 的 HT 基线。

### Klasing et al. (Applied Energy, 2025)

电加热器按 `€/kWel`、蒸汽发生器按 `€/kWth` 的端口映射与本合同一致。DLR 原报告已确认 `21 €/kWhth` 两罐中心值的基年为 2020 EUR，范围为 20–22；该系统值包含热罐、冷罐、盐、基础、保温、电加热、BoP/markups 等成本份额，是系统聚合锚点，只能用于校准分项 ledger 总量，不能再与盐和罐分项叠加。其 290–560°C Solar Salt 两罐边界与杨凌三温区 HITEC 不同。

### Wang et al. (Applied Energy, 2025) 与 Li et al. (Energy, 2026)

Wang 用于盐物性、盐价范围、动态流量以及泵/换热器设计边界；Li 的煤电级联 TES 总投资用于聚合工程校准。两者均不能在缺少完整分项价格年和容量分母时被反推成唯一的盐、罐、泵、换热器单价。

## 5. 尚未通过的门槛

- 明确最终 HT/MT/LT 工程温度和盐配方，并锁定相应 (c_p)、密度、冻结/分解与腐蚀边界；
- 为每个正式分项找到明确价格年，换算为 `CNY_2024_real`；
- 补齐泵扬程/流量、辅助用电和换热面积的工程缩放；
- 对 bottom-up ledger 与至少一个独立聚合工程锚点做总量校准；
- 为每个最终分项保存来源页码、容量分母、温区、价格年与转换链的不可变参数清单。

E0-D-10 已把上述门槛拆成逐来源机器可读记录，见 `风光火+熔盐储热/research-sessions/2026-07-12-bess-tes-lifecycle-cost-parameters/cost-evidence-gap-matrix.csv` 和 `e0_cost_evidence_gap_matrix.md`。其中 Trevisan、Klasing、Wang、Li 的直接成本仍因价格年或包含边界被阻断；McTigue、Vecchi 的明确 2020 USD 只允许作异拓扑敏感性/方法锚点。

这些门槛完成前，E0-D-5 只证明“单位、容量和温区不会静默错接”。12 个账户的正式资格由 `e0_tes_formal_cost_readiness_contract.md` 与 `formal_tes_costs.py` 继续把关；未颁发 TES 证书时不提供正式 TAC，也不启动 E1–E6 批量实验。
