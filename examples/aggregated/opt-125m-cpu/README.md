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
auto-detects the served model from the backend, and then exercises **every proxy
endpoint** against the real backend: completion, chat, streaming, the ten
passthrough endpoints (`/tokenize`, `/detokenize`, `/v1/embeddings`, `/pooling`,
`/score`, `/v1/score`, `/rerank`, `/v1/rerank`, `/v2/rerank`, `/invocations`),
their request validation and CORS preflight, the admin API rejection paths, and
`/health`, `/ping`, `/version`, `/status`, `/status/instances`, `/v1/models` and
`/metrics`. It validates node loss — where inference, the passthrough endpoints
and `/health` must all answer 503 — and confirms reconnection. It then uses an
isolated Hugging Face cache to verify a real automatic tokenizer download,
restarts with another empty cache in offline mode, and confirms inference
continues after the tokenizer load warning and round-robin fallback. Runtime
output is stored in the ignored `logs/` directory.

OPT-125M is a generative model, so the pooling and scoring families are answered
with a 4xx by vLLM itself. The smoke test asserts those requests are *forwarded*
(any non-5xx status) rather than asserting a specific payload, which is what
catches a proxy that fails to select a backend.

`run_all.sh` exports a throwaway `ADMIN_API_KEY` so the admin endpoint can be
exercised; the proxy only listens on loopback for the duration of the check.

The endpoint assertions live in `../../lib/proxy_api_smoke.sh` so the
disaggregated NIXL example checks the same API surface. They are written to be
topology agnostic, which lets the shared checks also run while part of the
deployment is offline. The lifecycle finishes by adding a healthy backend
alias through `/instances/add` and verifying the new role count and member,
covering the admin endpoint's successful mutation path without affecting later
traffic. It then drains and removes the aggregated backend through
`/instances/remove`, verifies it disappears from `/status/instances`, and
checks that subsequent inference returns 503.
