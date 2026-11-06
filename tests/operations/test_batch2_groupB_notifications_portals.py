"""ERP batch-2 Group B (C-10, C-11, C-12, C-20): notifications + portals.

Regression tests against the real modules under the stub frappe harness
from tests/operations/test_notifications_portals.py. Synthetic data only.

- C-10: delivery must reach ALL recipients (fail if any fails, with
  per-recipient status); retries are gated on next_retry_at.
- C-11: low-book-stock reads the native Item Reorder level (items without
  one are skipped, never defaulted to 5); overdue-tuition severity no
  longer grades on a currency-blind 1000 cutoff.
- C-12: portal DB read errors raise instead of returning empty lists
  masquerading as "no data"; limit is validated with ValidationError.
- C-20: a failed dispatch-rule read raises instead of silently returning
  the disabled default.
"""
import sys
import types
import unittest

from tests.operations.test_notifications_portals import BaseHarness


class _PartialProvider:
    """Succeeds only for the first recipient — proves partial delivery fails."""
    name = "partial-test-provider"

    def send(self, notification):
        return notification.get("recipient") == "a@example.com"


class _AllOkProvider:
    name = "all-ok-test-provider"

    def send(self, notification):
        return True


def _enable(mod, event_type, recipients, channel="Dashboard", **extra):
    rule = {
        "event_type": event_type, "enabled": True,
        "recipients": list(recipients), "severity": "warning",
        "channel": channel, "max_retries": 2, "retry_delay_minutes": 1,
    }
    rule.update(extra)
    mod.set_dispatch_rule(rule)


class NotificationDeliveryTests(BaseHarness):
    def test_all_recipients_must_succeed(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com"], channel="Dashboard")
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        status, detail = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=_PartialProvider())
        self.assertEqual(status, "failed")
        self.assertIn("b@example.com", detail)
        stored = self.notifications_mod._memory_notifications[n["name"]]
        results = {r["recipient"]: r["delivered"]
                   for r in stored["delivery_results"]}
        self.assertEqual(results, {"a@example.com": True,
                                   "b@example.com": False})

    def test_delivered_only_when_every_recipient_succeeds(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com", "b@example.com"], channel="Dashboard")
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        status, detail = self.notifications_mod.attempt_delivery(
            n["name"], provider_override=_AllOkProvider())
        self.assertEqual(status, "delivered")
        self.assertIn("a@example.com", detail)
        self.assertIn("b@example.com", detail)

    def test_retry_gated_on_next_retry_at(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="SMS")  # SMS stub always fails
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        s1, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s1, "failed")
        stored = self.notifications_mod._memory_notifications[n["name"]]
        self.assertEqual(stored["retry_count"], 1)
        self.assertIsNotNone(stored.get("next_retry_at"))
        # Immediate retry must not attempt delivery.
        s2, detail2 = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s2, "failed")
        self.assertIn("Retry time has not arrived", detail2)
        self.assertEqual(
            self.notifications_mod._memory_notifications[n["name"]]["retry_count"], 1)
        # Past next_retry_at, the retry is attempted again (and fails).
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        s3, _ = self.notifications_mod.attempt_delivery(n["name"])
        self.assertEqual(s3, "failed")
        self.assertEqual(
            self.notifications_mod._memory_notifications[n["name"]]["retry_count"], 2)

    def test_retry_failed_notifications_skips_not_yet_due(self):
        _enable(self.notifications_mod, "overdue_tuition",
                ["a@example.com"], channel="SMS")
        n = self.notifications_mod.create_notification(
            event_type="overdue_tuition", title="T", message="M")
        self.notifications_mod.attempt_delivery(n["name"])
        # Mirror the durable failure into the stub DB store, which the
        # batch retry reads (the in-memory doc proxy does not write back
        # to the stub store — production doc.save does persist).
        self.notifications[n["name"]].update(
            self.notifications_mod._memory_notifications[n["name"]])
        attempted, delivered, still_failed = (
            self.notifications_mod.retry_failed_notifications())
        self.assertEqual((attempted, delivered, still_failed), (0, 0, 0))
        self.frappe.utils.now_datetime = lambda: "2026-10-24 12:02:00"
        attempted, delivered, still_failed = (
            self.notifications_mod.retry_failed_notifications())
        self.assertEqual((attempted, delivered, still_failed), (1, 0, 1))


class NotificationThresholdTests(BaseHarness):
    def test_overdue_tuition_has_no_amount_severity_cutoff(self):
        snap = {"fees": [{"name": "F-1", "student": "STU-1",
                          "student_name": "Ali", "due_date": "2026-10-20",
                          "outstanding_amount": 5000, "docstatus": 1}]}
        specs = list(self.notifications_mod.generate_overdue_tuition(snap))
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0]["severity"], "warning")

    def test_low_book_stock_snapshot_without_reorder_level_is_skipped(self):
        snap = {"book_bins": [{"item_code": "BOOK-1", "item_name": "No Level",
                               "actual_qty": 0, "warehouse": "Main"}]}
        self.assertEqual(
            list(self.notifications_mod.generate_low_book_stock(snap)), [])

    def test_low_book_stock_snapshot_with_explicit_level_still_fires(self):
        snap = {"book_bins": [
            {"item_code": "BOOK-1", "item_name": "Oxford 101", "actual_qty": 2,
             "reorder_level": 5, "warehouse": "Main"},
            {"item_code": "BOOK-2", "item_name": "Full", "actual_qty": 10,
             "reorder_level": 5, "warehouse": "Main"},
        ]}
        specs = list(self.notifications_mod.generate_low_book_stock(snap))
        self.assertEqual([s["related_name"] for s in specs], ["BOOK-1"])

    def test_low_book_stock_live_path_reads_native_item_reorder(self):
        items = [{"name": "BOOK-A", "item_name": "Book A"},
                 {"name": "BOOK-B", "item_name": "Book B"}]
        reorder_rows = [{"parent": "BOOK-A", "parenttype": "Item",
                         "warehouse": "Main", "warehouse_reorder_level": 3}]
        bins = [{"item_code": "BOOK-A", "actual_qty": 2, "warehouse": "Main"},
                {"item_code": "BOOK-B", "actual_qty": 1, "warehouse": "Main"}]
        orig_get_all = self.frappe.db.get_all

        def get_all2(doctype, filters=None, fields=None, **kw):
            if doctype == "Item":
                return [dict(r) for r in items]
            if doctype == "Item Reorder":
                return [dict(r) for r in reorder_rows]
            if doctype == "Bin":
                code = (filters or {}).get("item_code")
                return [dict(r) for r in bins if r["item_code"] == code]
            return orig_get_all(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = get_all2
        # BOOK-A is below its native level 3 and fires; BOOK-B has no
        # configured level and is skipped even though qty is 1.
        specs = list(self.notifications_mod.generate_low_book_stock({}))
        self.assertEqual([s["related_name"] for s in specs], ["BOOK-A"])
        self.assertIn("reorder at 3", specs[0]["message"])


class DispatchRuleReadFailureTests(BaseHarness):
    def _break_dispatch_rule_reads(self):
        orig_get_all = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype == "TH Notification Dispatch Rule":
                raise RuntimeError("synthetic DB outage")
            return orig_get_all(doctype, filters=filters, fields=fields, **kw)

        self.frappe.db.get_all = raising

    def test_rule_read_failure_raises_not_disabled(self):
        self._break_dispatch_rule_reads()
        with self.assertRaises(RuntimeError):
            self.notifications_mod.get_dispatch_rule("overdue_tuition")

    def test_generate_all_surfaces_rule_read_failure(self):
        self._break_dispatch_rule_reads()
        with self.assertRaises(RuntimeError):
            self.notifications_mod.generate_all_notifications({})

    def test_no_rule_configured_still_returns_disabled_default(self):
        rule = self.notifications_mod.get_dispatch_rule("overdue_tuition")
        self.assertFalse(rule["enabled"])
        self.assertEqual(rule["recipients"], [])


class _PortalHarness(BaseHarness):
    """BaseHarness + a raising-DB wrapper for the portal read under test."""

    def _raise_on_get_all(self, *doctypes):
        # Portals call frappe.get_all (module level); notifications use
        # frappe.db.get_all — wrap both.
        orig_get_all = self.frappe.get_all
        orig_db_get_all = self.frappe.db.get_all

        def raising(doctype, filters=None, fields=None, **kw):
            if doctype in doctypes:
                raise RuntimeError(f"synthetic DB outage on {doctype}")
            return orig_get_all(doctype, filters=filters, fields=fields, **kw)

        def db_raising(doctype, filters=None, fields=None, **kw):
            if doctype in doctypes:
                raise RuntimeError(f"synthetic DB outage on {doctype}")
            return orig_db_get_all(doctype, filters=filters, fields=fields, **kw)

        self.frappe.get_all = raising
        self.frappe.db.get_all = db_raising

    def _raise_on_get_value(self, *doctypes):
        orig_get_value = self.frappe.db.get_value

        def raising(doctype, name_or_filters, fieldname=None, **kw):
            if doctype in doctypes:
                raise RuntimeError(f"synthetic DB outage on {doctype}")
            return orig_get_value(doctype, name_or_filters, fieldname, **kw)

        self.frappe.db.get_value = raising


class PortalReadErrorTests(_PortalHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(student_portal=True)
        self._add_user("alice@example.com", email="alice@example.com",
                       roles=["Student"])
        self._add_student("STU-ALICE", "alice@example.com", customer="CUST-A",
                          dob="2010-05-01")
        self.user_permissions.append(
            {"name": "UP-ALICE", "user": "alice@example.com",
             "allow": "Student", "for_value": "STU-ALICE"})
        self.roster.append({"parent": "GRP-10A", "student": "STU-ALICE",
                            "active": 1})
        self.course_schedules.append(
            {"name": "CS-1", "student_group": "GRP-10A", "course": "TOEFL-A",
             "room": "R1", "schedule_date": "2026-10-24",
             "from_time": "09:00", "to_time": "10:00", "instructor": "T1"})
        self.attendances.append(
            {"name": "ATT-1", "student": "STU-ALICE", "student_group": "GRP-10A",
             "course_schedule": "CS-1", "date": "2026-10-24",
             "status": "Present", "docstatus": 1})
        self.assessment_results.append(
            {"name": "AR-1", "student": "STU-ALICE", "assessment_plan": "AP-1",
             "grade": "A", "docstatus": 1, "posting_date": "2026-10-24"})
        self._set_session("alice@example.com")

    def test_schedule_read_error_raises_not_empty(self):
        self._raise_on_get_all("Course Schedule")
        with self.assertRaises(RuntimeError):
            self.student_portal.get_my_schedule()

    def test_attendance_read_error_raises_not_empty(self):
        self._raise_on_get_all("Student Attendance")
        with self.assertRaises(RuntimeError):
            self.student_portal.get_my_attendance()

    def test_grades_read_error_raises_not_empty(self):
        self._raise_on_get_all("Assessment Result")
        with self.assertRaises(RuntimeError):
            self.student_portal.get_my_grades()

    def test_student_identity_read_error_raises(self):
        self._raise_on_get_value("Student")
        with self.assertRaises(RuntimeError):
            self.student_portal.get_my_student()

    def test_non_numeric_limit_is_validation_error(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            self.student_portal.get_my_attendance(limit="abc")

    def test_numeric_string_limit_is_accepted(self):
        rows = self.student_portal.get_my_attendance(limit="5")
        self.assertEqual(len(rows), 1)


class GuardianPortalReadErrorTests(_PortalHarness):
    def setUp(self):
        super().setUp()
        self.portal_policy.set_portal_flags(guardian_portal=True)
        self._add_user("guardian@example.com", email="guardian@example.com",
                       roles=["Guardian"])
        self._add_student("STU-CHILD1", "child1@example.com", customer="CUST-1",
                          dob="2015-06-01")
        self._add_guardian("GUARD-1", "guardian@example.com")
        self._link_guardian("STU-CHILD1", "GUARD-1")
        self.roster.append({"parent": "GRP-1", "student": "STU-CHILD1",
                            "active": 1})
        self.course_schedules.append(
            {"name": "CS-G1", "student_group": "GRP-1", "course": "TOEFL",
             "room": "R1", "schedule_date": "2026-10-24",
             "from_time": "09:00", "to_time": "10:00", "instructor": "T1"})
        self.attendances.append(
            {"name": "ATT-C1", "student": "STU-CHILD1", "student_group": "GRP-1",
             "course_schedule": "CS-G1", "date": "2026-10-24",
             "status": "Present", "docstatus": 1})
        self.fees.append(
            {"name": "FEE-C1", "student": "STU-CHILD1", "program": "TOEFL",
             "academic_year": "2026", "grand_total": 500,
             "outstanding_amount": 100, "due_date": "2026-10-20",
             "docstatus": 1})
        self.assessment_results.append(
            {"name": "AR-C1", "student": "STU-CHILD1", "assessment_plan": "AP-1",
             "grade": "B", "docstatus": 1, "posting_date": "2026-10-24"})
        gl = types.ModuleType("toefl_house.operations.guardian_lifecycle")
        gl.governing_guardian_lifecycle = lambda on_date=None: {
            "effective_from": "2026-10-20", "delegation_window_days": 90,
            "pre_admission_proxy": "Allowed", "consent_evidence": "Link",
            "consent_expiry_days": 365,
            "records_recording_rights": "Test rights text"}
        sys.modules["toefl_house.operations.guardian_lifecycle"] = gl
        self._set_session("guardian@example.com")
        pending = self.guardian_portal.record_consent(
            student="STU-CHILD1", evidence_type="Link",
            link_reference="https://example.com/consent")
        self.guardian_portal.approve_guardian_consent(
            "synthetic-guardian-approval-STU-CHILD1", pending["name"])

    def test_child_schedule_read_error_raises_not_empty(self):
        self._raise_on_get_all("Course Schedule")
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_child_schedule(student="STU-CHILD1")

    def test_child_attendance_read_error_raises_not_empty(self):
        self._raise_on_get_all("Student Attendance")
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_child_attendance(student="STU-CHILD1")

    def test_child_grades_read_error_raises_not_empty(self):
        self._raise_on_get_all("Assessment Result")
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_child_grades(student="STU-CHILD1")

    def test_child_fees_read_error_raises_not_empty(self):
        self._raise_on_get_all("Fees")
        with self.assertRaises(RuntimeError):
            self.guardian_portal.get_child_fees(student="STU-CHILD1")


if __name__ == "__main__":
    unittest.main()
