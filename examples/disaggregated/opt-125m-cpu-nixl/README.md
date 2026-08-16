# OPT-125M disaggregated CPU/NIXL TCP example

This example runs one prefill and one decode vLLM instance on the same Linux
host. Both instances serve `facebook/opt-125m` on CPU, while NIXL transfers KV
cache data through UCX over TCP. It is the smallest real 1P1D
counterpart to the aggregated OPT-125M CPU example.

Standard GitHub-hosted Linux runners do not provide GPUs. NIXL therefore must
be built with UCX from source instead of using its CUDA-oriented PyPI quick
install. The workflow caches the resulting wheel and caps each vLLM process at
512 MiB of KV cache. A self-hosted GPU runner remains the recommended target
for performance testing; this CPU scenario validates behavior only.

Run it on Ubuntu 22.04 with:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
../../aggregated/opt-125m-cpu/install_vllm_cpu.sh
./install_nixl_cpu.sh
../../aggregated/opt-125m-cpu/download_model.sh
./run_all.sh
```

The lifecycle starts xPyD before either backend, checks HTTP 503 while the
topology is incomplete, discovers both nodes, performs NIXL TCP inference,
then validates prefill and decode loss and reconnection independently.
`/status/instances` and the concise disaggregated heartbeat are checked.
Runtime output is stored in the ignored `logs/` directory.
