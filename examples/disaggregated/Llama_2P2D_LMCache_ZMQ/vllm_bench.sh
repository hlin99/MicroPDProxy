#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NUM_PROMPTS="${NUM_PROMPTS:-16}"

mkdir -p "${SCRIPT_DIR}/bench_results"
vllm bench serve \
    --host 127.0.0.1 \
    --port 8868 \
    --model /workspace/Meta-Llama-3-8B-Instruct/ \
    --backend openai \
    --endpoint /v1/completions \
    --dataset-name random \
    --random-input-len 512 \
    --random-output-len 64 \
    --random-range-ratio 0.8 \
    --num-prompts "${NUM_PROMPTS}" \
    --request-rate 2 \
    --ignore-eos \
    --save-result \
    --result-dir "${SCRIPT_DIR}/bench_results" \
    --result-filename "lmcache_zmq_2p2d.json"
