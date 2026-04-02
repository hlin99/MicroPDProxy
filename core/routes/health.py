# SPDX-License-Identifier: Apache-2.0
"""Health, info, and metrics route handlers."""

import aiohttp
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse, Response

try:
    from ..metrics import get_metrics
except ImportError:
    from metrics import get_metrics

logger = logging.getLogger("MicroPDProxyServer")


def register(router: APIRouter, server) -> None:
    """Register health/info routes on *router*."""

    async def get_from_instance(path: str, is_full_instancelist: int = 0):
        if not server.prefill_instances:
            return JSONResponse(content={"error": "No instances available"}, status_code=500)

        if is_full_instancelist == 0:
            instances = [server.prefill_instances[0]]
        else:
            instances = server.prefill_instances + server.decode_instances

        results = {}
        async with aiohttp.ClientSession() as session:
            for inst in instances:
                url = f"http://{inst}{path}"
                try:
                    async with session.get(url) as resp:
                        try:
                            data = await resp.json()
                            dtype = "json"
                        except aiohttp.ContentTypeError:
                            data = await resp.text()
                            dtype = "text"
                        results[inst] = {
                            "status": resp.status,
                            "type": dtype,
                            "data": data,
                        }
                except Exception as e:
                    results[inst] = {"status": 500, "error": str(e)}
                    print(f"Failed to fetch {url}: {e}, continue...")

        return JSONResponse(content=results, status_code=200)

    async def get_health():
        return await get_from_instance("/health", is_full_instancelist=1)

    async def get_ping():
        return await get_from_instance("/ping", is_full_instancelist=1)

    async def get_models():
        return await get_from_instance("/v1/models")

    async def get_version():
        return await get_from_instance("/version")

    async def get_metrics_endpoint():
        return Response(
            content=get_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    router.get("/health", response_class=PlainTextResponse)(get_health)
    router.get("/ping", response_class=PlainTextResponse)(get_ping)
    router.post("/ping", response_class=PlainTextResponse)(get_ping)
    router.get("/v1/models", response_class=JSONResponse)(get_models)
    router.get("/version", response_class=JSONResponse)(get_version)
    router.get("/metrics")(get_metrics_endpoint)

    router.options("/health")(lambda: None)
    router.options("/ping")(lambda: None)
    router.options("/v1/models")(lambda: None)
    router.options("/version")(lambda: None)

    # Expose get_from_instance on server for backward compatibility
    server.get_from_instance = get_from_instance
