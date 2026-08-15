#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
BACKEND_PID=""
PROXY_PID=""

cleanup() {
    for pid in "${PROXY_PID}" "${BACKEND_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}"
            wait "${pid}" 2>/dev/null || true
        fi
    done
}

wait_for_health() {
    local url=$1 pid=$2 deadline=$((SECONDS + 1200))
    until curl --silent --fail --max-time 2 "${url}" >/dev/null; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            echo "ERROR: process exited before ${url} became healthy." >&2
            return 1
        fi
        (( SECONDS < deadline )) || {
            echo "ERROR: timed out waiting for ${url}." >&2
            return 1
        }
        sleep 2
    done
}

trap cleanup EXIT INT TERM
mkdir -p "${LOG_DIR}"

bash "${SCRIPT_DIR}/start_proxy.sh" >"${LOG_DIR}/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for_health "http://127.0.0.1:8868/status/instances" "${PROXY_PID}"

bash "${SCRIPT_DIR}/vllm_servers.sh" >"${LOG_DIR}/backends.log" 2>&1 &
BACKEND_PID=$!
for port in 8100 8200 8000 8001; do
    wait_for_health "http://127.0.0.1:${port}/health" "${BACKEND_PID}"
done

bash "${SCRIPT_DIR}/smoke_test.sh"
