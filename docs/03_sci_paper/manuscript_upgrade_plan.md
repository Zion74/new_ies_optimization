# SCI 初稿升级计划

更新时间：2026-04-10

本文件用于指导当前 SCI 初稿从“已有完整第一贡献、第二贡献待补齐”升级到“按最终 full 结果回填后的正式版本”。

## 1. 先改什么，后改什么

当前不建议先大面积润色英文，而应按以下顺序推进：

1. **先拿到 full 结果**
   - 德国 full pipeline
   - Songshan Lake full pipeline
   - Exp3 full
   - Exp4 full
2. **再回填 `results.tex`**
   - 这是对摘要、引言贡献点、结论最有约束力的章节。
3. **然后改摘要**
   - 只保留已经被 full 结果证明的量化结论。
4. **然后收紧引言贡献表述**
   - 用 final results 验证是否需要调整措辞强度。
5. **最后改结论**
   - 只总结已被 `Results` 实证支持的结论。

## 2. 各章节当前状态

### `Introduction`

当前状态：

- 背景清晰
- 文献脉络顺
- 第一贡献表述较强
- 第二贡献表述已经写成核心贡献

升级动作：

- 保留当前背景和 gap 主线。
- 待 Exp3 / Exp4 full 结果回来后，再决定第二贡献的措辞强度。
- 建议最终在引言末尾显式写出 3 个研究问题：
  - RQ1：规划阶段是否需要用 Carnot exergy factors 区分电 / 热 / 冷匹配失衡？
  - RQ2：EQD 是否比现有指标带来可兑现的规划与运行优势？
  - RQ3：EQD 是否能更有效识别 Carnot battery 的配置价值？

### `System modeling`

当前状态：

- 结构完整
- 缺系统拓扑图

升级动作：

- 补 `fig:topology`
- 若最终 Carnot 电池建模细节有改动，确保图和文字同步

### `Matching index`

当前状态：

- 第一贡献的理论表达已经较成熟
- 与近邻 exergy literature 的区分仍可更锋利

升级动作：

- 在 final version 中把差异压缩成一句更明确的话：
  - existing exergy literature mainly evaluates or optimizes operation;
  - this work uses Carnot exergy factors as planning-stage cross-carrier mismatch weights.

### `Case studies`

当前状态：

- 实验 1-4 已有表格骨架
- 德国电价合理性仍需确认来源

升级动作：

- 如果德国电价 `0.0025 €/kWh` 确为特殊口径，必须在案例说明或脚注中解释。
- 若数据源需要改口径，应在 final results 前同步修正。

### `Results`

当前状态：

- 已重构为最终骨架版，包含 Exp1 / post-analysis / Exp2 / Exp3 / Exp4 / integrated discussion。

升级动作：

- 服务器结果回来后，按 `results.tex` 中的 TODO 顺序替换占位段落。

### `Conclusions`

当前状态：

- 现在的结论强依赖第二贡献已经完整闭环。

升级动作：

- 在 Exp3 / Exp4 full 结果回来前，不应再强化第二贡献措辞。
- 结果回来后，按最终证据强度决定是写“more effectively guides Carnot battery sizing”还是更克制的“demonstrates potential for coupled-storage-aware planning”。

## 3. 摘要升级规则

摘要最终版本建议遵守以下规则：

1. 第一段先写问题和方法，不抢结果。
2. 第二段只写已经由 full 结果支持的 3-4 个最强数字。
3. 不在摘要里提前写还没完成的卡诺电池量化结论。
4. 如果 Songshan Lake trade-off 明显，摘要中要避免“uniform superiority”这种过强表述。

## 4. 结论升级规则

最终结论要分三段：

1. **方法结论**
   - EQD 的 planning-stage value
2. **运行验证结论**
   - 8760h post-analysis 证明该指标是有效 proxy objective
3. **设备层结论**
   - Carnot battery 的 planning value 及其与 EQD 的相互验证

不建议在结论里把“未来工作”写成一个很长的清单，保留 3-4 条最关键扩展即可。

## 5. 结果回来后的回填顺序

推荐按以下顺序改稿：

1. `论文撰写/paper/sections/results.tex`
2. `论文撰写/paper/sections/conclusions.tex`
3. `论文撰写/paper/sections/introduction.tex`
4. `论文撰写/paper/main.tex` 的 abstract
5. `docs/03_sci_paper/latest_logic_structure.md`（若结论边界变化）
6. `docs/03_sci_paper/figure_table_plan.md`

## 6. 当前可先做、不必等 full 的动作

- 画系统拓扑图
- 统一 figure label / table label 命名
- 修正参考文献 key 和年份 hygiene
- 收紧引言中的 gap 句子
- 给 Results 所有小节补过渡句和论证功能句
