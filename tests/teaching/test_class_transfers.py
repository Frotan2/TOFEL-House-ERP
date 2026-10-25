"""Mission 3 controlled transfers: request, independent approval, atomic move.

The workflow must prove eligibility twice (at request and again under lock at
approval), never let the requester approve their own request, pin the policy
version the decision is judged against, refuse a full target without a
matching override, and move the roster while leaving attendance, assessment,
finance and instructor records exactly where they happened.
"""
import json
import unittest

from tests.teaching.operations_site import (
    ACTOR, APPROVER, OperationsSite, PermissionError_, ValidationError)


class TransferTestBase(unittest.TestCase):
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
        self.ops.seed_instructor("INS-1")
        self.ops.seed_room("ROOM-1")
        self.site.add("Course", name="ENG-101", course_name="English")
        self.site.add("Program Course", parent="TH-PROG", course="ENG-101")
        # History that must survive the move.
        self.site.add("Student Attendance", student="STU-1",
                      course_schedule="CS-OLD", status="Present", docstatus=1)
        self.ops.seed_session(name="CS-OLD", group="GRP-A",
                              date="2026-09-14")
        self.site.add("Assessment Result", student="STU-1", docstatus=1)
        self.site.add("Fees", student="STU-1", docstatus=1)
        self.site.add("TH Teaching Assignment", student_group="GRP-A",
                      instructor="INS-1", skill="Vocabulary")

    def request(self, student="STU-1", source="GRP-A", target="GRP-B",
                day="2026-09-25", key="transfer-request-0001"):
        return self.ops.transfers.request_class_transfer(
            key, student, source, target, "family requested", day)


class ClassificationTests(TransferTestBase):
    def test_transfer_kind_names_what_actually_changes(self):
        base = {"program": "TH-PROG", "th_branch": "BR-A",
                "academic_term": "Fall"}
        self.assertEqual(self.ops.transfers.classify(
            base, dict(base, program="TH-OTHER")), "Program")
        self.assertEqual(self.ops.transfers.classify(
            base, dict(base, th_branch="BR-B")), "Branch")
        self.assertEqual(self.ops.transfers.classify(
            base, dict(base, academic_term="Spring")), "Time")
        self.assertEqual(self.ops.transfers.classify(base, dict(base)), "Class")


class RequestTests(TransferTestBase):
    def test_a_request_pins_the_policy_and_snapshots_preserved_evidence(self):
        result = self.request()
        self.assertEqual(result["status"], "Requested")
        self.assertEqual(result["transfer_kind"], "Class")
        self.assertEqual(result["pinned_effective_from"], "2026-09-01")
        self.assertEqual(result["approver_role"], "Academic Manager")
        self.assertEqual(result["target_seats"]["available"], 3)
        self.assertFalse(result["target_requires_override"])
        self.assertEqual(result["preserved"]["attendance_in_source_class"], 1)
        self.assertEqual(result["preserved"]["assessment_results"], 1)
        self.assertEqual(result["preserved"]["fees"], 1)
        stored = self.site.get("TH Class Transfer", result["name"])
        evidence = json.loads(stored["eligibility_json"])
        self.assertEqual(evidence["kind"], "Class")
        self.assertIn("no target timetable collision", evidence["checks"])
        preserved = json.loads(stored["preserved_json"])
        self.assertEqual(preserved["instructor_assignments"]["count"], 1)
        self.assertEqual(preserved["program_enrollments"][0]["program"],
                         "TH-PROG")
        self.assertEqual(stored["requested_by"], ACTOR)

    def test_a_request_is_refused_when_transfers_are_switched_off(self):
        self.ops.append_policy("2026-09-02", allow_transfers=0,
                               allow_program_transfers=0,
                               allow_branch_transfers=0)
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("Transfers are not permitted", str(ctx.exception))

    def test_program_and_branch_transfers_need_their_own_switches(self):
        self.ops.seed_class(name="GRP-P", capacity=2, members=[],
                            program="TH-OTHER", start="2026-09-01")
        self.ops.seed_enrollment("STU-1", program="TH-OTHER")
        self.ops.append_policy("2026-09-02", allow_program_transfers=0,
                               allow_branch_transfers=0)
        with self.assertRaises(ValidationError) as ctx:
            self.request(target="GRP-P")
        self.assertIn("between programs", str(ctx.exception))
        self.ops.seed_class(name="GRP-BR", capacity=2, members=[],
                            branch="BR-KABUL", start="2026-09-01")
        with self.assertRaises(ValidationError) as ctx:
            self.request(target="GRP-BR")
        self.assertIn("between branches", str(ctx.exception))

    def test_source_and_target_membership_facts_are_proven(self):
        with self.assertRaises(ValidationError) as ctx:
            self.request(source="GRP-A", target="GRP-A")
        self.assertIn("must differ", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.request(student="STU-9")
        self.assertIn("Unknown student", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.request(student="STU-3")
        self.assertIn("not an active member", str(ctx.exception))
        self.site.add("Student Group Student", parent="GRP-B",
                      student="STU-1", active=1, idx=1)
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("already an active member of GRP-B", str(ctx.exception))

    def test_terminal_classes_cannot_start_or_receive_a_transfer(self):
        self.site.get("Student Group", "GRP-A")["th_class_status"] = "Completed"
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("no transfer can start there", str(ctx.exception))
        self.site.get("Student Group", "GRP-A")["th_class_status"] = "Active"
        self.site.get("Student Group", "GRP-B")["th_class_status"] = "Cancelled"
        with self.assertRaises(ValidationError) as ctx:
            self.request(key="transfer-request-0002")
        self.assertIn("no transfer can land there", str(ctx.exception))

    def test_the_transfer_window_is_bounded_from_the_target_start(self):
        self.site.get("Student Group", "GRP-B")["th_class_start_date"] = \
            "2026-07-01"
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("on or before 2026-08-30", str(ctx.exception))

    def test_a_past_effective_date_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.request(day="2026-09-01")
        self.assertIn("cannot take effect in the past", str(ctx.exception))

    def test_the_target_intake_enrollment_is_required(self):
        self.site.table("Program Enrollment").pop(
            next(name for name, row in self.site.table("Program Enrollment").items()
                 if row["student"] == "STU-1"))
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("is not enrolled", str(ctx.exception))

    def test_an_active_student_suspension_blocks_the_transfer(self):
        self.site.add("TH Class Suspension", scope="Student",
                      student_group="GRP-A", student="STU-1",
                      status="Active", from_date="2026-09-22",
                      until_date="2026-09-30", reason="travelling")
        with self.assertRaises(ValidationError) as ctx:
            self.request()
        self.assertIn("is suspended in GRP-A", str(ctx.exception))

    def test_a_timetable_collision_blocks_the_transfer(self):
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


class ApprovalTests(TransferTestBase):
    def test_approval_requires_the_pinned_role_and_a_different_person(self):
        transfer = self.request()["name"]
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0001", transfer)
        self.assertIn("Academic Manager", str(ctx.exception))
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        result = self.ops.transfers.approve_class_transfer(
            "transfer-approve-0002", transfer)
        self.assertEqual(result["status"], "Executed")
        stored = self.site.get("TH Class Transfer", transfer)
        self.assertEqual(stored["approved_by"], APPROVER)
        self.assertTrue(stored["executed_on"])

    def test_a_closed_roster_window_blocks_execution_and_touches_no_roster(self):
        # Executing a transfer is a roster change: the same owner window that
        # governs add/move/remove governs it, so a transfer can never be used
        # to slip a roster edit past a closed policy.
        transfer = self.request()["name"]
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        before = (self.ops.roster("GRP-A"), self.ops.roster("GRP-B"))
        self.site.cutoff = "2026-01-01"
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-closed-01", transfer)
        self.assertIn("Roster changes closed", str(ctx.exception))
        self.assertEqual((self.ops.roster("GRP-A"), self.ops.roster("GRP-B")),
                         before)
        self.assertEqual(self.site.get("TH Class Transfer", transfer)["status"],
                         "Requested")
        self.ops.login(APPROVER)
        self.site.cutoff = "2026-12-31"
        executed = self.ops.transfers.approve_class_transfer(
            "transfer-approve-open-01", transfer)
        self.assertEqual(executed["status"], "Executed")

    def test_the_requester_cannot_approve_their_own_transfer(self):
        transfer = self.request()["name"]
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        self.site.get("TH Class Transfer", transfer)["requested_by"] = APPROVER
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0003", transfer)
        self.assertIn("cannot be approved by the person who requested it",
                      str(ctx.exception))

    def test_a_new_policy_version_invalidates_the_pinned_request(self):
        transfer = self.request()["name"]
        self.ops.append_policy("2026-09-02", transfer_window_days=90)
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0004", transfer)
        self.assertIn("pinned class-operations policy version", str(ctx.exception))

    def test_approval_moves_the_roster_and_leaves_history_untouched(self):
        transfer = self.request()["name"]
        history_before = {
            "attendance": len(self.site.all("Student Attendance")),
            "assessments": len(self.site.all("Assessment Result")),
            "fees": len(self.site.all("Fees")),
            "assignments": len(self.site.all("TH Teaching Assignment")),
            "enrollments": len(self.site.all("Program Enrollment")),
        }
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        result = self.ops.transfers.approve_class_transfer(
            "transfer-approve-0005", transfer)
        self.assertEqual(result["from_group"], "GRP-A")
        self.assertEqual(result["to_group"], "GRP-B")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 0), ("STU-2", 1)],
                         "the source row is kept and deactivated")
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-1", 1)])
        self.assertEqual(
            {key: len(self.site.all(doctype)) for key, doctype in {
                "attendance": "Student Attendance",
                "assessments": "Assessment Result", "fees": "Fees",
                "assignments": "TH Teaching Assignment",
                "enrollments": "Program Enrollment"}.items()},
            history_before)
        self.assertEqual(result["preserved"]["attendance_in_source_class"][
                             "count_total_for_student"], 1)

    def test_approving_twice_or_after_a_denial_is_refused(self):
        transfer = self.request()["name"]
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        self.ops.transfers.approve_class_transfer("transfer-approve-0006",
                                                  transfer)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0007", transfer)
        self.assertIn("is Executed", str(ctx.exception))

    def test_a_full_target_needs_a_matching_override(self):
        self.ops.seed_class(name="GRP-B", capacity=1, members=["STU-2"],
                            start="2026-09-01")
        self.site.set_roles(APPROVER, ["Academic Manager"])
        transfer = self.request(key="transfer-request-0003")["name"]
        self.assertTrue(self.site.get("TH Class Transfer", transfer)[
            "eligibility_json"])
        self.ops.login(APPROVER)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0008", transfer)
        self.assertIn("is full", str(ctx.exception))
        override = self.ops.seed_override("GRP-B", "STU-1")
        result = self.ops.transfers.approve_class_transfer(
            "transfer-approve-0009", transfer, override=override)
        self.assertEqual(result["override"]["override"], override)
        self.assertEqual(self.site.get("TH Capacity Approval",
                                       override)["status"], "Used")
        self.assertEqual(self.ops.roster("GRP-B"), [("STU-2", 1), ("STU-1", 1)])

    def test_approval_re_proves_eligibility_under_lock(self):
        transfer = self.request()["name"]
        # The world moves between request and decision.
        for row in self.site.all("Student Group Student"):
            if row["student"] == "STU-1" and row["parent"] == "GRP-A":
                row["active"] = 0
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0010", transfer)
        self.assertIn("not an active member", str(ctx.exception))


class DecisionTests(TransferTestBase):
    def test_denial_keeps_the_student_in_the_source_class(self):
        transfer = self.request()["name"]
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        result = self.ops.transfers.deny_class_transfer(
            "transfer-deny-0001", transfer, "no room in the target cohort")
        self.assertEqual(result["status"], "Denied")
        stored = self.site.get("TH Class Transfer", transfer)
        self.assertEqual(stored["denial_reason"], "no room in the target cohort")
        self.assertEqual(self.ops.roster("GRP-A"),
                         [("STU-1", 1), ("STU-2", 1)])
        self.assertEqual(self.ops.roster("GRP-B"), [])

    def test_denial_requires_the_approver_role(self):
        transfer = self.request()["name"]
        with self.assertRaises(PermissionError_):
            self.ops.transfers.deny_class_transfer(
                "transfer-deny-0002", transfer, "not allowed")

    def test_only_the_requester_can_cancel_a_pending_request(self):
        transfer = self.request()["name"]
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.transfers.cancel_class_transfer(
                "transfer-cancel-0001", transfer, "changed my mind")
        self.assertIn("Only the requester", str(ctx.exception))
        self.ops.login(ACTOR)
        result = self.ops.transfers.cancel_class_transfer(
            "transfer-cancel-0002", transfer, "family withdrew the request")
        self.assertEqual(result["status"], "Cancelled")
        self.assertEqual(self.ops.roster("GRP-B"), [])

    def test_a_cancelled_request_cannot_be_approved(self):
        transfer = self.request()["name"]
        self.ops.transfers.cancel_class_transfer(
            "transfer-cancel-0003", transfer, "family changed their mind")
        self.ops.login(APPROVER)
        self.site.set_roles(APPROVER, ["Academic Manager"])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.transfers.approve_class_transfer(
                "transfer-approve-0011", transfer)
        self.assertIn("is Cancelled", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
