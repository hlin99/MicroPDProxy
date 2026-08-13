# NIXL 2P2D scenario

Run this scenario with `./run_all.sh`. It starts two prefill and two decode
NIXL backends, waits for their loopback health endpoints, starts xPyD, runs the
complete configured vLLM benchmark, and cleans up the proxy and backends.
Generated benchmark output and logs are retained.
