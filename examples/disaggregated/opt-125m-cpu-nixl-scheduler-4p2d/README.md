# OPT-125M 4P2D scheduler matrix

This dedicated CPU NIXL example starts xPyD before four prefill and two decode
vLLM instances. The six backends stay online while xPyD restarts once for each
scheduling policy.

Run it after installing the dependencies and model from the sibling
`opt-125m-cpu-nixl` example:

```bash
./run_all.sh
```

The smoke test verifies exact round-robin P/D rotation, consistent-hash session
affinity, cache-aware prefix affinity, concurrent load distribution for
load-balanced and power-of-two scheduling, and P/D removal and re-addition for
all five policies. Runtime output is written to the ignored `logs/` directory.
