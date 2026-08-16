# OPT-125M aggregated CPU example

This example follows LMCache's GitHub CPU CI setup: it installs a pinned,
prebuilt `vllm-cpu-nightly`, adds the distribution metadata alias required to
activate vLLM's CPU plugin, and downloads OPT-125M from LMCache's GitHub
Release instead of Hugging Face.

Run the complete lifecycle check with:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
./install_vllm_cpu.sh
./download_model.sh
./run_all.sh
```

The check starts xPyD before vLLM, verifies offline inference returns HTTP 503,
auto-detects the served model from the backend, exercises completion, chat,
streaming, health, models, and metrics APIs, validates node loss, and confirms
reconnection. Runtime output is stored in the ignored `logs/` directory.
