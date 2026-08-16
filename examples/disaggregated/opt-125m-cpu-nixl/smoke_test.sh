#!/usr/bin/env bash

set -euo pipefail

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"

completion="$(
    curl --fail-with-body --silent --show-error \
        "${PROXY_ENDPOINT}/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "facebook/opt-125m",
            "prompt": "The disaggregated proxy test says",
            "max_tokens": 4,
            "temperature": 0
        }'
)"

python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["object"] == "text_completion", output
assert output["model"] == "facebook/opt-125m", output
assert output["choices"][0]["text"], output
assert output["choices"][0]["finish_reason"] == "length", output
assert output["usage"]["completion_tokens"] == 4, output["usage"]
' <<<"${completion}"

models="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/v1/models"
)"
python -c '
import json
import sys

output = json.load(sys.stdin)
assert [model["id"] for model in output["data"]] == [
    "facebook/opt-125m"
], output
' <<<"${models}"

metrics="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/metrics"
)"
grep -q 'proxy_prefill_requests_total{' <<<"${metrics}"
grep -q 'proxy_decode_requests_total{' <<<"${metrics}"

echo "OPT-125M NIXL TCP 1P1D smoke test passed."
