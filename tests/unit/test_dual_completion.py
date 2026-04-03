# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dual-role completion fast path."""

from __future__ import annotations

from unittest.mock import MagicMock

from xpyd.registry import InstanceRegistry


class TestIsDualModel:
    """Test _is_dual_model detection."""

    def test_dual_model_detected(self):
        proxy = MagicMock()
        proxy.dual_instances = {"qwen-2": ["10.0.0.1:8000"]}
        from xpyd.proxy import Proxy
        assert Proxy._is_dual_model(proxy, "qwen-2") is True

    def test_pd_model_not_dual(self):
        proxy = MagicMock()
        proxy.dual_instances = {}
        from xpyd.proxy import Proxy
        assert Proxy._is_dual_model(proxy, "llama-3") is False

    def test_empty_dual_list_not_dual(self):
        proxy = MagicMock()
        proxy.dual_instances = {"qwen-2": []}
        from xpyd.proxy import Proxy
        assert Proxy._is_dual_model(proxy, "qwen-2") is False


class TestScheduleDual:
    """Test schedule_dual picks from registry."""

    def setup_method(self):
        self.reg = InstanceRegistry()
        self.reg.add("dual", "10.0.0.1:8000", model="qwen-2")
        self.reg.add("dual", "10.0.0.2:8000", model="qwen-2")
        self.reg.mark_healthy("10.0.0.1:8000")
        self.reg.mark_healthy("10.0.0.2:8000")

    def test_schedule_dual_returns_instance(self):
        from xpyd.scheduler import RoundRobinSchedulingPolicy
        policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy = MagicMock()
        proxy.dual_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {}
        proxy._get_model_scheduler = lambda model: policy
        from xpyd.proxy import Proxy
        result = Proxy.schedule_dual(proxy, "qwen-2")
        assert result in ("10.0.0.1:8000", "10.0.0.2:8000")

    def test_schedule_dual_no_model(self):
        proxy = MagicMock()
        proxy.dual_instances = {}
        proxy.registry = self.reg
        from xpyd.proxy import Proxy
        result = Proxy.schedule_dual(proxy, "nonexistent")
        assert result is None


class TestScheduleDualCompletion:
    """Test single load accounting for dual."""

    def test_single_accounting(self):
        policy = MagicMock()
        proxy = MagicMock()
        proxy.scheduling_policy = policy
        from xpyd.proxy import Proxy
        Proxy.schedule_dual_completion(proxy, "10.0.0.1:8000", req_len=100)
        policy.schedule_completion.assert_called_once_with(
            prefill_instance=None,
            decode_instance="10.0.0.1:8000",
            req_len=100,
        )


class TestPerModelScheduler:
    """Test per-model scheduler selection."""

    def test_model_scheduler_used(self):
        model_sched = MagicMock()
        global_sched = MagicMock()
        proxy = MagicMock()
        proxy.model_schedulers = {"qwen-2": model_sched}
        proxy.scheduling_policy = global_sched
        from xpyd.proxy import Proxy
        result = Proxy._get_model_scheduler(proxy, "qwen-2")
        assert result is model_sched

    def test_fallback_to_global(self):
        global_sched = MagicMock()
        proxy = MagicMock()
        proxy.model_schedulers = {}
        proxy.scheduling_policy = global_sched
        from xpyd.proxy import Proxy
        result = Proxy._get_model_scheduler(proxy, "unknown-model")
        assert result is global_sched
