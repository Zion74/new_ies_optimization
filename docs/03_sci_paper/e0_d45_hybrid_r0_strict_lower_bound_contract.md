# E0-D-45 Hybrid R0 原生双快照—fork 并行严格下界合同

状态：**第 1–11 节结果前合同保持冻结；Gate A 已通过，唯一正式 D45 已结束，终态 `no_strict_certificate`，不得重跑**

适用范围：D44 已从冻结 IPX dual 恢复 TES R0/R1 严格下界之后，为 Hybrid 架构恢复最弱但完整合法的全年严格下界

日期：2026-07-15

## 1. 本关只回答什么

D45 只回答：在不改变 D40–D44 的真实 2024 年 8784 h 输入、Hybrid 物理模型、服务目标、容量边界、公开成本敏感性口径和严格证书公式的前提下，能否为 **Hybrid R0 全连续松弛**形成至少一个有限、方向正确、可复核的全年严格下界。

D45 不求 Hybrid R1 两个拓扑分支，不生成原 MILP 可行解、容量、项目 TAC、gap 或技术排序。Hybrid R0 已把全部原始二元连续化，原 MILP、R1 及其 0/1 拓扑分支的可行域都是 R0 可行域的子集；因此任何合法 R0 下界都同时是这些更强问题的合法下界。R1 只能在后续独立增强合同中提高下界，不能成为本关成功的必要条件。

## 2. 不可覆盖的既有结果

- D41/D42 的 BESS 严格下界为 `1,144,950,604.8368804 CNY`；
- D44 的 TES R0/R1 严格下界为 `254,860,566.61931588889075258309724606578637338890918249419801438224278086471875331 CNY`；
- 两个数值都属于受控公开成本敏感性下界，不是原 MILP 可行上界、容量方案或项目 TAC，不能据其大小形成技术排序；
- D38/R1/D39、D40–D43 的历史失败终态保持不变，D42/D43/D44 均不得重跑；
- D44 正式总 manifest SHA-256 为 `d6fe2f34a354e5986ad4775034135f090df2e74492e0c7abc8f95861cb89739f`，状态 `tes_lower_bound_recovered`；
- 当前没有 Hybrid 合法下界，也没有三架构可比的可行上界、容量、gap 或赢家。

D45 若成功，只新增 Hybrid R0 严格下界，并允许另立全年可行上界/修复合同；不修改任何历史终态。

## 3. 锁定输入与身份链

| 输入/源码 | SHA-256 / 锁定值 |
|---|---|
| D42 structure manifest | `2d049208e8d8bafffce6a69878555d4d478bb305f8e5c2de42743c69cc9831d1` |
| D42 `structure_hybrid_r0.json` | `0923ae65d123e29691ff794828dfa9f2228ea81fbc93608bde0ccd914c23315b` |
| D44 formal manifest | `d6fe2f34a354e5986ad4775034135f090df2e74492e0c7abc8f95861cb89739f` |
| D44 formal execution | `673f4442d1f53d714f5eabd0c450c33373457cbd214a5ce0a85956d60f89946e` |
| `planning_model.py` | `fd894fbba0c5aba6cd50f9afb85088b6a9ffb3bad8efb66f1261d620e8bc90e2` |
| D42 formal driver | `a2ba832e51a227b3ad9e3c3484ffe958ca1df39442555dfd397a4330666ca53e` |
| D42 archive executor | `c46f7fac9013c8101699d04ee7a6d449e89ff7cd665fd0edceb6a80655c3ff51` |
| D42 certificate kernel | `3806db0ab7f878b4aea115f0b8f263a114b9eff3f3c90d7896390cd8cfdbb298` |
| D44 fork certificate kernel | `16786dd98757851dc2829b335d12ddb8dfeab38fd9bc03fcf3ac840e9df41c4c` |

D42 structure manifest 继续锁定 D40/D41 Gate A、正式热量、风光、服务与价格目录树哈希。D45 不接收替换输入、更新成本、不同服务、不同域变换或不同模型源码。

正式 prepare 必须独立重建并验证：

- 架构 `hybrid`，放松模式 `r0_all_continuous`；
- 原始二元 `96,625` 个，R0 后剩余非连续列 `0`；
- 原始 LP：`667,662 × 685,194`，`2,688,087` 个非零元，指纹 `3534a0c91e1f47bbd32b7125216c70bdfc06df91984b15136b5d8b5cd68e35c8`；
- presolved LP：`495,630 × 539,546`，`1,985,956` 个非零元，指纹 `756014eca3a93581a09f0abf99b42fd52e73a94694d532798d60290d7ddf740a`；
- Pyomo 6.10.1、highspy 1.15.1、Python 3.10.18、线性模型和最小化方向。

任一身份不一致即停止，不允许以新指纹继续。

## 4. 冻结数值路线

D45 把“求解器生成 row dual”与“严格证书复算”彻底分离：

1. prepare 子进程只构建一次 Hybrid R0，翻译并显式 presolve，核验第 3 节全部身份，写出确定性压缩 LP 归档；
2. IPX 与 simplex_1 phase parent 分别从同一只读 LP 归档加载独立 native HiGHS 实例，二者并行运行；
3. IPX 固定 12 线程、`900 s` callback 软中断和 `1020 s` phase parent 硬墙钟；simplex_1 固定 12 线程、`600 s` callback 软中断和 `720 s` phase parent 硬墙钟；
4. 两 phase 保持 D42 的全部 `1e-7` 容差、无 presolve 重跑、无 crossover/basis 跨指纹注入；soft interrupt 不是最优性声明；
5. native `run()` 返回后立即把完整 solution 归档并绑定 LP 指纹、`value_valid`、`dual_valid`、数组长度、finite row dual、执行 sidecar 与 SHA-256；此阶段不做 Decimal 证书；
6. 两个 solver phase 都必须尝试。某 phase 没有完整合法 row dual 时只使该快照不具备证书资格，不撤销另一快照；
7. 对每个合格快照调用**未修改的 D44 证书核**：行投影与行界项保持串行，`539,546` 列固定按 `floor(k*n/24):floor((k+1)*n/24)` 切为 24 块，Linux fork 24 worker，以 `Decimal.from_float()`、80 位精度、`ROUND_FLOOR/ROUND_CEILING` 计算；
8. 任一块缺失、重复、重叠、越界、非零元数不符、内容哈希不符、worker 异常或出现所需无穷列端点时，该快照不合格；不允许汇总部分块；
9. 至少一个快照合格时，按 Decimal lower 取较大者；完全相等时固定选择 IPX。两者都不合格时状态 `no_strict_certificate`。

不得根据正式结果增加 simplex 段、改变线程/块数、延长墙钟、修 dual、缩放 LP 或换证书公式。

## 5. Gate A：正式 Hybrid 之前必须证明什么

D45 新源码与测试必须在任何正式 Hybrid prepare/solve 前独立提交，并与 OpenBayes 逐字节同哈希。Gate A 只使用人工小 LP、合成 row dual 和既有只读结构 manifest，不运行正式 Hybrid：

- D42 native IPX/simplex 软中断后 solution 归档与执行 sidecar 能在证书前完整落盘，且不把中断 objective 当作严格下界；
- LP 归档往返、solution 数组、`dual_valid`、finite row dual、phase/LP 哈希链和篡改拒绝均通过；
- D44 fork 核在 Hybrid 尺寸无关的合成 LP 上继续包含 Fraction 精确值，`1/2/3/24` 块资格一致；
- IPX/simplex 双 phase 选择、相等时 IPX、单快照失败、双快照失败、缺块/失败 worker 均按冻结规则处理；
- prepare 身份门拒绝错误架构、非 R0、残留二元、错误规模、错误原始/presolve 指纹和源码漂移；
- Linux 确认 `fork`、4-worker 集成、solver/worker 进程树终止、输出不存在门、心跳/进度与哈希链；
- 本地/OpenBayes D40–D45 定向和全包回归通过，Ruff 与 py_compile 通过；
- Gate A manifest 绑定完整 Git commit、D45 source/test SHA-256、测试计数、零失败/零跳过和 Linux fork 证据。

Gate A 通过不代表 Hybrid 有限、可行或经济占优。

## 6. 正式资源合同

正式环境固定为 OpenBayes Linux、60 CPU、约 97 GiB、Python 3.10.18、Pyomo 6.10.1、highspy 1.15.1；不增加数值库或求解器依赖。

- prepare：单 child，硬墙钟 `420 s`，进程树 RSS `12 GiB`，父子聚合 RSS `15 GiB`；
- solver stage：IPX 与 simplex_1 两个 phase parent 并行，各 12 个 HiGHS 线程；总 stage 硬墙钟 `1080 s`，每 phase 进程树 RSS `20 GiB`，父子聚合 RSS `45 GiB`；
- certificate stage：每个合格快照 24 个 fork worker，最多 48 worker；每 phase 硬墙钟 `900 s`，总 stage 硬墙钟 `1080 s`，每 phase RSS `20 GiB`，父子聚合 RSS `45 GiB`；
- D45 总父进程硬墙钟 `2700 s`，主机可用内存始终不得低于 `30 GiB`；
- `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`；HiGHS 自身线程数只由 phase 的 12-thread 设置控制；
- 每 `5 s` 写心跳；资源或墙钟停止时终止完整进程组，等待 `30 s` 后强杀；任何残留子进程使执行失败。

D45 只允许一次正式执行，不因结果调整资源合同。

## 7. 输出与确定性

正式输出固定写入：

`/root/e0-b-20260711-019f4f64/results/e0d45_hybrid_r0_strict_lower_bound/`

输出目录事前必须不存在。规范证据至少包括：prepare manifest/execution 与 LP 归档；两个 solver phase 的 solution/result/execution/log/heartbeat/progress；合格快照的 certificate/chunks；总 manifest/execution/README。运行时间、PID、RSS 与完成时序只进入 execution sidecar，不进入规范 certificate。

总 manifest 必须登记 D42/D44 输入、D45 Gate A、全部依赖源码、LP/solution/certificate/result/execution 哈希、双快照选择、R0 包含关系、BESS/TES 既有下界引用和声明权限。所有下载件逐文件与远端 SHA-256 核对。

## 8. 成功、失败与后续权限

- 至少一个快照形成 24/24 块、有限 lower/upper、非负区间宽度且非法端点为 0：`hybrid_r0_lower_bound_recovered`；
- 两个快照都没有完整合法证书：`no_strict_certificate`；
- prepare 身份不一致、资源停止或执行器失败只说明 D45 路线未闭合，不证明 Hybrid 不可行；
- 成功下界按 R0→R1→原 MILP 的可行域包含关系覆盖 Hybrid 全架构，但不声称 R1 分支强化值；
- D45 成功后，BESS/TES/Hybrid 三架构才都具有至少一个合法全年下界，可另立 D46 全年可行上界/修复合同；
- D45 失败后不得重跑。任何后续必须另立缩放、对偶修复、R1 分支或严格分解合同。

## 9. 主张边界

无论成败，D45 都不得生成或支持：原 MILP 可行容量、项目 TAC、相对 gap、Hybrid 协同价值、三架构赢家、TES/Hybrid 可行或不可行结论、E2–E4 批量边界图。

成功时允许的最强表述是：某个冻结 Hybrid R0 row dual 在同一 hash-locked presolved LP 上，通过 24 块、80 位向外舍入拉格朗日审计形成有限合法下界；由 R0 松弛包含关系，该下界也覆盖 Hybrid R1 和原 MILP。

BESS、TES、Hybrid 下界大小不能代替上界或最优目标进行技术排序。

## 10. Agentic 角色

Agentic 仅负责：哈希准入、阶段依赖、资源监控、完整块资格、证书选择、停止规则、声明权限和证据下载核对。它不修改模型、不生成 dual、不替代 HiGHS、不判断技术赢家，也不是 SCI 的独立算法贡献。

## 11. 禁止事项与停止规则

D45 禁止：重跑 D42/D43/D44；修改正式输入/模型/成本/服务；读取 solver objective 代替证书；降低精度；只算部分列；忽略失败 worker；事后增加 simplex 段或 R1 分支；用 TES 下界替代 Hybrid 下界；启动可行上界、容量恢复、E2–E4 扫描或技术排序。

只有 Gate A 已提交且 OpenBayes 同哈希、零跳过通过后，才允许唯一一次正式 D45。D45 输出下载、逐文件哈希核对、三层文档同步和本地提交前，不进入 D46。

## 12. 实现后、正式运行前记录

2026-07-15 已新增：

- `src/tes_bess_boundary/e0d45_hybrid_r0_strict_lower_bound.py`，SHA-256 `cf977561f6471fd99fb9c4d3eed4dc04b65277f7b8a10f3013d10bd5e4a0866d`；
- `tests/test_e0d45_hybrid_r0_strict_lower_bound.py`，SHA-256 `8e6b598530a886073188cc60f3ecd6b4c8cbd2c9ffcd0e75c0b4b3595219fe33`。

实现保持第 1–11 节不变：D42 prepare 只重建 Hybrid R0；IPX/simplex_1 由两个独立进程组并行生成 solution snapshot，solver child 不调用 Decimal 证书；证书 child 不调用 HiGHS `run()`，只复用 D43 快照门和 D44 24 块核。父进程强制阶段/总墙钟、RSS、主机内存、完整 artifact hash map、LP 指纹和残留进程组清理。

Windows 候选检查为 D45 `25 passed + 2 Linux-only skipped`、D40–D45 `128 passed + 3 Linux-only skipped`、全包 `582 passed + 3 Linux-only skipped`；Ruff 与 py_compile 通过。

## 13. Gate A 结果与正式运行权限

D45 源码与测试已由提交 `270b04d6c8e65bd67a3953db722a0c082e058fc5` 固定，SHA-256 分别为 `cf977561f6471fd99fb9c4d3eed4dc04b65277f7b8a10f3013d10bd5e4a0866d` 与 `8e6b598530a886073188cc60f3ecd6b4c8cbd2c9ffcd0e75c0b4b3595219fe33`。OpenBayes Linux 逐字节同哈希，D45、D40–D45 定向和全包回归分别为 `27/131/585 passed`，全部零失败、零跳过；Ruff 与 py_compile 通过。Linux fork、4-worker smoke、双快照归档、篡改拒绝、分块等价、Decimal 选择、身份门和进程树清理均已实际执行。

Gate A manifest SHA-256 为 `570b801c4ea46a9b74668c4782f178261e8d49f235720b761b50e272996cc529`；远端与 `数据采集/e0d45_gate_a/` 本地副本的 9 个受清单约束文件逐文件同哈希。Gate A 明确记录 `optimization_invoked=false`、`native_solver_invoked=false` 和 `technical_ranking_permitted=false`。

Gate A 当时据此开放唯一一次正式 D45 Hybrid R0 权限；本节只记录运行前状态，后续唯一正式终态见第 14 节。

## 14. 唯一正式运行结果与终态

2026-07-15 在 OpenBayes 固定目录执行唯一一次正式 D45。prepare 的 16 项身份检查全部通过，原始/presolved 规模和指纹逐项复现；presolved LP 归档 SHA-256 为 `e84eb73544153e0fa1381d753ae154404eed82a661a8397719a0973b0dd43b12`。prepare 未调用优化器，随后两个 12-thread HiGHS phase 按冻结软墙钟并行运行并分别落盘完整 row-dual solution snapshot：

- IPX solution SHA-256：`eed2b064d13f31f6718dd7292374f545607709445705bdb9f54210c5688d4a80`；
- simplex_1 solution SHA-256：`6f4d0276ae62a58ee8053f0be60373068c883782b113c15455fdf2ade3a5c25c`。

两个合格快照随后各启用 24 个 Linux fork worker，并行执行未修改 D44 证书核。冻结 `900 s` phase 硬墙钟触发前，IPX 完成 `20/24` 块，simplex_1 完成 `16/24` 块；两 phase 均没有完整 chunks、certificate 或 result，分别以 `phase_hard_wall_reached:ipx`、`phase_hard_wall_reached:simplex_1` 和 `SIGTERM` 收口。对应 certificate execution SHA-256 为 `c85de258ea1374555d1e1c92fb731a0499761843897436785845ea2236531977` 与 `9ae2b24bab8164ab1954a8e41c23abeb8c283d7ce0758e23615cb1096ce82694`。

资源审计表明：certificate stage 峰值聚合 RSS `16.827327728271484 GiB`，两个 phase 峰值进程树 RSS 分别为 `8.429241180419922/8.414146423339844 GiB`，最低主机可用内存 `87.73542022705078 GiB`；因此失败原因为证书墙钟耗尽，不是 CPU/RAM 配额耗尽。IPX execution 在终止瞬间记录过待清理进程组，父编排器随后完成整组终止；运行结束后的独立审计为 D45 残留进程 `0`。

总运行时间 `1969.9582074005157 s`。总 manifest/execution SHA-256 分别为 `668fb0ea4c9293f789781298ca54f56da2bdcb55a3a7806d5bf8171d6e24cc55` / `60af4ee5b16f9aed6ec1a048b87cd57cbaf58b9b90141001ad667bdc71dcbca0`，终态字段为：

- `status=no_strict_certificate`；
- `formal_lower_bound_eligible=false`、`formal_lower_bound_decimal=null`、`selected_phase=null`；
- `hybrid_r0_certificate_covers_r1_and_original_milp=false`；
- `d46_feasible_upper_bound_contract_permitted=false`；
- `technical_ranking_permitted=false`。

远端 29 个正式文件已由 `artifact_sha256.txt` 逐文件校验，清单自身 SHA-256 为 `ef53178bcfdab3cad719d94994c41f8e35906b1593ee95e55e679182303058e9`；本地副本连同清单和 launcher 共 31 个文件，全部复核通过。`README.md` 中“Strict lower bound: None”与 manifest 一致；其后通用成功说明句不构成数值证书，不能覆盖 manifest 的 `null/false` 字段。

据第 8、9、11 节，D45 不得重跑，也不开放 D46 可行上界/修复、容量恢复、TAC、gap、E2–E4 或技术排序。任何继续计算必须先另立并在结果前冻结缩放、对偶修复、R1 分支或严格分解型 Hybrid 下界恢复合同；D45 已完成的部分块不得被拼接成下界。
