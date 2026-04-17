# SCI 论文：最新逻辑结构

更新时间：2026-04-10

## 1. 定位

SCI 论文要承担“**把核心创新扩成完整论文故事**”的任务，因此它不是会议稿的简单放大版，而是“规划层正式展开 + 设备层价值验证”的完整论证。

一句话主张是：

> 㶲加权欧氏距离（EQD）能够比传统匹配度指标更合理地量化分布式电热综合能源系统的源荷匹配，并进一步更有效地识别卡诺电池这类电热耦合储能的配置价值。

## 2. SCI 稿必须回答的核心问题

1. 为什么源荷匹配度需要从 IEMI 进一步升级为 **EQD**，即补上㶲加权的物理基础？
2. 为什么 EQD 在规划结果上比 `economic_only / std / pearson / ssr` 更强？
3. 为什么这种方法优势不仅停留在 Pareto 图上，还能体现在全年运行指标、敏感性和韧性上？
4. 为什么 EQD 能更好地识别卡诺电池这类耦合设备的配置价值？

## 3. SCI 稿的故事结构

### 3.1 第一层：规划层正式展开

- 用两案例、多方法对比把 EQD 的方法优势讲实。
- 从会议稿中的几何概念验证，升级到“几何 + 热力学”的完整表达。
- 这里的主角是 `EQD vs std`，其他方法更多承担基线或边界参照角色。

### 3.2 第二层：设备层扩展

- 把卡诺电池作为“能否识别电热耦合设备价值”的试金石。
- 先做 `euclidean / EQD` 下无卡诺 vs 有卡诺。
- 再做有卡诺条件下 `std vs EQD`，验证设备价值识别能力是否受匹配度指标影响。

### 3.3 第三层：强证据链，但不把硕士论文第 4 章抢走

SCI 稿需要更强证据，但仍然要守边界：

- 可以保留：8760h 后验运行指标、λ 敏感性、极端场景韧性。
- 不展开：完整的负荷预测模型、日前调度架构、误差传播分析。
- 换句话说，SCI 稿里的“运行层内容”只作为强化证据，不作为独立研究层。

## 4. 推荐章节职责

1. `Introduction`：研究问题、文献空白、规划层与设备层两条贡献线。
2. `System modeling`：CCHP / IES 拓扑、设备模型、卡诺电池、典型日。
3. `Energy-quality-weighted matching index`：EQD 定义、㶲系数来源、与 IEMI / Std 的关系。
4. `Bi-objective optimization framework`：目标函数、决策变量、算法流程。
5. `Case studies`：德国与松山湖案例、四组核心实验定义。
6. `Results and discussion`：实验 1-4 + 后验指标 + 敏感性 / 韧性补充。
7. `Conclusions`：方法、设备、证据链三层收束。

建议把 `Results and discussion` 内部固定为以下顺序：

- 6.1 Experiment 1: German 5-method comparison
- 6.2 Post-optimization 8760h operational validation
- 6.3 Experiment 2: Cross-climate validation on Songshan Lake
- 6.4 Experiment 3: Carnot battery ablation
- 6.5 Experiment 4: Joint validation under Carnot integration
- 6.6 Integrated discussion and limitations

建议每个结果子节内部统一采用：

- `trade-off`：先交代 Pareto 权衡与可接受预算区间
- `configuration mechanism`：再解释关键设备容量如何变化
- `operational evidence`：再用 `8760h` 或典型日调度兑现规划差异
- `implication`：最后说明该结果支撑全文哪条主线

结果分析扩充方案单列文档：

- `docs/03_sci_paper/results_analysis_expansion_plan.md`

## 5. 术语约束

- SCI 稿主术语：**EQD**。
- IEMI 只用于说明会议稿前导关系，不再作为正文主标签。
- 卡诺电池是设备层第二贡献，不是会抢走全文主线的独立论文。
- 负荷预测 / 日前调度 / 鲁棒性完整章节保留给硕士论文第 4 章。

## 6. 对应源码与入口

- 主稿：`论文撰写/paper/main.tex`
- 分节：`论文撰写/paper/sections/`
- 图表统一落点：`论文撰写/paper/figures/`
- 对应映射：`docs/03_sci_paper/experiment_figure_code_map.md`
- 服务器执行清单：`docs/03_sci_paper/server_full_run_checklist.md`
- 图表计划：`docs/03_sci_paper/figure_table_plan.md`
- 初稿升级计划：`docs/03_sci_paper/manuscript_upgrade_plan.md`
- Phase 2 高强度审稿报告：`docs/03_sci_paper/adversarial_review_phase2.md`

