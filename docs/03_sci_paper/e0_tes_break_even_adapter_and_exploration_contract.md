# E0-D-17 年度结果适配与探索窗口合同

更新时间：2026-07-13

状态：**E0-C 年度结果到 E0-D-16 盈亏平衡内核的保守适配已实现；2024-01-01 的 24 h 探索窗口已通过本地/远端零 gap 复现。本文保留 E0-D-17 的历史 formulation 与未闭合两周记录；当前两窗口权威状态已由 E0-D-18 合同取代。** 本合同不构成正式全年 TAC、TES CAPEX、杨凌风光实测基线或 E1 技术比较。

## 1. 解决的问题

E0-D-16 只定义了“同服务、无人工罚值”的全系统 TES 年化所有权成本上限。E0-D-17 增加三条实际接缝：

1. 年度模型公开加权可用新能源、PCC 外送和弃电服务上限；
2. 将实际 E0-C 年度解转换为 E0-D-16 的可比结果，并逐项剔除 TES 所有权账户；
3. 用锁定输入跑一个 24 h 探索窗口，检查适配、物理路径、成本差值和跨平台复现。

## 2. 无罚值服务与退化解处理

弃电惩罚始终为 0。每个年度解分两阶段求解：

1. 用 HiGHS 最小化当前已知年度成本；
2. 固定第一阶段 incumbent 的全部整数决策，并在成本不高于第一阶段值加数值容差的条件下最小化弃电。

因此服务 ID 明确写为 `primary_incumbent_conditional_no_storage_plus_tolerance:*`。它表示“成本最优整数方案条件下的最小弃电”，不是对所有同成本整数方案重新执行全局字典序搜索。该处理消除连续新能源分配退化，同时避免用货币罚值虚构 TES 价值。

`model.py` 的年度公开审计新增：

- `weighted_renewable_available_mwh`；
- `weighted_pcc_export_mwh`；
- `curtailment_service_id / curtailment_ceiling_mwh`；
- 主目标与次目标 MIP gap、主成本容差和固定整数变量数量。

## 3. 结果适配门

`tes_break_even_adapter.py` 只接受：

- `appsi_highs` 的最优年度解；
- 显式且一致的弃电服务；
- 零人工弃电罚值；
- PCC、供热和循环边界残差通过；
- 实际弃电不超过上限；
- 正的可用新能源量。

适配器保留燃料等已知运行成本、非 TES 固定成本和经验证的 BESS 成本；剔除 `TES_COMPONENT`、`SALT_TO_STEAM_GENERATOR`、`EXISTING_TURBINE_REUSE`、`NEW_POWER_BLOCK` 全部 TES 所有权成本。现有 E0-C 尚缺 CHP VOM、碳、电力结算和 TES VOM，因此强制 `non_tes_scope_complete=false`，结果只能是 `exploratory_threshold_only`。

## 4. 24 h 探索切片

### 4.1 输入与设备

- 热负荷：正式 E0-B `heat_net_mw` 非负截断，SHA-256 `a89d3654600eac53768529ad9ef6d304b7d756783359fc1f1db95fd2bd4c709e`；
- 风光形状：2019 资源年映射到 2024 日历的旧数据，SHA-256 `515892a944dacf75c4bae3f41f008b01924f30dbd9b004d132afbdb7c0e25b6f`，不是杨凌 2024 实测风光；
- 固定规模：风电 1050 MW、光伏 200 MW、PCC 700 MW；
- TES：1200 MWhth，电加热/电输出/热输出各 150 MW，MT=285 °C，采用 E0-D-9 基准损失/泵耗作者敏感性；
- TES 发电路径只作拓扑分类：盐—蒸汽发生器未定价、复用现有汽轮机零新增资本；两项均作为 TES 所有权账户从阈值比较中剔除；
- 求解：HiGHS 单线程、随机种子 0、MIP relative gap 0。

### 4.2 结果

2024-01-01 的 24 h 以每小时权重 366 年化，仅用于冬季典型日筛查：

| 指标 | 结果 |
|---|---:|
| 弃电服务上限 | 578,534.890444 MWh/a |
| 比较架构弃电 | 578,534.890132 MWh/a |
| TES 候选弃电 | 369,164.905507 MWh/a |
| 弃电减少 | 209,369.984626 MWh/a |
| 燃煤节约 | 70,222.107616 tce/a |
| PCC 外送变化（候选－比较） | -883,593.281085 MWh/a |
| TES 辅机电量 | 10,140.311091 MWh/a |
| TES 全系统最大 EAC | 56,238,077.105431 CNY/a |
| 按完整显热库存归一化 | 46.865064 CNY/(kWhth·a) |
| 按 150 MW 端口归一化 | 374.920514 CNY/(kW·a) |

这是燃料单项范围的冬季典型日年化上限。不得写成全年节煤、正式 TES 成本、部件单价或技术赢家；PCC 外送下降也说明后续必须补齐电力结算后再谈系统经济性。

## 5. 历史两周性能状态

336 h 全级联 TES 与双机 UC 的主 MILP 在本地 10 min 和 OpenBayes 15 min 受控预算内均未形成可接受的完整双窗口产物；固定第一阶段整数只消除了第二阶段重复整数搜索，未消除主 MILP 规模瓶颈。因此：

- 不生成两周 CSV 行；
- 不把超时解释为 TES 经济性为零或为负；
- 下一步先强化 TES 流量 Big-M、可达状态和 UC/TES 联合 formulation，再重跑两周门。

上述是 E0-D-17 结束时的历史判定。E0-D-18 已完成该强化：24 h 精确 gap 0，336 h 主目标 gap 0.004800、固定整数次目标 gap 0，并将非零主 gap 传播成 EAC 上下界。当前数字与允许表述以 `e0_tes_two_window_performance_and_interval_contract.md` 为准。

## 6. 复现证据

规范产物位于 `风光火+熔盐储热/数据采集/e0d17_tes_break_even/`：

- `e0d17_tes_break_even.csv`：SHA-256 `ab2dbd3e77068826e41785f585ffe4e70c8ae4c72baaedde054428f265b780f3`；
- `manifest.json`：SHA-256 `5cec9f0c436bf3c5ea44e8d4cd170939c4fd4dc168c9f31e414feb92ca79a1e5`；
- `execution.json`：非规范运行时 sidecar。

CSV 浮点值统一保留 6 位小数；本地 Python 3.11/Windows 与远端 Python 3.10/Linux 生成的 CSV/manifest 哈希完全一致。生成 E0-D-17 产物时的完整回归为本地 `284 passed in 76.16s`、OpenBayes `284 passed in 21.37s`；E0-D-18 里程碑为 `288 passed`，当前 E0-D-23 完整回归已升级为本地 `316 passed in 54.51s`、OpenBayes `316 passed in 26.54s`。

复现命令：

```bash
python -m tes_bess_boundary.e0d17_exploration \
  --heat /path/to/e0b_heat_hourly_2024.csv \
  --vre /path/to/legacy_vre_2024.csv \
  --output /path/to/e0d17_tes_break_even \
  --window winter_day_20240101
```

省略 `--window` 会尝试 E0-D-17 锁定的 24 h 与两周窗口；该入口只用于复现历史基线，新的性能验收与区间导出使用 `e0d18_performance.py`。

## 7. 下一接口

E0-D-18 已完成两周 MILP 强化、性能验收和界区间传播。下一步 E0-D-19 补齐 CHP VOM、碳、电力结算和 TES VOM 等同范围年度成本；TES 12 账户、正式 TAC、结构化代表周和 endogenous capacity 仍是 E1 前置条件。
