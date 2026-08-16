#!/usr/bin/env bash

set -euo pipefail

NIXL_VERSION="${NIXL_VERSION:-v1.3.0}"
VLLM_VERSION="${VLLM_VERSION:-0.25.0}"
export WHEELS_CACHE_HOME="${WHEELS_CACHE_HOME:-${HOME}/.cache/xpyd-nixl-wheels}"

mkdir -p "${WHEELS_CACHE_HOME}"

if ! compgen -G "${WHEELS_CACHE_HOME}/nixl*.whl" >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        automake \
        autotools-dev \
        build-essential \
        cmake \
        libtool \
        libtool-bin \
        meson \
        ninja-build \
        patchelf \
        pkg-config
fi

installer="$(mktemp)"
trap 'rm -f "${installer}"' EXIT

curl --fail --location --retry 3 \
    "https://raw.githubusercontent.com/vllm-project/vllm/v${VLLM_VERSION}/tools/install_nixl_from_source_ubuntu.py" \
    --output "${installer}"

# The upstream installer uses the Git tag in its wheel filename glob. NIXL
# tags carry a leading "v", while Python wheel versions do not.
sed -i 's/f"nixl\*{NIXL_VERSION}\*\.whl"/"nixl*.whl"/' "${installer}"
NIXL_VERSION="${NIXL_VERSION}" python "${installer}"
python - <<'PY'
import nixl

agent = nixl.nixl_agent("xpyd-cpu-check")
assert agent is not None
print("NIXL CPU/UCX initialization passed.")
PY
