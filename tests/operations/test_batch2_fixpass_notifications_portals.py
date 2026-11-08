"""ERP Batch 2 — narrow fix pass (deep-review findings C-10/C-12/U-15/D6).

Regression tests for the fix pass. Every test in this file was written
to FAIL on the unfixed tree first (see the fix-pass report for the
per-test unfixed failure) and to pass only after the narrow fix.

- C-10 crash double-send window: a mid-batch crash must leave
  already-succeeded recipients durably recorded and un-resent on retry.
- C-10 escalation-recipient silent drop: a failed escalation-recipient
  read in _load_notification must raise, not silently drop recipients.
- C-10 create_notification swallowing recipient persistence: a failed
  recipient child-row write must raise, not report success.
- C-10 generate_system_alerts fail-open: an observability error must
  raise, not silently yield no system alerts.
- C-10 unparseable-timestamp stall: an unevaluable deliver_at /
  next_retry_at must persist a diagnostic and must not be counted as
  an attempt by the batch retry.
- C-12 _governing_guardian_terms fail-open: a policy-read failure must
  raise, not resolve to {} and silently drop evidence/window checks.
- D6 consent/revocation: _get_consent must select the Active row (not
  merely the newest), revoke_consent must revoke every non-Revoked row,
  and CONSENT_ROWS_MAX must bound the read with a raise past it.

Synthetic data only. Runs against the stub frappe harness from
tests/operations/test_notifications_portals.py.
"""
import json
import sys
import types
import unittest

from tests.operations.test_notifications_portals import BaseHarness


def _decode_outcome(last_failure):
    """Independent decoder for the persisted per-recipient outcome record."""
    if not last_failure:
        return ("", None)
    text = str(last_failure).strip()
    if not text.startswith("{"):
        return (text, None)
    try:
        payload = json.loads(text)
    except ValueError:
        return (text, None)
    if not isinstance(payload, dict):
        return (text, None)
    results = payload.get("results")
    if not isinstance(results, list):
        return (payload.get("detail") or text, None)
    return (payload.get("detail") or text, results)


def _enable(mod, event_type, recipients, channel="Dashboard", **extra):
    rule = {
        "event_type": event_type, "enabled": True,
        "recipients": list(recipients), "severity": "warning",
        "channel": channel, "max_retries": 2, "retry_delay_minutes": 1,
    }
    rule.update(extra)
    mod.set_dispatch_rule(rule)


class _CrashAfterFirstProvider:
    """Succeeds for the first recipient, then dies mid-batch.

    The raise is a BaseException (KeyboardInterrupt): _send_to_recipients
    catches Exception per recipient, so only a real crash/interrupt
    escapes the send loop — exactly the window the per-recipient
    incremental persist must close.
    """
    name = "crash-after-first-test-provider"

    def __init__(self):
        self.calls = []

    def send(self, notification):
        self.calls.append(notification.get("recipient"))
        if len(self.calls) == 1:
            return True
        raise KeyboardInterrupt("synthetic crash mid-batch")


class _RecordingProvider:
    """Records every recipient; succeeds/fails per the given mapping."""

    name = "recording-test-provider"

    def __init__(self, ok_for):
        self.ok_for = set(ok_for)
        self.calls = []

    def send(self, notification):
        self.calls.append(notification.get("recipient"))
        return notification.get("recipient") in self.ok_for


class CrashDoubleSendTests(BaseHarness):
    def test_mid_batch_crash_leaves_first_recipient_recorded_and_unresent(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com", "c@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        # Drop the in-memory fallback BEFORE attempting, so the attempt
        # goes through the durable doc path (frappe.get_doc + save, the
        # production path): only the doc path proves the incremental
        # persist is durable across a crash.
        self.notifications_mod._memory_notifications.pop(n["name"], None)
        crashing = _CrashAfterFirstProvider()
        with self.assertRaises(KeyboardInterrupt):
            self.notifications_mod.attempt_delivery(
                n["name"], provider_override=crashing)
        self.assertEqual(crashing.calls,
                         ["a@example.com", "b@example.com"])
        # The crash happened after a@example.com was sent: that success
        # must already be durable, not lost with the crashed attempt.
        doc = self.frappe.get_doc("TH Notification", n["name"])
        _, results = _decode_outcome(doc.get("last_failure"))
        self.assertIsNotNone(results, "no durable per-recipient record "
                               "survived the mid-batch crash")
        self.assertEqual({r["recipient"]: r["delivered"] for r in results},
                         {"a@example.com": True})
        # Retry with a provider that FAILS for a but succeeds for the
        # rest: any resend to a fails the retry outright.
        second = _RecordingProvider(
            ok_for={"b@example.com", "c@example.com"})
        status, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=second)
        self.assertEqual(status, "delivered")
        self.assertEqual(second.calls, ["b@example.com", "c@example.com"],
                         "retry resent to a@example.com, who already succeeded")


class EscalationLoadFailureTests(BaseHarness):
    def test_escalation_recipient_read_failure_raises_in_load(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"],
                escalation_recipients=["boss@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        self.notifications_mod._memory_notifications.pop(n["name"], None)
        # Patch the stub doc class (not the instance: _FakeDoc.__setattr__
        # stores attribute assignment as a dict key, so an instance
        # attribute never shadows the class .get method).
        from tests.operations.test_notifications_portals import _FakeDoc
        orig_get = _FakeDoc.get

        def raising_get(self, k, d=None):
            if k == "escalation_recipients":
                raise RuntimeError("synthetic escalation read outage")
            return orig_get(self, k, d)

        _FakeDoc.get = raising_get
        self.addCleanup(setattr, _FakeDoc, "get", orig_get)
        with self.assertRaises(RuntimeError):
            self.notifications_mod._load_notification(n["name"])
        # The failure must surface from delivery too, never silently
        # deliver without the escalation recipients.
        with self.assertRaises(RuntimeError):
            self.notifications_mod.attempt_delivery(n["name"])


class RecipientPersistenceFailureTests(BaseHarness):
    def test_recipient_child_row_failure_raises_not_silent_success(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"])
        # Patch the stub doc class (not the instance: _FakeDoc.__setattr__
        # stores attribute assignment as a dict key, so an instance
        # attribute never shadows the class .append method).
        from tests.operations.test_notifications_portals import _FakeDoc
        orig_append = _FakeDoc.append

        def raising_append(self, field, row):
            if field == "recipients":
                raise RuntimeError("synthetic recipient write outage")
            return orig_append(self, field, row)

        _FakeDoc.append = raising_append
        self.addCleanup(setattr, _FakeDoc, "append", orig_append)
        # The isolated harness simulates missing DB writes as success;
        # the recipient-persistence failure must be proven on the
        # non-isolated path, where a failed write is a failure.
        self.frappe.flags.in_test = False
        self.addCleanup(setattr, self.frappe.flags, "in_test", True)
        with self.assertRaises(RuntimeError):
            self.notifications_mod.create_notification(
                event_type="overdue_tuition", title="T", message="M")


class SystemAlertFailureTests(BaseHarness):
    def test_observability_failure_raises_not_silent_empty(self):
        obs = sys.modules["toefl_house.observability"]
        orig = obs.evaluate_alert_conditions

        def raising(summary, *, ping_ok=True):
            raise RuntimeError("synthetic observability outage")

        obs.evaluate_alert_conditions = raising
        self.addCleanup(setattr, obs, "evaluate_alert_conditions", orig)
        with self.assertRaises(RuntimeError):
            list(self.notifications_mod.generate_system_alerts())


class UnparseableTimestampTests(BaseHarness):
    def _failed_notification(self, title="T"):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="SMS")  # SMS stub always fails
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title=title, message="M")
        self.notifications_mod.attempt_delivery(n["name"])
        self.notifications[n["name"]].update(
            self.notifications_mod._memory_notifications[n["name"]])
        return n

    def _set_field(self, name, **fields):
        self.notifications_mod._memory_notifications[name].update(fields)
        self.notifications[name].update(fields)

    def test_unparseable_deliver_at_persists_diagnostic(self):
        n = self._failed_notification()
        self._set_field(n["name"], deliver_at="not-a-date")
        status, detail = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(detail, "Delivery time could not be evaluated")
        stored = self.notifications_mod._memory_notifications[n["name"]]
        detail_text, _ = _decode_outcome(stored.get("last_failure"))
        self.assertIn("Delivery time could not be evaluated", detail_text)

    def test_unparseable_deliver_at_is_not_counted_as_attempt(self):
        n = self._failed_notification()
        self._set_field(n["name"], deliver_at="not-a-date")
        self.assertEqual(
            self.notifications_mod.retry_failed_notifications(), (0, 0, 0))

    def test_future_deliver_at_is_not_counted_as_attempt(self):
        n = self._failed_notification()
        self._set_field(n["name"], deliver_at="2026-10-24 13:00:00")
        status, detail = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(detail, "Delivery time has not arrived")
        self.assertEqual(
            self.notifications_mod.retry_failed_notifications(), (0, 0, 0))

    def test_unparseable_next_retry_at_persists_diagnostic(self):
        n = self._failed_notification()
        self._set_field(n["name"], next_retry_at="not-a-date")
        status, detail = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(detail, "Retry time could not be evaluated")
        stored = self.notifications_mod._memory_notifications[n["name"]]
        detail_text, _ = _decode_outcome(stored.get("last_failure"))
        self.assertIn("Retry time could not be evaluated", detail_text)
        self.assertEqual(
            self.notifications_mod.retry_failed_notifications(), (0, 0, 0))


class _GuardianHarness(BaseHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(guardian_portal=True)
        self._add_user("guardian@example.com",
                       email="guardian@example.com", roles=["Guardian"])
        self._add_student("STU-CHILD1", "child1@example.com",
                          customer="CUST-1", dob="2015-06-01")
        self._add_guardian("GUARD-1", "guardian@example.com")
        self._link_guardian("STU-CHILD1", "GUARD-1")
        self.roster.append({"parent": "GRP-1", "student": "STU-CHILD1",
                            "active": 1})
        self.course_schedules.append(
            {"name": "CS-G1", "student_group": "GRP-1", "course": "TOEFL",
             "room": "R1", "schedule_date": "2026-10-24",
             "from_time": "09:00", "to_time": "10:00", "instructor": "T1"})
        self.attendances.append(
            {"name": "ATT-C1", "student": "STU-CHILD1",
             "student_group": "GRP-1", "course_schedule": "CS-G1",
             "date": "2026-10-24", "status": "Present", "docstatus": 1})
        gl = types.ModuleType("toefl_house.operations.guardian_lifecycle")
        gl.governing_guardian_lifecycle = lambda on_date=None: {
            "effective_from": "2026-10-20", "delegation_window_days": 90,
            "pre_admission_proxy": "Allowed", "consent_evidence": "Link",
            "consent_expiry_days": 365,
            "records_recording_rights": "Test rights text"}
        sys.modules["toefl_house.operations.guardian_lifecycle"] = gl

    def _approve_independently(self, student):
        self._set_session("guardian@example.com")
        pending = self.guardian_portal.record_consent(
            student=student, evidence_type="Link",
            link_reference="https://example.com/consent")
        return self.guardian_portal.approve_guardian_consent(
            "synthetic-guardian-approval-" + student, pending["name"])

    def _break_policy_read(self):
        gl = sys.modules["toefl_house.operations.guardian_lifecycle"]
        orig = gl.governing_guardian_lifecycle

        def raising(on_date=None):
            raise RuntimeError("synthetic policy read outage")

        gl.governing_guardian_lifecycle = raising
        self.addCleanup(setattr, gl, "governing_guardian_lifecycle", orig)


class GuardianPolicyReadFailureTests(_GuardianHarness):
    def test_policy_read_failure_raises_not_empty_terms(self):
        self._break_policy_read()
        with self.assertRaises(RuntimeError):
            self.guardian_portal._governing_guardian_terms()

    def test_policy_read_failure_fails_closed_on_access_check(self):
        self._approve_independently("STU-CHILD1")
        # Access works while the policy reads.
        self.guardian_portal.get_child_attendance(student="STU-CHILD1")
        self._break_policy_read()
        self._set_session("guardian@example.com")
        # A policy-read outage must raise, never silently drop the
        # evidence/window checks and grant access on a bare consent.
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_child_attendance(student="STU-CHILD1")


class ConsentActiveRowTests(_GuardianHarness):
    def _two_rows_newest_pending(self):
        # List order is the code's newest-first order (creation desc):
        # the newest row is Pending, the older row is Active.
        self.guardian_consents.extend([
            {"name": "CONSENT-NEW-PENDING", "guardian": "GUARD-1",
             "student": "STU-CHILD1", "status": "Pending",
             "consent_date": "2026-10-24", "expiry_date": "2027-10-24",
             "evidence_type": "Link", "revoked_at": None,
             "approved_by": "", "approved_on": "",
             "link_reference": "https://example.com/consent",
             "recorded_by": "guardian@example.com"},
            {"name": "CONSENT-OLD-ACTIVE", "guardian": "GUARD-1",
             "student": "STU-CHILD1", "status": "Active",
             "consent_date": "2026-10-20", "expiry_date": "2027-10-20",
             "evidence_type": "Link", "revoked_at": None,
             "approved_by": "course.owner@example.com",
             "approved_on": "2026-10-20 10:00:00",
             "link_reference": "https://example.com/consent",
             "recorded_by": "guardian@example.com"},
        ])

    def test_get_consent_selects_active_row_under_newer_pending_row(self):
        self._two_rows_newest_pending()
        consent = self.guardian_portal._get_consent("GUARD-1", "STU-CHILD1")
        self.assertEqual(consent["name"], "CONSENT-OLD-ACTIVE")
        # End to end: the newer Pending row must not hide the Active
        # authorization from the access check.
        self._set_session("guardian@example.com")
        rows = self.guardian_portal.get_child_attendance(student="STU-CHILD1")
        self.assertEqual([r["name"] for r in rows], ["ATT-C1"])

    def test_revoke_consent_revokes_older_active_row_under_newer_pending(self):
        self._two_rows_newest_pending()
        self._set_session("guardian@example.com")
        result = self.guardian_portal.revoke_consent(
            student="STU-CHILD1", reason="revoke all")
        remaining = [c for c in self.guardian_consents
                     if c.get("status") != "Revoked"]
        self.assertEqual(remaining, [])
        self.assertEqual(result["name"], "CONSENT-OLD-ACTIVE")
        with self.assertRaises(PermissionError):
            self.guardian_portal.get_child_attendance(student="STU-CHILD1")

    def test_revoke_consent_revokes_rows_beyond_the_first_page(self):
        self._set_session("guardian@example.com")
        for i in range(60):
            self.guardian_consents.append({
                "name": "CONSENT-%02d" % i, "guardian": "GUARD-1",
                "student": "STU-CHILD1", "status": "Pending",
                "consent_date": "2026-10-20", "expiry_date": "2027-10-20",
                "evidence_type": "Link",
                "link_reference": "https://example.com/consent",
                "recorded_by": "guardian@example.com"})
        self.guardian_portal.revoke_consent(
            student="STU-CHILD1", reason="revoke all")
        remaining = [c for c in self.guardian_consents
                     if c.get("status") != "Revoked"]
        self.assertEqual(remaining, [])

    def test_consent_history_past_cap_raises_not_silent(self):
        # The consolidated guardian implementation enforces a stronger
        # paginated full-history census with a configurable fail-closed cap.
        # Set the test cap to 500 without weakening the real 10,000-row bound.
        original_cap = self.guardian_portal._CONSENT_MAX_ROWS
        self.guardian_portal._CONSENT_MAX_ROWS = 500
        self.addCleanup(setattr, self.guardian_portal, "_CONSENT_MAX_ROWS", original_cap)
        for i in range(501):
            self.guardian_consents.append({
                "name": "CONSENT-%03d" % i, "guardian": "GUARD-1",
                "student": "STU-CHILD1", "status": "Pending",
                "consent_date": "2026-10-20", "expiry_date": "2027-10-20",
                "evidence_type": "Link",
                "link_reference": "https://example.com/consent",
                "recorded_by": "guardian@example.com"})
        with self.assertRaises(ValueError):
            self.guardian_portal._get_consent("GUARD-1", "STU-CHILD1")


if __name__ == "__main__":
    unittest.main()
