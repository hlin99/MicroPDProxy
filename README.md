# xPyD-proxy

**Lightweight Prefill-Decode disaggregated proxy for LLM serving.**

xPyD-proxy routes inference requests between prefill and decode nodes, enabling disaggregated LLM serving with load balancing, health monitoring, and fault tolerance.

## Key Features

- **disaggregated serving** — separate prefill and decode nodes for optimal resource utilization
- **Multiple scheduling policies** — round-robin, consistent hash, cache-aware, power-of-two
- **Resilience** — circuit breaker, health monitoring, automatic failover
- **Multi-model routing** — serve multiple models through a single proxy
- **OpenAI-compatible API** — drop-in replacement for vLLM/OpenAI endpoints
- **YAML configuration** — declarative topology and settings

## Install

```bash
pip install xpyd-proxy
```

Or as part of the full xPyD toolkit:

```bash
pip install xpyd
```

## Quick Start

```bash
# Generate YAML: enter Y for the wizard, or wait 5s for the template
xpyd --init-config proxy.yaml

# Validate and start with YAML config
xpyd --validate-config proxy.yaml
xpyd --config proxy.yaml
```

## Part of xPyD

| Component | Description |
|-----------|-------------|
| **xpyd-proxy** | disaggregated proxy |
| [xpyd-sim](https://github.com/xPyD-hub/xPyD-sim) | OpenAI-compatible inference simulator |
| [xpyd-bench](https://github.com/xPyD-hub/xPyD-bench) | Benchmarking & planning tool |

📖 **[Full Guide →](docs/guide.md)** | 💡 **[Examples →](examples/)** | 🏗️ **[Contributing →](CONTRIBUTING.md)**

The [aggregated OPT-125M CPU example](examples/aggregated/opt-125m-cpu/) and
[disaggregated 1P1D NIXL TCP variant](examples/disaggregated/opt-125m-cpu-nixl/)
validate proxy-first startup and real vLLM lifecycles on GitHub-hosted runners.
For local GPU validation, the [GPU integration suite](tests/gpu/) wraps the
aggregated, disaggregated, mixed, LMCache, and NIXL examples behind one command:
`bash tests/gpu/run.sh`.

## License

Apache 2.0 — see [LICENSE](LICENSE)
