# SCI 论文实验重审方案 v2（数据可信度分层后）

更新时间：2026-04-17
状态：已确认，进入实施阶段
上一版：`experiment_redesign_prompt.md`（诊断与诉求）

---

## 0. 本文档定位

本文档是**基于数据可信度分层后的实验重构正式方案**，由 v1 prompt（问题诊断）+ 重审讨论 + 用户确认后沉淀而成。

后续论文逻辑、章节结构、图表清单、代码实现均以本方案为准。凡涉及"SCI 论文实验如何设计"的讨论，优先读本文件，再读：

1. `docs/03_sci_paper/latest_logic_structure.md`
2. `docs/03_sci_paper/experiment_figure_code_map.md`
3. `docs/03_sci_paper/adversarial_review_phase2.md`
4. `docs/辩论确认/carnot_battery_parameters_consensus.md`
5. `docs/辩论确认/latest_松山湖数据与模型口径辩论共识.md`

---

## 1. 核心判断与主线调整

### 1.1 核心判断

现有 4 组实验设计的根本问题：**"方法论创新验证"的主证据链建立在可信度最低的数据上（松山湖合成数据）**，而可信度最高的德国案例只用于 5 方法 Pareto 对比，缺少卡诺电池相关实验。从 Phase 2 数据看，EQD 最干净的运行优势恰出现在 **Exp4@n100 松山湖+卡诺基准预算**处，这个场景同时踩中了"数据合成"和"单次运行"两个弱点。

### 1.2 主线调整

| 原主线 | 新主线 |
|---|---|
| 主线1：EQD 改变规划构型偏好 | **保留并强化**（跨案例、跨规模稳定） |
| 主线2：卡诺电池本身配置价值 | **保留并迁移证据基地**（从松山湖转到德国，加弃电消除机制） |
| 主线3：EQD 优势在高耦合场景兑现 | **限定场景并补强基准证据**（德国+CB 为主，松山湖为方向佐证） |
| 主线4：德国案例展示方法边界 | **并入 Discussion**（不再作为独立章节） |

### 1.3 案例定位调整

| 案例 | 原定位 | 新定位 | 原因 |
|---|---|---|---|
| 德国 | 主案例（仅承担 5 方法对比） | **主案例 + CB 证据基地** | 数据实测、参数可溯源 |
| 松山湖 | 并列主案例（承担 exp2/3/4） | **跨气候方向性验证** | 逐时数据合成、多项参数口径错误 |

---

## 2. 新实验编号（E 系列）

### 2.1 E1 — 德国方法基线对比（替代旧 exp1）

- **案例**：德国，无卡诺
- **方法**：`economic_only / std / euclidean / pearson / ssr`
- **目的**：在可信数据上建立 EQD 相对其他方法的构型偏好差异
- **代码入口**：`run.py --exp E1`
- **参数**：`n=100, g=200, process pool`
- **数据复用**：已有 `Results/服务器结果/第三次实验/第三次实验/exp1/` 的 n100×g200 可直接用于论文，只需重新后处理
- **论文位置**：Section 6.1

### 2.2 E2 — 德国卡诺电池消融（新增，替代旧 exp3）

- **案例**：德国
- **方法**：`euclidean`
- **对照**：无 CB vs 有 CB（`--carnot` 切换）
- **CB 参数**：`RTE=0.60, loss_rate=0.002/h, E/P∈[4h,8h]`，删 heat recovery
- **成本情景**：主结果用 `reference-literature`（`cb_invest_power=37€/kW·a`），Appendix 用 `optimistic`（`12-15€/kW·a`）做 break-even
- **目的**：
  - Phase 1：CB 在 EQD 下进入 Pareto 前沿的条件与代价
  - Phase 2：8760h 后验——CB 弃电消除机制是否在德国可再现
- **代码入口**：`run.py --exp E2`
- **论文位置**：Section 6.2

### 2.3 E3 — 德国方法-设备协同（新增，替代旧 exp4）

- **案例**：德国 + 卡诺
- **方法**：`std` vs `euclidean`
- **CB 参数**：同 E2
- **成本情景**：主结果 `reference-literature`
- **目的**：
  - Phase 1：EQD 与 Std 是否配置出不同的 CB 容量/时长
  - Phase 2：基准 / +10% / +30% 预算下运行指标对比
  - 诚实披露：电网波动 trade-off
- **代码入口**：`run.py --exp E3`
- **论文位置**：Section 6.3

### 2.4 E4 — 松山湖跨气候方向性验证（降级，替代旧 exp2+3+4）

- **案例**：松山湖（**重建数据**后）
- **必做**：
  - **E4a**：std vs euclidean（无 CB），`n=100, g=200`
  - **E4b**：euclidean × {无 CB, 有 CB}，`n=100, g=200`
- **可选**（时间充足）：
  - **E4c**：std+CB vs euclidean+CB
- **目的**：验证构型偏好差异 + CB 价值机制在冷主导气候下方向一致
- **代码入口**：`run.py --exp E4a` / `--exp E4b` / `--exp E4c`
- **论文位置**：Section 6.5（Supplementary）
- **必须披露**：数据合成性（逐时数据重建、热负荷完全假设、TMY 合成）

### 2.5 E5 — λ 敏感性与消融（新增，P0）

- **案例**：德国（主）+ 松山湖（补）
- **两部分**：
  - **E5a λ=1 消融**：令 `λ_e=λ_h=λ_c=1`（已有 `--unit-lambda` 开关支持），观察 EQD 退化行为
  - **E5b λ±30% 敏感性**：λ_h 和 λ_c 分别 ±30%（通过临时改 T0 / T_heat / T_cool 实现，或直接覆盖 lambda 值）
- **可选**：T0 季节性敏感（winter T0 与 summer T0 对换）
- **目的**：验证 λ 不是随意调参，方法排序在 λ 合理范围内不翻转
- **代码入口**：`scripts/lambda_sensitivity.py`（已有，需配合新 `--carnot-scenario` 更新）
- **论文位置**：Section 6.4

### 2.6 E6 — 韧性扰动（可选，Appendix）

- **案例**：德国 E3 最优解
- **扰动**：电价 ±20%、负荷 ±15%、气价 ±15%
- **代码入口**：`scripts/resilience_test.py`

### 2.7 与旧实验的映射关系

| 旧实验 | 新编号 | 处理方式 |
|---|---|---|
| exp1 | E1 | 保留，重命名 |
| exp2 | E4a（降级） | 降级为跨气候方向验证 |
| exp3 | E4b（降级）+ E2（新主）| 主 CB 消融叙事迁到德国 |
| exp4 | E4c（可选降级）+ E3（新主）| 主方法-设备协同叙事迁到德国 |

### 2.8 向后兼容

`run.py` 保留 `--exp 1/2/3/4` 的映射，但打印 deprecation warning 并建议使用 E 系列。具体映射：

```
--exp 1  → E1（无变化）
--exp 2  → E4a（warn: 仅保留构型差异，删除 +50% 预算对比叙事）
--exp 3  → E4b（warn: 主 CB 证据已迁至 E2）
--exp 4  → E4c（warn: 主方法-设备证据已迁至 E3）
```

---

## 3. 实验-图表-代码映射

| 实验 | 核心图 | 核心表 | 论文章节 |
|---|---|---|---|
| E1 | Fig 3: 德国 5 方法 Pareto + 构型偏好雷达图 | Tab 2: 容量配置对比 | 6.1 |
| E2 | Fig 4: 德国 CB 消融 Pareto + 弃电率对比 | Tab 3: CB 投资 break-even | 6.2 |
| E3 | Fig 5: 德国 std+CB vs EQD+CB 运行指标雷达 | Tab 4: CB 容量配置差异 | 6.3 |
| E5 | Fig 6: λ=1 / λ±30% 下方法排序变化 | - | 6.4 |
| E4 | Fig 7: 松山湖构型偏好跨气候一致性 | - | 6.5 |
| E6 | Fig A1 (Appendix): 扰动下成本退化 | - | Appendix |

详见 `docs/03_sci_paper/experiment_figure_code_map.md`（需同步更新）

---

## 4. 论文 Results 章节结构

```
6 Results and Discussion

6.1 Method-level configuration preference (German, no CB)                  [E1]
    - 6.1.1 Pareto and cost range across 5 methods
    - 6.1.2 Configuration preference shift (HP+AC vs GT+HS)
    - 6.1.3 Honest operational cross-check at +30% budget (n100 data)
    → 主线1：EQD 改变构型偏好（强）

6.2 Carnot battery as a test of device-value identification (German)       [E2]
    - 6.2.1 Pareto and break-even under two cost scenarios
    - 6.2.2 Curtailment elimination mechanism (Phase 2 new story)
    - 6.2.3 CB capacity/duration distribution
    → 主线2：CB 低代价换高匹配（强）

6.3 Method-device synergy under Carnot integration (German)                [E3]
    - 6.3.1 Pareto: EQD+CB vs Std+CB
    - 6.3.2 CB capacity/duration configuration differences
    - 6.3.3 Phase 2 runtime: self-sufficiency, purchase, curtailment
    - 6.3.4 Honest disclosure: grid volatility trade-off
    → 主线3：EQD 更能识别 CB 价值（中-强，依赖 E3 结果）

6.4 Robustness of the energy-quality weighting                             [E5]
    - 6.4.1 λ=1 ablation: degeneration behavior vs Std convergence
    - 6.4.2 λ±30% sensitivity: method ranking stability
    - 6.4.3 Discussion: T0 seasonal variation
    → 主线核心根基：λ 不是随意参数（强）

6.5 Cross-climate supplementary validation (Songshan Lake)                 [E4]
    - 6.5.1 Data reconstruction disclosure (limitations box)
    - 6.5.2 Configuration-preference direction match
    - 6.5.3 CB curtailment mechanism cross-climate
    → 跨气候方向性佐证（弱-中，明确降级）

6.6 Integrated discussion and limitations
    - Method-device coupling synthesis
    - German λ 小值场景下 EQD 运行层优势弱的物理解释
    - Grid volatility trade-off engineering implications
    - Data limitations (esp. Songshan synthetic hourly)
    - Future work: dynamic T0, robust optimization, 3rd objective
```

---

## 5. 重跑实验清单（按优先级）

### 5.1 P0（必做，决定论文成稿）

| # | 实验 | 参数 | 预计时间 |
|---|---|---|---|
| P0-1 | **代码微调** | operation.py 默认值 0.005→0.002；case_config.py 成本情景化 + 清理 cb_heat_recovery_ratio；run.py EXPERIMENTS 重构为 E 系列；新增 `--carnot-scenario optimistic/reference` | 代码 |
| P0-2 | **E2 德国 CB 消融**（reference 情景）| n100×g200, 2 方法组合 | 1.5-2h |
| P0-3 | **E3 德国 std+CB vs EQD+CB**（reference 情景）| n100×g200, 2 方法 | 1.5-2h |
| P0-4 | **E5a λ=1 消融**（德国 + 松山湖）| 2 方法 × 2 案例 | 2-3h |
| P0-5 | **E5b λ±30% 敏感性**（德国）| 4 点 × euclidean | 2-3h |

**P0 小计：约 8-10h 服务器 + 代码工作**

### 5.2 P1（强烈推荐）

| # | 实验 | 参数 | 预计时间 |
|---|---|---|---|
| P1-1 | **松山湖数据重建** | 按共识修正 generate_songshan_data.py + sanity check | 代码 0.5h + 审核 |
| P1-2 | **E4a 松山湖方法对比（重建数据）** | n100×g200, 2 方法 | 1h |
| P1-3 | **E4b 松山湖 CB 消融（重建数据）** | n100×g200, 2 方法 | 1.5h |
| P1-4 | **E2/E3 optimistic 情景补跑** | 同 P0-2/P0-3 换 cost | 3-4h |

**P1 小计：约 6-7h 服务器**

### 5.3 P2（可选）

| # | 实验 | 预计时间 |
|---|---|---|
| P2-1 | E3 多次独立运行（3×n80，不同 seed） | 3×1.5h |
| P2-2 | E6 韧性测试 | 3-4h |
| P2-3 | E4c 松山湖+CB std vs EQD | 1.5h |

### 5.4 总时间

- MVP：P0（约 8-10h）
- 推荐：P0+P1（约 15-20h）
- 完整：P0+P1+P2（约 25-30h）

---

## 6. 风险评估

### 风险 1：德国 E2/E3 EQD 无运行优势（概率：中-高）

德国 λ_c=0.064 很小，EQD 对冷侧引导弱；Exp1 Phase 2 已显示运行层弱于 Std。

**分级应对**：

- **A（首选）**：6.3 叙事从"EQD 运行更优"调整为"**EQD 产生不同的 CB 配置偏好**"——即使运行指标持平，方法影响 CB 容量/时长选择本身就是贡献。
- **B**：Discussion 显式讨论"λ 小值 + 热主导场景下 EQD 方法边界"，用 6.5（松山湖）做 EQD 优势场景的方向性佐证。
- **C**：用 E5 (λ=1 消融) 结果把 EQD 贡献拆为"距离度量 + λ 物理基础"两层。

### 风险 2：松山湖重建数据与旧结果趋势不符（概率：高）

ele_load 从 166 万降到 69.59 万 kWh 后，模型内生制冷耗电可能改变整体结构。

**应对**：
- 重建后先跑 economic_only 做 sanity check，确认隐含总电量量级与 PDF 一致
- 论文中明确"松山湖结果基于重建版数据"
- 若趋势与旧一致 → 强化 6.5；若相反 → Discussion 分析原因

### 风险 3：λ 敏感性结果不利（概率：低-中）

**应对**：诚实报告，把 EQD 贡献拆为"几何距离 + λ 物理基础"两层；给出 EQD 适用 λ 区间。

### 风险 4：审稿人质疑"只有一个真实案例"

**应对**：
- Introduction 明确"德国提供 credibility，松山湖提供 cross-climate directional check"
- Discussion 列出可扩展案例类型
- 强调方法框架本身 case-agnostic

### 风险 5：CB 参数选择被质疑

**应对**：
- 方法章节引用 Frate 2020、Zhao 2022、Lin 2026 三锚点
- 主结果 reference-literature，Appendix optimistic break-even
- 余热回收删除在方法章节说明理由

### 风险 6：服务器时间不够

**MVP 可发稿集**：P0-1 代码 + E2(ref) + E3(ref) + E5a(仅德国) + E4a
约 6-8h 服务器。删除 E5b、E4b、E6 放入 Future Work。

---

## 7. 松山湖数据处理策略

### 7.1 数据路径

1. **短期**：按 `docs/辩论确认/latest_松山湖数据与模型口径辩论共识.md` 重建合成数据（ele_load=非空调电、冷峰值 3460、表 2 月度）
2. **长期**：用户正在尝试获取真实 8760h 数据；若拿到则切换到 `--source measured` 模式，重跑 E4

### 7.2 脚本设计

`scripts/generate_songshan_data.py` 改造为可切换：

```
uv run python scripts/generate_songshan_data.py --source synthesis     # 默认
uv run python scripts/generate_songshan_data.py --source measured --csv <file>
```

重建后必须运行 `scripts/check_songshan_data.py` 做 sanity check：

- `ele_load` 年总量 ≈ 69.59 万kWh（±1%）
- `cool_load` 年总量 ≈ 291.15 万kWh（±2%）
- `cool_load` 峰值 ≈ 3460 kW（±100 kW）
- 冷电比（`cool/ele_load`）应显著大于 1
- 隐含总电（`ele_load + cool_load/COP_ec`）量级应接近 PDF 166 万kWh

---

## 8. 代码结构改动清单

| 文件 | 改动内容 | 优先级 |
|---|---|---|
| `operation.py` | `cb_loss_rate` 后备默认值 0.005 → 0.002；更新注释（已删 heat recovery） | P0 |
| `case_config.py` | 成本情景化（`cb_cost_scenarios` dict）；移除未使用的 `cb_heat_recovery_ratio` | P0 |
| `cchp_gaproblem.py` | ✅ E/P 约束已加（4h-8h） | 已完成 |
| `run.py` | `EXPERIMENTS` 重构为 E1/E2/E3/E4a/E4b/E5；新增 `--carnot-scenario` 选项；保留 `--exp 1-4` 向后兼容 | P0 |
| `scripts/generate_songshan_data.py` | 按松山湖共识重建；支持 `--source synthesis/measured` | P1 |
| `scripts/check_songshan_data.py` | 新增 sanity check 脚本 | P1 |
| `scripts/lambda_sensitivity.py` | 更新以支持 `--carnot-scenario` | P0 |
| `run_full_experiment.py` | 新增一站式脚本，替代 `run_pipeline.py`；Results/ 下创建单次实验主文件夹 | P0 |

---

## 9. 文档同步清单

按 `AGENTS.md` 第 8 节规则，本方案确认后以下文档必须同步更新：

| 文档 | 更新内容 | 状态 |
|---|---|---|
| `docs/03_sci_paper/latest_logic_structure.md` | Results 章节结构改为第 4 节的 6 小节；主线 1/2/3 表述更新 | 待更新 |
| `docs/03_sci_paper/experiment_figure_code_map.md` | S1-S8 改为 E1-E6；图表编号与代码入口更新 | 待更新 |
| `docs/03_sci_paper/figure_table_plan.md` | 图表槽位与数据来源更新 | 待更新 |
| `docs/03_sci_paper/server_full_run_checklist.md` | 新 P0/P1/P2 执行清单 | 待更新 |
| `docs/01_overview/latest_research_architecture.md` | 两案例定位变化 | 待更新 |
| `项目索引目录.md` | 第 6、9 节实验编号与映射更新 | 待更新 |

---

## 10. 变更日志

- **2026-04-17**：初版。确认新实验编号 E 系列、松山湖降级、CB 证据链迁至德国案例。代码改动清单待逐项实施。
