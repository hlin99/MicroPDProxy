#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""

cleanup() {
    if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill "${BACKEND_PID}"
        wait "${BACKEND_PID}" 2>/dev/null || true
    fi
}

wait_for_health() {
    local port=$1 deadline=$((SECONDS + 1200))
    until curl --silent --fail --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null; do
        if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
            echo "ERROR: backend process exited before port ${port} became healthy." >&2
            return 1
        fi
        (( SECONDS < deadline )) || { echo "ERROR: timed out waiting for port ${port}." >&2; return 1; }
        sleep 2
    done
}

trap cleanup EXIT INT TERM

bash "${SCRIPT_DIR}/vllm_disaggregated_server.sh" >"${SCRIPT_DIR}/pd_servers.log" 2>&1 &
BACKEND_PID=$!
for port in {8100..8107} {8200..8207}; do
    wait_for_health "${port}"
done

bash "${SCRIPT_DIR}/run_matrix.sh" "$@"
