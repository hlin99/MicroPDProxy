#!/usr/bin/env bash

set -euo pipefail

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
MODEL="facebook/opt-125m"

completion="$(
    curl --fail-with-body --silent --show-error \
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
assert output["object"] == "text_completion", output
assert output["model"] == "facebook/opt-125m", output
assert isinstance(output["id"], str) and output["id"], output
assert isinstance(output["created"], int), output
assert len(output["choices"]) == 1, output
assert output["choices"][0]["index"] == 0, output
assert output["choices"][0]["text"], "empty completion"
assert output["choices"][0]["finish_reason"] == "length", output
assert output["usage"]["completion_tokens"] == 4, output["usage"]
' <<<"${completion}"

chat_result="$(
    curl --silent --show-error --write-out $'\n%{http_code}' \
        "${PROXY_ENDPOINT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"${MODEL}\",
            \"messages\": [{\"role\": \"user\", \"content\": \"Say hello\"}],
            \"max_tokens\": 4,
            \"temperature\": 0
        }"
)"
chat="${chat_result%$'\n'*}"
chat_status="${chat_result##*$'\n'}"
if [[ "${chat_status}" != "200" ]]; then
    echo "ERROR: chat completion returned HTTP ${chat_status}: ${chat}" >&2
    exit 1
fi

python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["object"] == "chat.completion", output
assert output["model"] == "facebook/opt-125m", output
assert isinstance(output["id"], str) and output["id"], output
assert isinstance(output["created"], int), output
assert len(output["choices"]) == 1, output
choice = output["choices"][0]
assert choice["index"] == 0, output
assert choice["message"]["role"] == "assistant", output
assert choice["message"]["content"], output
assert choice["finish_reason"] == "length", output
assert output["usage"]["completion_tokens"] == 4, output["usage"]
' <<<"${chat}"

stream="$(
    curl --fail --silent --show-error --no-buffer \
        "${PROXY_ENDPOINT}/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "facebook/opt-125m",
            "prompt": "The streaming proxy test says",
            "max_tokens": 4,
            "temperature": 0,
            "stream": true,
            "stream_options": {"include_usage": true}
        }'
)"

python -c '
import json
import sys

events = [
    line.removeprefix("data: ")
    for line in sys.stdin.read().splitlines()
    if line.startswith("data: ")
]
assert events and events[-1] == "[DONE]", events
chunks = [json.loads(event) for event in events[:-1]]
assert chunks, events
assert all(chunk["object"] == "text_completion" for chunk in chunks), chunks
assert all(chunk["model"] == "facebook/opt-125m" for chunk in chunks), chunks
assert "".join(
    choice["text"]
    for chunk in chunks
    for choice in chunk["choices"]
), chunks
usage_chunks = [chunk["usage"] for chunk in chunks if chunk.get("usage")]
assert usage_chunks[-1]["completion_tokens"] == 4, chunks
' <<<"${stream}"

health="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/health"
)"
python -c '
import json
import sys

output = json.load(sys.stdin)
backend = output["127.0.0.1:8000"]
assert backend["status"] == 200, output
assert backend["type"] == "text", output
' <<<"${health}"

models="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/v1/models"
)"
python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["object"] == "list", output
assert [model["id"] for model in output["data"]] == [
    "facebook/opt-125m"
], output
' <<<"${models}"

unsupported_media_status="$(
    curl --silent --output /dev/null --write-out "%{http_code}" \
        "${PROXY_ENDPOINT}/v1/completions" \
        -H "Content-Type: text/plain" \
        -d "not json"
)"
[[ "${unsupported_media_status}" == "415" ]]

unknown_model_status="$(
    curl --silent --output /dev/null --write-out "%{http_code}" \
        "${PROXY_ENDPOINT}/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "unknown-model",
            "prompt": "This must not be routed",
            "max_tokens": 1
        }'
)"
[[ "${unknown_model_status}" == "404" ]]

metrics="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/metrics"
)"
grep -q 'proxy_requests_total{endpoint="/v1/completions"}' <<<"${metrics}"
grep -q 'proxy_requests_total{endpoint="/v1/chat/completions"}' <<<"${metrics}"
grep -q "proxy_request_duration_seconds" <<<"${metrics}"
grep -q "proxy_active_requests 0.0" <<<"${metrics}"

echo "OPT-125M aggregated CPU API smoke tests passed."
