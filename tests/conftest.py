"""Shared test fixtures and utilities."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from helpers import _DECODE_PORT, _PREFILL_PORT, _TOKENIZER_PATH
from httpx import ASGITransport, AsyncClient
from MicroPDProxyServer import Proxy, RoundRobinSchedulingPolicy


def _make_proxy_app():
    """Create a FastAPI app with a Proxy router for testing."""
    proxy = Proxy(
        prefill_instances=[f"127.0.0.1:{_PREFILL_PORT}"],
        decode_instances=[f"127.0.0.1:{_DECODE_PORT}"],
        model=_TOKENIZER_PATH,
        scheduling_policy=RoundRobinSchedulingPolicy(),
        generator_on_p_node=False,
    )
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(proxy.router)
    return app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async HTTP client wired to the proxy app."""
    app = _make_proxy_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as cli:
        yield cli
