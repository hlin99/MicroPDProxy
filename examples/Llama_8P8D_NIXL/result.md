# 8P8D NIXL matrix scenario

Run this scenario with `./run_all.sh`. The wrapper starts eight prefill and
eight decode NIXL backends, waits for every loopback health endpoint, and runs
the complete PD matrix.

The matrix covers prefill-first and decode-first responses, completion and
chat APIs, and the round-robin, load-balanced, consistent-hash, power-of-two,
and cache-aware schedulers. It starts a fresh proxy for each combination and
stops it after collecting the result. The default workload is 1,000 requests
at concurrency 8 per combination. Results, proxy logs, metrics, and the
summary remain in the ignored artifact directories.
