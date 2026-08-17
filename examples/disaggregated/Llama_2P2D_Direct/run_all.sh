#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
        (( SECONDS < deadline )) || { echo "ERROR: timed out waiting for ${url}." >&2; return 1; }
        sleep 2
    done
}

wait_for_instances() {
    local deadline=$((SECONDS + 120))

    until curl --silent --fail --max-time 2 \
        "http://127.0.0.1:8868/status/instances" |
        python3 -c '
import json
import sys

status = json.load(sys.stdin)
expected = {"prefill_instances": 2, "decode_instances": 2}
raise SystemExit(
    0
    if all(
        len(status[key]) == count
        and all(instance["status"] == "healthy" for instance in status[key])
        for key, count in expected.items()
    )
    else 1
)
'; do
        if ! kill -0 "${PROXY_PID}" 2>/dev/null; then
            echo "ERROR: proxy exited before all direct instances became healthy." >&2
            return 1
        fi
        (( SECONDS < deadline )) || {
            echo "ERROR: timed out waiting for all direct instances." >&2
            curl --silent "http://127.0.0.1:8868/status/instances" >&2 || true
            return 1
        }
        sleep 2
    done
}

trap cleanup EXIT INT TERM

bash "${SCRIPT_DIR}/start_proxy.sh" >"${SCRIPT_DIR}/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for_health "http://127.0.0.1:8868/status/instances" "${PROXY_PID}"

bash "${SCRIPT_DIR}/vllm_disaggregated_server.sh" >"${SCRIPT_DIR}/pd_servers.log" 2>&1 &
BACKEND_PID=$!
for port in 8100 8101 8200 8201; do
    wait_for_health "http://127.0.0.1:${port}/health" "${BACKEND_PID}"
done
wait_for_instances

bash "${SCRIPT_DIR}/smoke_test.sh"
