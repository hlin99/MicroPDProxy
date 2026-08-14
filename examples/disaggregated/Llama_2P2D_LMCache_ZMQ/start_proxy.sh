#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec xpyd proxy \
    --config "${SCRIPT_DIR}/xpyd_2p2d.yaml" \
    --disaggregated-mode zmq
