# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NodeDiscovery aggregated instance support."""

from __future__ import annotations

from unittest.mock import patch

from xpyd.discovery import NodeDiscovery


class TestDiscoveryAggregatedReady:
    def test_heartbeat_mode_uses_only_configured_roles(self):
        disaggregated = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000"],
            decode_instances=["10.0.0.2:8000"],
        )
        aggregated = NodeDiscovery(
            prefill_instances=[],
            decode_instances=[],
            aggregated_instances=["10.0.0.3:8000"],
        )

        with patch("xpyd.discovery.logger.info") as log_info:
            disaggregated._log_heartbeat_if_due()
            assert log_info.call_args.args == (
                "Node heartbeat | mode=%s | %s",
                "disaggregated",
                "P=0/1 online | D=0/1 online",
            )

            aggregated._log_heartbeat_if_due()
            assert log_info.call_args.args == (
                "Node heartbeat | mode=%s | %s",
                "aggregated",
                "aggregated=0/1 online",
            )

    def test_heartbeat_reports_online_role_counts(self):
        d = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000", "10.0.0.2:8000"],
            decode_instances=["10.0.0.3:8000"],
        )
        d.healthy_prefill.add("10.0.0.1:8000")

        assert (
            d._role_heartbeat("P", d.prefill_instances, d.healthy_prefill)
            == "P=1/2 online"
        )
        assert (
            d._role_heartbeat("D", d.decode_instances, d.healthy_decode)
            == "D=0/1 online"
        )

    def test_aggregated_only_is_ready(self):
        """Aggregated deployment is ready when its nodes are healthy."""
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
        """A healthy aggregated node makes a mixed deployment ready."""
        d = NodeDiscovery(
            prefill_instances=["10.0.0.1:8000"],
            decode_instances=[],
            aggregated_instances=["10.0.0.3:8000"],
        )
        d.healthy_aggregated.add("10.0.0.3:8000")
        assert d.is_ready is True
