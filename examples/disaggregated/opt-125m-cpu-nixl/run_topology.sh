#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_NAME="${1:?usage: run_topology.sh <config-name> <prefill-count> <decode-count>}"
PREFILL_COUNT="${2:?usage: run_topology.sh <config-name> <prefill-count> <decode-count>}"
DECODE_COUNT="${3:?usage: run_topology.sh <config-name> <prefill-count> <decode-count>}"
CONFIG_PATH="${SCRIPT_DIR}/${CONFIG_NAME}"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
LOG_DIR="${SCRIPT_DIR}/logs"
PROXY_PID=""
PREFILL_PIDS=()
DECODE_PIDS=()

[[ -f "${CONFIG_PATH}" ]] || {
    echo "ERROR: topology config does not exist: ${CONFIG_PATH}" >&2
    exit 2
}
[[ "${PREFILL_COUNT}" =~ ^[1-9][0-9]*$ && "${DECODE_COUNT}" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: prefill and decode counts must be positive integers." >&2
    exit 2
}

cleanup() {
    local pid
    for pid in "${DECODE_PIDS[@]-}" "${PREFILL_PIDS[@]-}" "${PROXY_PID}"; do
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
    if any(
        instance["address"] == address and instance["status"] == expected
        for instance in instances
    )
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

start_node() {
    local role=$1 index=$2 http_port side_channel_port log_file pid
    if [[ "${role}" == "prefill" ]]; then
        http_port=$((8100 + index))
        side_channel_port=$((5600 + index))
    else
        http_port=$((8200 + index))
        side_channel_port=$((5700 + index))
    fi
    log_file="${LOG_DIR}/${role}-${index}.log"
    bash "${SCRIPT_DIR}/vllm_server.sh" \
        "${role}" "${http_port}" "${side_channel_port}" >>"${log_file}" 2>&1 &
    pid=$!
    if [[ "${role}" == "prefill" ]]; then
        PREFILL_PIDS[index]="${pid}"
    else
        DECODE_PIDS[index]="${pid}"
    fi
    wait_for_url "http://127.0.0.1:${http_port}/health" "${pid}"
    wait_for_instance_status "${role}" "127.0.0.1:${http_port}" healthy
}

stop_node() {
    local role=$1 index=$2 http_port pid
    if [[ "${role}" == "prefill" ]]; then
        http_port=$((8100 + index))
        pid="${PREFILL_PIDS[index]}"
        PREFILL_PIDS[index]=""
    else
        http_port=$((8200 + index))
        pid="${DECODE_PIDS[index]}"
        DECODE_PIDS[index]=""
    fi
    kill "${pid}"
    wait "${pid}" 2>/dev/null || true
    wait_for_port_close "http://127.0.0.1:${http_port}/health"
    wait_for_instance_status "${role}" "127.0.0.1:${http_port}" unhealthy
}

run_smoke_test() {
    local request_count=$((PREFILL_COUNT > DECODE_COUNT ? PREFILL_COUNT : DECODE_COUNT))
    local expected_prefill="" expected_decode="" index
    for ((index = 0; index < PREFILL_COUNT; index++)); do
        expected_prefill+="${expected_prefill:+,}127.0.0.1:$((8100 + index))"
    done
    for ((index = 0; index < DECODE_COUNT; index++)); do
        expected_decode+="${expected_decode:+,}127.0.0.1:$((8200 + index))"
    done
    REQUEST_COUNT="${request_count}" \
    EXPECTED_PREFILL_INSTANCES="${expected_prefill}" \
    EXPECTED_DECODE_INSTANCES="${expected_decode}" \
    TOPOLOGY_NAME="${PREFILL_COUNT}P${DECODE_COUNT}D" \
        bash "${SCRIPT_DIR}/smoke_test.sh"
}

trap cleanup EXIT INT TERM

mkdir -p "${LOG_DIR}"
: >"${LOG_DIR}/proxy.log"
for ((index = 0; index < PREFILL_COUNT; index++)); do
    : >"${LOG_DIR}/prefill-${index}.log"
done
for ((index = 0; index < DECODE_COUNT; index++)); do
    : >"${LOG_DIR}/decode-${index}.log"
done

phase "Phase 1: proxy-first startup with all P/D nodes offline"
bash "${SCRIPT_DIR}/start_proxy.sh" "${CONFIG_PATH}" >>"${LOG_DIR}/proxy.log" 2>&1 &
PROXY_PID=$!
wait_for_url "${PROXY_ENDPOINT}/status/instances" "${PROXY_PID}"
for ((index = 0; index < PREFILL_COUNT; index++)); do
    wait_for_instance_status prefill "127.0.0.1:$((8100 + index))" unhealthy
done
for ((index = 0; index < DECODE_COUNT; index++)); do
    wait_for_instance_status decode "127.0.0.1:$((8200 + index))" unhealthy
done
assert_inference_status 503

phase "Phase 2: all prefill nodes online with decode nodes offline"
for ((index = 0; index < PREFILL_COUNT; index++)); do
    start_node prefill "${index}"
done
assert_inference_status 503

phase "Phase 3: all nodes online and NIXL TCP inference"
for ((index = 0; index < DECODE_COUNT; index++)); do
    start_node decode "${index}"
done
run_smoke_test
wait_for_log \
    "Node heartbeat | mode=disaggregated | P=${PREFILL_COUNT}/${PREFILL_COUNT} online | D=${DECODE_COUNT}/${DECODE_COUNT} online"

phase "Phase 4: prefill loss and reconnection"
stop_node prefill 0
wait_for_log \
    "Node heartbeat | mode=disaggregated | P=$((PREFILL_COUNT - 1))/${PREFILL_COUNT} online | D=${DECODE_COUNT}/${DECODE_COUNT} online"
if ((PREFILL_COUNT == 1)); then
    assert_inference_status 503
else
    bash "${SCRIPT_DIR}/smoke_test.sh"
fi
start_node prefill 0
run_smoke_test

phase "Phase 5: decode loss and reconnection"
stop_node decode 0
wait_for_log \
    "Node heartbeat | mode=disaggregated | P=${PREFILL_COUNT}/${PREFILL_COUNT} online | D=$((DECODE_COUNT - 1))/${DECODE_COUNT} online"
if ((DECODE_COUNT == 1)); then
    assert_inference_status 503
else
    bash "${SCRIPT_DIR}/smoke_test.sh"
fi
start_node decode 0
run_smoke_test

echo "OPT-125M CPU NIXL TCP ${PREFILL_COUNT}P${DECODE_COUNT}D lifecycle test passed."
