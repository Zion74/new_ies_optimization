# SCI 论文：最新逻辑结构

更新时间：2026-07-13

## 1. 定位

当前主 SCI 已从“EQD + 卡诺电池”调整为：

> **热约束型燃煤 CHP 中锂离子 BESS、双用途熔盐 TES 与混合储能的公平比较、价值机理和技术选择边界。**

建议题目方向：

> *Technology-selection boundaries between lithium-ion batteries and dual-service molten-salt thermal storage in heat-constrained CHP systems*

杨凌 2×350 MW 系统是工程验证对象；论文结论必须由可迁移的归一化边界与全年验证共同支撑，不能只报告一个案例下的弃风率。

## 2. 核心科学问题

1. 如何在不同能量载体、效率、寿命和端口结构下公平比较 BESS 与熔盐 TES？
2. 热负荷造成的 CHP 强迫电出力如何改变储能价值来源？
3. 供热强度、风电接入和公共并网点拥塞如何共同触发 BESS—TES—Hybrid 的排序反转？
4. 时长和相对成本怎样移动该物理边界？
5. 代表周得到的边界能否通过杨凌 2024 年 8784 h 时序验证？

## 3. 论文主张

本文不主张“熔盐普遍优于电池”。主张限定为：

> 在相同热负荷安全和新能源消纳目标下，热致强迫发电与公共并网点拥塞改变了两类储能的边际价值；由此可形成可解释的 BESS—TES—Hybrid 技术选择区域和经济无差异带。

三条贡献线：

1. **机理贡献**：将价值分为电量时移、热供给替代和 CHP 强迫出力释放。
2. **方法贡献**：采用技术特定的功率—能量—寿命成本联合 MILP，在同服务下比较最小年化成本，而不是同 MW/MWh。
3. **工程贡献**：以热约束 × 通道紧张度和时长 × 相对成本两张地图给出选择边界，并用杨凌真实双机全年数据回代。

## 4. 非协商模型边界

- 架构：无储能 / BESS / TES / BESS+TES；
- 求解：确定性容量—运行综合 MILP；
- 主求解器：HiGHS；
- 主公平口径：同供热安全、同弃风上限下的最小年化总成本；
- 对偶口径：同增量年化预算下的最低弃风率；
- BESS：独立充电功率、放电功率和电量容量，计退化、替换、残值与寿命；
- TES：高温/中温库存及电加热、抽汽充热、发电、级联和供热端口分别定容计费；
- CHP：两台机组分别建模，保留启停、爬坡、热电可行域、强迫出力和变煤耗；
- 数据：代表周用于扫描，8784 h 用于关键点验证。

完整模型、实验水平和验收标准见：

- `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
- 当前 E0 实现与阻断项见 `docs/03_sci_paper/e0_validation_status.md`

## 5. 推荐章节结构

1. `Introduction`：问题、质量筛选后的文献空白、贡献边界。
2. `System description and data`：杨凌双机、签约风电、本地光伏、供热义务和公共并网点。
3. `Technology-specific models`：CHP、BESS、双品位熔盐及成本寿命模型。
4. `Fair planning and boundary identification`：综合 MILP、ε-约束、公平口径、选择判据和机理指标。
5. `Experimental design`：代表周、网格、边界加密、全年回代和确定性敏感性。
6. `Results and discussion`：
   - 6.1 模型与杨凌基准验证；
   - 6.2 受控机理实验；
   - 6.3 同服务成本—消纳前沿；
   - 6.4 热约束—通道紧张度选择地图；
   - 6.5 时长—相对成本边界；
   - 6.6 8784 h 验证与确定性稳健性；
   - 6.7 适用范围、工程含义与限制。
7. `Conclusions`：只收束已验证的机制和边界，不外推到调频、黑启动或所有电力系统服务。

## 6. 主图逻辑

论文只保留两张真正承担结论的边界图：

1. **物理适用域**：归一化热约束 × 通道紧张度，按三档风电容量分面；颜色为 No storage / BESS / TES / Hybrid / Indifferent / Infeasible。
2. **经济适用域**：储能时长 × TES/BESS 相对年化成本，按低、中、高物理冲突分面。

其余图用于验证、解释和敏感性，不再堆积孤立的一维扫描。

## 7. 明确排除

本 SCI 不加入：

- 负荷预测；
- 随机或鲁棒优化；
- 蒙特卡洛概率边界；
- 滚动调度 / MPC；
- Agentic 或 LLM 决策支持；
- 德国与松山湖案例。

源荷匹配方法和德国/松山湖结果属于独立成果与硕士论文辅助方法证据，不进入本 SCI 主线。

## 8. 证据与代码状态

- 高质量文献证据包：`风光火+熔盐储热/research-sessions/2026-07-11-tes-ees-regime-boundary/`；
- 现有 `_ch4_*.py` 为探索原型，可复用数据与局部约束，但不足以支撑公平边界结论；
- 当前 `论文撰写/paper/` 仍是旧 EQD/Carnot 稿件源码，不视为新 SCI 正式稿；
- `风光火+熔盐储热/tes_bess_boundary/` 已建立独立 `Pyomo + highspy` 包；E0-D-5–D-16 已锁定 TES 物理/作者筛查、BESS 正式账本、TES 成本门和无罚值 EAC 内核。E0-D-17 加入实际年度结果适配与 24 h 冬季切片；E0-D-18 以对数 PWL、连续启停包络和端口 Big-M 将 336 h 双周候选压缩 60.87% 未固定二进制，并在 0.48% 主 gap 下形成 57.572–59.818 百万元/a 的燃料范围 EAC 区间。24 h/336 h 规范产物均跨平台一致；
- 原始证据审计确认杨凌表内没有供回水温度、抽汽温压或可直接识别三罐逐时损失/泵耗的设备参数。MT 继续使用 0.25/0.50/0.75 作者显热分割；E0-D-9B-1/2 数值均登记为作者敏感性。Guccione `140 EUR/kWe` 仍缺报价价格年，且罐、循环、三条换热/蒸汽发生路径、power-block retrofit、项目附加费和寿命项也未闭合；DLR `20–22 EUR_2020/kWh_th-net` 仅为两罐 Solar Salt 工程聚合锚点。TES 正式来源、系统级完整 TAC、endogenous capacity 和结构化代表周仍未闭合；E0-D-18 仍不能形成技术赢家，因此不得进入 E1 或批量边界实验。合同见 `e0_tes_break_even_contract.md`、`e0_tes_break_even_adapter_and_exploration_contract.md` 与 `e0_tes_two_window_performance_and_interval_contract.md`。

## 9. 与旧 SCI 文档的关系

`docs/03_sci_paper/` 中 2026-04 的 EQD/Carnot 审稿、重设计、出图和服务器清单保留为独立旧稿的历史资产，但不再定义当前主 SCI。当前只以本文件、模型实验设计、实验映射和图表计划为权威。
