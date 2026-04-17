#!/usr/bin/env bash
# ============================================================
# openbayes_run_experiments.sh
# ------------------------------------------------------------
# 一键在 OpenBayes / 任意服务器上跑松山湖数据重建后的正式实验。
#
# 流程：
#   0) （可选）跑 openbayes_setup.sh 装依赖
#   1) 重新生成松山湖负荷数据（--source synthesis）
#   2) 独立口径校验（check_songshan_data.py）
#   3) 依次跑指定实验（默认 --exp all），每组实验跑完再做 Phase2
#   4) 所有 stdout/stderr 落盘到 logs/ 下的时间戳文件
#
# 环境变量（全部有合理默认值）：
#   IES_SKIP_SETUP       1=跳过 openbayes_setup.sh（默认 0）
#   IES_SKIP_DATA_REGEN  1=跳过数据重新生成（默认 0）
#   IES_SKIP_SANITY      1=跳过 sanity check（默认 0）
#   IES_EXP              要跑的实验："1 2 3 4" 或 "all"（默认 "all"）
#   IES_WORKERS          并行 worker 数（默认空=由 run.py 自动选 CPU 核数）
#   IES_POST_MODE        Phase2 后验模式：test/quick/medium/full（默认 medium）
#   IES_TEST_RUN         1=用 nind=10/maxgen=5 的 --test-run（默认 0）
#   IES_QUICK_RUN        1=用 nind=20/maxgen=20 的 --quick-run（默认 0）
#   IES_STRICT_SANITY    1=sanity WARN 即中止（默认 0，仅打印）
#   IES_RUN_TAG          结果根目录前缀标签（默认 post_rebuild）
#
# 用法示例：
#   # 服务器冷启动，按默认参数跑完全部实验
#   bash scripts/openbayes_run_experiments.sh
#
#   # 快速烟测（10 分钟级）
#   IES_TEST_RUN=1 bash scripts/openbayes_run_experiments.sh
#
#   # 只跑松山湖相关（exp 2 3 4）
#   IES_EXP="2 3 4" bash scripts/openbayes_run_experiments.sh
#
#   # 数据已生成过，直接跑实验
#   IES_SKIP_DATA_REGEN=1 bash scripts/openbayes_run_experiments.sh
# ============================================================

set -Eeuo pipefail

log()  { printf '\n[INFO %(%F %T)T] %s\n' -1 "$*"; }
warn() { printf '\n[WARN %(%F %T)T] %s\n' -1 "$*" >&2; }
die()  { printf '\n[ERROR %(%F %T)T] %s\n' -1 "$*" >&2; exit 1; }
hr()   { printf '%s\n' "================================================================"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

[[ -f "pyproject.toml" ]]             || die "pyproject.toml not found under ${REPO_ROOT}"
[[ -f "run.py" ]]                     || die "run.py not found under ${REPO_ROOT}"
[[ -f "scripts/generate_songshan_data.py" ]] || die "scripts/generate_songshan_data.py missing"
[[ -f "scripts/check_songshan_data.py" ]]    || die "scripts/check_songshan_data.py missing"

# ---- 环境变量解析 ----
IES_SKIP_SETUP="${IES_SKIP_SETUP:-0}"
IES_SKIP_DATA_REGEN="${IES_SKIP_DATA_REGEN:-0}"
IES_SKIP_SANITY="${IES_SKIP_SANITY:-0}"
IES_EXP="${IES_EXP:-all}"
IES_WORKERS="${IES_WORKERS:-}"
IES_POST_MODE="${IES_POST_MODE:-medium}"
IES_TEST_RUN="${IES_TEST_RUN:-0}"
IES_QUICK_RUN="${IES_QUICK_RUN:-0}"
IES_STRICT_SANITY="${IES_STRICT_SANITY:-0}"
IES_RUN_TAG="${IES_RUN_TAG:-post_rebuild}"

# ---- 运行参数归一化 ----
if [[ "${IES_TEST_RUN}" == "1" && "${IES_QUICK_RUN}" == "1" ]]; then
  die "IES_TEST_RUN 和 IES_QUICK_RUN 不能同时开启"
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${REPO_ROOT}/logs/${IES_RUN_TAG}_${TIMESTAMP}"
mkdir -p "${LOG_DIR}"

# ---- 0) 打印配置 ----
hr
log "一键实验：松山湖数据重建后正式实验"
cat <<EOF
  Repo root         : ${REPO_ROOT}
  Log directory     : ${LOG_DIR}
  Experiments       : ${IES_EXP}
  Workers           : ${IES_WORKERS:-auto}
  Post-analysis mode: ${IES_POST_MODE}
  Test-run mode     : ${IES_TEST_RUN}
  Quick-run mode    : ${IES_QUICK_RUN}
  Skip setup        : ${IES_SKIP_SETUP}
  Skip data regen   : ${IES_SKIP_DATA_REGEN}
  Skip sanity check : ${IES_SKIP_SANITY}
EOF
hr

# ---- 1) 环境准备 ----
if [[ "${IES_SKIP_SETUP}" != "1" ]]; then
  log "[1/5] 运行 openbayes_setup.sh"
  IES_SKIP_RUN_CHECK=1 bash "${SCRIPT_DIR}/openbayes_setup.sh" 2>&1 | tee "${LOG_DIR}/01_setup.log"
else
  warn "已跳过 openbayes_setup.sh（IES_SKIP_SETUP=1）"
fi

# ---- 2) 重新生成松山湖数据 ----
if [[ "${IES_SKIP_DATA_REGEN}" != "1" ]]; then
  log "[2/5] 重新生成松山湖负荷数据"
  uv run python scripts/generate_songshan_data.py 2>&1 | tee "${LOG_DIR}/02_generate.log"
else
  warn "已跳过数据重生（IES_SKIP_DATA_REGEN=1），沿用既有 data/songshan_lake_data.csv"
fi

# ---- 3) 独立 sanity check ----
if [[ "${IES_SKIP_SANITY}" != "1" ]]; then
  log "[3/5] 独立口径校验 check_songshan_data.py"
  SANITY_EXTRA=""
  if [[ "${IES_STRICT_SANITY}" == "1" ]]; then
    SANITY_EXTRA="--strict"
  fi
  set +e
  uv run python scripts/check_songshan_data.py ${SANITY_EXTRA} 2>&1 | tee "${LOG_DIR}/03_sanity.log"
  SANITY_RC=${PIPESTATUS[0]}
  set -e
  if [[ ${SANITY_RC} -ne 0 ]]; then
    if [[ "${IES_STRICT_SANITY}" == "1" ]]; then
      die "sanity check 未通过（IES_STRICT_SANITY=1）"
    else
      warn "sanity check 返回非 0，但 IES_STRICT_SANITY != 1，继续执行"
    fi
  fi
else
  warn "已跳过 sanity check（IES_SKIP_SANITY=1）"
fi

# ---- 4) 跑实验 ----
log "[4/5] 跑正式实验"

RUN_FLAGS=()
[[ -n "${IES_WORKERS}" ]]   && RUN_FLAGS+=(--workers "${IES_WORKERS}")
[[ "${IES_TEST_RUN}" == "1" ]]  && RUN_FLAGS+=(--test-run)
[[ "${IES_QUICK_RUN}" == "1" ]] && RUN_FLAGS+=(--quick-run)
[[ -n "${IES_POST_MODE}" ]] && RUN_FLAGS+=(--post-analysis-mode "${IES_POST_MODE}")

OVERALL_START=$SECONDS

if [[ "${IES_EXP}" == "all" ]]; then
  # IES_EXP=all：一次性调 run.py --exp all，让 run.py 自己生成
  # `Results/paper-batch__exp-all__...__<ts>/` 统一父目录，四组实验 + batch_timing_summary.md
  # 全部落在同一个子目录下，方便后续打包 / 归档 / 汇总回传。
  hr
  log "  >>> 开始批次：IES_EXP=all（四组实验共享一个 Results/paper-batch__.../ 父目录）"
  EXP_LOG="${LOG_DIR}/04_exp-all.log"
  EXP_START=$SECONDS
  set +e
  uv run python run.py --exp all "${RUN_FLAGS[@]}" 2>&1 | tee "${EXP_LOG}"
  EXP_RC=${PIPESTATUS[0]}
  set -e
  EXP_ELAPSED=$((SECONDS - EXP_START))
  if [[ ${EXP_RC} -eq 0 ]]; then
    log "  <<< 批次完成，用时 ${EXP_ELAPSED}s"
  else
    warn "  <<< 批次返回非 0（rc=${EXP_RC}，用时 ${EXP_ELAPSED}s）"
  fi
else
  # 非 all：逐个 exp 单独跑，每个 exp 会各自生成 `Results/paper-batch__expN__...__<ts>/`，
  # 若希望它们也合并到一个父目录，请直接用 IES_EXP=all 或先手工调 run.py --exp all。
  warn "IES_EXP='${IES_EXP}' 不是 'all'，四组实验将分别生成独立的父目录。"
  warn "若要统一汇总到单一 Results/paper-batch__.../，请改用 IES_EXP=all。"
  for EXP in ${IES_EXP}; do
    hr
    log "  >>> 开始实验 exp${EXP}"
    EXP_LOG="${LOG_DIR}/04_exp${EXP}.log"
    EXP_START=$SECONDS
    set +e
    uv run python run.py --exp "${EXP}" "${RUN_FLAGS[@]}" 2>&1 | tee "${EXP_LOG}"
    EXP_RC=${PIPESTATUS[0]}
    set -e
    EXP_ELAPSED=$((SECONDS - EXP_START))
    if [[ ${EXP_RC} -eq 0 ]]; then
      log "  <<< exp${EXP} 完成，用时 ${EXP_ELAPSED}s"
    else
      warn "  <<< exp${EXP} 返回非 0（rc=${EXP_RC}，用时 ${EXP_ELAPSED}s），继续下一组"
    fi
  done
fi

OVERALL_ELAPSED=$((SECONDS - OVERALL_START))

# ---- 5) 汇总 ----
hr
log "[5/5] 实验汇总"
{
  echo "# post_rebuild 实验批次汇总"
  echo ""
  echo "- 时间戳：${TIMESTAMP}"
  echo "- 实验序列：${IES_EXP}"
  echo "- 总用时：${OVERALL_ELAPSED} 秒"
  echo "- 运行标记参数："
  echo "  - workers=${IES_WORKERS:-auto}"
  echo "  - post-analysis-mode=${IES_POST_MODE}"
  echo "  - test-run=${IES_TEST_RUN}"
  echo "  - quick-run=${IES_QUICK_RUN}"
  echo ""
  echo "## 日志清单"
  echo ""
  for f in "${LOG_DIR}"/*.log; do
    [[ -f "$f" ]] || continue
    echo "- $(basename "$f")  ($(wc -l < "$f") 行)"
  done
  echo ""
  echo "## 实验产出目录"
  echo ""
  if [[ "${IES_EXP}" == "all" ]]; then
    echo "本批次四组实验统一落在 \`Results/paper-batch__exp-all__...__${TIMESTAMP%_*}_*/\` 下（由 run.py 自动创建）。"
    echo ""
    echo "典型结构："
    echo ""
    echo "\`\`\`"
    echo "Results/paper-batch__exp-all__full__n80__g150__w${IES_WORKERS:-*}__<ts>/"
    echo "├── exp1__german__base__...__n80__g150__<ts>/"
    echo "├── exp2a__german__base__...__n80__g150__<ts>/"
    echo "├── exp2b__german__carnot__...__n80__g150__<ts>/"
    echo "├── exp3__songshan_lake__base__...__n80__g150__<ts>/"
    echo "├── exp4__songshan_lake__carnot__...__n80__g150__<ts>/"
    echo "└── batch_timing_summary.md"
    echo "\`\`\`"
  else
    echo "IES_EXP='${IES_EXP}'（非 all）：每组 exp 会各自生成 \`Results/paper-batch__expN__.../\`，不共享父目录。"
  fi
} > "${LOG_DIR}/SUMMARY.md"

log "一键实验完成，日志目录：${LOG_DIR}"
hr
