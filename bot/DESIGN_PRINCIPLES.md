# Design Principles — xPyD-proxy

Architecture constraints and design rules that all code changes must respect.

---

## Architecture Constraints

1. **PD Disaggregation** — xPyD-proxy is built for prefill/decode (PD)
   disaggregated inference. Every routing and scheduling decision must
   account for the prefill→decode handoff.

2. **Stateless Proxy** — the proxy itself holds no model weights and no KV
   cache. It is a pure routing/scheduling layer between clients and vLLM
   worker nodes.

3. **vLLM CLI Compatibility** — proxy configuration and startup must remain
   compatible with vLLM's CLI interface. Users should be able to swap in
   xPyD-proxy without changing their vLLM deployment scripts.

## Design Rules

4. **Topology-Driven Routing** — routing decisions are determined by the
   topology matrix configuration `(P, D, replicas)`. The supported topologies
   `(1,2,1) (2,2,1) (1,2,2) (1,2,4) (1,2,8) (2,2,2) (2,4,1) (2,4,2)` must
   not be broken by any code change.

5. **Health-First Scheduling** — node health checks drive scheduling. Unhealthy
   nodes must be removed from the active pool immediately. Recovery is
   automatic when health checks pass again.

6. **Circuit Breaker Pattern** — repeated failures to a node trigger a circuit
   breaker. The proxy must not keep sending traffic to a node that is
   consistently failing.

7. **Configuration Layering** — configuration is resolved in order:
   CLI flags → environment variables → YAML config → defaults.
   Higher-priority sources override lower ones.

## Coding Guidelines

8. **Type Annotations** — all public functions and methods must have full
   type annotations (parameters and return types).

9. **No Bare `except`** — always catch specific exception types. Bare
   `except:` or `except Exception:` without re-raising is not allowed.

10. **Async by Default** — new I/O-bound code should use `async`/`await`.
    Synchronous I/O in the request path is not acceptable.

11. **Tests Required** — every new feature or bug fix must include
    corresponding unit tests. Integration tests go to the
    `xPyD-integration` repo.

12. **Minimal Dependencies** — do not add new runtime dependencies without
    discussion. The proxy should remain lightweight.
