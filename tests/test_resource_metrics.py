import json
import unittest
from unittest.mock import MagicMock, patch

from resource_metrics import NullMetricsTracker, ProcessSnapshot, ResourceMonitor, _avg_cpu_percent


class TestResourceMetrics(unittest.TestCase):
    def test_avg_cpu_percent_scales_by_cpu_count(self) -> None:
        with patch("resource_metrics.psutil.cpu_count", return_value=8):
            self.assertEqual(_avg_cpu_percent(4.0, 2.0), 25.0)

    def test_avg_cpu_percent_zero_duration(self) -> None:
        self.assertEqual(_avg_cpu_percent(1.0, 0.0), 0.0)

    def test_null_tracker_emits_no_logs(self) -> None:
        tracker = NullMetricsTracker()
        with patch("resource_metrics.logger") as mock_logger:
            tracker.log_job_start()
            with tracker.track_phase("tts", submission_id="abc"):
                pass
            tracker.log_job_summary(job_run_time_sec=1.0)
        mock_logger.info.assert_not_called()

    def test_resource_monitor_logs_structured_json(self) -> None:
        start = ProcessSnapshot(
            wall_time=0.0,
            rss_bytes=100 * 1024 * 1024,
            vms_bytes=200 * 1024 * 1024,
            cpu_user=1.0,
            cpu_system=0.5,
            num_threads=2,
        )
        end = ProcessSnapshot(
            wall_time=2.0,
            rss_bytes=150 * 1024 * 1024,
            vms_bytes=250 * 1024 * 1024,
            cpu_user=3.0,
            cpu_system=1.0,
            num_threads=4,
        )

        mock_process = MagicMock()
        with (
            patch("resource_metrics.psutil.Process", return_value=mock_process),
            patch.object(ResourceMonitor, "_snapshot", side_effect=[start, end, end]),
            patch("resource_metrics.logger") as mock_logger,
            patch("resource_metrics.psutil.cpu_count", return_value=4),
        ):
            monitor = ResourceMonitor()
            with monitor.track_phase("tts", submission_id="abc123"):
                pass

        payload = json.loads(mock_logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "resource_phase")
        self.assertEqual(payload["phase"], "tts")
        self.assertEqual(payload["submission_id"], "abc123")
        self.assertEqual(payload["rss_mb_start"], 100.0)
        self.assertEqual(payload["rss_mb_end"], 150.0)
        self.assertEqual(payload["rss_mb_delta"], 50.0)
        self.assertEqual(payload["cpu_time_user_sec"], 2.0)
        self.assertEqual(payload["cpu_time_system_sec"], 0.5)

    def test_job_summary_includes_peak_rss(self) -> None:
        end = ProcessSnapshot(1.0, 80 * 1024 * 1024, 0, 5.0, 1.0, 1)

        with (
            patch("resource_metrics.psutil.Process", return_value=MagicMock()),
            patch.object(ResourceMonitor, "_snapshot", return_value=end),
            patch("resource_metrics.logger") as mock_logger,
        ):
            monitor = ResourceMonitor()
            monitor._peak_rss_bytes = 100 * 1024 * 1024
            monitor.log_job_summary(job_run_time_sec=10.0, submissions_processed=2)

        payload = json.loads(mock_logger.info.call_args.args[0])
        self.assertEqual(payload["event"], "resource_job_summary")
        self.assertEqual(payload["rss_mb_peak"], 100.0)
        self.assertEqual(payload["submissions_processed"], 2)
