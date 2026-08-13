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
    local port=$3

    echo "Starting ${role}: GPU=${gpu}, HTTP=${port}"
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    VLLM_ENABLE_V1_MULTIPROCESSING=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
        vllm serve "${MODEL}" \
        --port "${port}" \
        --enforce-eager \
        --no-enable-prefix-caching &
    PIDS+=("$!")
}

trap cleanup EXIT INT TERM

start_instance prefill-1 0 8100
start_instance prefill-2 1 8101
start_instance decode-1 2 8200
start_instance decode-2 3 8201

echo "Started direct 2P2D instances. Press Ctrl-C to stop."
wait
