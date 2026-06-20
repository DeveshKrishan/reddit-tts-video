"""Process-level CPU and memory metrics for pipeline observability."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

import psutil

from logger import logger

_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class ProcessSnapshot:
    wall_time: float
    rss_bytes: int
    cpu_user: float
    cpu_system: float

    @classmethod
    def capture(cls, process: psutil.Process) -> ProcessSnapshot:
        memory = process.memory_info()
        cpu = process.cpu_times()
        return cls(
            wall_time=time.perf_counter(),
            rss_bytes=memory.rss,
            cpu_user=cpu.user,
            cpu_system=cpu.system,
        )


def _bytes_to_mb(value: int) -> float:
    return round(value / _BYTES_PER_MB, 2)


def _cpu_percent(cpu_seconds: float, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    cpu_count = psutil.cpu_count(logical=True) or 1
    return round((cpu_seconds / duration_sec / cpu_count) * 100, 2)


def _memory_percent(rss_bytes: int) -> float:
    total = psutil.virtual_memory().total
    if total <= 0:
        return 0.0
    return round((rss_bytes / total) * 100, 2)


class MetricsTracker(Protocol):
    def log_job_summary(self, **fields: Any) -> None: ...

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]: ...


class ResourceMonitor:
    """Emits simple per-phase CPU and memory metrics for this process."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        start = ProcessSnapshot.capture(self._process)
        self._job_start_cpu = start.cpu_user + start.cpu_system
        self._peak_rss_bytes = start.rss_bytes

    def _snapshot(self) -> ProcessSnapshot:
        snapshot = ProcessSnapshot.capture(self._process)
        self._peak_rss_bytes = max(self._peak_rss_bytes, snapshot.rss_bytes)
        return snapshot

    def _log_event(self, event: str, **fields: Any) -> None:
        payload = {"event": event, **fields}
        logger.info(json.dumps(payload, separators=(",", ":")))

    def log_job_summary(self, **fields: Any) -> None:
        duration_sec = fields.pop("duration_sec", 0.0)
        end = self._snapshot()
        cpu_seconds = (end.cpu_user + end.cpu_system) - self._job_start_cpu
        self._log_event(
            "resource_job_summary",
            duration_sec=round(float(duration_sec), 3),
            cpu_percent=_cpu_percent(cpu_seconds, float(duration_sec)),
            memory_mb=_bytes_to_mb(self._peak_rss_bytes),
            memory_percent=_memory_percent(self._peak_rss_bytes),
            **fields,
        )

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        start = self._snapshot()
        try:
            yield
        finally:
            end = self._snapshot()
            duration_sec = end.wall_time - start.wall_time
            cpu_seconds = (end.cpu_user - start.cpu_user) + (end.cpu_system - start.cpu_system)
            self._log_event(
                "resource_phase",
                phase=phase,
                duration_sec=round(duration_sec, 3),
                cpu_percent=_cpu_percent(cpu_seconds, duration_sec),
                memory_mb=_bytes_to_mb(end.rss_bytes),
                memory_percent=_memory_percent(end.rss_bytes),
                **labels,
            )


class NullMetricsTracker:
    """No-op tracker used when metrics are disabled in config."""

    def log_job_summary(self, **fields: Any) -> None:
        return None

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        yield


def create_metrics_tracker(enabled: bool = True) -> MetricsTracker:
    return ResourceMonitor() if enabled else NullMetricsTracker()
