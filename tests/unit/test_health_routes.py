# SPDX-License-Identifier: Apache-2.0
"""Tests for proxy health aggregation."""

# Standard
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# First Party
from xpyd.proxy import Proxy


def test_get_from_instance_aggregates_aggregated_instances() -> None:
    """Health aggregation queries every configured aggregated-role instance."""
    proxy = MagicMock()
    proxy.prefill_instances = []
    proxy.decode_instances = []
    proxy.aggregated_instances = {
        "llama": ["127.0.0.1:8000", "127.0.0.1:8001"],
    }

    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"status": "ok"})

    request_context = MagicMock()
    request_context.__aenter__ = AsyncMock(return_value=response)
    request_context.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get.return_value = request_context
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "xpyd.proxy.aiohttp.ClientSession",
        return_value=session_context,
    ):
        result = asyncio.run(
            Proxy.get_from_instance(
                proxy,
                "/health",
                is_full_instancelist=1,
            )
        )

    assert result.status_code == 200
    assert [call.args[0] for call in session.get.call_args_list] == [
        "http://127.0.0.1:8000/health",
        "http://127.0.0.1:8001/health",
    ]
