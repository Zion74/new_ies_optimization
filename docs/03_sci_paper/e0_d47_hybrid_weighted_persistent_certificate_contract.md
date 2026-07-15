# E0-D-47 Hybrid 加权持久化 fork 严格证书恢复合同

状态：**第 1–11 节结果前合同保持冻结；源码/测试、OpenBayes 同哈希 Gate A 与唯一正式 D47 均已完成；终态 `hybrid_r0_lower_bound_recovered`，不得重跑**

适用范围：D45 唯一正式 Hybrid R0 双快照—24 块证书以 `no_strict_certificate` 结束后，只读复用其冻结 LP 与 row dual，以新的严格分解合同恢复最弱合法 Hybrid 全年下界

日期：2026-07-15

## 1. 本关只回答什么

D47 只回答：在不重新构建 Hybrid 模型、不调用 HiGHS `run()`、不修改 D45 冻结 LP/dual、80 位定向舍入和拉格朗日证书含义的前提下，能否通过**确定性加权连续分块、单快照顺序准入和逐块原子持久化**，为 Hybrid R0 形成至少一个完整、有限、方向正确且可复核的严格下界。

D47 不修正或覆盖 D45。D45 的 `20/24` 与 `16/24` 只用于诊断长尾，不得作为 D47 已完成块、不得拼接、不得贡献任何数值下界。D47 必须从冻结 LP/solution 归档重新计算全部 56 块。

## 2. 不可覆盖的既有终态

- BESS 严格下界保持 `1,144,950,604.8368804 CNY`；
- TES R0/R1 严格下界保持 `254,860,566.61931588889075258309724606578637338890918249419801438224278086471875331 CNY`；
- D45 总状态保持 `no_strict_certificate`，`formal_lower_bound_decimal=null`、`selected_phase=null`、`d46_feasible_upper_bound_contract_permitted=false`；
- D42/D43/D44/D45 均不得重跑；
- 上述 BESS/TES 数值仍只是受控公开成本敏感性下界，不是容量、原 MILP 可行上界、项目 TAC、gap 或技术排序。

D47 若成功，只新增 Hybrid R0 严格下界。由既有可行域包含关系，该数值也是 Hybrid R1 与原 MILP 的合法下界；这不恢复 D45 的成功状态，也不自动开放可行上界、容量或批量扫描。

## 3. 为什么编号跳过 D46

D45 manifest 已明确写出 `d46_feasible_upper_bound_contract_permitted=false`。因此 D46 继续保留为“只有三架构下界闭合后才可能讨论的全年可行上界/修复关”，本轮不得借改名绕过。

D47 属于 D45 第 8 节允许的**新严格分解合同**：它不延长 D45 墙钟、不续跑 D45 输出目录，而是在新源码、新 Gate A、新输出目录和新单次正式机会下，只读复用冻结快照。

## 4. 锁定输入与身份链

| 输入 | SHA-256 / 锁定值 |
|---|---|
| D45 formal manifest | `668fb0ea4c9293f789781298ca54f56da2bdcb55a3a7806d5bf8171d6e24cc55` |
| D45 formal execution | `60af4ee5b16f9aed6ec1a048b87cd57cbaf58b9b90141001ad667bdc71dcbca0` |
| D45 artifact checksum list | `ef53178bcfdab3cad719d94994c41f8e35906b1593ee95e55e679182303058e9` |
| frozen presolved LP archive | `e84eb73544153e0fa1381d753ae154404eed82a661a8397719a0973b0dd43b12` |
| frozen presolved LP fingerprint | `756014eca3a93581a09f0abf99b42fd52e73a94694d532798d60290d7ddf740a` |
| IPX solution archive | `eed2b064d13f31f6718dd7292374f545607709445705bdb9f54210c5688d4a80` |
| IPX solver execution | `39b547a06bea1fdbd7924651e8e57b8be06322a2b6da7d205640fabfa2eed6f1` |
| simplex_1 solution archive | `6f4d0276ae62a58ee8053f0be60373068c883782b113c15455fdf2ade3a5c25c` |
| simplex_1 solver execution | `8bf887665d6271d27963e8d90aa53822cc90eb037d8c0b56ddc539feeb0f1167` |
| D44 certificate kernel | `16786dd98757851dc2829b335d12ddb8dfeab38fd9bc03fcf3ac840e9df41c4c` |
| D45 orchestrator | `cf977561f6471fd99fb9c4d3eed4dc04b65277f7b8a10f3013d10bd5e4a0866d` |

正式准入还必须复核：架构 `hybrid`、放松模式 `r0_all_continuous`、presolved LP `495,630 × 539,546`、`1,985,956` 个非零元、全部列连续、最小化方向、两个 solution 的 `dual_valid=true`、row dual 长度 `495,630` 且全部有限。任一身份不一致即停止。

## 5. 冻结的加权持久化证书算法

### 5.1 确定性 56 块分区

对 CSC 矩阵第 (j) 列定义整数工作权重

\[
w_j=1+\left(\mathrm{start}_{j+1}-\mathrm{start}_j\right),
\]

其中常数 1 代表每列固定的目标系数、上下界和残差端点处理，差分项代表该列非零元循环。令 (S_j=\sum_{t<j}w_t\)、(W=S_n\)、块数 (K=56\)。边界固定为 (b_0=0,b_K=n\)；对 (k=1,\ldots,K-1\)，先取满足

\[
S_j\ge \left\lceil\frac{kW}{K}\right\rceil
\]

的最小 (j)，再确定性夹到区间 ([b_{k-1}+1,\ n-(K-k)]\)。第 (k) 块覆盖半开区间 ([b_k,b_{k+1})\)。

分区只依赖冻结 CSC `start_`，必须输出 56 行 partition JSON，登记每块列范围、列数、非零元数、工作权重和内容 SHA-256。正式 LP 的结构诊断值固定为总工作权重 `2,525,502`；原 24 个等列块非零元最大/最小比 `2.7173835683`，56 个加权块工作权重最大/最小比约 `1.054`。Gate A 必须从同哈希 LP 独立复算这些值。

### 5.2 证书核与持久化

1. 行 dual 投影、行界项、`Decimal.from_float()`、80 位精度、`ROUND_FLOOR/ROUND_CEILING` 和每列拉格朗日残差端点逻辑继续复用未修改 D44 核；
2. 新模块只新增任意连续分区验证、56-worker Linux fork 编排、逐块原子 JSON 和新分区汇总；不得修改 D44 源文件；
3. 每个 worker 完成后，父进程立即写 `phase/chunks/chunk_000.json` 至 `chunk_055.json`，内容绑定 LP、solution、phase、partition、列范围、非零元数、lower/upper、非法端点数和 canonical content hash；
4. 汇总只接受 56 个唯一块，要求无缺失、重复、重叠、越界、哈希漂移和非零元数漂移；按 chunk id 顺序以定向舍入累加；
5. 任一部分块集合都没有下界资格。逐块持久化只用于失败定位和完整性审计，不开放人工续拼。

不同分块会改变有限精度加法分组，因此 D47 不要求与 D44 小数末位逐字相等；Gate A 必须用 Fraction 精确参考证明 D47 lower 不大于精确值、upper 不小于精确值、区间宽度非负，并证明 56 块与 1/2/3/24 块具有相同的端点合法性分类。

### 5.3 快照准入顺序

IPX 固定为第一且充分快照：

1. 先只运行 IPX 的 56 块；
2. IPX 形成完整、有限、非法端点为 0 的证书时立即成功，不运行 simplex_1；
3. IPX 缺块、执行失败、超时或因所需无穷端点不合格时，才运行 simplex_1 的全部 56 块；
4. simplex_1 合格则采用 simplex_1；两者都不合格则 `no_strict_certificate`。

该顺序只寻求至少一个合法下界，不声称选得最强 dual，也不以 solver objective 排序。

## 6. Gate A：正式运行前必须证明什么

D47 源码与测试必须在任何正式证书计算前独立提交，并与 OpenBayes 逐字节同哈希。Gate A 只使用人工小 LP、合成 dual、D44 已有 TES 证书只读副本和 D45 元数据，不对 Hybrid 正式 dual 执行证书：

- 加权边界公式在 `1/2/3/24/56` 块下确定、全覆盖、无空块、无重叠，拒绝错误 partition；
- Fraction 精确参考同时包含 D44 等列和 D47 加权结果，方向、端点资格与 Decimal 选择正确；
- 56 个 chunk JSON 原子写入，缺失、重复、篡改、错误 solution/LP/partition hash、错误非零元数全部拒绝；
- IPX 成功停止、IPX 失败后 simplex 回退、双失败、进程树终止和输出目录不存在门全部通过；
- Linux `fork` 与至少 4-worker 持久化集成实际执行，Windows 对 Linux-only 项显式 skipped；
- D45 manifest/execution/LP/solution/solver-execution 和 D44 kernel 哈希准入均通过；
- D47 定向、D40–D47 定向、全包回归、Ruff 与 py_compile 通过；OpenBayes 零失败、零跳过；
- Gate A manifest 绑定完整 Git commit、source/test SHA-256、测试计数、Linux fork 证据、分区统计和 `optimization_invoked=false`。

Gate A 通过不代表 Hybrid 已有下界、可行解或经济优势。

## 7. 正式资源合同

正式环境固定为 OpenBayes Linux、60 CPU、约 97 GiB、Python 3.10.18、Pyomo 6.10.1、highspy 1.15.1；正式执行不调用求解器。

- 每个 phase：1 个 phase parent + 56 个 fork worker，phase 硬墙钟 `1800 s`；
- IPX 与 simplex_1 严格顺序，不得并发；
- 每 phase 进程树 RSS 上限 `30 GiB`，父子聚合 RSS 上限 `40 GiB`，主机可用内存不得低于 `30 GiB`；
- 总父进程硬墙钟 `3900 s`，终止宽限 `30 s`；
- `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`；
- 每 `5 s` 写 heartbeat，每个块完成立即写 chunk JSON 与 progress；资源或墙钟停止时终止完整进程组，最终残留进程必须为 0。

D47 只允许一次正式执行，不因中间完成速度改变块数、worker 数、快照顺序或墙钟。

## 8. 输出与确定性

Gate A 输出固定为：

`/root/e0-b-20260711-019f4f64/results/e0d47_gate_a/`

正式输出固定为：

`/root/e0-b-20260711-019f4f64/results/e0d47_hybrid_weighted_persistent_certificate/`

两个目录事前都必须不存在。正式证据至少包括：input audit、partition JSON、逐 phase heartbeat/progress/log/execution、56 个逐块 JSON、合格 phase certificate/result、总 manifest/execution/README 与 artifact checksum。所有下载件逐文件和目录树 SHA-256 与远端核对。

运行时间、PID、RSS、完成顺序和 stop reason 只进入 execution sidecar；规范 certificate 只包含冻结身份、分区、定向舍入数值和完整性审计。

## 9. 成功、失败与后续权限

- IPX 或 fallback simplex_1 形成 56/56 完整块、有限 lower/upper、非负区间宽度且非法端点为 0：`hybrid_r0_lower_bound_recovered`；
- 两个快照都没有完整合法证书：`no_strict_certificate`；
- 执行失败或资源停止只说明 D47 路线未闭合，不证明 Hybrid 不可行；
- 只有成功并完成远端/本地证据提交后，BESS/TES/Hybrid 才都具有至少一个全年合法下界，才可另立 D46 全年可行上界/修复合同；
- D47 失败后不得重跑，后续只能另立对偶修复、R1 分支或更强严格分解合同。

## 10. 主张边界

D47 成功时允许的最强表述是：某个 D45 冻结 Hybrid R0 row dual 在同一 hash-locked presolved LP 上，通过 56 个确定性加权连续块、80 位向外舍入和完整块哈希审计，形成有限合法下界；由可行域包含关系，该数值也下界 Hybrid R1 与原 MILP。

D47 无论成败都不生成：可行容量、原 MILP 上界、项目 TAC、相对 gap、Hybrid 协同价值、三架构赢家、TES/Hybrid 可行或不可行结论、E2–E4 边界图。BESS/TES/Hybrid 下界大小不能替代上界或最优目标进行技术排序。

## 11. Agentic 角色、禁止事项与停止规则

Agentic 只负责哈希准入、分区确定性、完整块资格、资源监控、快照顺序、停止规则、主张权限和证据回传；不修改 LP/dual、不调用优化器、不判断技术赢家。该编排属于硕士论文可审计决策支持素材，不作为 SCI 的独立优化算法贡献。

D47 禁止：重跑 D42–D45；读取 D45 部分块作为结果；修改正式 LP/dual；降低精度；跳过缺块；事后改为等列分区、改块数/worker/墙钟；IPX 成功后继续 simplex 以挑更大值；读取 native objective 代替证书；启动可行上界、容量恢复、TAC、E2–E4 扫描或技术排序。

只有合同、源码/测试提交和 OpenBayes 同哈希 Gate A 全部完成后，才允许唯一正式 D47。正式证据下载、逐文件哈希核对、三层文档同步和本地提交前，不进入 D46。

## 12. 实现与 OpenBayes Gate A 记录

D47 生产模块与测试先后由提交 `6d584ee` 和进程组清理加固提交 `1515eca9cb24b0a3e073889b51480b8eefb0c413` 固定。最终源码与测试 SHA-256 分别为 `a503a8c0d1544e7c4c35c6ffc80d00d4b96324560accd6fb2f755963472a5fb5` 和 `9347f4e5ec4b9fe80864586c112aef8d31575bf44c28fa95af4ffa04049c9191`，OpenBayes 上传件逐字节同哈希。实现保持 D44 列证书核不变，新增确定性加权分区、56-worker Linux fork、逐块原子 JSON、完整集合汇总、IPX 优先回退、资源监控和主动进程组复核；证书路径未调用 HiGHS `run()`。

第一次 Linux Gate A 在进程组清理测试中得到 `36 passed + 1 failed`，因此没有开放正式运行；失败证据保留在远端 `e0d47_gate_a_failed_6d584ee/`。随后 D47 将 `/proc` 进程组成员按活动态与 zombie 态分开审计，确保活动残留为 0，并以新提交、新源码/测试哈希完整重跑 Gate A。

最终 OpenBayes Gate A 结果为 D47 `37 passed`、D40–D47 `168 passed`、全包 `622 passed`，全部零失败、零跳过；Ruff 0.15.10 与 py_compile 通过。对冻结正式 LP 的只读结构复核得到 `56` 块、总工作权重 `2,525,502`、块权重最小/最大 `43,901/46,293`、比值 `1.054486230381996`，partition content SHA-256 为 `6c8dd0cff80dabfdbe3cf3d629d5e3518f93c956cf56566942c4d11c1c02b677`。Gate A 未读取正式 dual 进行证书计算，`optimization_invoked=false`。

Gate A manifest SHA-256 为 `80591c66ef15a1d01c02513283eb86d5f5bca2edacdcf0041791c87e349cb22d`；本地证据共 23 个文件，checksum 清单覆盖其余 22 个文件并逐文件与远端一致，清单 SHA-256 为 `7de18630e2c46a514b3bb88433e7a96ece88b55b35d02997729a3f6a67c916eb`。本节只开放一次正式 D47 的执行资格，不代表 Hybrid 已有下界、可行容量、项目 TAC、gap、协同价值或技术排序。

## 13. 唯一正式运行终态

唯一正式 D47 已在 OpenBayes 的冻结 60 核环境完成。IPX phase 的 56/56 个确定性加权连续块全部合格，覆盖 `539,546` 列；没有缺块、重复块、内容哈希冲突或非法端点。按预注册的“IPX 成功即停止”规则，`simplex_1` 未启动。最终状态为 `hybrid_r0_lower_bound_recovered`，`formal_lower_bound_eligible=true`，且没有调用优化器或原生求解器：`optimization_invoked=false`、`native_solver_invoked=false`。

80 位向外舍入得到 Hybrid R0 严格下界：

`232011577.83593156905560264049764989154935073609620115224488377919660126326832988 CNY`

对应的严格包络上端点为：

`3391819174.0195139161100476321219415875005205920146107618296368626924607177507169 CNY`

区间宽度为 `3159807596.1835823470544449916242916959511698559184096095847530834958594544823871 CNY`。这里的“上端点”只是同一拉格朗日表达式的定向舍入包络端点，**不是**原 MILP 的可行上界、可行方案目标值或项目 TAC；不得用它计算优化 gap、容量方案或技术排序。由既有可行域包含关系，Hybrid R0 下界同时是 Hybrid R1 与原始 Hybrid MILP 的合法下界，但不证明任何 Hybrid 可行解存在。

正式 phase 在约 `532.387 s` 完成全部块计算，phase 运行 `539.041 s`，总运行 `539.050 s`。峰值 phase 进程树 RSS 为 `18.812 GiB`，峰值聚合 RSS 为 `18.838 GiB`，最低可用内存 `86.714 GiB`；资源门通过，非法端点为 0，结束后活动残留进程为 0。

正式总 manifest、execution、phase execution、result、certificate 与 artifact-list SHA-256 分别为：

- `8b74c4044854d18d5dffa6c2759bfe747455631e0347293d6a89c16d35276101`
- `ed978c3607f080456576e35dede75c57e017150514e24160462a62566bf9c330`
- `9020d15db2e869081364d5c45b2c5697a4e090f96c0c4ff510b57b29a7b724f5`
- `f8c33ca2fab2882e0a444b24351de45301592c18a147fc0b70b0ae17ad54b725`
- `1caa1b6bd051d682e3fb001e64c39c94fcf28f62cd95256634ff269da22b1c05`
- `9a766aab5c1e07ef94e7c76d164403c3fc9eab9a44437f5cdd4fc5f092b42c76`

正式 partition 文件 SHA-256 为 `840cd949626b44f4c891a96117b545aa0d681f4196cb26027a28334c4fc2ba23`，partition content SHA-256 与 Gate A 一致，仍为 `6c8dd0cff80dabfdbe3cf3d629d5e3518f93c956cf56566942c4d11c1c02b677`；56 个 chunk 的树哈希为 `999f3a6b62765f81524163e31fb2bc30e37184db92989998b9a39dc85122f664`。本地正式证据共 72 个文件，checksum 清单覆盖其余 71 个文件，全部与远端逐文件同哈希。

D47 成功后，BESS、TES、Hybrid 三种架构都已有至少一个严格全年下界，因此 manifest 中 `d46_feasible_upper_bound_contract_permitted=true`。这只允许另立并冻结 D46 可行上界/修复合同；它不授权立即求解 D46，更不开放容量恢复、TAC、相对 gap、E2–E4 批量扫描或技术排序。唯一正式 D47 已用尽，今后不得因上端点过宽或希望获得更大下界而重跑。
