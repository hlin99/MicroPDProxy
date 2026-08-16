#!/usr/bin/env bash

set -euo pipefail

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
REQUEST_COUNT="${REQUEST_COUNT:-1}"

for ((request_index = 1; request_index <= REQUEST_COUNT; request_index++)); do
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
done

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

METRICS="${metrics}" python - <<'PY'
import os
import re

expected_prefill = set(filter(None, os.getenv("EXPECTED_PREFILL_INSTANCES", "").split(",")))
expected_decode = set(filter(None, os.getenv("EXPECTED_DECODE_INSTANCES", "").split(",")))
if expected_prefill or expected_decode:
    selected_prefill = set()
    selected_decode = set()
    for line in os.environ["METRICS"].splitlines():
        if not line.startswith("proxy_prefill_requests_total{"):
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', line))
        if float(line.rsplit(" ", 1)[1]) > 0:
            selected_prefill.add(labels["prefill_instance"])
            selected_decode.add(labels["decode_instance"])
    assert expected_prefill <= selected_prefill, (expected_prefill, selected_prefill)
    assert expected_decode <= selected_decode, (expected_decode, selected_decode)
PY

echo "OPT-125M NIXL TCP ${TOPOLOGY_NAME:-1P1D} smoke test passed."
