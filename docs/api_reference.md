# API Reference

MicroDisaggregatedProxy exposes an OpenAI-compatible API surface. All endpoints are served
by the proxy process (default port `8868`).

## Authentication

Most endpoints are open. The admin endpoints (`/instances/add` and
`/instances/remove`) require an API key passed via the `X-API-Key` header. Set
the key with the `ADMIN_API_KEY` environment variable. When `ADMIN_API_KEY` is
unset the endpoints reject every request with `500`; a wrong key returns `403`
and a missing header `422`.

---

## Endpoints

### POST `/v1/chat/completions`

Chat completion (streaming and non-streaming). OpenAI-compatible.

**Request:**
```json
{
  "model": "DeepSeek-R1",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 256,
  "stream": false
}
```

**Response (non-streaming):**
```json
{
  "id": "cmpl-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Hello! How can I help?"},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}
}
```

**Response (streaming, `stream: true`):**

Returns `text/event-stream` with SSE chunks:
```
data: {"id":"cmpl-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}

data: [DONE]
```

**Auth:** None required.

---

### POST `/v1/completions`

Text completion. OpenAI-compatible.

**Request:**
```json
{
  "model": "DeepSeek-R1",
  "prompt": "The meaning of life is",
  "max_tokens": 64,
  "stream": false
}
```

**Response:**
```json
{
  "id": "cmpl-abc123",
  "object": "text_completion",
  "choices": [
    {
      "index": 0,
      "text": " to find purpose and connection.",
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
}
```

**Auth:** None required.

---

### GET `/v1/models`

List available models. Aggregated from backend instances.

List every model registered across the backend instances.

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "DeepSeek-R1",
      "object": "model",
      "created": 0,
      "owned_by": "system"
    }
  ]
}
```

**Auth:** None required.

---

### GET `/status`

Proxy status: lists prefill and decode node addresses and counts.

**Response:**
```json
{
  "prefill_node_count": 2,
  "decode_node_count": 2,
  "prefill_nodes": ["10.0.0.1:8100", "10.0.0.2:8100"],
  "decode_nodes": ["10.0.0.3:8200", "10.0.0.4:8200"]
}
```

**Auth:** None required.

---

### GET `/health`

Health fan-out across every backend node. Each configured instance is queried on
its own `/health` endpoint and the raw per-node result is returned.

**Response (`200`, at least one node reachable):**
```json
{
  "10.0.0.1:8100": {"status": 200, "type": "text", "data": "OK"},
  "10.0.0.3:8200": {"status": 500, "error": "Failed to connect to instance"}
}
```

The proxy answers `503` when *no* node is reachable or every node returns `5xx`,
and `500` when no instance is registered at all. Load balancers can therefore use
this endpoint directly to take the proxy out of rotation.

**Auth:** None required.

---

### GET/POST `/ping`

Same fan-out as `/health`, using each node's `/ping` endpoint. Both verbs are
accepted and share one handler.

**Auth:** None required.

---

### GET `/metrics`

Prometheus text exposition of the proxy metrics.

**Response:** `text/plain; version=0.0.4; charset=utf-8`

**Auth:** None required.

---

### POST `/instances/add`

Dynamically register a prefill or decode instance. The instance is validated
(`GET /v1/models` must answer with the model the proxy serves) before it joins
the scheduling rotation.

**Request:**
```json
{
  "type": "prefill",
  "instance": "10.0.0.5:8100"
}
```

`type` must be `prefill` or `decode`. `instance` must be `host:port` where host is
a literal IPv4 address or `localhost`, and port is in `1-65535`. IPv6 addresses
are not supported.

**Response (`200`):**
```json
{
  "message": "Added 10.0.0.5:8100 to prefill_instances."
}
```

**Errors:** `400` for an invalid type, address, port, duplicate instance or a
failed validation handshake; `403` for a wrong API key; `422` when the
`X-API-Key` header is absent; `500` when `ADMIN_API_KEY` is unset.

**Auth:** Required. Pass `X-API-Key` header matching `ADMIN_API_KEY`.

---

### POST `/instances/remove`

Drain and remove a prefill, decode, or aggregated instance. The instance is
marked `draining` first, which immediately excludes it from new scheduling.
The request then waits for its active request count to reach zero before
removing it from discovery, health checks, scheduling, and the instance
registry.

**Request:**
```json
{
  "type": "decode",
  "instance": "10.0.0.4:8200",
  "timeout_seconds": 60
}
```

`type` must be `prefill`, `decode`, or `aggregated`. `timeout_seconds` is
optional, defaults to 60 seconds, and must be between 0 and 3600. A timeout
returns `504` and leaves the instance in `draining`, so it remains unavailable
to new requests and the same removal request can be retried.

**Response (`200`):**
```json
{
  "message": "Removed 10.0.0.4:8200 from decode_instances."
}
```

**Errors:** `400` for an invalid type, timeout, or role mismatch; `403` for a
wrong API key; `404` when the instance is not registered; `422` when the
`X-API-Key` header is absent; `500` when `ADMIN_API_KEY` is unset; `504` when
active requests do not drain before the timeout.

**Auth:** Required. Pass `X-API-Key` header matching `ADMIN_API_KEY`.

---

### Passthrough endpoints

The following endpoints are forwarded verbatim to a single backend instance and
their response is returned unchanged, including the backend status code. A
healthy prefill node is preferred, falling back to aggregated and then decode
nodes, so these endpoints work in every topology.

| Endpoint | Required fields |
| --- | --- |
| `POST /tokenize` | `model`, `prompt` |
| `POST /detokenize` | `model`, `tokens` |
| `POST /v1/embeddings` | `model`, `input` |
| `POST /pooling` | `model`, `messages` |
| `POST /score`, `POST /v1/score` | `model`, `text_1`, `text_2`, `predictions` |
| `POST /rerank`, `POST /v1/rerank`, `POST /v2/rerank` | `model`, `query`, `documents` |
| `POST /invocations` | `model`, `prompt` |

A body missing any required field is rejected with `400` listing every missing
field. When no backend instance can serve the request the proxy returns `503`.

**Example:**
```json
{
  "model": "DeepSeek-R1",
  "prompt": "Hello world"
}
```

**Auth:** None required.

---

### GET `/version`

Return the version reported by a single backend instance, keyed by address.

**Response:**
```json
{
  "10.0.0.1:8100": {"status": 200, "type": "json", "data": {"version": "0.11.0"}}
}
```

**Auth:** None required.
