#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${MODEL:-/workspace/Meta-Llama-3-8B-Instruct/}"
FIRST_TOKEN_SOURCE="${FIRST_TOKEN_SOURCE:-decode}"
PIDS=()

if [[ "${FIRST_TOKEN_SOURCE}" == "prefill" ]]; then
    DECODE_SKIP_LAST_TOKENS=1
elif [[ "${FIRST_TOKEN_SOURCE}" == "decode" ]]; then
    DECODE_SKIP_LAST_TOKENS=1
else
    echo "FIRST_TOKEN_SOURCE must be 'prefill' or 'decode'" >&2
    exit 2
fi
DISCARD_PARTIAL_CHUNKS=false

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
    local config=$5
    local kv_role rpc_port extra_config

    if [[ "${role}" == "prefill" ]]; then
        kv_role="kv_producer"
        rpc_port="producer${index}"
        extra_config="\"discard_partial_chunks\":${DISCARD_PARTIAL_CHUNKS},\"lmcache_rpc_port\":\"${rpc_port}\""
    else
        kv_role="kv_consumer"
        rpc_port="consumer${index}"
        extra_config="\"discard_partial_chunks\":${DISCARD_PARTIAL_CHUNKS},\"lmcache_rpc_port\":\"${rpc_port}\",\"skip_last_n_tokens\":${DECODE_SKIP_LAST_TOKENS}"
    fi

    echo "Starting ${role}${index}: GPU=${gpu}, HTTP=${http_port}"
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=123 \
    CUDA_VISIBLE_DEVICES="${gpu}" \
    UCX_TLS=cuda_ipc,cuda_copy,tcp \
    LMCACHE_CONFIG_FILE="${config}" \
    LMCACHE_USE_EXPERIMENTAL=True \
    LMCACHE_SAVE_UNFULL_CHUNK=True \
    VLLM_ENABLE_V1_MULTIPROCESSING=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn \
        vllm serve "${MODEL}" \
        --port "${http_port}" \
        --max-model-len 1024 \
        --max-num-seqs 8 \
        --gpu-memory-utilization 0.22 \
        --quantization fp8 \
        --kv-cache-dtype fp8 \
        --enforce-eager \
        --no-enable-prefix-caching \
        --kv-transfer-config \
        "{\"kv_connector\":\"LMCacheConnectorV1\",\"kv_role\":\"${kv_role}\",\"kv_connector_extra_config\":{${extra_config}}}" &
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

trap cleanup EXIT INT TERM

# Start one process per GPU per round to avoid transient FP8 conversion OOM.
for round in 0 1 2 3; do
    ports=()
    for gpu in 0 1 2 3; do
        index=$((round * 4 + gpu))
        if ((index < 8)); then
            instance=$((index + 1))
            port=$((8100 + index))
            start_instance prefill "${instance}" "${gpu}" "${port}" \
                "${SCRIPT_DIR}/configs/prefill.yaml"
        else
            decode_index=$((index - 8))
            instance=$((decode_index + 1))
            port=$((8200 + decode_index))
            start_instance decode "${instance}" "${gpu}" "${port}" \
                "${SCRIPT_DIR}/configs/decode-${instance}.yaml"
        fi
        ports+=("${port}")
    done
    for port in "${ports[@]}"; do
        wait_port "${port}"
    done
done

echo "All 8P8D ${FIRST_TOKEN_SOURCE}-first instances are ready. Press Ctrl-C to stop."
wait
