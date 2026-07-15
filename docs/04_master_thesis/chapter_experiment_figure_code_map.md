# 硕士论文：章节 / 实验 / 图表 / 代码映射

更新时间：2026-07-15

除明确写出完整路径外，本文件中的代码路径均相对于 `风光火+熔盐储热/tes_bess_boundary/`。D38–D43 失败已登记。D42 保留 BESS 下界 `1,144,950,604.8368804 CNY`，但 TES R0 无合法证书，Hybrid 未启动。D43 唯一一次正式复算中，两个冻结 dual 均通过准入，但两个证书 child 都在约 1800.49 s 硬墙钟前未完成且无 result/certificate，状态 `no_strict_certificate`。该下界不是可行方案或项目 TAC，不能形成技术排序。严格证据路线仍为 `0/16`，项目运行账户为 `0/4`；正式 TAC、新的三架构严格证书路线与 E2-E6 批量入口尚待完成。

## 1. 第 2 章：系统、数据与统一模型

| 编号 | 内容 | 目的 | 代码 / 数据 | 状态 |
|---|---|---|---|---|
| T2-1 | 2024 年 8784 h 数据审计 | 锁定时区、单位、缺失、同步和边界 | `data.py`、`raw_heat.py`、`heat_dataset.py`、`heat_adapter.py`、原始机组数据 | E0-B 正式质量数据及 E0-C 主/敏感性消费规则均已生成并跨平台复现 |
| T2-2 | 双机 CHP 可行域与煤耗校准 | 建立热致强迫出力和燃料面 | `components/chp.py`、机组台账 | 厂界有效热、厂用电率、相邻段一维 PWL 与三种 98–105 MW 规则已实现；二维热增量燃料仍无证据 |
| T2-3 | BESS 单元验证 | 验证 P/E、SOC、退化和更换 | `components/bess.py`、`economics.py` | AC SOC、两锚点、更换/残值、EFC 与 2024 CNY 转换机制通过；cell/PCS/BoP 正式指数快照待补 |
| T2-4 | 双品位 TES 单元验证 | 验证 HT/MT、端口、盐量、品位方向、分部件寿命和缺证成本风险 | `components/molten_salt.py`、`tes_loss_auxiliary.py`、`model.py`、`formal_tes_costs.py`、`tes_break_even*.py`、`operating_cost_evidence.py`、`project_primary_evidence_intake.py`、`shadow_cost_robustness.py`、`pcc_settlement_exposure.py`、`alternative_dispatch_envelope.py` | 三温区/五端口、损失/辅机、成本门、同 PCC 燃料空间、影子成本传播、调度价差暴露和 51 字段取证门通过；12 个 TES 与四个项目运行账户仍阻断，阈值只能作 sensitivity |
| T2-5 | HiGHS 求解验证 | 验证可行性、MIP gap、复现和资源占用 | `solver.py`、`heat_bridge.py`、D17–D32 数值模块 + `highspy` | D26 使用无量纲 cap、`1e-9` 容差和已知证人；D27 分离方向 dual 与全局 dual，24 h 精确闭合；D29/D30 将 336 h 上界降至 `777,141.368858 MWh/a`；D31 完成 1440 个 OBBT LP但 336 h 增量不足 `0.1%`；D32 完成 15 个联合块 dual 与 24 h reopened 等价门，但 14 块和为 `1,930,160.868929 MWh/a`，高于 D30，故未生成新 336 h dual |

建议图表：系统边界图、2024 数据覆盖图、CHP 热电可行域、BESS/TES 能量守恒测试、求解器验收表。

## 2. 第 3 章：源荷匹配与灵活性服务需求识别

| 编号 | 内容 | 目的 | 代码 / 数据 | 状态 |
|---|---|---|---|---|
| T3-1 | 杨凌源荷冲突指标 | 识别热致强迫发电与风光富余的时序重叠 | 复用 IEMI/EQD 思想；杨凌适配层待建 | 待定义最小版本 |
| T3-2 | 风光接入与灵活性服务指标 | 输出风光规模、ε、冲突功率和持续能量，不预设设备容量 | `run.py` / `cchp_gaproblem.py` 方法资产 + 新统一模型 | 待迁移 |
| T3-3 | 第 4 章接口状态提取 | 输出统一的 `H* / G* / R_W / I_HC`、ε、关键周和低/中/高冲突状态 | 计划 `scenarios.py` | 待实现 |
| T3-4 | 方法辅助验证 | 证明指标不是杨凌特例 | 德国 / 松山湖已有结果 | 可选，不作为主案例 |

建议图表：源荷/热约束冲突指数、关键周剖面、风光—灵活性规划曲线、三类物理状态。

## 3. 第 4 章：BESS—熔盐 TES 适用边界

| 编号 | 内容 | 目的 | 代码 / 数据 | 状态 |
|---|---|---|---|---|
| T4-1 / E1 | 受控价值分解 | 解释 BESS 与 TES 的价值来源 | `planning_model.py`、`e0d34_endogenous_capacity_sample.py`、`e0d35_tes_materiality.py`、`e0d35_materiality_bundle.py`；`_ch4_p1_milp_compare.py` 仅作旧原型 | D35–D37 结论已冻结；D38/R1/D39 失败均已登记。D41 三架构严格证书通过前不得恢复机制扫描或写成技术赢家 |
| T4-2 / E2 | 同服务 ε 前沿 | 建立公平经济比较 | `model.py`、`scenarios.py` | 待实现 |
| T4-3 / E3 | 热约束 × 通道紧张度地图 | 识别物理选择边界 | `run_sweep.py`、`postprocess.py` | 待实现 |
| T4-4 / E4 | 时长 × 相对成本地图 | 识别经济选择边界 | 同上 | 待实现 |
| T4-5 / E5 | 8784 h 全年证据与时间方法 | 建立不依赖失真代表期的正式边界路线 | D36–D39 失败证据；D40/D41 合同与失败证据；D42 全链证据；D43 合同、只读编排器、测试与正式失败证据 | D43 唯一一次正式复算已结束：两个 child 均触及 1800 s 硬墙钟且无证书。D43 不得重跑；Hybrid、全年上界修复与技术排序仍禁止，后续需另立严格数值路线合同 |
| T4-6 / E6 | 确定性稳健性 | 检查边界移动 | `run_sweep.py` | 待实现 |

建议图表与 SCI 相同：价值分解、ε 前沿、物理主地图、经济主地图、全年验证和边界敏感性。

完整设计见：

- `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
- `docs/04_master_thesis/chapter4_tes_ees_regime_boundary_plan.md`

## 4. 第 5 章：Agentic 决策支持

| 编号 | 内容 | 目的 | 代码 / 数据 | 状态 |
|---|---|---|---|---|
| T5-1 | Scenario Schema 与校验器 | 将自然语言输入转为可复现参数 | 待设计，复用场景化接口经验 | 待实现 |
| T5-2 | 工具调用与任务编排 | 安全调用第 3、4 章优化器 | 待实现 | 待实现 |
| T5-3 | 独立物理审计 | 阻止单位、边界、能量守恒和证据错误 | 待实现 | 待实现 |
| T5-4 | 三流程对照 | 人工脚本 vs 普通 LLM vs Agentic | 预注册任务集 | 待设计 |
| T5-5 | 人机协同评价 | 检验准确性、复现、违规漏检和耗时 | 评价脚本待建 | 待实现 |

建议图表：Agentic 工作流、任务集结构、参数抽取/违规识别结果、复现率与耗时、失败案例矩阵。

详细计划见 `docs/04_master_thesis/chapter5_agentic_decision_support_plan.md`。

## 5. 明确删除的旧实验

以下内容不再属于硕士论文主实验：

- 多能负荷预测精度；
- 日前预测 vs 完美信息调度；
- 预测误差传播；
- `Std / EQD / EQD+CB` 的预测鲁棒性对比。

已有预测成果可以独立投稿会议，不需要为了大论文再扩建预测模块。
