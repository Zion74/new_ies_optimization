# E0-D-26 研究会话记录

## 目标

复核 D23 的 24 h/336 h 替代调度极值是否受 HiGHS 容差、约束尺度、warm start 和固定整数 presolve 影响，并形成可审计的严格数值证书。

## 已确认

1. D23 的约 `5e8 CNY/a` 成本 cap 与默认绝对容差组合会产生 cold/warm start 不一致；旧 24 h 最小值不能按 9 位小数继续引用。
2. 将年度准入行无量纲化后，原单位约 `4.77e-7 CNY/a` 的残差对应归一化约 `9e-16`，可在 `1e-9` 严格阈值下正确审计。
3. 已固定的主模型整数变量可等价移除 integrality；否则 336 h HiGHS 会先修复出可行 LP，再在 MIP presolve 中报告无穷界。
4. `optimal` 标签不等于完整证书。336 h 条件面最大化有严格可行 incumbent，但没有有限 dual。
5. 全局求解必须显式接收条件面可行证人，并检查全局 incumbent 不得劣于该子集证人。
6. 8 个原始探针、规范 CSV、manifest 与 execution sidecar 已从 OpenBayes 下载，本地—远端逐文件 SHA-256 一致；manifest 反向锁定探针、sidecar、上游数据和源码。
7. OpenBayes 定向回归 `14 passed in 0.49s`，完整回归 `334 passed in 27.26s`；仅使用 HiGHS。

## 当前数值

- 24 h 全局严格包络：`26,010.171143–26,010.174918 MWh/a`；
- 336 h 最小化严格区间：`[0, 15,594.993900] MWh/a`；
- 336 h 最大化当前严格区间：`[36,382.462799, 1,362,149.106858] MWh/a`；
- 336 h 仍未全局闭合，不是实际价格、TAC 或技术赢家。

## 复现环境

OpenBayes 60 CPU / 97 GiB，Python 3.10.18，Pyomo 6.10.1，highspy 1.15.1；求解器仅使用 HiGHS。源码、原始探针和规范汇总分别见 `tes_bess_boundary/`、远端 `e0d26_numeric_normalized/` 与 `数据采集/e0d26_numerical_certification/`。
