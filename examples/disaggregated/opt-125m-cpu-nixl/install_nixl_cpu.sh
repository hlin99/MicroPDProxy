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
        liburing-dev \
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

# Ubuntu 22.04 provides patchelf 0.14.3, while current auditwheel requires
# at least 0.14.5. The venv binary takes precedence over the apt package.
python -m pip install "patchelf>=0.14.5"

# The upstream installer uses the Git tag in its wheel filename glob. NIXL
# tags carry a leading "v", while Python wheel versions do not.
sed -i 's/f"nixl\*{NIXL_VERSION}\*\.whl"/"nixl*.whl"/' "${installer}"
# Build only the transport used by this example. The default plugin set also
# builds POSIX support and leaves auditwheel with an unavailable liburing.so.2.
sed -i \
    '/f"--wheel-dir={temp_wheel_dir}",/a\            "--config-settings=setup-args=-Denable_plugins=UCX",' \
    "${installer}"

python - "${installer}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
content = path.read_text()
content = content.replace(
    "import subprocess\n",
    "import subprocess\nimport shutil\nimport tempfile\nimport zipfile\n",
    1,
)
content = content.replace(
    "    auditwheel_command = [\n",
    """    wheel_extract_dir = tempfile.mkdtemp(prefix="nixl-wheel-")
    with zipfile.ZipFile(unrepaired_wheel) as wheel:
        wheel.extractall(wheel_extract_dir)
    internal_libraries = glob.glob(
        os.path.join(
            wheel_extract_dir,
            ".*.mesonpy.libs",
            "**",
            "*.so*",
        ),
        recursive=True,
    )
    internal_lib_dirs = sorted({
        os.path.dirname(library)
        for library in internal_libraries
    })
    if not internal_lib_dirs:
        raise RuntimeError("NIXL wheel did not contain internal shared libraries")
    for library in internal_libraries:
        soname = subprocess.check_output(
            ["patchelf", "--print-soname", library],
            text=True,
        ).strip()
        soname_path = os.path.join(os.path.dirname(library), soname)
        if soname and not os.path.exists(soname_path):
            os.symlink(os.path.basename(library), soname_path)
    build_env["LD_LIBRARY_PATH"] = ":".join(
        internal_lib_dirs + [build_env.get("LD_LIBRARY_PATH", "")]
    ).strip(":")

    auditwheel_command = [
""",
    1,
)
content = content.replace(
    "    run_command(auditwheel_command, env=build_env)\n",
    """    run_command(auditwheel_command, env=build_env)
    shutil.rmtree(wheel_extract_dir)
""",
    1,
)
path.write_text(content)
PY

NIXL_VERSION="${NIXL_VERSION}" python "${installer}"
platform_version="$(
    python -c 'import importlib.metadata as m; print(m.version("nixl-cu12"))'
)"
python -m pip install --no-deps "nixl==${platform_version}"
UCX_NET_DEVICES=all UCX_TLS=tcp python - <<'PY'
import nixl

agent = nixl.nixl_agent("xpyd-cpu-check")
assert agent is not None
print("NIXL CPU/UCX initialization passed.")
PY
