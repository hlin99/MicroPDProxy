#!/usr/bin/env bash

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/tmp/tokenizers/facebook/opt-125m}"
PORT="${PORT:-8000}"

export GLOO_SOCKET_IFNAME="${GLOO_SOCKET_IFNAME:-lo}"
export HF_HUB_OFFLINE=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export TRANSFORMERS_OFFLINE=1
export VLLM_CPU_KVCACHE_SPACE="${VLLM_CPU_KVCACHE_SPACE:-1}"
export VLLM_CPU_OMP_THREADS_BIND="${VLLM_CPU_OMP_THREADS_BIND:-nobind}"
export VLLM_DEVICE=cpu
export VLLM_HOST_IP="${VLLM_HOST_IP:-127.0.0.1}"
export VLLM_TARGET_DEVICE=cpu

exec vllm serve "${MODEL_DIR}" \
    --host 127.0.0.1 \
    --port "${PORT}" \
    --served-model-name facebook/opt-125m \
    --dtype bfloat16 \
    --disable-hybrid-kv-cache-manager \
    --no-enable-prefix-caching \
    --kv-cache-memory-bytes 1073741824 \
    --max-model-len 128 \
    --max-num-seqs 1 \
    --enforce-eager
