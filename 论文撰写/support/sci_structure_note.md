论所有引用的 key 都在 references.bib 中有对应条目，论文结构完整。

论文初稿已完成，文件结构如下：

- **[论文撰写/会议/](../会议/)** — IEEE 会议前导稿：根目录 LaTeX + `data/`；`guides/`（反抄袭等）、`word/`（Word 草稿）、`archive/superseded_pre_IEMI/`（废弃 Markdown）。说明见 `会议/README.md` 与 `会议/agents.md`（原 `研究思路/IEEE会议` 已并入此处）

[论文撰写/paper/](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/)

- [main.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/main.tex) — Elsevier Applied Energy 格式主文件，含完整 Abstract
- [references.bib](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/references.bib) — 30 篇真实文献
- [sections/introduction.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/introduction.tex) — 引言（5段，含研究背景、文献综述、研究空白、两个创新点）
- [sections/system_modeling.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/system_modeling.tex) — 系统建模（CCHP拓扑、9类设备、卡诺电池、OEMOF调度、典型日方法）
- [sections/matching_index.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/matching_index.tex) — 能质加权匹配度指标（㶲分析理论、EQD公式、5种方法对比表）
- [sections/optimization.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/optimization.tex) — 双目标优化框架（决策变量、目标函数、NSGA-II、种群继承）
- [sections/case_studies.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/case_studies.tex) — 案例研究（两个案例参数表、四组实验设计表）
- [sections/results.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/results.tex) — 结果与讨论（四组实验的数据表格、分析、讨论）
- [sections/conclusions.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/conclusions.tex) — 结论与展望

**下一步你需要做的**：

1. 填写作者信息和单位（main.tex 第23-30行）
2. 用 Python/matplotlib 画图并插入（系统拓扑图、Pareto前沿对比图等）
3. 正式实验（nind=50, maxgen=100）跑完后更新结果数据
4. 在 CNKI 补充中文文献（源荷匹配领域的中文核心文献）
5. 用 LaTeX 编译验证格式

---

## IEEE 会议前导稿（概念验证）

已合并至 **[../会议/](../会议/)**：根目录为 LaTeX + `data/` + `references.bib`；`guides/`、`word/`、`archive/` 见 [../会议/README.md](../会议/README.md)。

- [../会议/main_conference.tex](../会议/main_conference.tex) — IEEEtran `conference`，**IEMI**
- [../会议/sections_conference/](../会议/sections_conference/)
- [../会议/agents.md](../会议/agents.md) — 给 AI 助手的编辑约定

编译：在 `论文撰写/会议/` 下运行 `pdflatex main_conference.tex`（需 `IEEEtran.cls`）；期刊稿仍用本目录 `elsarticle`。

