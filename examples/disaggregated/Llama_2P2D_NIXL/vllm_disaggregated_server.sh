#!/usr/bin/env bash

set -euo pipefail

MODEL="${MODEL:-/workspace/Meta-Llama-3-8B-Instruct/}"
PIDS=()

cleanup() {
    trap - INT TERM
    for pid in "${PIDS[@]}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}"
        fi
    done
    wait "${PIDS[@]}" 2>/dev/null || true
}

start_instance() {
    local role=$1
    local gpu=$2
    local http_port=$3
    local side_channel_port=$4
    local kv_role

    if [[ "${role}" == "prefill" ]]; then
        kv_role="kv_producer"
    else
        kv_role="kv_consumer"
    fi

    echo "Starting ${role} instance: GPU=${gpu}, HTTP=${http_port}, NIXL=${side_channel_port}"
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    UCX_NET_DEVICES=all \
    VLLM_NIXL_SIDE_CHANNEL_PORT="${side_channel_port}" \
        vllm serve "${MODEL}" \
        --port "${http_port}" \
        --enforce-eager \
        --enable-request-id-headers \
        --no-enable-prefix-caching \
        --kv-transfer-config \
        "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"${kv_role}\"}" &
    PIDS+=("$!")
}

if ! python3 -c "import nixl" >/dev/null 2>&1; then
    echo "ERROR: Python package 'nixl' is not installed." >&2
    exit 1
fi

gpu_count=$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l)
if [[ "${gpu_count}" -lt 4 ]]; then
    echo "ERROR: this scenario requires at least 4 GPUs." >&2
    exit 1
fi

trap cleanup EXIT INT TERM

start_instance prefill 0 8100 5600
start_instance prefill 1 8101 5601
start_instance decode 2 8200 5700
start_instance decode 3 8201 5701

echo "Started 2 prefill and 2 decode instances. Press Ctrl-C to stop."
wait
