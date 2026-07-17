# E0-D-25 项目原始证据接收与隐私隔离合同

更新时间：2026-07-14

状态：**四类非燃料运行账户的数据请求已转为机器可读合同，但项目原始证据仍未收齐。** 当前 `ready_account_count=0/4`：电力结算、碳履约和 TES VOM 为 `missing`，CHP VOM 为 `partial`（6/14 字段）。`project_data_request_ready=true`，但 `project_primary_intake_ready=false`、`formal_tac_ready=false`、`e1_ready=false`。

## 1. 本合同解决什么问题

E0-D-20 证明四个运行账户都缺正式输入，E0-D-24 又证明公开论文或官方工程报告不能替代杨凌项目台账。D25 不再继续猜价格，而是把“还需要什么”变成三份可交付数据表：

1. 51 项字段要求及验证规则；
2. 当前四账户覆盖与缺口；
3. 可直接交给项目方填写的空白提交模板。

D25 只颁发“材料已完整、可以进入正式复核”的接收证书。即使未来 51 项全部填写，也仍须回到 D20/D24 复核账户边界、证据权限、燃料重叠和技术映射；接收完整不等于正式 TAC 成立。

## 2. 四账户字段合同

| 账户 | 必需字段数 | 当前可确认 | 当前状态 | 核心缺口 |
|---|---:|---:|---|---|
| 分时电力结算 | 12 | 0 | missing | 市场主体、合同头寸、逐时/结算时段电量与价格、偏差和辅助服务账单 |
| 碳配额履约 | 11 | 0 | missing | 核查排放、免费配额、期初期末持仓、CCER、购入量与实际购入成本 |
| CHP 变动运维 | 14 | 6 | partial | 成本科目、是否含燃料、固定/变动拆分、物理驱动及纳入/排除边界 |
| TES 变动运维 | 14 | 0 | missing | 杨凌或明确标注为 sensitivity 的拓扑、价格基期、科目、驱动与边界 |

现有杨凌经济表只能确认 CHP 的机组、报告期、原始成本标签、年度金额及来源标识/定位。原始金额不由 D25 导出；由于缺少科目拆分和驱动，H 列仍不得作为正式 CHP VOM。

## 3. 隐私与外传规则

所有项目值默认标记为 `confidential_local_only`。D25 的受版本控制产物只允许输出字段定义、缺失字段、空白模板和已有杨凌来源的最小元数据，不输出提交值。

- 原始保密文档不进入 canonical、不上传服务器、不加入 Git；
- `source_locator` 默认 `do_not_export`，只在本地证据登记簿解析；
- 其他字段最多 `metadata_only`，提交值仍不得导出；
- 非杨凌工程可比资料只能另行标注为 sensitivity，不能补齐项目原始账户；
- 不得用公开价格、同类项目均值或作者假设回填缺失值；
- 不得把“模板填满”写成正式 TAC、技术赢家或 E1 已就绪。

## 4. 代码、产物与证书语义

实现：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/project_primary_evidence_intake.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_project_primary_evidence_intake.py`
- `风光火+熔盐储热/数据采集/e0d25_project_primary_evidence_intake/`

schema：

```text
tes_bess_boundary.e0d25_project_primary_evidence_intake.v1
```

规范产物：

- `e0d25_required_fields.csv`：51 行字段、单位、粒度、验证规则和隐私策略；
- `e0d25_current_coverage.csv`：4 行账户覆盖、缺失字段和接收状态；
- `e0d25_submission_template.csv`：51 行空白值模板；
- `manifest.json`：文件哈希、当前门状态、杨凌来源最小回执和禁止事项。

`certify_intake()` 只有在四账户所有必需字段均已有审核后的元数据覆盖时才能通过。证书字段 `formal_validation_required=true` 明确说明后续仍需正式账户审计；代码把 `formal_tac_ready` 和 `e1_ready` 固定为 `false`，避免接收门越权。

本地 E0 隔离环境完整回归为 `328 passed in 61.48s`，OpenBayes 为 `328 passed in 26.64s`。两端新增源码、测试、三份 CSV 与 manifest 的 SHA-256 全部一致；远端再生成目录为 `/root/e0-b-20260711-019f4f64/e0d25_project_primary_evidence_intake_remote/`。服务器只收到新增源码和测试，本地受限资料未上传。

## 5. 当前结论与下一步

当前唯一可执行的正式路线是向项目方索取：

1. 杨凌 2024 发电侧合同、结算清单或逐时/结算时段账单；
2. 机组碳核查、配额分配/持仓/清缴和实际交易台账；
3. CHP 运维会计科目明细，特别是燃料边界、固定/变动拆分及驱动量；
4. 与本文三温区、五路径、双服务边界对应的 TES O&M 报价或项目测算。

收到资料后先保存在本地隔离区，以不透明 `source_document_id` 登记；只把字段覆盖状态更新到 D25。完成接收复核后，再依次更新 D20 四账户证书和 D24 的 16 账户路线。上述两道正式门均通过前，不进入 E1。
