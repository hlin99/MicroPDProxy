# Repository Guidelines

> [!IMPORTANT]
> **COMMIT IDENTITY AND ATTRIBUTION:** All commits must use
> `Tony Lin <tony.lin@intel.com>`. Never include `Co-authored-by`, Copilot, or
> any other agent attribution in commit messages.

- Read related examples, documentation, and tests before modifying proxy behavior,
  configuration, or examples.
- New P/D examples must support starting the proxy before the backends. Offline
  nodes must not make proxy startup fail and inference must return 503 until ready.
- Node examples must enable health checks. Keep heartbeats concise:
  `mode=... | P=x/y online | D=x/y online`; aggregated deployments show only
  aggregated counts and mixed deployments show all configured roles.
- New topology examples include configuration, startup scripts, smoke tests,
  `run_all.sh`, documentation, and ignored runtime logs.
- A logical model uses either aggregated or P/D topology. Mixed deployments use
  distinct logical model names, mapping vLLM names with `--served-model-name`
  when sharing weights.
- Validate proxy-first startup, node discovery, partial node loss, reconnection,
  `/status/instances`, and heartbeat output.
- Stop test services after validation and confirm GPU memory is released. Before
  restarting vLLM, wait for the former process to exit, its port to close, and
  GPU memory to be reclaimed.
- Store test logs in ignored `logs/` directories or the session directory; do
  not commit runtime artifacts. Scenario logs use phase separators.
- When testing features not installed locally, start the proxy from repository
  source rather than treating an older installed `xpyd` as current behavior.
- Update relevant documentation and focused tests with configuration or behavior
  changes.
