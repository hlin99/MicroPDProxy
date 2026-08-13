#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
NUM_PROMPTS="${NUM_PROMPTS:-32}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/bench_results}"

MODEL=$(
    python3 - "${PROXY_ENDPOINT%/}/v1/models" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.load(response)
except Exception as exc:
    raise SystemExit(f"Failed to query {url}: {exc}")

models = payload.get("data", [])
if not models or not models[0].get("id"):
    raise SystemExit(f"No model was returned by {url}")
print(models[0]["id"])
PY
)

mkdir -p "${RESULT_DIR}"
vllm bench serve \
    --host 127.0.0.1 \
    --port 8868 \
    --model "${MODEL}" \
    --backend openai \
    --endpoint /v1/completions \
    --dataset-name random \
    --random-input-len 512 \
    --random-output-len 64 \
    --random-range-ratio 0.8 \
    --num-prompts "${NUM_PROMPTS}" \
    --request-rate 4 \
    --ignore-eos \
    --save-result \
    --result-dir "${RESULT_DIR}" \
    --result-filename "xpyd_2p2d_nixl.json"
