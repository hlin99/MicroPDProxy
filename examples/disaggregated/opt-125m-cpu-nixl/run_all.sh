#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
LOG_DIR="${SCRIPT_DIR}/logs"
PROXY_PID=""
PREFILL_PID=""
DECODE_PID=""

cleanup() {
    for pid in "${DECODE_PID}" "${PREFILL_PID}" "${PROXY_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}"
            wait "${pid}" 2>/dev/null || true
        fi
    done
}

phase() {
    local message="=== $1 ==="
    echo "${message}"
    printf '%s\n' "${message}" >>"${LOG_DIR}/proxy.log"
    printf '%s\n' "${message}" >>"${LOG_DIR}/prefill.log"
    printf '%s\n' "${message}" >>"${LOG_DIR}/decode.log"
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

wait_for_log() {
    local pattern=$1 deadline=$((SECONDS + 30))
    until grep -F -q "${pattern}" "${LOG_DIR}/proxy.log"; do
        (( SECONDS < deadline )) || {
            echo "ERROR: proxy log pattern did not appear: ${pattern}" >&2
            return 1
        }
        sleep 1
    done
}

wait_for_instance_status() {
    local role=$1 address=$2 expected=$3 deadline=$((SECONDS + 60))
    until curl --silent --fail --max-time 2 \
        "${PROXY_ENDPOINT}/status/instances" |
        python -c '
import json
import sys

role, address, expected = sys.argv[1:]
instances = json.load(sys.stdin)[f"{role}_instances"]
raise SystemExit(
    0
    if len(instances) == 1
    and instances[0]["address"] == address
    and instances[0]["status"] == expected
    else 1
)
' "${role}" "${address}" "${expected}"; do
        (( SECONDS < deadline )) || {
            echo "ERROR: ${role} ${address} did not become ${expected}." >&2
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

start_prefill() {
    bash "${SCRIPT_DIR}/vllm_server.sh" prefill 8100 5600 \
        >>"${LOG_DIR}/prefill.log" 2>&1 &
    PREFILL_PID=$!
    wait_for_url "http://127.0.0.1:8100/health" "${PREFILL_PID}"
    wait_for_instance_status prefill 127.0.0.1:8100 healthy
}

start_decode() {
    bash "${SCRIPT_DIR}/vllm_server.sh" decode 8200 5601 \
        >>"${LOG_DIR}/decode.log" 2>&1 &
    DECODE_PID=$!
    wait_for_url "http://127.0.0.1:8200/health" "${DECODE_PID}"
    wait_for_instance_status decode 127.0.0.1:8200 healthy
}

stop_prefill() {
    kill "${PREFILL_PID}"
    wait "${PREFILL_PID}" 2>/dev/null || true
    PREFILL_PID=""
    wait_for_port_close "http://127.0.0.1:8100/health"
    wait_for_instance_status prefill 127.0.0.1:8100 unhealthy
}

stop_decode() {
    kill "${DECODE_PID}"
    wait "${DECODE_PID}" 2>/dev/null || true
    DECODE_PID=""
    wait_for_port_close "http://127.0.0.1:8200/health"
    wait_for_instance_status decode 127.0.0.1:8200 unhealthy
}

trap cleanup EXIT INT TERM

mkdir -p "${LOG_DIR}"
: >"${LOG_DIR}/proxy.log"
: >"${LOG_DIR}/prefill.log"
: >"${LOG_DIR}/decode.log"

phase "Phase 1: proxy-first startup with both P/D nodes offline"
bash "${SCRIPT_DIR}/start_proxy.sh" >>"${LOG_DIR}/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for_url "${PROXY_ENDPOINT}/status/instances" "${PROXY_PID}"
wait_for_instance_status prefill 127.0.0.1:8100 unhealthy
wait_for_instance_status decode 127.0.0.1:8200 unhealthy
assert_inference_status 503

phase "Phase 2: prefill-only partial topology"
start_prefill
assert_inference_status 503

phase "Phase 3: decode discovery and NIXL TCP inference"
start_decode
bash "${SCRIPT_DIR}/smoke_test.sh"
wait_for_log \
    "Node heartbeat | mode=disaggregated | P=1/1 online | D=1/1 online"

phase "Phase 4: prefill loss and reconnection"
stop_prefill
assert_inference_status 503
start_prefill
bash "${SCRIPT_DIR}/smoke_test.sh"

phase "Phase 5: decode loss and reconnection"
stop_decode
assert_inference_status 503
start_decode
bash "${SCRIPT_DIR}/smoke_test.sh"

wait_for_log \
    "Node heartbeat | mode=disaggregated | P=0/1 online | D=0/1 online"

echo "OPT-125M CPU NIXL TCP lifecycle test passed."
