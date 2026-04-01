# SPDX-License-Identifier: Apache-2.0
"""Tests for CacheAwarePolicy."""

from core.scheduler.cache_aware import CacheAwarePolicy


class TestCacheAwarePolicy:
    """Unit tests for cache-aware routing policy."""

    def test_same_prefix_same_worker(self):
        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        # Build a prompt with >256 whitespace-separated tokens
        base_tokens = [f"token{i}" for i in range(300)]
        prompt_a = " ".join(base_tokens)
        prompt_b = " ".join(base_tokens + ["extra", "suffix", "here"])
        w1 = policy.select(prompt=prompt_a)
        w2 = policy.select(prompt=prompt_b)
        assert w1 == w2  # same first 256 tokens → same worker

    def test_different_prefix_can_differ(self):
        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        selected = set()
        for i in range(50):
            w = policy.select(prompt=f"Unique prompt {i} " * 100)
            selected.add(w)
        assert len(selected) > 1

    def test_no_workers_returns_none(self):
        policy = CacheAwarePolicy(workers=[], prefix_length=256)
        assert policy.select(prompt="hello") is None

    def test_single_worker(self):
        policy = CacheAwarePolicy(workers=["w1"], prefix_length=256)
        assert policy.select(prompt="anything") == "w1"
        assert policy.select(prompt="something else") == "w1"

    def test_none_prompt(self):
        policy = CacheAwarePolicy(workers=["w1", "w2"], prefix_length=256)
        result = policy.select(prompt=None)
        assert result in ("w1", "w2")

    def test_empty_prompt(self):
        policy = CacheAwarePolicy(workers=["w1", "w2"], prefix_length=256)
        result = policy.select(prompt="")
        assert result in ("w1", "w2")

    def test_prompt_shorter_than_prefix_length(self):
        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        result = policy.select(prompt="short")
        assert result in ("w1", "w2", "w3")
        # Same short prompt → same worker
        assert policy.select(prompt="short") == result

    def test_deterministic(self):
        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        prompt = "deterministic test prompt " * 20
        results = {policy.select(prompt=prompt) for _ in range(10)}
        assert len(results) == 1

    def test_add_worker(self):
        policy = CacheAwarePolicy(workers=["w1", "w2"], prefix_length=256)
        policy.add_worker("w3")
        # Should still work
        result = policy.select(prompt="test")
        assert result in ("w1", "w2", "w3")

    def test_remove_worker(self):
        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        policy.remove_worker("w2")
        result = policy.select(prompt="test")
        assert result in ("w1", "w3")

    def test_add_duplicate_worker(self):
        policy = CacheAwarePolicy(workers=["w1", "w2"], prefix_length=256)
        policy.add_worker("w1")
        assert len(policy._workers) == 2

    def test_remove_nonexistent_worker(self):
        policy = CacheAwarePolicy(workers=["w1"], prefix_length=256)
        policy.remove_worker("w99")  # should not raise
        assert policy.select(prompt="test") == "w1"

    def test_schedule_interface(self):
        """schedule() delegates to select()."""
        import itertools

        policy = CacheAwarePolicy(workers=["w1", "w2", "w3"], prefix_length=256)
        prompt = "The quick brown fox " * 50
        cycler = itertools.cycle(["w1", "w2", "w3"])
        result = policy.schedule(cycler, prompt=prompt)
        assert result == policy.select(prompt=prompt)

    def test_custom_prefix_length(self):
        workers = ["w1", "w2", "w3"]
        # Very short prefix: only first 2 tokens matter
        policy = CacheAwarePolicy(workers=workers, prefix_length=2)
        w1 = policy.select(prompt="hello world AAAA BBBB")
        w2 = policy.select(prompt="hello world CCCC DDDD")
        assert w1 == w2  # same 2-token prefix

    def test_default_prefix_length(self):
        policy = CacheAwarePolicy(workers=["w1"])
        assert policy._prefix_length == 256
