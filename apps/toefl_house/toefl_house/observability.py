"""Operational visibility over native sources: health, workers, failed jobs.

Pure standard-library module; no Frappe import (same discipline as
scoring.py/policy.py). The desks project the raw rows; this module turns a
snapshot of those rows into named alert CONDITIONS.

Vocabulary is native-only, pinned at frappe 988e54f3c4c2:
- RQ Job.status: queued/started/finished/failed/deferred/scheduled/canceled
  (lowercase, from rq_job.json options).
- Scheduled Job Log.status: Scheduled/Complete/Failed.
- Scheduled Job Type.stopped: 1 means the job type is stopped.
- RQ Worker.status: free-text Data column with NO native vocabulary — this
  module never interprets it. Unknown worker states are surfaced as raw
  facts on the desk, never as alert conditions.

RECEIVER BOUNDARY (binding): conditions are generated, never delivered.
No receiver exists in this product: no email, no SMS, no webhook, no
dashboard push. Selecting a receiver (and the retention/escalation policy
around it) is an owner decision; delivery against a real receiver is a
real-environment proof that does not exist yet. Any code that delivers a
condition to a human must live outside this module and cite that decision.
"""
from datetime import datetime

# Native RQ Job statuses that mean "needs a human look", from rq_job.json.
FAILED_JOB_STATUSES = ("failed",)

# Native Scheduled Job Log statuses that mean "needs a human look".
FAILED_SCHEDULED_STATUSES = ("Failed",)


def summarize_snapshot(rows):
    """Count a desk-projected snapshot into plain facts. No thresholds.

    rows: mapping with optional keys error_logs, failed_jobs, workers,
    stopped_job_types, failed_scheduled_logs — each a list of projected
    row dicts (or, for failed_jobs, dicts with at least queue/job_name).
    Returns fact dicts; every value is a count or an echoed native value.
    """
    rows = rows or {}
    errors = list(rows.get("error_logs") or [])
    failed = list(rows.get("failed_jobs") or [])
    workers = list(rows.get("workers") or [])
    stopped = list(rows.get("stopped_job_types") or [])
    sched_failed = list(rows.get("failed_scheduled_logs") or [])
    queues = sorted({str(job.get("queue") or "") for job in failed if job.get("queue")})
    return {
        "unseen_error_logs": len(errors),
        "failed_jobs": len(failed),
        "failed_job_queues": queues,
        "workers_observed": len(workers),
        "worker_states": sorted({str(w.get("status") or "") for w in workers}),
        "stopped_scheduled_job_types": len(stopped),
        "failed_scheduled_logs": len(sched_failed),
    }


def evaluate_alert_conditions(summary, *, ping_ok):
    """Turn a snapshot summary into alert conditions. Pure and total.

    A condition is a fact with a name: {"condition", "detail", "observed"}.
    No severity is invented (ROLE-DESKS forbids it); ordering is by
    observation, not importance. An empty summary yields no conditions —
    silence is a signal only insofar as the snapshot exists, which the
    desk proves by showing its own query facts alongside.
    """
    summary = summary or {}
    conditions = []

    def add(condition, detail):
        conditions.append({"condition": condition, "detail": detail,
                           "observed": True})

    if not ping_ok:
        add("application_unreachable",
            "The application did not answer its own health ping.")
    if int(summary.get("unseen_error_logs") or 0) > 0:
        count = int(summary["unseen_error_logs"])
        add("unseen_error_logs",
            f"{count} unseen Error Log row(s). Open the native Error Log list.")
    if int(summary.get("failed_jobs") or 0) > 0:
        count = int(summary["failed_jobs"])
        queues = summary.get("failed_job_queues") or []
        where = f" on queue(s) {', '.join(queues)}" if queues else ""
        add("failed_background_jobs",
            f"{count} background job(s) in native failed status{where}. "
            "Open the native RQ Job list; tracebacks stay there, not on desks.")
    if int(summary.get("stopped_scheduled_job_types") or 0) > 0:
        count = int(summary["stopped_scheduled_job_types"])
        add("stopped_scheduled_job_types",
            f"{count} scheduled job type(s) are stopped (native stopped flag).")
    if int(summary.get("failed_scheduled_logs") or 0) > 0:
        count = int(summary["failed_scheduled_logs"])
        add("failed_scheduled_runs",
            f"{count} scheduled run(s) ended in native Failed status.")
    return conditions


def snapshot_timestamp(value=None):
    """Echo a snapshot time for display; never invents one."""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value or ""
