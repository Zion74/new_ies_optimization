# E0-D-24 完整 TAC 证据路线合同

更新时间：2026-07-14

状态：**16 个非可选账户的统一证据门已实现；严格正式账户为 `0/16`，`formal_tac_ready=false`，`e1_ready=false`。** 其中 12 个 TES 账户包含 8 个“直接候选不完整”和 4 个“无直接候选”；4 个非燃料运行账户均要求杨凌项目原始记录。用户尚未批准 TES 分层/复合证据路线；即使未来批准，批准本身也不能补齐缺失的价格基年、容量分母、部件边界或项目台账。

## 1. 本阶段回答的问题

E0-D-24 不再继续寻找一个可以直接套用的“TES 总单价”，而是回答：

> 将 E0-D-15 的 12 个 TES 所有权账户与 E0-D-20 的 4 个非燃料运行账户合并后，当前 Energy 级以上论文、官方工程报告和杨凌原始台账分别能支持什么，完整 TAC 还缺哪一类证据？

统一门禁要求每个账户逐项通过，禁止以下替代：

- 用高影响因子期刊的系统总投资替代部件价格基年和容量分母；
- 用 NREL、DLR、DOE/Sandia 等官方工程报告替代 Energy 级以上同行评议主证据；
- 用公开市场规则或全国碳市场信息替代杨凌合同、配额和实际账单；
- 把聚合系统锚点反向分摊到 12 个 TES 部件账户；
- 在证书缺失时把 D19–D23 的燃料/风险边界改写为完整 TAC 或技术赢家。

## 2. 16 个账户的统一判定

| 账户组 | 数量 | 当前判定 | 关键缺口 |
|---|---:|---|---|
| TES 有直接候选但不完整 | 8 | `DIRECT_CANDIDATE_INCOMPLETE` | 价格基年、来源 provenance、容量分母、技术边界或正式允许用途至少一项缺失 |
| TES 无直接候选 | 4 | `NO_DIRECT_CANDIDATE` | 高品位蒸汽充热换热器、中品位蒸汽充热换热器、对外供热换热器、power-block retrofit |
| 非燃料运行账户 | 4 | `PROJECT_PRIMARY_REQUIRED` | 杨凌逐时结算、碳履约账本、CHP O&M 科目拆分、双服务 TES O&M 驱动 |

严格就绪账户数为 `0/16`。因此：

```text
formal_tac_ready = false
e1_ready = false
```

这个结果没有否定公开来源的价值，而是把公开来源的用途限定为技术映射、工程量级校准或敏感性。

## 3. 三层证据角色

### 3.1 Energy 级以上同行评议

新纳入的 Zhang et al. *Energy* 论文（DOI `10.1016/j.energy.2023.130132`）直接讨论燃煤机组耦合熔盐储热改造。ScienceDirect 出版者页面给出系统设备和材料总成本及 LCOD，并且 *Energy* 官方期刊页在 2026-07-14 显示 Impact Factor `9.4`。

该论文通过用户要求的期刊等级门槛，但当前可访问记录没有闭合：

- 原始价格基年；
- 12 个账户的分项分配；
- 当前三温区、五路径、供热/发电双服务拓扑；
- FOM、VOM、更换、残值和退役互斥边界。

因此仅登记为 `aggregate_technology_anchor`，不能满足任何部件账户。期刊等级通过不等于成本证书通过。

### 3.2 官方工程报告

本阶段复核并登记：

- NREL 2011，DOI `10.2172/1031953`：高温 TES 成本模型方法；
- NREL 2013，DOI `10.2172/1067902`：100 MWe 两罐硝酸盐 CSP 的部件化成本模型；
- DOE / Black & Veatch 2016，DOI `10.2172/1335150`：约 10 MWe 高温熔盐/sCO2 概念与资本估价；
- DLR 2021：`20–22 EUR_2020/kWh_th-net` 两罐 Solar Salt 系统锚点。

这些来源可用于账户结构、缩放方法和 bottom-up 总量校准。除 DLR 已明确 2020 EUR 和净热容量分母外，其余来源的报告日期不被自动当作本研究可执行的价格基年；四项均不是当前三罐 HITEC—燃煤 CHP 拓扑的 Energy+ 正式部件组合。

### 3.3 杨凌项目原始记录

以下账户不能由公开论文或官方行业规则正式替代：

1. 分时电力结算：需要 2024 合同持仓、逐时结算价格、偏差和辅助服务账单；
2. 碳配额履约：需要核定排放、免费配额、持仓、CCER、购入量和实际成本；
3. CHP VOM：需要 H 列科目组成、燃料包含说明、固定/变动拆分和活动驱动；
4. TES VOM：需要当前双服务 TES 的项目边界和可审计驱动量。

公开来源仍可进入 `public_sensitivity`，但不能让上述账户从 `PROJECT_PRIMARY_REQUIRED` 自动转为正式。

## 4. 分层/复合路线边界

当前 canonical 产物记录：

```text
layered_route_approved = false
```

未来若研究负责人明确批准分层路线，仍必须逐字段满足：

- Energy+ 来源负责当前技术和拓扑边界；
- 官方工程报告或可审计报价负责价格、基年和容量分母；
- 映射公式、缩放、包含/排除项和防双计逐项登记；
- 4 个项目特异运行账户继续使用项目原始记录；
- 聚合锚点只做总量校准，不进入部件求和。

代码回归明确验证：仅设置 `layered_route_approved=True` 仍得到 `0/16` 严格账户和 `formal_tac_ready=false`。审批不是证据。

## 5. 可执行实现与规范产物

实现：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/formal_tac_evidence_route.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_formal_tac_evidence_route.py`
- `风光火+熔盐储热/数据采集/e0d24_formal_tac_evidence_route/`

规范 schema：

```text
tes_bess_boundary.e0d24_formal_tac_evidence_route.v1
```

输出：

- `e0d24_formal_tac_account_routes.csv`：16 行统一账户状态、候选阻断项和下一取证要求；
- `e0d24_public_source_audit.csv`：5 条公开来源的证据层、期刊指标、价格基年、分母、拓扑和允许用途；
- `manifest.json`：规范哈希、账户计数、审批状态和四条禁止性主张。

规范文件 SHA-256：

- 账户路线 CSV：`643850ead0c71c70bbe405130b8f234a69c631b25bac11cbe68a368b4bac0180`；
- 公开来源 CSV：`162a7e4fdd82db87f3729c371122ec86efddac4f47ce2643e9d9025ded7659c1`；
- manifest：`c153b11cc59067a911c1cdc24a3b3cf4d1456d19051786ccf4c9f22832ccec86`。

本地 E0 隔离环境完整回归为 `322 passed in 54.69s`，OpenBayes 为 `322 passed in 26.55s`，均关闭 pytest cache。远端使用显式正式数据合同 `TES_BESS_E0B_FORMAL_DIR=/root/e0-b-20260711-019f4f64/formal_data/e0b_formal_2024`；D24 再生成件位于 `/root/e0-b-20260711-019f4f64/e0d24_formal_tac_evidence_route_remote/`，源码、测试及三份规范化产物的 SHA-256 均与本地一致。

## 6. 下一步决策顺序

E0-D-25 已把本合同要求的四类项目原始记录转为 51 项接收字段、四账户 coverage 和空白提交模板，并强制隔离本地受限资料。当前仍为 `0/4` 运行账户可进入正式复核；接收完整后也必须先回到 D20 和本合同重新发证，不能直接把 D25 证书解释为 formal TAC。

1. 优先向杨凌取得 4 个项目特异账户的原始材料；公开检索不能替代它们；
2. 继续获取 Guccione 报价价格年及完整边界；
3. 对 4 个无直接候选的 TES 账户定向检索 Energy/Applied Energy 同等级来源；
4. 若严格路线仍无法闭合，由研究负责人另行决定是否批准分层证据路线；
5. 在 16 个账户未正式就绪前，E1–E6 和技术赢家结论继续关闭。
