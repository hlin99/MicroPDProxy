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
    local gpu=$1 port=$2 model_name=$3

    echo "Starting ${model_name}: GPU=${gpu}, HTTP=${port}"
    PYTHONUNBUFFERED=1 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    VLLM_ENABLE_V1_MULTIPROCESSING=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
        vllm serve "${MODEL}" \
        --served-model-name "${model_name}" \
        --port "${port}" \
        --enforce-eager \
        --no-enable-prefix-caching &
    PIDS+=("$!")
}

trap cleanup EXIT INT TERM

start_instance 0 8100 disaggregated-model
start_instance 1 8200 disaggregated-model
start_instance 2 8000 aggregated-model
start_instance 3 8001 aggregated-model

echo "Started 1P1D and 2 aggregated instances. Press Ctrl-C to stop."
wait
