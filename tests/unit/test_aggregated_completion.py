# SPDX-License-Identifier: Apache-2.0
"""Unit tests for aggregated-role completion fast path."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from xpyd.registry import InstanceRegistry


class TestIsAggregatedModel:
    """Test _is_aggregated_model detection."""

    def test_aggregated_model_detected(self):
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000"]}
        from xpyd.proxy import Proxy

        assert Proxy._is_aggregated_model(proxy, "qwen-2") is True

    def test_disaggregated_model_not_aggregated(self):
        proxy = MagicMock()
        proxy.aggregated_instances = {}
        from xpyd.proxy import Proxy

        assert Proxy._is_aggregated_model(proxy, "llama-3") is False

    def test_empty_aggregated_list_not_aggregated(self):
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": []}
        proxy.registry = None
        from xpyd.proxy import Proxy

        assert Proxy._is_aggregated_model(proxy, "qwen-2") is False

    def test_auto_discovered_aggregated_model_detected(self):
        from xpyd.proxy import Proxy

        registry = InstanceRegistry()
        registry.add("aggregated", "10.0.0.1:8000")
        registry.update_model("10.0.0.1:8000", "qwen-2")
        proxy = MagicMock()
        proxy.aggregated_instances = {"": ["10.0.0.1:8000"]}
        proxy.registry = registry

        assert Proxy._is_aggregated_model(proxy, "qwen-2") is True


class TestScheduleAggregated:
    """Test schedule_aggregated picks from registry."""

    def setup_method(self):
        self.reg = InstanceRegistry()
        self.reg.add("aggregated", "10.0.0.1:8000", model="qwen-2")
        self.reg.add("aggregated", "10.0.0.2:8000", model="qwen-2")
        self.reg.mark_healthy("10.0.0.1:8000")
        self.reg.mark_healthy("10.0.0.2:8000")

    def test_schedule_aggregated_returns_instance(self):
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {}
        proxy._aggregated_rr_counters = {}
        from xpyd.proxy import Proxy

        result = Proxy.schedule_aggregated(proxy, "qwen-2")
        assert result in ("10.0.0.1:8000", "10.0.0.2:8000")

    def test_schedule_aggregated_no_model(self):
        proxy = MagicMock()
        proxy.aggregated_instances = {}
        proxy.registry = self.reg
        proxy._aggregated_rr_counters = {}
        from xpyd.proxy import Proxy

        result = Proxy.schedule_aggregated(proxy, "nonexistent")
        assert result is None

    def test_schedule_auto_discovered_aggregated_model(self):
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        reg = InstanceRegistry()
        reg.add("aggregated", "10.0.0.3:8000")
        reg.update_model("10.0.0.3:8000", "qwen-2")
        reg.mark_healthy("10.0.0.3:8000")
        proxy = MagicMock()
        proxy.aggregated_instances = {"": ["10.0.0.3:8000"]}
        proxy.registry = reg
        proxy.scheduling_policy = RoundRobinSchedulingPolicy(registry=reg)
        proxy.model_schedulers = {}
        proxy._aggregated_rr_counters = {}
        proxy._aggregated_instances_for_model = (
            lambda model: Proxy._aggregated_instances_for_model(proxy, model)
        )

        assert Proxy.schedule_aggregated(proxy, "qwen-2") == "10.0.0.3:8000"


class TestScheduleAggregatedCompletion:
    """Test single load accounting for aggregated."""

    def test_single_accounting(self):
        registry = MagicMock()
        proxy = MagicMock()
        proxy.registry = registry
        from xpyd.proxy import Proxy

        Proxy.schedule_aggregated_completion(proxy, "10.0.0.1:8000", req_len=100)
        registry.decrement_active_requests.assert_called_once_with(
            "10.0.0.1:8000",
        )

    def test_no_registry(self):
        proxy = MagicMock()
        proxy.registry = None
        from xpyd.proxy import Proxy

        # Should not raise even without registry
        Proxy.schedule_aggregated_completion(proxy, "10.0.0.1:8000", req_len=100)


class TestPerModelSchedulerDispatch:
    """Test per-model scheduler fallback chain."""

    def setup_method(self):
        self.reg = InstanceRegistry()
        self.reg.add("aggregated", "10.0.0.1:8000", model="qwen-2")
        self.reg.add("aggregated", "10.0.0.2:8000", model="qwen-2")
        self.reg.mark_healthy("10.0.0.1:8000")
        self.reg.mark_healthy("10.0.0.2:8000")

    def test_explicit_loadbalanced_picks_lowest_load(self):
        """model_schedulers={'qwen-2': 'loadbalanced'} uses load-balanced."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        # Global policy is RR, but model-level overrides to loadbalanced
        policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {"qwen-2": "loadbalanced"}
        proxy._aggregated_rr_counters = {}
        proxy._schedule_aggregated_load_balanced = (
            lambda available: Proxy._schedule_aggregated_load_balanced(proxy, available)
        )

        # Give instance 1 more load
        self.reg.increment_active_requests("10.0.0.1:8000")
        self.reg.increment_active_requests("10.0.0.1:8000")

        result = Proxy.schedule_aggregated(proxy, "qwen-2")
        # Should pick instance 2 (lower load)
        assert result == "10.0.0.2:8000"

    def test_explicit_roundrobin_cycles(self):
        """model_schedulers={'qwen-2': 'roundrobin'} uses round-robin."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import LoadBalancedScheduler

        # Global is loadbalanced, but model overrides to roundrobin
        policy = LoadBalancedScheduler(
            prefill_instances=[],
            decode_instances=[],
            registry=self.reg,
        )
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {"qwen-2": "roundrobin"}
        proxy._aggregated_rr_counters = {}

        results = []
        for _ in range(4):
            r = Proxy.schedule_aggregated(proxy, "qwen-2")
            results.append(r)
        # Should alternate between the two instances
        assert results[0] != results[1]
        assert results[0] == results[2]

    def test_fallback_to_global_loadbalanced(self):
        """No model-level scheduler, global is LoadBalanced → load-balanced."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import LoadBalancedScheduler

        policy = LoadBalancedScheduler(
            prefill_instances=[],
            decode_instances=[],
            registry=self.reg,
        )
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {}
        proxy._aggregated_rr_counters = {}
        proxy._schedule_aggregated_load_balanced = (
            lambda available: Proxy._schedule_aggregated_load_balanced(proxy, available)
        )

        self.reg.increment_active_requests("10.0.0.1:8000")
        result = Proxy.schedule_aggregated(proxy, "qwen-2")
        assert result == "10.0.0.2:8000"

    def test_fallback_global_rr_uses_rr(self):
        """No model-level, global is RR → uses round-robin (not load_balanced)."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {}
        proxy._aggregated_rr_counters = {}

        results = []
        for _ in range(4):
            r = Proxy.schedule_aggregated(proxy, "qwen-2")
            results.append(r)
        # Round-robin: alternates
        assert results[0] != results[1]
        assert results[0] == results[2]

    def test_consistent_hash_keeps_session_on_same_instance(self):
        """Consistent hash keeps repeated session IDs on one aggregated instance."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        proxy = MagicMock()
        proxy.aggregated_instances = {
            "qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"],
        }
        proxy.registry = self.reg
        proxy.scheduling_policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy.model_schedulers = {"qwen-2": "consistent_hash"}
        proxy._aggregated_policies = {}
        proxy.tokenizer = MagicMock()
        proxy._get_aggregated_policy = lambda model, strategy, instances: (
            Proxy._get_aggregated_policy(proxy, model, strategy, instances)
        )

        first = Proxy.schedule_aggregated(
            proxy,
            "qwen-2",
            header="session-123",
        )
        second = Proxy.schedule_aggregated(
            proxy,
            "qwen-2",
            header="session-123",
        )

        assert first == second

    def test_power_of_two_picks_lower_load_from_sampled_pair(self):
        """Power-of-two compares live loads for its sampled aggregated pair."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        proxy = MagicMock()
        proxy.aggregated_instances = {
            "qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"],
        }
        proxy.registry = self.reg
        proxy.scheduling_policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy.model_schedulers = {"qwen-2": "power_of_two"}
        proxy._aggregated_policies = {}
        proxy.tokenizer = MagicMock()
        proxy._get_aggregated_policy = lambda model, strategy, instances: (
            Proxy._get_aggregated_policy(proxy, model, strategy, instances)
        )
        for _ in range(3):
            self.reg.increment_active_requests("10.0.0.1:8000")

        with patch(
            "xpyd.scheduler.power_of_two.random.sample",
            return_value=["10.0.0.1:8000", "10.0.0.2:8000"],
        ):
            result = Proxy.schedule_aggregated(proxy, "qwen-2")

        assert result == "10.0.0.2:8000"

    def test_cache_aware_keeps_same_prefix_on_same_instance(self):
        """Cache-aware routing keeps repeated prefixes on one aggregated instance."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        proxy = MagicMock()
        proxy.aggregated_instances = {
            "qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"],
        }
        proxy.registry = self.reg
        proxy.scheduling_policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy.model_schedulers = {"qwen-2": "cache_aware"}
        proxy._aggregated_policies = {}
        proxy.tokenizer = MagicMock()
        proxy.tokenizer.encode.side_effect = lambda prompt: list(
            prompt.encode(),
        )
        proxy._get_aggregated_policy = lambda model, strategy, instances: (
            Proxy._get_aggregated_policy(proxy, model, strategy, instances)
        )

        first = Proxy.schedule_aggregated(
            proxy,
            "qwen-2",
            prompt="shared prefix and request one",
        )
        second = Proxy.schedule_aggregated(
            proxy,
            "qwen-2",
            prompt="shared prefix and request one",
        )

        assert first == second


class TestScheduleAggregatedRoundRobinMultiple:
    """Test round-robin rotates through aggregated instances."""

    def setup_method(self):
        self.reg = InstanceRegistry()
        self.reg.add("aggregated", "10.0.0.1:8000", model="qwen-2")
        self.reg.add("aggregated", "10.0.0.2:8000", model="qwen-2")
        self.reg.mark_healthy("10.0.0.1:8000")
        self.reg.mark_healthy("10.0.0.2:8000")

    def test_schedule_aggregated_round_robin_multiple_calls(self):
        """Multiple calls rotate through available instances."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = policy
        proxy.model_schedulers = {}
        proxy._aggregated_rr_counters = {}

        results = [Proxy.schedule_aggregated(proxy, "qwen-2") for _ in range(4)]
        assert results == [
            results[0],
            results[1],
            results[0],
            results[1],
        ]
        assert results[0] != results[1]


class TestStreamingErrorHandling:
    """Test _ok flag logic in _handle_aggregated_completion streaming path."""

    def test_record_failure_not_success_on_exception(self):
        """When streaming raises, only record_failure is called."""
        registry = MagicMock()
        instance = "10.0.0.1:8000"

        # Simulate the wrapped() generator logic from _handle_aggregated_completion
        _ok = True
        try:
            raise RuntimeError("backend error")
        except Exception:
            _ok = False
            registry.record_failure(instance)

        # finally block logic
        if _ok:
            registry.record_success(instance)

        registry.record_failure.assert_called_once_with(instance)
        registry.record_success.assert_not_called()

    def test_cancelled_error_no_record_success(self):
        """CancelledError sets _ok=False, record_success not called."""
        registry = MagicMock()
        instance = "10.0.0.1:8000"

        _ok = True
        try:
            raise asyncio.CancelledError()
        except asyncio.CancelledError:
            _ok = False

        # finally block
        if _ok:
            registry.record_success(instance)

        registry.record_success.assert_not_called()


class TestScheduleAggregatedCompletionReal:
    """Test schedule_aggregated_completion with real registry."""

    def test_with_real_loadbalanced_scheduler(self):
        """schedule_aggregated_completion with real registry decrements active requests."""
        from xpyd.proxy import Proxy

        reg = InstanceRegistry()
        reg.add("aggregated", "10.0.0.1:8000", model="qwen-2")
        reg.mark_healthy("10.0.0.1:8000")
        reg.increment_active_requests("10.0.0.1:8000")

        proxy = MagicMock()
        proxy.registry = reg

        Proxy.schedule_aggregated_completion(proxy, "10.0.0.1:8000", req_len=100)
        assert reg.get_active_requests("10.0.0.1:8000") == 0


class TestScheduleAggregatedUnderscoreAlias:
    """Test underscore alias for load_balanced scheduler."""

    def setup_method(self):
        self.reg = InstanceRegistry()
        self.reg.add("aggregated", "10.0.0.1:8000", model="qwen-2")
        self.reg.add("aggregated", "10.0.0.2:8000", model="qwen-2")
        self.reg.mark_healthy("10.0.0.1:8000")
        self.reg.mark_healthy("10.0.0.2:8000")

    def test_underscore_alias_loadbalanced(self):
        """'load_balanced' (with underscore) correctly maps to loadbalanced."""
        from xpyd.proxy import Proxy
        from xpyd.scheduler import RoundRobinSchedulingPolicy

        proxy = MagicMock()
        proxy.aggregated_instances = {"qwen-2": ["10.0.0.1:8000", "10.0.0.2:8000"]}
        proxy.registry = self.reg
        proxy.scheduling_policy = RoundRobinSchedulingPolicy(registry=self.reg)
        proxy.model_schedulers = {"qwen-2": "load_balanced"}
        proxy._aggregated_rr_counters = {}
        proxy._schedule_aggregated_load_balanced = (
            lambda available: Proxy._schedule_aggregated_load_balanced(proxy, available)
        )

        self.reg.increment_active_requests("10.0.0.1:8000")
        result = Proxy.schedule_aggregated(proxy, "qwen-2")
        assert result == "10.0.0.2:8000"
