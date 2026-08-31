#!/usr/bin/env bash
# Validate every proxy configuration shipped in the repository.
#
# Backend-side files (vLLM/LMCache receiver configs under examples/**/configs/)
# are not proxy configurations and are intentionally excluded.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

mapfile -t CONFIGS < <(
    {
        find examples -name 'xpyd*.yaml'
        find examples -path '*/proxy_configs/*' -name '*.yaml'
        ls examples/proxy.yaml examples/proxy-simple.yaml xpyd.yaml 2>/dev/null
    } | sort -u
)

if ((${#CONFIGS[@]} == 0)); then
    echo "ERROR: no example configurations found." >&2
    exit 1
fi

failed=0
for config in "${CONFIGS[@]}"; do
    if xpyd --validate-config "${config}" >/dev/null 2>&1; then
        echo "ok    ${config}"
    else
        echo "FAIL  ${config}" >&2
        xpyd --validate-config "${config}" >&2 || true
        failed=1
    fi
done

if ((failed)); then
    echo "ERROR: one or more example configurations are invalid." >&2
    exit 1
fi

echo "All ${#CONFIGS[@]} example configurations validated."
