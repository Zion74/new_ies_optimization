# E0-D-21 影子成本稳健性会话

日期：2026-07-14

目标：在四类非燃料成本均无正式证书的前提下，不猜测项目价格，计算多大的合计或单账户不利影响才足以抹掉 E0-D-19 的同 PCC 燃料空间。

结论：

- 24 h 精确阈值为 `12.893119760 百万元/a`；
- 336 h 的稳健正区为 `<15.031096496 百万元/a`，不确定区为 `15.031096496–16.330188393 百万元/a`，稳健负区为 `>16.330188393 百万元/a`；
- 四个单账户阈值是假设“其他三个账户为零”的隔离反事实，不是账户估值；
- 正式 TAC、项目收益和 E1–E6 仍保持关闭。

产出：

- `docs/03_sci_paper/e0_shadow_cost_robustness_contract.md`；
- `tes_bess_boundary/src/tes_bess_boundary/shadow_cost_robustness.py`；
- `tes_bess_boundary/tests/test_shadow_cost_robustness.py`；
- `数据采集/e0d21_shadow_cost_robustness/`。

复现：

- 定向测试：Windows/OpenBayes 均 `6 passed`；
- 完整回归：Windows `303 passed in 49.52s`，OpenBayes `303 passed in 26.34s`；
- 代码/测试 SHA-256：`1a56f3b7…` / `c6d32bc7…`；
- thresholds/stress/manifest SHA-256：`e56e1ee0…` / `6c178255…` / `b7f6e325…`；
- 五个文件均跨平台逐字节一致。
