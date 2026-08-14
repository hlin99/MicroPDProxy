# Direct 2P2D scenario

Run this scenario with `./run_all.sh`. It starts two prefill and two decode
loopback backends, waits for all four health endpoints, starts xPyD in direct
disaggregated mode, runs the four-request completion smoke test, and stops both xPyD and
the backends. Logs and benchmark artifacts remain in this directory.
