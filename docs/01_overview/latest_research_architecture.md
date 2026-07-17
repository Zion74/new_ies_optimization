# 最新研究架构

更新时间：2026-07-16

## 1. 当前统一主线

当前硕士论文不再采用“EQD → 卡诺电池 → 负荷预测”的旧三层结构，而改为：

> **以杨凌热约束型风—光—火系统为统一对象，先建立数据与物理模型，再用源荷匹配方法识别灵活性需求，进一步给出 BESS—熔盐 TES—Hybrid 的公平技术选择边界，最后用可审计的 Agentic 工作流把确定性模型转化为规划决策支持。**

研究递进是：

```text
统一对象与物理口径
→ 何时出现、多强的灵活性服务需求
→ 应由 BESS、TES 还是 Hybrid 提供
→ 如何把模型可靠地用于场景化决策支持
```

## 2. 论文载体分工

### 2.1 会议成果

当前会议成果彼此独立，不再强行组成大论文主线：

1. **源荷匹配会议稿**：保留 IEMI / EQD 方法的概念验证，可作为硕士论文第 3 章的方法来源；德国和松山湖只作辅助证据。
2. **负荷预测会议稿**：作为独立会议论文保留，不再承担硕士论文主章节，也不进入 TES/BESS SCI。
3. `风光火+熔盐储热/IEEE-conference-proceeding-Latex/` 中的旧同规格储能比较是早期探索稿，其数值不能自动继承为新 SCI 结论。

### 2.2 当前主 SCI

SCI 只研究：

- 杨凌 2×350 MW 抽凝 CHP；
- 签约风电、本地 PV、固定供热义务和公共并网点；
- 无储能 / BESS / 双用途熔盐 TES / Hybrid；
- 同服务 ε-约束下的最小年化成本；
- 热约束—通道紧张度和时长—相对成本选择边界；
- 代表周扫描与 8784 h 验证。

SCI 不加入负荷预测、随机优化、滚动调度或 Agentic。

### 2.3 硕士论文

硕士论文以杨凌为唯一主案例：

- **第 2 章**：系统、数据、统一模型与验证；
- **第 3 章**：基于源荷匹配的新能源接入规划与灵活性服务需求识别；
- **第 4 章**：BESS—熔盐 TES 的价值机理与适用边界，即主 SCI；
- **第 5 章**：可验证的 Agentic 规划决策支持；
- **第 6 章**：结论与展望。

第 3 章回答“在哪种规划状态下、何时以及多强地需要灵活性服务”，输出风光规模、ε、冲突时段和服务需求指标；第 4 章才联合优化“由哪一种储能、配多少功率/容量来提供”，第 5 章回答“如何安全、可追溯地调用前两章模型”。

## 3. 源荷匹配的保留方式

源荷匹配保留为第 3 章的方法，不再要求德国或松山湖成为大论文主题。推荐做法：

- 用 IEMI / EQD 或其简化指标识别杨凌的风—光—热致强迫发电失配；
- 输出风光接入规模、灵活性需求和关键冲突时段；
- 把这些典型规划状态传递给第 4 章；
- 德国 / 松山湖只用于方法迁移或放入附录。

因此，原 `run.py`、`cchp_gaproblem.py` 和德国/松山湖结果仍是研究资产，但不再控制当前 SCI 和硕士论文主线。

## 4. 负荷预测的处理

- 负荷预测不再写入硕士论文主线；
- 不再新建“预测—日前—实时”第 4 章；
- 已有预测工作可作为独立会议论文或展望；
- 当前 SCI 与硕士论文核心模型使用已知历史时序和确定性情景。

这避免为了章节完整性引入一个与核心科学问题弱耦合、且投稿竞争激烈的预测模块。

## 5. Agentic 的正确位置

Agentic 只属于硕士论文第 5 章的**可信决策支持层**：

```text
自然语言场景
→ 结构化 Scenario Schema
→ 单位、范围和完整性校验
→ 调用第 3 / 4 章确定性优化器
→ 独立物理与证据审计
→ 可追溯建议和报告
→ 人工确认
```

Agent 不直接生成容量答案，不替代 MILP，不擅自改变物理参数。只有在参数抽取、非法输入识别、调用成功率、结果复现、物理违规漏检和无证据建议率上完成对照实验，才可作为论文内容；否则降级为工具演示或展望。

## 6. 当前研究状态

- **文献与科学问题**：已完成高质量文献门槛筛选，当前主空白可辩护；
- **杨凌数据**：E0-B 正式构建已完成；保留 52,707 行源证据、52,704 点 canonical 网格和 8,784 h net/forward/zero-sensitivity 三口径。单位、老城单点哨兵、29 个东方双负、49 个仅流量为负、2,050 个居民负值与 5/85/226 三段全零均进入结构化质量合同；
- **机制原型**：已有 `_ch4_*` MILP、储能对照、敏感性和典型期脚本；
- **公平主模型**：E0-C fixed-capacity 四架构统一调度、真实热需求桥接及 E0-D-1–D-20 已闭合相应物理、寿命经济、证据资格、同 PCC 服务和四类非燃料成本证据门。E0-D-21 不猜项目价格，而将 D19 燃料空间与 D20 缺口连接成来源无关的影子成本稳健性边界；D22 导出同服务逐时 PCC；D23 建立联合双向极值，D26–D30 将 24 h 包络精确闭合并把 336 h 严格区间收紧为 `[36,382.462799,777,141.368858] MWh/a`，D31/D32 为负筛查。D24/D25 仍为 `0/16` 严格账户与 `0/4` 项目账户可复核。D33 已实现公开敏感性成本账与独立容量核，D34 完成容量核向双机 CHP/PCC/损失辅机/额定服务认证的线性集成，D35 完成结果前 TES 材料性网格，D36 冻结六个代表周、52 周权重和年尾真实 warm-up/计分段，D37 已实现共享容量、七块独立 CHP/BESS/TES 循环状态边界。D38 原高热状态与 R1 baseline 时间聚合门均已登记失败。公开或本地可比工程资料仍不能替代杨凌项目账本；TES 正式成本、新的有效时间聚合合同、正式 E5 和 336 h 包络闭合继续阻断正式 E2–E6；
- **D32 联合分块负筛查**：结果前固定 24 h 连续分块、300 s/块和 1% 材料性门。24 h reopened 等价探针在全部主整数/符号二元开放时保持精确；336 h 的 14 个受保护块 dual 之和为 `1,930,160.868929 MWh/a`，高于 D30，故不启动新 336 h global probe。该结果排除“可分离日块上界求和”作为当前闭合路线，并进一步表明后续证书必须保留跨块共同轨迹互斥性；
- **D33 公开成本与容量核**：已建立聚合储热包/分项台账两套互斥 TES 公开敏感性组合，强制 12 账户各覆盖一次、作者价格年和相似部件代理显式确认，并保持 `formal_project_eligible=false`；BESS/TES 线性内生容量核已通过 HiGHS 小模型测试；
- **D34 完整内生容量模型**：容量核已接入双机 CHP、风光、供热、公共 PCC 和年度服务；Rahman BESS 采用一个共同 PCS 并执行 `0` 或 `5–100 MW` 来源域析取，TES 接入环境相关损失、伴热、五路径泵耗、HT 发电/MT 供热两条独立额定放能轨迹及充热可达性。同弃电上限、同年度 PCC 的 24/336 h 四架构样本已按 objective bounds 和 SHA-256 冻结；早期只同弃电的结果降级为 smoke。1% 严格 ε 初筛得到 BESS `13.04 MW / 189.21 MWh` 与约 `98–104 t` TES，但 Hybrid 的 BESS 为零，且 TES 仍不到旧 `1,200 MWhth` 参考切片盐量的 `1%`。该尺度疑问现由 D35 材料性门闭合；D34 本身只打开公开成本下的小样本诊断与 E1 受控机制，不打开杨凌正式 TAC、E2 经济前沿或项目技术赢家；
- **D35 材料性门**：以旧 `1,200 MWhth / 13,913.716 t / 150 MW` 切片为分母，在结果前锁定 `0/1%/5%/10%`，对盐量及每个启用端口实施半连续门。自然服务的 1% 解为约 `139–142 t` heat-only TES，但公开代理成本改善仅约 `0.03%–0.05%`；5%/10% 精确选择零 TES。严格服务在 1%/5%/10% 下形成约 `174–186/871/1,742 t` TES，且 Hybrid 全部折叠为 TES；TES/Hybrid objective bounds 重叠，不排序。D35 是材料性稳健性，不是现场最小规模或项目赢家；
- **D36 代表周数据门**：以热负荷、风电 CF、光伏 CF 和气温组成 672 维周曲线，确定性 PAM 加热峰/高可再生压力强制极端周后冻结第 `4/5/8/29/39/48` 周和 `1/3/10/13/21/4` 权重；加入年尾实际 24 h warm-up 与 48 h 计分段后共 1080 行、8784 加权小时。三个规范文件跨平台逐字节一致。热量 `+5.35%` 和风电 `-8.98%` 等聚合偏差保留给 D38 验证，不事后改周；D36 没有运行单循环优化模型；
- **D37 分块状态边界门**：新增显式 `BlockAnnualHorizonSpec` 和 D36 严格适配器；六个 168 h 周与一个 72 h 年尾块共享容量，但分别闭合 BESS SOC、HT/MT/LT 库存和两台 CHP 首尾启停/出力/爬坡。年尾 24 h warm-up 权重为零、48 h 计分权重为一；完整 Hybrid 结构审计为 1087 个 BESS/TES 状态节点、每台 CHP 各 1080 条转移及双向爬坡约束、零非线性组件，且未调用求解器。规范 manifest 双端哈希为 `1e460ef35921d670a23867ad39716302c7f4eecb90cfd225ee628ea7bbd0ddb6`；
- **D38 三状态预验证**：结果前合同冻结了 `baseline`、`H*=0.80/G*=0.70` 高热紧 PCC 与基准物理下 24 h 长时边界，以及实际全年无储能两阶段 PCC 目标、10% 弃电帽、代表期规划、固定容量回代和全年重优化。首次执行已在原高热状态的真实 8784 h 无储能最小弃电阶段返回 `infeasible`；静态必要条件表明 490 MW PCC 下最大供热为 `766.077 MWth`，冻结高热序列 36 h 超限且全部已在代表周 4。故原 D38 不能关闭，该失败不是代表周漏选；
- **D38-R1 一次性修订与失败**：在任何 R1 储能结果产生前另行冻结 `H*=G*=0.70`，静态诊断峰值 `724.034 MWth`、0 h 超限；但当前代码/同一服务哈希下，baseline 无储能代表期以 `338,777.027 MWh` 弃电满足 10% 帽，真实 8784 h 回放却 `infeasible`。零燃料自然最小弃电由代表期的 `338,704.669 MWh` 上升到真实全年的 `565,916.122 MWh`，低估 `227,211.453 MWh`。因此 R1 三状态合同已失败，不得继续 E2/E3/E4；
- **D39 服务感知增量修订与失败**：结果前冻结原六周加第 `49/16` 周，Gate A 八周数据双端复现通过。Gate B 将真实全年和八周代表期的 10% 服务分类统一为不可行，但自然最小弃电率仍为 `16.6657%` 与 `11.4895%`，误差 `5.1762` 个百分点，超过 1 个百分点门。D39 因此失败，Gate C/D 不启动，也不得继续加周或放宽阈值；
- **D40 全年优先计算门与失败**：已在任何 D40 构造或求解结果产生前冻结真实 8784 h 单块、baseline 同服务、三种储能架构、HiGHS `0.1%` 正式 gap、3600 s/案例和内存停止规则。代表期不再进入正式容量规划。OpenBayes Gate A 已通过：四架构均为线性单全年循环，Hybrid 含 `685,194` 个活动变量、`96,625` 个二元变量和 `667,662` 条活动约束；峰值 RSS `0.645 GiB`、构造后可用内存 `96.705 GiB`，总 manifest SHA-256 为 `23e0831ed017ca794a73b897196495079db3ace847fe840d51c1fa60af0de577`。唯一一次 BESS 60 s 预检只确认接入与资源。正式 BESS 因父进程缺少硬墙钟，在总运行 `4527.395 s` 后仍无结果 JSON、有限 incumbent/dual 或不可行证明；滞后终止后分类为 `monolithic_not_viable`，资源门通过且峰值 RSS 仅 `2.916 GiB`。因此失败来自当前单体执行路线而非内存或 BESS 物理不可行，D40 已不能通过；TES/Hybrid 未在失效执行器下继续；
- **D41 严格全年界—修复分解（Gate B 最弱案例失败）**：Gate A 的 BESS/TES/Hybrid 原始二元为 `79,057/87,840/96,625`，R0 均剩 0，R1 只剩 `1/0/1` 个拓扑二元，完整固定后均无遗漏。修复接入后正式 Gate B 中，BESS R0/R1 均达到最优并通过审计，严格下界为 `1,144,950,604.8368804 CNY`；它只是受控公开成本敏感性下界，不是原 MILP 上界或项目 TAC。TES R0 已进入 dual simplex，但在 `720.462 s` 硬墙钟内没有返回结果 JSON、有限合法 dual 或不可行证明；峰值子进程树 RSS 仅 `2.389 GiB`，不是内存耗尽。按 BESS→TES→Hybrid 串行停止规则，TES R1 与 Hybrid 未启动，Gate C/D 禁止。总 manifest SHA-256 为 `bbc0638470859a58fe26a3166ec4825f455fd27671b7edf234b6e51557ee8aef`，状态 `no_strict_certificate`；不能推出 TES 不可行、BESS 优于 TES、容量方案或技术排序；
- **D42 原生 HiGHS 可中断拉格朗日下界（TES R0 无证书，路线停止）**：Gate A、执行器实现门和 BESS R0 复核通过，BESS 严格下界 `1,144,950,604.8368804 CNY` 保留。正式 TES R0 的原始/presolve LP 指纹与 Gate A 一致；IPX 完成 31 次 IPM 迭代，simplex 第 1 段完成 `315,298` 次迭代，但两者均在求解器软中断返回后的 80 位证书计算阶段触发父进程硬墙钟，没有落盘 certificate 或 basis。TES R0 为 `no_strict_certificate`，simplex 2–4、TES R1 与 Hybrid 均未启动；
- **D43 冻结快照离线证书恢复（正式 Gate B 失败）**：唯一一次正式复算已在 OpenBayes 执行。两个完整 `439,018` 维 row dual 均通过冻结哈希链和准入门，并在两个 clean child 中并行进入未修改的 80 位证书器；IPX/simplex child 均运行约 `1800.49 s` 后触发冻结硬墙钟、返回码 `-15`，没有生成 result 或 certificate。总 manifest SHA-256 为 `c7b7e42973c30778efb791e2369ec5dc60dd4c70c75db333bfb5d3e1ac8f4526`，状态 `no_strict_certificate`；
- **D44 fork 并行 80 位证书（TES 下界已恢复）**：源码/测试先以提交 `b52c722` 冻结并在 OpenBayes 同哈希通过 Gate A：D44 `24 passed`、D40–D44 `104 passed`、全包 `558 passed`，零失败、零跳过。唯一正式 Gate B 中，两个快照各完成 24/24 块；IPX 覆盖全部 `509,289` 列与 `1,806,011` 个非零元且无非法端点，形成 TES R0 严格下界 `254,860,566.6193158889 CNY`，并由结构同一性覆盖 R1。simplex_1 因 `15,195` 个所需无穷端点不合格。总 manifest SHA-256 为 `d6fe2f34a354e5986ad4775034135f090df2e74492e0c7abc8f95861cb89739f`，运行 `819.732 s`，峰值聚合 RSS `15.434 GiB`；
- **D45 Hybrid R0 严格下界（唯一正式运行无证书）**：只求 Hybrid 的全连续 R0 松弛，不把 R1 两个拓扑分支设为成功条件。prepare 完整复现原始 `667,662 × 685,194` 与 presolved `495,630 × 539,546` LP 指纹，IPX/simplex_1 均形成完整 row-dual 快照；但 D44 的 24 块、80 位 fork 认证在冻结 `900 s` 硬墙钟内分别只完成 `20/24` 与 `16/24` 块，两个 phase 均以 `SIGTERM` 收口且未生成 certificate/result。总状态 `no_strict_certificate`，manifest SHA-256 为 `668fb0ea4c9293f789781298ca54f56da2bdcb55a3a7806d5bf8171d6e24cc55`；总运行 `1969.958 s`，峰值聚合 RSS `16.827 GiB`、最低可用内存 `87.735 GiB`，不是内存耗尽。D45 没有形成 Hybrid 下界，因而也不能主张 R0 对 R1/原 MILP 的数值覆盖；
- **D47 Hybrid 加权持久化证书（Hybrid 下界已恢复）**：D47 只读 D45 同哈希 LP 与双 row dual，不调用 HiGHS `run()`；按每列固定开销加非零元数生成 56 个确定性连续块，以 56 个 fork worker 先认证 IPX、失败才回退 simplex_1，并逐块原子落盘。源码/测试已由提交 `1515eca` 固定，OpenBayes Gate A 为 `37/168/622 passed`。唯一正式运行中 IPX 56/56 块全部合格且无非法端点，simplex_1 按合同未启动，恢复 Hybrid R0 严格下界 `232,011,577.8359315691 CNY`；由可行域包含关系，该数值也下界 Hybrid R1 与原 MILP。总 manifest/execution SHA-256 为 `8b74c404...` / `ed978c36...`，总运行 `539.050 s`，峰值聚合 RSS `18.838 GiB`；
- **D46 三架构可行上界正式批次（零上界恢复）**：结果前合同、最终源码提交 `4a18f42` 与 OpenBayes `22/204/644 passed` Gate A 已闭合。唯一正式 BESS→TES→Hybrid 总批次运行 `8820.162 s`，总 manifest `8693722...`。三个 R0 guide 均最优但只提供连续引导；BESS 新 seed 与限定 D41 回退均未产生 incumbent，TES/Hybrid seed 分别有 `48,801/48,791` 条行不可行，原 MILP 各跑满 `3600 s` 后 Primal bound 仍为 `inf`。三架构均为 `no_candidate_incumbent`，没有进入 Repair A/B，上界恢复数为 0；
- **D46 事后只读诊断与 D48 结果前路线**：诊断 bundle `c74a694...` 未调用求解器；BESS 的 `55,425` 条违约主要来自 CHP 编码/启停轨迹，TES/Hybrid 的 `48,801/48,791` 条违约在幅值上由 HT 接收/送出模式主导，说明逐变量取整不能形成一致离散轨迹。D48 第 1–11 节已在任何实现和正式数值前冻结；实现与测试提交为 `1090cd83...`，OpenBayes 同源 Gate A manifest 为 `1d894652...`，三架构 build-only 审计、15 项定向测试和 659 项全包回归全部通过，Gate A 未调用正式优化；
- **服务器与当前准入**：OpenBayes 60 核 / 约 100 GB 内存，D43、D45、D47、D46 均不得原样重跑。D48 首次错误路径启动已作为无结果行政失败归档；D48-R1 唯一正确路径总批次已完成。BESS/TES/Hybrid 候选阶段分别在 `3720.176/3720.581/3720.803 s` 父级硬墙钟受控终止，均未生成 candidate、repair、容量或上界，活动残留均为 0；三者都只能登记为 `no_primal_status_closure`，不构成相应架构不可行。正式总状态为 `partial_or_no_upper_bound_recovery`，成功上界恢复数 0，总 manifest SHA-256 `ca024880...`。正式 E2–E4、gap 收缩、项目 TAC 和技术赢家继续阻断；
- **D49 物理优先燃料投影恢复（唯一 BESS 正式门已关闭）**：提交 `86a8b80e...` 与 OpenBayes Gate A `11b283d6...` 已闭合；三架构 build-only 均投影 `52,704` 个燃料编码位并保留 `26,353/35,136/43,921` 个物理二元，`14/219/673 passed` 且未调用 solver。唯一正式 BESS 候选在 `3720.637 s` 父级硬墙钟受控终止，没有 candidate、exact lift、repair、容量或上界；峰值进程树/聚合 RSS `3.138/3.162 GiB`、最低可用内存 `94.173 GiB`、残留进程 0，故不是内存失败。formal manifest `0d66f06d...` 将终态锁为 `no_primal_status_closure`；D49 不得原样重跑，只开放另立 D50 方法设计；
- **D50 全年耦合物理分块 Relax-and-Fix（唯一正式 BESS 路径已关闭）**：完整 8784 h 年度 PCC、弃电帽、吞吐和单全年循环始终保留，`52,704` 个燃料编码位连续化，物理二元使用 `336 h` 前视、`168 h` 提交。阶段 `0/1/2` 捕获 incumbent 并累计固定 `1,513` 个物理二元；阶段 `3` 在已固定路径下返回 `Infeasible` 且无 incumbent，终态 `block_path_no_incumbent`。正式 manifest `3efdbba5...`；总运行 `1218.713 s`、峰值聚合 RSS `3.607 GiB`、残留进程 0。没有完整物理轨迹、精确提升、repair、容量、上界或 gap；该失败只否定无回退贪心块路径，不证明原 BESS MILP 不可行，D50 不得原样重跑；
- **D51 检查点化有界回退 Gate 0（已验证）**：提交 `baec961...` 的同哈希 OpenBayes 证据以 `15/249/703 passed`、零跳过通过，24 h 三个 `8 h` 检查点均由 clean 模型重放且最大固定值残差为 `0`，随后完成精确燃料提升和原成本 clean repair；manifest `883d4c0b...` 登记 `gate0_controller_validated`。该 repair 只属于缩短时域机制验证；`formal_8784h_optimization_invoked=false`、`formal_run_permitted=false`，仍无全年容量、上界、gap 或技术结论；
- **D52 全年检查点化有界回退（唯一正式 BESS 已关闭）**：结果前合同只开放 BESS，逐字节沿用 D50 的真实 `8784 h` 模型与服务，保留 `336 h` 整数前视、`168 h` 提交和 48 h 年尾，共 `53` 个阶段；使用常数零可行性目标、一步回退、每阶段至多 3 个不同模式、全批至多 8 次回退和至多 69 次 solver 尝试，再执行确定性燃料提升与 clean 原成本 repair。实现提交 `c3b2e0cf...` 的 OpenBayes 同哈希 Gate A 以 D52/D40–D52/全包 `17/266/720 passed`、零跳过闭合。唯一正式运行中阶段 0/1 均以 HiGHS `Optimal` 捕获完整 `597,318` 变量映射，累计固定 `1,009` 个物理二元；阶段 2 attempt 0 未在冻结 `390 s` 父级硬墙钟前返回结果，父进程以 `SIGTERM` 收口。正式状态为 `no_primal_status_closure`，manifest SHA-256 `c80fc8bf...`，总运行 `1185.041 s`；峰值聚合 RSS `3.471 GiB`、最低可用内存 `93.859 GiB`、残留进程 0，故不是内存耗尽。未形成完整 candidate、精确提升、clean repair、容量、上界或 gap；两个 checkpoint 均明确无上界资格，D52 不得恢复或原样重跑，TES/Hybrid 继续禁止；
- **Agentic**：只完成研究定位，尚未实现与评价。

## 7. 权威入口

- SCI 逻辑：`docs/03_sci_paper/latest_logic_structure.md`
- SCI 模型实验：`docs/03_sci_paper/fair_storage_boundary_model_and_experiment_design.md`
- E0 实现状态：`docs/03_sci_paper/e0_validation_status.md`
- E0 正式成本闭环：`docs/03_sci_paper/e0_formal_cost_closure_audit.md`
- TES 正式成本就绪度门禁：`docs/03_sci_paper/e0_tes_formal_cost_readiness_contract.md`
- TES 价格无关价值与盈亏平衡合同：`docs/03_sci_paper/e0_tes_break_even_contract.md`
- 年度结果适配与 24 h/两周探索状态：`docs/03_sci_paper/e0_tes_break_even_adapter_and_exploration_contract.md`
- E0 Rahman BESS 关联证据合同：`docs/03_sci_paper/e0_rahman_bess_linked_evidence_contract.md`
- E0 同 PCC 服务与运行成本证据边界：`docs/03_sci_paper/e0_same_pcc_service_and_operating_cost_boundary_contract.md`
- E0 非燃料运行成本证据就绪度：`docs/03_sci_paper/e0_operating_cost_evidence_readiness_contract.md`
- E0 非燃料影子成本稳健性：`docs/03_sci_paper/e0_shadow_cost_robustness_contract.md`
- E0 逐时 PCC 与结算价差暴露：`docs/03_sci_paper/e0_pcc_settlement_exposure_contract.md`
- E0 替代可接受调度的结算暴露包络：`docs/03_sci_paper/e0_alternative_dispatch_settlement_envelope_contract.md`
- E0 完整 TAC 16 账户证据路线：`docs/03_sci_paper/e0_formal_tac_evidence_route_contract.md`
- E0 项目原始证据接收与隐私隔离：`docs/03_sci_paper/e0_project_primary_evidence_intake_contract.md`
- E0 公开 TES 成本组合与内生容量门：`docs/03_sci_paper/e0_public_tes_cost_portfolio_and_capacity_gate_contract.md`
- E0-D-34 完整内生容量与额定服务认证：`docs/03_sci_paper/e0_d34_endogenous_capacity_full_model_contract.md`
- E0-D-37 分块循环状态边界：`docs/03_sci_paper/e0_d37_block_cyclic_state_boundary_contract.md`
- E0-D-38 三状态代表周—全年预验证：`docs/03_sci_paper/e0_d38_three_state_representative_full_year_prevalidation_contract.md`
- E0-D-38 原高热状态失败记录：`docs/03_sci_paper/e0_d38_original_high_heat_state_failure.md`
- E0-D-38-R1 一次性高热状态修订：`docs/03_sci_paper/e0_d38r1_revised_high_heat_prevalidation_contract.md`
- E0-D-38-R1 baseline 时间聚合失败：`docs/03_sci_paper/e0_d38r1_baseline_temporal_aggregation_failure.md`
- E0-D-39 服务感知代表周一次性修订：`docs/03_sci_paper/e0_d39_service_aware_representative_week_refinement_contract.md`
- E0-D-40 全年优先可计算性与证据门：`docs/03_sci_paper/e0_d40_full_year_first_compute_evidence_gate_contract.md`
- E0-D-41 严格全年界—修复分解合同：`docs/03_sci_paper/e0_d41_strict_full_year_bound_repair_decomposition_contract.md`
- E0-D-42 原生 HiGHS 可中断拉格朗日下界合同：`docs/03_sci_paper/e0_d42_native_highs_interruptible_lagrangian_bound_contract.md`
- E0-D-43 冻结快照离线对偶证书恢复合同与正式失败：`docs/03_sci_paper/e0_d43_frozen_snapshot_offline_dual_certificate_contract.md`
- E0-D-44 fork 并行 80 位拉格朗日证书合同：`docs/03_sci_paper/e0_d44_fork_parallel_lagrangian_certificate_contract.md`
- E0-D-49 物理优先燃料投影—原成本可行上界恢复合同：`docs/03_sci_paper/e0_d49_physics_first_fuel_projection_primal_recovery_contract.md`
- 硕士论文逻辑：`docs/04_master_thesis/latest_logic_structure.md`
- 第 4 章计划：`docs/04_master_thesis/chapter4_tes_ees_regime_boundary_plan.md`
- 第 5 章计划：`docs/04_master_thesis/chapter5_agentic_decision_support_plan.md`
- 文献证据包：`风光火+熔盐储热/research-sessions/2026-07-11-tes-ees-regime-boundary/`；成本闭环证据：`风光火+熔盐储热/research-sessions/2026-07-13-e0d12-formal-cost-closure/`；BESS 三接缝闭合记录：`风光火+熔盐储热/research-sessions/2026-07-13-e0d14-bess-join-closure/`；TES 正式成本复核：`风光火+熔盐储热/research-sessions/2026-07-13-e0d15-tes-formal-cost-closure/`；同 PCC 服务边界：`风光火+熔盐储热/research-sessions/2026-07-13-e0d19-operating-cost-boundary/`；非燃料成本证据门控：`风光火+熔盐储热/research-sessions/2026-07-14-e0d20-operating-cost-evidence/`；影子成本稳健性：`风光火+熔盐储热/research-sessions/2026-07-14-e0d21-shadow-cost-robustness/`；逐时 PCC 结算暴露：`风光火+熔盐储热/research-sessions/2026-07-14-e0d22-pcc-settlement-exposure/`；替代调度包络：`风光火+熔盐储热/research-sessions/2026-07-14-e0d23-alternative-dispatch-envelope/`；完整 TAC 证据路线：`风光火+熔盐储热/research-sessions/2026-07-14-e0d24-formal-tac-evidence-route/`；项目原始证据接收：`风光火+熔盐储热/research-sessions/2026-07-14-e0d25-project-primary-evidence-intake/`
