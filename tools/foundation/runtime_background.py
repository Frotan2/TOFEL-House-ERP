"""Exercise real site Redis cache and an RQ worker with an upstream read-only job."""
import json
import os
from pathlib import Path
import sys
import time


def main():
    import frappe
    if os.environ.get("GITHUB_ACTIONS") != "true" or sys.argv[1] != "foundation.localhost":
        raise SystemExit("Requires isolated Actions test site")
    report = {"scope": "Actual Redis cache and RQ processing; not all scheduler/realtime behavior", "status": "running"}
    frappe.init(site=sys.argv[1], sites_path=str(Path.cwd() / "sites"))
    try:
        frappe.connect()
        frappe.cache.set_value("foundation-cache-proof", "synthetic-value", expires_in_sec=60)
        assert frappe.cache.get_value("foundation-cache-proof") == "synthetic-value"
        frappe.cache.delete_value("foundation-cache-proof")
        report["cache_round_trip"] = True
        started = time.monotonic()
        job = frappe.enqueue("frappe.utils.now", queue="short", job_id="foundation-background-proof", enqueue_after_commit=False)
        for attempt in range(60):
            status = job.get_status(refresh=True)
            status = getattr(status, "value", str(status))
            if status in ("finished", "failed", "stopped", "canceled"):
                break
            time.sleep(1)
        assert status == "finished", "Job did not finish: " + status
        value = job.return_value()
        assert isinstance(value, str) and len(value) >= 10
        report.update(job_status=status, result_type=type(value).__name__, job_seconds=round(time.monotonic() - started, 3), status="pass")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = {"exception": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        Path(os.environ["FOUNDATION_BACKGROUND_REPORT"]).write_text(json.dumps(report, indent=2) + "\n")
        frappe.destroy()


if __name__ == "__main__":
    main()
