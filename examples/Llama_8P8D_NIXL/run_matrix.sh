#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "${SCRIPT_DIR}/generate_proxy_configs.py"
python3 "${SCRIPT_DIR}/../pd_matrix/run_pd_matrix.py" \
    --scenario-dir "${SCRIPT_DIR}" \
    --transport nixl \
    --requests "${REQUESTS:-1000}" \
    --concurrency "${CONCURRENCY:-8}" \
    "$@"
