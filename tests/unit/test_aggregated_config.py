# SPDX-License-Identifier: Apache-2.0
"""Unit tests for aggregated-role instance configuration."""

from __future__ import annotations

import pytest

from xpyd.config import InstanceEntry, ProxyConfig


class TestInstanceEntryAggregatedRole:
    """InstanceEntry accepts role='aggregated'."""

    def test_aggregated_role_valid(self):
        entry = InstanceEntry(address="10.0.0.1:8000", role="aggregated", model="qwen-2")
        assert entry.role == "aggregated"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValueError, match="role must be"):
            InstanceEntry(address="10.0.0.1:8000", role="unknown")


class TestAggregatedInstancesConfig:
    """Config parsing for aggregated instances."""

    def test_format2_aggregated_instances(self):
        cfg = ProxyConfig(
            instances=[
                {"address": "10.0.0.1:8000", "role": "aggregated", "model": "qwen-2"},
                {"address": "10.0.0.2:8000", "role": "aggregated", "model": "qwen-2"},
            ],
        )
        assert len(cfg.instances) == 2
        assert all(e.role == "aggregated" for e in cfg.instances)

    def test_format3_aggregated_shorthand(self):
        cfg = ProxyConfig(
            models=[
                {
                    "name": "qwen-2",
                    "aggregated": ["10.0.0.1:8000", "10.0.0.2:8000"],
                },
            ],
        )
        assert cfg.instances is not None
        assert len(cfg.instances) == 2
        assert all(e.role == "aggregated" for e in cfg.instances)
        assert cfg.models is None

    def test_format3_aggregated_with_scheduler(self):
        cfg = ProxyConfig(
            models=[
                {
                    "name": "qwen-2",
                    "aggregated": ["10.0.0.1:8000"],
                    "scheduler": "round_robin",
                },
            ],
        )
        assert cfg._model_schedulers == {"qwen-2": "round_robin"}

    def test_format3_mixed_models_aggregated_and_pd(self):
        """Different models can use aggregated vs disaggregated."""
        cfg = ProxyConfig(
            models=[
                {
                    "name": "llama-3",
                    "prefill": ["10.0.0.1:8000"],
                    "decode": ["10.0.0.2:8000"],
                },
                {
                    "name": "qwen-2",
                    "aggregated": ["10.0.0.3:8000", "10.0.0.4:8000"],
                },
            ],
        )
        assert cfg.instances is not None
        roles = {e.model: e.role for e in cfg.instances}
        assert roles["llama-3"] in ("prefill", "decode")
        assert roles["qwen-2"] == "aggregated"


class TestAggregatedDisaggregatedMutualExclusivity:
    """Same model cannot mix aggregated and disaggregated."""

    def test_format2_mixing_rejected(self):
        with pytest.raises(ValueError, match="mixes aggregated and prefill/decode"):
            ProxyConfig(
                instances=[
                    {"address": "10.0.0.1:8000", "role": "aggregated", "model": "qwen-2"},
                    {"address": "10.0.0.2:8000", "role": "decode", "model": "qwen-2"},
                ],
            )

    def test_format3_mixing_rejected(self):
        with pytest.raises(ValueError, match="cannot have both 'aggregated' and"):
            ProxyConfig(
                models=[
                    {
                        "name": "qwen-2",
                        "aggregated": ["10.0.0.1:8000"],
                        "prefill": ["10.0.0.2:8000"],
                    },
                ],
            )

    def test_format3_mixing_aggregated_decode_rejected(self):
        with pytest.raises(ValueError, match="cannot have both 'aggregated' and"):
            ProxyConfig(
                models=[
                    {
                        "name": "qwen-2",
                        "aggregated": ["10.0.0.1:8000"],
                        "decode": ["10.0.0.2:8000"],
                    },
                ],
            )


class TestRequireDecodeWithAggregated:
    """_require_decode accepts aggregated as alternative to decode."""

    def test_aggregated_only_valid(self):
        cfg = ProxyConfig(
            instances=[
                {"address": "10.0.0.1:8000", "role": "aggregated", "model": "qwen-2"},
            ],
        )
        assert len(cfg.instances) == 1

    def test_disaggregated_without_decode_rejected(self):
        with pytest.raises(
            ValueError, match="requires at least one prefill and one decode"
        ):
            ProxyConfig(
                instances=[
                    {"address": "10.0.0.1:8000", "role": "prefill", "model": "llama-3"},
                ],
            )

    def test_legacy_format_unchanged(self):
        """Old prefill/decode format still works."""
        cfg = ProxyConfig(
            model="llama-3",
            decode=["10.0.0.1:8000"],
        )
        assert cfg.model == "llama-3"
        assert cfg.instances is None


class TestConfigEdgeCases:
    """Edge cases for aggregated config validation."""

    def test_disaggregated_without_prefill_rejected(self):
        """Model with only decode instances (no prefill) is rejected."""
        with pytest.raises(ValueError, match="requires at least one prefill"):
            ProxyConfig(
                instances=[
                    {"address": "10.0.0.1:8000", "role": "decode", "model": "llama-3"},
                ],
            )

    def test_invalid_scheduler_name_accepted_by_config(self):
        """Config accepts unknown scheduler names (validation happens at runtime)."""
        cfg = ProxyConfig(
            models=[
                {
                    "name": "qwen-2",
                    "aggregated": ["10.0.0.1:8000"],
                    "scheduler": "nonexistent_strategy",
                },
            ],
        )
        assert cfg._model_schedulers == {"qwen-2": "nonexistent_strategy"}

    def test_scheduler_alias_round_robin(self):
        """'round_robin' (underscore) is accepted in config."""
        cfg = ProxyConfig(
            models=[
                {
                    "name": "qwen-2",
                    "aggregated": ["10.0.0.1:8000"],
                    "scheduler": "round_robin",
                },
            ],
        )
        assert cfg._model_schedulers == {"qwen-2": "round_robin"}
