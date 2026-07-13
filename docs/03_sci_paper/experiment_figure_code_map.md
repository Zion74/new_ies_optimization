# SCI 论文：实验 / 图表 / 代码映射

更新时间：2026-07-13

## 1. 当前实验链

| 编号 | 目的 | 核心设置 | 主输出 | 代码状态 |
|---|---|---|---|---|
| E0 | 验证数据、物理与 MILP | 双机 CHP、BESS、HT/MT TES、PCC、寿命成本 | 可行域、能量守恒、现金流审计、三 MT 损失标定、三档底层泵耗与五路径运行审计、成本证据资格门、BESS 正式账本与 TES 12 账户就绪度、HiGHS 状态与求解误差 | E0-D-14 已闭合完整 fixed-capacity BESS 生命周期账本；E0-D-15 已隔离 TES 部件账户与聚合锚点，但 TES 正式候选仍为零；本地 273 项通过，远端最近 258 项通过 |
| E1 | 隔离价值机制 | No storage / BESS / P2H / TES-E / TES-H / dual TES；控制后恢复真实参数 | 电移峰、热替代、强迫出力释放 | `_ch4_p1_milp_compare.py` 仅为旧原型 |
| E2 | 建立公平成本—消纳前沿 | 四架构 × 5 个共同可行 ε 目标 | TAC—弃风前沿、容量、煤耗、碳排、启停 | 待实现综合 MILP |
| E3 | 识别物理选择边界 | 6 档 \(H^*\) × 5 档架构无关 \(G^*\) × 3 档风电 × 四架构 | BESS / TES / Hybrid / No storage / Indifferent / Infeasible 地图 | `_ch4_p4_sensitivity.py` 只能复用扫描经验 |
| E4 | 识别时长—成本边界 | 低/中/高 3 锚点 × 6 档服务时长 × 7 档 TES 成本倍率；边界二分加密 | 经济边界与边界移动量 | 待实现 |
| E5 | 验证代表周与真实点 | 6 个代表周 + 年末 48 h；三状态预验证；12 点固定容量 8784 h；6 点全年重优化 | 代表周误差、后悔值、全年赢家 | `_ch4_p3_typdays.py` 需升级为代表周 |
| E6 | 确定性稳健性 | 4 锚点 OAT：循环寿命、TES 效率、碳价、价差、退化口径和可比资源年 | 边界移动与结论稳定区间 | 待实现；不做随机分析 |

完整水平、算例预算与验收标准见：

- `docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`

## 2. 主图 / 主表映射

| 编号 | 内容 | 对应实验 | 主要字段 | 状态 |
|---|---|---|---|---|
| Fig 1 | 联营组合、双机 CHP、PCC、BESS 与双品位 TES 拓扑 | E0 | 物理端口与边界 | 待绘制 |
| Fig 2 | CHP 热电可行域、热致最小电出力与模型校准 | E0 | `P/Q/fuel/u` | 待生成 |
| Fig 3 | BESS、TES-E、TES-H、dual TES 价值分解 | E1 | 电移峰、热替代、强迫出力释放、TAC | 待生成 |
| Fig 4 | 杨凌基准点四架构成本—弃风 ε 前沿 | E2 | `epsilon/TAC/curtailment/capacity` | 待生成 |
| Fig 5 | \(H^*\times G^*\) 技术选择地图，三档风电分面 | E3 | winner、次优差、不可行、容量、`I_HC`、`Gamma_C0` | 待生成；全文核心图 |
| Fig 6 | 时长 × TES 相对基准成本倍率，三类物理冲突分面 | E4 | `D/kappa_T/winner/regret` | 待生成；全文核心图 |
| Fig 7 | 边界点代表周与 8784 h 结果对比 | E5 | TAC、弃风、煤耗、容量、赢家 | 待生成 |
| Fig S1 | 边界二分加密与 5% 无差异带 | E3/E4 | refined grid、regret | 待生成 |
| Fig S2 | 参数变化引起的边界移动 | E6 | 边界位移和无差异带 | 待生成 |
| Fig S3 | 4 个 medoid 周、2 个极端周与年末 48 h | E5 | 周权重、覆盖和极端事件 | 待生成 |
| Tab 1 | 系统物理、价格与碳参数 | E0 | 来源、基准值、范围、等级证据 | 待核查 |
| Tab 2 | BESS 与 TES 功率、质量、效率、寿命和成本参数 | E0 | 技术特定参数、成本拆分、价格基年与证据等级 | BESS 已闭合；TES 12 个账户均保持 BLOCKED，DLR 2020 EUR 两罐值只作工程聚合校准 |
| Tab 3 | 公平比较口径与四架构定义 | E1/E2 | 服务约束、容量变量、成本项 | 待整理 |
| Tab 4 | 杨凌基准点最优配置与运行结果 | E2 | TAC、P/E/盐量、弃风、煤耗、碳排 | 待生成 |
| Tab 5 | 代表周—全年验收 | E5 | 误差、后悔值、MIP gap、运行时间 | 待生成 |
| Tab S1 | HiGHS 求解性能 | E0-E6 | gap、时间、RSS、失败重试 | 待生成 |

## 3. 现有代码的科学地位

| 文件 | 定位 | 是否可直接形成主结论 |
|---|---|---|
| `风光火+熔盐储热/_ch4_p1_milp_compare.py` | 固定容量的机制探索 | 否 |
| `风光火+熔盐储热/_ch4_milp.py` | 双机 + PCC + MILP 原型 | 否，需拆分 TES 端口并加入容量成本 |
| `风光火+熔盐储热/_ch4_p4_sensitivity.py` | 固定 TES 的一维敏感性 | 否 |
| `风光火+熔盐储热/_ch4_p3_typdays.py` | 典型期原型 | 否，需代表周与全年验证 |
| `风光火+熔盐储热/_ch4_p3_nsga.py` | 启发式容量搜索原型 | 否，核心改为综合 MILP |
| `风光火+熔盐储热/杨凌_合并逐时_2024_清洗.csv` | 旧 2024 年统一输入候选 | 否；仅保留历史探索，热数据以 E0-B 新产物为准 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/e0b_heat_source_ledger_2024.csv` | 52,707 行源证据台账 | 是；保留重复、非网格、原值、修复值与质量标志 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/e0b_heat_hourly_2024.csv` | 8,784 h net / forward / zero-sensitivity | 是；进入模型前仍须显式选择非负需求适配 |
| `风光火+熔盐储热/数据采集/e0b_formal_2024/manifest.json` | E0-B schema v2 构建合同 | 是；记录源 SHA、规则、计数、签名与输出 SHA |
| `风光火+熔盐储热/数据采集/e0c_heat_demand_adapter/` | 三份全年非负需求、六份窗口产品及真实双机桥接诊断 | 是；主口径/敏感性、修改审计、规范哈希和 runtime sidecar 分离 |
| `风光火+熔盐储热/杨凌机组数据/` | 机组台账、电功率与供热原始材料 | 核心工程证据，需脱敏和口径记录 |

## 4. 当前新代码映射

`风光火+熔盐储热/tes_bess_boundary/` 已建立，使用独立 `src/` 包和 Pyomo + HiGHS，不继续叠加 `_ch4_*` 单文件脚本：

| 模块 | 职责 | 对应实验 | 状态 |
|---|---|---|---|
| `src/tes_bess_boundary/data.py` | 单位、8784 h 完整性与恒等式校验 | E0/E5 | 已实现结构审计 |
| `src/tes_bess_boundary/raw_heat.py` | 原始 Excel A 列、源追溯、10 min 网格、重复与异常审计 | E0 | 已实现 |
| `src/tes_bess_boundary/heat_dataset.py` | 正式源台账、三口径小时数据、质量标志与 manifest | E0/E5 | E0-B 已实现并通过真实双构建 |
| `src/tes_bess_boundary/heat_adapter.py` | 正式全网格/manifest 校验、三口径非负消费规则、窗口与修改审计 | E0/E5 | 已实现；三份全年产品与六份窗口产品跨平台哈希一致 |
| `src/tes_bess_boundary/heat_bridge.py` | 两个正交窗口 × 三口径的真实双机 No-storage/HiGHS 桥接诊断 | E0 | 六案均 optimal、gap 0；规范结果与 runtime sidecar 分离 |
| `src/tes_bess_boundary/heat_bridge_cli.py` | 一键重建 E0-C 适配与桥接证据 | E0 | 已实现，本地/OpenBayes 复现一致 |
| `src/tes_bess_boundary/solver.py` | 确定性 `appsi_highs` 配置与求解元数据 | E0-E6 | 已实现最小版本 |
| `src/tes_bess_boundary/economics.py` | 项目 NPV/EAC、价格转换、分部件更换/残值/FOM、BESS 两锚点、防双计与年度计分合同 | E0/E2-E6 | E0-D-1–D-3 已实现；2024 CNY、转换审计和三角色成本分类通过独立金标准，正式数值待换算 |
| `src/tes_bess_boundary/price_basis.py` | 官方 CPI/HICP/汇率快照、逐源哈希与唯一转换构造 | E0/E2-E6 | E0-D-4 已实现；正式快照本地/OpenBayes 哈希一致 |
| `src/tes_bess_boundary/tes_cost_mapping.py` | 盐/显热/三罐/五端口容量基准、部件温区覆盖与寿命 portfolio 绑定 | E0/E2-E6 | E0-D-5 已实现；本地容量、端口和温区金标准通过，正式成本值待闭合 |
| `src/tes_bess_boundary/formal_tes_costs.py` | TES 12 账户正式来源就绪度、聚合锚点隔离与复合证据审批 | E0/E2-E6 | E0-D-15 已实现；当前全部账户阻断，不颁发 TES 正式证书 |
| `src/tes_bess_boundary/tes_topology_evidence.py` | 五条 TES 路径的 Energy+ 证据等级、模块化合成与本文扩展披露 | E0/E2-E6 | E0-D-6 已实现；`MT→LT` 供热级联必须显式声明为 proposed extension |
| `src/tes_bess_boundary/tes_heat_delivery.py` | 温度来源身份、MT→LT 两端夹点、HITEC 温区、可交付热量与盐/水流量 | E0/E2-E6 | E0-D-7 已实现；120/70 °C 只作核心参考情景，MT 不由夹点唯一确定 |
| `src/tes_bess_boundary/tes_temperature_scenarios.py` | MT 归一化低品位焓占比、三点作者敏感性、来源身份与逐点认证 | E0/E6 | E0-D-8 已实现；232.5/285/337.5 °C 不得写成现场或论文直接值 |
| `src/tes_bess_boundary/tes_loss_auxiliary.py` | 库存—环境温差损失、固定伴热、五路径比泵耗、五路径累计吨位、参数身份与时间步复合 | E0/E2-E6 | E0-D-9A/9B-2 已实现；正式杨凌参数仍缺失 |
| `src/tes_bess_boundary/tes_loss_calibration.py` | Trevisan/Klasing 聚合锚点、低/基准/高损失—伴热作者集、三 MT 等留存反标定与聚合反推量审计 | E0/E6 | E0-D-9B-1 已实现；三 MT 的 24 h Pyomo/HiGHS 交叉验证通过 |
| `src/tes_bess_boundary/tes_pump_calibration.py` | Trevisan 液压锚点、Wang HITEC 物性、40/50/200 kPa 三档五路径泵耗、45 MWhth 标准循环与 3×3 确定性产物 | E0/E6 | E0-D-9B-2 已实现；结果是作者筛查，不是杨凌现场标定 |
| `src/tes_bess_boundary/cost_evidence.py` | 期刊层级、价格基年、容量分母、技术边界、底层出处和允许用途的正式成本认证门 | E0/E2-E6 | E0-D-15 扩展为 16 条记录并区分可审计一手报价；当前只认证 Rahman BESS，TES 继续阻断 |
| `src/tes_bess_boundary/formal_bess_costs.py` | Rahman 2019 USD 原值、边界拆分、三接缝策略、统一价格转换和完整 fixed-capacity BESS 年度经济构建 | E0/E2-E6 | E0-D-14 已实现；原始来源对象继续显式未决，resolved contract 为 `formal_fixed_capacity_ready=True` |
| `src/tes_bess_boundary/sensitivity_cost_anchors.py` | NREL/OEDI 4 h BESS 工作簿哈希加载、功率/可用能量双分母 CAPEX、含 augmentation FOM 防双计与 2024 CNY 转换 | E0/E4/E6 | E0-D-11 已实现；仅作官方工程敏感性锚点，`formal_baseline_eligible=False` |
| `数据采集/e0d11_sensitivity_cost_anchors/` | NREL 2022 ATB v3 原工作簿、精确单元格提取 JSON 与 manifest | E0/E4/E6 | 本地/OpenBayes 哈希一致；RTE 0.85/0.86 冲突已排除，不随成本锚点入模 |
| `research-sessions/2026-07-13-e0d12-formal-cost-closure/` | Energy+ BESS/TES 来源日志、主张—证据图、访问日志和机器候选矩阵 | E0/E2-E6 | 13 个候选中 Rahman BESS 为唯一 `formal_candidate=true`；Guccione/TES 继续阻断 |
| `research-sessions/2026-07-13-e0d14-bess-join-closure/` | BESS 寿命所有权、AC 放电 VOM 与 PCS 5–100 MW 口径的证据—决策记录 | E0/E2-E6 | E0-D-14 已闭合 fixed-capacity BESS 三接缝；TES/系统 TAC 继续阻断 |
| `research-sessions/2026-07-13-e0d15-tes-formal-cost-closure/` | Trevisan/Klasing/Li/Guccione/DLR 逐源复核、访问日志与 TES 正式账户判定 | E0/E2-E6 | 严格路线未闭合；DLR 仅为 2020 EUR 两罐工程聚合锚点 |
| `docs/03_sci_paper/e0_formal_cost_closure_audit.md` | 严格证据门、关联证据政策及当前证书边界 | E0/E2-E6 | Rahman 来源层证书已颁发；完整 TAC 与 TES 证书未颁发 |
| `docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md` | Rahman 关联证据、2019 USD→2024 CNY、三接缝决策与 fixed-capacity BESS 账本 | E0/E2-E6 | E0-D-14 权威合同 |
| `src/tes_bess_boundary/components/chp.py` | 台账凸包、毛/净口径、显式低负荷规则、UC 与精确 PWL | E0-E6 | fixed-capacity 调度合同已实现；二维燃料面与经济敏感性待补 |
| `src/tes_bess_boundary/components/bess.py` | 交流侧 SOC、能量口径与最小 Pyomo 组件 | E0-E6 | 已实现 E0-A；模型外退化经济核、年度 AC 吞吐成本及 EFC 接缝已完成；cell/PCS/BoP 候选证据与转换机制已建，正式指数快照待补 |
| `src/tes_bess_boundary/components/molten_salt.py` | HT/MT/LT 盐量、焓与最小 Pyomo 组件 | E0-E6 | fixed-capacity 五端口及损失/伴热/泵耗线性表达已接入；正式成本和数值校准待补 |
| `tests/` | 真实数据、本构、适配/桥接、线性、四架构、HiGHS、寿命、TES 温区/拓扑/夹点/MT/损失辅机/三档损失与泵耗标定、五路径运行审计、成本证据认证、官方工程敏感性、Rahman 正式 BESS 账本、TES 正式就绪度及年度经济回归 | E0 | 本地 E0-D-15 `273 passed in 30.31s`（关闭 pytest cache）；OpenBayes 最近仍为 `258 passed in 21.36s`，本轮尚未同步 |
| `src/tes_bess_boundary/model.py` | 统一 fixed-capacity Pyomo 模型、四架构开关、可选年度经济审计与 TES 五路径/损失/辅机运行审计 | E0-E6 | E0-D-14 已把 BESS 退化成本与 AC 放电 VOM 分列并各计一次；系统级正式 TAC 与容量规划待补 |
| `representative_weeks.py` | 4 个聚类周 + 2 个强制极端周 | E3-E5 | 待实现 |
| `scenarios.py` / `run_sweep.py` | 场景网格和并行断点续跑 | E2-E6 | 待实现 |
| `validate_full_year.py` / `postprocess.py` | 全年回代、边界和机理分解 | E1-E6 | 待实现 |

E0 当前状态详见 `docs/03_sci_paper/e0_validation_status.md`。

## 5. 服务器映射

- 平台：OpenBayes CPU-xxlarge；
- 已核对：60 CPU、约 97 GiB 可用内存、Python 3.10.18；
- 求解器：HiGHS，通过 `highspy`；
- 隔离环境：`/root/e0-b-20260711-019f4f64/tes_bess_boundary/.venv-e0`；
- 已验证：`Pyomo 6.10.1`、`highspy / HiGHS 1.15.1`，微型 MILP 状态 `optimal`；
- 完整 E0 当前回归：本地 Python 3.11 E0-D-15 为 `273 passed in 30.31s`（关闭 pytest cache，无警告）；OpenBayes Python 3.10.18 最近为 `258 passed in 21.36s`，E0-D-14/15 尚未同步；
- 复现依赖：`风光火+熔盐储热/requirements-highs.txt`；
- 未安装且当前不需要：`oemof.solph`；
- 输出路径：`/output`；
- 初始并发：代表周 `20×2` 线程，8784 h 固定容量 `4×4`，全年重优化 `2×4`；再按峰值 RSS 调整，总 HiGHS 线程不超过 56；
- 凭据与密码禁止写入仓库、配置或日志。
- 最新版代码和最小必要杨凌原始数据位于 `/root/e0-b-20260711-019f4f64/`；正式 E0-B 三文件位于其 `formal_data/e0b_formal_2024/`，E0-C 证据位于 `formal_data/e0c_heat_demand_adapter/`；除 runtime sidecar 外，本地/远端规范 SHA-256 一致；凭据和非必要保密资料未上传。

## 6. 旧稿边界

原 `run.py --exp 1/2/3/4`、德国/松山湖、EQD/Carnot 和对应 `论文撰写/paper/` 文件属于旧独立稿，不再映射到当前 SCI。若未来继续投稿，应单独维护，不能把其结果混入本实验链。
