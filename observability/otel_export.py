"""OpenTelemetry export to Grafana Cloud (or any OTLP backend)."""

from __future__ import annotations

import base64
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import unquote

from logger import logger

try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.metrics import Observation
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when deps not installed
    _OTEL_AVAILABLE = False

_METER_NAME = "reddit_tts.pipeline"
_DEFAULT_RESOURCE_EXPORT_INTERVAL_SEC = 1.0
# Keep submission_id off metric labels to avoid Prometheus/Mimir cardinality growth.
_METRIC_LABEL_KEYS = ("part", "total_parts", "subreddit", "destination")
_SPAN_LABEL_KEYS = _METRIC_LABEL_KEYS + ("submission_id",)

_active: PipelineOtel | None = None


def _parse_headers(raw: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for part in raw.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        headers[key.strip()] = unquote(value.strip())
    return headers


def _normalize_authorization(value: str) -> str:
    auth = unquote(value.strip())
    if auth.lower().startswith("basic "):
        return "Basic " + auth[6:].lstrip()
    if auth.startswith("glc_"):
        return auth
    return f"Basic {auth}"


def _grafana_instance_id() -> str:
    for name in (
        "GRAFANA_CLOUD_OTEL_INSTANCE_ID",
        "GRAFANA_CLOUD_INSTANCE_ID",
        "GRAFANA_CLOUD_STACK_ID",
    ):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _resolve_otlp_headers() -> dict[str, str]:
    if _OTEL_AVAILABLE:
        from opentelemetry.util.re import parse_env_headers

        explicit = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
        if explicit:
            headers = dict(parse_env_headers(explicit, liberal=True))
            if not headers:
                headers = _parse_headers(explicit)
            if "Authorization" in headers:
                headers["Authorization"] = _normalize_authorization(headers["Authorization"])
            elif "authorization" in headers:
                headers["Authorization"] = _normalize_authorization(headers["authorization"])
            if headers.get("Authorization", "").startswith("glc_"):
                instance_id = _grafana_instance_id()
                api_key = headers["Authorization"]
                if instance_id:
                    token = base64.b64encode(f"{instance_id}:{api_key}".encode()).decode()
                    headers["Authorization"] = f"Basic {token}"
            return headers

    explicit = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "").strip()
    if explicit:
        headers = _parse_headers(explicit)
        if "Authorization" in headers:
            headers["Authorization"] = _normalize_authorization(headers["Authorization"])
        return headers

    instance_id = _grafana_instance_id()
    api_key = os.getenv("GRAFANA_CLOUD_API_KEY", "").strip()
    if instance_id and api_key:
        token = base64.b64encode(f"{instance_id}:{api_key}".encode()).decode()
        return {"Authorization": f"Basic {token}"}
    return {}


def _resolve_endpoint(config: dict[str, Any]) -> str:
    return (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        or str(config.get("endpoint", "")).strip()
        or os.getenv("GRAFANA_CLOUD_OTEL_ENDPOINT", "").strip()
    )


def _metric_labels(labels: dict[str, Any]) -> dict[str, str]:
    return {key: str(labels[key]) for key in _METRIC_LABEL_KEYS if key in labels and labels[key] is not None}


def _span_labels(labels: dict[str, Any]) -> dict[str, str]:
    return {key: str(labels[key]) for key in _SPAN_LABEL_KEYS if key in labels and labels[key] is not None}


class PipelineOtel:
    """Records pipeline metrics, traces, and log export for Grafana via OTLP."""

    def __init__(
        self,
        *,
        endpoint: str,
        service_name: str,
        export_metrics: bool,
        export_traces: bool,
        export_logs: bool,
        headers: dict[str, str],
        resource_export_interval_sec: float = _DEFAULT_RESOURCE_EXPORT_INTERVAL_SEC,
        utilization_reader: Any | None = None,
    ) -> None:
        if not _OTEL_AVAILABLE:
            raise RuntimeError("OpenTelemetry packages are not installed")

        from observability.resource_metrics import ProcessUtilizationReader

        resource = Resource.create({"service.name": service_name})
        self._endpoint = endpoint.rstrip("/")
        self._headers = headers
        self._log_handler: LoggingHandler | None = None
        self._utilization = utilization_reader or ProcessUtilizationReader()
        self._cached_sample: Any | None = None
        self._cached_sample_at = 0.0
        export_interval_ms = max(int(resource_export_interval_sec * 1000), 1000)

        if export_metrics:
            metric_exporter = OTLPMetricExporter(
                endpoint=f"{self._endpoint}/v1/metrics",
                headers=self._headers,
            )
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=export_interval_ms)
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(meter_provider)
            self._meter_provider = meter_provider
            meter = metrics.get_meter(_METER_NAME)
            self._phase_duration = meter.create_histogram(
                "reddit_tts.phase.duration",
                unit="s",
                description="Wall-clock duration of a pipeline phase",
            )
            self._job_duration = meter.create_histogram(
                "reddit_tts.job.duration",
                unit="s",
                description="Total wall-clock duration of a pipeline job",
            )
            self._video_uploads = meter.create_counter(
                "reddit_tts.video.uploads",
                description="YouTube video uploads by outcome",
            )
            self._errors = meter.create_counter(
                "reddit_tts.errors",
                description="Pipeline errors by phase and type",
            )
            # OTEL semantic convention: observable gauges sampled each export interval.
            meter.create_observable_gauge(
                "process.cpu.utilization",
                callbacks=[self._observe_cpu_utilization],
                unit="1",
                description="Fraction of logical CPU capacity used by the pipeline process tree",
            )
            meter.create_observable_gauge(
                "process.memory.usage",
                callbacks=[self._observe_memory_usage],
                unit="By",
                description="RSS bytes for the pipeline process tree",
            )
            meter.create_observable_gauge(
                "process.memory.utilization",
                callbacks=[self._observe_memory_utilization],
                unit="1",
                description="Fraction of system RAM used by the pipeline process tree",
            )
        else:
            self._meter_provider = None
            self._phase_duration = None
            self._job_duration = None
            self._video_uploads = None
            self._errors = None

        if export_traces:
            tracer_provider = TracerProvider(resource=resource)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=f"{self._endpoint}/v1/traces",
                        headers=self._headers,
                    )
                )
            )
            trace.set_tracer_provider(tracer_provider)
            self._tracer_provider = tracer_provider
            self._tracer = trace.get_tracer(_METER_NAME)
        else:
            self._tracer_provider = None
            self._tracer = None

        if export_logs:
            log_provider = LoggerProvider(resource=resource)
            log_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(
                        endpoint=f"{self._endpoint}/v1/logs",
                        headers=self._headers,
                    )
                )
            )
            self._log_handler = LoggingHandler(level=logging.NOTSET, logger_provider=log_provider)
            logger.addHandler(self._log_handler)
            self._log_provider = log_provider
        else:
            self._log_provider = None

    def set_active_phase(self, phase: str) -> None:
        self._utilization.set_active_phase(phase)

    def _resource_attributes(self) -> dict[str, str]:
        return {"phase": self._utilization.active_phase}

    def _current_sample(self) -> Any:
        """Return one psutil reading shared across gauge callbacks in the same export tick."""
        now = time.perf_counter()
        if self._cached_sample is not None and (now - self._cached_sample_at) < 0.05:
            return self._cached_sample
        self._cached_sample = self._utilization.observe()
        self._cached_sample_at = now
        return self._cached_sample

    def _observe_cpu_utilization(self, _options: Any) -> Iterator[Observation]:
        sample = self._current_sample()
        yield Observation(sample.cpu_utilization, self._resource_attributes())

    def _observe_memory_usage(self, _options: Any) -> Iterator[Observation]:
        sample = self._current_sample()
        yield Observation(sample.memory_bytes, self._resource_attributes())

    def _observe_memory_utilization(self, _options: Any) -> Iterator[Observation]:
        sample = self._current_sample()
        yield Observation(sample.memory_utilization, self._resource_attributes())

    @contextmanager
    def span(self, phase: str, **labels: Any) -> Iterator[None]:
        if self._tracer is None:
            yield
            return

        attributes = {"phase": phase, **_span_labels(labels)}
        with self._tracer.start_as_current_span(f"pipeline.{phase}", attributes=attributes):
            yield

    def emit_resource_event(self, event: str, **fields: Any) -> None:
        if event == "resource_phase":
            self._record_phase(fields)
        elif event == "resource_job_summary":
            self._record_job_summary(fields)

    def record_upload_success(self, **labels: Any) -> None:
        if self._video_uploads is None:
            return
        attrs = {"status": "success", **_metric_labels(labels)}
        self._video_uploads.add(1, attrs)

    def record_upload_error(self, error_type: str, **labels: Any) -> None:
        if self._video_uploads is not None:
            attrs = {"status": "error", "error_type": error_type, **_metric_labels(labels)}
            self._video_uploads.add(1, attrs)
        self.record_error("youtube_upload", error_type, **labels)

    def record_error(self, phase: str, error_type: str, **labels: Any) -> None:
        if self._errors is None:
            return
        attrs = {"phase": phase, "error_type": error_type, **_metric_labels(labels)}
        self._errors.add(1, attrs)

    def _record_phase(self, fields: dict[str, Any]) -> None:
        if self._phase_duration is None:
            return
        attrs = {"phase": str(fields.get("phase", "unknown")), **_metric_labels(fields)}
        self._phase_duration.record(float(fields.get("duration_sec", 0.0)), attrs)

    def _record_job_summary(self, fields: dict[str, Any]) -> None:
        if self._job_duration is None:
            return
        attrs = _metric_labels(fields)
        self._job_duration.record(float(fields.get("duration_sec", 0.0)), attrs)

    def shutdown(self) -> None:
        if self._log_handler is not None:
            logger.removeHandler(self._log_handler)
            self._log_handler = None
        if self._log_provider is not None:
            self._log_provider.force_flush()
            self._log_provider.shutdown()
        if self._meter_provider is not None:
            self._meter_provider.force_flush()
            self._meter_provider.shutdown()
        if self._tracer_provider is not None:
            self._tracer_provider.force_flush()
            self._tracer_provider.shutdown()


def setup_otel(config: dict[str, Any] | None) -> PipelineOtel | None:
    """Initialize OTLP export when enabled in config and endpoint credentials are present."""
    global _active

    otel_config = config or {}
    if not otel_config.get("enabled", False):
        return None

    from config import DEBUG

    if DEBUG:
        logger.info("OpenTelemetry export disabled (DEBUG=True)")
        return None

    if not _OTEL_AVAILABLE:
        logger.warning("metrics.otel.enabled is true but OpenTelemetry packages are not installed")
        return None

    endpoint = _resolve_endpoint(otel_config)
    if not endpoint:
        logger.warning("metrics.otel.enabled is true but no OTLP endpoint is configured")
        return None

    headers = _resolve_otlp_headers()
    if not headers:
        logger.warning("metrics.otel.enabled is true but OTLP auth headers are missing")
        return None

    service_name = (
        os.getenv("OTEL_SERVICE_NAME", "").strip() or str(otel_config.get("service_name", "reddit-tts-video")).strip()
    )

    try:
        resource_interval = float(
            otel_config.get("resource_export_interval_sec", _DEFAULT_RESOURCE_EXPORT_INTERVAL_SEC)
        )
        _active = PipelineOtel(
            endpoint=endpoint,
            service_name=service_name,
            export_metrics=bool(otel_config.get("export_metrics", True)),
            export_traces=bool(otel_config.get("export_traces", True)),
            export_logs=bool(otel_config.get("export_logs", True)),
            headers=headers,
            resource_export_interval_sec=resource_interval,
        )
    except Exception as exc:  # pragma: no cover - network/provider init edge cases
        logger.error(f"Failed to initialize OpenTelemetry export: {exc}")
        return None

    logger.info(f"OpenTelemetry export enabled (service={service_name})")
    return _active


def get_otel() -> PipelineOtel | None:
    return _active


def shutdown_otel() -> None:
    global _active
    if _active is not None:
        _active.shutdown()
        _active = None


def record_video_upload_success(**labels: Any) -> None:
    if _active is not None:
        _active.record_upload_success(**labels)


def record_video_upload_error(error_type: str, **labels: Any) -> None:
    if _active is not None:
        _active.record_upload_error(error_type, **labels)
