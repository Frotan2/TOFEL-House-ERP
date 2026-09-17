"""Prove monitoring, alert delivery and backup retention against a real receiver.

Recovery proved the bytes come back and custody proved the keys come back. Neither
asked whether anyone would be told when something goes wrong, or whether the artifacts
recovery depends on are kept for long enough to be useful. This probe exercises those
three controls on a live site.

**Error logging.** An error is written through Frappe's own logging call and then read
back through its API, with a run-unique marker so the entry observed is provably the
one this probe caused rather than unrelated background noise. Which call wrote it is
recorded, because the native logging function and inserting an ``Error Log`` document
are different claims about the same store.

**Scheduled work.** The registry the scheduler actually reads is compared against the
scheduler events the installed code declares, obtained at runtime from
``frappe.get_hooks("scheduler_events")``. Declaring a hook and having it registered are
not the same thing, and the comparison is made against what this checkout declares
rather than against a list of hook names written down in advance.

**Alert delivery.** A real SMTP sink holds a real listening socket, and the alert is
sent through Frappe's own outgoing transport. Delivery counts only if the message that
arrived matches what was sent - subject, recipient and body. Then the sink is stopped,
its port is confirmed released, and the same alert is attempted again: the requirement
inverts, because the dangerous outcome is not a failed delivery but a delivery reported
as successful to nobody. That attempt must report failure and record it.

**Retention.** ``backup_limit`` is set below the number of backups taken, so pruning has
something to do. A limit that was never exceeded proves nothing, and a count that is
right while the oldest artifacts survived would be worse than no limit at all - so
which artifacts remained is checked, not just how many.

Not exercised here, and listed again in ``not_proven_by_this_probe``: automatic capture
of an unhandled exception raised inside a live HTTP request, and delivery to a real
external provider.
"""
import json
import os
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from bench_bootstrap import (  # noqa: E402
    MARIADB_CONTAINER, REDIS_CACHE_CONTAINER, REDIS_QUEUE_CONTAINER,
    Probe, build_bench, cleanup, clone_pinned_sources, install_apps, load_components,
    machine_identity, new_site, require_hosted_runner, start_services,
    wait_mariadb_healthy,
)
import monitoring_retention as monitoring  # noqa: E402
from smtp_sink import SmtpSink, parse_message_headers  # noqa: E402

SITE = "monitoring.localhost"
EVIDENCE = ROOT / ".foundation/monitoring-evidence"
#: The limit is deliberately lower than the number of backups taken, so pruning is
#: exercised rather than merely configured.
BACKUP_LIMIT = 2
BACKUPS_TAKEN = 4


def extract_json(text):
    """Pull the JSON value out of a ``bench execute`` reply.

    bench can emit warnings around the value it prints, and a probe that fails to
    parse that would report "nothing was logged" when in fact the read succeeded.
    """
    text = (text or "").strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    raise ValueError("No JSON value in the bench reply: " + text[:400])


def main() -> int:
    require_hosted_runner()
    components = load_components()
    lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-monitoring"
    lab.mkdir(mode=0o700, parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    root_password = secrets.token_urlsafe(32)
    db_password = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(32)
    marker = "foundation-monitor-" + uuid.uuid4().hex[:12]

    report = {
        "artifact_name": "monitoring-result.json",
        "scope": ("Monitoring, alert delivery and backup retention on a live site: a native error "
                  "log round trip, the scheduler registry compared against what the installed "
                  "code declares, an alert delivered to a real local SMTP receiver and then "
                  "refused with the receiver removed, and a backup retention limit that is "
                  "actually exercised; synthetic data only"),
        "role": "monitoring",
        "site": SITE,
        "marker": marker,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
        "status": "running",
        "checks": [],
        "mocks_or_simulations_used": False,
        "machine_identity": machine_identity(),
        "target_revisions": {},
        "verdicts": {},
    }
    probe = Probe(report, EVIDENCE, lab)
    for value in (root_password, db_password, admin_password):
        probe.mask(value)

    secret_file = lab / "db-password"
    secret_file.write_text(root_password)
    secret_file.chmod(0o600)
    bench_dir = lab / "bench"
    source_dir = lab / "sources"
    source_dir.mkdir()
    python_bin = Path(os.environ["RUNNER_TEMP"]) / "foundation-runner-probe/python/bin/python3"
    if not python_bin.exists():
        python_bin = Path(sys.executable)
    mail_result = EVIDENCE / "mail-result.json"
    bench = None
    sink = SmtpSink().start()
    report["alert_receiver"] = monitoring.receiver_summary(
        {"address": sink.address, "listening": True, "connections": 0, "messages": 0})

    def site_execute(label, function, kwargs=None, *, allow_failure=False, quiet=True):
        command = [str(bench), "--site", SITE, "execute", function]
        if kwargs is not None:
            command += ["--kwargs", json.dumps(kwargs)]
        return probe.run(label, command, cwd=bench_dir, timeout=600, quiet=quiet,
                         allow_failure=allow_failure)

    def list_doctype(label, doctype, fields, limit=200):
        raw = site_execute(label, "frappe.client.get_list",
                           {"doctype": doctype, "fields": fields, "limit_page_length": limit})
        rows = extract_json(raw)
        if not isinstance(rows, list):
            raise RuntimeError(label + " did not return a list: " + str(rows)[:200])
        return rows

    try:
        start_services(probe, components, secret_file)
        report["mariadb_health"] = wait_mariadb_healthy(probe)
        report["target_revisions"] = clone_pinned_sources(probe, components, source_dir,
                                                          ("frappe", "erpnext"))
        bench = build_bench(probe, components, lab, source_dir, bench_dir, python_bin)
        new_site(probe, bench, bench_dir, SITE, root_password, db_password, admin_password,
                 label="new-site-for-monitoring")
        install_apps(probe, bench, bench_dir, SITE, ("erpnext",))
        raw_apps = probe.run("list-apps-on-monitoring-site",
                             [str(bench), "--site", SITE, "list-apps"], cwd=bench_dir, quiet=True)
        report["installed_apps"] = sorted(line.strip() for line in raw_apps.splitlines()
                                          if line.strip())

        # --- 1. Error log round trip, attributed by a run-unique marker ---
        before = list_doctype("error-log-before", "Error Log", ["name", "creation"])
        report["error_log_entries_before"] = len(before)
        # The native logging call is attempted first. It is allowed to fail because
        # its signature differs between releases, and a signature mismatch must not be
        # mistaken for the error store being broken.
        site_execute("trigger-native-error-logging", "frappe.log_error",
                     {"title": "foundation-monitoring-probe", "message": marker},
                     allow_failure=True)
        native_call_failed = any(check["name"] == "trigger-native-error-logging"
                                 and check["status"] == "fail" for check in report["checks"])
        if native_call_failed:
            # The native logging call is not callable that way on this checkout, so the
            # entry is written through the doctype itself. Which path was used is part
            # of the evidence, because they are different claims about the same store.
            site_execute("write-error-log-document", "frappe.client.insert",
                         {"doc": {"doctype": "Error Log", "method": "foundation-monitoring-probe",
                                  "error": marker}})
        after = list_doctype("error-log-after", "Error Log", ["name", "creation", "error"])
        entries_before = [{"name": row["name"]} for row in before]
        entries_after = [{"name": row["name"], "error": str(row.get("error") or "")}
                         for row in after]
        error_verdict = monitoring.error_log_verdict(entries_before, entries_after, marker=marker)
        error_verdict["written_through"] = ("frappe.client.insert on Error Log"
                                            if native_call_failed else "frappe.log_error")
        report["verdicts"]["error_logging"] = error_verdict
        report["error_log_entries_after"] = len(after)
        if error_verdict["verdict"] != "ERROR LOGGED NATIVELY":
            raise RuntimeError("Error logging not proven: " + error_verdict["reason"])

        # --- 2. The scheduler registry against what this checkout declares ---
        declared_raw = site_execute("read-declared-scheduler-events", "frappe.get_hooks",
                                    {"hook": "scheduler_events"}, allow_failure=True)
        declared = []
        try:
            events = extract_json(declared_raw)
        except ValueError:
            events = {}

        def flatten(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for item in value.values():
                    yield from flatten(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    yield from flatten(item)

        declared = sorted({method for method in flatten(events) if "." in method})
        # Scheduled Job Type rows are created by the scheduler's own sync step, so a
        # site that has never run one can have an empty registry. Syncing it natively
        # first is what makes the comparison meaningful: without this the check would
        # be measuring whether a scheduler had happened to run, not whether declared
        # work is registered. Allowed to fail because the function's location differs
        # between releases, and the read below reports the truth either way.
        sync_raw = site_execute("sync-scheduled-job-type-registry",
                                "frappe.utils.scheduler.sync_jobs", None, allow_failure=True)
        report["scheduler_registry_sync"] = {
            "attempted": True,
            "succeeded": not any(check["name"] == "sync-scheduled-job-type-registry"
                                 and check["status"] == "fail" for check in report["checks"]),
            "reply_tail": (sync_raw or "")[-200:],
        }
        registry_names = list_doctype("scheduled-job-type-registry", "Scheduled Job Type",
                                      ["name"])
        # Discover which field this checkout stores the method in, rather than guessing
        # a field name and having the query fail.
        method_field = None
        if registry_names:
            sample_raw = site_execute("read-one-scheduled-job-type", "frappe.client.get",
                                      {"doctype": "Scheduled Job Type",
                                       "name": registry_names[0]["name"]})
            sample = extract_json(sample_raw)
            method_field = next((field for field in ("method", "scheduled_method", "hook")
                                 if field in sample), None)
        registry = []
        if registry_names and method_field:
            registry = list_doctype("scheduled-job-type-with-methods", "Scheduled Job Type",
                                    ["name", method_field])
            registry = [{"name": row["name"], "method": row.get(method_field)}
                        for row in registry]
        else:
            registry = [{"name": row["name"], "method": row["name"]} for row in registry_names]
        # Only hooks that name a module path can be matched against the registry.
        required = [method for method in declared if method.count(".") >= 1]
        registry_verdict = monitoring.scheduler_registry_verdict(registry, required_hooks=required)
        registry_verdict["method_field_discovered"] = method_field
        registry_verdict["declared_scheduler_events"] = len(declared)
        registry_verdict["declared_sample"] = declared[:10]
        report["verdicts"]["scheduler_registry"] = registry_verdict
        if registry_verdict["verdict"] != "SCHEDULED WORK REGISTERED":
            raise RuntimeError("Scheduler registry not proven: " + registry_verdict["reason"])

        # --- 3. Alert delivery to a real receiver ---
        mail_env = {"FOUNDATION_SINK_HOST": "127.0.0.1", "FOUNDATION_SINK_PORT": str(sink.port),
                    "FOUNDATION_ALERT_MARKER": marker,
                    "FOUNDATION_MONITORING_MAIL_RESULT": str(mail_result)}
        probe.run("send-alert-to-the-real-receiver",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_monitoring_mail.py"), "send", SITE],
                  cwd=bench_dir / "sites", timeout=300, env=mail_env)
        sent = json.loads(mail_result.read_text())
        report["alert_send_attempt"] = {key: sent[key] for key in
                                        ("transport_class", "transport_used", "transport_accepts",
                                         "attempts", "delivered", "error")
                                        if key in sent}
        received = [parse_message_headers(message["raw"]) for message in sink.messages]
        delivery = monitoring.alert_delivery_verdict(
            sent["delivered"], received,
            expected_subject=f"foundation-monitoring-alert {marker}",
            expected_recipients=["oncall@monitoring.foundation.internal"],
            expected_body_fragment=marker)
        report["verdicts"]["alert_delivery"] = delivery
        report["alert_receiver"] = monitoring.receiver_summary(
            {"address": sink.address, "listening": True, "connections": sink.connections,
             "messages": len(sink.messages)})
        if delivery["verdict"] != "ALERT DELIVERED TO A REAL RECEIVER":
            raise RuntimeError("Alert delivery not proven: " + delivery["reason"])

        # --- 4. The same alert with the receiver removed must fail loudly ---
        sink.stop()
        released = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            import socket as socket_module
            try:
                socket_module.create_connection(("127.0.0.1", sink.port), timeout=2).close()
            except OSError:
                released = True
                break
            time.sleep(0.3)
        if not released:
            raise RuntimeError("The receiver kept its port after being stopped, so removal "
                               "cannot be demonstrated")
        report["receiver_removed"] = {"stopped": True, "port_released": True,
                                      "port": sink.port, "connections_before_stop":
                                          report["alert_receiver"]["connections_accepted"]}
        fail_env = dict(mail_env, FOUNDATION_EXPECT_DELIVERY_FAILURE="true")
        probe.run("send-alert-with-the-receiver-removed",
                  [str(bench_dir / "env/bin/python"),
                   str(ROOT / "tools/foundation/runtime_monitoring_mail.py"), "send", SITE],
                  cwd=bench_dir / "sites", timeout=300, env=fail_env)
        refused = json.loads(mail_result.read_text())
        report["alert_refusal_attempt"] = {key: refused[key] for key in
                                           ("delivered", "failure_reported", "error", "status")
                                           if key in refused}
        fail_closed = monitoring.fail_closed_verdict(
            receiver_present=False,
            delivery_reported_success=refused["delivered"],
            error_recorded=bool(refused["failure_reported"] and refused.get("error")),
            detail={"error": refused.get("error"), "transport": refused.get("transport_used")})
        report["verdicts"]["alert_fail_closed"] = fail_closed
        if fail_closed["verdict"] != "FAILS CLOSED":
            raise RuntimeError("Alert delivery does not fail closed: " + fail_closed["reason"])

        # --- 5. Backup retention, with the limit below the number taken ---
        site_config = bench_dir / "sites" / SITE / "site_config.json"

        def configured_limit():
            return extract_json(site_config.read_text()).get("backup_limit")

        # bench accepts the site either as a global --site option or as its own flag,
        # depending on release. Try the form the rest of this repository uses, confirm
        # the value actually landed in site_config.json, and only then fall back -
        # because a retention limit that was never written would make the pruning
        # observation meaningless rather than merely wrong.
        probe.run("configure-backup-retention-limit",
                  [str(bench), "--site", SITE, "set-config", "backup_limit", str(BACKUP_LIMIT)],
                  cwd=bench_dir, allow_failure=True)
        if configured_limit() != BACKUP_LIMIT:
            probe.run("configure-backup-retention-limit-alternate-form",
                      [str(bench), "set-config", "--site", SITE, "backup_limit",
                       str(BACKUP_LIMIT)], cwd=bench_dir, allow_failure=True)
        report["configured_backup_limit"] = configured_limit()
        report["retention_limit_written_by"] = next(
            (check["name"] for check in reversed(report["checks"])
             if check["name"].startswith("configure-backup-retention-limit")
             and check["status"] == "pass"), None)
        if report["configured_backup_limit"] != BACKUP_LIMIT:
            raise RuntimeError("The retention limit was not written to site config by either "
                               "invocation form; site_config holds "
                               + json.dumps(report["configured_backup_limit"]))
        backups = bench_dir / "sites" / SITE / "private" / "backups"
        taken_names = []
        for index in range(BACKUPS_TAKEN):
            probe.run(f"take-backup-{index + 1}-of-{BACKUPS_TAKEN}",
                      [str(bench), "--site", SITE, "backup"], cwd=bench_dir, timeout=1200)
            # Two backups inside one second would share a name prefix, and the ordering
            # the retention verdict depends on would become meaningless.
            time.sleep(2)
            current = monitoring.ordered_artifacts(backups, monitoring.database_artifact_patterns())
            if current:
                newest = current[-1]["name"]
                if newest not in taken_names:
                    taken_names.append(newest)
        remaining = monitoring.ordered_artifacts(backups, monitoring.database_artifact_patterns())
        report["backup_artifacts"] = {
            "limit_configured": BACKUP_LIMIT, "backups_requested": BACKUPS_TAKEN,
            "distinct_artifacts_observed": taken_names,
            "remaining": [entry["name"] for entry in remaining],
            "remaining_count": len(remaining),
        }
        retention = monitoring.retention_verdict(
            BACKUP_LIMIT, max(BACKUPS_TAKEN, len(taken_names)), len(remaining),
            kept_names=[entry["name"] for entry in remaining], taken_names=taken_names)
        report["verdicts"]["backup_retention"] = retention
        if retention["verdict"] != "RETENTION ENFORCED":
            raise RuntimeError("Backup retention not proven: " + retention["reason"])

        report["not_proven_by_this_probe"] = [
            "Automatic capture of an unhandled exception raised inside a live HTTP request: the "
            "error store is exercised through Frappe's own logging path and read back through its "
            "API, but no 500 was produced from a running web process to observe whether the "
            "request handler logs it on its own",
            "Delivery to a real external provider: the receiver is a local SMTP sink holding a "
            "real socket. It proves Frappe's outgoing transport delivers and that a lost alert is "
            "reported rather than swallowed; it does not prove delivery to a provider with its own "
            "authentication, rate limits and bounce handling",
            "An alerting rule that decides WHEN to page someone: no threshold, escalation policy, "
            "deduplication or on-call rotation is exercised. What is proven is the delivery path "
            "and its failure behaviour, not the decision to alert",
            "Scheduler execution over time: the registry the scheduler reads is compared against "
            "the events this checkout declares, but no scheduled job was observed firing on its "
            "own cadence, which would need the scheduler and a worker running across a tick "
            "boundary",
            "Retention of the file archives alongside the database dumps: the limit is exercised "
            "against database artifacts",
            "Retention across a long horizon or against off-site copies: backups are taken minutes "
            "apart on one disposable runner",
            "Log shipping, metrics export, or tracing to an external observability backend",
            "Owner-defined alerting thresholds or availability objectives: none were supplied, so "
            "none were invented",
            "Any production workload: every record, alert and credential here is synthetic and "
            "generated for this run",
        ]
        report["status"] = "pass"
        print("Error logging, the scheduler registry, alert delivery to a real receiver with "
              "fail-closed behaviour, and backup retention all observed")
    except Exception as exc:
        report["status"] = "fail"
        report["failure"] = probe.redact(str(exc))[-4000:]
        print(report["failure"], file=sys.stderr)
    finally:
        try:
            sink.stop()
        except Exception:  # noqa: BLE001 - teardown must not mask the real result
            pass
        secret_file.unlink(missing_ok=True)
        (EVIDENCE / "monitoring-result.json").write_text(
            probe.redact(json.dumps(report, indent=2)) + "\n")
        cleanup((MARIADB_CONTAINER, REDIS_QUEUE_CONTAINER, REDIS_CACHE_CONTAINER))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
