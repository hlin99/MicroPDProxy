# SPDX-License-Identifier: Apache-2.0
"""Cache-aware routing policy that optimizes for prefix cache hits."""

import hashlib
import itertools
import logging
from typing import Optional

try:
    from .scheduler_base import SchedulingPolicy
except ImportError:
    from scheduler_base import SchedulingPolicy

logger = logging.getLogger(__name__)

DEFAULT_PREFIX_LENGTH = 256


class CacheAwarePolicy(SchedulingPolicy):
    """Route similar prompts to the same worker for prefix cache reuse.

    Hashes the first *prefix_length* characters of the prompt text to
    deterministically select a worker.  Requests sharing the same prefix
    will land on the same node, maximising KV-cache hit rates.

    YAML config::

        scheduling: cache_aware
        cache_aware:
          prefix_length: 256
    """

    def __init__(
        self,
        workers: Optional[list[str]] = None,
        prefix_length: int = DEFAULT_PREFIX_LENGTH,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._workers: list[str] = list(workers) if workers else []
        self._prefix_length = prefix_length

    # ------------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------------

    def add_worker(self, addr: str) -> None:
        """Add a worker to the pool."""
        with self.lock:
            if addr not in self._workers:
                self._workers.append(addr)

    def remove_worker(self, addr: str) -> None:
        """Remove a worker from the pool."""
        with self.lock:
            self._workers = [w for w in self._workers if w != addr]

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(self, *, prompt: Optional[str] = None) -> Optional[str]:
        """Select a worker based on prompt prefix hash.

        Returns ``None`` when no workers are available.
        """
        with self.lock:
            if not self._workers:
                return None
            if len(self._workers) == 1:
                return self._workers[0]

            prefix = (prompt or "")[:self._prefix_length]
            h = int(
                hashlib.md5(prefix.encode()).hexdigest(),  # noqa: S324
                16,
            )
            return self._workers[h % len(self._workers)]

    # ------------------------------------------------------------------
    # SchedulingPolicy interface
    # ------------------------------------------------------------------

    def schedule(
        self,
        cycler: itertools.cycle,
        is_prompt: Optional[bool] = None,
        request_len: Optional[int] = None,
        max_tokens: Optional[int] = None,
        *,
        prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Schedule using prompt prefix for cache-aware routing.

        If a registry is attached, refreshes the worker list from
        available instances before selecting.
        """
        if self._registry is not None:
            available = self._registry.get_available_instances("decode")
            with self.lock:
                self._workers = list(available)

        return self.select(prompt=prompt)
