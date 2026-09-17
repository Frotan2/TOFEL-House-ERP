"""Contract for monitoring, alert delivery and retention (P5).

These controls fail in production by being silent, so almost every test here is about
a verdict refusing to pass when the observation is weak rather than about the happy
path:

* an alert reported sent but received by nobody must not read as delivered;
* a delivery that reported success with no receiver listening and no error recorded is
  the dangerous case, and the fail-closed verdict passes only when that did NOT happen;
* a retention limit that was never exercised proves nothing, and one that kept the
  oldest artifacts while satisfying the count is worse than no limit at all;
* an error log entry that does not carry the marker cannot be attributed to the error
  that was triggered;
* the SMTP sink is a real socket, and stopping it really releases the port - without
  that, "receiver removed" could not be demonstrated at all.

Boundary with the existing coverage: nothing here upgrades a release gate, and the
PASS comes from the hosted operational-boundary run, never from this file.
"""
import smtplib
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

import monitoring_retention as monitoring  # noqa: E402
from smtp_sink import SmtpSink, parse_message_headers  # noqa: E402


class ErrorLogVerdict(unittest.TestCase):
    def entries(self, names, marker=None):
        return [{"name": name, "error": f"traceback for {name} {marker or ''}"}
                for name in names]

    def test_a_new_entry_carrying_the_marker_is_logged(self):
        verdict = monitoring.error_log_verdict(self.entries(["E-1"]),
                                               self.entries(["E-1", "E-2"], "MARK"),
                                               marker="MARK")
        self.assertEqual(verdict["verdict"], "ERROR LOGGED NATIVELY")
        self.assertTrue(verdict["logged"])
        self.assertEqual(verdict["new_entries"], ["E-2"])

    def test_a_new_entry_without_the_marker_is_not_attributable(self):
        verdict = monitoring.error_log_verdict(self.entries(["E-1"]),
                                               self.entries(["E-1", "E-2"]),
                                               marker="MARK")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("cannot be attributed", verdict["reason"])
        self.assertEqual(verdict["new_entries"], ["E-2"])

    def test_no_new_entry_is_not_proven(self):
        verdict = monitoring.error_log_verdict(self.entries(["E-1"]), self.entries(["E-1"]),
                                               marker="MARK")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("no new Error Log entry", verdict["reason"])

    def test_an_empty_log_after_the_error_is_not_proven(self):
        self.assertEqual(monitoring.error_log_verdict([], [])["verdict"], "NOT PROVEN")

    def test_without_a_marker_any_new_entry_counts(self):
        verdict = monitoring.error_log_verdict(self.entries(["E-1"]), self.entries(["E-1", "E-2"]))
        self.assertEqual(verdict["verdict"], "ERROR LOGGED NATIVELY")


class AlertDeliveryVerdict(unittest.TestCase):
    def message(self, subject="Alert", to="oncall@foundation.internal", body="body"):
        return {"subject": subject, "to": to, "body": body}

    def test_a_matching_message_at_a_real_receiver_is_delivery(self):
        verdict = monitoring.alert_delivery_verdict(
            True, [self.message()], expected_subject="Alert",
            expected_recipients=["oncall@foundation.internal"])
        self.assertEqual(verdict["verdict"], "ALERT DELIVERED TO A REAL RECEIVER")
        self.assertTrue(verdict["delivered"])

    def test_reported_sent_but_received_by_nobody_is_the_silent_failure(self):
        verdict = monitoring.alert_delivery_verdict(True, [], expected_subject="Alert")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertFalse(verdict["delivered"])
        self.assertIn("silent-failure case", verdict["reason"])

    def test_nothing_sent_is_not_delivery(self):
        verdict = monitoring.alert_delivery_verdict(False, [self.message()])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("no alert was sent", verdict["reason"])

    def test_a_message_with_the_wrong_subject_does_not_count(self):
        verdict = monitoring.alert_delivery_verdict(True, [self.message(subject="Other")],
                                                    expected_subject="Alert")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(verdict["messages_matching_the_alert"], 0)

    def test_a_message_to_the_wrong_recipient_does_not_count(self):
        verdict = monitoring.alert_delivery_verdict(
            True, [self.message(to="someone-else@example.com")],
            expected_recipients=["oncall@foundation.internal"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("recipients", verdict["reason"])

    def test_recipient_matching_ignores_case_and_extra_recipients(self):
        verdict = monitoring.alert_delivery_verdict(
            True, [self.message(to="OnCall@Foundation.Internal, second@example.com")],
            expected_recipients=["oncall@foundation.internal"])
        self.assertTrue(verdict["delivered"])

    def test_a_body_fragment_can_be_required(self):
        self.assertFalse(monitoring.alert_delivery_verdict(
            True, [self.message(body="unrelated")],
            expected_body_fragment="scheduler")["delivered"])
        self.assertTrue(monitoring.alert_delivery_verdict(
            True, [self.message(body="the scheduler stopped")],
            expected_body_fragment="scheduler")["delivered"])


class FailClosedVerdict(unittest.TestCase):
    def test_a_recorded_failure_with_no_receiver_fails_closed(self):
        verdict = monitoring.fail_closed_verdict(False, False, True)
        self.assertEqual(verdict["verdict"], "FAILS CLOSED")
        self.assertTrue(verdict["fails_closed"])

    def test_a_silent_success_with_no_receiver_is_the_dangerous_case(self):
        verdict = monitoring.fail_closed_verdict(False, True, False)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertTrue(verdict["silently_reported_success"])
        self.assertIn("lost silently", verdict["reason"])

    def test_success_reported_with_an_error_recorded_is_not_silent(self):
        verdict = monitoring.fail_closed_verdict(False, True, True)
        self.assertFalse(verdict["silently_reported_success"])
        self.assertEqual(verdict["verdict"], "FAILS CLOSED")

    def test_a_failure_with_nothing_recorded_is_not_enough(self):
        verdict = monitoring.fail_closed_verdict(False, False, False)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("nothing to alert on", verdict["reason"])

    def test_an_observation_made_while_the_receiver_existed_proves_nothing(self):
        verdict = monitoring.fail_closed_verdict(True, False, True)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("receiver was still present", verdict["reason"])


class RetentionVerdict(unittest.TestCase):
    def names(self, count):
        return [f"2026091{i}_00000{index}-s-database.sql.gz" for index, i in
                enumerate(range(count))]

    def test_pruning_to_the_limit_keeps_the_newest(self):
        taken = self.names(5)
        verdict = monitoring.retention_verdict(3, 5, 3, kept_names=taken[-3:],
                                               taken_names=taken)
        self.assertEqual(verdict["verdict"], "RETENTION ENFORCED")
        self.assertTrue(verdict["pruning_exercised"])
        self.assertTrue(verdict["kept_the_newest"])
        self.assertEqual(verdict["pruned_count"], 2)

    def test_a_limit_never_exercised_proves_nothing(self):
        verdict = monitoring.retention_verdict(5, 2, 2)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertFalse(verdict["pruning_exercised"])
        self.assertIn("never exercised", verdict["reason"])

    def test_retaining_more_than_the_limit_fails(self):
        verdict = monitoring.retention_verdict(3, 6, 5)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertFalse(verdict["within_limit"])

    def test_pruning_everything_is_not_enforcement(self):
        verdict = monitoring.retention_verdict(3, 5, 0)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")

    def test_keeping_the_oldest_while_satisfying_the_count_is_caught(self):
        taken = self.names(5)
        verdict = monitoring.retention_verdict(3, 5, 3, kept_names=taken[:3],
                                               taken_names=taken)
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertFalse(verdict["kept_the_newest"])
        self.assertIn("wrong artifacts survived", verdict["reason"])

    def test_a_count_only_observation_is_still_enforcement(self):
        # Without names the newest-kept check is not attempted, and that is recorded.
        verdict = monitoring.retention_verdict(3, 5, 3)
        self.assertEqual(verdict["verdict"], "RETENTION ENFORCED")
        self.assertIsNone(verdict["kept_the_newest"])


class SchedulerRegistryVerdict(unittest.TestCase):
    def entries(self, methods):
        return [{"name": method.split(".")[-1], "method": method} for method in methods]

    def test_a_populated_registry_with_the_required_hooks_passes(self):
        methods = ["frappe.desk.notifications.clear_notifications",
                   "frappe.email.doctype.email_account.pull",
                   "erpnext.accounts.reconciliation.xxx"]
        verdict = monitoring.scheduler_registry_verdict(
            self.entries(methods), required_hooks=["frappe.email"])
        self.assertEqual(verdict["verdict"], "SCHEDULED WORK REGISTERED")
        self.assertEqual(verdict["registry_entries"], 3)
        self.assertEqual(verdict["missing_required_hooks"], [])

    def test_an_empty_registry_is_not_proven(self):
        verdict = monitoring.scheduler_registry_verdict([], required_hooks=["frappe.email"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertIn("registry is empty", verdict["reason"])

    def test_a_missing_required_hook_is_reported(self):
        verdict = monitoring.scheduler_registry_verdict(
            self.entries(["frappe.desk.notifications.clear_notifications"]),
            required_hooks=["frappe.email.doctype.email_account.pull"])
        self.assertEqual(verdict["verdict"], "NOT PROVEN")
        self.assertEqual(len(verdict["missing_required_hooks"]), 1)

    def test_a_registry_with_no_required_hooks_passes_on_population_alone(self):
        verdict = monitoring.scheduler_registry_verdict(
            self.entries(["frappe.desk.notifications.clear_notifications"]))
        self.assertEqual(verdict["verdict"], "SCHEDULED WORK REGISTERED")


class SmtpSinkBehaviour(unittest.TestCase):
    """The receiver is a real socket, and removing it is really observable."""

    def send(self, port, subject="heartbeat"):
        with smtplib.SMTP("127.0.0.1", port, timeout=20) as client:
            client.sendmail("alerts@foundation.internal", ["oncall@foundation.internal"],
                            f"Subject: {subject}\r\nTo: oncall@foundation.internal\r\n\r\nbody")

    def test_a_real_client_delivers_and_the_message_is_readable(self):
        sink = SmtpSink().start()
        try:
            self.send(sink.port)
            deadline = time.monotonic() + 10
            while not sink.messages and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertEqual(len(sink.messages), 1)
            parsed = parse_message_headers(sink.messages[0]["raw"])
            self.assertEqual(parsed["subject"], "heartbeat")
            self.assertEqual(parsed["to"], "oncall@foundation.internal")
            verdict = monitoring.alert_delivery_verdict(
                True, [parsed], expected_subject="heartbeat",
                expected_recipients=["oncall@foundation.internal"])
            self.assertEqual(verdict["verdict"], "ALERT DELIVERED TO A REAL RECEIVER")
        finally:
            sink.stop()

    def test_stopping_really_releases_the_port(self):
        sink = SmtpSink().start()
        port = sink.port
        self.send(port)
        sink.stop()
        deadline = time.monotonic() + 5
        released = False
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=2).close()
            except OSError:
                released = True
                break
            time.sleep(0.2)
        self.assertTrue(released, "the sink kept the port after stop(), so removal is not "
                                  "demonstrable")
        self.assertTrue(sink.stopped)

    def test_delivery_fails_once_the_receiver_is_gone(self):
        sink = SmtpSink().start()
        port = sink.port
        self.send(port)
        sink.stop()
        time.sleep(0.5)
        with self.assertRaises(OSError):
            self.send(port)

    def test_dot_stuffing_is_reversed_so_the_body_survives(self):
        sink = SmtpSink().start()
        try:
            with smtplib.SMTP("127.0.0.1", sink.port, timeout=20) as client:
                client.sendmail("a@b.c", ["d@e.f"],
                                "Subject: dots\r\n\r\nfirst\r\n.leading dot\r\nlast\r\n")
            deadline = time.monotonic() + 10
            while not sink.messages and time.monotonic() < deadline:
                time.sleep(0.1)
            body = parse_message_headers(sink.messages[0]["raw"])["body"]
            self.assertIn("\r\n.leading dot\r\n", body)
            self.assertNotIn("\r\n..leading", body)
        finally:
            sink.stop()

    def test_concurrent_deliveries_are_all_held(self):
        sink = SmtpSink().start()
        try:
            threads = [threading.Thread(target=self.send, args=(sink.port,), daemon=True)
                       for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            deadline = time.monotonic() + 10
            while len(sink.messages) < 4 and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertEqual(len(sink.messages), 4)
            self.assertGreaterEqual(sink.connections, 4)
        finally:
            sink.stop()

    def test_the_receiver_summary_reports_what_it_did(self):
        sink = SmtpSink().start()
        self.send(sink.port)
        time.sleep(0.4)
        state = monitoring.receiver_summary({"address": sink.address, "listening": True,
                                             "connections": sink.connections,
                                             "messages": len(sink.messages)})
        sink.stop()
        self.assertTrue(state["is_a_real_socket"])
        self.assertEqual(state["messages_held"], 1)
        self.assertIn("Python 3.12 removed smtpd", state["note"])

    def test_an_unbound_port_is_reported_as_nothing_received(self):
        sink = SmtpSink()
        sink.stop()
        verdict = monitoring.alert_delivery_verdict(True, [], expected_subject="x")
        self.assertEqual(verdict["verdict"], "NOT PROVEN")


class ArtifactOrdering(unittest.TestCase):
    """Retention depends on knowing which artifacts are newest, and on the -enc suffix."""

    def make(self, directory, names):
        import os
        for index, name in enumerate(names):
            path = directory / name
            path.write_bytes(b"payload" * (index + 1))
            # Force the ordering to come from mtime rather than from the filename.
            os.utime(path, (1000 + index * 100, 1000 + index * 100))
        return names

    def test_orders_by_mtime_oldest_first(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            names = self.make(directory, ["20260917_080000-s-database.sql.gz",
                                          "20260917_080100-s-database.sql.gz",
                                          "20260917_080200-s-database.sql.gz"])
            found = monitoring.ordered_artifacts(directory, monitoring.database_artifact_patterns())
            self.assertEqual([entry["name"] for entry in found], names)
            self.assertEqual([entry["mtime"] for entry in found], [1000.0, 1100.0, 1200.0])
            self.assertEqual(found[0]["bytes"], 7)

    def test_the_enc_suffix_is_matched(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory, ["20260917_080000-s-database-enc.sql.gz"])
            found = monitoring.ordered_artifacts(directory, monitoring.database_artifact_patterns())
            self.assertEqual(len(found), 1)
            self.assertIn("-enc", found[0]["name"])

    def test_other_artifact_kinds_are_excluded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory, ["20260917_080000-s-database.sql.gz",
                                  "20260917_080000-s-files.tar",
                                  "20260917_080000-s-private-files.tar",
                                  "20260917_080000-s-site_config_backup.json"])
            found = monitoring.ordered_artifacts(directory, monitoring.database_artifact_patterns())
            self.assertEqual([entry["name"] for entry in found],
                             ["20260917_080000-s-database.sql.gz"])

    def test_duplicates_across_patterns_are_counted_once(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make(directory, ["20260917_080000-s-database.sql.gz"])
            found = monitoring.ordered_artifacts(
                directory, ["*-database*.sql.gz", "*-database*.sql", "*database*"])
            self.assertEqual(len(found), 1)

    def test_an_empty_directory_yields_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(monitoring.ordered_artifacts(
                Path(tmp), monitoring.database_artifact_patterns()), [])


class BenchReplyParsing(unittest.TestCase):
    """``bench execute`` can wrap its reply, and a failed parse would read as an empty log."""

    def setUp(self):
        import importlib.util
        path = ROOT / "tools" / "foundation" / "runtime_monitoring.py"
        spec = importlib.util.spec_from_file_location("monitoring_probe", path)
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)

    def test_a_clean_list_reply_parses(self):
        self.assertEqual(self.probe.extract_json('[{"name": "abc"}]'), [{"name": "abc"}])

    def test_a_reply_wrapped_in_warnings_still_parses(self):
        self.assertEqual(
            self.probe.extract_json('DeprecationWarning: x\n[{"name": "abc"}]\nDone.'),
            [{"name": "abc"}])

    def test_a_nested_hook_structure_parses(self):
        parsed = self.probe.extract_json(
            '{"daily": ["a.b"], "cron": {"0 * * * *": ["c.d"]}}')
        self.assertEqual(parsed["daily"], ["a.b"])

    def test_a_reply_with_no_value_raises_instead_of_reading_as_empty(self):
        with self.assertRaises(ValueError):
            self.probe.extract_json("no json here")
        with self.assertRaises(ValueError):
            self.probe.extract_json("")


class HeaderParsing(unittest.TestCase):
    def test_headers_and_body_are_separated(self):
        parsed = parse_message_headers(
            "Subject: test\r\nTo: a@b.c\r\nFrom: c@d.e\r\n\r\nthe body\r\n")
        self.assertEqual(parsed["subject"], "test")
        self.assertEqual(parsed["to"], "a@b.c")
        self.assertEqual(parsed["from"], "c@d.e")
        self.assertEqual(parsed["body"], "the body\r\n")

    def test_folded_headers_are_joined(self):
        parsed = parse_message_headers("Subject: a very long\r\n folded subject\r\n\r\nbody")
        self.assertEqual(parsed["subject"], "a very long folded subject")

    def test_lf_only_messages_are_parsed_too(self):
        parsed = parse_message_headers("Subject: lf\nTo: a@b.c\n\nbody\n")
        self.assertEqual(parsed["subject"], "lf")
        self.assertEqual(parsed["body"], "body\n")

    def test_empty_input_is_not_a_message(self):
        parsed = parse_message_headers("")
        self.assertEqual(parsed["headers"], {})
        self.assertIsNone(parsed["subject"])


if __name__ == "__main__":
    unittest.main()
