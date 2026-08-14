# LMCache ZMQ 2P2D scenario

Run this scenario with `./run_all.sh`. It starts two prefill and two decode
LMCache backends, verifies every backend health endpoint, starts the ZMQ xPyD
proxy, runs the configured vLLM benchmark, and cleans up all started
processes. Benchmark output and logs are retained in `bench_results/` and the
scenario directory.
