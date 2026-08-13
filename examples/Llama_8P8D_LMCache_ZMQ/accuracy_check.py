#!/usr/bin/env python3
"""Compare deterministic P-first proxy output with direct decoder output."""

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
    parser.add_argument("--api", choices=("completion", "chat"), required=True)
    parser.add_argument(
        "--first-token-source", choices=("prefill", "decode"), required=True
    )
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    random.seed(20260813)
    endpoint = (
        "/v1/chat/completions" if args.api == "chat" else "/v1/completions"
    )
    mismatches: list[dict[str, object]] = []
    timeout = aiohttp.ClientTimeout(total=180)
    started = time.monotonic()

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for index in range(args.requests):
            words = random.randint(32, 128)
            output_tokens = random.randint(8, 16)
            prompt = (
                f"Accuracy request {index}: continue this sequence. "
                + " ".join(
                    f"item{(index + offset) % 997}" for offset in range(words)
                )
            )
            body: dict[str, object] = {
                "model": MODEL,
                "max_tokens": output_tokens,
                "temperature": 0,
                "ignore_eos": True,
                "skip_special_tokens": False,
                "user": f"accuracy-user-{index}",
            }
            if args.api == "chat":
                body["messages"] = [{"role": "user", "content": prompt}]
            else:
                body["prompt"] = prompt
            headers = {
                "X-Session-Id": f"accuracy-session-{index}",
                "X-Request-Id": f"accuracy-{args.api}-{index}",
            }

            async def post(port: int) -> dict:
                async with session.post(
                    f"http://127.0.0.1:{port}{endpoint}",
                    json=body,
                    headers=headers,
                ) as response:
                    payload = await response.text()
                    if response.status != 200:
                        raise RuntimeError(
                            f"port {port} returned HTTP {response.status}: {payload[:300]}"
                        )
                    return json.loads(payload)

            proxy_output = await post(8868)
            direct_output = await post(8200 + index % 8)
            if args.api == "chat":
                proxy_text = proxy_output["choices"][0]["message"]["content"]
                direct_text = direct_output["choices"][0]["message"]["content"]
            else:
                proxy_text = proxy_output["choices"][0]["text"]
                direct_text = direct_output["choices"][0]["text"]
            proxy_tokens = proxy_output.get("usage", {}).get("completion_tokens")
            direct_tokens = direct_output.get("usage", {}).get("completion_tokens")
            if proxy_text != direct_text or proxy_tokens != direct_tokens:
                mismatches.append(
                    {
                        "index": index,
                        "proxy_text": proxy_text,
                        "direct_text": direct_text,
                        "proxy_completion_tokens": proxy_tokens,
                        "direct_completion_tokens": direct_tokens,
                    }
                )

    result = {
        "transport": "zmq",
        "first_token_source": args.first_token_source,
        "api": args.api,
        "requests": args.requests,
        "exact_matches": args.requests - len(mismatches),
        "mismatches": len(mismatches),
        "duration_seconds": round(time.monotonic() - started, 3),
        "mismatch_examples": mismatches[:20],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
