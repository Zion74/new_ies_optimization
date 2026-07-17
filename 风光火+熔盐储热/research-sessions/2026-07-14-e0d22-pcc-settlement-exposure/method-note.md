# 方法备忘录

## 轨迹与单位

每个时段导出比较架构和 TES 候选的 PCC 功率，单位 MW。以代表窗口年度权重 `w_t` 和 1 h 步长换算：

```text
delta_E_t = w_t * (P_TES_t - P_NS_t)  # MWh/a
```

同年度服务要求 `sum(delta_E_t)=0`。

## 价格跨度包络

```text
redistributed_MWh = 0.5 * sum(abs(delta_E_t))
settlement_delta = sum(price_t * delta_E_t)
abs(settlement_delta) <= (price_max-price_min) * redistributed_MWh
```

该上界只对当前求解规则选定的轨迹成立。若每个时段价格可在上下界间独立取值，则包络可达；真实市场价格具有时序、节点和规则结构，不能据此宣称实际可达。

## 防误读规则

1. 平价抵消来自年度服务恒等式，不代表分时结算为零；
2. 不填入作者 TOU 或用户侧购电价；
3. D21 临界成本除以重新分配电量，只得到结算单账户的反事实临界价差；
4. 未证明连续调度唯一时，不把所选轨迹包络写成全局包络；
5. 24 h/336 h 均是年化筛查窗口，不是全年顺序运行。
