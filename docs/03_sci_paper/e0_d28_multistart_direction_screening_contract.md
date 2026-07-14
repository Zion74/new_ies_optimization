# E0-D-28 多方向启动筛查合同

更新时间：2026-07-14

状态：**336 h 的 `negated` 与 `alternating` 两个预注册方向已在 OpenBayes 完成。两条一步筛查均未找到高于 D27 的新可行 L1 证人；D28 当次运行未改变 D27 区间，且只生成可行 L1 下界，不生成全局上界。后续 D29 已在保留下界的同时把最新全局上界收紧为 `845,052.030831 MWh/a`。**

## 1. 为什么 D27 之后还要多启动

D27 从 D19 选择轨迹的符号向量出发，固定方向支持问题在首轮达到符号固定点，得到 `36,382.462799 MWh/a` 可行 L1。但一个符号固定点只代表一个正交域的自洽，不排除其他初始符号收敛到更大的可行 L1。

D28 不修改 D27 已锁定的源码或规范证书，而是用独立模块对差异化符号种子做有界筛查。

## 2. 预注册种子与预算

基准符号 $s^0_t$ 来自 D19 条件面轨迹。两个 336 h 种子为：

1. `negated`：$s_t=-s^0_t$；
2. `alternating`：$s_t=+1,-1,+1,-1,\ldots$。

每个种子只运行 1 轮固定支持方向 MILP，单任务时限 1800 s、HiGHS 线程数 28，两任务并行。本轮是“种子筛查”，不承诺在一轮内达到符号固定点。

## 3. 变换种子的负 support 证人

对任意种子 $s$，已知条件面轨迹在该方向上的目标为

\[
J_s=\frac12\sum_t w_t\Delta t\,s_t
\left(P_t^{TES}-P_t^{NS}\right).
\]

当种子与轨迹符号相反时，这个已知 support 证人可以为负。负值不表示 L1 为负：求解后仍按返回轨迹独立重算

\[
J_{L1}=\frac12\sum_t w_t\Delta t
\left|P_t^{TES}-P_t^{NS}\right|\ge J_s.
\]

因此验收必须分开 support primal/dual 与轨迹 L1。

## 4. 验收与科学边界

每个种子必须同时满足：

- 最大正归一化残差不高于 `1e-9`；
- support primal 不低于该方向的已知种子证人；
- 轨迹重算 L1 不低于 support primal；
- 最佳可行 L1 取 D27 条件面证人与本种子返回轨迹的较大者；
- `support_dual_is_global_l1_upper_bound=false`；
- `global_l1_bound_generated=false`。

任何种子的 support dual 都只界定该固定方向。即使返回更大可行 L1，也只能收紧全局最大值的下界，不能收紧或替代 D27 的全局上界。

## 5. 336 h 结果

| 种子 | 初始 support 证人 / MWh/a | support primal / dual / MWh/a | 返回轨迹 L1 / MWh/a | 符号变化 | 固定点 | 终止 |
|---|---:|---:|---:|---:|---|---|
| `negated` | -36,382.462799 | -36,382.462799 / 29,357.698910 | 36,382.462799 | 248 | 否 | `maxtimelimit` |
| `alternating` | -2,801.416745 | -2,801.416745 / 38,535.924321 | 36,382.462799 | 125 | 否 | `maxtimelimit` |

两条轨迹的最大正归一化残差均为 `2.0145e-12`，通过 `1e-9` 严格可行性门；二者的轨迹 L1 都没有超过 D27 条件面证人，故 `improvement_over_selected_face_mwh=0`。support primal 为负只说明相应固定方向与返回差值符号不一致，不影响独立重算的非负 L1。

因此 D28 不改变首选 336 h 最大严格区间：

\[
J_{\max}^{336h}\in
[36{,}382.462799,\ 1{,}081{,}649.139331]
\ \mathrm{MWh/a}.
\]

这是一项有界的负筛查结果：它说明两个明显不同的单步种子在各自 1800 s 预算内没有轻易抬高全局可行下界，但不能证明其他正交域不存在更强证人，也不能证明 D27 符号固定点是全局最优。若继续数值收紧，应预注册 D27 稳定符号周围的有限 Hamming 邻域或更长全局预算；任何邻域 dual 仍只能解释为局部界。

## 6. 实现与复现

- 多启动入口：`src/tes_bess_boundary/d28_multistart_direction.py`；
- 确定性汇总：`src/tes_bess_boundary/d28_multistart_bundle.py`；
- 回归：`tests/test_d28_multistart_direction.py`、`tests/test_d28_multistart_bundle.py`；
- OpenBayes 运行目录：`/root/e0-b-20260711-019f4f64/e0d28_multistart_direction/`；
- 规范产物：`数据采集/e0d28_multistart_direction/`；
- 求解器：HiGHS 1.15.1，不使用 Gurobi。
