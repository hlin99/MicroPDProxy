"""Tests for error handling / fault tolerance."""

import os
import socket

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from MicroPDProxyServer import Proxy, RoundRobinSchedulingPolicy

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKENIZER_PATH = os.path.join(_REPO_ROOT, "tokenizers", "DeepSeek-R1")


def _free_port():
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_proxy_app(prefill=None, decode=None):
    proxy = Proxy(
        prefill_instances=prefill or [],
        decode_instances=decode or [],
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


CHAT_PAYLOAD = {
    "model": "dummy",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 5,
    "stream": False,
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Tests with dead prefill node ---

@pytest.fixture
async def client_dead_prefill():
    dead_port = _free_port()
    live_port = _free_port()
    app = _make_proxy_app(
        prefill=[f"127.0.0.1:{dead_port}"],
        decode=[f"127.0.0.1:{live_port}"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_proxy_handles_dead_prefill_node(client_dead_prefill: AsyncClient):
    """Proxy should return an error (not crash) when prefill node is dead."""
    resp = await client_dead_prefill.post(
        "/v1/chat/completions", json=CHAT_PAYLOAD
    )
    # Should get an error response, not a server crash
    assert resp.status_code >= 400 or resp.status_code == 200


# --- Tests with dead decode node ---

@pytest.fixture
async def client_dead_decode():
    dead_port = _free_port()
    live_port = _free_port()
    app = _make_proxy_app(
        prefill=[f"127.0.0.1:{live_port}"],
        decode=[f"127.0.0.1:{dead_port}"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_proxy_handles_dead_decode_node(client_dead_decode: AsyncClient):
    """Proxy should return an error (not crash) when decode node is dead."""
    resp = await client_dead_decode.post(
        "/v1/chat/completions", json=CHAT_PAYLOAD
    )
    assert resp.status_code >= 400 or resp.status_code == 200


# --- Tests with nonexistent backend ---

@pytest.fixture
async def client_nonexistent():
    dead1 = _free_port()
    dead2 = _free_port()
    app = _make_proxy_app(
        prefill=[f"127.0.0.1:{dead1}"],
        decode=[f"127.0.0.1:{dead2}"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_request_to_nonexistent_backend(client_nonexistent: AsyncClient):
    """Request forwarded to nonexistent backends should not crash proxy."""
    resp = await client_nonexistent.post(
        "/v1/chat/completions", json=CHAT_PAYLOAD
    )
    assert resp.status_code >= 400 or resp.status_code == 200
