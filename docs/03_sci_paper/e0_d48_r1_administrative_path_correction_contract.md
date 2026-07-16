# E0-D-48-R1 行政路径纠正与替代启动合同

## 1. 触发原因与无结果边界

E0-D-48 的结果前合同预注册正式远端目录为：

`/root/e0-b-20260711-019f4f64/results/e0d48_hamming_feasibility_primal_recovery/`

首次启动时，编排命令误用了：

`/root/e0-b-20260711-019f4f64/results/e0d48_full_year_hamming_primal_recovery/`

该偏差只涉及证据目录名称，不涉及模型、输入、seed、目标、HiGHS
选项或资源合同；但目录身份属于结果前预注册内容，因此该启动不得登记为
正式 D48。偏差在 BESS 候选阶段发现后立即终止。终止时：

- 父进程和候选子进程均已终止，活动残留进程为 0；
- 最后心跳约为启动后 `1186.384 s`；
- `bess_candidate.log` 为 0 字节；
- 不存在 candidate CSV、candidate result JSON、repair、架构 manifest 或总
  manifest；
- 不存在可用于上界、容量、Hamming 结果、infeasible 状态、gap 或技术排序
  的数值。

错误路径目录必须原样保留为行政失败证据，归档到：

`风光火+熔盐储热/数据采集/e0d48_invalid_wrong_output_path_launch/`

## 2. 已通过且继续有效的身份

以下身份在错误启动前已经冻结，且本补充合同不修改它们：

- 实现提交：`1090cd83b54aac8a99dce0041c1371b1e0b4320d`；
- OpenBayes Gate A manifest：
  `1d894652bfb91f9995f428c8f36fc7ad555675496e42c1dbec4c6673c14c8bfe`；
- Gate A 绑定的全部代码 SHA-256、15 项定向测试、659 项全包回归、三架构
  build-only 身份和 HiGHS 1.15.1 选项回读；
- D40/D41/D46、正式热负荷、VRE、价格树和三份 D46 guide 的全部锁定哈希。

Gate A 使用版本化归档目录 `e0d48_gate_a_1090cd8/` 与
`e0d48_gate_a_work_1090cd8/`。其证据身份由 manifest SHA-256 和逐文件哈希
决定；版本化目录名不改变 Gate A 内容，也未调用正式优化。

## 3. 唯一允许的纠正

本合同只允许一次替代启动，并强制使用原 D48 合同已经预注册的正式目录：

`/root/e0-b-20260711-019f4f64/results/e0d48_hamming_feasibility_primal_recovery/`

替代启动前该目录必须不存在。正式本地副本固定为：

`风光火+熔盐储热/数据采集/e0d48_hamming_feasibility_primal_recovery/`

替代启动必须继续由 `e0d48_monitored_executor.py formal-batch` 验证 Gate A
与全部输入哈希。除输出目录字符串外，命令参数必须与首次启动逐项相同。

## 4. 非协商不变项

不得修改：

- 原 MILP 约束、原容量边界、服务合同或成本目标；
- 三份 D46 guide、完整二元清单、等权 Hamming 目标或首 incumbent 停止规则；
- `threads=12`、`random_seed=0`、HiGHS 启发式/预处理选项和全部容差；
- `3600/3720/1500/5400/16200 s` 软硬时限；
- BESS→TES→Hybrid 顺序、每架构一次 candidate 和至多一次 repair；
- 进程树 RSS、聚合 RSS、主机内存保留、心跳和残留清理规则。

不得新增第二 seed、Repair B、fallback、IIS 修补、局部分支、目标加权、容量
锚点或事后调参。错误路径启动消耗的时间不得加入或扣减替代启动的冻结时限。

## 5. 权限与声明

本补充合同是在替代启动产生任何结果前提交的行政纠正，不是依据数值结果改变
算法。提交后仅开放一次上述正确路径的替代启动。替代批次结束后不得原样重跑；
任何算法、输入、选项或时限增强必须另立新的结果前合同。

错误启动和本补充合同均不产生正式上界、容量、不可行证明、项目 TAC、gap 或
技术排序；`formal_project_tac_ready=false`、
`technical_ranking_permitted=false` 保持不变。
