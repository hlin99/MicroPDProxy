# SPDX-License-Identifier: Apache-2.0
"""Generate a well-commented YAML configuration template for xpyd proxy."""

from __future__ import annotations

import ipaddress
import os
import re
import select
import sys
from pathlib import Path
from typing import Optional

import yaml

_TEMPLATE = """\
# xpyd proxy configuration
# Docs: https://github.com/xPyD-hub/xPyD-proxy

# Required: model name served by this proxy
model: "deepseek-ai/DeepSeek-V4-Flash"

# Optional: local tokenizer root. Model "org/name" is loaded from
# "<tokenizer_path>/org/name/". Without this setting, xPyD downloads the
# tokenizer and falls back to roundrobin if the download fails.
# tokenizer_path: "/models/tokenizers"

# Default topology: one backend performs both prefill and decode
instances:
  - address: "10.0.0.1:8100"
    role: "aggregated"
    model: "deepseek-ai/DeepSeek-V4-Flash"

# Server port (default: 8000)
port: 8000

# Log level: debug | info | warning | error (default: warning)
log_level: "warning"

# Scheduling policy: loadbalanced | roundrobin | consistent_hash | power_of_two | cache_aware
scheduling: "loadbalanced"

# Startup probe settings
startup:
  wait_timeout_seconds: 600
  probe_interval_seconds: 10
  heartbeat_interval_seconds: 30

# Health check configuration
health_check:
  enabled: true
  interval_seconds: 10.0
  timeout_seconds: 3.0

# Circuit breaker configuration
circuit_breaker:
  enabled: false
  failure_threshold: 5
  success_threshold: 2
  timeout_duration_seconds: 30
  window_duration_seconds: 60

# Retry / resilience configuration
retry:
  enabled: false
  max_retries: 2
  initial_backoff_ms: 100
  max_backoff_ms: 10000
  backoff_multiplier: 2.0
  jitter_factor: 0.1
  retryable_status_codes: [408, 429, 500, 502, 503, 504]

# API keys (prefer env vars ADMIN_API_KEY / OPENAI_API_KEY)
# admin_api_key: ""
# openai_api_key: ""
"""


def generate_config_template(output_path: str) -> None:
    """Write a well-commented YAML template to *output_path*.

    Creates parent directories if they do not exist.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TEMPLATE)
    print(f"Config template written to {path}")


def _format_default(value: str) -> str:
    """Underline defaults in interactive terminals without polluting logs."""
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[4m{value}\033[0m"
    return value


def _use_interactive_mode(timeout_seconds: float = 5.0) -> bool:
    """Return whether the user selects the wizard before the timeout."""
    print(
        "Configure interactively? "
        f"[y/{_format_default('N')}] "
        f"({timeout_seconds:g}s timeout): ",
        end="",
        flush=True,
    )
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    except (OSError, ValueError):
        print()
        return False
    if not ready:
        print("\nNo response; generating the default template.")
        return False
    response = sys.stdin.readline()
    if not response:
        print()
        return False
    return response.strip().lower() in {"y", "yes"}


def generate_config(output_path: str, *, timeout_seconds: float = 5.0) -> None:
    """Choose interactive or template generation, defaulting to the template."""
    if _use_interactive_mode(timeout_seconds):
        generate_interactive_config(output_path)
    else:
        generate_config_template(output_path)


def _prompt(
    label: str,
    *,
    default: Optional[str] = None,
    choices: Optional[tuple[str, ...]] = None,
) -> str:
    """Prompt until a non-empty value matching *choices* is provided."""
    if choices:
        label = f"{label} ({'/'.join(choices)})"
    suffix = (
        f" [{_format_default(default)}]"
        if default is not None
        else ""
    )
    while True:
        value = input(f"{label}{suffix}: ").strip()
        value = value or default or ""
        if choices:
            normalized = value.lower()
            if normalized in choices:
                return normalized
        if value and (choices is None or value in choices):
            return value
        if choices:
            print(f"Choose one of: {', '.join(choices)}")
        else:
            print("A value is required.")


def _prompt_instance_count(role: str) -> int:
    """Prompt for a bounded positive number of instances."""
    return _prompt_positive_int(
        f"Number of {role} instances",
        default=1,
        maximum=1000,
    )


def _prompt_positive_int(
    label: str,
    *,
    default: int,
    maximum: int,
) -> int:
    """Prompt for a positive integer no greater than *maximum*."""
    while True:
        raw = _prompt(label, default=str(default))
        try:
            count = int(raw)
        except ValueError:
            count = 0
        if 1 <= count <= maximum:
            return count
        print(f"Value must be an integer between 1 and {maximum}.")


_IP_PORT_PATTERN = re.compile(
    r"^(?P<start_ip>\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:-(?P<end_ip>\d{1,3}(?:\.\d{1,3}){3}))?"
    r"(?::(?P<start_port>\d+)(?:-(?P<end_port>\d+))?)?$"
)


def _expand_address_input(
    raw: str,
    *,
    default_port: int,
    require_explicit_port: bool = False,
) -> list[str]:
    """Expand address, IPv4, and port ranges into host:port strings."""
    tokens = [token for token in re.split(r"[,\s]+", raw.strip()) if token]
    if not tokens:
        raise ValueError("At least one address is required.")

    addresses = []
    for token in tokens:
        match = _IP_PORT_PATTERN.fullmatch(token)
        if match is None:
            if "-" in token:
                raise ValueError(f"Invalid address or range {token!r}.")
            if require_explicit_port and ":" not in token:
                raise ValueError(
                    f"Address {token!r} must include a port in per-instance mode."
                )
            addresses.append(
                token if ":" in token else f"{token}:{default_port}"
            )
            continue

        values = match.groupdict()
        try:
            start_ip = ipaddress.IPv4Address(values["start_ip"])
            end_ip = ipaddress.IPv4Address(values["end_ip"] or values["start_ip"])
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"Invalid IPv4 range {token!r}: {exc}") from exc
        if start_ip > end_ip:
            raise ValueError(
                f"Invalid IPv4 range {token!r}; start must not exceed end."
            )
        ip_count = int(end_ip) - int(start_ip) + 1
        if ip_count > 1000:
            raise ValueError(
                f"IP range {token!r} expands to {ip_count} addresses; "
                "the maximum is 1000."
            )
        ips = [
            ipaddress.IPv4Address(value)
            for value in range(int(start_ip), int(end_ip) + 1)
        ]

        start_port_text = values["start_port"]
        end_port_text = values["end_port"]
        if start_port_text is None:
            if require_explicit_port:
                raise ValueError(
                    f"Address range {token!r} must include port information "
                    "in per-instance mode."
                )
            ports = [default_port] * len(ips)
        else:
            start_port = int(start_port_text)
            end_port = int(end_port_text or start_port_text)
            if not (1 <= start_port <= end_port <= 65535):
                raise ValueError(
                    f"Invalid port range in {token!r}; ports must be "
                    "between 1 and 65535 in ascending order."
                )
            port_count = end_port - start_port + 1
            if port_count > 1000:
                raise ValueError(
                    f"Port range in {token!r} expands to {port_count} ports; "
                    "the maximum is 1000."
                )
            ports = list(range(start_port, end_port + 1))
            if len(ports) == 1:
                ports *= len(ips)
            elif len(ips) == 1:
                ips *= len(ports)
            elif len(ips) != len(ports):
                raise ValueError(
                    f"IP and port ranges in {token!r} must have equal lengths."
                )

        addresses.extend(
            f"{address}:{port}" for address, port in zip(ips, ports)
        )

    if len(addresses) > 1000:
        raise ValueError("Address input expands to more than 1000 instances.")
    if len(set(addresses)) != len(addresses):
        raise ValueError("Address input contains duplicate instances.")
    return addresses


def _prompt_role_instances(
    role: str,
    count: int,
    *,
    base_port: int,
    model: str,
) -> list[dict[str, str]]:
    """Prompt once for a role's addresses and enforce the declared count."""
    from xpyd.config import InstanceEntry

    role_name = role.capitalize()
    port_mode = _prompt(
        f"{role_name} port assignment",
        default="same",
        choices=("same", "per-instance"),
    )
    if port_mode == "same":
        default_port = _prompt_port(
            f"{role_name} shared port",
            default=base_port,
        )
        print(
            f"{role_name} address formats (all use port {default_port}):\n"
            "  single: 192.168.0.1\n"
            "  list:   192.168.0.1,192.168.0.2 (commas or spaces)\n"
            "  range:  192.168.0.1-192.168.0.10"
        )
        require_explicit_port = False
    else:
        default_port = base_port
        print(
            f"{role_name} address formats (ports required):\n"
            f"  list:          192.168.0.1:{base_port},"
            f"192.168.0.2:{base_port + 1}\n"
            f"  port range:    192.168.0.1:"
            f"{base_port}-{base_port + 9}\n"
            "  aligned range: "
            f"192.168.0.1-192.168.0.10:{base_port}-{base_port + 9}"
        )
        require_explicit_port = True

    default = None
    if count <= 10:
        if port_mode == "same":
            default = ",".join(
                f"127.0.0.{offset + 1}"
                for offset in range(count)
            )
        else:
            default = ",".join(
                f"127.0.0.1:{default_port + offset}"
                for offset in range(count)
            )

    while True:
        raw = _prompt(
            f"{role_name} addresses ({count} required)",
            default=default,
        )
        try:
            addresses = _expand_address_input(
                raw,
                default_port=default_port,
                require_explicit_port=require_explicit_port,
            )
            if port_mode == "same":
                unexpected_ports = [
                    address for address in addresses
                    if int(address.rsplit(":", 1)[1]) != default_port
                ]
                if unexpected_ports:
                    raise ValueError(
                        f"All addresses must use shared port {default_port}."
                    )
            for address in addresses:
                InstanceEntry(address=address, role=role, model=model)
        except ValueError as exc:
            print(f"Invalid address input: {exc}")
            continue
        if len(addresses) != count:
            print(
                f"Expected {count} {role} addresses, "
                f"but the input expands to {len(addresses)}."
            )
            continue
        return [
            {"address": address, "role": role, "model": model}
            for address in addresses
        ]


def _prompt_port(label: str = "Proxy port", *, default: int = 8000) -> int:
    """Prompt for a valid TCP port."""
    while True:
        raw = _prompt(label, default=str(default))
        try:
            port = int(raw)
        except ValueError:
            print("Port must be an integer between 1 and 65535.")
            continue
        if 1 <= port <= 65535:
            return port
        print("Port must be an integer between 1 and 65535.")


def _prompt_port_block(
    label: str,
    *,
    default: int,
    size: int,
    occupied: Optional[set[int]] = None,
) -> int:
    """Prompt for the first port in a contiguous, available block."""
    while True:
        start = _prompt_port(label, default=default)
        end = start + size - 1
        if end > 65535:
            print(
                f"{label} requires {size} consecutive ports; "
                f"the last port would be {end}."
            )
            continue
        ports = set(range(start, end + 1))
        if occupied and ports & occupied:
            print(
                f"{label} overlaps another configured ZMQ port range."
            )
            continue
        return start


def _prompt_zmq_config(
    decode_instances: list[dict[str, str]],
) -> dict[str, object]:
    """Collect a basic, complete ZMQ receiver mapping."""
    notification_host = _prompt(
        "ZMQ notification host",
        default="127.0.0.1",
    )
    notification_port = _prompt_port(
        "ZMQ notification port",
        default=7500,
    )
    max_channels = max(1, min(64, 65535 // (2 * len(decode_instances))))
    channels = _prompt_positive_int(
        "ZMQ channels per decode instance",
        default=1,
        maximum=max_channels,
    )
    port_count = len(decode_instances) * channels
    init_base = _prompt_port_block(
        "ZMQ receiver init base port",
        default=7300,
        size=port_count,
    )
    init_port_set = set(range(init_base, init_base + port_count))
    alloc_default = max(7400, init_base + port_count)
    if alloc_default + port_count - 1 > 65535:
        alloc_default = 1
    alloc_base = _prompt_port_block(
        "ZMQ receiver allocation base port",
        default=alloc_default,
        size=port_count,
        occupied=init_port_set,
    )

    receivers = {}
    for index, instance in enumerate(decode_instances):
        offset = index * channels
        address = instance["address"]
        receivers[address] = {
            "host": address.rsplit(":", 1)[0],
            "init_ports": list(
                range(init_base + offset, init_base + offset + channels)
            ),
            "alloc_ports": list(
                range(alloc_base + offset, alloc_base + offset + channels)
            ),
        }
    return {
        "host": notification_host,
        "port": notification_port,
        "notification_timeout_seconds": 30.0,
        "receivers": receivers,
    }


def _prompt_bool(label: str, *, default: bool) -> bool:
    """Prompt for a yes/no value."""
    default_text = (
        f"{_format_default('Y')}/n"
        if default
        else f"y/{_format_default('N')}"
    )
    while True:
        value = input(f"{label} [{default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def generate_interactive_config(output_path: str) -> None:
    """Guide the user through common settings and write a validated YAML file."""
    from xpyd.config import ProxyConfig

    print("Create an xPyD proxy configuration. Press Enter to accept defaults.")
    topology = _prompt(
        "Deployment topology",
        default="disaggregated",
        choices=("aggregated", "disaggregated"),
    )
    model = _prompt("Model name", default="deepseek-ai/DeepSeek-V4-Flash")
    instances = []
    disaggregated_mode = None
    zmq_config = None
    if topology == "aggregated":
        aggregated_count = _prompt_instance_count("aggregated")
        instances.extend(
            _prompt_role_instances(
                "aggregated",
                aggregated_count,
                base_port=8100,
                model=model,
            )
        )
    else:
        disaggregated_mode = _prompt(
            "Disaggregated transfer mode",
            default="direct",
            choices=("direct", "nixl", "zmq"),
        )
        prefill_count = _prompt_instance_count("prefill")
        decode_count = _prompt_instance_count("decode")
        instances.extend(
            _prompt_role_instances(
                "prefill",
                prefill_count,
                base_port=8100,
                model=model,
            )
        )
        decode_instances = _prompt_role_instances(
            "decode",
            decode_count,
            base_port=8200,
            model=model,
        )
        instances.extend(decode_instances)
        if disaggregated_mode == "zmq":
            zmq_config = _prompt_zmq_config(decode_instances)
    tokenizer_path = input("Local tokenizer root (optional): ").strip()
    port = _prompt_port("Proxy port")
    log_level = _prompt(
        "Log level",
        default="warning",
        choices=("debug", "info", "warning", "error"),
    )
    scheduling = _prompt(
        "Scheduling policy",
        default="loadbalanced",
        choices=(
            "loadbalanced",
            "roundrobin",
            "consistent_hash",
            "power_of_two",
            "cache_aware",
        ),
    )
    first_token_source = "decode"
    if topology == "disaggregated":
        first_token_source = _prompt(
            "First token source",
            default="decode",
            choices=("prefill", "decode"),
        )
    health_check_enabled = _prompt_bool(
        "Enable health checks?",
        default=True,
    )

    config_data = {
        "instances": instances,
        "port": port,
        "log_level": log_level,
        "scheduling": scheduling,
        "startup": {
            "wait_timeout_seconds": 600,
            "probe_interval_seconds": 10,
            "heartbeat_interval_seconds": 30,
        },
        "health_check": {
            "enabled": health_check_enabled,
            "interval_seconds": 10.0,
            "timeout_seconds": 3.0,
        },
        "circuit_breaker": {
            "enabled": False,
            "failure_threshold": 5,
            "success_threshold": 2,
            "timeout_duration_seconds": 30,
            "window_duration_seconds": 60,
        },
        "retry": {
            "enabled": False,
            "max_retries": 2,
            "initial_backoff_ms": 100,
            "max_backoff_ms": 10000,
            "backoff_multiplier": 2.0,
            "jitter_factor": 0.1,
            "retryable_status_codes": [408, 429, 500, 502, 503, 504],
        },
    }
    if topology == "disaggregated":
        config_data["disaggregated_mode"] = disaggregated_mode
        config_data["first_token_source"] = first_token_source
        if zmq_config is not None:
            config_data["zmq"] = zmq_config
    if tokenizer_path:
        config_data["tokenizer_path"] = tokenizer_path

    validation_data = dict(config_data)
    startup = validation_data.pop("startup")
    validation_data.update(startup)
    ProxyConfig(**validation_data)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(config_data, sort_keys=False)
    path.write_text("# Generated by xpyd proxy --init-config wizard\n" + rendered)
    print(f"Config written to {path}")
