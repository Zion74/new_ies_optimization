# E0-D-23 替代调度结算暴露包络

日期：2026-07-14

## 目的

把 D22 的单一 HiGHS 选择轨迹扩展为 D19 成本/弃电/PCC 合同内的联合最小—最大 PCC 重分配问题，不指定实际电价。

## 关键决定

- 两架构完整模型进入同一 MILP；
- 主成本和弃电 cap 保留，主问题整数模式重新开放；
- 24 h 精确求解；336 h 每个极值 900 秒、0.5% 请求 gap，并保留方向正确的 primal/dual；
- 336 h 用 D19 三阶段调度复制变量值作为 warm start，只改变搜索起点；
- D22 锁定轨迹作为额外可行证人，不覆盖原始 solver incumbent。

## 结果

- 24 h：最小 `26,009.981813`、最大 `26,010.174929 MWh/a`，均 gap 0；D22 值 `26,010.174918` 几乎等于最大端。
- 336 h：最小值属于 `[0, 31,172.816468] MWh/a`；最大值属于 `[31,228.008145, 983,262.066874] MWh/a`。下端使用 D22 额外可行证人，上端使用 HiGHS dual。
- 336 h 未数值闭合，不能把 dual 当成实际暴露，也不能宣布真实结算或技术赢家。

## 产物

- 代码：`tes_bess_boundary/src/tes_bess_boundary/alternative_dispatch_envelope.py`；
- 测试：`tes_bess_boundary/tests/test_alternative_dispatch_envelope.py`；
- 正式数据：`数据采集/e0d23_alternative_dispatch_envelope/`；
- 权威合同：`docs/03_sci_paper/e0_alternative_dispatch_settlement_envelope_contract.md`。

## 验证

- Windows：`316 passed in 54.51s`；
- OpenBayes：`316 passed in 26.54s`；
- CSV：`7711d894e947ee9bc942606a0936e01b4bc5c3e7015cde9e65a7f5021dac4fbd`；
- manifest：`81e1b40c1e375791c3b57b7412dcc655280d1d9b54191c156320d452cd453448`。
