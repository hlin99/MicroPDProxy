# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for route-level tests."""

# Standard
from contextlib import contextmanager
from types import MethodType, SimpleNamespace
from typing import Any, Callable, Optional
from unittest.mock import patch

# Third Party
import aiohttp
from fastapi import APIRouter, FastAPI

# First Party
from xpyd.proxy import Proxy


class FakeResponse:
    """Minimal stand-in for :class:`aiohttp.ClientResponse`."""

    def __init__(
        self,
        status: int = 200,
        json_data: Any = None,
        text_data: str = "",
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def json(self) -> Any:
        if self._json_data is None:
            raise aiohttp.ContentTypeError(None, ())
        return self._json_data

    async def text(self) -> str:
        return self._text_data


class _RequestContext:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def __aenter__(self) -> Any:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def __aexit__(self, *_exc: Any) -> bool:
        return False


class FakeClientSession:
    """Records requests and replays canned responses."""

    def __init__(self, handler: Callable[[str, str, Any], Any]) -> None:
        self._handler = handler
        self.calls: list[tuple[str, str, Any]] = []

    async def __aenter__(self) -> "FakeClientSession":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    def get(self, url: str, **_kwargs: Any) -> _RequestContext:
        self.calls.append(("GET", url, None))
        return _RequestContext(self._handler("GET", url, None))

    def post(self, url: str, json: Any = None, **_kwargs: Any) -> _RequestContext:
        self.calls.append(("POST", url, json))
        return _RequestContext(self._handler("POST", url, json))

    @property
    def urls(self) -> list[str]:
        return [call[1] for call in self.calls]


@contextmanager
def fake_aiohttp(handler: Callable[[str, str, Any], Any]):
    """Patch ``xpyd.proxy.aiohttp.ClientSession`` with a recording stub."""
    session = FakeClientSession(handler)
    with patch("xpyd.proxy.aiohttp.ClientSession", lambda *a, **k: session):
        yield session


class FakeRequest:
    """Minimal stand-in for :class:`fastapi.Request`."""

    def __init__(self, body: Any) -> None:
        self._body = body

    async def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def make_proxy(
    prefill: Optional[list[str]] = None,
    decode: Optional[list[str]] = None,
    aggregated: Optional[dict[str, list[str]]] = None,
    registry: Any = None,
) -> Any:
    """Build a lightweight object exposing the Proxy forwarding helpers."""
    proxy = SimpleNamespace(
        prefill_instances=list(prefill or []),
        decode_instances=list(decode or []),
        aggregated_instances=dict(aggregated or {}),
        registry=registry,
    )
    proxy._healthy_instances = MethodType(Proxy._healthy_instances, proxy)
    proxy.auxiliary_instances = MethodType(Proxy.auxiliary_instances, proxy)
    proxy.post_to_instance = MethodType(Proxy.post_to_instance, proxy)
    proxy.get_from_instance = MethodType(Proxy.get_from_instance, proxy)
    return proxy


def build_app(register: Callable[[APIRouter, Any], None], server: Any) -> FastAPI:
    """Mount *register*'s routes on a bare FastAPI app backed by *server*."""
    router = APIRouter()
    register(router, server)
    app = FastAPI()
    app.include_router(router)
    return app
