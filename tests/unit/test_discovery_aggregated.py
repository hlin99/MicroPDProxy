# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NodeDiscovery aggregated instance support."""

from __future__ import annotations

from xpyd.discovery import NodeDiscovery


class TestDiscoveryAggregatedReady:
    def test_aggregated_only_is_ready(self):
        """All-aggregated deployment: is_ready=True when aggregated nodes are healthy."""
        d = NodeDiscovery(
            prefill_instances=[],
            decode_instances=[],
            aggregated_instances=["10.0.0.1:8000"],
        )
        d.healthy_aggregated.add("10.0.0.1:8000")
        assert d.is_ready is True

    def test_no_nodes_not_ready(self):
        """No healthy nodes: is_ready=False."""
        d = NodeDiscovery(
            prefill_instances=[],
            decode_instances=[],
            aggregated_instances=["10.0.0.1:8000"],
        )
        assert d.is_ready is False

    def test_disaggregated_only_is_ready(self):
        """disaggregated only: is_ready when 1P+1D healthy."""
        d = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000"],
            decode_instances=["10.0.0.2:8000"],
        )
        d.healthy_prefill.add("10.0.0.1:8000")
        d.healthy_decode.add("10.0.0.2:8000")
        assert d.is_ready is True

    def test_disaggregated_missing_decode_not_ready(self):
        """disaggregated missing decode: not ready."""
        d = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000"],
            decode_instances=["10.0.0.2:8000"],
        )
        d.healthy_prefill.add("10.0.0.1:8000")
        assert d.is_ready is False

    def test_mixed_aggregated_and_pd(self):
        """Mixed: aggregated healthy but disaggregated not complete → still ready (aggregated suffices)."""
        d = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000"],
            decode_instances=[],
            aggregated_instances=["10.0.0.3:8000"],
        )
        d.healthy_aggregated.add("10.0.0.3:8000")
        assert d.is_ready is True
