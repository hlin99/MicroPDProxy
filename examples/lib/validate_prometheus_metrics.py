#!/usr/bin/env python3
"""Validate Prometheus metrics emitted by a running xPyD proxy."""

from __future__ import annotations

import argparse
import math
import urllib.request
from collections import defaultdict
from pathlib import Path

from prometheus_client.parser import text_string_to_metric_families

CORE_FAMILIES = {
    "proxy_requests": "counter",
    "proxy_request_duration_seconds": "histogram",
    "proxy_active_requests": "gauge",
}
DISAGGREGATED_FAMILIES = {
    "proxy_prefill_duration_seconds": "histogram",
    "proxy_kv_transfer_duration_seconds": "histogram",
    "proxy_decode_duration_seconds": "histogram",
    "proxy_ttft_seconds": "histogram",
    "proxy_tpot_seconds": "histogram",
    "proxy_e2e_latency_seconds": "histogram",
    "proxy_prefill_active_requests": "gauge",
    "proxy_decode_active_requests": "gauge",
    "proxy_prefill_queue_depth": "gauge",
    "proxy_prefill_requests": "counter",
    "proxy_decode_requests": "counter",
    "proxy_instance_errors": "counter",
}
PD_LABELS = {"prefill_instance", "decode_instance", "model"}


def fetch_metrics(url: str) -> str:
    with urllib.request.urlopen(f"{url}/metrics", timeout=10) as response:
        content_type = response.headers.get("Content-Type")
        expected = "text/plain; version=0.0.4; charset=utf-8"
        assert content_type == expected, (content_type, expected)
        return response.read().decode("utf-8")


def parse_metrics(text: str):
    families = {}
    samples = {}
    for family in text_string_to_metric_families(text):
        assert family.name not in families, f"duplicate family: {family.name}"
        families[family.name] = family
        for sample in family.samples:
            key = (sample.name, frozenset(sample.labels.items()))
            assert key not in samples, f"duplicate sample: {sample.name}"
            assert math.isfinite(sample.value), (sample.name, sample.value)
            samples[key] = sample.value
    return families, samples


def sample_total(samples, name: str, **required_labels: str) -> float:
    return sum(
        value
        for (sample_name, labels), value in samples.items()
        if sample_name == name and dict(labels).items() >= required_labels.items()
    )


def assert_family_types(families, mode: str) -> None:
    expected = dict(CORE_FAMILIES)
    if mode == "disaggregated":
        expected.update(DISAGGREGATED_FAMILIES)
    for name, metric_type in expected.items():
        assert name in families, f"missing metric family: {name}"
        assert families[name].type == metric_type, (
            name,
            families[name].type,
            metric_type,
        )
        assert families[name].documentation, f"missing HELP text: {name}"


def assert_histograms(samples) -> None:
    buckets = defaultdict(list)
    for (name, labels), value in samples.items():
        if name.endswith("_bucket"):
            label_dict = dict(labels)
            upper_bound = float(label_dict.pop("le"))
            buckets[
                (name.removesuffix("_bucket"), frozenset(label_dict.items()))
            ].append((upper_bound, value))
    for (name, labels), values in buckets.items():
        ordered = sorted(values)
        counts = [value for _, value in ordered]
        assert counts == sorted(counts), f"non-monotonic histogram buckets: {name}"
        count = samples[(f"{name}_count", labels)]
        assert ordered[-1][0] == math.inf, f"missing +Inf bucket: {name}"
        assert ordered[-1][1] == count, f"histogram count mismatch: {name}"


def assert_delta(
    before,
    after,
    name: str,
    expected: int,
    **labels: str,
) -> None:
    actual = sample_total(after, name, **labels) - sample_total(before, name, **labels)
    assert actual == expected, (name, labels, actual, expected)


def assert_idle(samples, mode: str) -> None:
    assert sample_total(samples, "proxy_active_requests") == 0
    if mode == "disaggregated":
        assert sample_total(samples, "proxy_prefill_active_requests") == 0
        assert sample_total(samples, "proxy_decode_active_requests") == 0
        assert sample_total(samples, "proxy_prefill_queue_depth") == 0


def assert_pd_labels(
    before,
    after,
    expected_prefill: set[str],
    expected_decode: set[str],
):
    selected_prefill = set()
    selected_decode = set()
    for (name, labels), value in after.items():
        if name != "proxy_prefill_requests_total":
            continue
        if value - before.get((name, labels), 0) <= 0:
            continue
        label_dict = dict(labels)
        assert set(label_dict) == PD_LABELS, (name, label_dict)
        assert label_dict["model"] == "facebook/opt-125m", label_dict
        selected_prefill.add(label_dict["prefill_instance"])
        selected_decode.add(label_dict["decode_instance"])
    assert expected_prefill <= selected_prefill, (expected_prefill, selected_prefill)
    assert expected_decode <= selected_decode, (expected_decode, selected_decode)


def compare(args) -> None:
    before_families, before = parse_metrics(Path(args.before).read_text())
    after_text = fetch_metrics(args.url)
    after_families, after = parse_metrics(after_text)
    assert_family_types(before_families, args.mode)
    assert_family_types(after_families, args.mode)
    assert_histograms(after)
    assert_idle(after, args.mode)

    expected = {
        "/v1/completions": args.completion_delta,
        "/v1/chat/completions": args.chat_delta,
    }
    for endpoint, delta in expected.items():
        assert_delta(
            before,
            after,
            "proxy_requests_total",
            delta,
            endpoint=endpoint,
        )
        assert_delta(
            before,
            after,
            "proxy_request_duration_seconds_count",
            delta,
            endpoint=endpoint,
        )

    if args.mode == "disaggregated":
        routed_total = args.completion_delta + args.chat_delta
        labels = {"model": "facebook/opt-125m"}
        for name in (
            "proxy_prefill_requests_total",
            "proxy_decode_requests_total",
        ):
            assert_delta(before, after, name, routed_total, **labels)
        for name in (
            "proxy_prefill_duration_seconds_count",
            "proxy_kv_transfer_duration_seconds_count",
            "proxy_decode_duration_seconds_count",
            "proxy_ttft_seconds_count",
            "proxy_e2e_latency_seconds_count",
        ):
            assert_delta(before, after, name, routed_total, **labels)
        tpot_delta = sample_total(
            after, "proxy_tpot_seconds_count", **labels
        ) - sample_total(before, "proxy_tpot_seconds_count", **labels)
        assert tpot_delta >= 1, ("proxy_tpot_seconds_count", tpot_delta)
        assert_pd_labels(
            before,
            after,
            set(filter(None, args.expected_prefill.split(","))),
            set(filter(None, args.expected_decode.split(","))),
        )


def assert_active(args) -> None:
    _, samples = parse_metrics(fetch_metrics(args.url))
    assert sample_total(samples, "proxy_active_requests") > 0
    if args.mode == "disaggregated":
        active = sample_total(samples, "proxy_prefill_active_requests") + sample_total(
            samples, "proxy_decode_active_requests"
        )
        assert active > 0


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--url", required=True)
    capture_parser.add_argument("--output", required=True)

    active_parser = subparsers.add_parser("active")
    active_parser.add_argument("--url", required=True)
    active_parser.add_argument(
        "--mode", choices=("aggregated", "disaggregated"), required=True
    )

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--url", required=True)
    compare_parser.add_argument("--before", required=True)
    compare_parser.add_argument(
        "--mode", choices=("aggregated", "disaggregated"), required=True
    )
    compare_parser.add_argument("--completion-delta", type=int, required=True)
    compare_parser.add_argument("--chat-delta", type=int, required=True)
    compare_parser.add_argument("--expected-prefill", default="")
    compare_parser.add_argument("--expected-decode", default="")
    args = parser.parse_args()

    if args.command == "capture":
        Path(args.output).write_text(fetch_metrics(args.url))
    elif args.command == "active":
        assert_active(args)
    else:
        compare(args)


if __name__ == "__main__":
    main()
