#!/usr/bin/env bash

set -euo pipefail

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

python - <<'PY'
from importlib.metadata import version
import subprocess

actual = subprocess.check_output(["xpyd", "--version"], text=True).strip()
assert actual == f"xpyd {version('xpyd-proxy')}", actual
PY

mkdir "${tmpdir}/default"
(
    cd "${tmpdir}/default"
    printf 'n\n' | xpyd
    xpyd --validate-config xpyd.yaml
)

printf 'n\n' | xpyd --init-config "${tmpdir}/generated/config.yaml"
before="$(sha256sum "${tmpdir}/generated/config.yaml")"
if printf 'n\n' | xpyd --init-config "${tmpdir}/generated/config.yaml"; then
    echo "Expected --init-config to refuse an existing file" >&2
    exit 1
fi
[[ "$(sha256sum "${tmpdir}/generated/config.yaml")" == "${before}" ]]
printf 'n\n' | xpyd --init-config "${tmpdir}/generated/config.yaml" --force
xpyd proxy --validate-config "${tmpdir}/generated/config.yaml"

cat >"${tmpdir}/invalid.yaml" <<'YAML'
model: demo
decode:
  - invalid-address
YAML
if xpyd --validate-config "${tmpdir}/invalid.yaml"; then
    echo "Expected invalid config validation to fail" >&2
    exit 1
fi
if xpyd --validate-config "${tmpdir}/missing.yaml"; then
    echo "Expected missing config validation to fail" >&2
    exit 1
fi

for args in \
    "--port 0" \
    "--port 65536" \
    "--port not-a-number" \
    "--log-level trace" \
    "--disaggregated-mode invalid" \
    "--first-token-source invalid"; do
    if xpyd proxy ${args} --config "${tmpdir}/generated/config.yaml"; then
        echo "Expected invalid arguments to fail: ${args}" >&2
        exit 1
    fi
done

if xpyd --force --config "${tmpdir}/generated/config.yaml"; then
    echo "Expected --force without --init-config to fail" >&2
    exit 1
fi
if xpyd --config "${tmpdir}/missing.yaml"; then
    echo "Expected a missing startup config to fail" >&2
    exit 1
fi

cat >"${tmpdir}/fixable.yaml" <<'YAML'
model: " demo "
decode:
  - 127.0.0.1
scheduling: round_robbin
YAML
xpyd fix-config "${tmpdir}/fixable.yaml" --write
xpyd --validate-config "${tmpdir}/fixable.yaml"
test "$(find "${tmpdir}" -name '*.bak' -type f | wc -l)" -eq 1
