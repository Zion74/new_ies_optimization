# E0-D-29 外送耦合全局上界紧化合同

更新时间：2026-07-14

状态：**24 h 等价性门已通过；336 h 的 1800 s HiGHS 全局探针将合法上界从 D27 的 `1,081,649.139331` 收紧到 `845,052.030831 MWh/a`，改善 `21.8737%`。D29 不改变 D19 可接受调度集，只紧化 D27 正负差值模型的连续松弛；336 h 仍未闭合。**

## 1. 问题与目标

D27 已把 336 h 最大端的全局上界从 `1,362,149.106858` 收紧到 `1,081,649.139331 MWh/a`，但全局 gap 仍宽。D28 的两个异质符号种子没有提高 `36,382.462799 MWh/a` 可行下界，说明继续堆叠短预算方向启动不是当前最有效的路线。

D29 因而直接处理全局上界：保持 D27 的正负差值分解、全部主整数模式和全部符号二元开放，增加由两架构逐时 PCC 外送量推出的有效不等式，以去除 LP 松弛中不可能的“同时正负差值质量”。

## 2. 逐时有效不等式

令无储能比较架构外送为 $x_t$，TES 候选架构外送为 $y_t$，共同 PCC 容量为 $M$，且

\[
0\le x_t,y_t\le M,
\qquad
y_t-x_t=p_t-n_t,
\qquad
|y_t-x_t|=p_t+n_t.
\]

D27 已用一个符号二元保证整数解中 $p_t$ 与 $n_t$ 不会同时为正。D29 对每个时段再增加

\[
\begin{aligned}
p_t&\le y_t, & p_t&\le M-x_t,\\
n_t&\le x_t, & n_t&\le M-y_t.
\end{aligned}
\]

当 $y_t\ge x_t$ 时，$p_t=y_t-x_t$，前两式分别由 $x_t\ge0$ 与 $y_t\le M$ 推出；负差值同理。因此四类约束对每个整数可行解都成立，不固定符号，也不删除任何真实调度。

## 3. 年化质量守恒与总帽

两架构满足相同年度 PCC 外送服务 $E$。定义

\[
P=\Delta t\sum_t w_t p_t,
\qquad
N=\Delta t\sum_t w_t n_t,
\qquad
H=\Delta t\sum_t w_t.
\]

由两架构外送总量相同可得 $P=N$。逐时约束求和还给出

\[
P,N\le E,
\qquad
P,N\le MH-E.
\]

D29 将这 1 条质量平衡和 4 条总帽显式写入模型。它们在整数可行集上是冗余的，但能让求解器在分支前直接利用共同服务与 PCC 容量结构。

## 4. 验收与科学边界

- 24 h 合并 D27 精确证书后，严格区间必须仍为唯一点 `26,010.174929 MWh/a`；
- 336 h 新严格下界不得低于 D27，新严格上界不得高于 D27；
- 最大正归一化残差不高于 `1e-9`；
- 求解器目标与逐时轨迹 L1 重算差绝对值不高于 `1e-4 MWh/a`，严格下界只使用轨迹重算值或既有 D27 证人；
- `primary_integer_patterns_reopened=true`、`sign_binaries_reopened=true`；
- `feasible_set_changed_for_integer_solutions=false`；
- 有限 global dual 才允许写为全局 L1 上界；
- `actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

## 5. 结果

| 窗口 | D27 严格区间 / MWh/a | D29 primal / 轨迹重算 / dual / MWh/a | D29 首选严格区间 / MWh/a | 上界改善 |
|---|---:|---:|---:|---:|
| 24 h | `[26,010.174929, 26,010.174929]` | `26,010.174937 / 26,010.174919 / 26,010.174937` | `[26,010.174929, 26,010.174929]` | 0，保留 D27 精确点 |
| 336 h | `[36,382.462799, 1,081,649.139331]` | `36,382.462799 / 36,382.462799 / 845,052.030831` | `[36,382.462799, 845,052.030831]` | `236,597.108500 MWh/a`（`21.8737%`） |

24 h D29 求解器目标与轨迹重算差为 `-1.7997e-5 MWh/a`，小于预注册 `1e-4 MWh/a` 重算门；因此严格结果沿用 D27 已精确闭合的点，而不把 D29 solver primal 提升为新证书。336 h 两者差为 0，最大正归一化残差为 `6.3615e-13`，finite global dual 合法。

336 h 运行在 1800 s 达到 `maxtimelimit`，相对 gap 从 D27 的 `28.72996` 降至 `22.22691`。相对 D26 原始上界 `1,362,149.106858 MWh/a`，D27+D29 累计收紧 `517,097.076027 MWh/a`（`37.9619%`）。但当前上下界仍相差约 23.23 倍，不能写成闭合、实际结算暴露或技术赢家。

## 6. 实现与复现

- 运行器：`src/tes_bess_boundary/d29_export_linked_bound_tightening.py`；
- 规范汇总：`src/tes_bess_boundary/d29_certification_bundle.py`；
- 回归：`tests/test_d29_export_linked_bound_tightening.py`、`tests/test_d29_certification_bundle.py`；
- OpenBayes 原始运行：`/root/e0-b-20260711-019f4f64/e0d29_export_linked_bound_tightening/`；
- 规范产物：`数据采集/e0d29_export_linked_bound_tightening/`；
- 求解器：HiGHS 1.15.1，不使用 Gurobi。
