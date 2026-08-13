# SPDX-License-Identifier: Apache-2.0
"""Completion route handlers."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from asyncio import CancelledError
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from xpyd.errors import INVALID_REQUEST, PROXY_ERROR, error_response

if TYPE_CHECKING:
    from xpyd.proxy import Proxy

from xpyd.metrics import (
    FirstTokenTracker,
    proxy_decode_active_requests,
    proxy_decode_requests_total,
    proxy_instance_errors_total,
    proxy_prefill_active_requests,
    proxy_prefill_requests_total,
    record_pd_metrics,
    track_request_end,
    track_request_start,
)

logger = logging.getLogger("xpyd.proxy")


# ---------------------------------------------------------------------------
# Pure helper functions (no server dependency or explicit server param)
# ---------------------------------------------------------------------------


def validate_completion_request(request: dict, is_chat: bool) -> JSONResponse | None:
    """Validate required fields. Returns JSONResponse on error, None on success."""
    if is_chat:
        if "messages" not in request:
            return error_response("Missing required field: messages", INVALID_REQUEST, 400)
        if not isinstance(request["messages"], list):
            return error_response("Field messages must be a list", INVALID_REQUEST, 400)
    else:
        if "prompt" not in request:
            return error_response("Missing required field: prompt", INVALID_REQUEST, 400)
    return None


def extract_prompt_info(request: dict, is_chat: bool, server: Proxy) -> tuple[int, int, str]:
    """Extract prompt metrics. Returns (total_length, max_tokens, prompt_text)."""
    if is_chat:
        total_length = 0
        prompt_parts = []
        for msg in request["messages"]:
            content = msg.get("content")
            if content is None:
                continue
            if isinstance(content, str):
                total_length += server.get_total_token_length(content)
                prompt_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        total_length += server.get_total_token_length(text)
                        prompt_parts.append(text)
        max_tokens = request.get("max_completion_tokens", 0)
        if max_tokens == 0:
            max_tokens = request.get("max_tokens", 0)
        prompt_text = " ".join(prompt_parts)
    else:
        prompt = request.get("prompt")
        total_length = server.get_total_token_length(prompt)
        max_tokens = request.get("max_tokens", 0)
        prompt_text = prompt if isinstance(prompt, str) else str(prompt)
    return total_length, max_tokens, prompt_text


def build_kv_prepare_request(
    request: dict,
    is_chat: bool,
    kv_transfer_backend: str = "none",
) -> dict:
    """Build the KV-prepare request with max_tokens=1."""
    kv_prepare_request = request.copy()
    kv_prepare_request["max_tokens"] = 1
    if is_chat:
        kv_prepare_request["max_completion_tokens"] = 1
    if kv_transfer_backend == "nixl":
        kv_prepare_request["stream"] = False
        kv_prepare_request.pop("stream_options", None)
        kv_prepare_request["kv_transfer_params"] = {
            "do_remote_decode": True,
            "do_remote_prefill": False,
            "remote_engine_id": None,
            "remote_block_ids": None,
            "remote_host": None,
            "remote_port": None,
        }
    return kv_prepare_request


def build_zmq_prepare_request(
    request: dict,
    prompt_tokens: list[int],
    request_id: str,
    receiver,
    first_token_source: str,
) -> dict:
    """Build an LMCache sender request for a preselected decode instance."""
    prepare = request.copy()
    prepare["prompt"] = prompt_tokens
    prepare["max_tokens"] = 1
    prepare["stream"] = False
    prepare.pop("stream_options", None)
    transfer_params = {
        "disagg_spec": {
            "req_id": request_id,
            "receiver_host": receiver.host,
            "receiver_init_port": receiver.init_ports,
            "receiver_alloc_port": receiver.alloc_ports,
        }
    }
    if first_token_source == "prefill":
        transfer_params["ret_first_tok"] = True
    prepare["kv_transfer_params"] = transfer_params
    return prepare


async def _zmq_stream_generator(
    prefill_output: dict,
    decode_generator,
    server: Proxy,
    prefill_instance: str,
    decode_instance: str,
    request_len: int,
):
    """Return the P token followed by every streamed D token."""
    head = {
        "id": prefill_output["id"],
        "object": "text_completion",
        "created": prefill_output["created"],
        "model": prefill_output["model"],
        "choices": [{
            "index": 0,
            "text": prefill_output["choices"][0]["text"],
            "logprobs": None,
            "finish_reason": None,
        }],
        "usage": None,
    }
    yield f"data: {json.dumps(head, separators=(',', ':'))}\n\n".encode()
    try:
        async for chunk in decode_generator:
            yield chunk
    finally:
        server.exception_handler(
            prefill_instance=prefill_instance,
            decode_instance=decode_instance,
            req_len=request_len,
        )


async def _zmq_nonstream_generator(
    prefill_output: dict,
    decode_generator,
    server: Proxy,
    prefill_instance: str,
    decode_instance: str,
    request_len: int,
):
    """Merge the P token into the non-streaming D response."""
    value = b""
    try:
        async for chunk in decode_generator:
            value += chunk
        output = json.loads(value)
        output["choices"][0]["text"] = (
            prefill_output["choices"][0]["text"]
            + output["choices"][0]["text"]
        )
        usage = output.get("usage")
        if isinstance(usage, dict):
            usage["completion_tokens"] = usage.get("completion_tokens", 0) + 1
            usage["total_tokens"] = usage.get("total_tokens", 0) + 1
        yield json.dumps(output, separators=(",", ":")).encode()
    finally:
        server.exception_handler(
            prefill_instance=prefill_instance,
            decode_instance=decode_instance,
            req_len=request_len,
        )


async def handle_completion(endpoint: str, raw_request: Request, server: Proxy, is_chat: bool) -> JSONResponse | StreamingResponse:
    """Unified completion handler for both /v1/completions and /v1/chat/completions."""
    _metrics_start = track_request_start(endpoint)
    t_request_start = time.monotonic()
    handler_name = "create_chat_completion" if is_chat else "create_completion"
    t_prefill_done = None
    decode_tracker = None
    try:
        try:
            request = await raw_request.json()
        except (json.JSONDecodeError, ValueError):
            return error_response("Invalid JSON in request body", INVALID_REQUEST, 400)

        error_resp = validate_completion_request(request, is_chat)
        if error_resp:
            return error_resp

        prefill_instance = None
        decode_instance = None

        start_time = time.time()
        total_length, max_tokens, prompt_text = extract_prompt_info(
            request, is_chat, server
        )
        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000
        logger.info(
            "Completion request received",
            extra={
                "endpoint": endpoint,
                "prompt_length": total_length,
                "max_tokens": max_tokens,
                "tokenizer_ms": round(elapsed_ms, 2),
            },
        )

        requested_model = request.get("model", "")
        model_label = requested_model or "unknown"

        # Dual-role fast path: single forward, no P→D split
        if server._is_dual_model(requested_model):
            return await _handle_dual_completion(
                endpoint, request, raw_request, server,
                requested_model, total_length, max_tokens, prompt_text,
                _metrics_start, handler_name,
            )
        if server.pd_mode == "zmq" and is_chat:
            return error_response(
                "ZMQ PD mode currently supports /v1/completions only",
                PROXY_ERROR,
                501,
            )

        kv_prepare_request = build_kv_prepare_request(
            request, is_chat, server.kv_transfer_backend,
        )
        upstream_headers = None
        if server.kv_transfer_backend == "nixl":
            request_id = (
                raw_request.headers.get("x-request-id")
                or str(uuid.uuid4())
            )
            upstream_headers = {"X-Request-Id": request_id}

        _session_id = (
            raw_request.headers.get("x-session-id")
            or request.get("user")
            or (raw_request.client.host if raw_request.client else None)
        )
        _sched_kwargs = {
            "header": raw_request.headers.get("x-session-id"),
            "session_id": _session_id,
            "user": request.get("user"),
            "client_ip": (
                raw_request.client.host if raw_request.client else None
            ),
            "prompt": prompt_text,
            "model": request.get("model", ""),
        }

        prefill_instance = server.schedule(
            server.prefill_cycler,
            is_prompt=True,
            request_len=total_length,
            max_tokens=1,
            **_sched_kwargs,
        )

        decode_instance = server.schedule(
            server.decode_cycler,
            is_prompt=False,
            request_len=total_length,
            max_tokens=max_tokens,
            **_sched_kwargs,
        )

        if prefill_instance is None or decode_instance is None:
            logger.warning(
                "No available instance",
                extra={"endpoint": endpoint, "prompt_length": total_length, "model": requested_model},
            )
            # Check for unknown model first to return a clean 404 without
            # triggering error-path side effects (logging, metrics, etc.)
            if requested_model and server.registry is not None:
                known_models = server.registry.get_registered_models()
                if requested_model not in known_models:
                    return error_response(
                        f"The model '{requested_model}' does not exist",
                        INVALID_REQUEST,
                        404,
                    )
            server.exception_handler(
                prefill_instance=prefill_instance,
                decode_instance=decode_instance,
                req_len=total_length,
            )
            proxy_instance_errors_total.labels(
                instance=str(prefill_instance or decode_instance or "unknown"),
                error_type="no_available_instance",
                model=model_label,
            ).inc()
            return error_response("No available instance can handle the request", PROXY_ERROR, 503)

        zmq_request_id = None
        if server.pd_mode == "zmq":
            if server.zmq_notifications is None or server.zmq_config is None:
                raise HTTPException(
                    status_code=503,
                    detail="ZMQ notification listener is not ready",
                )
            receiver = server.zmq_config.receivers[decode_instance]
            zmq_request_id = str(uuid.uuid4())
            prompt = request["prompt"]
            prompt_tokens = (
                list(prompt)
                if isinstance(prompt, list)
                else server.tokenizer.encode(prompt)
            )
            kv_prepare_request = build_zmq_prepare_request(
                request,
                prompt_tokens,
                zmq_request_id,
                receiver,
                server.first_token_source,
            )
            await server.zmq_notifications.register(zmq_request_id)

        # Track per-instance request counters
        proxy_prefill_requests_total.labels(
            prefill_instance=prefill_instance, decode_instance=decode_instance,
            model=model_label,
        ).inc()
        proxy_decode_requests_total.labels(
            prefill_instance=prefill_instance, decode_instance=decode_instance,
            model=model_label,
        ).inc()

        # Track active prefill requests
        proxy_prefill_active_requests.labels(
            prefill_instance=prefill_instance, decode_instance=decode_instance,
            model=model_label,
        ).inc()

        value = b""
        try:
            async for chunk in server.forward_request(
                f"http://{prefill_instance}{endpoint}",
                kv_prepare_request,
                extra_headers=upstream_headers,
            ):
                value += chunk
        except HTTPException as http_exc:
            if zmq_request_id is not None:
                await server.zmq_notifications.discard(zmq_request_id)
            server.exception_handler(prefill_instance, decode_instance, total_length)
            server._record_failure(prefill_instance, decode_instance)
            proxy_instance_errors_total.labels(
                instance=prefill_instance, error_type="prefill_forward_error",
                model=model_label,
            ).inc()
            proxy_prefill_active_requests.labels(
                prefill_instance=prefill_instance, decode_instance=decode_instance,
                model=model_label,
            ).dec()
            raise http_exc

        t_prefill_done = time.monotonic()
        # Prefill complete — decrement active prefill, start active decode
        proxy_prefill_active_requests.labels(
            prefill_instance=prefill_instance, decode_instance=decode_instance,
            model=model_label,
        ).dec()
        proxy_decode_active_requests.labels(
            prefill_instance=prefill_instance, decode_instance=decode_instance,
            model=model_label,
        ).inc()

        value = (
            value.strip().decode("utf-8").removesuffix("data: [DONE]").encode("utf-8")
        )
        if server.kv_transfer_backend == "nixl":
            try:
                prefill_output = json.loads(value)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Prefill response did not contain valid JSON",
                ) from exc
            kv_transfer_params = prefill_output.get("kv_transfer_params")
            if not kv_transfer_params:
                raise HTTPException(
                    status_code=502,
                    detail="Prefill response did not contain kv_transfer_params",
                )
            request = request.copy()
            request["kv_transfer_params"] = kv_transfer_params
        elif server.pd_mode == "zmq":
            prefill_output = None
            first_token = None
            if server.first_token_source == "prefill":
                try:
                    prefill_output = json.loads(value)
                    first_token = prefill_output["kv_transfer_params"]["first_tok"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    assert zmq_request_id is not None
                    await server.zmq_notifications.discard(zmq_request_id)
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "Prefill response did not contain an LMCache "
                            "first token"
                        ),
                    ) from exc
            receiver = server.zmq_config.receivers[decode_instance]
            try:
                await server.zmq_notifications.wait(
                    zmq_request_id,
                    len(receiver.init_ports),
                )
            except TimeoutError as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"Timed out waiting for ZMQ notification {zmq_request_id}",
                ) from exc
            request = request.copy()
            request["prompt"] = list(kv_prepare_request["prompt"])
            if server.first_token_source == "prefill":
                request["prompt"].append(first_token)
                request["max_tokens"] = max(1, max_tokens - 1)
            request.pop("kv_transfer_params", None)

        async def streaming_response(value):
            if value:
                yield value
            else:
                yield b""

        generator_p = streaming_response(value)
        # Note: server.forward_request() is an async generator — calling it
        # only creates the generator object; it never raises synchronously.
        # Actual HTTP errors surface when the generator is iterated inside
        # wrapped_generator(), where they are caught and handled.
        generator_d_raw = server.forward_request(
            f"http://{decode_instance}{endpoint}",
            request,
            extra_headers=upstream_headers,
        )
        decode_tracker = FirstTokenTracker(generator_d_raw)
        generator_d = decode_tracker

        if (
            server.pd_mode == "zmq"
            and server.first_token_source == "prefill"
        ):
            assert prefill_output is not None
            if request.get("stream", False):
                final_generator = _zmq_stream_generator(
                    prefill_output,
                    generator_d,
                    server,
                    prefill_instance,
                    decode_instance,
                    total_length,
                )
            else:
                final_generator = _zmq_nonstream_generator(
                    prefill_output,
                    generator_d,
                    server,
                    prefill_instance,
                    decode_instance,
                    total_length,
                )
            first_token_from_p = True
        else:
            if request.get("stream", False):
                generator_class = server.generator
            else:
                generator_class = server.d_first_token_generator_class
            # Determine if user's first token comes from prefill or decode node.
            # P_first_token_generator yields P's token first; D_first_token_generator
            # discards P's token and yields D's tokens only.
            from xpyd.proxy import P_first_token_generator
            first_token_from_p = (
                server.first_token_source == "prefill"
                and generator_class is P_first_token_generator
            )
            final_generator = generator_class(
                generator_p,
                generator_d,
                server,
                prefill_instance,
                decode_instance,
                req_len=total_length,
            )
        media_type = (
            "text/event-stream"
            if request.get("stream", False)
            else "application/json"
        )

        async def wrapped_generator():
            try:
                async for chunk in final_generator:
                    yield chunk
            except CancelledError:
                logger.warning(
                    "[0]Client disconnected during %s (CancelledError)",
                    handler_name,
                )
            except HTTPException as http_exc:
                server.exception_handler(prefill_instance, decode_instance, total_length)
                server._record_failure(prefill_instance, decode_instance)
                proxy_instance_errors_total.labels(
                    instance=decode_instance, error_type="decode_forward_error",
                    model=model_label,
                ).inc()
                logger.error("[1] HTTPException in wrapped_generator: %s", str(http_exc.detail))
                raise
            except Exception as e:
                proxy_instance_errors_total.labels(
                    instance=decode_instance, error_type="decode_forward_error",
                    model=model_label,
                ).inc()
                logger.error("[1] Exception in wrapped_generator: %s", str(e))
                raise
            finally:
                if (
                    prefill_instance
                    and decode_instance
                    and t_prefill_done is not None
                    and decode_tracker is not None
                ):
                    record_pd_metrics(
                        prefill_instance=prefill_instance,
                        decode_instance=decode_instance,
                        model=model_label,
                        t_request_start=t_request_start,
                        t_prefill_done=t_prefill_done,
                        tracker=decode_tracker,
                        is_streaming=request.get("stream", False),
                        first_token_from_prefill=first_token_from_p,
                    )
                # Decrement decode active gauge (only if decode was started)
                if decode_instance and prefill_instance and t_prefill_done is not None:
                    proxy_decode_active_requests.labels(
                        prefill_instance=prefill_instance,
                        decode_instance=decode_instance,
                        model=model_label,
                    ).dec()
                track_request_end(endpoint, _metrics_start)

        return StreamingResponse(wrapped_generator(), media_type=media_type)
    except HTTPException:
        if decode_instance and prefill_instance and t_prefill_done is not None:
            proxy_decode_active_requests.labels(
                prefill_instance=prefill_instance,
                decode_instance=decode_instance,
                model=model_label,
            ).dec()
        track_request_end(endpoint, _metrics_start)
        raise
    except Exception:
        if decode_instance and prefill_instance and t_prefill_done is not None:
            proxy_decode_active_requests.labels(
                prefill_instance=prefill_instance,
                decode_instance=decode_instance,
                model=model_label,
            ).dec()
        track_request_end(endpoint, _metrics_start)
        logger.error("Error in %s: %s", handler_name, sys.exc_info()[1])
        return JSONResponse(
            {"error": {"message": "Internal proxy error", "type": "proxy_error"}},
            status_code=500,
        )


async def _handle_dual_completion(
    endpoint: str,
    request: dict,
    raw_request: Request,
    server: Proxy,
    model: str,
    total_length: int,
    max_tokens: int,
    prompt_text: str,
    metrics_start: float,
    handler_name: str,
) -> JSONResponse | StreamingResponse:
    """Single-pass completion for dual-role instances."""
    instance = server.schedule_dual(
        model,
        request_len=total_length,
        max_tokens=max_tokens,
        header=raw_request.headers.get("x-session-id"),
        session_id=request.get("session_id"),
        user=request.get("user"),
        client_ip=(
            raw_request.client.host if raw_request.client else None
        ),
        prompt=prompt_text,
    )

    logger.info(
        "Dual %s request",
        handler_name,
        extra={
            "model": model,
            "prompt_length": total_length,
            "max_tokens": max_tokens,
            "prompt": prompt_text[:200] if prompt_text else "",
            "instance": instance,
        },
    )

    if instance is None:
        # Check for unknown model
        if model and server.registry is not None:
            known_models = server.registry.get_registered_models()
            if model not in known_models:
                return error_response(
                    f"The model '{model}' does not exist",
                    INVALID_REQUEST,
                    404,
                )
        return error_response(
            "No available instance can handle the request",
            PROXY_ERROR,
            503,
        )

    url = f"http://{instance}{endpoint}"

    if request.get("stream", False):
        generator = server.forward_request(url, request)

        async def wrapped():
            _ok = True
            try:
                async for chunk in generator:
                    yield chunk
            except CancelledError:
                _ok = False
                logger.warning(
                    "Client disconnected during dual %s (CancelledError)",
                    handler_name,
                )
            except Exception as e:
                _ok = False
                logger.error("Exception in dual stream: %s", str(e))
                if server.registry is not None:
                    server.registry.record_failure(instance)
                raise
            finally:
                server.schedule_dual_completion(instance, req_len=total_length)
                if _ok and server.registry is not None:
                    server.registry.record_success(instance)
                track_request_end(endpoint, metrics_start)

        return StreamingResponse(wrapped(), media_type="text/event-stream")
    else:
        # Non-streaming: forward request using server.forward_request()
        # for consistent auth, timeouts, and connection handling.
        try:
            value = b""
            async for chunk in server.forward_request(url, request):
                value += chunk
            data = json.loads(value)
            # Detect error responses from upstream. forward_request yields
            # raw bytes without HTTP status, so inspect the parsed JSON.
            # OpenAI error format: {"error": {"message": ..., "type": ..., "code": ...}}
            # where "code" can be null, a string like "invalid_api_key", or an int.
            if "error" in data:
                err = data["error"]
                err_type = err.get("type", "")
                # Map error type to HTTP status code
                if err_type == "invalid_request_error":
                    status_code = 400
                elif err_type == "authentication_error":
                    status_code = 401
                elif err_type == "not_found_error":
                    status_code = 404
                elif err_type == "rate_limit_error":
                    status_code = 429
                else:
                    status_code = 502
            else:
                status_code = 200
            server.schedule_dual_completion(
                instance, req_len=total_length,
            )
            if status_code < 400 and server.registry is not None:
                server.registry.record_success(instance)
            elif status_code >= 400 and server.registry is not None:
                server.registry.record_failure(instance)
            track_request_end(endpoint, metrics_start)
            return JSONResponse(data, status_code=status_code)
        except HTTPException as http_exc:
            server.schedule_dual_completion(
                instance, req_len=total_length,
            )
            if server.registry is not None:
                server.registry.record_failure(instance)
            track_request_end(endpoint, metrics_start)
            return error_response(
                str(http_exc.detail), PROXY_ERROR, http_exc.status_code,
            )
        except Exception as e:
            logger.error("Error in dual non-streaming: %s", str(e))
            server.schedule_dual_completion(
                instance, req_len=total_length,
            )
            if server.registry is not None:
                server.registry.record_failure(instance)
            track_request_end(endpoint, metrics_start)
            return error_response(
                "Internal proxy error", PROXY_ERROR, 500,
            )


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register(router: APIRouter, server: Proxy) -> None:
    """Register completion routes on *router*."""

    async def _validate_json(raw_request: Request):
        # HTTPException is intentional here: FastAPI Depends() dependencies
        # cannot return a JSONResponse to short-circuit the request; only
        # raising an exception aborts the dependency chain.
        content_type = raw_request.headers.get("content-type", "").lower()
        if content_type != "application/json":
            raise HTTPException(
                status_code=415,
                detail="Unsupported Media Type: Only 'application/json' is allowed",
            )

    async def create_completion(raw_request: Request):
        return await handle_completion(
            "/v1/completions", raw_request, server, is_chat=False
        )

    async def create_chat_completion(raw_request: Request):
        return await handle_completion(
            "/v1/chat/completions", raw_request, server, is_chat=True
        )

    router.post(
        "/v1/completions",
        dependencies=[Depends(_validate_json)],
    )(
        server.custom_create_completion
        if server.custom_create_completion
        else create_completion
    )

    router.post(
        "/v1/chat/completions",
        dependencies=[Depends(_validate_json)],
    )(
        server.custom_create_chat_completion
        if server.custom_create_chat_completion
        else create_chat_completion
    )

    router.options("/v1/completions")(lambda: None)
    router.options("/v1/chat/completions")(lambda: None)
