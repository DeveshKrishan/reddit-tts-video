# Observability

This folder owns **how the pipeline measures and reports itself**. Application code imports from here; future exporters and dashboards build on the same structured events.

## Layout

| File | Purpose |
|------|---------|
| `resource_metrics.py` | v1 process-tree metrics via `psutil` — phase timing, peak CPU %, peak memory MB / % |
| `otel_export.py` | Optional OTLP push to Grafana Cloud — metrics, traces, logs |
| `otel_tracker.py` | Wraps `ResourceMonitor` and forwards events to OTLP |
| `README.md` | This doc — current format, config, and upgrade paths |

Planned additions (not implemented yet):

| File | Purpose |
|------|---------|
| `alloy/` | Sample Grafana Alloy config to ship stdout logs without Python changes |

## Design principles

1. **Measure in Python, ship elsewhere.** `psutil` snapshots stay in-process; Grafana, Loki, or a DB are optional sinks.
2. **Structured JSON on stdout.** Every metric line is one JSON object — easy to grep locally and parse in Loki.
3. **Batch-job friendly.** The pipeline exits after each run, so prefer log shipping or **push** APIs over Prometheus scrape.
4. **Opt-in cloud export.** Local dev keeps `metrics.enabled: true` with stdout only; cloud keys stay in env / secrets.

## Configuration

```yaml
# configs/youtube_config.yaml
metrics:
  enabled: true   # false disables all resource_* JSON log lines
  otel:
    enabled: false  # true pushes metrics/traces/logs via OTLP when credentials are set
    service_name: reddit-tts-video
    export_metrics: true
    export_traces: true
    export_logs: true
```

Env vars for Grafana Cloud (never commit):

| Variable | Purpose |
|----------|---------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gateway URL (e.g. `https://otlp-gateway-prod-us-central-0.grafana.net/otlp`) |
| `GRAFANA_CLOUD_OTEL_INSTANCE_ID` | Grafana Cloud stack instance ID |
| `GRAFANA_CLOUD_API_KEY` | Grafana Cloud access policy token |
| `OTEL_EXPORTER_OTLP_HEADERS` | Auth header — Grafana often copies as `Authorization=Basic%20...` (URL-encoded); both forms work |
| `OTEL_SERVICE_NAME` | Overrides `service_name` in config |

Usage in `main.py`:

```python
from observability import create_metrics_tracker, shutdown_otel

metrics = create_metrics_tracker(config.get("metrics", {}))
with metrics.track_phase("video_render", submission_id=submission.id):
    videos = create_videos(submission)
# shutdown_otel() flushes pending OTLP batches at process exit
```

## Current log format (v1)

Logger prefix is unchanged (`YYYY-MM-DD HH:MM:SS UTC - INFO -`). The message body is JSON.

### Events

| Event | When |
|-------|------|
| `resource_phase` | After each tracked phase |
| `resource_job_summary` | Once at end of `main()` |

### Per-phase fields

| Field | Meaning |
|-------|---------|
| `duration_sec` | Wall-clock time for the phase |
| `max_cpu_percent` | Peak CPU use during the phase (process + child processes; can exceed 100% on multi-core) |
| `max_memory_mb` | Peak RSS in MB during the phase (process + child processes) |
| `max_memory_percent` | Peak RSS as % of total system RAM |

Sampling runs every 0.5s in a background thread while the phase is active, plus start/end snapshots so short phases are still covered.

Optional labels: `phase`, `submission_id`, `part`, `total_parts`.

### Tracked phases

| Phase | Labels |
|-------|--------|
| `fetch_submissions` | — |
| `tts` | `submission_id` |
| `video_render` | `submission_id` |
| `youtube_upload` | `submission_id`, `part`, `total_parts` |

### Example

```
2026-06-20 12:04:55 UTC - INFO - {"event":"resource_phase","phase":"video_render","submission_id":"abc123","duration_sec":277.441,"max_cpu_percent":115.42,"max_memory_mb":1842.17,"max_memory_percent":11.3}
2026-06-20 12:05:40 UTC - INFO - {"event":"resource_job_summary","duration_sec":340.12,"max_cpu_percent":115.42,"max_memory_mb":1842.17,"max_memory_percent":11.3,"job_start_time":"2026-06-20T12:00:00Z","job_end_time":"2026-06-20T12:05:40Z","destination":"YouTube","submissions_processed":1}
```

Job summary uses the same fields; `max_*` values are the highest peaks seen across the full run.

---

## Building on these metrics

Below are practical upgrade paths, ordered from least to most effort.

### Option 1 — Stdout only (current)

**Effort:** none  
**Cost:** free  

Grep local runs:

```bash
python3 main.py 2>&1 | grep resource_phase
```

Good for dev and CI artifacts. No external dependencies.

---

### Option 2 — Grafana Cloud Free + Grafana Alloy (recommended next step)

**Effort:** low (no Python changes)  
**Cost:** Grafana Cloud free tier (Loki + Prometheus + Grafana UI)

Run [Grafana Alloy](https://grafana.com/docs/alloy/latest/) on the host that executes `main.py`:

1. Alloy tails stdout or a log file.
2. Parses JSON lines where `"event":"resource_phase"`.
3. Sends raw lines → **Loki** (logs).
4. Optionally derives Prometheus metrics from JSON fields (duration, memory, CPU).

**Pros:** Secrets stay outside the repo; Python stays simple.  
**Cons:** Requires an agent on the runner; GitHub Actions needs an Alloy step or log upload.

**Loki query example:**

```logql
{job="reddit-tts-video"} | json | event="resource_phase" | phase="video_render"
```

**Dashboard ideas:**

- Bar chart: `duration_sec` by `phase`
- Stat panel: `max_memory_mb` where `phase="video_render"`
- Table: last run's `resource_job_summary`

---

### Option 3 — Python push to Grafana Cloud

**Effort:** medium  
**Cost:** free tier; watch series / ingest limits

Add `observability/grafana_export.py` that reads the same four fields and pushes:

| Sink | API | When to push |
|------|-----|--------------|
| Loki | `POST /loki/api/v1/push` | Each `resource_phase` / summary line |
| Prometheus (Mimir) | remote write | Gauges per phase at phase end |

Suggested metric names:

- `reddit_tts_phase_duration_seconds{phase,submission_id}`
- `reddit_tts_phase_max_cpu_percent{phase}`
- `reddit_tts_phase_max_memory_mb{phase}`
- `reddit_tts_phase_max_memory_percent{phase}`

Env vars (never commit):

- `GRAFANA_CLOUD_LOKI_URL`
- `GRAFANA_CLOUD_LOKI_USER`
- `GRAFANA_CLOUD_API_KEY`
- `GRAFANA_CLOUD_PROMETHEUS_URL`

**Pros:** Works in CI without a host agent; first-class time series.  
**Cons:** Network calls during pipeline; needs credential management.

---

## OpenTelemetry export (Grafana Cloud)

**Status:** implemented in `otel_export.py`  
**Effort:** medium  
**Cost:** Grafana Cloud free tier OTLP endpoint

When `metrics.otel.enabled: true` and credentials are present, each run pushes:

| Signal | What gets exported |
|--------|-------------------|
| **Metrics** | Phase duration, peak CPU/memory, job duration, upload success/error counters, error counters |
| **Traces** | One span per pipeline phase (`fetch_submissions`, `tts`, `video_render`, `youtube_upload`) |
| **Logs** | All `logger` output via OTLP (stdout JSON metrics still emit locally) |

### Metric names

| Metric | Type | Labels |
|--------|------|--------|
| `reddit_tts.phase.duration` | histogram (s) | `phase`, `subreddit`, `part`, `total_parts` |
| `reddit_tts.job.duration` | histogram (s) | `destination`, … |
| `reddit_tts.video.uploads` | counter | `status` (`success` / `error`), `subreddit`, `error_type` |
| `reddit_tts.errors` | counter | `phase`, `error_type`, … |
| `process.cpu.utilization` | observable gauge (0–1) | `phase` — sampled every `resource_export_interval_sec` |
| `process.memory.usage` | observable gauge (bytes) | `phase` |
| `process.memory.utilization` | observable gauge (0–1) | `phase` |

CPU and memory use **OpenTelemetry observable gauges** (OTEL semantic conventions). The SDK reads `psutil` on each export tick (default **1s**) and pushes a time series to Grafana — not just phase peaks. Phase-level peaks still appear in stdout JSON (`resource_phase` events) for local grep/CI.

`submission_id` is kept on **traces and logs** only — not metric labels — to avoid Prometheus cardinality limits.

### Grafana dashboard ideas

- Time series: `process.cpu.utilization` by `phase` (1s resolution)
- Time series: `process.memory.usage` / `process.memory.utilization` during `video_render`
- Time series: p50/p95 `reddit_tts.phase.duration` by `phase`
- Stat: `sum(reddit_tts.video.uploads{status="success"})` over 24h
- Table: recent errors from `reddit_tts.errors` grouped by `error_type`
- Trace search: `service.name="reddit-tts-video"` filtered by `phase`

### Local dev

Keep `metrics.otel.enabled: false` (default). Stdout JSON metrics still work with zero cloud dependencies.

---

### Option 5 — Persist to SQLite / Postgres

**Effort:** medium  
**Cost:** free (local SQLite) or DB hosting

Append each `resource_phase` row to a `run_metrics` table after the job. Enables:

- Historical comparison (“did Whisper get slower after the last deploy?”)
- Simple CLI reports without Grafana

Aligns with Phase 4 in `docs/roadmap.md`. Schema sketch:

```sql
CREATE TABLE phase_metrics (
  run_id TEXT,
  phase TEXT,
  submission_id TEXT,
  duration_sec REAL,
  max_cpu_percent REAL,
  max_memory_mb REAL,
  max_memory_percent REAL,
  recorded_at TEXT
);
```

**Pros:** Full history under your control; no cloud vendor.  
**Cons:** You build queries and alerts yourself.

---

### Option 6 — CI artifacts only

**Effort:** low  
**Cost:** free  

In GitHub Actions, redirect stdout to a file and upload as an artifact. Review metrics per workflow run without Grafana.

---

## Recommended roadmap

| Step | Action |
|------|--------|
| **Now (v1)** | Structured JSON via `resource_metrics.py` ✅ |
| **Now (v1.1)** | OTLP export via `otel_export.py` ✅ |
| **Next** | Alloy config in `observability/alloy/` + Grafana dashboards |
| **Later** | SQLite history for regression tracking |

## Adding a new phase

1. Wrap the work in `main.py` (or the relevant module) with `metrics.track_phase("my_phase", ...)`.
2. Document the phase name in the table above.
3. If using Loki, no schema change — new `phase` label values appear automatically.
4. If using Prometheus push, add the label to your metric registry.

## Related docs

- `docs/roadmap.md` — Phase 4 metrics vision
- Grafana Cloud Free: https://grafana.com/products/cloud/
