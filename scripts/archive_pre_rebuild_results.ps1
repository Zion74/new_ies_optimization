<#
.SYNOPSIS
  把松山湖数据重建之前的实验结果归档，避免与重建后实验混用。

.DESCRIPTION
  2026-04-17 松山湖负荷数据口径重建后，之前的 exp2/exp3a/exp3b/exp4 结果
  不再可比。本脚本只移动松山湖相关子目录，不碰德国 exp1（数据源 mergedData.csv 未变）。

  归档目标：Results\服务器结果\_pre_rebuild_2026-04-17\
  归档目录名 = 原相对路径展平（`\` → `__`），避免重名。

.PARAMETER DryRun
  只打印要移动哪些目录，不实际执行。

.EXAMPLE
  # 试跑
  pwsh -NoProfile -File scripts\archive_pre_rebuild_results.ps1 -DryRun

  # 真跑
  pwsh -NoProfile -File scripts\archive_pre_rebuild_results.ps1
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$ArchiveRoot = Join-Path $RepoRoot 'Results\服务器结果\_pre_rebuild_2026-04-17'

$Targets = @(
    'Results\服务器结果\full_all_50x100_20260413_134312\full_all_50x100_20260413_134312\exp2_songshan_lake_50x100_std+euclidean_20260413_153358',
    'Results\服务器结果\full_all_50x100_20260413_134312\full_all_50x100_20260413_134312\exp3a_songshan_lake_50x100_euclidean_20260413_161721',
    'Results\服务器结果\full_all_50x100_20260413_134312\full_all_50x100_20260413_134312\exp3b_songshan_lake_carnot_50x100_euclidean_20260413_163925',
    'Results\服务器结果\full_all_50x100_20260413_134312\full_all_50x100_20260413_134312\exp4_songshan_lake_carnot_50x100_std+euclidean_20260413_170421',
    'Results\服务器结果\第三次实验\第三次实验\exp4',
    'Results\服务器结果\第二次实验\paper-batch__exp-all__full__n50__g100__w28__20260414_062000\exp2__songshan_lake__base__std+euclidean__n50__g100__20260414_070312',
    'Results\服务器结果\第二次实验\paper-batch__exp-all__full__n50__g100__w28__20260414_062000\exp3a__songshan_lake__base__euclidean__n50__g100__20260414_072045',
    'Results\服务器结果\第二次实验\paper-batch__exp-all__full__n50__g100__w28__20260414_062000\exp3b__songshan_lake__carnot__euclidean__n50__g100__20260414_072933',
    'Results\服务器结果\第二次实验\paper-batch__exp-all__full__n50__g100__w28__20260414_062000\exp4__songshan_lake__carnot__std+euclidean__n50__g100__20260414_073933'
)

Write-Host '================================================================'
Write-Host '  松山湖重建前结果归档'
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

foreach ($rel in $Targets) {
    $src = Join-Path $RepoRoot $rel
    $flat = ($rel -replace '^Results\\服务器结果\\', '') -replace '\\', '__'
    $dst = Join-Path $ArchiveRoot $flat

    Write-Host ''
    Write-Host "[$rel]"
    Write-Host "  -> $dst"

    if (-not (Test-Path $src)) {
        Write-Host '  [SKIP] 不存在'
        $missing++
        continue
    }

    if ($DryRun) {
        Write-Host '  [DRY] move'
    } else {
        try {
            Move-Item -Path $src -Destination $dst -Force
            Write-Host '  [OK] 已归档'
            $moved++
        } catch {
            Write-Host "  [ERROR] $_"
        }
    }
}

Write-Host ''
Write-Host '================================================================'
Write-Host "  归档汇总：成功 $moved 项，跳过 $missing 项"
Write-Host '================================================================'

if (-not $DryRun -and $moved -gt 0) {
    $readme = Join-Path $ArchiveRoot 'README.md'
    $content = @'
# 松山湖重建前结果归档

**归档时间**：2026-04-17

**归档原因**：

本目录收纳 `scripts/generate_songshan_data.py` 重建之前产生的所有松山湖案例实验结果。
数据口径变更后（`ele_load` 从 166.64 → 69.59 万kWh/年、冷峰值 5797 → 3460 kW、
月度对齐表 2），这些结果已不与当前 `data/songshan_lake_data.csv` 可比，
不能与重建后实验混用。

**保留用途**：

- 仅用于论文写作时对比口径修正前后的差异
- 不再作为图表 / 数据的主引用

**未归档的是**：

- 德国案例 `exp1`（数据源 `data/mergedData.csv` 未变，仍可参考）

**新实验产出位置**：

新的正式实验放在 `Results/服务器结果/post_rebuild_*` 目录。
由 `scripts/openbayes_run_experiments.sh` 在服务器上产出。
'@
    Set-Content -Path $readme -Value $content -Encoding UTF8
    Write-Host "归档说明已写入：$readme"
}
