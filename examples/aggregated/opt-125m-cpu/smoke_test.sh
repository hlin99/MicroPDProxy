#!/usr/bin/env bash

set -euo pipefail

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"

response="$(
    curl --fail --silent --show-error \
        "${PROXY_ENDPOINT}/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "facebook/opt-125m",
            "prompt": "The proxy smoke test says",
            "max_tokens": 4,
            "temperature": 0
        }'
)"

python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["choices"][0]["text"], "empty completion"
assert output["usage"]["completion_tokens"] == 4, output["usage"]
' <<<"${response}"

echo "OPT-125M aggregated CPU inference passed."
