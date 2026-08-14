#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /workspace/xPyD-proxy
exec xpyd proxy -c "${SCRIPT_DIR}/xpyd_2p2d.yaml"
