#!/usr/bin/env bash
# Shared proxy API assertions used by the CPU example smoke tests.
#
# Source this file and call the smoke_* functions. It only depends on
# PROXY_ENDPOINT and MODEL, so it works unchanged for aggregated and
# disaggregated topologies of any size, including phases where some nodes are
# deliberately offline.
#
#   PROXY_ENDPOINT  proxy base URL, defaults to http://127.0.0.1:8868
#   MODEL           served model name
#   ADMIN_API_KEY   optional; when set the admin assertions expect 403 for a
#                   wrong key instead of the 500 an unconfigured proxy returns

PROXY_ENDPOINT="${PROXY_ENDPOINT:-http://127.0.0.1:8868}"
MODEL="${MODEL:-facebook/opt-125m}"

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
# regression these checks exist for. OPT-125M is a generative model, so the
# pooling and scoring families legitimately answer 4xx from vLLM.
assert_forwarded() {
    local label=$1 actual=$2
    (( actual >= 200 && actual < 500 )) || {
        echo "ERROR: ${label} was not forwarded, proxy returned ${actual}." >&2
        return 1
    }
    echo "  ${label} forwarded (HTTP ${actual})"
}

smoke_informational_endpoints() {
    echo "=== Informational endpoints ==="

    local verb ping version status instances
    for verb in GET POST; do
        ping="$(
            curl --fail --silent --show-error --request "${verb}" \
                "${PROXY_ENDPOINT}/ping"
        )"
        python -c '
import json
import sys

output = json.load(sys.stdin)
assert output, "ping returned no instances"
assert any(entry.get("status") == 200 for entry in output.values()), output
' <<<"${ping}"
        echo "  ${verb} /ping ok"
    done

    version="$(
        curl --fail --silent --show-error "${PROXY_ENDPOINT}/version"
    )"
    python -c '
import json
import sys

output = json.load(sys.stdin)
assert len(output) == 1, output
entry = next(iter(output.values()))
assert entry["status"] == 200, output
assert entry["data"]["version"], output
' <<<"${version}"
    echo "  /version ok"

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
    echo "  /status ok"

    instances="$(
        curl --fail --silent --show-error "${PROXY_ENDPOINT}/status/instances"
    )"
    python -c '
import json
import sys

output = json.load(sys.stdin)
known = [
    instance
    for key in ("prefill_instances", "decode_instances", "aggregated_instances")
    for instance in output.get(key, [])
]
assert known, output
assert any(instance["status"] == "healthy" for instance in known), output
for instance in known:
    assert instance["circuit"] in {"closed", "open", "half_open"}, instance
    assert instance["active_requests"] >= 0, instance
' <<<"${instances}"
    echo "  /status/instances ok"
}

smoke_passthrough_endpoints() {
    echo "=== Passthrough endpoints ==="

    local tokenized tokens detokenized path
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
}

smoke_passthrough_validation() {
    echo "=== Passthrough request validation ==="

    # The proxy rejects an incomplete body itself, before contacting a backend.
    local path
    for path in /tokenize /detokenize /v1/embeddings /pooling /score /v1/score \
        /rerank /v1/rerank /v2/rerank /invocations; do
        assert_status "${path} with missing fields" 400 \
            "$(post_status "${path}" '{}')"
        assert_status "OPTIONS ${path}" 200 "$(
            curl --silent --output /dev/null --write-out "%{http_code}" \
                --request OPTIONS "${PROXY_ENDPOINT}${path}"
        )"
    done
    echo "  all 10 passthrough endpoints validate their body and answer OPTIONS"
}

admin_post() {
    curl --silent --output /dev/null --write-out "%{http_code}" \
        "${PROXY_ENDPOINT}/instances/add" \
        -H "Content-Type: application/json" \
        -H "x-api-key: $1" \
        -d "$2"
}

smoke_admin_endpoint() {
    echo "=== Admin endpoint ==="

    local before after
    before="$(curl --fail --silent --show-error "${PROXY_ENDPOINT}/status")"

    assert_status "/instances/add without API key" 422 "$(
        post_status /instances/add \
            "{\"type\": \"prefill\", \"instance\": \"127.0.0.1:9100\"}"
    )"

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
    after="$(curl --fail --silent --show-error "${PROXY_ENDPOINT}/status")"
    [[ "${after}" == "${before}" ]] || {
        echo "ERROR: a rejected admin call changed the instance pools." >&2
        echo "before: ${before}" >&2
        echo "after:  ${after}" >&2
        return 1
    }
    echo "  rejected admin calls left the instance pools untouched"
}

smoke_all_endpoints() {
    smoke_informational_endpoints
    smoke_passthrough_endpoints
    smoke_passthrough_validation
    smoke_admin_endpoint
}
