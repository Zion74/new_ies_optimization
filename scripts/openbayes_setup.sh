#!/usr/bin/env bash
set -Eeuo pipefail

# One-click bootstrap for an OpenBayes workspace or task container.
# Default behavior:
#   1) install uv if missing
#   2) install Python from .python-version
#   3) sync project dependencies from uv.lock / pyproject.toml
#   4) best-effort install GLPK system binary when available
#   5) print solver availability and run `python run.py --check`
#
# Optional environment variables:
#   IES_SKIP_GLPK_INSTALL=1  Skip apt-based GLPK installation
#   IES_SKIP_RUN_CHECK=1     Skip the final `run.py --check`

log() {
  printf '\n[INFO] %s\n' "$*"
}

warn() {
  printf '\n[WARN] %s\n' "$*" >&2
}

die() {
  printf '\n[ERROR] %s\n' "$*" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

[[ -f "${REPO_ROOT}/pyproject.toml" ]] || die "pyproject.toml not found under ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/run.py" ]] || die "run.py not found under ${REPO_ROOT}"

PYTHON_VERSION="3.8"
if [[ -f "${REPO_ROOT}/.python-version" ]]; then
  PYTHON_VERSION="$(tr -d '[:space:]' < "${REPO_ROOT}/.python-version")"
fi

export PATH="${HOME}/.local/bin:${PATH}"
export PIP_DISABLE_PIP_VERSION_CHECK=1

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    log "uv already available: $(command -v uv)"
    return
  fi

  command -v python3 >/dev/null 2>&1 || die "python3 is required to install uv"
  if ! python3 -m pip --version >/dev/null 2>&1; then
    log "pip not found for python3; bootstrapping with ensurepip"
    python3 -m ensurepip --upgrade
  fi

  log "Installing uv with python3 -m pip --user"
  python3 -m pip install --user --upgrade pip uv
  command -v uv >/dev/null 2>&1 || die "uv installation failed"
  log "uv installed: $(command -v uv)"
}

ensure_glpk() {
  if [[ "${IES_SKIP_GLPK_INSTALL:-0}" == "1" ]]; then
    warn "Skipping GLPK install because IES_SKIP_GLPK_INSTALL=1"
    return
  fi

  if command -v glpsol >/dev/null 2>&1; then
    log "GLPK already available: $(command -v glpsol)"
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    warn "apt-get not available; skipping GLPK system package install"
    return
  fi

  if [[ "$(id -u)" != "0" ]]; then
    warn "Not running as root; skipping apt-based GLPK install"
    return
  fi

  log "glpsol not found; installing glpk-utils via apt-get"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends glpk-utils

  if command -v glpsol >/dev/null 2>&1; then
    log "GLPK installed: $(command -v glpsol)"
  else
    warn "glpk-utils install finished but glpsol is still missing"
  fi
}

print_solver_status() {
  log "Checking solver visibility from the project environment"
  (
    cd "${REPO_ROOT}"
    uv run python - <<'PY'
from pyomo.opt import SolverFactory
from solver_config import (
    available_solver_names,
    configure_gurobi_license,
    is_solver_available,
    is_cloud_environment,
    iter_solver_display_names,
    preferred_solver_order,
)

license_path = configure_gurobi_license()
print(f"Runtime cloud mode : {is_cloud_environment()}")
print(f"Preferred order    : {iter_solver_display_names(preferred_solver_order())}")
print(f"Gurobi license path: {license_path or 'not configured'}")
print(f"Available solvers  : {iter_solver_display_names(available_solver_names(('gurobi_direct', 'highs', 'glpk'))) or 'none'}")

for solver_name in ("gurobi_direct", "highs", "glpk"):
    try:
        available = is_solver_available(solver_name)
        print(f"{solver_name:13s}: {'available' if available else 'not available'}")
    except Exception as exc:
        print(f"{solver_name:13s}: error ({exc})")
PY
  )
}

run_project_check() {
  if [[ "${IES_SKIP_RUN_CHECK:-0}" == "1" ]]; then
    warn "Skipping run.py --check because IES_SKIP_RUN_CHECK=1"
    return
  fi

  log "Running project health check: uv run python run.py --check"
  (
    cd "${REPO_ROOT}"
    uv run python run.py --check
  )
}

main() {
  cd "${REPO_ROOT}"
  log "Repo root: ${REPO_ROOT}"
  ensure_uv

  log "Installing Python ${PYTHON_VERSION} with uv"
  uv python install "${PYTHON_VERSION}"

  log "Syncing project dependencies"
  uv sync --python "${PYTHON_VERSION}"

  log "Active project Python: $(uv run python --version)"

  ensure_glpk
  print_solver_status
  run_project_check

  log "OpenBayes bootstrap finished successfully"
  cat <<EOF

Next suggested commands:
  cd "${REPO_ROOT}"
  uv run python run.py --exp 1 --test-run --workers 4
  uv run python run.py --exp 1 --workers 8

EOF
}

main "$@"
