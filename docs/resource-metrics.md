# Resource Metrics

Process-level CPU and memory tracking for the reddit-tts-video pipeline using [psutil](https://github.com/giampaolo/psutil).

## Why psutil

- Cross-platform (macOS, Linux, GitHub Actions)
- Measures the **current Python process** only (not whole-machine stats)
- Standard choice for operational metrics in Python services and batch jobs
- Lightweight: snapshots at phase boundaries, no background sampling thread

## Configuration

```yaml
# configs/youtube_config.yaml
metrics:
  enabled: true   # set false to disable all resource_* log lines
```

## Log format

Each metric line uses the existing UTC logger prefix, with a **JSON payload** as the message body. Parse by extracting the JSON after `INFO - `.

### Events

| Event | When emitted |
|-------|----------------|
| `resource_job_start` | Once at the start of `main()` |
| `resource_phase` | After each tracked pipeline phase completes |
| `resource_job_summary` | Once at the end of `main()` |

### Tracked phases

| Phase | Labels | Typical cost |
|-------|--------|--------------|
| `fetch_submissions` | — | Network I/O, low memory |
| `tts` | `submission_id` | Edge TTS network calls |
| `video_render` | `submission_id` | Whisper + MoviePy (high CPU/RSS) |
| `youtube_upload` | `submission_id`, `part`, `total_parts` | Network I/O |

### Example output

```
2026-06-20 12:00:00 UTC - INFO - {"event":"resource_job_start","rss_mb":118.42,"vms_mb":401.55,"cpu_time_user_sec":0.012,"cpu_time_system_sec":0.004,"num_threads":1}
2026-06-20 12:00:02 UTC - INFO - {"event":"resource_phase","phase":"fetch_submissions","duration_sec":1.842,"rss_mb_start":118.42,"rss_mb_end":121.05,"rss_mb_delta":2.63,"rss_mb_peak":121.05,"cpu_time_user_sec":0.118,"cpu_time_system_sec":0.021,"cpu_time_total_sec":0.139,"cpu_avg_percent":3.78,"num_threads_start":1,"num_threads_end":3}
2026-06-20 12:00:18 UTC - INFO - {"event":"resource_phase","phase":"tts","submission_id":"abc123","duration_sec":15.204,"rss_mb_start":121.05,"rss_mb_end":128.33,"rss_mb_delta":7.28,"rss_mb_peak":128.33,"cpu_time_user_sec":0.412,"cpu_time_system_sec":0.088,"cpu_time_total_sec":0.5,"cpu_avg_percent":2.06,"num_threads_start":3,"num_threads_end":4}
2026-06-20 12:04:55 UTC - INFO - {"event":"resource_phase","phase":"video_render","submission_id":"abc123","duration_sec":277.441,"rss_mb_start":128.33,"rss_mb_end":1842.17,"rss_mb_delta":1713.84,"rss_mb_peak":1842.17,"cpu_time_user_sec":142.881,"cpu_time_system_sec":18.204,"cpu_time_total_sec":161.085,"cpu_avg_percent":115.42,"num_threads_start":4,"num_threads_end":12}
2026-06-20 12:05:40 UTC - INFO - {"event":"resource_phase","phase":"youtube_upload","submission_id":"abc123","part":1,"total_parts":1,"duration_sec":44.992,"rss_mb_start":1842.17,"rss_mb_end":1838.02,"rss_mb_delta":-4.15,"rss_mb_peak":1842.17,"cpu_time_user_sec":2.104,"cpu_time_system_sec":0.612,"cpu_time_total_sec":2.716,"cpu_avg_percent":3.77,"num_threads_start":12,"num_threads_end":10}
2026-06-20 12:05:40 UTC - INFO - {"event":"resource_job_summary","rss_mb_peak":1842.17,"rss_mb_end":1838.02,"cpu_time_user_sec_total":148.612,"cpu_time_system_sec_total":19.118,"num_threads_end":10,"job_run_time_sec":340.12,"job_start_time":"2026-06-20T12:00:00Z","job_end_time":"2026-06-20T12:05:40Z","destination":"YouTube","submissions_processed":1}
```

### Field reference

| Field | Meaning |
|-------|---------|
| `rss_mb` | Resident Set Size — physical RAM used by this process (primary OOM signal) |
| `vms_mb` | Virtual memory size |
| `rss_mb_peak` | Highest RSS seen since job start |
| `rss_mb_delta` | RSS change during the phase |
| `cpu_time_user_sec` | CPU seconds in user space during the phase |
| `cpu_time_system_sec` | CPU seconds in kernel space during the phase |
| `cpu_avg_percent` | `(user + system) / duration / logical_cpus × 100` — can exceed 100% on multi-core |
| `duration_sec` | Wall-clock time for the phase |
| `num_threads` | Active thread count (useful for MoviePy / Whisper parallelism) |

## Future extensions (out of scope)

- Persist metrics to SQLite or a time-series DB (Phase 4 in `docs/roadmap.md`)
- Per-step breakdown inside `video_render` (Whisper vs encode vs composite)
- System-wide memory pressure via `psutil.virtual_memory()`
