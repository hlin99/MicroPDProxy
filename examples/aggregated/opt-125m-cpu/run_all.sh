#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
BACKEND_ENDPOINT="${BACKEND_ENDPOINT:-http://127.0.0.1:8000}"
LOG_DIR="${SCRIPT_DIR}/logs"
PROXY_PID=""
BACKEND_PID=""

cleanup() {
    for pid in "${BACKEND_PID}" "${PROXY_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}"
            wait "${pid}" 2>/dev/null || true
        fi
    done
}

wait_for_url() {
    local url=$1 pid=$2 deadline=$((SECONDS + 600))
    until curl --silent --fail --max-time 2 "${url}" >/dev/null; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            echo "ERROR: process ${pid} exited before ${url} became ready." >&2
            return 1
        fi
        (( SECONDS < deadline )) || {
            echo "ERROR: timed out waiting for ${url}." >&2
            return 1
        }
        sleep 2
    done
}

wait_for_port_close() {
    local url=$1 deadline=$((SECONDS + 60))
    while curl --silent --max-time 1 "${url}" >/dev/null; do
        (( SECONDS < deadline )) || {
            echo "ERROR: ${url} did not close." >&2
            return 1
        }
        sleep 1
    done
}

wait_for_log_count() {
    local pattern=$1 expected=$2 deadline=$((SECONDS + 30))
    until [[ "$(grep -F -c "${pattern}" "${LOG_DIR}/proxy.log" || true)" -ge "${expected}" ]]; do
        (( SECONDS < deadline )) || {
            echo "ERROR: log pattern did not appear ${expected} times: ${pattern}" >&2
            return 1
        }
        sleep 1
    done
}

wait_for_instance_status() {
    local expected=$1 deadline=$((SECONDS + 60))
    until curl --silent --fail --max-time 2 \
        "${PROXY_ENDPOINT}/status/instances" |
        python -c '
import json
import sys

expected = sys.argv[1]
instances = json.load(sys.stdin)["aggregated_instances"]
raise SystemExit(
    0
    if len(instances) == 1
    and instances[0]["address"] == "127.0.0.1:8000"
    and instances[0]["status"] == expected
    else 1
)
' "${expected}"; do
        (( SECONDS < deadline )) || {
            echo "ERROR: backend did not become ${expected}." >&2
            curl --silent "${PROXY_ENDPOINT}/status/instances" >&2 || true
            return 1
        }
        sleep 1
    done
}

assert_inference_status() {
    local expected=$1 actual
    actual="$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            "${PROXY_ENDPOINT}/v1/completions" \
            -H "Content-Type: application/json" \
            -d '{
                "model": "facebook/opt-125m",
                "prompt": "offline check",
                "max_tokens": 1
            }'
    )"
    [[ "${actual}" == "${expected}" ]] || {
        echo "ERROR: expected inference HTTP ${expected}, got ${actual}." >&2
        return 1
    }
}

start_backend() {
    bash "${SCRIPT_DIR}/vllm_server.sh" >>"${LOG_DIR}/vllm.log" 2>&1 &
    BACKEND_PID=$!
    wait_for_url "${BACKEND_ENDPOINT}/health" "${BACKEND_PID}"
    wait_for_instance_status healthy
}

stop_backend() {
    kill "${BACKEND_PID}"
    wait "${BACKEND_PID}" 2>/dev/null || true
    BACKEND_PID=""
    wait_for_port_close "${BACKEND_ENDPOINT}/health"
    wait_for_instance_status unhealthy
}

trap cleanup EXIT INT TERM

mkdir -p "${LOG_DIR}"
: >"${LOG_DIR}/proxy.log"
: >"${LOG_DIR}/vllm.log"

echo "=== Phase 1: proxy-first startup with backend offline ==="
bash "${SCRIPT_DIR}/start_proxy.sh" >"${LOG_DIR}/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for_url "${PROXY_ENDPOINT}/status/instances" "${PROXY_PID}"
wait_for_instance_status unhealthy
assert_inference_status 503

echo "=== Phase 2: node discovery and inference ==="
start_backend
wait_for_log_count "Node heartbeat | mode=aggregated | aggregated=1/1 online" 1
bash "${SCRIPT_DIR}/smoke_test.sh"

echo "=== Phase 3: node loss ==="
stop_backend
assert_inference_status 503

echo "=== Phase 4: node reconnection ==="
start_backend
wait_for_log_count "Node heartbeat | mode=aggregated | aggregated=1/1 online" 2
bash "${SCRIPT_DIR}/smoke_test.sh"

grep -q "Node heartbeat | mode=aggregated | aggregated=0/1 online" \
    "${LOG_DIR}/proxy.log"
grep -q "Node heartbeat | mode=aggregated | aggregated=1/1 online" \
    "${LOG_DIR}/proxy.log"

echo "Aggregated CPU lifecycle smoke test passed."
