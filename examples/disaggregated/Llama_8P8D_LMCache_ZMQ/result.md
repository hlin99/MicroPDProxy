# 8P8D LMCache ZMQ matrix scenario

Run this scenario with `./run_all.sh`. The wrapper starts eight prefill and
eight decode LMCache backends, waits for all loopback health endpoints, and
runs the complete disaggregated matrix without restarting the backends.

The matrix covers prefill-first and decode-first responses, completion and
chat APIs, and the round-robin, load-balanced, consistent-hash, power-of-two,
and cache-aware schedulers. It starts a fresh proxy for each combination and
stops it after collecting the result; the backends remain available for the
next proxy configuration. The default workload is 1,000 requests at
concurrency 8 per combination. Results, proxy logs, metrics, and the summary
remain in the ignored artifact directories.
