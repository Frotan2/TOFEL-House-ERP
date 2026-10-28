"""Owner-approved same-level class transfers ONLY (Owner addendum 2026-10-28).

Unlike tests/teaching/test_class_transfers.py, this file does NOT patch
_transfer_scope_authorized to True: it exercises the real authorization
boundary. The only transfer type that may be requested or executed here is
a same-level "Class" transfer (same program, same branch, same term,
different class). Cross-level, cross-program, branch and time transfers
must stay refused, with the policy switches on, because the switches are
business terms and cannot re-activate a deferred kind.
"""
import json
import unittest

from tests.teaching.operations_site import (
    ACTOR, APPROVER, OperationsSite, PermissionError_, ValidationError,
    load_real, APP)


class SameLevelBase(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site
        self.ops.seed_policy()
        self.ops.seed_class(name="GRP-A", capacity=3,
                            members=["STU-1", "STU-2"])
        self.ops.seed_class(name="GRP-B", capacity=3, members=[],
                            start="2026-09-01", end="2026-12-20")
        self.ops.seed_student("STU-1", student_name="Probe Learner")
        self.ops.seed_student("STU-2")
        self.ops.seed_student("STU-3")
        for student in ("STU-1", "STU-2", "STU-3"):
            self.ops.seed_enrollment(student)
        self.site.add("TH Program Level", name="LVL-GE",
                      native_program="TH-PROG", code="GE",
                      title="General English")
        self.site.add("TH Program Level", name="LVL-OTHER",
                      native_program="TH-OTHER", code="OTHER",
                      title="Other Program")
        self.ops.seed_instructor("INS-1")
        self.ops.seed_room("ROOM-1")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")
        self.site.add("Student Attendance", student="STU-1",
                      course_schedule="CS-OLD", status="Present", docstatus=1)
        self.ops.seed_session(name="CS-OLD", group="GRP-A",
                              date="2026-09-14")
        self.site.add("Assessment Result", student="STU-1", docstatus=1)
        self.site.add("Fees", student="STU-1", docstatus=1)
        self.site.add("TH Teaching Assignment", student_group="GRP-A",
                      instructor="INS-1", skill="Vocabulary")

    def request(self, student="STU-1", source="GRP-A", target="GRP-B",
                day="2026-09-25", key="same-level-request-0001",
                reason="family requested"):
        return self.ops.transfers.request_class_transfer(
            key, student, source, target, reason, day)

    def approve(self, transfer, key="same-level-approve-0001", override=""):
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        return self.ops.transfers.approve_class_transfer(key, transfer,
                                                         override=override)


class ScopeUnitTests(SameLevelBase):
    def test_scope_authorizes_only_a_same_level_class_kind(self):
        transfers = self.ops.transfers
        same = {"program": "TH-PROG"}
        other = {"program": "TH-OTHER"}
        self.assertTrue(transfers._transfer_scope_authorized(same, same, "Class"))
        # Different programs resolve to different level rows: cross-level.
        self.assertFalse(transfers._transfer_scope_authorized(same, other, "Class"))
        # Kind alone defeats scope, even with identical programs.
        for kind in ("Program", "Branch", "Time"):
            self.assertFalse(transfers._transfer_scope_authorized(same, same, kind))
        # No proven facts at all: refused, and the function still ends False.
        self.assertFalse(transfers._transfer_scope_authorized())
        self.assertFalse(transfers._transfer_scope_authorized(None, None, None))
        self.assertTrue(transfers._same_level(same, same))
        self.assertFalse(transfers._same_level(same, other))
        self.assertEqual(transfers._program_level("TH-PROG"), "LVL-GE")
        self.assertEqual(transfers._program_level("TH-OTHER"), "LVL-OTHER")
        self.assertIsNone(transfers._program_level("TH-UNKNOWN"))
        # Identical but unanchored native programs are not level evidence.
        unknown = {"program": "TH-UNKNOWN"}
        self.assertFalse(transfers._transfer_scope_authorized(
            unknown, unknown, "Class"))


class PositiveTransferTests(SameLevelBase):
    def test_a_same_level_class_transfer_executes_with_approval_and_reason(self):
        result = self.request()
        self.assertEqual(result["status"], "Requested")
        self.assertEqual(result["transfer_kind"], "Class")
        stored = self.site.get("TH Class Transfer", result["name"])
        self.assertEqual(stored["reason"], "family requested")
        self.assertEqual(stored["requested_by"], ACTOR)
        executed = self.approve(result["name"])
        self.assertEqual(executed["status"], "Executed")
        self.assertEqual(executed["approved_by"], APPROVER)
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 0), ("STU-2", 1)])
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-1", 1)])

    def test_a_bounded_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.request(reason="")
        with self.assertRaises(ValidationError):
            self.request(reason="x" * 501, key="same-level-request-0002")

    def test_history_is_preserved_unchanged_after_transfer(self):
        before = {
            doctype: [dict(row) for row in self.site.all(doctype)]
            for doctype in ("Student Attendance", "Assessment Result",
                            "Fees", "TH Teaching Assignment",
                            "Program Enrollment")}
        transfer = self.request()["name"]
        self.approve(transfer)
        for doctype, rows in before.items():
            after = [dict(row) for row in self.site.all(doctype)]
            self.assertEqual(after, rows, f"{doctype} was rewritten by the transfer")
        preserved = json.loads(
            self.site.get("TH Class Transfer", transfer)["preserved_json"])
        self.assertEqual(preserved["source_class"], "GRP-A")
        self.assertEqual(preserved["fees"]["count"], 1)
        self.assertEqual(preserved["assessment_results"]["count"], 1)
        fees = self.site.all("Fees")[0]
        self.assertEqual(fees["student"], "STU-1")


class RefusedKindTests(SameLevelBase):
    def test_cross_program_transfer_is_refused_despite_policy_switches(self):
        # seed_policy enables allow_program_transfers; the scope gate, not
        # the switch, decides. The student is enrolled in the other program
        # so eligibility would otherwise pass.
        self.ops.seed_class(name="GRP-P", capacity=2, members=[],
                            program="TH-OTHER", start="2026-09-01")
        self.ops.seed_enrollment("STU-1", program="TH-OTHER")
        with self.assertRaises(ValidationError) as ctx:
            self.request(target="GRP-P")
        self.assertIn("same-level", str(ctx.exception))
        self.assertIn("D5", str(ctx.exception))

    def test_cross_branch_transfer_is_refused(self):
        self.ops.seed_class(name="GRP-BR", capacity=2, members=[],
                            branch="BR-KABUL", start="2026-09-01")
        with self.assertRaises(ValidationError) as ctx:
            self.request(target="GRP-BR")
        self.assertIn("same-level", str(ctx.exception))

    def test_cross_term_time_transfer_is_refused(self):
        self.ops.seed_class(name="GRP-T", capacity=2, members=[],
                            term="Spring", start="2026-09-01")
        self.ops.seed_enrollment("STU-1", term="Spring")
        with self.assertRaises(ValidationError) as ctx:
            self.request(target="GRP-T")
        self.assertIn("same-level", str(ctx.exception))

    def test_scope_is_rechecked_at_approval_on_live_facts(self):
        transfer = self.request()["name"]
        # The target class changes program after the request: eligibility
        # still passes (the student is enrolled in the new program), but
        # the transfer is no longer a same-level Class transfer.
        self.site.get("Student Group", "GRP-B")["program"] = "TH-OTHER"
        self.ops.seed_enrollment("STU-1", program="TH-OTHER")
        with self.assertRaises(ValidationError) as ctx:
            self.approve(transfer)
        self.assertIn("same-level", str(ctx.exception))
        self.assertEqual(self.site.get("TH Class Transfer", transfer)["status"],
                         "Requested")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 1)])
        self.assertEqual(self.ops.roster("GRP-B"), [])


class ApprovalAndCapacityTests(SameLevelBase):
    def test_self_approval_is_refused_from_live_rows(self):
        # The approver files the request themselves, then tries to approve it.
        self.ops.login(APPROVER)
        transfer = self.request(key="same-level-request-self")["name"]
        self.assertEqual(
            self.site.get("TH Class Transfer", transfer)["requested_by"],
            APPROVER)
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.transfers.approve_class_transfer(
                "same-level-approve-self", transfer)
        self.assertIn("cannot be approved by the person who requested it",
                      str(ctx.exception))

    def test_approver_without_the_academic_role_is_refused(self):
        transfer = self.request()["name"]
        # ACTOR is a Teaching Scheduler, not an Academic Manager.
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.transfers.approve_class_transfer(
                "same-level-approve-norole", transfer)
        self.assertIn("Academic Manager", str(ctx.exception))

    def test_a_full_target_is_refused_without_an_override(self):
        self.ops.seed_class(name="GRP-B", capacity=1, members=["STU-2"],
                            start="2026-09-01")
        transfer = self.request(key="same-level-request-full")["name"]
        with self.assertRaises(ValidationError) as ctx:
            self.approve(transfer, key="same-level-approve-full")
        self.assertIn("is full", str(ctx.exception))
        override = self.ops.seed_override("GRP-B", "STU-1")
        executed = self.approve(transfer, key="same-level-approve-override",
                                override=override)
        self.assertEqual(executed["status"], "Executed")
        self.assertEqual(self.ops.roster("GRP-B"),
                         [("STU-2", 1), ("STU-1", 1)])

    def test_duplicate_active_membership_is_refused(self):
        self.site.add("Student Group Student", parent="GRP-B",
                      student="STU-1", active=1, idx=1)
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("already an active member of GRP-B", str(ctx.exception))

    def test_a_timetable_collision_is_refused(self):
        self.ops.seed_session(name="CS-TARGET", group="GRP-B",
                              date="2026-09-29", start="09:00:00",
                              end="10:00:00")
        self.ops.seed_class(name="GRP-C", capacity=2, members=["STU-1"],
                            start="2026-09-01")
        self.ops.seed_session(name="CS-OTHER", group="GRP-C",
                              date="2026-09-29", start="09:30:00",
                              end="10:30:00")
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("collides with session CS-OTHER", str(ctx.exception))


class ReplayConcurrencyAndBranchTests(SameLevelBase):
    def test_second_execution_of_the_same_transfer_is_refused(self):
        transfer = self.request()["name"]
        self.approve(transfer, key="same-level-approve-replay-1")
        # Same request key again, and a fresh key: both hit the status guard.
        for key in ("same-level-approve-replay-1", "same-level-approve-replay-2"):
            with self.subTest(key=key):
                self.ops.login(APPROVER)
                self.site.set_roles(APPROVER, ["Academic Manager"])
                with self.assertRaises(ValidationError) as ctx:
                    self.ops.transfers.approve_class_transfer(key, transfer)
                self.assertIn("is Executed", str(ctx.exception))
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-1", 1)])

    def test_a_second_pending_transfer_for_the_same_student_cannot_execute(self):
        first = self.request(key="same-level-request-first")["name"]
        second = self.request(key="same-level-request-second")["name"]
        self.approve(first, key="same-level-approve-first")
        with self.assertRaises(ValidationError) as ctx:
            self.approve(second, key="same-level-approve-second")
        self.assertIn("not an active member", str(ctx.exception))
        self.assertEqual(self.site.get("TH Class Transfer", second)["status"],
                         "Requested")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 0), ("STU-2", 1)])
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-1", 1)])

    def test_unauthorized_branch_access_is_refused_by_command_scope(self):
        # Production branch scoping runs in api._execute via
        # command_scope.authorize_command_scope, whose REFERENCES include
        # from_group/to_group. Exercise that real module against the stub
        # site: a branch-scoped actor may not touch classes in another branch.
        self.ops.seed_class(name="GRP-BR1", capacity=2, members=["STU-1"],
                            branch="BR-KABUL", start="2026-09-01")
        self.ops.seed_class(name="GRP-BR2", capacity=2, members=[],
                            branch="BR-KABUL", start="2026-09-01")
        self.site.add("User Permission", user=APPROVER, allow="Branch",
                      for_value="BR-HERAT")
        original_get_all = self.ops.frappe.get_all

        def get_all_with_pluck(doctype, filters=None, fields=None,
                               limit_page_length=None, limit=None,
                               order_by=None, pluck=None):
            rows = original_get_all(
                doctype, filters=filters, fields=fields,
                limit_page_length=limit_page_length, limit=limit,
                order_by=order_by)
            return [row.get(pluck) for row in rows] if pluck else rows

        self.ops.frappe.get_all = get_all_with_pluck
        self.ops.frappe.db.get_all = get_all_with_pluck
        command_scope = load_real("toefl_house.command_scope",
                                  APP / "command_scope.py")
        payload = {"from_group": "GRP-BR1", "to_group": "GRP-BR2"}
        with self.assertRaises(PermissionError_) as ctx:
            command_scope.authorize_command_scope(
                "request_class_transfer", payload, APPROVER)
        self.assertIn("permitted branches", str(ctx.exception))
        # The same actor, once permitted for the classes' branch, passes.
        self.site.add("User Permission", user=APPROVER, allow="Branch",
                      for_value="BR-KABUL")
        command_scope.authorize_command_scope(
            "request_class_transfer", payload, APPROVER)


if __name__ == "__main__":
    unittest.main()
