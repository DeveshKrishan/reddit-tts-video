"""Metrics tracker that combines stdout JSON metrics with OTLP export."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from observability.otel_export import PipelineOtel
from observability.resource_metrics import ResourceMonitor


class OtelResourceMonitor(ResourceMonitor):
    """Emits resource metrics to stdout and forwards the same events to OTLP."""

    def __init__(self, otel: PipelineOtel) -> None:
        super().__init__()
        self._otel = otel

    def _log_event(self, event: str, **fields: Any) -> None:
        super()._log_event(event, **fields)
        self._otel.emit_resource_event(event, **fields)

    @contextmanager
    def track_phase(self, phase: str, **labels: Any) -> Iterator[None]:
        self._otel.set_active_phase(phase)
        try:
            with self._otel.span(phase, **labels):
                try:
                    with super().track_phase(phase, **labels):
                        yield
                except Exception as exc:
                    self._otel.record_error(phase, type(exc).__name__, **labels)
                    raise
        finally:
            self._otel.set_active_phase("idle")
