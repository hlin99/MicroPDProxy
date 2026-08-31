#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
BACKEND_ENDPOINT="${BACKEND_ENDPOINT:-http://127.0.0.1:8000}"
LOG_DIR="${SCRIPT_DIR}/logs"
LOCAL_CONFIG="${SCRIPT_DIR}/xpyd_aggregated.yaml"
AUTO_CONFIG="${SCRIPT_DIR}/xpyd_aggregated_auto.yaml"
AUTO_SUCCESS_CACHE="${LOG_DIR}/hf-auto-success"
AUTO_FAILURE_CACHE="${LOG_DIR}/hf-auto-failure"
PROXY_PID=""
BACKEND_PID=""

# Exercised by smoke_test.sh against the admin endpoint. Never a real secret:
# the proxy only binds to loopback for the duration of this check.
export ADMIN_API_KEY="${ADMIN_API_KEY:-xpyd-example-admin-key}"

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

start_proxy() {
    local config=$1
    shift
    env CONFIG_FILE="${config}" "$@" \
        bash "${SCRIPT_DIR}/start_proxy.sh" >>"${LOG_DIR}/proxy.log" 2>&1 &
    PROXY_PID=$!
    wait_for_url "${PROXY_ENDPOINT}/status/instances" "${PROXY_PID}"
}

stop_proxy() {
    kill "${PROXY_PID}"
    wait "${PROXY_PID}" 2>/dev/null || true
    PROXY_PID=""
    wait_for_port_close "${PROXY_ENDPOINT}/status/instances"
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

wait_for_discovered_model() {
    local deadline=$((SECONDS + 60))
    until curl --silent --fail --max-time 2 \
        "${PROXY_ENDPOINT}/v1/models" |
        python -c '
import json
import sys

models = json.load(sys.stdin)
raise SystemExit(
    0
    if models == {
        "object": "list",
        "data": [{
            "id": "facebook/opt-125m",
            "object": "model",
            "created": 0,
            "owned_by": "system",
        }],
    }
    else 1
)
'; do
        (( SECONDS < deadline )) || {
            echo "ERROR: proxy did not auto-detect facebook/opt-125m." >&2
            curl --silent "${PROXY_ENDPOINT}/v1/models" >&2 || true
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

assert_health_status() {
    local expected=$1 actual
    actual="$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            "${PROXY_ENDPOINT}/health"
    )"
    [[ "${actual}" == "${expected}" ]] || {
        echo "ERROR: expected /health HTTP ${expected}, got ${actual}." >&2
        curl --silent "${PROXY_ENDPOINT}/health" >&2 || true
        return 1
    }
}

assert_passthrough_status() {
    local expected=$1 actual
    actual="$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            "${PROXY_ENDPOINT}/tokenize" \
            -H "Content-Type: application/json" \
            -d '{"model": "facebook/opt-125m", "prompt": "offline check"}'
    )"
    [[ "${actual}" == "${expected}" ]] || {
        echo "ERROR: expected /tokenize HTTP ${expected}, got ${actual}." >&2
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
rm -rf "${AUTO_SUCCESS_CACHE}" "${AUTO_FAILURE_CACHE}"
: >"${LOG_DIR}/proxy.log"
: >"${LOG_DIR}/vllm.log"

echo "=== Phase 1: proxy-first startup with backend offline ==="
start_proxy "${LOCAL_CONFIG}"
wait_for_instance_status unhealthy
assert_inference_status 503
assert_passthrough_status 503
assert_health_status 503

echo "=== Phase 2: node discovery and inference ==="
start_backend
wait_for_discovered_model
wait_for_log_count "Auto-detected model 'facebook/opt-125m' on 127.0.0.1:8000" 1
wait_for_log_count "Node heartbeat | mode=aggregated | aggregated=1/1 online" 1
bash "${SCRIPT_DIR}/smoke_test.sh"

echo "=== Phase 3: node loss ==="
stop_backend
assert_inference_status 503
assert_passthrough_status 503
assert_health_status 503

echo "=== Phase 4: node reconnection ==="
start_backend
wait_for_discovered_model
wait_for_log_count "Node heartbeat | mode=aggregated | aggregated=1/1 online" 2
bash "${SCRIPT_DIR}/smoke_test.sh"

echo "=== Phase 5: automatic tokenizer download ==="
stop_proxy
start_proxy "${AUTO_CONFIG}" "HF_HOME=${AUTO_SUCCESS_CACHE}"
wait_for_instance_status healthy
wait_for_discovered_model
wait_for_log_count \
    "Loaded tokenizer for model 'facebook/opt-125m' from facebook/opt-125m" 1
assert_inference_status 200

echo "=== Phase 6: tokenizer download failure and round-robin fallback ==="
stop_proxy
start_proxy "${AUTO_CONFIG}" \
    "HF_HOME=${AUTO_FAILURE_CACHE}" \
    "HF_HUB_OFFLINE=1" \
    "TRANSFORMERS_OFFLINE=1"
wait_for_instance_status healthy
wait_for_discovered_model
wait_for_log_count \
    "Falling back to roundrobin scheduling for this model." 1
assert_inference_status 200
source "${SCRIPT_DIR}/../../lib/proxy_api_smoke.sh"
smoke_admin_success decode 127.0.0.1:8000

grep -q "Node heartbeat | mode=aggregated | aggregated=0/1 online" \
    "${LOG_DIR}/proxy.log"
grep -q "Node heartbeat | mode=aggregated | aggregated=1/1 online" \
    "${LOG_DIR}/proxy.log"

echo "Aggregated CPU lifecycle smoke test passed."
