# SPDX-License-Identifier: Apache-2.0
"""Scheduler module for MicroPDProxy."""

try:
    from .scheduler_base import SchedulingPolicy
    from .round_robin import RoundRobinSchedulingPolicy
    from .load_balanced import LoadBalancedScheduler
    from .consistent_hash import ConsistentHashPolicy
except ImportError:
    from scheduler_base import SchedulingPolicy
    from round_robin import RoundRobinSchedulingPolicy
    from load_balanced import LoadBalancedScheduler
    from consistent_hash import ConsistentHashPolicy

__all__ = [
    "SchedulingPolicy",
    "RoundRobinSchedulingPolicy",
    "LoadBalancedScheduler",
    "ConsistentHashPolicy",
]
