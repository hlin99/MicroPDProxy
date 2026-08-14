#!/usr/bin/env python3
"""Run one deterministic disaggregated endpoint load-test combination."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import aiohttp

MODEL = "/workspace/Meta-Llama-3-8B-Instruct/"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", choices=("completion", "chat"), required=True)
    parser.add_argument("--scheduler", required=True)
    parser.add_argument("--first-token-source", choices=("prefill", "decode"), required=True)
    parser.add_argument("--transport", choices=("nixl", "zmq"), required=True)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    random.seed(20260813)
    semaphore = asyncio.Semaphore(args.concurrency)
    timeout = aiohttp.ClientTimeout(total=180)
    latencies: list[float] = []
    failures: list[str] = []
    completion_tokens = 0

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def send(index: int) -> None:
            nonlocal completion_tokens
            input_words = random.randint(48, 240)
            requested_tokens = random.randint(8, 32)
            prompt = (
                f"Request {index}: continue this deterministic sequence briefly. "
                + " ".join(
                    f"item{(index + offset) % 997}" for offset in range(input_words)
                )
            )
            body: dict[str, object] = {
                "model": MODEL,
                "max_tokens": requested_tokens,
                "temperature": 0,
                "ignore_eos": True,
                "user": f"matrix-user-{index}",
            }
            if args.api == "chat":
                endpoint = "/v1/chat/completions"
                body["messages"] = [{"role": "user", "content": prompt}]
            else:
                endpoint = "/v1/completions"
                body["prompt"] = prompt
            headers = {
                "X-Session-Id": f"matrix-session-{index}",
                "X-Request-Id": (
                    f"{args.transport}-{args.first_token_source}-"
                    f"{args.api}-{args.scheduler}-{index}"
                ),
            }

            async with semaphore:
                started = time.monotonic()
                error: str | None = None
                try:
                    async with session.post(
                        f"http://127.0.0.1:8868{endpoint}",
                        json=body,
                        headers=headers,
                    ) as response:
                        payload = await response.text()
                        if response.status != 200:
                            error = f"HTTP {response.status}: {payload[:300]}"
                        else:
                            parsed = json.loads(payload)
                            choices = parsed.get("choices")
                            usage = parsed.get("usage", {})
                            if not choices:
                                error = "missing choices"
                            elif args.api == "chat":
                                content = choices[0].get("message", {}).get("content")
                                if not content:
                                    error = "missing assistant content"
                            elif not choices[0].get("text"):
                                error = "missing completion text"
                            actual_tokens = usage.get("completion_tokens")
                            if error is None and actual_tokens != requested_tokens:
                                error = (
                                    f"completion_tokens={actual_tokens}, "
                                    f"expected={requested_tokens}"
                                )
                            if isinstance(actual_tokens, int):
                                completion_tokens += actual_tokens
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                finally:
                    latencies.append(time.monotonic() - started)
                if error is not None:
                    failures.append(f"{index}: {error}")

        started = time.monotonic()
        await asyncio.gather(*(send(index) for index in range(args.requests)))
        duration = time.monotonic() - started

    result = {
        "transport": args.transport,
        "first_token_source": args.first_token_source,
        "api": args.api,
        "scheduler": args.scheduler,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "successful": args.requests - len(failures),
        "failed": len(failures),
        "duration_seconds": round(duration, 3),
        "throughput_rps": round(args.requests / duration, 3),
        "completion_tokens": completion_tokens,
        "mean_latency_seconds": round(statistics.mean(latencies), 3),
        "p99_latency_seconds": round(percentile(latencies, 0.99), 3),
        "max_latency_seconds": round(max(latencies), 3),
        "error_examples": failures[:100],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
