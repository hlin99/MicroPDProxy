# SPDX-License-Identifier: Apache-2.0
"""Tests for ``Proxy.post_to_instance`` and backend selection."""

# Standard
import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

# Third Party
import aiohttp
import pytest

from ._helpers import FakeRequest, FakeResponse, fake_aiohttp, make_proxy

TEMPLATE = {"model": "", "prompt": ""}


def _forward(proxy: Any, body: Any, handler: Any) -> tuple[Any, Any]:
    request = FakeRequest(body)
    with fake_aiohttp(handler) as session:
        response = asyncio.run(proxy.post_to_instance(request, "/tokenize", TEMPLATE))
    return response, session


def _ok(*_args: Any) -> FakeResponse:
    return FakeResponse(200, {"tokens": [1, 2, 3]})


def _body_of(response: Any) -> Any:
    return json.loads(response.body)


def test_forwards_to_prefill_with_merged_payload() -> None:
    """The template supplies defaults that the request body overrides."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"], decode=["127.0.0.1:8200"])

    response, session = _forward(proxy, {"model": "opt", "prompt": "hi"}, _ok)

    assert response.status_code == 200
    assert session.calls == [
        ("POST", "http://127.0.0.1:8100/tokenize", {"model": "opt", "prompt": "hi"})
    ]


def test_extra_body_fields_are_preserved() -> None:
    """Fields outside the template are forwarded untouched."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    _, session = _forward(
        proxy, {"model": "opt", "prompt": "hi", "add_special_tokens": False}, _ok
    )

    assert session.calls[0][2]["add_special_tokens"] is False


def test_missing_fields_are_reported_together() -> None:
    """A 400 lists every missing template field, not just the first."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    response, session = _forward(proxy, {}, _ok)

    assert response.status_code == 400
    message = _body_of(response)["error"]["message"]
    assert "model" in message and "prompt" in message
    assert session.calls == []


def test_invalid_json_body_is_rejected() -> None:
    """A malformed body fails fast with 400 instead of reaching a backend."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    response, session = _forward(
        proxy, json.JSONDecodeError("bad", "", 0), _ok
    )

    assert response.status_code == 400
    assert _body_of(response)["error"]["type"] == "invalid_request_error"
    assert session.calls == []


def test_non_json_backend_response_is_wrapped() -> None:
    """A non-JSON backend body is surfaced under a ``raw`` key."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    response, _ = _forward(
        proxy,
        {"model": "opt", "prompt": "hi"},
        lambda *_a: FakeResponse(200, None, "plain text"),
    )

    assert _body_of(response) == {"raw": "plain text"}


def test_backend_error_status_is_propagated() -> None:
    """Backend 5xx responses keep their status code and payload."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    response, _ = _forward(
        proxy,
        {"model": "opt", "prompt": "hi"},
        lambda *_a: FakeResponse(502, {"error": "upstream"}),
    )

    assert response.status_code == 502
    assert _body_of(response) == {"error": "upstream"}


def test_connection_failure_returns_structured_error() -> None:
    """An unreachable backend produces a 500 proxy error, not a traceback."""
    proxy = make_proxy(prefill=["127.0.0.1:8100"])

    response, _ = _forward(
        proxy,
        {"model": "opt", "prompt": "hi"},
        lambda *_a: aiohttp.ClientConnectorError(MagicMock(), OSError("refused")),
    )

    assert response.status_code == 500
    assert "Failed to forward" in _body_of(response)["error"]["message"]


def test_aggregated_deployment_is_served() -> None:
    """Aggregated topologies have no prefill role but must still forward."""
    proxy = make_proxy(aggregated={"opt": ["127.0.0.1:8000", "127.0.0.1:8001"]})

    response, session = _forward(proxy, {"model": "opt", "prompt": "hi"}, _ok)

    assert response.status_code == 200
    assert session.urls == ["http://127.0.0.1:8000/tokenize"]


def test_decode_only_deployment_is_served() -> None:
    """Decode nodes are the last-resort target when no other role exists."""
    proxy = make_proxy(decode=["127.0.0.1:8200"])

    _, session = _forward(proxy, {"model": "opt", "prompt": "hi"}, _ok)

    assert session.urls == ["http://127.0.0.1:8200/tokenize"]


def test_no_instances_returns_503() -> None:
    """An empty cluster yields a structured 503 rather than an IndexError."""
    proxy = make_proxy()

    response, session = _forward(proxy, {"model": "opt", "prompt": "hi"}, _ok)

    assert response.status_code == 503
    assert _body_of(response)["error"]["type"] == "proxy_error"
    assert session.calls == []


@pytest.mark.parametrize(
    "available,expected",
    [
        ({"prefill": ["127.0.0.1:8100"]}, "http://127.0.0.1:8100/tokenize"),
        ({"aggregated": ["127.0.0.1:8000"]}, "http://127.0.0.1:8000/tokenize"),
        ({"decode": ["127.0.0.1:8200"]}, "http://127.0.0.1:8200/tokenize"),
    ],
)
def test_registry_roles_are_tried_in_order(
    available: dict[str, list[str]], expected: str
) -> None:
    """Healthy instances from the registry take precedence over static lists."""
    registry = MagicMock()
    registry.get_available_instances.side_effect = (
        lambda role, model="": available.get(role, [])
    )
    proxy = make_proxy(prefill=["10.0.0.1:9999"], registry=registry)

    _, session = _forward(proxy, {"model": "opt", "prompt": "hi"}, _ok)

    assert session.urls == [expected]


def test_registry_without_healthy_instance_for_model_returns_503() -> None:
    """A model with no healthy backend must not fall back to another model."""
    registry = MagicMock()
    registry.get_available_instances.return_value = []
    proxy = make_proxy(prefill=["127.0.0.1:8100"], registry=registry)

    response, session = _forward(proxy, {"model": "other", "prompt": "hi"}, _ok)

    assert response.status_code == 503
    assert session.calls == []


def test_registry_without_model_falls_back_to_static_lists() -> None:
    """An unnamed model still reaches the statically configured instances."""
    registry = MagicMock()
    registry.get_available_instances.return_value = []
    proxy = make_proxy(prefill=["127.0.0.1:8100"], registry=registry)

    _, session = _forward(proxy, {"model": "", "prompt": "hi"}, _ok)

    assert session.urls == ["http://127.0.0.1:8100/tokenize"]
