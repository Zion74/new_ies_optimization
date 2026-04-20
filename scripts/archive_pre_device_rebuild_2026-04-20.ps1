<#
.SYNOPSIS
  2026-04-20 松山湖数据 + 设备参数重建前，作废已有实验的归档脚本。

.DESCRIPTION
  commit b682cfc（2026-04-20）同时变更：
    1. 松山湖负荷数据（ele_load 从 166.64 → 69.59 万 kWh/a，冷电比 1.75 → 4.18）
    2. 松山湖设备效率（gt_eta_e 0.35→0.423，gt_eta_h 0.45→0.42，ec_cop 3.5→5.5）
    3. 用户额外提示："德国的卡诺电池好像之前改过，没事重新做吧"（即 DE_carnot 也存疑）

  因此两批 20260417 实验里的以下实验作废：
    - exp2a  (DE_base subset: std + euclidean)   ← 保守归档（和 exp1 重叠但样本量新批会补）
    - exp2b  (DE_carnot)                          ← 用户不确定是否已用新 Carnot 参数
    - exp3   (SL_base)                            ← 松山湖全变
    - exp4   (SL_carnot)                          ← 松山湖全变

  保留：
    - exp1   (DE_base, 5 方法)                    ← 德国基线，数据 + 参数均未变

  归档目标：Results\服务器结果\_pre_device_rebuild_2026-04-20\
  归档目录名 = 原相对路径展平（\ → __），避免重名。

.PARAMETER DryRun
  只打印要移动哪些目录，不实际执行。

.EXAMPLE
  # 试跑
  pwsh -NoProfile -File scripts\archive_pre_device_rebuild_2026-04-20.ps1 -DryRun

  # 真跑
  pwsh -NoProfile -File scripts\archive_pre_device_rebuild_2026-04-20.ps1
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ArchiveRoot = Join-Path $RepoRoot 'Results\服务器结果\_pre_device_rebuild_2026-04-20'

# 两批 20260417 里的 exp2a/exp2b/exp3/exp4 作废，exp1 保留
$Batches = @(
    'paper-batch__exp-all__full__n80__g150__w28__20260417_105519',
    'paper-batch__exp-all__full__n80__g150__w28__20260417_170546'
)

$ExpPatterns = @(
    'exp2a__*',
    'exp2b__*',
    'exp3__*',
    'exp4__*'
)

Write-Host '================================================================'
Write-Host '  设备参数 + 松山湖数据重建前实验归档（2026-04-20）'
Write-Host "  归档目标：$ArchiveRoot"
if ($DryRun) { Write-Host '  模式：DRYRUN（只打印不实际移动）' }
Write-Host '================================================================'

if (-not (Test-Path $ArchiveRoot)) {
    if ($DryRun) {
        Write-Host "[DRY] mkdir $ArchiveRoot"
    } else {
        New-Item -ItemType Directory -Path $ArchiveRoot -Force | Out-Null
    }
}

$moved = 0
$missing = 0

foreach ($batch in $Batches) {
    $batchDir = Join-Path $RepoRoot "Results\服务器结果\$batch"
    if (-not (Test-Path $batchDir)) {
        Write-Host ''
        Write-Host "[$batch] 不存在，跳过整批"
        $missing++
        continue
    }
    foreach ($pat in $ExpPatterns) {
        $matches = Get-ChildItem -Path $batchDir -Directory -Filter $pat -ErrorAction SilentlyContinue
        foreach ($m in $matches) {
            $rel = "Results\服务器结果\$batch\$($m.Name)"
            $flat = "${batch}__$($m.Name)"
            $dst = Join-Path $ArchiveRoot $flat

            Write-Host ''
            Write-Host "[$rel]"
            Write-Host "  -> $dst"

            if ($DryRun) {
                Write-Host '  [DRY] move'
            } else {
                try {
                    Move-Item -Path $m.FullName -Destination $dst -Force
                    Write-Host '  [OK] 已归档'
                    $moved++
                } catch {
                    Write-Host "  [ERROR] $_"
                }
            }
        }
    }
}

Write-Host ''
Write-Host '================================================================'
Write-Host "  归档汇总：成功 $moved 项，跳过批次 $missing 批"
Write-Host '================================================================'

if (-not $DryRun -and $moved -gt 0) {
    $readme = Join-Path $ArchiveRoot 'README.md'
    $content = @'
# 设备参数 + 松山湖数据重建前实验归档

**归档时间**：2026-04-20

**对应代码 commit**：`b682cfc feat(songshan): rebuild data from XLS source + correct device params`

**归档原因**：

本次 commit 同时变更了两类可能影响实验结果的要素：

1. **松山湖负荷数据重建**（从 XLS 源数据）
   - `ele_load`: 166.64 → 69.59 万 kWh/a（仅公用电，不含空调电）
   - 冷电比: 1.75 → 4.18（PDF 精确对齐）
   - 冷负荷峰值: 5797 → 3460 kW
   - 冷负荷形状: 12 月×24h 典型日（XLS Sheet 3 源数据）
   - 电负荷形状: 12 月×24h 典型日（XLS Sheet 4 源数据）

2. **松山湖设备效率修正**（基于官方手册 + 行业经验）
   - `gt_eta_e`: 0.35 → 0.423（CAT G3512E 官方最大发电效率 42.3%）
   - `gt_eta_h`: 0.45 → 0.42（综合效率≥80% 反算）
   - `ec_cop`: 3.5 → 5.5（1500kW 级水冷离心/螺杆机组行业值）

3. **德国 Carnot 参数**（用户提示存疑）
   - 用户：「德国的卡诺电池好像之前改过，忘记有没有做过实验了」
   - 保守起见一并归档 `exp2b`（DE_carnot），新批次统一用修正后配置重跑

**归档内容**（两批 20260417 实验）：

- `exp2a__german__base__std+euclidean__*` (DE_base subset)
- `exp2b__german__carnot__std+euclidean__*` (DE_carnot)
- `exp3__songshan_lake__base__std+euclidean__*` (SL_base)
- `exp4__songshan_lake__carnot__std+euclidean__*` (SL_carnot)

**保留不归档**：

- `exp1__german__base__m5__*`（DE_base, 5 方法）
  - 德国数据 `data/mergedData.csv` 和 `GERMAN_CASE` 所有参数均未改动，exp1 结果仍有效

**保留用途**：

- 仅用于论文写作时对比修正前后的差异（如需）
- 不再作为图表 / 数据的主引用
- `method_scenario_matrix.py` / `pareto_hypervolume.py` / `pareto_overlay.py` 等后处理脚本扫描 `paper-batch__*` 时会自动跳过已归档目录

**下一步**：

- 服务器重跑 `exp2` (DE_carnot) + `exp3` (SL_base) + `exp4` (SL_carnot)，两批 n80×g150
- 新批次回来后，`method_scenario_matrix` / `pareto_hypervolume` / `pareto_overlay` 会自动合并：旧 exp1 + 新 exp2/3/4
- 三大发现里德国部分仍有效（F1/F2/F3 的 DE_base 部分），SL 部分重评，DE_carnot 部分（F3 ΔHV）重评

**历史背景**：

参见 `docs/辩论确认/2026-04-18_德国松山湖三大发现诊断报告.md`
'@
    Set-Content -Path $readme -Value $content -Encoding UTF8
    Write-Host "归档说明已写入：$readme"
}
