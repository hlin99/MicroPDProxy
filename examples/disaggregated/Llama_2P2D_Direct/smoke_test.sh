#!/usr/bin/env bash

set -euo pipefail

SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-/workspace/Meta-Llama-3-8B-Instruct/}"

for request in 1 2 3 4; do
    response=$(
        curl --fail --silent --show-error \
            http://127.0.0.1:8868/v1/completions \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"${SERVED_MODEL_NAME}\",
                \"prompt\": \"Reply with the word smoke for request ${request}.\",
                \"max_tokens\": 4,
                \"temperature\": 0
            }"
    )
    python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["choices"][0]["text"], "empty completion"
assert output["usage"]["completion_tokens"] == 4, output["usage"]
' <<<"${response}"
done

echo "Direct 2P2D smoke test passed: 4/4 requests."
