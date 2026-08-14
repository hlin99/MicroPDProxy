#!/usr/bin/env python3
"""Send varied concurrent requests and save a compact benchmark result."""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

import aiohttp

MODEL = "/workspace/Meta-Llama-3-8B-Instruct/"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", required=True)
    parser.add_argument("--requests", type=int, default=64)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=Path("bench_results"))
    args = parser.parse_args()

    random.seed(20260813)
    semaphore = asyncio.Semaphore(args.concurrency)
    timeout = aiohttp.ClientTimeout(total=180)
    latencies: list[float] = []
    errors: list[str] = []

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async def send(index: int) -> None:
            words = random.randint(48, 240)
            output_tokens = random.randint(8, 40)
            prompt = (
                f"Request {index}: summarize this sequence. "
                + " ".join(f"item{(index + offset) % 997}" for offset in range(words))
            )
            body = {
                "model": MODEL,
                "prompt": prompt,
                "max_tokens": output_tokens,
                "temperature": 0,
                "user": f"scheduler-user-{index}",
            }
            headers = {"X-Session-Id": f"scheduler-session-{index}"}
            async with semaphore:
                started = time.monotonic()
                try:
                    async with session.post(
                        "http://127.0.0.1:8868/v1/completions",
                        json=body,
                        headers=headers,
                    ) as response:
                        payload = await response.text()
                        if response.status != 200:
                            errors.append(f"{index}: HTTP {response.status}: {payload[:200]}")
                        else:
                            parsed = json.loads(payload)
                            if not parsed.get("choices"):
                                errors.append(f"{index}: missing choices")
                except Exception as exc:
                    errors.append(f"{index}: {type(exc).__name__}: {exc}")
                finally:
                    latencies.append(time.monotonic() - started)

        started = time.monotonic()
        await asyncio.gather(*(send(index) for index in range(args.requests)))
        duration = time.monotonic() - started

    result = {
        "scheduler": args.scheduler,
        "requests": args.requests,
        "successful": args.requests - len(errors),
        "failed": len(errors),
        "duration_seconds": round(duration, 3),
        "throughput_rps": round(args.requests / duration, 3),
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 3),
        "max_latency_seconds": round(max(latencies), 3),
        "errors": errors,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{args.scheduler}.json"
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
