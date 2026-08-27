# CLI Reference *(planned)*

> **Status:** CLI packaging is in progress (Task 8). This document describes
> the planned interface.

## Installation

```bash
pip install .
```

For development:

```bash
pip install -e .
```

After installation, the `xpyd` command is available system-wide.
The `proxy` subcommand is optional for every command and option: `xpyd ...`
and `xpyd proxy ...` are equivalent.

## Quick Start

```bash
xpyd -c proxy.yaml
```

This starts the proxy using the specified YAML configuration file. The proxy
will begin startup node discovery, probing configured backend nodes until at
least one prefill and one decode node are healthy, then start accepting
requests.

## CLI Reference

| Flag / Env | Description |
|---|---|
| `-c`, `--config FILE` | Path to YAML configuration file. |
| `--help` | Show help message and exit. |
| `--version` | Show version number and exit. |
| `--validate-config FILE` | Validate a YAML config file without starting the server. Exits with code 0 if valid, non-zero with error details if invalid. |
| `--init-config [PATH]` | Generate a YAML config and exit. Offers an interactive wizard, defaulting to the documented template after 5 seconds. Defaults to `./xpyd.yaml`. |
| `XPYD_CONFIG` | Environment variable alternative to `--config`. |

The proxy configuration is YAML-only. Legacy arguments such as `--model`,
`--prefill`, and `--decode` are not supported.

When neither `--config` nor `XPYD_CONFIG` is set, `xpyd` uses `./xpyd.yaml`
and prints that choice. If the file does not exist, it automatically starts
the `--init-config` flow and exits after creating it.

## Startup Node Discovery

When `xpyd` starts, the following sequence occurs:

```
1. Parse configuration (CLI → env → YAML → defaults)
2. Start uvicorn (port opens immediately)
3. Return 503 "waiting for backend nodes" for all business requests
4. Background task: probe all configured nodes every <probe_interval_seconds>
   and log the deployment mode and online P/D node counts every
   <heartbeat_interval_seconds>
5. As nodes respond healthy, add them to the scheduling pool
   Log: "[3/16 decode nodes ready]"
6. Once ≥1 prefill + ≥1 decode are ready:
   Log: "Proxy ready: N prefill, M decode nodes available"
   → Start accepting requests (200 OK)
7. If <wait_timeout_seconds> expires without 1P+1D → exit with error
```

This design ensures:

- The proxy port is reachable immediately (load balancers see it as "up").
- No requests are lost — clients receive a clear 503 until backends are ready.
- Nodes can start in any order; the proxy discovers them dynamically.

## Configuration Resolution

The proxy resolves configuration from multiple sources in the following
precedence order (highest priority first):

| Priority | Source | Example |
|---|---|---|
| 1 (highest) | CLI arguments | `xpyd --port 9000` |
| 2 | Environment variables | `XPYD_CONFIG=proxy.yaml` |
| 3 | YAML config file | `port: 8000` in proxy.yaml |
| 4 (lowest) | Built-in defaults | port defaults to 8000 |

See [Configuration Guide](configuration.md) for the full YAML schema.

## Examples

### Start with a config file

```bash
xpyd -c /etc/xpyd/production.yaml
```

### Start with environment variable

```bash
export XPYD_CONFIG=/etc/xpyd/production.yaml
xpyd
```

### Validate configuration without starting

```bash
xpyd --validate-config proxy.yaml
# Output: Config is valid: proxy.yaml
# Exit code: 0
```

```bash
xpyd --validate-config bad.yaml
# Output: Configuration error: "model" is required
# Exit code: 1
```

### Generate configuration

```bash
xpyd --init-config proxy.yaml
```

Enter `Y` within five seconds to use the wizard. Its first question selects an
`aggregated` or `disaggregated` topology, followed by the model, topology-
appropriate instance counts and addresses, tokenizer path, port, logging,
scheduling, first-token source (for disaggregated deployments), and health
checks. Enter `N` or wait five seconds to generate the documented template
instead. The default template uses one aggregated backend at
`10.0.0.1:8100`; choose the wizard's `disaggregated` topology to configure
separate Prefill and Decode nodes. Wizard-generated files are validated before they are written.
Defaults are underlined in interactive terminals; pressing Enter selects the
underlined value.

Disaggregated deployments also select `direct`, `nixl`, or `zmq` transfer.
For ZMQ, the wizard creates the required notification listener and per-decode
receiver mappings from the chosen base ports and channel count.

Backend addresses can be entered as a single address, a comma/space-separated
list, or a full IPv4 range such as `192.168.0.1-192.168.0.10`. For each role,
choose `same` to enter one shared port, or `per-instance` to provide ports in
the address input. Per-instance mode supports explicit `IP:PORT` lists, a
single-host port range such as `192.168.0.1:8100-8109`, and aligned IP/port
ranges such as `192.168.0.1-192.168.0.10:8100-8109`. The wizard expands the
input and requires the resulting address count to match the declared instance
count.

### Use default config file

If no `--config` or `XPYD_CONFIG` is set, `xpyd` looks for
`./xpyd.yaml` in the current directory:

```bash
cd /app
ls xpyd.yaml   # exists
xpyd           # automatically uses ./xpyd.yaml
```

### Run directly without installing

The legacy invocation still works:

```bash
python core/MicroDisaggregatedProxyServer.py --model /path/to/model --prefill ... --decode ...
```
