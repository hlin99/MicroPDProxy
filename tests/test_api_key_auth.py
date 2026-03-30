"""Tests for API key authentication."""

import os
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from MicroPDProxyServer import Proxy, RoundRobinSchedulingPolicy

from dummy_nodes.decode_node import app as decode_app
from dummy_nodes.prefill_node import app as prefill_app

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOKENIZER_PATH = os.path.join(_REPO_ROOT, "tokenizers", "DeepSeek-R1")


def _free_port():
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_PREFILL_PORT = _free_port()
_DECODE_PORT = _free_port()


def _run_server(app, port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uvicorn.Server(config).run()


threading.Thread(target=_run_server, args=(prefill_app, _PREFILL_PORT), daemon=True).start()
threading.Thread(target=_run_server, args=(decode_app, _DECODE_PORT), daemon=True).start()
time.sleep(2)


def _make_proxy_app():
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
    app = _make_proxy_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_request_without_api_key(client: AsyncClient):
    """Accessing /instances/add without x-api-key header should fail (422)."""
    resp = await client.post(
        "/instances/add",
        json={"type": "prefill", "instance": "127.0.0.1:9999"},
    )
    assert resp.status_code == 422  # Missing required header


@pytest.mark.anyio
async def test_request_with_valid_api_key(client: AsyncClient, monkeypatch):
    """With correct ADMIN_API_KEY, auth passes (may fail on validation)."""
    monkeypatch.setenv("ADMIN_API_KEY", "secret-key-123")
    resp = await client.post(
        "/instances/add",
        json={"type": "prefill", "instance": "127.0.0.1:9999"},
        headers={"x-api-key": "secret-key-123"},
    )
    # Auth passes, but instance validation will fail (no real server at 9999)
    assert resp.status_code in (200, 400, 500)


@pytest.mark.anyio
async def test_request_with_invalid_api_key(client: AsyncClient, monkeypatch):
    """With wrong API key, should get 403 Forbidden."""
    monkeypatch.setenv("ADMIN_API_KEY", "correct-key")
    resp = await client.post(
        "/instances/add",
        json={"type": "prefill", "instance": "127.0.0.1:9999"},
        headers={"x-api-key": "wrong-key"},
    )
    assert resp.status_code == 403
