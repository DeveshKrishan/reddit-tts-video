import os
import unittest
from unittest.mock import MagicMock, patch

from observability.otel_export import (
    PipelineOtel,
    _parse_headers,
    _resolve_otlp_headers,
    record_video_upload_error,
    record_video_upload_success,
    setup_otel,
    shutdown_otel,
)
from observability.otel_tracker import OtelResourceMonitor
from observability.resource_metrics import PhasePeaks, ProcessSnapshot, ProcessUtilizationReader, ResourceMonitor


class TestOtelExport(unittest.TestCase):
    def test_parse_headers(self) -> None:
        headers = _parse_headers("Authorization=Basic abc, X-Test=1")
        self.assertEqual(headers["Authorization"], "Basic abc")
        self.assertEqual(headers["X-Test"], "1")

    def test_parse_headers_url_decodes_values(self) -> None:
        headers = _parse_headers("Authorization=Basic%20abc123")
        self.assertEqual(headers["Authorization"], "Basic abc123")

    def test_normalize_authorization_adds_basic_prefix(self) -> None:
        from observability.otel_export import _normalize_authorization

        self.assertEqual(_normalize_authorization("abc123"), "Basic abc123")
        self.assertEqual(_normalize_authorization("Basic abc123"), "Basic abc123")
        self.assertEqual(_normalize_authorization("Basic%20abc123"), "Basic abc123")

    def test_resolve_headers_from_url_encoded_grafana_header(self) -> None:
        with patch.dict(
            os.environ,
            {"OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic%20dGVzdDoxMjM="},
            clear=False,
        ):
            headers = _resolve_otlp_headers()
        self.assertEqual(headers["Authorization"], "Basic dGVzdDoxMjM=")

    def test_resolve_headers_from_grafana_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OTEL_EXPORTER_OTLP_HEADERS": "",
                "GRAFANA_CLOUD_OTEL_INSTANCE_ID": "123456",
                "GRAFANA_CLOUD_API_KEY": "glc_secret",
            },
            clear=False,
        ):
            headers = _resolve_otlp_headers()
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    def test_setup_otel_disabled_returns_none(self) -> None:
        self.assertIsNone(setup_otel({"enabled": False}))

    @patch("observability.otel_export._OTEL_AVAILABLE", False)
    def test_setup_otel_missing_packages(self) -> None:
        with patch("observability.otel_export.logger") as mock_logger:
            result = setup_otel({"enabled": True, "endpoint": "https://example.com/otlp"})
        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()

    def test_setup_otel_missing_endpoint(self) -> None:
        with patch("observability.otel_export.logger") as mock_logger:
            result = setup_otel({"enabled": True})
        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()

    @patch("observability.otel_export._OTEL_AVAILABLE", True)
    @patch("observability.otel_export.PipelineOtel")
    def test_setup_otel_success(self, mock_pipeline: MagicMock) -> None:
        with patch.dict(
            os.environ,
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.com/otlp",
                "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic token",
            },
            clear=False,
        ):
            setup_otel({"enabled": True})
        mock_pipeline.assert_called_once()
        shutdown_otel()

    def test_record_upload_helpers_noop_without_active_otel(self) -> None:
        shutdown_otel()
        record_video_upload_success(submission_id="abc")
        record_video_upload_error("ValueError", submission_id="abc")

    def test_setup_otel_missing_headers(self) -> None:
        with (
            patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://example.com/otlp"}, clear=False),
            patch("observability.otel_export._OTEL_AVAILABLE", True),
            patch("observability.otel_export.logger") as mock_logger,
        ):
            result = setup_otel({"enabled": True})
        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()

    @patch("observability.otel_export._OTEL_AVAILABLE", True)
    @patch("observability.otel_export.metrics")
    @patch("observability.otel_export.trace")
    def test_pipeline_otel_records_phase_and_upload_metrics(
        self, mock_trace: MagicMock, mock_metrics: MagicMock
    ) -> None:
        meter = MagicMock()
        mock_metrics.get_meter.return_value = meter
        phase_duration = MagicMock()
        job_duration = MagicMock()
        uploads = MagicMock()
        errors = MagicMock()
        meter.create_histogram.side_effect = [phase_duration, job_duration]
        meter.create_counter.side_effect = [uploads, errors]
        meter.create_observable_gauge.return_value = MagicMock()

        tracer = MagicMock()
        mock_trace.get_tracer.return_value = tracer
        span_cm = MagicMock()
        tracer.start_as_current_span.return_value = span_cm
        span_cm.__enter__ = MagicMock(return_value=None)
        span_cm.__exit__ = MagicMock(return_value=False)

        utilization = MagicMock()
        utilization.active_phase = "tts"
        utilization.observe.return_value = MagicMock(
            cpu_utilization=0.42,
            memory_bytes=256 * 1024 * 1024,
            memory_utilization=0.11,
        )

        otel = PipelineOtel(
            endpoint="https://example.com/otlp",
            service_name="test-service",
            export_metrics=True,
            export_traces=True,
            export_logs=False,
            headers={"Authorization": "Basic token"},
            utilization_reader=utilization,
        )

        otel.emit_resource_event(
            "resource_phase",
            phase="tts",
            submission_id="abc",
            duration_sec=1.5,
            max_cpu_percent=42.0,
            max_memory_mb=256.0,
        )
        phase_duration.record.assert_called_once()
        meter.create_observable_gauge.assert_called()
        self.assertEqual(meter.create_observable_gauge.call_count, 3)

        otel.record_upload_success(submission_id="abc", subreddit="AITAH")
        uploads.add.assert_called_with(1, {"status": "success", "subreddit": "AITAH"})

        otel.record_upload_error("RefreshError", submission_id="abc")
        uploads.add.assert_called()
        errors.add.assert_called_with(
            1,
            {"phase": "youtube_upload", "error_type": "RefreshError"},
        )

        otel.shutdown()


class TestShutdownOtel(unittest.TestCase):
    @patch("observability.otel_export._OTEL_AVAILABLE", True)
    @patch("observability.otel_export.metrics")
    @patch("observability.otel_export.trace")
    def test_shutdown_flushes_providers(self, mock_trace: MagicMock, mock_metrics: MagicMock) -> None:
        meter_provider = MagicMock()
        tracer_provider = MagicMock()
        mock_metrics.set_meter_provider.return_value = None
        mock_trace.set_tracer_provider.return_value = None
        mock_metrics.get_meter.return_value = MagicMock(
            create_histogram=MagicMock(return_value=MagicMock()),
            create_counter=MagicMock(return_value=MagicMock()),
        )
        mock_trace.get_tracer.return_value = MagicMock()

        with patch("observability.otel_export.MeterProvider", return_value=meter_provider):
            with patch("observability.otel_export.TracerProvider", return_value=tracer_provider):
                with patch("observability.otel_export.PeriodicExportingMetricReader"):
                    with patch("observability.otel_export.OTLPMetricExporter"):
                        with patch("observability.otel_export.BatchSpanProcessor"):
                            with patch("observability.otel_export.OTLPSpanExporter"):
                                otel = PipelineOtel(
                                    endpoint="https://example.com/otlp",
                                    service_name="test-service",
                                    export_metrics=True,
                                    export_traces=True,
                                    export_logs=False,
                                    headers={"Authorization": "Basic token"},
                                )

        otel.shutdown()
        meter_provider.force_flush.assert_called_once()
        meter_provider.shutdown.assert_called_once()
        tracer_provider.force_flush.assert_called_once()
        tracer_provider.shutdown.assert_called_once()
        shutdown_otel()


class TestProcessUtilizationReader(unittest.TestCase):
    def test_observe_returns_cpu_and_memory_fractions(self) -> None:
        process = MagicMock()
        process.memory_info.return_value.rss = 512 * 1024 * 1024
        process.cpu_times.return_value = MagicMock(user=1.0, system=0.5)
        process.children.return_value = []

        with (
            patch("observability.resource_metrics.psutil.virtual_memory") as mock_vm,
            patch("observability.resource_metrics.time.perf_counter", side_effect=[0.0, 1.0, 2.0]),
            patch("observability.resource_metrics.psutil.cpu_count", return_value=4),
        ):
            mock_vm.return_value.total = 1024 * 1024 * 1024
            reader = ProcessUtilizationReader(process=process)
            first = reader.observe()
            process.cpu_times.return_value = MagicMock(user=3.0, system=1.0)
            second = reader.observe()

        self.assertEqual(first.cpu_utilization, 0.0)
        self.assertEqual(first.memory_bytes, 512 * 1024 * 1024)
        self.assertAlmostEqual(first.memory_utilization, 0.5, places=2)
        self.assertGreater(second.cpu_utilization, 0.0)
        self.assertLessEqual(second.cpu_utilization, 1.0)

    def test_active_phase_is_thread_safe(self) -> None:
        reader = ProcessUtilizationReader(process=MagicMock())
        reader.set_active_phase("video_render")
        self.assertEqual(reader.active_phase, "video_render")


class TestOtelResourceMonitor(unittest.TestCase):
    def test_forwards_logged_events_to_otel(self) -> None:
        otel = MagicMock()
        monitor = OtelResourceMonitor(otel)

        with patch.object(ResourceMonitor, "_log_event") as mock_super_log:
            monitor._log_event("resource_phase", phase="tts", duration_sec=1.0)

        mock_super_log.assert_called_once()
        otel.emit_resource_event.assert_called_once_with("resource_phase", phase="tts", duration_sec=1.0)

    def test_phase_error_records_otel_error(self) -> None:
        otel = MagicMock()
        otel.span.return_value.__enter__ = MagicMock(return_value=None)
        otel.span.return_value.__exit__ = MagicMock(return_value=False)

        start = ProcessSnapshot(wall_time=0.0, rss_bytes=100, cpu_seconds=0.0)
        end = ProcessSnapshot(wall_time=1.0, rss_bytes=100, cpu_seconds=0.0)
        sampled = PhasePeaks(peak_rss_bytes=100, peak_cpu_percent=0.0)

        with (
            patch("observability.resource_metrics.psutil.Process", return_value=MagicMock()),
            patch.object(ProcessSnapshot, "capture", return_value=start),
            patch.object(ResourceMonitor, "_snapshot", side_effect=[start, end, end]),
            patch("observability.resource_metrics._run_peak_sampler", return_value=sampled),
            patch("observability.resource_metrics.logger"),
            patch("observability.resource_metrics.psutil.cpu_count", return_value=4),
            patch("observability.resource_metrics.psutil.virtual_memory") as mock_vm,
        ):
            mock_vm.return_value.total = 16 * 1024 * 1024 * 1024
            monitor = OtelResourceMonitor(otel)
            with self.assertRaises(ValueError):
                with monitor.track_phase("tts", submission_id="abc"):
                    raise ValueError("boom")

        otel.record_error.assert_called_once_with("tts", "ValueError", submission_id="abc")
        otel.set_active_phase.assert_any_call("tts")
        otel.set_active_phase.assert_any_call("idle")


class TestCreateMetricsTrackerOtel(unittest.TestCase):
    def test_create_metrics_tracker_disabled(self) -> None:
        from observability.resource_metrics import NullMetricsTracker, create_metrics_tracker

        tracker = create_metrics_tracker({"enabled": False})
        self.assertIsInstance(tracker, NullMetricsTracker)

    @patch("observability.otel_export.setup_otel", return_value=None)
    def test_create_metrics_tracker_without_otel(self, _mock_setup: MagicMock) -> None:
        from observability.resource_metrics import ResourceMonitor, create_metrics_tracker

        tracker = create_metrics_tracker({"enabled": True, "otel": {"enabled": False}})
        self.assertIsInstance(tracker, ResourceMonitor)

    @patch("observability.otel_export.setup_otel")
    def test_create_metrics_tracker_with_otel(self, mock_setup: MagicMock) -> None:
        from observability.resource_metrics import create_metrics_tracker

        mock_otel = MagicMock()
        mock_setup.return_value = mock_otel
        tracker = create_metrics_tracker({"enabled": True, "otel": {"enabled": True}})
        self.assertIsInstance(tracker, OtelResourceMonitor)


if __name__ == "__main__":
    unittest.main()
