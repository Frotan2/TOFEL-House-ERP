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

    def test_more_than_maximum_live_offers_are_counted_exactly(self):
        # A finite get_all limit must never undercount offers and let staff
        # reserve a seat that the existing live offers have already held.
        group = self._full_class(capacity=260, roster=0)
        for i in range(self.ops.capacity.MAX_ENTRIES):
            self.ops.seed_waiting(group, f"WAIT-TEST-{i}",
                                  status="Offered", expires="2026-09-30")
        self.assertEqual(self.ops.capacity.seat_facts(group)["reserved"],
                         self.ops.capacity.MAX_ENTRIES)
        overflow = self.ops.seed_waiting(group, "WAIT-OVERFLOW",
                                         status="Offered", expires="2026-09-30")
        seats = self.ops.capacity.seat_facts(group)
        self.assertEqual(seats["reserved"], self.ops.capacity.MAX_ENTRIES + 1)
        self.assertEqual(seats["available"], 260 - (self.ops.capacity.MAX_ENTRIES + 1))
        # A held seat for the exact entry being admitted is counted once,
        # not again as a competing reservation.
        self.assertEqual(self.ops.capacity.reserved_offers(
            group, exclude_entry=overflow), self.ops.capacity.MAX_ENTRIES)

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
    def test_stale_active_class_end_date_cannot_offer_new_seats(self):
        group = self._full_class(capacity=3, roster=1)
        self.site.get("Student Group", group)["th_class_end_date"] = "2026-09-21"
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.assert_seat_available(group, "STU-2")
        self.assertIn("no current class end date", str(ctx.exception))
        self.ops.login(RECEPTION)
        self._log_in_branch_reception()
        self.assertEqual(self.ops.capacity.class_availability(
            student_group=group)["classes"], [])

    def test_missing_class_end_date_never_becomes_an_open_seat(self):
        group = self._full_class(capacity=3, roster=1)
        self.site.get("Student Group", group)["th_class_end_date"] = None
        with self.assertRaises(ValidationError):
            self.ops.capacity.assert_seat_available(group, "STU-2")

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

    def test_full_waiting_queue_refuses_new_join_before_creation(self):
        group = self._full_class()
        self.ops.seed_policy()
        for i in range(self.ops.capacity.MAX_ENTRIES):
            self.ops.seed_waiting(group, f"WAIT-TEST-{i}", status="Waiting")
        before = len(self.site.all("TH Class Waiting List"))
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.join_waiting_list(
                "join-over-cap-0001", group, "STU-3")
        self.assertIn("reached the complete read limit", str(ctx.exception))
        self.assertEqual(len(self.site.all("TH Class Waiting List")), before)

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

    def test_offer_enforces_priority_and_time_order_at_server(self):
        self.ops.seed_class(name="GRP-QUEUE", capacity=3, members=["STU-1"])
        for student in ("STU-2", "STU-3", "STU-4"):
            self.ops.seed_student(student)
            self.ops.seed_enrollment(student)
        self.ops.seed_policy()
        earlier = self.ops.seed_waiting(
            "GRP-QUEUE", "STU-2", priority=0,
            requested_on="2026-09-20 08:00:00")
        high = self.ops.seed_waiting(
            "GRP-QUEUE", "STU-3", priority=10,
            requested_on="2026-09-21 08:00:00")
        later = self.ops.seed_waiting(
            "GRP-QUEUE", "STU-4", priority=0,
            requested_on="2026-09-21 09:00:00")
        self.assertEqual(self.ops.capacity._queue_position(high, {
            "student_group": "GRP-QUEUE"}), 1)
        self.assertEqual(self.ops.capacity._queue_position(earlier, {
            "student_group": "GRP-QUEUE"}), 2)
        self.assertEqual(self.ops.capacity._queue_position(later, {
            "student_group": "GRP-QUEUE"}), 3)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.offer_waiting_list_seat(
                "queue-skip-0001", earlier)
        self.assertIn("Earlier waiting-list entries have priority", str(ctx.exception))
        self.assertEqual(self.site.get("TH Class Waiting List", earlier)["status"],
                         "Waiting")
        result = self.ops.capacity.offer_waiting_list_seat(
            "queue-first-0001", high)
        self.assertEqual(result["status"], "Offered")
        result = self.ops.capacity.offer_waiting_list_seat(
            "queue-second-0001", earlier)
        self.assertEqual(result["status"], "Offered")
        with self.assertRaises(ValidationError):
            self.ops.capacity.offer_waiting_list_seat("queue-full-0001", later)

    def test_offer_refuses_the_fifth_entry_ahead_of_the_first(self):
        # C-06 trace: entry #5 must never be offered ahead of entry #1.
        self.ops.seed_class(name="GRP-QUEUE5", capacity=6, members=["STU-1"])
        for index in range(2, 7):
            student = f"STU-{index}"
            self.ops.seed_student(student)
            self.ops.seed_enrollment(student)
        self.ops.seed_policy()
        entries = [
            self.ops.seed_waiting(
                "GRP-QUEUE5", f"STU-{index}", priority=0,
                requested_on=f"2026-09-20 0{index}:00:00")
            for index in range(2, 7)
        ]
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.offer_waiting_list_seat(
                "queue-fifth-0001", entries[4])
        self.assertIn("Earlier waiting-list entries have priority", str(ctx.exception))
        self.assertEqual(self.site.get(
            "TH Class Waiting List", entries[4])["status"], "Waiting")
        result = self.ops.capacity.offer_waiting_list_seat(
            "queue-first-0001", entries[0])
        self.assertEqual(result["status"], "Offered")

    def test_waiting_board_offers_only_the_first_waiting_student(self):
        self.ops.seed_class(name="GRP-QUEUE", capacity=3, members=["STU-1"])
        high = self.ops.seed_waiting(
            "GRP-QUEUE", "STU-2", priority=8,
            requested_on="2026-09-21 08:00:00")
        lower = self.ops.seed_waiting(
            "GRP-QUEUE", "STU-3", priority=0,
            requested_on="2026-09-20 08:00:00")
        self._log_in_branch_reception()
        board = self.ops.capacity.waiting_list_board(student_group="GRP-QUEUE")
        by_id = {row["entry"]: row for row in board["entries"]}
        self.assertEqual(by_id[high]["position"], 1)
        self.assertEqual(by_id[high]["next_command"], "offer_waiting_list_seat")
        self.assertEqual(by_id[lower]["position"], 2)
        self.assertEqual(by_id[lower]["next_command"], "")
        self.assertIn("earlier waiting entries", by_id[lower]["next"])

    def test_offer_expiry_cannot_outlive_the_class(self):
        self.ops.seed_class(name="GRP-SOON", capacity=3,
                            members=["STU-1"], end="2026-09-24")
        self.ops.seed_student("STU-2")
        self.ops.seed_enrollment("STU-2")
        self.ops.seed_policy()
        entry = self.ops.seed_waiting("GRP-SOON", "STU-2")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.offer_waiting_list_seat(
                "offer-beyond-class-0001", entry, "2026-09-29")
        self.assertIn("cannot extend beyond the class end date", str(ctx.exception))
        self.assertEqual(self.site.get("TH Class Waiting List", entry)["status"],
                         "Waiting")
        result = self.ops.capacity.offer_waiting_list_seat(
            "offer-clipped-class-0001", entry)
        self.assertEqual(result["status"], "Offered")
        self.assertEqual(result["offer_expires_on"], "2026-09-24")

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

    def test_direct_admission_from_waiting_cannot_skip_priority(self):
        self.ops.seed_class(name="GRP-DIRECT", capacity=3, members=["STU-1"])
        for student in ("STU-2", "STU-3"):
            self.ops.seed_student(student)
            self.ops.seed_enrollment(student)
        self.ops.seed_policy()
        first = self.ops.seed_waiting(
            "GRP-DIRECT", "STU-2", priority=9,
            requested_on="2026-09-21 09:00:00")
        later = self.ops.seed_waiting(
            "GRP-DIRECT", "STU-3", priority=0,
            requested_on="2026-09-20 09:00:00")
        # A Waiting entry holds no offer: even the head of the queue cannot
        # be admitted silently — offer the seat first, or record why not.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list("skip-direct-0001", first)
        self.assertIn("holds no seat offer", str(ctx.exception))
        self.assertEqual(self.ops.roster("GRP-DIRECT"), [("STU-1", 1)])
        self.assertEqual(self.site.get("TH Class Waiting List", first)["status"],
                         "Waiting")
        # A reason does not buy a queue jump: the later entry is still
        # behind the first.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list(
                "skip-direct-0002", later,
                queue_jump_reason="head of queue is absent today")
        self.assertIn("Earlier waiting-list entries have priority", str(ctx.exception))
        self.assertEqual(self.ops.roster("GRP-DIRECT"), [("STU-1", 1)])
        self.assertEqual(self.site.get("TH Class Waiting List", later)["status"],
                         "Waiting")
        result = self.ops.capacity.admit_from_waiting_list(
            "first-direct-0001", first,
            queue_jump_reason="student present at reception; seat offered in person")
        self.assertEqual(result["status"], "Admitted")
        self.assertEqual(result["queue_jump_reason"],
                         "student present at reception; seat offered in person")
        self.assertEqual(self.ops.roster("GRP-DIRECT"),
                         [("STU-1", 1), ("STU-2", 1)])
        result = self.ops.capacity.admit_from_waiting_list(
            "next-direct-0001", later,
            queue_jump_reason="student present at reception; seat offered in person")
        self.assertEqual(result["status"], "Admitted")

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
        # No seat exists to offer in a full class, so the admission needs
        # the audited reason as well as the override.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.admit_from_waiting_list(
                "admit-full-0001", entry,
                queue_jump_reason="no seat exists to offer; override admission")
        self.assertIn("is full", str(ctx.exception))
        override = self.ops.seed_override(group, "STU-3")
        result = self.ops.capacity.admit_from_waiting_list(
            "admit-full-0002", entry, override=override,
            queue_jump_reason="no seat exists to offer; approved override "
                              "admits the queued learner")
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

    def test_override_creation_requires_enrollment_and_no_live_duplicate(self):
        group = self._full_class()
        self.ops.seed_policy()
        self.ops.login(APPROVER)
        # No enrollment for the intake: there is no override to grant.
        self.ops.seed_student("STU-9")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-noenrol-0001", group, "STU-9", 1,
                "no enrollment", "2026-09-30")
        self.assertIn("not enrolled", str(ctx.exception))
        # An active member already holds a seat: nothing to override.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-member-0001", group, "STU-1", 1,
                "already seated", "2026-09-30")
        self.assertIn("already an active member", str(ctx.exception))
        # One live override per student per class.
        result = self.ops.capacity.create_capacity_override(
            "override-first-0001", group, "STU-3", 1,
            "late admission", "2026-09-30")
        self.assertEqual(result["status"], "Approved")
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-dup-0001", group, "STU-3", 1,
                "second grant", "2026-09-30")
        self.assertIn("already holds a live capacity override", str(ctx.exception))
        # An expired Approved row is not live and does not block a grant.
        self.ops.seed_student("STU-4")
        self.ops.seed_enrollment("STU-4")
        self.ops.seed_override(group, "STU-4", expires="2026-09-01")
        result = self.ops.capacity.create_capacity_override(
            "override-after-expiry-0001", group, "STU-4", 1,
            "late admission", "2026-09-30")
        self.assertEqual(result["status"], "Approved")

    def test_override_grants_exactly_one_seat(self):
        group = self._full_class()
        self.ops.seed_policy(capacity_override_max_seats=2)
        self.ops.login(APPROVER)
        # Two seats are within the policy bound, but an override names one
        # student: the second seat could never be used.
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-two-seats-0001", group, "STU-3", 2,
                "two seats", "2026-09-30")
        self.assertIn("exactly one seat", str(ctx.exception))
        result = self.ops.capacity.create_capacity_override(
            "override-one-seat-0001", group, "STU-3", 1,
            "one seat", "2026-09-30")
        self.assertEqual(result["status"], "Approved")
        self.assertEqual(result["seats"], 1)

    def test_live_override_hidden_behind_two_expired_rows_still_blocks(self):
        # C-07 (Area B re-check): _live_override_exists used to read at
        # most two Approved rows with no ordering, so a live override
        # filed behind two expired ones was missed and a duplicate grant
        # was allowed. The liveness test is now one exact database count.
        group = self._full_class()
        self.ops.seed_policy()
        self.ops.seed_override(group, "STU-3", expires="2026-09-01")
        self.ops.seed_override(group, "STU-3", expires="2026-09-02")
        live = self.ops.seed_override(group, "STU-3", expires="2026-10-01")
        self.assertEqual(self.site.get("TH Capacity Approval", live)["status"],
                         "Approved")
        self.ops.login(APPROVER)
        with self.assertRaises(ValidationError) as ctx:
            self.ops.capacity.create_capacity_override(
                "override-hidden-0001", group, "STU-3", 1,
                "second grant", "2026-09-30")
        self.assertIn("already holds a live capacity override", str(ctx.exception))

    def test_create_locks_the_class_row_before_checking_live_overrides(self):
        # C-07 concurrency (Area B): the live-override check and the insert
        # serialize per class only because the class row is locked first and
        # held for the one request transaction. The stub harness cannot run
        # two threads against a real row lock, so this pins the lock itself:
        # the SELECT ... FOR UPDATE on the class must fire during creation.
        group = self._full_class()
        self.ops.seed_policy()
        self.ops.login(APPROVER)
        before = len(self.site.sql_log)
        self.ops.capacity.create_capacity_override(
            "override-lock-0001", group, "STU-3", 1,
            "late admission", "2026-09-30")
        locks = [entry for entry in self.site.sql_log[before:]
                 if "for update" in entry[0] and "Student Group" in entry[0]]
        self.assertTrue(
            locks, "create must lock the class row before the live-override check")

    def test_legacy_multiseat_override_remedy_is_revoke_and_reissue(self):
        # C-07 legacy remedy (Area B): a pre-rule 5-seat Approved override
        # is still consumable-whole, so the remedy is revoke + re-issue as
        # a single seat — verified here end to end, not just documented.
        group = self._full_class()
        self.ops.seed_policy()
        legacy = self.ops.seed_override(group, "STU-3", seats=5)
        self.assertEqual(int(self.site.get(
            "TH Capacity Approval", legacy)["seats"]), 5)
        self.ops.login(APPROVER)
        revoked = self.ops.capacity.revoke_capacity_override(
            "revoke-legacy-0001", legacy,
            "superseded by single-seat override")
        self.assertEqual(revoked["status"], "Revoked")
        fresh = self.ops.capacity.create_capacity_override(
            "override-reissue-0001", group, "STU-3", 1,
            "replaces revoked 5-seat grant", "2026-09-30")
        self.assertEqual(fresh["status"], "Approved")
        self.assertEqual(fresh["seats"], 1)
        seat = self.ops.capacity.assert_seat_available(group, "STU-3", fresh["name"])
        self.assertEqual(seat["override"]["seats"], 1)
        self.assertEqual(self.site.get(
            "TH Capacity Approval", fresh["name"])["status"], "Used")

    def test_queue_jump_reason_is_recorded_on_the_waiting_entry(self):
        # C-06 (Area B re-check): the reason used to live only in the
        # returned result and the operation receipt. It is now also written
        # on the waiting-list entry itself, so the queue record shows why
        # the learner was admitted without an offer.
        self.ops.seed_class(name="GRP-OPEN", capacity=3, members=["STU-1", "STU-2"])
        for index in range(1, 4):
            self.ops.seed_student(name=f"STU-{index}")
            self.ops.seed_enrollment(student=f"STU-{index}")
        self.ops.seed_policy()
        entry = self.ops.seed_waiting("GRP-OPEN", "STU-3")
        result = self.ops.capacity.admit_from_waiting_list(
            "admit-note-0001", entry,
            queue_jump_reason="student present at reception; seat offered in person")
        self.assertEqual(result["queue_jump_reason"],
                         "student present at reception; seat offered in person")
        stored = self.site.get("TH Class Waiting List", entry)
        self.assertEqual(stored["status"], "Admitted")
        self.assertIn("student present at reception", stored.get("note") or "")

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
        self.assertEqual(row["walk_in_available"], 0)
        self.assertTrue(row["queue_has_priority"])
        self.assertFalse(row["full"])
        self.assertIn("capacity minus every roster row", report["definitions"]["available"])
        self.assertIn("not a walk-in promise", report["definitions"]["available"])
        self.ops.login("finance.officer@example.test")
        self.site.set_roles("finance.officer@example.test", ["Finance Officer"])
        with self.assertRaises(PermissionError_) as ctx:
            self.ops.capacity.class_availability()
        self.assertIn("Reception and Academic staff", str(ctx.exception))

    def test_held_offer_does_not_block_other_free_seats_without_waiting_priority(self):
        self.ops.seed_class(name="GRP-OPEN", capacity=4, members=["STU-1"])
        self.ops.seed_waiting("GRP-OPEN", "STU-OFFERED",
                              status="Offered", expires="2026-09-30")
        self._log_in_branch_reception()
        record = self.ops.capacity.class_availability(
            student_group="GRP-OPEN")["classes"][0]
        self.assertEqual(record["available"], 2)
        self.assertEqual(record["walk_in_available"], 2)
        self.assertFalse(record["queue_has_priority"])

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
        self.assertEqual(intake["waiting_to_offer"], 2)
        self.assertEqual(intake["walk_in_seats_available"], 3)
        self.assertEqual(intake["projected_unmet_demand"], 2,
                         "three spare GRP-B seats cannot satisfy GRP-A's "
                         "two waiting learners without a separate approved move")
        by_class = {row["student_group"]: row for row in report["classes"]}
        self.assertEqual(by_class["GRP-A"]["projected_unmet_demand"], 2)
        self.assertEqual(by_class["GRP-B"]["projected_unmet_demand"], 0)

    def test_reserved_offered_seat_is_not_double_counted_as_unmet_demand(self):
        self.ops.seed_class(name="GRP-INTAKE", capacity=3,
                            members=["STU-1", "STU-2"])
        self.ops.seed_waiting("GRP-INTAKE", "STU-OFFER",
                              status="Offered", expires="2026-09-30")
        self._log_in_branch_reception()
        report = self.ops.capacity.class_availability(
            student_group="GRP-INTAKE")
        row = report["classes"][0]
        self.assertEqual(row["waiting"], 1)
        self.assertEqual(row["waiting_to_offer"], 0)
        self.assertEqual(row["reserved"], 1)
        self.assertEqual(row["available"], 0)
        self.assertEqual(row["walk_in_available"], 0)
        intake = report["intake"][0]
        self.assertEqual(intake["waiting"], 1)
        self.assertEqual(intake["waiting_to_offer"], 0)
        self.assertEqual(intake["projected_unmet_demand"], 0)
        self.assertEqual(intake["walk_in_seats_available"], 0)

        self.ops.seed_waiting("GRP-INTAKE", "STU-UNMET", status="Waiting")
        report = self.ops.capacity.class_availability(
            student_group="GRP-INTAKE")
        row = report["classes"][0]
        self.assertEqual(row["waiting"], 2)
        self.assertEqual(row["waiting_to_offer"], 1)
        self.assertEqual(report["intake"][0]["projected_unmet_demand"], 1)

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
                         "leave_waiting_list")
        self.assertIn("expired", by_student["STU-4"]["next"])
        self.assertIn("Withdraw the old entry", by_student["STU-4"]["next"])
        self.assertEqual(by_student["STU-2"]["next_role"], "Teaching Scheduler")


if __name__ == "__main__":
    unittest.main()
