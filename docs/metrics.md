# Metrics

## Overview

MicroDisaggregatedProxy exposes a Prometheus-compatible `/metrics` endpoint for real-time observability of proxy behavior, including request counts, latency distributions, and in-flight request tracking.

## Available Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `proxy_requests_total` | Counter | `endpoint` | Total number of requests received |
| `proxy_request_duration_seconds` | Histogram | `endpoint` | Request duration including full streaming lifetime |
| `proxy_active_requests` | Gauge | — | Number of currently in-flight requests |
| `proxy_prefill_duration_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | Prefill response time |
| `proxy_kv_transfer_duration_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | Estimated KV transfer time |
| `proxy_decode_duration_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | Decode phase duration |
| `proxy_ttft_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | End-to-end time to first token |
| `proxy_tpot_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | Approximate time per output chunk for streaming requests |
| `proxy_e2e_latency_seconds` | Histogram | `prefill_instance`, `decode_instance`, `model` | End-to-end request latency |
| `proxy_prefill_active_requests` | Gauge | `prefill_instance`, `decode_instance`, `model` | Requests in the prefill stage |
| `proxy_decode_active_requests` | Gauge | `prefill_instance`, `decode_instance`, `model` | Requests in the decode stage |
| `proxy_prefill_queue_depth` | Gauge | `prefill_instance`, `decode_instance`, `model` | Requests waiting for prefill |
| `proxy_prefill_requests_total` | Counter | `prefill_instance`, `decode_instance`, `model` | Requests routed to each prefill instance |
| `proxy_decode_requests_total` | Counter | `prefill_instance`, `decode_instance`, `model` | Requests routed to each decode instance |
| `proxy_instance_errors_total` | Counter | `instance`, `error_type`, `model` | Errors by instance and error type |

## How It Works

Request counters and active gauges are updated when an inference request enters
the proxy. Duration histograms are observed and active gauges are decremented
after the complete response body or stream has finished.

The P/D metrics are emitted only for disaggregated requests. TPOT is approximate
because it is calculated from streamed HTTP chunks rather than tokenizer output.
The proxy currently has no explicit prefill queue, so
`proxy_prefill_queue_depth` is initialized to `0` for each routed P/D label set.

## Endpoint

```
GET /metrics
```

Returns metrics in Prometheus text exposition format with
`Content-Type: text/plain; version=0.0.4; charset=utf-8`.

## Grafana Examples

**QPS (requests per second):**

```promql
rate(proxy_requests_total[5m])
```

**P99 latency:**

```promql
histogram_quantile(0.99, rate(proxy_request_duration_seconds_bucket[5m]))
```

**Active requests:**

```promql
proxy_active_requests
```

## Configuration

Metrics are **always enabled** — no configuration is needed. The `/metrics` endpoint is available as soon as the proxy starts.

> **Note:** MicroDisaggregatedProxy uses a dedicated `CollectorRegistry` to avoid exposing default process collectors, keeping the metrics output clean and focused on proxy-specific data.
