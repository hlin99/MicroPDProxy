#!/usr/bin/env bash

set -euo pipefail

for model in aggregated-model disaggregated-model; do
    response=$(
        curl --fail --silent --show-error \
            http://127.0.0.1:8868/v1/completions \
            -H "Content-Type: application/json" \
            -d "{
                \"model\": \"${model}\",
                \"prompt\": \"Reply with the word smoke.\",
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
    echo "${model} smoke test passed."
done
