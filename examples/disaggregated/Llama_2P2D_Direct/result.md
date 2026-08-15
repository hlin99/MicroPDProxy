# Direct 2P2D scenario

Run this scenario with `./run_all.sh`. It starts xPyD first; the proxy listens
immediately and returns 503 for inference until it discovers healthy nodes.
The script then starts two prefill and two decode loopback backends, waits for
their health endpoints, runs the four-request completion smoke test, and stops
both xPyD and the backends. Health checks run every two seconds, removing
offline P/D nodes from scheduling and restoring them when they reconnect.
Logs and benchmark artifacts remain in this directory.
