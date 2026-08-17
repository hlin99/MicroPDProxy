#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
BACKEND_LOG="${SCRIPT_DIR}/pd_servers.log"
PARTS_DIR="${SCRIPT_DIR}/bench_results/matrix_parts"
STATUS=0
SCHEDULERS=(roundrobin loadbalanced consistent_hash power_of_two cache_aware)

cleanup() {
    if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill "${BACKEND_PID}"
        wait "${BACKEND_PID}" 2>/dev/null || true
    fi
    BACKEND_PID=""
}

wait_for_health() {
    local port=$1 deadline=$((SECONDS + 1200))
    until curl --silent --fail --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null; do
        if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
            echo "ERROR: backend process exited before port ${port} became healthy." >&2
            return 1
        fi
        (( SECONDS < deadline )) || { echo "ERROR: timed out waiting for port ${port}." >&2; return 1; }
        sleep 2
    done
}

resources_are_free() {
    python3 - <<'PY'
import socket

ports = [
    *range(8100, 8108),
    *range(8200, 8208),
    *range(7300, 7308),
    *range(7400, 7408),
]
for port in ports:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
    finally:
        sock.close()
PY
}

stop_backend() {
    cleanup
    local deadline=$((SECONDS + 180))
    until resources_are_free &&
            [[ -z "$(nvidia-smi --query-compute-apps=pid \
                --format=csv,noheader,nounits | sed '/^[[:space:]]*$/d')" ]]; do
        if ((SECONDS >= deadline)); then
            echo "ERROR: backend resources were not released within 180 seconds." >&2
            return 1
        fi
        sleep 2
    done
}

start_backend() {
    local label=$1
    {
        echo
        echo "=== ${label} ==="
    } >>"${BACKEND_LOG}"
    bash "${SCRIPT_DIR}/vllm_disaggregated_server.sh" >>"${BACKEND_LOG}" 2>&1 &
    BACKEND_PID=$!
    for port in {8100..8107} {8200..8207}; do
        wait_for_health "${port}" || return 1
    done
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

mkdir -p "${PARTS_DIR}"
: >"${BACKEND_LOG}"
rm -f "${PARTS_DIR}"/*.json

for api in completion chat; do
    for scheduler in "${SCHEDULERS[@]}"; do
        label="decode/${api}/${scheduler}"
        if ! start_backend "${label}"; then
            STATUS=1
            stop_backend || true
            continue
        fi
        if ! bash "${SCRIPT_DIR}/run_matrix.sh" "$@" \
                --api "${api}" --scheduler "${scheduler}"; then
            STATUS=1
        fi
        cp "${SCRIPT_DIR}/matrix_summary.json" \
            "${PARTS_DIR}/${api}-${scheduler}.json"
        stop_backend || STATUS=1
    done
done

python3 - "${SCRIPT_DIR}/matrix_summary.json" "${PARTS_DIR}"/*.json <<'PY'
import json
import sys
from pathlib import Path

output = Path(sys.argv[1])
parts = [json.loads(Path(path).read_text()) for path in sys.argv[2:]]
summary = {
    "transport": "zmq",
    "requests_per_combination": parts[0]["requests_per_combination"],
    "combinations": sum(part["combinations"] for part in parts),
    "total_requests": sum(part["total_requests"] for part in parts),
    "failures": [
        failure
        for part in parts
        for failure in part["failures"]
    ],
}
output.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY

exit "${STATUS}"
