# xPyD-proxy

**Lightweight Prefill-Decode proxy for LLM serving.**

xPyD-proxy routes inference requests across aggregated and disaggregated backends with configurable scheduling, readiness gating, and Prometheus metrics.

## Key Features

- **Topology modes** — aggregated, disaggregated, and mixed model deployments (`examples/`)
- **Scheduling policies** — `loadbalanced`, `roundrobin`, `consistent_hash`, `power_of_two`, `cache_aware`
- **Resilience controls** — startup discovery/readiness (503 until ready), optional health monitor, optional circuit breaker
- **Multi-model routing** — model-aware instance registry via `instances:` or `models:` config
- **OpenAI-compatible endpoints** — `/v1/completions`, `/v1/chat/completions`, `/v1/models`
- **YAML-first operation** — config generation, validation, and startup from YAML

## Install

Python requirement: **3.10+** (`pyproject.toml`).

```bash
pip install xpyd-proxy
```

Console entrypoint (`pyproject.toml`):

```text
xpyd -> xpyd.proxy:main
```

Runtime dependencies are defined in `pyproject.toml` (project metadata) and `requirements.txt`.

## Quick Start

```bash
# Generate config (optional PATH; default is ./xpyd.yaml)
xpyd --init-config ./xpyd.yaml

# Validate config only
xpyd --validate-config ./xpyd.yaml

# Start proxy (default command is "proxy")
xpyd --config ./xpyd.yaml
# equivalent:
xpyd proxy --config ./xpyd.yaml
```

### CLI Surface (current)

| Command | Description |
|---|---|
| `xpyd [proxy]` | Start proxy (default subcommand) |
| `xpyd fix-config <config_path>` | Auto-fix common config mistakes |
| `xpyd --version` | Print CLI version |

`proxy` flags:

| Flag | Meaning |
|---|---|
| `--config, -c <FILE>` | YAML config path |
| `--validate-config <FILE>` | Validate config and exit |
| `--init-config [PATH]` | Generate config and exit (default path `./xpyd.yaml`) |
| `--port <INT>` | Override `port` from YAML |
| `--log-level <LEVEL>` | Override log level (`debug|info|warning|error`) |
| `--disaggregated-mode <MODE>` | Override mode (`direct|nixl|zmq`) |
| `--first-token-source <SRC>` | Override first token source (`prefill|decode`) |

Defaults from code:
- Listen host: `0.0.0.0`
- Port default: `8000`
- Log level default: `warning`
- Config resolution: `--config` > `XPYD_CONFIG` env > `./xpyd.yaml` (if present)

### Scheduling Policies

| Config value (`scheduling`) | Implementation |
|---|---|
| `loadbalanced` (default) | `xpyd/scheduler/load_balanced.py` |
| `roundrobin` | `xpyd/scheduler/round_robin.py` |
| `consistent_hash` | `xpyd/scheduler/consistent_hash.py` |
| `power_of_two` | `xpyd/scheduler/power_of_two.py` |
| `cache_aware` | `xpyd/scheduler/cache_aware.py` |

Notes:
- `round_robin` and `load_balanced` are accepted aliases in the policy registry.
- Strategy-specific YAML sections are supported for `consistent_hash`, `power_of_two`, and `cache_aware`.

## Configuration

Minimal example (derived from `examples/proxy-simple.yaml`):

```yaml
model: /path/to/model
port: 8868
prefill:
  - "PREFILL_HOST:8100"
decode:
  - "DECODE_HOST_1:8200"
  - "DECODE_HOST_2:8200"
scheduling: loadbalanced
```

See also:
- `examples/proxy.yaml` for a fuller topology-style config
- `docs/configuration.md` for field-by-field reference

## Deployment Modes / Docker & Monitoring

### Deployment modes in `examples/`

| Mode | Config knobs | Example path |
|---|---|---|
| Aggregated | `instances` (role `aggregated`) or `models[].aggregated` | `examples/aggregated/` |
| Disaggregated (direct) | `prefill` + `decode`, `disaggregated_mode: direct` | `examples/disaggregated/Llama_2P2D_Direct/` |
| Disaggregated (NIXL) | `prefill` + `decode`, `disaggregated_mode: nixl` | `examples/disaggregated/Llama_2P2D_NIXL/`, `examples/disaggregated/opt-125m-cpu-nixl/` |
| Disaggregated (LMCache/ZMQ) | `disaggregated_mode: zmq` + `zmq` receiver map | `examples/disaggregated/Llama_2P2D_LMCache_ZMQ/` |
| Mixed | Distinct logical models mapped via `models:` entries | `examples/mixed/llama-pd1x1-aggregated-tp1x2/` |

### Implemented endpoints

| Endpoint | Method(s) | Purpose |
|---|---|---|
| `/v1/completions` | `POST` | OpenAI-compatible completion |
| `/v1/chat/completions` | `POST` | OpenAI-compatible chat completion |
| `/v1/models` | `GET` | Model list from registry/backends |
| `/health` | `GET` | Backend health fan-out |
| `/ping` | `GET`, `POST` | Backend ping fan-out |
| `/metrics` | `GET` | Prometheus metrics |
| `/version` | `GET` | Backend version fan-out |
| `/status` | `GET` | Basic node status |
| `/status/instances` | `GET` | Per-instance health/circuit/load view |
| `/instances/add` | `POST` | Add backend instance (admin API key required) |
| `/tokenize`, `/detokenize` | `POST` | Forward tokenizer operations |
| `/v1/embeddings` | `POST` | Forward embeddings |
| `/pooling` | `POST` | Forward pooling |
| `/score`, `/v1/score` | `POST` | Forward scoring |
| `/rerank`, `/v1/rerank`, `/v2/rerank` | `POST` | Forward rerank |
| `/invocations` | `POST` | Forward invocations |

### Docker and monitoring assets

- Container build/runtime files: `Dockerfile`, `docker-compose.yml`
- Monitoring stack: `monitoring/` (Prometheus + Grafana via `monitoring/docker-compose.yml`)

## Part of xPyD

| Component | Description |
|-----------|-------------|
| **xpyd-proxy** | prefill/decode proxy |
| [xpyd-sim](https://github.com/xPyD-hub/xPyD-sim) | OpenAI-compatible inference simulator |
| [xpyd-bench](https://github.com/xPyD-hub/xPyD-bench) | Benchmarking & planning tool |

📖 **[CLI Guide →](docs/cli.md)** | ⚙️ **[Configuration →](docs/configuration.md)** | 💡 **[Examples →](examples/)** | 🏗️ **[Contributing →](CONTRIBUTING.md)**

The [aggregated OPT-125M CPU example](examples/aggregated/opt-125m-cpu/) and
[disaggregated 1P1D NIXL TCP example](examples/disaggregated/opt-125m-cpu-nixl/)
validate proxy-first startup and lifecycle behavior. For local GPU validation,
see the [GPU integration suite](tests/gpu/).

## License

Apache 2.0 — see [LICENSE](LICENSE)
