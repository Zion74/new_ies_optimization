# E0-D-30 物理可达域与年度服务联合紧化合同

更新时间：2026-07-14

状态：**24 h 等价性门已通过；336 h 的 1800 s HiGHS 全局探针将 D29 严格上界从 `845,052.030831` 进一步收紧到 `777,141.368858 MWh/a`，改善 `8.0363%`。D30 不改变 D19 可接受调度集，全部主整数与符号二元仍开放；336 h 仍未闭合。**

## 1. 问题与决策

D29 已用逐时外送/余量与年化正负质量守恒将 336 h global dual 降至 `845,052.030831 MWh/a`，但严格上下界仍宽。通用 FBBT 在比较架构和 TES 候选架构上都保留了逐时 `[0,700] MW` PCC 界，没有任何紧化，因此不再延续通用传播路线。

D30 改为构造一个逐时可分离的物理外松弛，求每个架构的 PCC 可达区间，再用共同年度 PCC 外送等式做区间传播。只有 bounds-only 筛查显示符号宽度有实质压缩后，才允许启动长时全局探针。

## 2. 逐时物理外松弛

对每个时段保留：

- 两台 CHP 的原始台账凸包和在线/离线选择；
- 供热平衡、风光可用上界和 PCC 功率平衡；
- TES 五端口容量；
- 由罐容、温度、环境温度、损失补偿与五路径流量上界解析得到的 TES 辅机功率上界。

主动省略 CHP 启停时序、爬坡、燃料分段、TES 库存跨时段状态、年度成本和弃电帽。这些删除只会扩大可行域，因此外松弛所得的下界不高于真实逐时最小值，上界不低于真实逐时最大值。每个数值界外扩 `1e-4 MW` 作为预注册求解容差。

## 3. 年度服务传播

对区间 $L_t\le x_t\le U_t$ 和年度服务

\[
\Delta t\sum_t w_tx_t=E,
\]

逐时传播

\[
L_t\leftarrow\max\left(L_t,
\frac{E-\Delta t\sum_{s\ne t}w_sU_s}{\Delta t w_t}\right),
\qquad
U_t\leftarrow\min\left(U_t,
\frac{E-\Delta t\sum_{s\ne t}w_sL_s}{\Delta t w_t}\right).
\]

传播只使用 D19 已有的精确同 PCC 年度服务，不引入价格。数值保护不得把服务传播后的区间扩大到原始静态外包络之外。

## 4. 区间感知符号不等式

记比较架构为 $x_t\in[L_t^x,U_t^x]$，TES 候选架构为 $y_t\in[L_t^y,U_t^y]$，D27 正负分解为 $y_t-x_t=p_t-n_t$，符号二元为 $z_t$。D30 定义

\[
M_t^+=\max(0,U_t^y-L_t^x),
\qquad
M_t^-=\max(0,U_t^x-L_t^y),
\]

并增加

\[
p_t\le M_t^+z_t,
\qquad
n_t\le M_t^-(1-z_t),
\]

以及四条带符号释放项的条件外送包络。它们在 $z_t=1/0$ 的对应整数面分别退化为 $p_t=y_t-x_t$ 或 $n_t=x_t-y_t$ 的可达区间界，在另一符号面由有限释放项保持冗余。每时段共增加 6 条 D30 不等式，不固定任何二元变量。

## 5. bounds-only 筛查

| 窗口 | 平均正向宽度 / MW | 正向压缩 | 平均反向宽度 / MW | 反向压缩 |
|---|---:|---:|---:|---:|
| 24 h | `460.687180` | `34.1875%` | `689.302779` | `1.5282%` |
| 336 h | `466.825419` | `33.3107%` | `686.938862` | `1.8659%` |

336 h 正向 big-M 平均下降 `233.174581 MW`。因两架构年度外送相同，年化正负差值质量相等，单侧显著紧化仍能约束整个 L1 包络，因此筛查通过。四个静态 HiGHS 子问题在 336 h 合计求解时间不到 2 s。

## 6. 全局结果

| 窗口 | D29 严格区间 / MWh/a | D30 primal / 轨迹重算 / dual / MWh/a | D30 首选严格区间 / MWh/a | 上界改善 |
|---|---:|---:|---:|---:|
| 24 h | `[26,010.174929,26,010.174929]` | `26,010.174918 / 26,010.174918 / 26,010.174918` | `[26,010.174929,26,010.174929]` | 0，保留 D29 精确点 |
| 336 h | `[36,382.462799,845,052.030831]` | `36,382.462799 / 36,382.462799 / 777,141.368858` | `[36,382.462799,777,141.368858]` | `67,910.661973 MWh/a`（`8.0363%`） |

24 h 返回 `optimal`，原始 dual 比已有精确可行点低 `1.1365e-5 MWh/a`，在预注册 `1e-4 MWh/a` L1 数值容差内，因此透明记录 `dual_clamped_to_reference_lower=true` 并保守沿用 D29 精确点。336 h 运行 `1804.576 s`，返回 `maxtimelimit`、finite global dual 和完整上界证书；求解器目标与轨迹 L1 重算差为 0，最大正归一化残差为 `4.24e-13`，没有发生 witness/dual 数值钳制。

相对 D26 原始上界 `1,362,149.106858 MWh/a`，D27+D29+D30 累计收紧 `585,007.738000 MWh/a`（`42.9474%`）。但 D30 的 336 h 上界仍是下界的约 `21.36` 倍，相对 gap `20.36033`，不能写成全局最优、实际结算暴露、正式 TAC 或技术赢家。

## 7. 验收与实现

- 已知 D19 选择调度必须逐时落入 D30 区间；
- 24 h 合并 D29 后必须保留精确点；
- 336 h 严格下界不得低于 D29，上界不得高于 D29；
- 最大正归一化残差不高于 `1e-9`，L1 重算误差不高于 `1e-4 MWh/a`；
- `feasible_set_changed_for_integer_solutions=false`、`primary_integer_patterns_reopened=true`、`sign_binaries_reopened=true`；
- 只有 finite global dual 可作为全局 L1 上界；
- `actual_price_path_assigned=false`、`formal_tac=false`、`e1_ready=false`。

实现与复现入口：

- `src/tes_bess_boundary/d30_physics_service_bound_tightening.py`；
- `src/tes_bess_boundary/d30_certification_bundle.py`；
- `tests/test_d30_physics_service_bound_tightening.py`；
- `tests/test_d30_certification_bundle.py`；
- `风光火+熔盐储热/数据采集/e0d30_physics_service_bound_tightening/`；
- OpenBayes：`/root/e0-b-20260711-019f4f64/数据采集/e0d30_physics_service_bound_tightening/`；
- 求解器：HiGHS 1.15.1，不使用 Gurobi。
