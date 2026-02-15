# SARA Monitoring Guide

Once you add more crawl setups and automate runs (cron, task scheduler, or a job queue), you need a **monitoring mechanism** to:

- See which crawls ran and whether they succeeded or failed
- Spot errors (fetch failures, parsing errors, stage crashes)
- Track volume over time (URLs discovered, pages fetched, records extracted)
- Get alerted when something breaks so you can fix it before the next run

This document outlines what to monitor and how, using what you already have plus optional upgrades.

---

## What to Monitor

| Concern | What to track | Where it appears today |
|--------|----------------|-------------------------|
| **Pipeline success** | Did discovery → retriever → parser all complete for a run? | `crawl_runner.py` exit code; completion messages in `logs/pipeline.log` |
| **Per-stage completion** | Discovery/retriever/parser “Completed” with schedule_id | `[discovery] Completed schedule_id=... \| URLs discovered: N` etc. in pipeline.log |
| **Errors** | Fetch failures, parse errors, unhandled exceptions | `"status": "error"` and ERROR-level lines in pipeline.log |
| **Throughput** | URLs discovered, pages fetched, records extracted per run | Same completion messages (parse the numbers) |
| **Queue health** | Are URLs piling up in RabbitMQ? | RabbitMQ CloudAMQP dashboard or API |
| **Run frequency** | Are scheduled crawls actually firing? | Scheduler logs; or infer from “Starting” lines in pipeline.log |

---

## Option 1: Use What You Have (Logs + Script)

Your pipeline already writes **structured JSON** to `logs/pipeline.log` with:

- `stage`, `schedule_id`, `project`, `site` in every message (when context is set)
- Completion lines: `[discovery] Completed ...`, `[retriever] Completed ...`, `[parser] Completed ...`
- Errors: `"status": "error"` and ERROR level

**Practical first step:** run the provided **log summary script** regularly (e.g. after each crawl or on a schedule):

```bash
python monitor_pipeline.py
python monitor_pipeline.py --last-runs 5
python monitor_pipeline.py --fail-if-recent-failure   # exit 1 if last run had a failure (for alerting)
```

It parses `pipeline.log`, summarizes recent runs and errors, and can exit non-zero for automation/alerting.

---

## Option 2: Log Aggregation + Search (ELK, Datadog, etc.)

If you scale to many projects/sites and many runs:

1. **Ship logs** from `logs/pipeline.log` to a central system (e.g. Filebeat → Elasticsearch, or Datadog agent).
2. Treat each line (or each JSON blob) as a document; your existing `crawl` object gives you `stage`, `schedule_id`, `project`, `site` for filtering.
3. Build dashboards for:
   - Count of “Completed” by stage/project/site/schedule_id
   - Count of `status: "error"` by project/site/stage
   - Time-series of “URLs discovered”, “Pages fetched”, “Records extracted” (by parsing the completion message text or adding dedicated metric events later)

No code change required for basic shipping; you can later add a dedicated “metric” log line per run (e.g. one JSON object with all three stage metrics) to make querying easier.

---

## Option 3: Metrics + Alerting (Prometheus, health checks)

For stricter SLAs and alerting:

1. **Expose simple metrics** (e.g. Prometheus text format or a small HTTP `/metrics` endpoint) from a sidecar or from the runner:
   - Last run timestamp per (project, site, schedule_id)
   - Last run success/failure per stage
   - Counts from last run (URLs, pages, records)
2. **Scrape** with Prometheus (or have your scheduler call a health URL).
3. **Alert** when:
   - Last run failed (any stage)
   - No run in the last N hours for a given schedule
   - Retriever success rate below a threshold (e.g. pages fetched vs discovered)

You can add a small `monitor_metrics.py` that reads `pipeline.log` (or a small JSON “run registry” file written by `crawl_runner.py`) and serves metrics.

---

## Option 4: RabbitMQ Visibility

- Use **CloudAMQP dashboard** (or RabbitMQ admin API) to watch queue lengths for `{site}_{project}_{schedule_id}_queue`.
- If queues grow without being consumed, retriever might be down or failing; if they’re always empty right after discovery, consumption is keeping up.

---

## Recommended Order

1. **Now:** Use `monitor_pipeline.py` (and optionally `--fail-if-recent-failure` in your automation) so you have a clear view of recent runs and a simple “last run failed” signal.
2. **As you add more sites/schedules:** Keep one log file per run or use log rotation; ensure pipeline.log is shipped or backed up so you don’t lose history.
3. **When you need dashboards or alerts:** Add log shipping (Option 2) and/or a small metrics endpoint (Option 3) and plug into your existing ops stack (PagerDuty, Slack, email, etc.).

---

## Files Added for Monitoring

- **`monitor_pipeline.py`** – Parses `logs/pipeline.log`, prints summary of recent runs and recent errors; supports `--last-runs N` and `--fail-if-recent-failure` for alerting.
