#!/usr/bin/env bash

set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/tmp/opt-125m}"
MODEL_URL="${MODEL_URL:-https://github.com/LMCache/opt-125m/releases/download/v1.0/opt-125m.tar.gz}"

configure_chat_template() {
    python - "${MODEL_DIR}/tokenizer_config.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
config = json.loads(path.read_text())
config["chat_template"] = (
    "{% for message in messages %}"
    "{{'<|im_start|>' + message['role'] + '\\n' + message['content']}}"
    "{% if (loop.last and add_generation_prompt) or not loop.last %}"
    "{{ '<|im_end|>' + '\\n'}}"
    "{% endif %}"
    "{% endfor %}"
    "{% if add_generation_prompt and messages[-1]['role'] != 'assistant' %}"
    "{{ '<|im_start|>assistant\\n' }}"
    "{% endif %}"
)
path.write_text(json.dumps(config, indent=2) + "\n")
PY
}

if [[ -f "${MODEL_DIR}/pytorch_model.bin" ]]; then
    configure_chat_template
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
configure_chat_template
echo "Downloaded OPT-125M to ${MODEL_DIR}."
