# SPDX-License-Identifier: Apache-2.0
"""Route registration aggregator for MicroDisaggregatedProxy."""

from fastapi import APIRouter

from .admin import register as register_admin
from .completions import register as register_completions
from .forward import register as register_proxy
from .health import register as register_health


def register_routes(router: APIRouter, server) -> None:
    """Register all route handlers on *router*, using *server* for state."""
    register_completions(router, server)
    register_proxy(router, server)
    register_admin(router, server)
    register_health(router, server)
