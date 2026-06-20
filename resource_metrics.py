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
    vms_bytes: int
    cpu_user: float
    cpu_system: float
    num_threads: int

    @classmethod
    def capture(cls, process: psutil.Process) -> ProcessSnapshot:
        memory = process.memory_info()
        cpu = process.cpu_times()
        return cls(
            wall_time=time.perf_counter(),
            rss_bytes=memory.rss,
            vms_bytes=memory.vms,
            cpu_user=cpu.user,
            cpu_system=cpu.system,
            num_threads=process.num_threads(),
        )


def _bytes_to_mb(value: int) -> float:
    return round(value / _BYTES_PER_MB, 2)


def _avg_cpu_percent(cpu_seconds: float, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    cpu_count = psutil.cpu_count(logical=True) or 1
    return round((cpu_seconds / duration_sec / cpu_count) * 100, 2)


def _snapshot_fields(snapshot: ProcessSnapshot, *, suffix: str = "") -> dict[str, Any]:
    suffix_token = f"_{suffix}" if suffix else ""
    return {
        f"rss_mb{suffix_token}": _bytes_to_mb(snapshot.rss_bytes),
        f"vms_mb{suffix_token}": _bytes_to_mb(snapshot.vms_bytes),
        f"cpu_time_user_sec{suffix_token}": round(snapshot.cpu_user, 3),
        f"cpu_time_system_sec{suffix_token}": round(snapshot.cpu_system, 3),
        f"num_threads{suffix_token}": snapshot.num_threads,
    }


class MetricsTracker(Protocol):
    def log_job_start(self) -> None: ...

    def log_job_summary(self, **fields: Any) -> None: ...

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]: ...


class ResourceMonitor:
    """Tracks RSS peak and emits structured JSON resource logs for each pipeline phase."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._peak_rss_bytes = 0

    def _snapshot(self) -> ProcessSnapshot:
        snapshot = ProcessSnapshot.capture(self._process)
        self._peak_rss_bytes = max(self._peak_rss_bytes, snapshot.rss_bytes)
        return snapshot

    def _log_event(self, event: str, **fields: Any) -> None:
        payload = {"event": event, **fields}
        logger.info(json.dumps(payload, separators=(",", ":")))

    def log_job_start(self) -> None:
        snapshot = self._snapshot()
        self._log_event("resource_job_start", **_snapshot_fields(snapshot))

    def log_job_summary(self, **fields: Any) -> None:
        end = self._snapshot()
        self._log_event(
            "resource_job_summary",
            rss_mb_peak=_bytes_to_mb(self._peak_rss_bytes),
            rss_mb_end=_bytes_to_mb(end.rss_bytes),
            cpu_time_user_sec_total=round(end.cpu_user, 3),
            cpu_time_system_sec_total=round(end.cpu_system, 3),
            num_threads_end=end.num_threads,
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
            cpu_user_delta = end.cpu_user - start.cpu_user
            cpu_system_delta = end.cpu_system - start.cpu_system
            cpu_delta = cpu_user_delta + cpu_system_delta
            self._log_event(
                "resource_phase",
                phase=phase,
                duration_sec=round(duration_sec, 3),
                rss_mb_start=_bytes_to_mb(start.rss_bytes),
                rss_mb_end=_bytes_to_mb(end.rss_bytes),
                rss_mb_delta=_bytes_to_mb(end.rss_bytes - start.rss_bytes),
                rss_mb_peak=_bytes_to_mb(self._peak_rss_bytes),
                cpu_time_user_sec=round(cpu_user_delta, 3),
                cpu_time_system_sec=round(cpu_system_delta, 3),
                cpu_time_total_sec=round(cpu_delta, 3),
                cpu_avg_percent=_avg_cpu_percent(cpu_delta, duration_sec),
                num_threads_start=start.num_threads,
                num_threads_end=end.num_threads,
                **labels,
            )


class NullMetricsTracker:
    """No-op tracker used when metrics are disabled in config."""

    def log_job_start(self) -> None:
        return None

    def log_job_summary(self, **fields: Any) -> None:
        return None

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        yield


def create_metrics_tracker(enabled: bool = True) -> MetricsTracker:
    return ResourceMonitor() if enabled else NullMetricsTracker()
