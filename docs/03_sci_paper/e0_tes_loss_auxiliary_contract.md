# E0-D-9 TES 静置损失、伴热与泵辅机合同

更新时间：2026-07-13

状态：**E0-D-9A 线性结构合同、E0-D-9B-1 三 MT 损失作者校准及 E0-D-9B-2 底层液压泵耗/统一运行审计均已通过。** 当前代码可审计五路径吞吐量、原始/补偿/净热损失以及泵耗和伴热如何进入 PCC，并已注册可复现的低/基准/高损失与 40/50/200 kPa 泵耗筛选集；这些数值仍是跨项目证据支持的 `AUTHOR_SENSITIVITY`，不是杨凌现场参数，因此不得形成正式损失价值、TAC 或技术赢家结论。

## 1. 证据边界

- Trevisan et al., *Energy Conversion and Management* (2022), DOI `10.1016/j.enconman.2022.116362`：罐损失取决于液位、湿/干表面积、保温热阻和环境温度；其 45 MWhth 案例中总损失、内置电加热补偿、净损失和泵耗是系统级聚合结果。
- Klasing et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2024.124524`：满充、每日一循环条件下约 99% 的储热效率只能作为聚合锚点。
- Wang et al., *Applied Energy* (2025), DOI `10.1016/j.apenergy.2025.126876`：动态模型忽略罐体/换热器热损，但支持“盐流量越高，泵功越大、RTE 越低”的方向性检查。

因此，`0.797 GWhth`、`73.4%`、约 `99%` 或动态 RTE 都不能直接转换成杨凌三罐的固定逐时自放电率。InstSci 本轮检索受 Semantic Scholar 限流且未返回新条目；这不构成“无相关论文”的证据。

## 2. 库存—环境温差损失

对状态罐 (i\in\{HT,MT\})，用户显式给出参考环境温度 (T_{a,ref}) 下的每小时损失分数 (r_{i,ref})。每期温差比例为

\[
s_{i,t}=\frac{\max(0,T_i-T_{a,t})}{T_i-T_{a,ref}}.
\]

为使任意步长保持复合留存率，期内等效损失流量系数为

\[
k_{i,t}=\frac{1-(1-r_{i,ref})^{s_{i,t}\Delta t}}{\Delta t},
\qquad
\dot m^{raw}_{i,t}=k_{i,t}M_{i,t}.
\]

环境温度是已知时间序列，因此该式对库存变量仍为线性。未提供环境温度序列时，模型明确使用 (T_{a,ref})，而不是声称采用杨凌实测环境温度。

## 3. 补偿伴热与未补偿损失

对每条损失弧设置固定、预注册补偿比例 (c_i\in[0,1])：

\[
\dot m^{comp}_{i,t}=c_i\dot m^{raw}_{i,t},\qquad
\dot m^{net}_{i,t}=(1-c_i)\dot m^{raw}_{i,t}.
\]

只有净损失进入 `HT→MT` 和 `MT→LT` 库存降级；补偿部分保持原状态并产生伴热电功率：

\[
P^{trace}_t=\frac{c_p}{\eta_{trace}}
\left[(T_{HT}-T_{MT})\dot m^{comp}_{HT,t}
+(T_{MT}-T_{LT})\dot m^{comp}_{MT,t}\right].
\]

`UNCOMPENSATED` 模式强制两个补偿比例均为零；`FIXED_FRACTION` 模式不允许优化器按电价自行开关伴热，避免引入未定义控制策略。

## 4. 流量相关泵辅机与 PCC

五条盐路径分别登记比泵耗 (e_j\,[\mathrm{kWh_e/t}])：

\[
P^{pump}_t=10^{-3}\sum_j e_j\dot m_{j,t}.
\]

TES 总辅助电功率为

\[
P^{aux,TES}_t=P^{trace}_t+P^{pump}_t.
\]

统一模型只在 PCC 平衡左侧扣除一次 `tes_auxiliary_total`。伴热不再重复写入电加热充电端口，泵耗也不嵌入发电或换热效率。

## 5. 参数身份与禁止事项

每个损失/辅机参数集必须登记：

- `SITE_PRIMARY`、`CORE_PAPER_DIRECT` 或 `AUTHOR_SENSITIVITY`；
- 数值来源 ID；作者敏感性必须使用 `author:` 前缀；
- 支撑结构和校准范围的高等级证据 DOI；
- 参考环境温度。

当前没有注册杨凌正式损失率、伴热比例或五路径正式比泵耗。E0-D-9B-1 的低/基准/高损失参数和 E0-D-9B-2 的三档压降均标为作者校准敏感性；Trevisan 的聚合泵耗只检查量级，Wang 的 HITEC 关联式只提供物性与单调方向。除非获得对应设备或现场一次资料，不得升级为 `SITE_PRIMARY`。

## 6. 代码、测试与跨平台复现

- `src/tes_bess_boundary/tes_loss_auxiliary.py`：参数身份、时间步复合、环境温差缩放、伴热模式、五路径比泵耗与累计吨位；
- `src/tes_bess_boundary/tes_loss_calibration.py`：Trevisan/Klasing 聚合锚点、低/基准/高作者情景、三 MT 损失反标定和聚合反推泵耗审计量；
- `src/tes_bess_boundary/tes_pump_calibration.py`：Trevisan 液压锚点、Wang HITEC 物性、三档五路径底层泵耗、标准循环与确定性 CSV/manifest；
- `src/tes_bess_boundary/components/molten_salt.py`：原始损失、补偿损失、净库存降级、伴热和泵功线性表达；
- `src/tes_bess_boundary/model.py`：环境温度序列、TES 辅机 PCC 单次计入，以及调度时域/年度权重下的五路径吨位、损失和辅机公开审计；
- `tests/test_tes_loss_auxiliary.py`、`test_tes_loss_calibration.py`、`test_tes_pump_calibration.py`、`test_pyomo_components.py`、`test_unified_model.py`：数值金标准、三 MT 的 24 h HiGHS 交叉验证、物性/液压/单调性/确定性产物、legacy 零损失、年度权重和 PCC 防双计。

本地 Python 3.11：`249 passed in 29.29s`；OpenBayes Python 3.10.18、`Pyomo 6.10.1 + highspy 1.15.1`：`249 passed in 21.17s`。E0-D-9B-2 当前相关文件 SHA-256 跨平台一致：

- `tes_loss_auxiliary.py`：`98a49b310340f4b834dd9fead63984731a3e40f657fba035f2072deff6e082e7`；
- `components/molten_salt.py`：`13fc524ba32ff2314f9a70b8b429b8759e89731c01e6711e8f2fcb7011009802`；
- `model.py`：`db443ea0860c61770d4ae34c0e8fb40d2f19e0c68912d135dfbea29dfad8e10b`；
- `test_tes_loss_auxiliary.py`：`7b90f473e85154f61c96601f3909e3f288adc483b8c6891a593af61838b4e84d`；
- `test_pyomo_components.py`：`de7f81ae49a39986cbf04d09dd34cb94eb46679d5b7cd4a4599e1fcb7e7752a5`；
- `test_unified_model.py`：`ce1ecebcf804fe271f058ba4bc5a203b3adc7ee6ad76c8d9fb5577542cf9f33c`；
- `tes_loss_calibration.py`：`c5f4fa4e9e1f530dd895d9b1cb4ae100028aaed2e136f47d0faf3a275c994bb0`；
- `test_tes_loss_calibration.py`：`f37770aca1a1a935e1477b94142b7f17bc4dc113cdf2dcdea14ee0353d477b90`；
- `tes_pump_calibration.py`：`cb9a069e138b830a36b54586f9acb5870b7e9f34990f8c3044218368c32e5a61`；
- `test_tes_pump_calibration.py`：`1d63bc056eadbd3e136211b901c951e9ae485ddd01fdf3796e80fdeba11da180`。

## 7. E0-D-9B-1 三 MT 聚合损失校准结果

Trevisan 基准案例公开量经统一单位换算后为：容量 `45 MWhth`、年度总热损 `797 MWhth`、固定补偿比例 `73.4%`、净热损 `212.002 MWhth`、年度总用电 `21110 MWhe`、泵辅机占比约 `0.5%`，对应泵耗聚合锚点 `105.55 MWhe/a`。Klasing 的满充日留存锚点为 `99%/24 h`。这些量只用于作者归一化，不作为杨凌直接输入。

令 MT 以下显热占比为

\[
f=\frac{T_{MT}-T_{LT}}{T_{HT}-T_{LT}},
\]

满充时全部盐在 HT；若每小时 HT→MT 与 MT→LT 使用相同净降级分数 (q)，离散保持 (n=24) 小时后的总储能留存率为

\[
R(q,f)=(1-q)^n+f\,nq(1-q)^{n-1}.
\]

对每个 MT 点分别反求满足同一目标 (R) 的 (q)，再按固定补偿比例 (c) 换回模型原始损失分数 (r=q/(1-c))。这避免把三温层的焓分割差异误当成保温差异。三档均为作者情景：低档采用 Klasing `R=0.99` 与 Trevisan `c=0.734`；基准档采用 Trevisan 净损失的容量—年度归一化 `R=0.987092724505`、`c=0.734`；高档是 Trevisan 总损失归一化且伴热失效的压力情景 `R=0.951476407915`、`c=0`。

| 档位 | MT (°C) | 24 h 目标留存率 | 补偿比例 | 原始小时分数 (r) | 净小时分数 (q) |
|---|---:|---:|---:|---:|---:|
| 低 | 232.5 | 0.990000000000 | 0.734 | 0.002097508498 | 0.000557937260 |
| 低 | 285.0 | 0.990000000000 | 0.734 | 0.003133013988 | 0.000833381721 |
| 低 | 337.5 | 0.990000000000 | 0.734 | 0.006048364264 | 0.001608864894 |
| 基准 | 232.5 | 0.987092724505 | 0.734 | 0.002710700308 | 0.000721046282 |
| 基准 | 285.0 | 0.987092724505 | 0.734 | 0.004044022887 | 0.001075710088 |
| 基准 | 337.5 | 0.987092724505 | 0.734 | 0.007734812306 | 0.002057460073 |
| 高 | 232.5 | 0.951476407915 | 0.000 | 0.002753286308 | 0.002753286308 |
| 高 | 285.0 | 0.951476407915 | 0.000 | 0.004048998476 | 0.004048998476 |
| 高 | 337.5 | 0.951476407915 | 0.000 | 0.007076402989 | 0.007076402989 |

三个 MT 的基准档均已通过独立 Pyomo 库存模型和 HiGHS 24 h 求解交叉验证，最终留存率与目标的绝对误差不超过 `1e-10`。

Trevisan 聚合值只允许在总盐吞吐量 (M_{throughput}) 已知后计算“聚合反推统一系数”：

\[
e^{pump}=\frac{105.55\times 1000}{M_{throughput}}\;\mathrm{kWh_e/t}.
\]

该系数不是路径物理标定，不再分配给正式五路径。E0-D-9B-2 使用独立底层液压式计算路径系数，从而避免“用优化吞吐量反推系数、系数又改变该吞吐量”的循环标定。

## 8. E0-D-9B-2 底层泵耗与统一运行审计结果

采用

\[
e_j=\frac{\Delta p_j}{\rho(T_j)\eta_p\,3600}\;\mathrm{kWh_e/t},
\]

其中 Wang HITEC 物性为 `rho=2288-0.748T` kg/m³、`cp=1507-0.1T` J/(kg·K)。Trevisan 给出工作压力 200 kPa、回路压损 20%、单个主动部件压损 5% 和泵效率 90%；据此预注册低/基准/高 `Δp=40/50/200 kPa`，均为作者敏感性。LT→HT 三条充热路径按 LT=180 °C，HT→MT 发电路径按 HT=390 °C，MT→LT 供热路径按所选 MT 计算密度。

标准循环固定为 45 MWhth、HITEC 180→390 °C、365 次/年；精确积分比热后盐量为 `521.764336 t`，每年电充、发电降级、供热降级各流过一次总盐量，总五路径吞吐量为 `571331.948403 t/a`。三档年泵耗结果为：

| 压降档 | MT=232.5 °C | MT=285 °C | MT=337.5 °C | 占 Trevisan 105.55 MWhe/a |
|---|---:|---:|---:|---:|
| 40 kPa | 3.3818 | 3.4028 | 3.4247 | 3.20%–3.24% |
| 50 kPa | 4.2272 | 4.2535 | 4.2808 | 4.00%–4.06% |
| 200 kPa | 16.9088 | 17.0141 | 17.1234 | 16.02%–16.22% |

Trevisan 聚合量在该标准吞吐量下反推 `0.184743738 kWh_e/t`，约为基准路径系数的 24.8 倍。该差异不是拟合失败，而是说明跨项目聚合量可能包含持续循环、更多管段或其他辅机；它只保留为非约束包络，绝不与底层泵耗相加。

统一 `model.py` 现按 `dispatch_horizon` 或 `annual_period_weighted` 两种明确口径输出五路径吨位、原始/补偿/净热损失、泵耗、伴热和总辅机，并验证泵耗随盐流量与压降单调增加。确定性产物位于 `风光火+熔盐储热/数据采集/e0d9b2_tes_pump_calibration/`：CSV 9 行，SHA-256 `0ae6bfe10853c6f654a515fd3213673d9f998479f265bfbce1b330463bf269e8`；manifest SHA-256 `6acd37583923d79b58455a97cff0e05814093ab8f7da66a982c835db8dc08806`。OpenBayes 上传件与独立再生成件逐字节一致。

## 9. E0 剩余验收门槛

1. 继续争取杨凌泵曲线、管路/换热器压降、实际循环时长和损失运行记录；没有现场证据时保留三档作者敏感性，不设置伪正式基线；
2. 在后续正式容量/运行算例中继续输出总损失、补偿率、净损失、五路径吞吐量及泵耗占比；
3. 聚合锚点只做量级包络，不与分项损失、底层泵耗或成本重复相加；
4. 具有明确价格年的成本参数、正式 TAC 与内生容量闭合前，不进入 E1 或 699 次批量边界扫描。
