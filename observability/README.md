# Observability

This folder owns **how the pipeline measures and reports itself**. Application code imports from here; future exporters and dashboards build on the same structured events.

## Layout

| File | Purpose |
|------|---------|
| `resource_metrics.py` | v1 process-tree metrics via `psutil` — phase timing, peak CPU %, peak memory MB / % |
| `README.md` | This doc — current format, config, and upgrade paths |

Planned additions (not implemented yet):

| File | Purpose |
|------|---------|
| `grafana_export.py` | Optional push to Grafana Cloud Loki + Prometheus remote write |
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
```

Usage in `main.py`:

```python
from observability import create_metrics_tracker

metrics = create_metrics_tracker(config.get("metrics", {}).get("enabled", True))
with metrics.track_phase("video_render", submission_id=submission.id):
    videos = create_videos(submission)
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

### Option 4 — OpenTelemetry

**Effort:** medium–high  
**Cost:** Grafana Cloud OTLP endpoint or any OTEL backend

Replace or wrap `ResourceMonitor` with OTEL spans:

- One span per phase (`fetch_submissions`, `tts`, …)
- Attributes: `duration_sec`, `max_cpu_percent`, `max_memory_mb`, `max_memory_percent`
- Export via OTLP to Grafana Cloud or Jaeger

**Pros:** Standard vendor-neutral model; traces + metrics together.  
**Cons:** Heavier dependency; overkill until you need distributed tracing across services.

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
| **Next** | Alloy config in `observability/alloy/` + Grafana Cloud stack |
| **Later** | Optional `grafana_export.py` for CI push |
| **Future** | SQLite history + dashboards for regression tracking |

## Adding a new phase

1. Wrap the work in `main.py` (or the relevant module) with `metrics.track_phase("my_phase", ...)`.
2. Document the phase name in the table above.
3. If using Loki, no schema change — new `phase` label values appear automatically.
4. If using Prometheus push, add the label to your metric registry.

## Related docs

- `docs/roadmap.md` — Phase 4 metrics vision
- Grafana Cloud Free: https://grafana.com/products/cloud/
