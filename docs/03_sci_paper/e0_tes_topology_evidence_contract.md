# E0-D-6 三温双服务熔盐 TES 拓扑证据合同

更新时间：2026-07-12
状态：**五条模型路径的证据等级和创新边界已锁定；E0-D-7 已建立 MT→LT 端点夹点与可交付热量合同，但杨凌现场供回水温度/抽汽温压、MT 设计候选、正式成本与完整工程参数仍未锁定。**

## 1. 本阶段解决的问题

当前 TES 模型把电加热、抽汽充热、发电放热和供热放热组合为一个 HT/MT/LT 三状态超结构。该超结构可以计算，不代表已有一篇论文完整验证过它。E0-D-6 将每条启用路径区分为：

- `core_direct`：Energy 同等级或更高论文直接支持该物理路径；
- `core_reduced_order`：高等级论文支持详细过程，MILP 以守恒等价的聚合路径表示；
- `core_modular_synthesis`：组成模块分别有高等级证据，但完整耦合是本文的模块化合成；
- `proposed_extension`：本文提出的拓扑扩展，必须明确披露并另做工程可行性验证；
- `blocked`：证据仍不足，不能进入正式算例。

代码合同位于：

- `风光火+熔盐储热/tes_bess_boundary/src/tes_bess_boundary/tes_topology_evidence.py`
- `风光火+熔盐储热/tes_bess_boundary/tests/test_tes_topology_evidence.py`

## 2. Energy+ 拓扑证据

### 2.1 三罐两阶段充热

Lv, Lu and Wei, *Energy* 322 (2025) 135580，DOI `10.1016/j.energy.2025.135580`，明确提出同一熔盐在冷罐、温罐和热罐之间的两阶段充热：第一阶段冷罐到温罐，利用蒸汽潜热和显热；第二阶段温罐到热罐，继续利用显热。

因此：

- `steam_lt_to_mt` 为 `core_direct`；
- 当前 `steam_lt_to_ht` 把 `LT→MT→HT` 在一个调度步长内聚合为净库存转移，属于 `core_reduced_order`，不得描述为论文原图中的单级直连换热器。

### 2.2 同一熔盐子系统的电/热双服务出口

Zhu et al., *Energy* 313 (2024) 133755，DOI `10.1016/j.energy.2024.133755`，设计了熔盐放热子回路：被熔盐加热的蒸汽可进入低压缸做功，也可进入供热网络补偿热需求。350 MW CHP 算例报告最大调峰范围提高 13.9%，最大供热能力提高 65.4%。

这直接证明“双服务熔盐 TES”不是概念拼接，也不需要退化为“熔盐罐 + 独立热水罐”。但该论文并未在公开可核验内容中证明供热必然使用本模型的 `MT→LT` 余热段。

因此：

- 熔盐—蒸汽—既有汽轮机发电出口与三状态库存的结合为 `core_modular_synthesis`；
- 双服务热出口有 Energy 级直接依据；
- 将供热专门分配给 `MT→LT` 低品位显热段是本文的 `proposed_extension`，必须通过供回水温度、最小端差、盐侧出口温度和换热器容量验证。

### 2.3 电加热入口

Trevisan et al., *Energy Conversion and Management* (2022)，DOI `10.1016/j.enconman.2022.116362`，以及 Klasing et al., *Applied Energy* (2025)，DOI `10.1016/j.apenergy.2024.124524`，均直接支持电加热—熔盐储热路径。因此 `electric_lt_to_ht` 为 `core_direct`。这些论文不证明完整三温双服务超结构。

## 3. 当前五路径证据地图

| 模型路径 | 证据等级 | 当前结论 |
|---|---|---|
| `electric_lt_to_ht` | `core_direct` | 电加热熔盐可用；完整系统仍是模块化合成 |
| `steam_lt_to_ht` | `core_reduced_order` | 表示文献中的 `LT→MT→HT` 两阶段净转移，不宣称单级设备 |
| `steam_lt_to_mt` | `core_direct` | Energy 三罐研究直接支持第一阶段 |
| `power_ht_to_mt` | `core_modular_synthesis` | 发电出口与三状态库存分别有依据，耦合需本模型验证 |
| `heat_mt_to_lt` | `proposed_extension` | 双服务热出口有依据；MT→LT 品位分配是本文扩展，E0-D-7 已建立夹点审计，E0-D-8 已注册三点作者敏感性；现场温压仍待闭合 |

正式用例若启用 `proposed_extension`，必须把它作为创新假设显式传给 `certify_formal_use()`；存在任何 `blocked` 活跃路径时，合同拒绝认证。

## 4. 盐配方与温度分层

### 4.1 物理候选基线，尚非正式参数基线

Wang et al., *Applied Energy* (2025)，DOI `10.1016/j.apenergy.2025.126876`，在煤电熔盐 TES 中采用 HITEC：53 wt% KNO3、40 wt% NaNO2、7 wt% NaNO3，热/冷罐温度为 390/180 °C。该组合与煤电中低温热源、低冷端温度和本项目三状态研究最接近，故暂定为后续工程验证的**首选物理候选**：

- 盐：HITEC 53/40/7；
- `LT = 180 °C`；
- `HT = 390 °C`；
- `MT`：**不填默认值**。E0-D-7 已证明夹点只给出下界而不能唯一识别 MT；在杨凌现场温压缺失时，MT 应作为显式离散设计/敏感性参数。

该候选不等于正式参数集。MT 未闭合前，不允许用 280 °C、300 °C 等方便数替代，也不允许把测试中的示例温度写入论文。

### 4.2 备选与敏感性

- McTigue et al., *Energy Conversion and Management* (2022)，DOI `10.1016/j.enconman.2021.115016`，给出硝酸盐 `0.5–1.3 USD_2020/kg`、230–565 °C；由于其 PTES 拓扑及盐类别不等同于 HITEC，该范围只进入盐价敏感性，不决定 HITEC 基线。
- Wang et al. 报告 HITEC 约 `0.9 USD/kg`，但未明确价格年，因此只能作为数量级交叉检查。
- Solar salt 冷端熔点约 240 °C，与 `LT=180 °C` 不兼容，不能与 HITEC 物性和价格混搭；它只能作为完整重定义温区的独立架构敏感性。

## 5. 检索与访问审计

本轮先调用 InstSci。Semantic Scholar 路由被限流，不能把“无返回”解释为“无论文”。随后通过出版社原始页面确认两篇 Energy 论文的 DOI、摘要、亮点和拓扑描述。

对 `10.1016/j.energy.2025.135580` 的可见 InstSci/CloakBrowser 复核在 2026-07-12 15:22:35 UTC 返回 Elsevier `CPE00001`，参考号 `a1a10b461cb0f90c`，出口 IP `103.227.167.102`。该结果只表示当前出口 IP 被 ScienceDirect 拦截，不表示论文不存在、学校无订阅或 DOI 失效；同一路由不再盲目重试。精确 MT、罐温和设备表保持 `blocked_pending_full_table`。

## 6. E0-D-6 后仍未通过的门槛

1. 获取 Energy 2025 三罐原文参数表，并向数据方索取杨凌一次网供回水温度、抽汽温压和换热器端差；
2. E0-D-7 已验证 Energy 2026 的 `120/70 °C` 核心参考情景在显式端差下可行，但该情景不是杨凌事实，也不能唯一确定 MT；正式算例需注册 MT 候选集；
3. 将 HITEC 的温变比热、密度、黏度、结晶裕度、分解与腐蚀边界锁定为同一配方数据集；
4. 为 HITEC 盐、三罐、泵、两级充热换热器、蒸汽发生/回送和供热换热器找到明确价格年的合格成本源；
5. 建立泵功、散热损失、伴热和换热面积缩放；
6. 完成 bottom-up ledger 与独立聚合工程锚点校准。

因此，E0-D-6 通过的是“拓扑证据披露合同”；E0-D-7 通过的是“夹点与可交付热量审计合同”，二者都不是正式杨凌工程参数或 TAC。E1–E6 仍不得启动。详细接口见 `e0_tes_heat_delivery_pinch_contract.md`。
