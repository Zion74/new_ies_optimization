# Agent instructions: `论文撰写/会议`

面向在本目录工作的 AI 助手（Cursor / Copilot 等）。与仓库根目录 `CLAUDE.md`、期刊 `论文撰写/paper/` 并列阅读。

## 1. 本文件夹是什么

- **IEEE 会议前导稿**：`main_conference.tex` + `sections_conference/`，核心术语为 **IEMI**（Instantaneous Euclidean Matching Index），强调**时刻级三维向量 + 欧氏距离**的匹配度量，与「先逐能流压缩再相加」的 Std 类指标对照。
- **不是** Applied Energy 长文的压缩版：期刊稿仍在 `论文撰写/paper/`，负责㶲/能质、双案例、卡诺电池等**完整论证**。
- **数据真源**：`data/source_manifest.txt` 指向的 `Results/...` 与 CSV；改表前先核对 manifest，避免叙事与实验配置不一致。

## 2. 编辑优先级与禁忌

1. **优先修改** `sections_conference/*.tex` 与 `main_conference.tex`；保持与 `data/` 中已有数字可核对。
2. **勿**把 `archive/superseded_pre_IEMI/` 里的旧稿内容合并回正文（除非用户明确要求恢复某一表述）。
3. **勿**删除或改写 `data/raw_pareto/`、`data/post_analysis_budget/` 下的 CSV 作为「清理」——这些是论文数值来源；清理只针对明显重复的**草稿文档**。
4. 术语：**会议稿避免使用 EQD** 作为方法简称（易与 Exergy-weighted 混淆）；期刊稿可用原有 EQD 表述。
5. **$L_2$ 动机**：若涉及与 $L_1$ 对比，须保留「采用欧氏范数是为几何意义上的向量长度，而非断言比线性加总更严厉」的表述（见 `matching_index.tex`）。

## 3. 与用户「研究思路」对齐

- 会议贡献表述应为：**向量–时刻耦合的匹配框架 + 欧氏度量 + 德国概念验证**（Pareto 宽度、预算对齐运行指标）。
- 㶲加权、熵权、卡诺电池等若出现，应压缩为 **Discussion / journal extension** 指向期刊稿，避免会议正文大段第二定律推导。

## 4. 脚本与路径约定

- `scripts/export_ieee_conference_data.py`：默认 `论文撰写/会议/data/raw_pareto` → `summary_conference.csv`。
- `scripts/archive_ieee_unit_lambda.py`：写入 `论文撰写/会议/data/raw_pareto_unit_lambda` 与 `summary_conference_unit_lambda.csv`。
- 修改默认路径时同步更新本 `agents.md` 与 `README.md`。

## 5. 新增材料放哪里

| 类型 | 位置 |
|------|------|
| LaTeX 节、图、表 | `sections_conference/` 或同级 `figures/`（若新建请更新 README） |
| 反抄袭、协作说明 | `guides/` |
| Word / PPT 草稿 | `word/` 或新建 `slides/`（并在 README 一行说明） |
| 已废弃但想保留的 Markdown | `archive/superseded_pre_IEMI/` 并在 `archive/README.md` 一句话说明 |

## 6. 编译与引用

- `references.bib` 与 `main_conference.tex` **同目录**；`\bibliography{references}` 勿改文件名除非同步改 bib。
- 期刊与会议 **共用文献库** 时，以各自目录下的 `references.bib` 为准；合并条目注意避免重复 key。
