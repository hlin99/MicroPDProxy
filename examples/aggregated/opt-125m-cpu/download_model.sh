#!/usr/bin/env bash

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/tmp/opt-125m}"
MODEL_URL="${MODEL_URL:-https://github.com/LMCache/opt-125m/releases/download/v1.0/opt-125m.tar.gz}"

if [[ -f "${MODEL_DIR}/pytorch_model.bin" ]]; then
    echo "OPT-125M already available at ${MODEL_DIR}."
    exit 0
fi

archive="$(mktemp)"
extract_dir="$(mktemp -d)"
cleanup() {
    rm -f "${archive}"
    rm -rf "${extract_dir}"
}
trap cleanup EXIT

curl --fail --location --retry 3 --output "${archive}" "${MODEL_URL}"
tar -xzf "${archive}" -C "${extract_dir}"

top_dir="$(
    tar -tzf "${archive}" |
        awk -F/ 'NF > 1 {print $1}' |
        sort -u
)"
if [[ -z "${top_dir}" ]] || [[ "${top_dir}" == *$'\n'* ]]; then
    echo "ERROR: model archive must contain exactly one top-level directory." >&2
    exit 1
fi

mkdir -p "${MODEL_DIR}"
cp -a "${extract_dir}/${top_dir}/." "${MODEL_DIR}/"
test -f "${MODEL_DIR}/pytorch_model.bin"
echo "Downloaded OPT-125M to ${MODEL_DIR}."
