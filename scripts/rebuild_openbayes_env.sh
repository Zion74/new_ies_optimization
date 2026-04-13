#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export IES_RESET_VENV="${IES_RESET_VENV:-1}"
export IES_PRUNE_UV_CACHE="${IES_PRUNE_UV_CACHE:-0}"

"${SCRIPT_DIR}/openbayes_setup.sh" "$@"
