# Mixed 1P1D + 2 aggregated scenario

Run this scenario with `./run_all.sh`. It starts xPyD before the backends,
then launches one prefill node, one decode node, and two aggregated nodes.
All four instances load the same model weights but expose topology-specific
served model names. The smoke test sends one request to each model.

The proxy heartbeat reports both topologies:

```text
Node heartbeat | mode=mixed | P=1/1 online | D=1/1 online | aggregated=2/2 online
```

Runtime logs are written to `logs/`.
