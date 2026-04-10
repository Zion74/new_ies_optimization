---
name: research-doc-maintainer
description: 当用户要求整理、合并、清理、归档或同步维护本仓库的会议论文 / SCI 论文 / 硕士论文文档体系时使用。特别适用于论文逻辑结构、研究架构、三层映射、实验-图表-代码映射、文档沉淀、合并笔记、归档旧文档等任务。
---

# Research Doc Maintainer

本仓库现在采用两套互相映射的“三层”体系：

- **论文载体三层**：会议论文 / SCI 论文 / 硕士论文
- **研究内容三层**：规划层 / 设备层 / 运行层

主动文档的唯一权威入口在 `docs/`，正式稿件源码只保留在 `论文撰写/`。

## 何时必须用这个 skill

只要用户提出以下任一类请求，就先用本 skill：

- 更新会议论文、SCI 论文、硕士论文的逻辑结构
- 梳理最新研究内容、研究架构、章节边界
- 制作或更新“三层映射表”
- 整理实验 / 图表 / 代码映射
- 合并分散笔记，沉淀为新的权威文档
- 清理活跃目录中的旧结构稿并归档
- 要求“以后每次更新论文逻辑结构时，也同步更新文档”

## 先读哪些文件

1. `docs/README.md`
2. `docs/01_overview/latest_research_architecture.md`
3. `docs/01_overview/three_layer_mapping.md`
4. 对应层级目录：
   - 会议论文：`docs/02_conference_paper/`
   - SCI 论文：`docs/03_sci_paper/`
   - 硕士论文：`docs/04_master_thesis/`
5. 治理规则：
   - `docs/90_governance/documentation_maintenance_rules.md`
   - `docs/90_governance/archiving_rules.md`

## 必须遵守的工作流

1. 先判断这次变化影响的是哪一个载体层（会议 / SCI / 硕士）以及哪一个研究层（规划 / 设备 / 运行）。
2. 更新对应的 `latest_logic_structure.md`。
3. 更新对应的实验 / 图表 / 代码映射文档。
4. 如果三层关系本身也变了，再同步更新：
   - `docs/01_overview/latest_research_architecture.md`
   - `docs/01_overview/three_layer_mapping.md`
5. 清理散落旧笔记：
   - 活跃结构说明写回 `docs/`
   - 支持材料移到 `论文撰写/support/` 或 `论文撰写/reports/`
   - 被替代的旧结构稿移到 `docs/99_archive/`
6. 检查稿件源码目录是否仍然干净：
   - `论文撰写/会议/` 只保留正式源码、图表、数据、README、编译产物
   - `论文撰写/paper/` 只保留正式源码、图表、参考文献、README、编译产物

## 非协商规则

- 不允许在不同目录同时保留两份“最新版结构说明”。
- 不允许继续把结构草稿堆回 `研究思路/` 或 `论文撰写/` 根目录。
- 会议稿不应膨胀成 SCI 缩略版；硕士论文才承担规划-设备-运行完整闭环。
- 若归档了旧文档，必须让 README 或权威文档能解释“现在该看哪里”。

## 交付目标

做完此类任务后，仓库应当能让下一位助手快速回答：

- 会议论文现在到底讲什么？
- SCI 论文现在到底讲什么？
- 硕士论文相对前两者新增了什么？
- 每一层各自对应哪些实验、图表、代码文件？
- 哪些文档只是历史材料，现在应该去哪里看最新版本？

