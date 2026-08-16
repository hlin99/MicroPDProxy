#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONFIG_PATH="${1:-${SCRIPT_DIR}/xpyd_1p1d.yaml}"

export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec python -m xpyd.proxy proxy --config "${CONFIG_PATH}"
