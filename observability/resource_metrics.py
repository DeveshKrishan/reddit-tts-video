"""Process-level CPU and memory metrics for pipeline observability."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

import psutil

from logger import logger

_BYTES_PER_MB = 1024 * 1024
_SAMPLE_INTERVAL_SEC = 0.5


@dataclass(frozen=True)
class UtilizationSample:
    """Instantaneous process-tree CPU and memory readings."""

    cpu_utilization: float  # 0.0–1.0 fraction of logical CPU capacity
    memory_bytes: int
    memory_utilization: float  # 0.0–1.0 fraction of system RAM


class ProcessUtilizationReader:
    """Reads current CPU/memory for the process tree; used by OTEL observable gauges."""

    def __init__(self, process: psutil.Process | None = None) -> None:
        self._process = process or psutil.Process(os.getpid())
        self._lock = threading.Lock()
        self._last_cpu_seconds: float | None = None
        self._last_wall_time: float | None = None
        self._active_phase = "startup"

    @property
    def active_phase(self) -> str:
        with self._lock:
            return self._active_phase

    def set_active_phase(self, phase: str) -> None:
        with self._lock:
            self._active_phase = phase

    def observe(self) -> UtilizationSample:
        with self._lock:
            now = time.perf_counter()
            cpu_seconds = _aggregate_cpu_seconds(self._process)
            rss_bytes = _aggregate_rss(self._process)

            cpu_utilization = 0.0
            if self._last_cpu_seconds is not None and self._last_wall_time is not None:
                interval = now - self._last_wall_time
                if interval > 0:
                    cpu_utilization = (
                        _cpu_rate_percent(
                            cpu_seconds - self._last_cpu_seconds,
                            interval,
                        )
                        / 100.0
                    )

            self._last_cpu_seconds = cpu_seconds
            self._last_wall_time = now

            total_ram = psutil.virtual_memory().total
            memory_utilization = (rss_bytes / total_ram) if total_ram > 0 else 0.0

            return UtilizationSample(
                cpu_utilization=round(cpu_utilization, 4),
                memory_bytes=rss_bytes,
                memory_utilization=round(memory_utilization, 4),
            )


@dataclass(frozen=True)
class ProcessSnapshot:
    wall_time: float
    rss_bytes: int
    cpu_seconds: float

    @classmethod
    def capture(cls, process: psutil.Process) -> ProcessSnapshot:
        return cls(
            wall_time=time.perf_counter(),
            rss_bytes=_aggregate_rss(process),
            cpu_seconds=_aggregate_cpu_seconds(process),
        )


@dataclass(frozen=True)
class PhasePeaks:
    peak_rss_bytes: int
    peak_cpu_percent: float


def _aggregate_rss(process: psutil.Process) -> int:
    total = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            total += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _aggregate_cpu_seconds(process: psutil.Process) -> float:
    total = 0.0
    for proc in (process, *process.children(recursive=True)):
        try:
            cpu = proc.cpu_times()
            total += cpu.user + cpu.system
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return total


def _bytes_to_mb(value: int) -> float:
    return round(value / _BYTES_PER_MB, 2)


def _cpu_rate_percent(cpu_seconds: float, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    cpu_count = psutil.cpu_count(logical=True) or 1
    return round((cpu_seconds / duration_sec / cpu_count) * 100, 2)


def _memory_percent(rss_bytes: int) -> float:
    total = psutil.virtual_memory().total
    if total <= 0:
        return 0.0
    return round((rss_bytes / total) * 100, 2)


def _collect_phase_peaks(
    process: psutil.Process,
    start: ProcessSnapshot,
    stop_event: threading.Event,
) -> PhasePeaks:
    peak_rss = start.rss_bytes
    peak_cpu = 0.0
    last_cpu = start.cpu_seconds
    last_wall = start.wall_time

    while not stop_event.wait(_SAMPLE_INTERVAL_SEC):
        try:
            rss = _aggregate_rss(process)
            peak_rss = max(peak_rss, rss)

            now = time.perf_counter()
            cpu = _aggregate_cpu_seconds(process)
            interval = now - last_wall
            if interval > 0:
                peak_cpu = max(peak_cpu, _cpu_rate_percent(cpu - last_cpu, interval))
            last_cpu = cpu
            last_wall = now
        except psutil.NoSuchProcess:
            break

    return PhasePeaks(peak_rss_bytes=peak_rss, peak_cpu_percent=peak_cpu)


def _finalize_phase_peaks(start: ProcessSnapshot, end: ProcessSnapshot, sampled: PhasePeaks) -> PhasePeaks:
    duration_sec = end.wall_time - start.wall_time
    phase_cpu = _cpu_rate_percent(end.cpu_seconds - start.cpu_seconds, duration_sec)
    return PhasePeaks(
        peak_rss_bytes=max(sampled.peak_rss_bytes, start.rss_bytes, end.rss_bytes),
        peak_cpu_percent=max(sampled.peak_cpu_percent, phase_cpu),
    )


def _run_peak_sampler(process: psutil.Process, start: ProcessSnapshot, stop_event: threading.Event) -> PhasePeaks:
    return _collect_phase_peaks(process, start, stop_event)


class MetricsTracker(Protocol):
    def log_job_summary(self, **fields: Any) -> None: ...

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]: ...


class ResourceMonitor:
    """Emits peak CPU and memory metrics per pipeline phase for this process tree."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        start = ProcessSnapshot.capture(self._process)
        self._peak_rss_bytes = start.rss_bytes
        self._peak_cpu_percent = 0.0

    def _snapshot(self) -> ProcessSnapshot:
        snapshot = ProcessSnapshot.capture(self._process)
        self._peak_rss_bytes = max(self._peak_rss_bytes, snapshot.rss_bytes)
        return snapshot

    def _record_peaks(self, peaks: PhasePeaks) -> None:
        self._peak_rss_bytes = max(self._peak_rss_bytes, peaks.peak_rss_bytes)
        self._peak_cpu_percent = max(self._peak_cpu_percent, peaks.peak_cpu_percent)

    def _log_event(self, event: str, **fields: Any) -> None:
        payload = {"event": event, **fields}
        logger.info(json.dumps(payload, separators=(",", ":")))

    def log_job_summary(self, **fields: Any) -> None:
        self._snapshot()
        duration_sec = round(float(fields.pop("duration_sec", 0.0)), 3)
        self._log_event(
            "resource_job_summary",
            duration_sec=duration_sec,
            max_cpu_percent=self._peak_cpu_percent,
            max_memory_mb=_bytes_to_mb(self._peak_rss_bytes),
            max_memory_percent=_memory_percent(self._peak_rss_bytes),
            **fields,
        )

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        start = self._snapshot()
        stop_event = threading.Event()
        sampled: list[PhasePeaks] = []

        def _sample() -> None:
            sampled.append(_run_peak_sampler(self._process, start, stop_event))

        sampler = threading.Thread(target=_sample, daemon=True)
        sampler.start()
        try:
            yield
        finally:
            stop_event.set()
            sampler.join(timeout=_SAMPLE_INTERVAL_SEC + 1.0)
            end = self._snapshot()
            sample = sampled[0] if sampled else PhasePeaks(start.rss_bytes, 0.0)
            peaks = _finalize_phase_peaks(start, end, sample)
            self._record_peaks(peaks)
            self._log_event(
                "resource_phase",
                phase=phase,
                duration_sec=round(end.wall_time - start.wall_time, 3),
                max_cpu_percent=peaks.peak_cpu_percent,
                max_memory_mb=_bytes_to_mb(peaks.peak_rss_bytes),
                max_memory_percent=_memory_percent(peaks.peak_rss_bytes),
                **labels,
            )


class NullMetricsTracker:
    """No-op tracker used when metrics are disabled in config."""

    def log_job_summary(self, **fields: Any) -> None:
        return None

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        yield


def create_metrics_tracker(metrics_config: dict[str, Any] | bool | None = None) -> MetricsTracker:
    if isinstance(metrics_config, bool):
        enabled = metrics_config
        otel_config: dict[str, Any] = {}
    elif metrics_config is None:
        enabled = True
        otel_config = {}
    else:
        enabled = bool(metrics_config.get("enabled", True))
        otel_config = metrics_config.get("otel", {}) or {}

    if not enabled:
        return NullMetricsTracker()

    from observability.otel_export import setup_otel
    from observability.otel_tracker import OtelResourceMonitor

    otel = setup_otel(otel_config)
    if otel is not None:
        return OtelResourceMonitor(otel)
    return ResourceMonitor()
