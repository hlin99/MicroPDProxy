# TP1x4 scheduler scenario

Run this scenario with `./run_all.sh`. It starts four loopback vLLM backends,
waits for all health endpoints, and invokes the scheduler smoke-test matrix.
The matrix starts and stops xPyD once for each supported scheduler, runs the
configured benchmark, and retains results in `scheduler_results/`. The wrapper
then stops all backends.
