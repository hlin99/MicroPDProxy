#!/usr/bin/env bash

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
BACKEND_LOG="${SCRIPT_DIR}/pd_servers.log"
STATUS=0

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

: >"${BACKEND_LOG}"

if start_backend "decode/matrix"; then
    if ! bash "${SCRIPT_DIR}/run_matrix.sh" "$@"; then
        STATUS=1
    fi
else
    STATUS=1
fi
stop_backend || STATUS=1

exit "${STATUS}"
