#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRST_TOKEN_SOURCE="${FIRST_TOKEN_SOURCE:-decode}"

if [[ "${FIRST_TOKEN_SOURCE}" != "prefill" && "${FIRST_TOKEN_SOURCE}" != "decode" ]]; then
    echo "FIRST_TOKEN_SOURCE must be 'prefill' or 'decode'" >&2
    exit 2
fi

python3 "${SCRIPT_DIR}/generate_proxy_configs.py"
python3 "${SCRIPT_DIR}/../pd_matrix/run_pd_matrix.py" \
    --scenario-dir "${SCRIPT_DIR}" \
    --transport zmq \
    --source "${FIRST_TOKEN_SOURCE}" \
    --requests "${REQUESTS:-1000}" \
    --concurrency "${CONCURRENCY:-8}" \
    "$@"
