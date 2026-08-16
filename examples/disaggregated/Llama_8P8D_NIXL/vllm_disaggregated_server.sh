#!/usr/bin/env bash

set -euo pipefail

MODEL="${MODEL:-/workspace/Meta-Llama-3-8B-Instruct/}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-/workspace/Meta-Llama-3-8B-Instruct/}"
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
    local index=$2
    local gpu=$3
    local http_port=$4
    local side_channel_port=$5
    local kv_role

    if [[ "${role}" == "prefill" ]]; then
        kv_role="kv_producer"
    else
        kv_role="kv_consumer"
    fi

    echo "Starting ${role}${index}: GPU=${gpu}, HTTP=${http_port}, NIXL=${side_channel_port}"
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=123 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    UCX_TLS=cuda_ipc,cuda_copy,tcp \
    UCX_NET_DEVICES=all \
    VLLM_NIXL_SIDE_CHANNEL_PORT="${side_channel_port}" \
    VLLM_ENABLE_V1_MULTIPROCESSING=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
        vllm serve "${MODEL}" \
        --served-model-name "${SERVED_MODEL_NAME}" \
        --port "${http_port}" \
        --max-model-len 1024 \
        --max-num-seqs 8 \
        --gpu-memory-utilization 0.22 \
        --quantization fp8 \
        --kv-cache-dtype fp8 \
        --enforce-eager \
        --enable-request-id-headers \
        --no-enable-prefix-caching \
        --kv-transfer-config \
        "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"${kv_role}\"}" &
    PIDS+=("$!")
}

wait_port() {
    local port=$1
    local deadline=$((SECONDS + 600))
    until curl --silent --fail --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null; do
        if ((SECONDS >= deadline)); then
            echo "Timed out waiting for port ${port}" >&2
            return 1
        fi
        sleep 2
    done
}

if ! python3 -c "import nixl" >/dev/null 2>&1; then
    echo "ERROR: Python package 'nixl' is not installed." >&2
    exit 1
fi

trap cleanup EXIT INT TERM

# Start one process per GPU per round to avoid transient FP8 conversion OOM.
for round in 0 1 2 3; do
    ports=()
    for gpu in 0 1 2 3; do
        index=$((round * 4 + gpu))
        if ((index < 8)); then
            instance=$((index + 1))
            port=$((8100 + index))
            side_port=$((5600 + index))
            start_instance prefill "${instance}" "${gpu}" "${port}" "${side_port}"
        else
            decode_index=$((index - 8))
            instance=$((decode_index + 1))
            port=$((8200 + decode_index))
            side_port=$((5700 + decode_index))
            start_instance decode "${instance}" "${gpu}" "${port}" "${side_port}"
        fi
        ports+=("${port}")
    done
    for port in "${ports[@]}"; do
        wait_port "${port}"
    done
done

echo "All 8P8D NIXL instances are ready. Press Ctrl-C to stop."
wait
