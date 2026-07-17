# E0-D-20 非燃料运行成本证据会话

日期：2026-07-14

目标：检查现有项目台账、官方公开材料与高等级论文能否支持分时电力结算、碳配额履约、CHP VOM 和 TES VOM 四个正式运行成本账户。

结论：四账户均未达到正式输入标准。最重要的新发现是杨凌经济性台账 H18:H19 虽标为“运维成本”，但金额与各自发电量精确成比例，并对应同一煤价下 `385.107408 gce/kWh`；由于科目边界不明，存在与既有燃料账本重叠的风险，不能直接当作独立 CHP VOM。

本会话产出：

- `source-log.md`：来源、等级与可用边界；
- `evidence-memo.md`：四账户判定和后续取证清单；
- `docs/03_sci_paper/e0_operating_cost_evidence_readiness_contract.md`：权威研究合同；
- `tes_bess_boundary/src/tes_bess_boundary/operating_cost_evidence.py`：机器可执行门控；
- `数据采集/e0d20_operating_cost_evidence/`：规范 CSV 与 manifest。

声明：本会话没有把低等级论文或来源不明参数升级为正式证据，也没有形成完整 TAC 或储能技术赢家。
