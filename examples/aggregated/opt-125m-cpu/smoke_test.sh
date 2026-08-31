#!/usr/bin/env bash

set -euo pipefail

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
MODEL="facebook/opt-125m"
BACKEND="${BACKEND:-127.0.0.1:8000}"

# Status of a JSON POST, discarding the body.
post_status() {
    curl --silent --output /dev/null --write-out "%{http_code}" \
        "${PROXY_ENDPOINT}$1" \
        -H "Content-Type: application/json" \
        -d "$2"
}

assert_status() {
    local label=$1 expected=$2 actual=$3
    [[ "${actual}" == "${expected}" ]] || {
        echo "ERROR: ${label} expected HTTP ${expected}, got ${actual}." >&2
        return 1
    }
}

# A passthrough endpoint must reach a backend. Any 5xx means the proxy itself
# failed to route (no instance selected, unhandled exception, ...), which is the
# regression this check exists for. OPT-125M is a generative model, so the
# pooling/scoring families legitimately answer 4xx from vLLM.
assert_forwarded() {
    local label=$1 actual=$2
    (( actual >= 200 && actual < 500 )) || {
        echo "ERROR: ${label} was not forwarded, proxy returned ${actual}." >&2
        return 1
    }
    echo "  ${label} forwarded (HTTP ${actual})"
}

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

echo "=== Informational endpoints ==="

for verb in GET POST; do
    ping="$(
        curl --fail --silent --show-error --request "${verb}" \
            "${PROXY_ENDPOINT}/ping"
    )"
    BACKEND="${BACKEND}" python -c '
import json
import os
import sys

output = json.load(sys.stdin)
backend = output[os.environ["BACKEND"]]
assert backend["status"] == 200, output
' <<<"${ping}"
    echo "  ${verb} /ping ok"
done

version="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/version"
)"
BACKEND="${BACKEND}" python -c '
import json
import os
import sys

output = json.load(sys.stdin)
backend = output[os.environ["BACKEND"]]
assert backend["status"] == 200, output
assert backend["data"]["version"], output
' <<<"${version}"

status="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/status"
)"
python -c '
import json
import sys

output = json.load(sys.stdin)
assert set(output) == {
    "prefill_node_count",
    "decode_node_count",
    "prefill_nodes",
    "decode_nodes",
}, output
assert output["prefill_node_count"] == len(output["prefill_nodes"]), output
assert output["decode_node_count"] == len(output["decode_nodes"]), output
' <<<"${status}"

instances="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/status/instances"
)"
BACKEND="${BACKEND}" python -c '
import json
import os
import sys

output = json.load(sys.stdin)
instances = output["aggregated_instances"]
assert len(instances) == 1, output
assert instances[0]["address"] == os.environ["BACKEND"], output
assert instances[0]["status"] == "healthy", output
' <<<"${instances}"

echo "=== Passthrough endpoints ==="

tokenized="$(
    curl --fail-with-body --silent --show-error \
        "${PROXY_ENDPOINT}/tokenize" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"${MODEL}\", \"prompt\": \"Hello proxy\"}"
)"
tokens="$(
    python -c '
import json
import sys

output = json.load(sys.stdin)
assert output["count"] > 0, output
assert len(output["tokens"]) == output["count"], output
print(json.dumps(output["tokens"]))
' <<<"${tokenized}"
)"
echo "  /tokenize ok (${tokens})"

detokenized="$(
    curl --fail-with-body --silent --show-error \
        "${PROXY_ENDPOINT}/detokenize" \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"${MODEL}\", \"tokens\": ${tokens}}"
)"
python -c '
import json
import sys

output = json.load(sys.stdin)
assert "Hello proxy" in output["prompt"], output
' <<<"${detokenized}"
echo "  /detokenize ok"

assert_forwarded "/v1/embeddings" "$(
    post_status /v1/embeddings \
        "{\"model\": \"${MODEL}\", \"input\": \"Hello proxy\"}"
)"
assert_forwarded "/pooling" "$(
    post_status /pooling \
        "{\"model\": \"${MODEL}\", \"messages\": \"Hello proxy\"}"
)"
for path in /score /v1/score; do
    assert_forwarded "${path}" "$(
        post_status "${path}" \
            "{\"model\": \"${MODEL}\", \"text_1\": \"a\", \"text_2\": \"b\", \"predictions\": \"\"}"
    )"
done
for path in /rerank /v1/rerank /v2/rerank; do
    assert_forwarded "${path}" "$(
        post_status "${path}" \
            "{\"model\": \"${MODEL}\", \"query\": \"a\", \"documents\": [\"b\"]}"
    )"
done
assert_forwarded "/invocations" "$(
    post_status /invocations \
        "{\"model\": \"${MODEL}\", \"prompt\": \"Hello proxy\", \"max_tokens\": 1}"
)"

echo "=== Passthrough request validation ==="

# The proxy rejects an incomplete body itself, before contacting a backend.
while read -r path body; do
    [[ -n "${path}" ]] || continue
    assert_status "${path} with missing fields" 400 "$(post_status "${path}" "${body}")"
    assert_status "OPTIONS ${path}" 200 "$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            --request OPTIONS "${PROXY_ENDPOINT}${path}"
    )"
done <<EOF
/tokenize {}
/detokenize {}
/v1/embeddings {}
/pooling {}
/score {}
/v1/score {}
/rerank {}
/v1/rerank {}
/v2/rerank {}
/invocations {}
EOF

echo "=== Admin endpoint ==="

assert_status "/instances/add without API key" 422 "$(
    post_status /instances/add \
        "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:9100\"}"
)"

admin_post() {
    curl --silent --output /dev/null --write-out "%{http_code}" \
        "${PROXY_ENDPOINT}/instances/add" \
        -H "Content-Type: application/json" \
        -H "x-api-key: $1" \
        -d "$2"
}

if [[ -n "${ADMIN_API_KEY:-}" ]]; then
    assert_status "/instances/add with a wrong API key" 403 "$(
        admin_post "definitely-wrong" \
            "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:9100\"}"
    )"
    assert_status "/instances/add with an invalid role" 400 "$(
        admin_post "${ADMIN_API_KEY}" \
            "{\"type\": \"aggregated\", \"instance\": \"127.0.0.1:9100\"}"
    )"
    assert_status "/instances/add with an invalid address" 400 "$(
        admin_post "${ADMIN_API_KEY}" \
            "{\"type\": \"prefill\", \"instance\": \"not-an-ip:9100\"}"
    )"
    assert_status "/instances/add with an out-of-range port" 400 "$(
        admin_post "${ADMIN_API_KEY}" \
            "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:70000\"}"
    )"
    assert_status "/instances/add for an unreachable instance" 400 "$(
        admin_post "${ADMIN_API_KEY}" \
            "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:9100\"}"
    )"
else
    assert_status "/instances/add without ADMIN_API_KEY configured" 500 "$(
        admin_post "any-key" \
            "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:9100\"}"
    )"
fi

# None of the admin calls above may mutate the instance pools.
status_after="$(
    curl --fail --silent --show-error "${PROXY_ENDPOINT}/status"
)"
[[ "${status_after}" == "${status}" ]] || {
    echo "ERROR: a rejected admin call changed the instance pools." >&2
    echo "before: ${status}" >&2
    echo "after:  ${status_after}" >&2
    exit 1
}

echo "OPT-125M aggregated CPU API smoke tests passed."
