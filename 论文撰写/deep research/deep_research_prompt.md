# Deep Research Prompt：㶲分析在综合能源系统中的应用文献搜索

## 搜索目标

我正在撰写一篇关于"基于㶲（exergy）加权的源荷匹配度指标用于分布式CCHP系统容量规划"的SCI论文，投稿目标为 Applied Energy / Energy Conversion and Management 级别期刊。

我需要找到高质量的文献来支撑以下核心论断：

### 论断1：电能与低温热能的㶲含量差异巨大
- 电能是纯㶲（exergy factor = 1.0）
- 低温供热（60-70°C）的㶲含量仅为能量的10-15%
- 低温供冷（5-10°C）的㶲含量仅为能量的5-10%
- 因此，1kW的电偏差在㶲层面比1kW的热偏差严重7-15倍

### 论断2：㶲分析可以用于综合能源系统的评价和优化
- 㶲效率比能量效率更能反映系统的热力学性能
- 㶲分析可以识别系统中的不可逆损失来源
- 基于㶲的优化可以引导更合理的资源配置

### 论断3：现有综合能源系统研究中，等权重处理电热冷是不科学的
- 传统方法将1kWh电和1kWh热等价看待
- 这违反了热力学第二定律
- 需要基于㶲的能质系数来区分不同能源形式的"质量"

### 论断4：卡诺电池（Carnot Battery）是一种有前景的电热耦合储能技术，适合集成到CCHP系统中
- 卡诺电池通过热泵充电（电→热）、热机放电（热→电），实现电热双向耦合
- 充放电过程中的余热可回收用于供热，形成电储能+热回收的协同效应
- 卡诺电池的电热耦合特性使其成为检验㶲加权匹配度方法的天然试验台
- 现有文献中，卡诺电池主要作为独立储能技术研究，**将其集成到CCHP系统并与源荷匹配度优化结合的研究尚属空白**

## 搜索要求

### 优先级1：顶刊论文（必须找到）
请在以下期刊中搜索：
- **Applied Energy** (IF ~11)
- **Energy Conversion and Management** (IF ~11)
- **Energy** (IF ~9)
- **Renewable and Sustainable Energy Reviews** (IF ~15)
- **Applied Thermal Engineering** (IF ~6)
- **International Journal of Exergy** (专业㶲分析期刊)

### 优先级2：经典教材和综述
- Bejan, Tsatsaronis, Moran 等人的㶲分析经典著作
- 综合能源系统㶲分析的综述论文
- 建筑能源系统㶲分析的综述论文

### 优先级3：中国学者的相关工作
- **贾宏杰**（天津大学）：㶲流计算模型、多能系统㶲分析
- **陈群**（清华大学）：能质系数（energy quality coefficient）
- 其他中国学者在综合能源系统㶲分析方面的工作

## 具体搜索关键词

### 英文关键词组合
1. `"exergy analysis" AND "integrated energy system" AND ("planning" OR "optimization")`
2. `"exergy" AND "energy quality" AND ("CCHP" OR "combined cooling heating and power")`
3. `"exergy factor" AND ("electricity" OR "heat" OR "cooling") AND "building"`
4. `"low exergy" AND "building" AND ("heating" OR "cooling")`
5. `"exergy-based" AND "multi-energy system" AND "optimization"`
6. `"energy quality coefficient" AND "integrated energy system"`
7. `"exergy" AND "source-load matching"` 或 `"supply-demand matching"`
8. `"Carnot exergy" AND "energy system" AND "planning"`
9. `"exergy destruction" AND "CCHP" AND "optimization"`
10. `"thermodynamic quality" AND "energy carrier" AND "comparison"`
11. `"Carnot battery" AND ("CCHP" OR "integrated energy system" OR "combined cooling heating")`
12. `"Carnot battery" AND ("capacity planning" OR "optimal sizing" OR "co-optimization")`
13. `"pumped thermal energy storage" AND ("CCHP" OR "district heating" OR "waste heat recovery")`
14. `"Carnot battery" AND "waste heat" AND ("building" OR "district")`
15. `"electro-thermal" AND "coupled storage" AND ("planning" OR "optimization" OR "sizing")`
16. `"Carnot battery" AND ("review" OR "survey" OR "state-of-the-art") AND 2022..2025`

### 中文关键词（用于搜索中文期刊或中国学者的英文论文）
1. `贾宏杰 㶲` 或 `Jia Hongjie exergy`
2. `㶲分析 综合能源系统` 或 `exergy analysis integrated energy system China`
3. `能质系数 综合能源` 或 `energy quality coefficient`
4. `陈群 能质` 或 `Chen Qun energy quality`

## 我特别需要的信息

对于每篇找到的文献，请提供：

1. **完整引用信息**：作者、标题、期刊、年份、卷号、页码、DOI
2. **期刊影响因子**（大致即可）
3. **与我论文的关联**：这篇文献支撑了我的哪个论断？
4. **关键结论/数据**：文献中与我论断直接相关的具体结论或数据
5. **可引用的原文**：如果有直接支撑我论断的原文句子，请摘录

## 特别关注：贾宏杰的工作

贾宏杰（Jia Hongjie），天津大学教授，在多能系统㶲分析方面有重要工作。我需要：

1. 找到他关于"㶲流计算模型"的论文
2. 找到他关于"多能系统㶲分析"的论文
3. 分析他的工作与我的工作的**区别和联系**：
   - 他的工作：㶲流计算 → 系统运行评价/优化
   - 我的工作：㶲系数 → 源荷匹配度指标 → 容量规划
   - 关键区别：他用㶲做"评价"，我用㶲做"优化目标函数中的权重"

同时也请搜索以下可能相关的学者：
- Yang 等人的"㶲-碳静态耦合优化方法"
- 其他将㶲分析与多能系统规划/运行结合的工作

## 特别关注：卡诺电池在CCHP/综合能源系统中的应用

卡诺电池（Carnot Battery）是本文的第二个创新点。我需要找到以下文献：

### 需要找的文献类型

1. **卡诺电池综述论文**（2020-2025，顶刊优先）
   - 技术原理、发展现状、商业化进展
   - 已有：Dumont et al. (2022, J. Energy Storage), Novotny et al. (2022, Energies)
   - 需要补充：Applied Energy / ECM / RSER 上的综述

2. **卡诺电池与建筑/区域供能结合的论文**
   - 卡诺电池用于区域供热（district heating）
   - 卡诺电池余热回收用于建筑供暖
   - 卡诺电池与CHP/CCHP系统的集成

3. **卡诺电池容量优化/规划的论文**
   - 卡诺电池的最优容量配置
   - 卡诺电池与其他储能设备的协同优化
   - 卡诺电池在多目标优化中的应用

4. **电热耦合储能的一般性论文**
   - 不限于卡诺电池，包括其他电热耦合储能技术
   - 如：pumped thermal energy storage (PTES), power-to-heat-to-power
   - 重点关注：电热耦合储能在IES规划中的价值

### 我需要回答的关键问题

- **卡诺电池集成到CCHP系统中是否有先例？** 如果没有，这就是一个明确的研究空白
- **卡诺电池的余热回收在供热场景中的价值有多大？** 需要定量数据
- **现有卡诺电池研究主要关注什么层面？** （设备层面的效率优化 vs 系统层面的容量规划）
- **将卡诺电池与源荷匹配度优化结合的研究是否存在？** 预期答案是不存在（这是我的创新点）

### 与我论文的关联

我的论文中卡诺电池的定位：
- **不是**独立的技术创新（卡诺电池本身不是我发明的）
- **而是**㶲加权匹配度方法的"试金石"——只有能区分能源品质的匹配度指标，才能正确识别电热耦合储能的价值
- 实验预期：EQD方法（㶲加权）配置的卡诺电池容量 > Std方法（等权重），从而反向验证㶲加权的必要性

## 输出格式

请按以下格式整理结果：

### A. 顶刊文献列表（按相关性排序）

| # | 作者 | 标题 | 期刊 | 年份 | IF | 支撑论断 | 关键数据/结论 |
|---|------|------|------|------|-----|---------|-------------|
| 1 | ... | ... | ... | ... | ... | 论断1 | ... |

### B. 贾宏杰相关工作分析

| # | 标题 | 期刊 | 年份 | 核心内容 | 与我工作的区别 |
|---|------|------|------|---------|-------------|

### B2. 卡诺电池相关文献

| # | 作者 | 标题 | 期刊 | 年份 | IF | 与CCHP/IES的关联 | 关键数据/结论 |
|---|------|------|------|------|-----|-----------------|-------------|

### C. 推荐的BibTeX条目

为每篇推荐文献提供完整的BibTeX条目，方便我直接复制到 references.bib。

### D. 论文中的引用建议

建议在论文的哪个位置引用哪篇文献，以及引用时的表述方式。

## 补充背景

我的论文核心创新：
1. **㶲加权匹配度指标**：用卡诺㶲系数（λ_h = 1-T₀/Tₕ, λ_c = T₀/T_c-1）作为能质系数，加权三维欧氏距离
2. **卡诺电池集成**：将卡诺电池（Carnot battery）作为电热耦合储能设备集成到CCHP系统
3. **后优化验证**：通过8760小时全年调度验证匹配度改善带来的运行指标提升

现有引用的㶲相关文献（质量不够高，需要替换或补充）：
- Dincer & Rosen (2001), Entropy — 基础但期刊影响因子低
- Sakulpipatsin et al. (2018), Buildings — 期刊影响因子低
- Torchio et al. (2015), Energy Conversion and Management — 还行但不够直接
- Meggers & Leibundgut (2012), Energy — 还行
- Schmidt (2004), Energy and Buildings — 较老

现有引用的卡诺电池文献（需要补充顶刊）：
- Dumont et al. (2022), Journal of Energy Storage — 综述，还行但不是顶刊
- Novotny et al. (2022), Energies — MDPI期刊，IF偏低
- Steinmann et al. (2020), Energy Technology — 还行
- McTigue et al. (2022), Energy Conversion and Management — 这篇不错
- Frate et al. (2020), Energies — MDPI期刊，IF偏低
- **缺少**：卡诺电池与CCHP/IES集成的论文、卡诺电池在系统规划层面的论文

希望找到 2018-2025 年发表在 Applied Energy / Energy / ECM / RSER 等顶刊上的文献来替换或补充。
