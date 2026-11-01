"""Mission 3 capacity: seat truth, waiting lists, overrides and the read surface.

The REAL ``toefl_house.teaching.capacity`` module runs against the in-memory
site. The acceptance questions are the operational ones:

* does "available" mean something a Reception clerk can act on (capacity minus
  every native roster row minus unexpired offers)?
* can a full class be overfilled only by an approved, single-use override held
  by the policy-configured role — never by a retry, a stale offer or a direct
  roster addition?
* is the waiting list actionable (offer -> admit / expire / withdraw) rather
  than a dead list, and does admission re-prove every fact under lock?
"""
import unittest

from tests.teaching.operations_site import (
    ACTOR, APPROVER, RECEPTION, OperationsSite, PermissionError_,
    ValidationError)


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.ops = OperationsSite()
        self.addCleanup(self.ops.close)
        self.site = self.ops.site

    def _full_class(self, capacity=2, roster=2):
        self.ops.seed_class(name="GRP-FULL", capacity=capacity,
                            members=[f"STU-{index}" for index in range(1, roster + 1)])
        for index in range(1, roster + 2):
            self.ops.seed_student(name=f"STU-{index}")
            self.ops.seed_enrollment(student=f"STU-{index}")
        return "GRP-FULL"

    def _log_in_branch_reception(self, branch="BR-A"):
        """Synthetic Reception requires explicit native Branch permission."""
        for group in self.site.all("Student Group"):
            group["th_branch"] = branch
        self.site.add("User Permission", name=f"RECEPTION-{branch}",
                      user=RECEPTION, allow="Branch", for_value=branch)
        self.ops.login(RECEPTION)

    # --- pure seat arithmetic -------------------------------------------
    def test_available_seats_never_goes_negative(self):
        self.assertEqual(self.ops.capacity.available_seats(20, 12, 3), 5)
        self.assertEqual(self.ops.capacity.available_seats(20, 20, 0), 0)
        self.assertEqual(self.ops.capacity.available_seats(20, 25, 0), 0)
        self.assertEqual(self.ops.capacity.available_seats(0, 0, 0), 0)

    def test_offer_expiry_is_inclusive_of_its_last_day(self):
        self.assertTrue(self.ops.capacity.unexpired("2026-09-22", "2026-09-22"))
        self.assertTrue(self.ops.capacity.unexpired("2026-09-30", "2026-09-22"))
        self.assertFalse(self.ops.capacity.unexpired("2026-09-21", "2026-09-22"))
        self.assertFalse(self.ops.capacity.unexpired("", "2026-09-22"))

    # --- seat facts ------------------------------------------------------
    def test_seat_facts_count_every_native_row_and_live_offer(self):
        group = self._full_class(capacity=3, roster=2)
        self.ops.seed_waiting(group, "STU-3", status="Offered",
                              expires="2026-09-30")
        self.ops.seed_waiting(group, "STU-4", status="Offered",
                              expires="2026-09-01")
        seats = self.ops.capacity.seat_facts(group)
        self.assertEqual(seats["capacity"], 3)
        self.assertEqual(seats["rostered"], 2)
        self.assertEqual(seats["reserved"], 1, "an expired offer holds no seat")
        self.assertEqual(seats["available"], 0)

    def test_deactivated_rows_still_occupy_the_native_seat(self):
        # Native Education counts len(students): a moved-out member keeps the
        # seat. Availability must agree with what a native save would accept.
        group = self._full_class(capacity=2, roster=2)
        self.site.table("Student Group Student")[
            next(name for name, row in self.site.table("Student Group Student").items()
                 if row["student"] == "STU-2")]["active"] = 0
        seats = self.ops.capacity.seat_facts(group)
        self.assertEqual(seats["rostered"], 2)
        self.assertEqual(seats["available"], 0)

    def test_seat_facts_refuse_a_terminal_class(self):
        group = self._full_class()
        self.site.get("Student Group", group)["th_class_status"] = "Completed"
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-3")
        self.assertIn("Completed", str(ctx.exception))

    # --- the seat gate ---------------------------------------------------
    def test_free_seat_returns_no_override(self):
        group = self._full_class(capacity=3, roster=2)
        seat = self.ops.capacity.assert_seat_available(group, "STU-3")
        self.assertEqual(seat["seats"]["available"], 1)
        self.assertIsNone(seat["override"])

    def test_full_class_refuses_with_the_operational_remedies(self):
        group = self._full_class()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-3")
        message = str(ctx.exception)
        self.assertIn("is full", message)
        self.assertIn("waiting list", message)
        self.assertIn("capacity override", message)

    def test_approved_override_admits_and_is_consumed_once(self):
        group = self._full_class()
        override = self.ops.seed_override(group, "STU-3")
        seat = self.ops.capacity.assert_seat_available(group, "STU-3", override)
        self.assertEqual(seat["override"]["override"], override)
        stored = self.site.get("TH Capacity Approval", override)
        self.assertEqual(stored["status"], "Used")
        self.assertTrue(stored["used_on"])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-3", override)
        self.assertIn("Used", str(ctx.exception))

    def test_override_for_another_student_or_class_is_refused(self):
        group = self._full_class()
        other = "GRP-OTHER"
        self.ops.seed_class(name=other, capacity=2,
                            members=["STU-1", "STU-2"])
        override = self.ops.seed_override(group, "STU-4")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-3", override)
        self.assertIn("different student", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(other, "STU-4", override)
        self.assertIn("different class", str(ctx.exception))

    def test_expired_or_revoked_override_is_refused(self):
        group = self._full_class()
        expired = self.ops.seed_override(group, "STU-3", expires="2026-09-01")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-3", expired)
        self.assertIn("expired", str(ctx.exception))
        revoked = self.ops.seed_override(group, "STU-4", status="Revoked")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-4", revoked)
        self.assertIn("Revoked", str(ctx.exception))

    # --- waiting list ----------------------------------------------------
    def test_join_refuses_when_a_seat_is_actually_free(self):
        self.ops.seed_class(name="GRP-OPEN", capacity=5, members=["STU-1"])
        self.ops.seed_student("STU-2")
        self.ops.seed_enrollment("STU-2")
        self.ops.seed_policy()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list(
                "join-open-0001", "GRP-OPEN", "STU-2")
        self.assertIn("free seat", str(ctx.exception))

    def test_join_requires_the_policy_switch_and_an_enrollment(self):
        group = self._full_class()
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list("join-none-0001", group, "STU-3")
        self.assertIn("No active class-operations policy", str(ctx.exception))
        self.ops.seed_policy(waiting_list_enabled=0)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list("join-off-0001", group, "STU-3")
        self.assertIn("waiting list is not enabled", str(ctx.exception))
        # Switch the waiting list back on with a version that is effective
        # today (a future version would not govern yet).
        self.ops.class_operations.set_class_operations_policy_version(
            "join-policy-version-0001", "TH-CLASS-OPS", "2026-09-02",
            "Re-enable the waiting list", self.ops.policy_terms(
                waiting_list_enabled=1))
        self.site.table("Program Enrollment").pop(
            next(name for name, row in self.site.table("Program Enrollment").items()
                 if row["student"] == "STU-3"))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list("join-enrol-0001", group, "STU-3")
        self.assertIn("not enrolled", str(ctx.exception))

    def test_join_records_the_policy_version_and_queue_position(self):
        group = self._full_class()
        self.ops.seed_policy()
        self.ops.seed_student("STU-4")
        self.ops.seed_enrollment("STU-4")
        self.ops.seed_waiting(group, "STU-3", priority=5)
        result = self.ops.capacity.join_waiting_list(
            "join-queue-0001", group, "STU-4", note="wants the morning class")
        self.assertEqual(result["status"], "Waiting")
        self.assertEqual(result["student"], "STU-4")
        self.assertEqual(result["position"], 2, "priority 5 keeps STU-3 ahead")
        self.assertEqual(result["policy_effective_from"], "2026-09-01")
        self.assertEqual(result["seats"]["available"], 0)
        stored = self.site.get("TH Class Waiting List", result["name"])
        self.assertEqual(stored["requested_by"], ACTOR)
        self.assertEqual(stored["synthetic"], 1)

    def test_join_refuses_a_duplicate_open_entry(self):
        group = self._full_class()
        self.ops.seed_policy()
        self.ops.seed_waiting(group, "STU-3")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list("join-dup-0001", group, "STU-3")
        self.assertIn("already has an open waiting-list entry", str(ctx.exception))

    def test_offer_holds_a_seat_for_exactly_the_policy_window(self):
        self.ops.seed_class(name="GRP-OPEN", capacity=3, members=["STU-1"])
        self.ops.seed_student("STU-2")
        self.ops.seed_enrollment("STU-2")
        self.ops.seed_policy()
        self.site.add("Student Group Student", parent="GRP-OPEN", student="STU-9",
                      active=0, idx=2)
        entry = self.ops.seed_waiting("GRP-OPEN", "STU-2")
        result = self.ops.capacity.offer_waiting_list_seat(
            "offer-seat-0001", entry)
        self.assertEqual(result["status"], "Offered")
        self.assertEqual(result["offer_expires_on"], "2026-09-29")
        self.assertEqual(result["seats"]["available"], 0,
                         "the offered seat is now reserved")
        stored = self.site.get("TH Class Waiting List", entry)
        self.assertEqual(stored["offered_by"], ACTOR)
        self.assertEqual(stored["offer_expires_on"], "2026-09-29")

    def test_offer_refuses_a_full_class_and_a_non_waiting_entry(self):
        group = self._full_class()
        self.ops.seed_policy()
        entry = self.ops.seed_waiting(group, "STU-3")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.offer_waiting_list_seat("offer-full-0001", entry)
        self.assertIn("no free seat to offer", str(ctx.exception))
        self.ops.seed_class(name="GRP-OPEN", capacity=3, members=[])
        other = self.ops.seed_waiting("GRP-OPEN", "STU-4", status="Admitted")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.offer_waiting_list_seat("offer-state-0001", other)
        self.assertIn("only a Waiting entry", str(ctx.exception))

    def test_admission_appends_the_native_row_and_releases_the_reservation(self):
        self.ops.seed_class(name="GRP-OPEN", capacity=2, members=["STU-1"])
        self.ops.seed_student("STU-2")
        self.ops.seed_enrollment("STU-2")
        self.ops.seed_policy()
        entry = self.ops.seed_waiting("GRP-OPEN", "STU-2")
        self.ops.capacity.offer_waiting_list_seat("admit-offer-0001", entry)
        result = self.ops.capacity.admit_from_waiting_list(
            "admit-seat-0001", entry)
        self.assertEqual(result["status"], "Admitted")
        self.assertFalse(result["reactivated"])
        self.assertIsNone(result["override"])
        self.assertEqual(result["seats"]["rostered"], 2)
        self.assertEqual(result["seats"]["reserved"], 0)
        self.assertEqual(result["seats"]["available"], 0)
        self.assertEqual(self.ops.roster("GRP-OPEN"),
                         [("STU-1", 1), ("STU-2", 1)])
        self.assertEqual(self.site.get("TH Class Waiting List", entry)["status"],
                         "Admitted")

    def test_admission_refuses_an_expired_offer(self):
        group = self._full_class()
        self.ops.seed_policy()
        entry = self.ops.seed_waiting(group, "STU-3", status="Offered",
                                      expires="2026-09-01")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list("admit-old-0001", entry)
        self.assertIn("expired", str(ctx.exception))

    def test_admission_into_a_full_class_needs_a_matching_override(self):
        group = self._full_class()
        self.ops.seed_policy()
        entry = self.ops.seed_waiting(group, "STU-3")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list("admit-full-0001", entry)
        self.assertIn("is full", str(ctx.exception))
        override = self.ops.seed_override(group, "STU-3")
        result = self.ops.capacity.admit_from_waiting_list(
            "admit-full-0002", entry, override=override)
        self.assertEqual(result["override"]["override"], override)
        self.assertEqual(self.site.get("TH Capacity Approval", override)["status"],
                         "Used")
        self.assertEqual(len(self.ops.roster(group)), 3,
                         "the override admits one student into the full class")

    def test_leave_withdraws_only_open_entries(self):
        group = self._full_class()
        self.ops.seed_policy()
        entry = self.ops.seed_waiting(group, "STU-3")
        result = self.ops.capacity.leave_waiting_list(
            "leave-entry-0001", entry, "family moved")
        self.assertEqual(result["status"], "Withdrawn")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.leave_waiting_list(
                "leave-entry-0002", entry, "again")
        self.assertIn("Withdrawn", str(ctx.exception))

    # --- override commands ----------------------------------------------
    def test_override_commands_require_the_configured_role(self):
        group = self._full_class()
        self.ops.seed_policy()
        with self.assertRaises(PermissionError_) as ctx:
            # The Teaching Scheduler may not grant extra seats.
            self.ops.capacity.create_capacity_override(
                "override-role-0001", group, "STU-3", 1,
                "late admission", "2026-09-30")
        self.assertIn("Academic Manager", str(ctx.exception))
        self.ops.login(APPROVER)
        result = self.ops.capacity.create_capacity_override(
            "override-role-0002", group, "STU-3", 1,
            "late admission", "2026-09-30")
        self.assertEqual(result["status"], "Approved")
        self.assertEqual(result["seats"], 1)
        self.assertEqual(result["expires_on"], "2026-09-30")
        self.assertEqual(result["policy_effective_from"], "2026-09-01")

    def test_override_seats_and_expiry_are_bounded_by_policy(self):
        group = self._full_class()
        self.ops.seed_policy(capacity_override_max_seats=2,
                             capacity_override_expiry_days=7)
        self.ops.login(APPROVER)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-seats-0001", group, "STU-3", 3, "too many", "")
        self.assertIn("between 1 and 2", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-exp-0001", group, "STU-3", 1, "too long",
                "2026-10-30")
        self.assertIn("may not exceed", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-past-0001", group, "STU-3", 1, "past", "2026-09-22")
        self.assertIn("future", str(ctx.exception))

    def test_revocation_is_one_way_and_keeps_the_reason(self):
        group = self._full_class()
        self.ops.seed_policy()
        override = self.ops.seed_override(group, "STU-3")
        self.ops.login(APPROVER)
        result = self.ops.capacity.revoke_capacity_override(
            "revoke-override-0001", override, "student declined")
        self.assertEqual(result["status"], "Revoked")
        stored = self.site.get("TH Capacity Approval", override)
        self.assertEqual(stored["revocation_reason"], "student declined")
        self.assertTrue(stored["revoked_on"])
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.revoke_capacity_override(
                "revoke-override-0002", override, "again")
        self.assertIn("Revoked", str(ctx.exception))

    # --- the read surface Reception and Academic staff use --------------
    def test_availability_is_readable_by_reception_and_refused_to_others(self):
        group = self._full_class(capacity=3, roster=2)
        self.ops.seed_waiting(group, "STU-3")
        self._log_in_branch_reception()
        report = self.ops.capacity.class_availability()
        self.assertEqual(report["as_of"], "2026-09-22")
        row = next(item for item in report["classes"]
                   if item["student_group"] == group)
        self.assertEqual((row["capacity"], row["rostered"], row["reserved"],
                          row["available"], row["waiting"]), (3, 2, 0, 1, 1))
        self.assertFalse(row["full"])
        self.assertIn("capacity minus every roster row", report["definitions"]["available"])
        self.ops.login("finance.officer@example.test")
        self.site.set_roles("finance.officer@example.test", ["Finance Officer"])
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.capacity.class_availability()
        self.assertIn("Reception and Academic staff", str(ctx.exception))

    def test_intake_projection_shows_unmet_demand_and_the_next_class_end(self):
        self.ops.seed_class(name="GRP-A", capacity=2, members=["STU-1", "STU-2"],
                            end="2026-12-20")
        self.ops.seed_class(name="GRP-B", capacity=4, members=["STU-1"],
                            end="2026-11-15")
        self.ops.seed_student("STU-3")
        for name in ("STU-3", "STU-4"):
            self.ops.seed_waiting("GRP-A", name)
        self._log_in_branch_reception()
        report = self.ops.capacity.class_availability(program="TH-PROG",
                                                       academic_year="2026-27")
        intake = report["intake"][0]
        self.assertEqual(intake["program"], "TH-PROG")
        self.assertEqual(intake["classes"], 2)
        self.assertEqual(intake["seats_available"], 3, "0 in GRP-A, 3 in GRP-B")
        self.assertEqual(intake["waiting"], 2)
        self.assertEqual(intake["next_class_end"], "2026-11-15")
        self.assertEqual(intake["projected_unmet_demand"], 0)

    def test_waiting_board_names_the_next_action_for_each_entry(self):
        self.ops.seed_class(name="GRP-OPEN", capacity=3, members=["STU-1"])
        self.ops.seed_student("STU-2")
        self.ops.seed_waiting("GRP-OPEN", "STU-2")
        self.ops.seed_waiting("GRP-OPEN", "STU-3", status="Offered",
                              expires="2026-09-25")
        self.ops.seed_waiting("GRP-OPEN", "STU-4", status="Offered",
                              expires="2026-09-01")
        self._log_in_branch_reception()
        board = self.ops.capacity.waiting_list_board("GRP-OPEN")
        by_student = {row["student"]: row for row in board["entries"]}
        self.assertEqual(by_student["STU-2"]["next_command"],
                         "offer_waiting_list_seat")
        self.assertIn("seat is free", by_student["STU-2"]["next"])
        self.assertEqual(by_student["STU-3"]["next_command"],
                         "admit_from_waiting_list")
        self.assertEqual(by_student["STU-4"]["next_command"],
                         "offer_waiting_list_seat")
        self.assertIn("expired", by_student["STU-4"]["next"])
        self.assertEqual(by_student["STU-2"]["next_role"], "Teaching Scheduler")


if __name__ == "__main__":
    unittest.main()
