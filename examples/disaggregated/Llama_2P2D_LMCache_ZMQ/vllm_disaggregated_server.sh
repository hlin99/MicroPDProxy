#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    local gpu=$2
    local http_port=$3
    local config=$4
    local rpc_port=$5
    local kv_role
    local extra_config

    if [[ "${role}" == "prefill" ]]; then
        kv_role="kv_producer"
        extra_config="\"discard_partial_chunks\":false,\"lmcache_rpc_port\":\"${rpc_port}\""
    else
        kv_role="kv_consumer"
        extra_config="\"discard_partial_chunks\":false,\"lmcache_rpc_port\":\"${rpc_port}\",\"skip_last_n_tokens\":1"
    fi

    echo "Starting ${role}: GPU=${gpu}, HTTP=${http_port}, RPC=${rpc_port}"
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=123 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    UCX_TLS=cuda_ipc,cuda_copy,tcp \
    LMCACHE_CONFIG_FILE="${config}" \
    LMCACHE_USE_EXPERIMENTAL=True \
    VLLM_ENABLE_V1_MULTIPROCESSING=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
        vllm serve "${MODEL}" \
        --served-model-name "${SERVED_MODEL_NAME}" \
        --port "${http_port}" \
        --enforce-eager \
        --no-enable-prefix-caching \
        --kv-transfer-config \
        "{\"kv_connector\":\"LMCacheConnectorV1\",\"kv_role\":\"${kv_role}\",\"kv_connector_extra_config\":{${extra_config}}}" &
    PIDS+=("$!")
}

trap cleanup EXIT INT TERM

start_instance prefill 0 8100 "${SCRIPT_DIR}/configs/prefill.yaml" producer1
start_instance prefill 1 8101 "${SCRIPT_DIR}/configs/prefill.yaml" producer2
start_instance decode 2 8200 "${SCRIPT_DIR}/configs/decode-1.yaml" consumer1
start_instance decode 3 8201 "${SCRIPT_DIR}/configs/decode-2.yaml" consumer2

echo "Started LMCache in-process 2P2D instances. Press Ctrl-C to stop."
wait
