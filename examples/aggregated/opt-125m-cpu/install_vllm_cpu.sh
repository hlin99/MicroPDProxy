#!/usr/bin/env bash

set -euo pipefail

VLLM_CPU_NIGHTLY_VERSION="${VLLM_CPU_NIGHTLY_VERSION:-0.25.2.dev202607190821}"

python -m pip install "numpy<2"
python -m pip install \
    "vllm-cpu-nightly==${VLLM_CPU_NIGHTLY_VERSION}" \
    "apache-tvm-ffi<0.1.13" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# vLLM's CPU plugin looks for a distribution named "vllm" whose version
# contains "cpu"; the nightly wheel ships only vllm-cpu-nightly metadata.
python - <<'PY'
import importlib.metadata as metadata
import pathlib
import shutil

distribution = metadata.distribution("vllm-cpu-nightly")
version = distribution.version
site_root = pathlib.Path(distribution.locate_file(""))
source_name = next(
    path.parts[0]
    for path in distribution.files or ()
    if path.parts and path.parts[0].endswith(".dist-info")
)
source = site_root / source_name
target = source.with_name(f"vllm-{version}+cpu.dist-info")
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target)

metadata_file = target / "METADATA"
content = metadata_file.read_text()
content = content.replace("Name: vllm-cpu-nightly", "Name: vllm", 1)
content = content.replace(f"Version: {version}", f"Version: {version}+cpu", 1)
metadata_file.write_text(content)

print("vLLM CPU alias:", metadata.version("vllm"))
PY

python -c "import torch, vllm; print('vllm:', vllm.__version__, 'torch:', torch.__version__)"
