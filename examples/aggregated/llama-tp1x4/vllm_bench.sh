#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
NUM_PROMPTS="${NUM_PROMPTS:-128}"
RANDOM_INPUT_LEN="${RANDOM_INPUT_LEN:-1024}"
RANDOM_OUTPUT_LEN="${RANDOM_OUTPUT_LEN:-128}"
RANDOM_RANGE_RATIO="${RANDOM_RANGE_RATIO:-0.9}"
REQUEST_RATE="${REQUEST_RATE:-8}"
RESULT_DIR="${RESULT_DIR:-${SCRIPT_DIR}/bench_results}"
RESULT_FILENAME="${RESULT_FILENAME:-xpyd_bench.json}"

read -r PROXY_HOST PROXY_PORT < <(
    python3 - "${PROXY_ENDPOINT}" <<'PY'
import sys
from urllib.parse import urlparse

endpoint = urlparse(sys.argv[1])
if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
    raise SystemExit(
        "PROXY_ENDPOINT must be an HTTP URL, for example http://127.0.0.1:8868"
    )
default_port = 443 if endpoint.scheme == "https" else 80
print(endpoint.hostname, endpoint.port or default_port)
PY
)

echo "Detecting model from ${PROXY_ENDPOINT%/}/v1/models..."
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
echo "Detected model: ${MODEL}"
echo "Sending ${NUM_PROMPTS} benchmark requests..."
echo "Input/output targets: ${RANDOM_INPUT_LEN}/${RANDOM_OUTPUT_LEN} tokens"
echo "Random range ratio: ${RANDOM_RANGE_RATIO}; request rate: ${REQUEST_RATE} RPS"

vllm bench serve \
    --host "${PROXY_HOST}" \
    --port "${PROXY_PORT}" \
    --model "${MODEL}" \
    --backend openai \
    --endpoint /v1/completions \
    --dataset-name random \
    --random-input-len "${RANDOM_INPUT_LEN}" \
    --random-output-len "${RANDOM_OUTPUT_LEN}" \
    --random-range-ratio "${RANDOM_RANGE_RATIO}" \
    --num-prompts "${NUM_PROMPTS}" \
    --request-rate "${REQUEST_RATE}" \
    --ignore-eos \
    --save-result \
    --result-dir "${RESULT_DIR}" \
    --result-filename "${RESULT_FILENAME}"

echo "SUCCESS: benchmark requests completed through ${PROXY_ENDPOINT}."
