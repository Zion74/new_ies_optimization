# E0-D-16 TES 价格无关价值与盈亏平衡合同

更新时间：2026-07-13

状态：**分析内核与确定性测试已实现；当前只允许形成探索性 TES 年化所有权成本上限，不构成正式 TES CAPEX、正式 TAC 或技术赢家。** E0-D-15 的 12 个 TES 正式成本账户仍全部阻断，系统 VOM、碳和电力结算范围也未闭合，因此 E1–E6 仍不得启动。

## 1. 目的

当 TES 部件价格缺少共同基年时，仍可回答一个不需要假造价格的问题：

> 在同一情景、同一供热安全和同一弃电服务目标下，TES 全系统每年最多允许承担多少所有权成本，才不会比无 TES 的比较架构更差？

该问题输出的是**全系统 TES 等效年成本上限**，不是某个罐、盐、电加热器或换热器的单价。

## 2. 数学定义

比较架构 $c\in\{\text{No storage},\text{BESS}\}$，候选架构 $t\in\{\text{TES},\text{Hybrid}\}$。候选结果必须移除全部 TES 初始投资、更换、残值、FOM 和 VOM，只保留双方同范围、已知且可比较的运行成本与非 TES 固定年成本：

\[
C_{TES,max}^{EAC}
=\left(C_{c}^{op}+C_{c}^{fixed,known}\right)
-\left(C_{t}^{op}+C_{t}^{fixed,known,nonTES}\right).
\]

- $C_{TES,max}^{EAC}>0$：TES 只有在完整年化所有权成本不超过该上限时，才可能不劣于比较架构；
- $C_{TES,max}^{EAC}=0$：只有零所有权成本时才打平；
- $C_{TES,max}^{EAC}<0$：即使 TES 免费，候选在当前已知成本范围内仍被比较架构支配。

代码同时分开报告：

\[
\Delta C^{op}=C_c^{op}-C_t^{op},\qquad
\Delta C^{fixed}=C_c^{fixed,known}-C_t^{fixed,known,nonTES},
\]

并核对 $C_{TES,max}^{EAC}=\Delta C^{op}+\Delta C^{fixed}$。人工弃电罚值不得进入 $C^{op}$，否则会凭空制造 TES 价值。

## 3. 价格无关物理价值

每次比较必须同时输出：

- 燃煤节约：(F_c-F_t)，单位 tce/a；
- 弃电减少：(E_c^{cur}-E_t^{cur})，单位 MWh/a；
- PCC 外送变化：(E_t^{PCC}-E_c^{PCC})，单位 MWh/a；
- TES 泵与伴热辅助用电，单位 MWh\(_e\)/a。

这些量不依赖 TES 设备价格，可以用于判断 TES 的物理作用是否存在。它们仍依赖统一调度模型、场景和服务约束，不能从旧同规格算例直接继承。

## 4. 可比性门禁

`tes_break_even.py` 只接受满足以下条件的结果：

1. 双方均为 HiGHS 最优结果；
2. 同一 `scenario_id / service_id / horizon_id`；
3. 加权时域严格为 2024 年 8,784 h；
4. 可用新能源和弃电上限完全一致，实际弃电均不超过上限；
5. 缺热量为零；
6. 已知成本使用同一范围、2024 年不变价人民币，且不含人工罚值；
7. 候选已剔除全部 TES 所有权成本；
8. TES/HYBRID 候选绑定 `TESCapacityLedger`，具有正的完整显热库存和至少一个正放能端口；
9. 比较架构不得含 TES，候选架构必须含 TES。

任一条件不满足即拒绝计算，而不是输出带警告的数字。

## 5. 容量归一化边界

为便于跨规模展示，可把同一个全系统上限分别除以：

- 完整 LT→HT 显热库存，kWh\(_{th}\)；
- 电加热输入功率，kW\(_e\)；
- TES 电输出功率，kW\(_e\)；
- TES 有效热输出功率，kW\(_{th}\)。

\[
c_{sys,b}^{BE}=C_{TES,max}^{EAC}/X_b.
\]

每个归一化值乘回自身容量都必须重构同一个 (C_{TES,max}^{EAC})。这些数值只能写作“全系统 EAC 上限的某容量基准视图”，不得解释为该部件的单位成本，也不得把不同基准下的数值相加。盐 kg、各罐 t 和 12 个成本账户不在该输出中做反向分摊。

## 6. 与正式成本门禁的关系

分析函数必须显式接收 `TESFormalCostReadinessAudit`：

- TES 正式 portfolio 未就绪，或非 TES 成本范围不完整：`exploratory_threshold_only`；
- 只有 TES 正式 portfolio 与同范围非 TES 成本同时闭合，才可升级为 `auditable_non_tes_cost_ceiling`。

当前严格路线下 12 个 TES 账户全部阻断，而且系统 VOM、碳和电力结算尚未闭合，所以代码虽可计算审计示例，杨凌数值仍只能作为探索性阈值，不能写入正式主结果表。

## 7. 当前允许与禁止用途

允许：

- 验证 TES 在零所有权成本下是否仍有运行价值；
- 报告燃煤、弃电、PCC 外送与 TES 辅机的物理差值；
- 在同一成本范围内给出全系统 TES 年化成本上限；
- 为后续厂商报价或正式部件 portfolio 提供“是否低于上限”的外部判据。

禁止：

- 将 EAC 上限改写成隔夜 CAPEX；
- 用 CRF 反推初始投资而忽略 FOM、更换、残值和退役；
- 把系统上限按 12 个账户任意分摊；
- 把 DLR/Klasing/Li 聚合锚点塞入部件账本；
- 在正式成本和系统结算范围未闭合时宣布 BESS/TES/Hybrid 赢家；
- 把 E0-D-16 当作 E1 已启动。

## 8. 代码与下一接口

- 分析内核：`src/tes_bess_boundary/tes_break_even.py`；
- 回归测试：`tests/test_tes_break_even.py`；
- TES 正式成本前置门：`e0_tes_formal_cost_readiness_contract.md`；
- 容量分母前置合同：`e0_tes_cost_capacity_mapping_contract.md`；
- E0-C 年度结果适配、24 h 产物和两周性能状态：`e0_tes_break_even_adapter_and_exploration_contract.md`。

E0-D-17 已完成无罚值服务审计、实际年度结果适配和 24 h 探索阈值；两周主 MILP 尚未闭合，非 TES 成本范围仍缺 VOM、碳和电力结算。下一接口不是填入一个“合理 TES 单价”，而是强化两周 formulation 并补齐同范围系统成本；正式 E1 仍等待 TES portfolio、系统级 TAC 与内生容量闭合。
