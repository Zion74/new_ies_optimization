# IEEE 会议稿（`论文撰写/会议`）

本目录只保留会议稿正式源码、图表、数据与 README，用于维护“规划层 concept validation”这条前导稿主线。

## 当前定位

- 会议稿主术语：**IEMI**
- 会议稿主任务：把“时刻级三能流联合失配应按向量方式理解”这一个核心点讲清楚
- 会议稿不是 Applied Energy 长文的压缩版

## 当前目录结构

```
会议/
├── main_conference.tex
├── sections_conference/
├── references.bib
├── data/
├── figures/
└── README.md
```

## 相关支持材料现在在哪里

- 会议辅助说明：`论文撰写/support/conference_agents.md`
- 会议写作辅助：`论文撰写/support/conference_guides/`
- 会议 Word 草稿：`论文撰写/support/conference_word/`
- pre-IEMI 历史草稿：`docs/99_archive/legacy_notes/2026-04-10_docs_restructure/会议_pre_iemi_archive/`

## 编译

在本目录下运行：

```bash
pdflatex main_conference.tex
bibtex main_conference
pdflatex main_conference.tex
pdflatex main_conference.tex
```

## 逻辑说明入口

如果要确认会议稿到底应该讲什么，先看：

- `docs/02_conference_paper/latest_logic_structure.md`
- `docs/02_conference_paper/experiment_figure_code_map.md`

