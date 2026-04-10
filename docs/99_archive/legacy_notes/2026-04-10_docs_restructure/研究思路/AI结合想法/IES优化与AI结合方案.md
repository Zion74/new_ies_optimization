# 综合能源系统优化与 AI 结合方案

> 基于当前 `cchp_gaproblem.py` / `cchp_gasolution.py` / `operation.py` 代码的深度分析
> 撰写时间：2026-03-16

---

## 一、现状梳理：代码里哪些地方需要"人工判断"

在当前纯运筹优化框架中，以下环节完全依赖研究者手动决策：

| 环节 | 当前做法 | 痛点 |
|------|---------|------|
| 选择匹配度方法（A/B/C/D/E） | 手动改 `methods_to_run` | 不知道哪种方法最适合当前场景 |
| 设定能质系数 λ_e/λ_h/λ_c | 硬编码 0.6 / 0.5 | 理论值与实际场景可能不符 |
| 设定算法参数 nind/maxgen | 手动调 | 不知道多少代够用 |
| 解读 Pareto 前沿 | 人工看图选点 | 主观，难以复现 |
| 判断结果是否合理 | 人工对比历史结果 | 耗时，容易遗漏异常 |
| 设备效率参数（COP、效率） | 硬编码常数 | 不同气候/季节应该不同 |
| 典型日聚类数量（k=14） | 固定值 | 不同数据集最优 k 不同 |

---

## 二、AI 结合的四个层次

### 层次 1：AI 作为"智能助手"——对话式参数配置（最易实现）

**核心思路**：用 Claude API 包裹整个优化流程，研究者用自然语言描述需求，AI 自动翻译成代码参数。

**具体场景**：

```
用户："我想比较一下能质耦合方法和师兄的波动率方法，
      用中等规模跑一下，不用太精确，快点出结果"

AI 自动设置：
  methods_to_run = ["std", "euclidean"]
  nind = 30
  maxgen = 50
  pool_type = "Process"
  inherit_population = True
```

**实现方式**：
- 用 Claude API 的 tool_use 功能，定义 `set_optimization_params` 工具
- AI 解析自然语言 → 调用工具 → 生成配置 → 启动优化
- 优化完成后 AI 自动读取结果并生成文字摘要

**代码接入点**：在 `cchp_gasolution.py` 的 `run_comparative_study()` 入口前加一层 AI 对话层

---

### 层次 2：AI 作为"结果解读器"——自动分析 Pareto 前沿（中等难度）

**核心思路**：优化完成后，把 Pareto 前沿数据喂给 LLM，让它自动生成分析报告，并推荐"最佳折中方案"。

**具体能做什么**：

1. **自动识别 Pareto 前沿形状**
   - "前沿呈现明显的凸形，说明经济性和匹配度之间存在强烈的权衡关系"
   - "前沿右侧有一个'肘点'，建议选择该点作为工程实施方案"

2. **自动对比两种方法的差异**
   - 读取 `comparison_report.md` 中的数据
   - 解释为什么方案C（Euclidean）配置了更多风电（WT: 1635 kW vs 397 kW）
   - 解释为什么方案C的电储能大幅增加（ES: 3062 kW vs 49 kW）

3. **自动生成论文段落草稿**
   - 输入：Pareto 数据 + 设备配置表
   - 输出：可直接用于论文 Case Study 章节的英文段落

**实现方式**：
```python
# 伪代码示意
def ai_analyze_results(result_dir):
    pareto_data = load_pareto_csv(result_dir)
    report = load_comparison_report(result_dir)

    prompt = f"""
    以下是综合能源系统优化的 Pareto 前沿结果：
    {pareto_data}

    请分析：
    1. 两种方法的 Pareto 前沿质量对比
    2. 设备配置差异的物理原因
    3. 推荐的工程实施方案（给出具体的设备容量）
    4. 生成一段 150 词的英文 Case Study 摘要
    """

    response = claude_client.messages.create(
        model="claude-opus-4-6",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content
```

---

### 层次 3：AI 作为"参数调优 Agent"——自适应优化（较难，高价值）

**核心思路**：用 AI Agent 替代研究者手动调参，通过多轮迭代自动找到最优的算法参数和能质系数。

**Agent 工作流程**：

```
第1轮：用小规模（nind=10, maxgen=5）快速探索
  → AI 观察收敛曲线，判断是否需要更多代数

第2轮：根据第1轮结果，AI 决定是否调整 λ_h/λ_c
  → 如果热储能配置过大，说明 λ_h 可能偏高，AI 自动降低

第3轮：用中等规模（nind=30, maxgen=50）精化
  → AI 判断 Pareto 前沿是否收敛（超体积变化 < 1%）

第4轮：如果未收敛，继续增加代数；如果收敛，输出最终结果
```

**关键技术**：
- **工具定义**：`run_optimization(method, nind, maxgen, lambda_h, lambda_c)` → 返回 Pareto 超体积
- **停止条件**：AI 判断"超体积变化 < 阈值"或"已达最大预算"
- **记忆机制**：把每轮结果存入上下文，AI 基于历史决策下一步

**能质系数自适应的具体逻辑**：
```
AI 观察到：方案C 的热储能 HS = 3832 kW（远大于方案B的 3001 kW）
AI 推断：当前 λ_h = 0.6 可能过高，导致系统过度重视热匹配
AI 决策：将 λ_h 从 0.6 降至 0.4，重新运行，观察热储能是否减小
AI 验证：如果热储能减小且 Pareto 超体积不下降，则接受新参数
```

---

### 层次 4：AI 作为"研究设计顾问"——方案选择与创新建议（最高层次）

**核心思路**：在研究开始前，让 AI 分析负荷数据特征，自动推荐最适合的匹配度方法，并给出创新方向建议。

**具体能做什么**：

1. **负荷特征分析 → 方法推荐**
   ```
   AI 分析 mergedData.csv：
   - 电负荷峰谷比：2.3（中等波动）
   - 热负荷季节性：强（冬夏差异 3 倍）
   - 风光互补性：弱（相关系数 0.12）

   AI 推荐：
   "由于热负荷季节性强，建议使用 Euclidean 方法（方案C），
    因为它能通过能质系数自动降低热匹配的权重，
    避免为季节性热负荷配置过大的储热设备"
   ```

2. **跨场景泛化建议**
   - 当前代码只有德国案例，AI 可以建议："如果迁移到中国北方供暖场景，λ_h 应提高到 0.8，因为供热温度更高（80°C vs 70°C）"

3. **创新点挖掘**
   - AI 读取现有 5 种方法的对比结果，自动发现"方案D（Pearson）在低可再生能源比例时表现最差"，建议增加一个"分段匹配度"方法作为新的对比组

---

## 三、最推荐的落地方案：结果解读 Agent

综合考虑实现难度和研究价值，**最推荐先实现层次2（结果解读器）**，原因：

1. **接入成本低**：只需在优化完成后调用一次 Claude API，不改动核心优化代码
2. **立竿见影**：直接解决"看 Pareto 图不知道选哪个点"的痛点
3. **论文价值高**：自动生成的分析段落可以直接用于论文，节省大量写作时间
4. **可扩展**：后续可以在此基础上逐步升级到层次3

**最小可行产品（MVP）设计**：

```python
# ai_result_analyzer.py
# 在 cchp_gasolution.py 的 run_comparative_study() 末尾调用

def analyze_with_ai(results, result_dir):
    """
    输入：优化结果字典 + 结果目录
    输出：AI 生成的分析报告（中文 + 英文摘要）
    """
    import anthropic

    # 1. 整理数据
    summary = build_result_summary(results)  # 提取关键数字

    # 2. 调用 Claude
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": ANALYSIS_PROMPT.format(summary=summary)
        }]
    )

    # 3. 保存报告
    ai_report_path = os.path.join(result_dir, "ai_analysis_report.md")
    with open(ai_report_path, "w", encoding="utf-8") as f:
        f.write(response.content[0].text)

    return response.content[0].text
```

---

## 四、与当前代码的具体接入点

| AI 功能 | 接入位置 | 改动量 |
|---------|---------|--------|
| 自然语言配置参数 | `cchp_gasolution.py` 第 554 行 `if __name__ == "__main__"` 前 | 小 |
| 结果自动解读 | `generate_comparison_report()` 函数末尾 | 小 |
| 参数自适应 Agent | 包裹 `run_single_experiment()` 的外层循环 | 中 |
| 负荷特征分析 | `CCHPProblem.__init__()` 数据加载后 | 中 |
| 论文段落生成 | 独立脚本，读取 Result 文件夹 | 独立 |

---

## 五、技术栈建议

- **LLM**：Claude Sonnet 4.6（速度快，适合迭代调用）
- **Agent 框架**：Claude API tool_use（无需额外框架，直接用 anthropic SDK）
- **数据传递**：把 Pareto CSV 数据直接放入 prompt（数据量小，不超过 context 限制）
- **异步执行**：优化本身已经是多进程，AI 调用可以在优化完成后同步执行

---

## 六、预期效果

| 指标 | 当前 | 加入 AI 后 |
|------|------|-----------|
| 从"跑完优化"到"理解结果"的时间 | 30-60 分钟（人工分析） | 2-3 分钟（AI 自动） |
| 参数调优轮次 | 3-5 轮（手动） | 1-2 轮（AI 辅助） |
| 论文 Case Study 初稿时间 | 2-4 小时 | 10-20 分钟 |
| 方法选择的可解释性 | 低（主观） | 高（AI 给出理由） |
