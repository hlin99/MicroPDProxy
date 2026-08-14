# SPDX-License-Identifier: Apache-2.0
"""Receive LMCache disaggregated completion notifications over ZMQ."""

from __future__ import annotations

import asyncio
import logging

import msgspec
import zmq
import zmq.asyncio

logger = logging.getLogger("xpyd.proxy")


class ZmqNotificationListener:
    """Correlate LMCache ``ProxyNotif`` messages with active request IDs."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.endpoint = f"tcp://{host}:{port}"
        self.timeout = timeout
        self._context: zmq.asyncio.Context | None = None
        self._socket: zmq.asyncio.Socket | None = None
        self._task: asyncio.Task | None = None
        self._condition = asyncio.Condition()
        self._active: set[str] = set()
        self._counts: dict[str, int] = {}

    async def start(self) -> None:
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.PULL)
        self._socket.bind(self.endpoint)
        self._task = asyncio.create_task(self._receive())
        logger.info("ZMQ notification listener started", extra={"endpoint": self.endpoint})

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._socket is not None:
            self._socket.close(linger=0)
        if self._context is not None:
            self._context.term()

    async def register(self, request_id: str) -> None:
        async with self._condition:
            self._active.add(request_id)
            self._counts[request_id] = 0

    async def discard(self, request_id: str) -> None:
        async with self._condition:
            self._active.discard(request_id)
            self._counts.pop(request_id, None)

    async def wait(self, request_id: str, expected: int) -> None:
        async def _wait() -> None:
            async with self._condition:
                await self._condition.wait_for(
                    lambda: self._counts.get(request_id, 0) >= expected
                )

        try:
            await asyncio.wait_for(_wait(), timeout=self.timeout)
        finally:
            await self.discard(request_id)

    async def _receive(self) -> None:
        assert self._socket is not None
        while True:
            payload = await self._socket.recv()
            try:
                message = msgspec.msgpack.decode(payload)
            except msgspec.DecodeError:
                logger.warning("Ignored invalid ZMQ msgpack notification")
                continue
            if not isinstance(message, dict) or message.get("type") != "ProxyNotif":
                logger.debug("Ignored non-ProxyNotif ZMQ message")
                continue
            request_id = message.get("req_id")
            if not isinstance(request_id, str):
                logger.warning("Ignored ProxyNotif without a string req_id")
                continue
            async with self._condition:
                if request_id not in self._active:
                    logger.warning(
                        "Ignored ProxyNotif for unknown request",
                        extra={"request_id": request_id},
                    )
                    continue
                self._counts[request_id] += 1
                self._condition.notify_all()
                logger.info(
                    "ZMQ prefill notification received",
                    extra={
                        "request_id": request_id,
                        "count": self._counts[request_id],
                    },
                )
