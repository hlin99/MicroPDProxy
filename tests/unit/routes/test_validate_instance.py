# SPDX-License-Identifier: Apache-2.0
"""Tests for runtime backend validation."""

# Standard
import asyncio
from types import SimpleNamespace

# First Party
from xpyd.proxy import Proxy

from ._helpers import FakeResponse, fake_aiohttp


def _backend_models(model: str) -> FakeResponse:
    return FakeResponse(200, {"data": [{"id": model}]})


def test_validate_instance_uses_the_explicit_model() -> None:
    proxy = SimpleNamespace(model="facebook/opt-125m", registry=None)

    with fake_aiohttp(lambda *_args: _backend_models("facebook/opt-125m")) as session:
        valid = asyncio.run(Proxy.validate_instance(proxy, "127.0.0.1:8100"))

    assert valid is True
    assert session.urls == ["http://127.0.0.1:8100/v1/models"]


def test_validate_instance_uses_discovered_models() -> None:
    registry = SimpleNamespace(
        get_all_instances=lambda: [
            SimpleNamespace(model="facebook/opt-125m"),
            SimpleNamespace(model=""),
        ]
    )
    proxy = SimpleNamespace(model="", registry=registry)

    with fake_aiohttp(lambda *_args: _backend_models("facebook/opt-125m")):
        valid = asyncio.run(Proxy.validate_instance(proxy, "127.0.0.1:8000"))

    assert valid is True


def test_validate_instance_rejects_an_unknown_model() -> None:
    registry = SimpleNamespace(
        get_all_instances=lambda: [SimpleNamespace(model="facebook/opt-125m")]
    )
    proxy = SimpleNamespace(model="", registry=registry)

    with fake_aiohttp(lambda *_args: _backend_models("other/model")):
        valid = asyncio.run(Proxy.validate_instance(proxy, "127.0.0.1:8000"))

    assert valid is False
