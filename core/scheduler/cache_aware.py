# SPDX-License-Identifier: Apache-2.0
"""Cache-Aware Routing scheduling policy.

Routes requests with similar prompt prefixes to the same worker,
optimizing for prefix cache hits on inference backends.
"""

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
    """Route requests to workers based on prompt prefix hash.

    Hashes the first *prefix_length* characters of the prompt to
    deterministically select a worker, so requests sharing the same
    prefix hit the same backend and benefit from KV-cache reuse.

    Parameters
    ----------
    workers:
        Initial list of worker addresses.
    prefix_length:
        Number of characters to consider for prefix hashing.
        Defaults to 256.
    """

    def __init__(
        self,
        workers: Optional[list[str]] = None,
        prefix_length: int = DEFAULT_PREFIX_LENGTH,
    ):
        super().__init__()
        self._workers: list[str] = list(workers) if workers else []
        self._prefix_length = prefix_length

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prefix_hash(self, prompt: str) -> int:
        """Hash the first *prefix_length* characters of *prompt*."""
        prefix = prompt[: self._prefix_length]
        return int(
            hashlib.md5(prefix.encode()).hexdigest(), 16  # noqa: S324
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_worker(self, addr: str) -> None:
        """Add a worker to the pool."""
        with self.lock:
            if addr not in self._workers:
                self._workers.append(addr)

    def remove_worker(self, addr: str) -> None:
        """Remove a worker from the pool."""
        with self.lock:
            try:
                self._workers.remove(addr)
            except ValueError:
                pass

    def select(
        self,
        *,
        prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Select a worker based on prompt prefix hash.

        Returns ``None`` when no workers are available or prompt is
        ``None``.
        """
        with self.lock:
            if not self._workers:
                return None
            if len(self._workers) == 1:
                return self._workers[0]
            if prompt is None:
                prompt = ""
            h = self._prefix_hash(prompt)
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
        """Schedule using prompt prefix for cache-aware routing."""
        return self.select(prompt=prompt)
