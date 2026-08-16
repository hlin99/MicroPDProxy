#!/usr/bin/env bash

set -euo pipefail

MODEL="${MODEL:-/workspace/Meta-Llama-3-8B-Instruct/}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-/workspace/Meta-Llama-3-8B-Instruct/}"
BASE_PORT="${BASE_PORT:-8000}"
PIDS=()

cleanup() {
    trap - INT TERM
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
        fi
    done
    wait "${PIDS[@]}" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

for gpu in 0 1 2 3; do
    port=$((BASE_PORT + gpu))
    echo "Starting Llama instance on GPU ${gpu}, port ${port}"
    PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES="${gpu}" \
        vllm serve "${MODEL}" \
        --served-model-name "${SERVED_MODEL_NAME}" \
        --port "${port}" \
        --no-enable-prefix-caching &
    PIDS+=("$!")
done

echo "All instances started. Ports: ${BASE_PORT}-$((BASE_PORT + 3))"
wait
