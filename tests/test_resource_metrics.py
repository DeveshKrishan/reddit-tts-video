import json
import unittest
from unittest.mock import MagicMock, patch

from observability.resource_metrics import (
    NullMetricsTracker,
    ProcessSnapshot,
    ResourceMonitor,
    _cpu_percent,
    _memory_percent,
)


class TestResourceMetrics(unittest.TestCase):
    def test_cpu_percent_scales_by_cpu_count(self) -> None:
        with patch("observability.resource_metrics.psutil.cpu_count", return_value=8):
            self.assertEqual(_cpu_percent(4.0, 2.0), 25.0)

    def test_cpu_percent_zero_duration(self) -> None:
        self.assertEqual(_cpu_percent(1.0, 0.0), 0.0)

    def test_memory_percent_of_system_ram(self) -> None:
        with patch("observability.resource_metrics.psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.total = 16 * 1024 * 1024 * 1024
            self.assertEqual(_memory_percent(8 * 1024 * 1024 * 1024), 50.0)

    def test_null_tracker_emits_no_logs(self) -> None:
        tracker = NullMetricsTracker()
        with patch("observability.resource_metrics.logger") as mock_logger:
            with tracker.track_phase("tts", submission_id="abc"):
                pass
            tracker.log_job_summary(duration_sec=1.0)
        mock_logger.info.assert_not_called()

    def test_phase_log_emits_simple_fields(self) -> None:
        start = ProcessSnapshot(wall_time=0.0, rss_bytes=100 * 1024 * 1024, cpu_user=1.0, cpu_system=0.5)
        end = ProcessSnapshot(wall_time=2.0, rss_bytes=150 * 1024 * 1024, cpu_user=3.0, cpu_system=1.0)

        with (
            patch("observability.resource_metrics.psutil.Process", return_value=MagicMock()),
            patch.object(ResourceMonitor, "_snapshot", side_effect=[start, end, end]),
            patch("observability.resource_metrics.logger") as mock_logger,
            patch("observability.resource_metrics.psutil.cpu_count", return_value=4),
            patch("observability.resource_metrics.psutil.virtual_memory") as mock_vm,
        ):
            mock_vm.return_value.total = 16 * 1024 * 1024 * 1024
            monitor = ResourceMonitor()
            with monitor.track_phase("tts", submission_id="abc123"):
                pass

        payload = json.loads(mock_logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "resource_phase")
        self.assertEqual(payload["phase"], "tts")
        self.assertEqual(payload["submission_id"], "abc123")
        self.assertEqual(payload["duration_sec"], 2.0)
        self.assertEqual(payload["cpu_percent"], 31.25)
        self.assertEqual(payload["memory_mb"], 150.0)
        self.assertEqual(payload["memory_percent"], 0.92)

    def test_job_summary_uses_peak_memory(self) -> None:
        end = ProcessSnapshot(1.0, 80 * 1024 * 1024, 5.0, 1.0)

        with (
            patch("observability.resource_metrics.psutil.Process", return_value=MagicMock()),
            patch.object(ResourceMonitor, "_snapshot", return_value=end),
            patch("observability.resource_metrics.logger") as mock_logger,
            patch("observability.resource_metrics.psutil.virtual_memory") as mock_vm,
        ):
            mock_vm.return_value.total = 16 * 1024 * 1024 * 1024
            monitor = ResourceMonitor()
            monitor._peak_rss_bytes = 100 * 1024 * 1024
            monitor._job_start_cpu = 0.0
            monitor.log_job_summary(duration_sec=10.0, submissions_processed=2)

        payload = json.loads(mock_logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "resource_job_summary")
        self.assertEqual(payload["duration_sec"], 10.0)
        self.assertEqual(payload["memory_mb"], 100.0)
        self.assertEqual(payload["submissions_processed"], 2)
