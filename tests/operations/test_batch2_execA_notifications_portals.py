"""ERP batch-2 execution, Area A (C-10, C-11, C-12, C-20) — higher-bar tests.

Reproduces, against the pre-fix base (5032608d) AND the batch-2 candidate
(64aee8c1), the gaps the candidate left open, and pins the Area A fixes:

- C-10: per-recipient delivery outcomes must be DURABLY persisted (not
  just in-memory) and retries must NEVER resend to recipients who already
  succeeded; batch retries must fail closed on DB errors and survive a
  single bad row; concurrent duplicate attempts must not double-send;
  escalation must actually deliver to escalation recipients.
- C-11: no invented severity grading anywhere (zero-stock "critical" is
  the same class as the removed 1000 cutoff); live generator reads must
  not silently truncate past their caps.
- C-12: announcement endpoints must raise on DB errors; the guardian
  announcement audience filter must actually filter (the field was never
  fetched, so student-only announcements leaked to guardians); portal
  lists must page (limit/offset) instead of silently truncating.
- C-20: a failed escalation-recipient read must raise like the main rule
  read; rule-read failures must surface from create_notification too.
- Cross-cutting: naive vs timezone-aware timestamps (Asia/Kabul) must not
  crash retry gating; EmailProvider must not claim delivery without
  sending; a channel-enablement check failure must fail closed.

Synthetic data only. Runs against the stub frappe harness from
tests/operations/test_notifications_portals.py.
"""
import json
import sys
import threading
import types
import unittest
from datetime import datetime

from tests.operations.test_notifications_portals import BaseHarness


def _decode_outcome(last_failure):
    """Independent decoder for the persisted per-recipient outcome record.

    Returns (detail_text, results_or_None). Plain-text legacy values decode
    to (text, None) — i.e. no durable per-recipient record exists.
    """
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


class _PartialProvider:
    """Succeeds only for a@example.com; records every recipient attempted."""
    name = "partial-test-provider"

    def __init__(self):
        self.calls = []

    def send(self, notification):
        self.calls.append(notification.get("recipient"))
        return notification.get("recipient") == "a@example.com"


class _RecordingProvider:
    """Records every recipient; succeeds/fails per the given mapping."""

    name = "recording-test-provider"

    def __init__(self, ok_for):
        self.ok_for = set(ok_for)
        self.calls = []

    def send(self, notification):
        self.calls.append(notification.get("recipient"))
        return notification.get("recipient") in self.ok_for


class _SlowCountingProvider:
    name = "slow-counting-test-provider"

    def __init__(self, entered, delay=0.3):
        self.entered = entered
        self.delay = delay
        self.calls = []

    def send(self, notification):
        import time
        self.calls.append(notification.get("recipient"))
        self.entered.set()
        time.sleep(self.delay)
        return True


def _enable(mod, event_type, recipients, channel="Dashboard", **extra):
    rule = {
        "event_type": event_type, "enabled": True,
        "recipients": list(recipients), "severity": "warning",
        "channel": channel, "max_retries": 2, "retry_delay_minutes": 1,
    }
    rule.update(extra)
    mod.set_dispatch_rule(rule)


class DeliveryPersistenceTests(BaseHarness):
    def test_partial_delivery_results_are_persisted_to_the_doc(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        # Drop the in-memory fallback BEFORE attempting, so the attempt
        # goes through the durable doc path (frappe.get_doc + save, the
        # production path): the harness's in-memory doc proxy never
        # writes back to the stub store, so only the doc path proves
        # persistence. A fresh load must then recover the per-recipient
        # outcomes from the durable doc alone.
        self.notifications_mod._memory_notifications.pop(n["name"], None)
        status, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=_PartialProvider())
        self.assertEqual(status, "failed")
        doc = self.frappe.get_doc("TH Notification", n["name"])
        _, results = _decode_outcome(doc.get("last_failure"))
        self.assertIsNotNone(results, "last_failure carries no durable "
                               "per-recipient outcome record")
        self.assertEqual({r["recipient"]: r["delivered"] for r in results},
                         {"a@example.com": True, "b@example.com": False})
        _, data = self.notifications_mod._load_notification(n["name"])
        self.assertEqual({r["recipient"]: r["delivered"]
                          for r in data.get("delivery_results") or []},
                         {"a@example.com": True, "b@example.com": False})

    def test_retry_after_fresh_load_skips_already_delivered_recipients(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        self.notifications_mod._memory_notifications.pop(n["name"], None)
        first = _PartialProvider()
        s1, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=first)
        self.assertEqual(s1, "failed")
        self.assertEqual(first.calls, ["a@example.com", "b@example.com"])
        # Past next_retry_at; the retry loads the notification fresh
        # from the durable doc and must skip a@example.com on the
        # strength of the persisted outcome alone. The retry provider
        # reaches b but would fail a — so any resend to a fails the
        # retry outright.
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        second = _RecordingProvider(ok_for={"b@example.com"})
        s2, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=second)
        self.assertEqual(s2, "delivered")
        self.assertEqual(second.calls, ["b@example.com"],
                         "retry resent to a@example.com, who already succeeded")
        doc = self.frappe.get_doc("TH Notification", n["name"])
        self.assertEqual(doc.get("status"), "delivered")
        self.assertEqual(doc.get("last_failure") or "", "",
                         "delivered notification keeps a stale failure record")

    def test_retry_never_resends_to_recipients_who_already_succeeded(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        first = _PartialProvider()
        s1, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=first)
        self.assertEqual(s1, "failed")
        self.assertEqual(first.calls, ["a@example.com", "b@example.com"])
        # Past next_retry_at; a provider that now FAILS for a but
        # succeeds for b. A correct retry sends only to b and delivers
        # (any resend to a fails the retry outright).
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        second = _RecordingProvider(ok_for={"b@example.com"})
        s2, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=second)
        self.assertEqual(s2, "delivered")
        self.assertEqual(second.calls, ["b@example.com"],
                         "retry resent to a@example.com, who already succeeded")
        stored = self.notifications_mod._memory_notifications[n["name"]]
        self.assertEqual({r["recipient"]: r["delivered"]
                          for r in stored["delivery_results"]},
                         {"a@example.com": True, "b@example.com": True})
        doc = self.frappe.get_doc("TH Notification", n["name"])
        self.assertEqual(doc.get("last_failure") or "", "",
                         "delivered notification keeps a stale failure record")

    def test_concurrent_duplicate_attempts_do_not_double_send(self):
        _enable(self.notifications_mod, "overdue_tuition", ["a@example.com"])
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        entered = threading.Event()
        provider = _SlowCountingProvider(entered)
        results = {}

        def run(key):
            results[key] = self.notifications_mod.attempt_delivery(
                n["name"], provider_override=provider)

        t1 = threading.Thread(target=run, args=("first",))
        t1.start()
        self.assertTrue(entered.wait(timeout=5),
                        "first delivery never started")
        t2 = threading.Thread(target=run, args=("second",))
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(provider.calls, ["a@example.com"],
                         "concurrent attempts sent twice")
        self.assertIn("already in progress", results["second"][1])
        self.assertEqual(results["first"][0], "delivered")


class RetryBatchTests(BaseHarness):
    def _failed_notification(self, title="T"):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="SMS")  # SMS stub always fails
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title=title, message="M")
        self.notifications_mod.attempt_delivery(n["name"])
        self.notifications[n["name"]].update(
            self.notifications_mod._memory_notifications[n["name"]])
        return n

    def test_batch_retry_db_read_failure_raises_not_silent_zero(self):
        self._failed_notification()
        orig = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "TH Notification":
                raise RuntimeError("synthetic DB outage")
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising
        with self.assertRaises(RuntimeError):
            self.notifications_mod.retry_failed_notifications()

    def test_batch_retry_survives_a_single_bad_row(self):
        # Distinct titles: notification names hash (now + title), so
        # identical titles at the same clock would collide into one row.
        n1 = self._failed_notification(title="T1")
        self._failed_notification(title="T2")
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        orig_attempt = self.notifications_mod.attempt_delivery

        def flaky(name, provider_override=None):
            if name == n1["name"]:
                raise ValueError("synthetic load failure for one row")
            return orig_attempt(name, provider_override=provider_override)

        self.notifications_mod.attempt_delivery = flaky
        self.addCleanup(setattr, self.notifications_mod,
                        "attempt_delivery", orig_attempt)
        attempted, delivered, still_failed = (
            self.notifications_mod.retry_failed_notifications())
        # One row errored (still failed), one row was attempted and is
        # still failed: still_failed counts both.
        self.assertEqual((attempted, delivered, still_failed), (1, 0, 2))

    def test_exhausted_old_rows_cannot_starve_a_later_due_retry(self):
        # Real Frappe applies the requested query limit. The old batch
        # fetched only `limit=1`, always saw one exhausted row, and
        # never reached the later due recipient.
        for i in range(25):
            blocked = self._failed_notification(title=f"BLOCKED-{i:02d}")
            self.notifications_mod._memory_notifications[
                blocked["name"]]["retry_count"] = 2
            self.notifications[blocked["name"]]["retry_count"] = 2
        due = self._failed_notification(title="DUE-LATER")
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        original = self.frappe.db.get_all

        def bounded_get_all(doctype, filters=None, fields=None, **kwargs):
            rows = original(doctype, filters=filters, fields=fields, **kwargs)
            if doctype == "TH Notification":
                bound = kwargs.get("limit_page_length") or kwargs.get("limit")
                if bound:
                    return rows[:bound]
            return rows

        self.frappe.db.get_all = bounded_get_all
        result = self.notifications_mod.retry_failed_notifications(limit=1)
        self.assertEqual(result, (1, 0, 1))
        self.assertEqual(
            self.notifications_mod._memory_notifications[
                due["name"]]["retry_count"], 2)

    def test_retry_scan_overflow_refuses_instead_of_silent_truncation(self):
        original = self.frappe.db.get_all

        def oversized(doctype, filters=None, fields=None, **kwargs):
            if doctype == "TH Notification" and filters == {"status": "failed"}:
                return [{"name": f"EXCESS-{i}"}
                        for i in range(self.notifications_mod.RETRY_SCAN_MAX + 1)]
            return original(doctype, filters=filters, fields=fields, **kwargs)

        self.frappe.db.get_all = oversized
        with self.assertRaisesRegex(self.frappe.ValidationError, "backlog"):
            self.notifications_mod.retry_failed_notifications(limit=1)

    def test_missing_recipient_cannot_be_reported_delivered(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="Dashboard")
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="MISSING-RECIPS", message="M")
        self.notifications_mod._memory_notifications[
            n["name"]]["recipients"] = []
        self.notifications[n["name"]]["recipients"] = []
        provider = _RecordingProvider({"a@example.com", ""})
        status, detail = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=provider)
        self.assertEqual(status, "failed")
        self.assertIn("No recipients configured", detail)
        self.assertEqual(provider.calls, [])
        self.assertIn(
            "No recipients configured",
            self.notifications_mod._memory_notifications[
                n["name"]]["last_failure"])

    def test_batch_retry_limit_is_validated(self):
        with self.assertRaises(ValueError):
            self.notifications_mod.retry_failed_notifications(limit=0)
        with self.assertRaises(ValueError):
            self.notifications_mod.retry_failed_notifications(limit="abc")


class EscalationDeliveryTests(BaseHarness):
    def _delivered_notification(self):
        self.notifications_mod.set_dispatch_rule({
            "event_type": "overdue_tuition", "enabled": True,
            "recipients": ["a@example.com"], "severity": "critical",
            "channel": "Dashboard", "escalate_after_minutes": 60,
            "escalation_recipients": ["boss@example.com"], "max_retries": 2,
            "retry_delay_minutes": 1,
        })
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        return n

    def test_escalation_actually_delivers_to_escalation_recipients(self):
        n = self._delivered_notification()
        rec = _RecordingProvider(ok_for={"a@example.com", "boss@example.com"})
        s, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=rec)
        self.assertEqual(s, "delivered")
        self.assertEqual(rec.calls, ["a@example.com"])
        self.frappe.utils.now_datetime = lambda: "2026-10-24 14:30:00"
        ok, detail = self.notifications_mod.escalate_if_needed(
            n["name"], provider_override=rec)
        self.assertTrue(ok)
        self.assertIn("boss@example.com", detail)
        self.assertEqual(rec.calls, ["a@example.com", "boss@example.com"],
                         "escalation never delivered to the escalation recipient")

    def test_failed_escalation_is_retryable_and_skips_original_recipients(self):
        n = self._delivered_notification()
        rec = _RecordingProvider(ok_for={"a@example.com"})
        self.notifications_mod.attempt_delivery(
            n["name"], provider_override=rec)
        self.frappe.utils.now_datetime = lambda: "2026-10-24 14:30:00"
        ok, _ = self.notifications_mod.escalate_if_needed(
            n["name"], provider_override=rec)
        self.assertFalse(ok, "escalation reported success though delivery failed")
        stored = self.notifications_mod._memory_notifications[n["name"]]
        self.assertEqual(stored["status"], "failed")
        self.assertTrue(stored.get("escalated"))
        # Retry with a provider that now reaches the boss: only the boss
        # is attempted, the original recipient is never resent.
        rec.ok_for.add("boss@example.com")
        self.frappe.utils.now_datetime = lambda: "2026-10-24 14:32:00"
        s, _ = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=rec)
        self.assertEqual(s, "delivered")
        self.assertEqual(rec.calls.count("a@example.com"), 1)
        self.assertEqual(rec.calls.count("boss@example.com"), 2)


class ThresholdTests(BaseHarness):
    def test_low_book_stock_zero_qty_is_not_critical(self):
        snap = {"book_bins": [{"item_code": "BOOK-1", "item_name": "Gone",
                               "actual_qty": 0, "reorder_level": 5,
                               "warehouse": "Main"}]}
        specs = list(self.notifications_mod.generate_low_book_stock(snap))
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["severity"], "warning")

    def test_overdue_generator_live_path_overflow_raises(self):
        orig = self.frappe.db.get_all

        def many(doctype, filters=None, fields=None, **kw):
            if doctype == "Fees":
                return [{"name": "F-%03d" % i, "student": "STU-%03d" % i,
                         "student_name": "S", "due_date": "2026-10-20",
                         "outstanding_amount": 100, "docstatus": 1}
                        for i in range(501)]
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = many
        with self.assertRaises(ValueError):
            list(self.notifications_mod.generate_overdue_tuition({}))

    def test_low_book_stock_live_path_overflow_raises(self):
        orig = self.frappe.db.get_all

        def many(doctype, filters=None, fields=None, **kw):
            if doctype == "Item":
                return [{"name": "BOOK-%03d" % i, "item_name": "B"}
                        for i in range(501)]
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = many
        with self.assertRaises(ValueError):
            list(self.notifications_mod.generate_low_book_stock({}))

    def test_overdue_generator_live_read_failure_raises(self):
        orig = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "Fees":
                raise RuntimeError("synthetic DB outage")
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising
        with self.assertRaises(RuntimeError):
            list(self.notifications_mod.generate_overdue_tuition({}))

    def test_low_book_stock_live_read_failure_raises(self):
        orig = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "Item":
                raise RuntimeError("synthetic DB outage")
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising
        with self.assertRaises(RuntimeError):
            list(self.notifications_mod.generate_low_book_stock({}))
        orig = self.frappe.db.get_all

        def many(doctype, filters=None, fields=None, **kw):
            if doctype == "Item":
                return [{"name": "BOOK-%03d" % i, "item_name": "B"}
                        for i in range(501)]
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = many
        with self.assertRaises(ValueError):
            list(self.notifications_mod.generate_low_book_stock({}))


class DispatchRuleFailureTests(BaseHarness):
    def test_escalation_recipient_read_failure_raises(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], escalation_recipients=["boss@example.com"])
        orig = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "TH Notification Escalation Recipient":
                raise RuntimeError("synthetic DB outage")
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising
        with self.assertRaises(RuntimeError):
            self.notifications_mod.get_dispatch_rule("overdue_tuition")

    def test_create_notification_surfaces_rule_read_failure(self):
        orig = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "TH Notification Dispatch Rule":
                raise RuntimeError("synthetic DB outage")
            return orig(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising
        with self.assertRaises(RuntimeError):
            self.notifications_mod.create_notification(
                event_type="overdue_tuition", title="T", message="M")


class TimezoneTests(BaseHarness):
    def test_retry_gate_survives_timezone_aware_now(self):
        from zoneinfo import ZoneInfo
        kabul = ZoneInfo("Asia/Kabul")
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="SMS")
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        # Site clock returns an aware Kabul datetime (frappe may hand
        # back either naive or aware values; both must compare cleanly).
        self.frappe.utils.now_datetime = lambda: datetime(
            2026, 10, 24, 12, 0, 0, tzinfo=kabul)
        s1, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s1, "failed")
        s2, detail2 = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s2, "failed")
        self.assertIn("Retry time has not arrived", detail2)
        self.frappe.utils.now_datetime = lambda: datetime(
            2026, 10, 24, 12, 2, 0, tzinfo=kabul)
        s3, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s3, "failed")
        self.assertEqual(
            self.notifications_mod._memory_notifications[n["name"]]["retry_count"], 2)


class ProviderSafetyTests(BaseHarness):
    def test_email_provider_does_not_claim_delivery_without_sending(self):
        # The stub frappe harness has no sendmail: nothing is enqueued,
        # so the provider must report failure, never success.
        ok = self.provider.EmailProvider().send({
            "recipient": "a@example.com", "title": "T", "message": "M"})
        self.assertFalse(ok)
        self.assertFalse(self.provider.EmailProvider().send({
            "recipient": "not-an-email", "title": "T", "message": "M"}))

    def test_channel_enablement_check_failure_fails_closed(self):
        orig = self.portal_policy.is_channel_enabled

        def raising(channel):
            raise RuntimeError("synthetic config outage")

        self.portal_policy.is_channel_enabled = raising
        self.addCleanup(setattr, self.portal_policy,
                        "is_channel_enabled", orig)
        ok, _, detail = self.provider.deliver(
            {"channel": "Dashboard", "recipient": "a@example.com",
             "title": "T", "message": "M", "notification_id": "X"})
        self.assertFalse(ok)
        self.assertIn("could not be verified", detail.lower())


class _AnnouncementHarness(BaseHarness):
    def _raise_on_get_all(self, *doctypes):
        orig_get_all = self.frappe.get_all
        orig_db_get_all = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype in doctypes:
                raise RuntimeError("synthetic DB outage on %s" % doctype)
            return orig_get_all(doctype, filters=filters, fields=fields, **kw)

        def db_raising(doctype, filters=None, fields=None, **kw):
            if doctype in doctypes:
                raise RuntimeError("synthetic DB outage on %s" % doctype)
            return orig_db_get_all(doctype, filters=filters, fields=fields, **kw)

        self.frappe.get_all = raising
        self.frappe.db.get_all = db_raising


class AnnouncementTests(_AnnouncementHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(
            student_portal=True, guardian_portal=True)
        self._add_user("alice@example.com", email="alice@example.com",
                       roles=["Student"])
        self._add_student("STU-ALICE", "alice@example.com", customer="CUST-A",
                          dob="2010-05-01")
        self.user_permissions.append(
            {"name": "UP-ALICE", "user": "alice@example.com",
             "allow": "Student", "for_value": "STU-ALICE"})
        self._add_user("guardian@example.com", email="guardian@example.com",
                       roles=["Guardian"])
        self._add_student("STU-CHILD1", "child1@example.com", customer="CUST-1",
                          dob="2015-06-01")
        self._add_guardian("GUARD-1", "guardian@example.com")
        self._link_guardian("STU-CHILD1", "GUARD-1")
        self.announcements.extend([
            {"name": "ANN-ALL", "title": "All", "message": "m",
             "publish_date": "2026-10-24", "audience": "All",
             "status": "Published"},
            {"name": "ANN-STU", "title": "Students only", "message": "m",
             "publish_date": "2026-10-24", "audience": "Students",
             "status": "Published"},
            {"name": "ANN-GRD", "title": "Guardians only", "message": "m",
             "publish_date": "2026-10-24", "audience": "Guardians",
             "status": "Published"},
        ])

    def test_student_announcement_read_error_raises(self):
        self._set_session("alice@example.com")
        self._raise_on_get_all("TH Portal Announcement")
        with self.assertRaises(RuntimeError):
            self.student_portal.get_announcements()

    def test_guardian_announcement_read_error_raises(self):
        self._set_session("guardian@example.com")
        self._raise_on_get_all("TH Portal Announcement")
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_announcements_for_guardian()

    def test_student_only_announcement_not_shown_to_guardians(self):
        self._set_session("guardian@example.com")
        anns = self.guardian_portal.get_announcements_for_guardian()
        self.assertEqual({a["name"] for a in anns}, {"ANN-ALL", "ANN-GRD"})

    def test_guardian_only_announcement_not_shown_to_students(self):
        self._set_session("alice@example.com")
        anns = self.student_portal.get_announcements()
        self.assertEqual({a["name"] for a in anns}, {"ANN-ALL", "ANN-STU"})


class PortalPaginationTests(BaseHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(student_portal=True,
                                            guardian_portal=True)
        self._add_user("alice@example.com", email="alice@example.com",
                       roles=["Student"])
        self._add_student("STU-ALICE", "alice@example.com", customer="CUST-A",
                          dob="2010-05-01")
        self.user_permissions.append(
            {"name": "UP-ALICE", "user": "alice@example.com",
             "allow": "Student", "for_value": "STU-ALICE"})
        for i in range(1, 4):
            self.attendances.append(
                {"name": "ATT-%d" % i, "student": "STU-ALICE",
                 "student_group": "GRP-10A", "course_schedule": "CS-1",
                 "date": "2026-10-2%d" % i, "status": "Present",
                 "docstatus": 1})
        self._add_user("guardian@example.com", email="guardian@example.com",
                       roles=["Guardian"])
        self._add_student("STU-CHILD1", "child1@example.com", customer="CUST-1",
                          dob="2015-06-01")
        self._add_guardian("GUARD-1", "guardian@example.com")
        self._link_guardian("STU-CHILD1", "GUARD-1")
        self.attendances.append(
            {"name": "ATT-C1", "student": "STU-CHILD1",
             "student_group": "GRP-1", "course_schedule": "CS-G1",
             "date": "2026-10-24", "status": "Present", "docstatus": 1})
        self.attendances.append(
            {"name": "ATT-C2", "student": "STU-CHILD1",
             "student_group": "GRP-1", "course_schedule": "CS-G1",
             "date": "2026-10-23", "status": "Present", "docstatus": 1})
        gl = types.ModuleType("toefl_house.operations.guardian_lifecycle")
        gl.governing_guardian_lifecycle = lambda on_date=None: {
            "effective_from": "2026-10-20", "delegation_window_days": 90,
            "pre_admission_proxy": "Allowed", "consent_evidence": "Link",
            "consent_expiry_days": 365,
            "records_recording_rights": "Test rights text"}
        sys.modules["toefl_house.operations.guardian_lifecycle"] = gl

    def _approve(self, student):
        self._set_session("guardian@example.com")
        pending = self.guardian_portal.record_consent(
            student=student, evidence_type="Link",
            link_reference="https://example.com/consent")
        self.guardian_portal.approve_guardian_consent(
            "synthetic-guardian-approval-" + student, pending["name"])

    def test_student_attendance_pages_with_limit_and_offset(self):
        self._set_session("alice@example.com")
        page1 = self.student_portal.get_my_attendance(limit=2)
        self.assertEqual([r["name"] for r in page1], ["ATT-1", "ATT-2"])
        page2 = self.student_portal.get_my_attendance(limit=2, offset=2)
        self.assertEqual([r["name"] for r in page2], ["ATT-3"])
        self.assertEqual(len(self.student_portal.get_my_attendance()),
                         3)

    def test_attendance_limit_and_offset_are_validated(self):
        self._set_session("alice@example.com")
        for bad in (0, -1, 201, "abc", 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.student_portal.get_my_attendance(limit=bad)
        with self.assertRaises(ValueError):
            self.student_portal.get_my_attendance(offset=-1)
        with self.assertRaises(ValueError):
            self.student_portal.get_my_attendance(offset="abc")

    def test_guardian_attendance_pages_with_limit_and_offset(self):
        self._approve("STU-CHILD1")
        page1 = self.guardian_portal.get_child_attendance(
            student="STU-CHILD1", limit=1)
        self.assertEqual([r["name"] for r in page1], ["ATT-C1"])
        page2 = self.guardian_portal.get_child_attendance(
            student="STU-CHILD1", limit=1, offset=1)
        self.assertEqual([r["name"] for r in page2], ["ATT-C2"])

    # INTEGRATION NOTE (Batch 2 execution, 2026-11-06): the candidate's
    # test_revoke_consent_revokes_rows_beyond_the_first_page was omitted
    # here. It pins _all_consents + revoke-every-row, which build on the
    # dangerous-fixes rewrite of _get_consent/revoke_consent (5032608d,
    # PR #137 C-04) that is not on main (b2e608e9). The test returns
    # with #137.

    def test_get_my_children_missing_student_row_raises(self):
        self._set_session("guardian@example.com")
        orig_get_value = self.frappe.db.get_value
        calls = {"n": 0}

        def flaky(doctype, name_or_filters, fieldname=None, **kw):
            if doctype == "Student" and isinstance(name_or_filters, str):
                calls["n"] += 1
                if calls["n"] >= 2:
                    return None
            return orig_get_value(doctype, name_or_filters, fieldname, **kw)

        self.frappe.db.get_value = flaky
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_my_children()


if __name__ == "__main__":
    unittest.main()
