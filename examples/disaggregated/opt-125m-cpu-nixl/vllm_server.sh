#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROLE="${1:?usage: vllm_server.sh <prefill|decode> <http-port> <side-channel-port>}"
PORT="${2:?usage: vllm_server.sh <prefill|decode> <http-port> <side-channel-port>}"
SIDE_CHANNEL_PORT="${3:?usage: vllm_server.sh <prefill|decode> <http-port> <side-channel-port>}"
MODEL_DIR="${MODEL_DIR:-/tmp/tokenizers/facebook/opt-125m}"
DEFAULT_UCX_NET_DEVICE=""
if [[ -r /proc/net/route ]]; then
    candidate_ucx_net_device="$(
        awk '$2 == "00000000" {print $1; exit}' /proc/net/route
    )"
    speed_file="/sys/class/net/${candidate_ucx_net_device}/speed"
    if [[ -n "${candidate_ucx_net_device}" && -r "${speed_file}" ]]; then
        candidate_ucx_net_device_speed="$(<"${speed_file}")"
        if [[ "${candidate_ucx_net_device_speed}" =~ ^[0-9]+$ ]] && (( candidate_ucx_net_device_speed > 0 )); then
            DEFAULT_UCX_NET_DEVICE="${candidate_ucx_net_device}"
        fi
    fi
fi

case "${ROLE}" in
    prefill)
        KV_ROLE=kv_producer
        ;;
    decode)
        KV_ROLE=kv_consumer
        ;;
    *)
        echo "ERROR: role must be prefill or decode, got ${ROLE}." >&2
        exit 2
        ;;
esac

export GLOO_SOCKET_IFNAME="${GLOO_SOCKET_IFNAME:-lo}"
export HF_HUB_OFFLINE=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export TRANSFORMERS_OFFLINE=1
export UCX_NET_DEVICES="${UCX_NET_DEVICES:-${DEFAULT_UCX_NET_DEVICE:-all}}"
export UCX_TLS="${UCX_TLS:-tcp}"
export NIXL_TELEMETRY_ENABLE="${NIXL_TELEMETRY_ENABLE:-y}"
export NIXL_TELEMETRY_DIR="${NIXL_TELEMETRY_DIR:-${SCRIPT_DIR}/logs/nixl-telemetry}"
export VLLM_CPU_OMP_THREADS_BIND="${VLLM_CPU_OMP_THREADS_BIND:-nobind}"
export VLLM_DEVICE=cpu
export VLLM_HOST_IP="${VLLM_HOST_IP:-127.0.0.1}"
export VLLM_NIXL_SIDE_CHANNEL_HOST=127.0.0.1
export VLLM_NIXL_SIDE_CHANNEL_PORT="${SIDE_CHANNEL_PORT}"
export VLLM_TARGET_DEVICE=cpu

mkdir -p "${NIXL_TELEMETRY_DIR}"

exec vllm serve "${MODEL_DIR}" \
    --host 127.0.0.1 \
    --port "${PORT}" \
    --served-model-name facebook/opt-125m \
    --dtype bfloat16 \
    --disable-hybrid-kv-cache-manager \
    --no-enable-prefix-caching \
    --kv-cache-memory-bytes 536870912 \
    --max-model-len 128 \
    --max-num-seqs 1 \
    --enforce-eager \
    --enable-request-id-headers \
    --kv-transfer-config \
    "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"${KV_ROLE}\",\"kv_buffer_device\":\"cpu\",\"kv_load_failure_policy\":\"fail\"}"
