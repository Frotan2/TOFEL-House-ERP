"""Reception queue and guided-action integration tests on the actual desk source."""
from datetime import datetime, timedelta
import unittest
from tests.desk.test_desk_contract import _import_desk


class RegistrationDeskTests(unittest.TestCase):
    def desk(self, *, placement=True, applicant=True, expired=False, applicant_status="Applied", returning_students=None):
        desk = _import_desk("reception", roles={"Reception", "Admission Officer", "Admission Approver"})
        desk.reception_sections = lambda **_kwargs: []
        desk.project_count = lambda *_args, **_kwargs: 0
        desk._subject_index = lambda rows: {
            row["name"]: "learner@example.test" for row in rows}
        desk.guided_action = lambda role, endpoint, label, args: dict(
            role=role, endpoint=endpoint, label=label, args=args)
        calls = []

        def project_rows(_surface, doctype, _fields, filters=None, **_kwargs):
            calls.append((doctype, filters))
            if doctype == desk.DECISION:
                return ([{
                    "name": "PL-1", "attempt": "A-1", "status": "Released",
                    "expires_at": "2026-01-01 00:00:00" if expired else "2027-12-31 00:00:00",
                    "released_at": "2026-09-15 12:00:00", "course_code": "GE-P1",
                }] if placement else [])
            if doctype == desk.ADMISSION:
                return []
            if doctype == desk.APPLICANT:
                return ([{
                    "name": "APP-1", "title": "Learner Name",
                    "student_email_id": "learner@example.test",
                    "program": "GE-P1", "academic_year": "2026",
                    "application_status": applicant_status, "creation": "2026-09-16",
                }] if applicant else [])
            if doctype == desk.STUDENT:
                return list(returning_students or []) if filters and "student_applicant" in filters else []
            if doctype == desk.INQUIRY:
                return [{
                    "name": "INQ-1", "person_name": "Visitor Name", "phone": "+93700000001",
                    "program_interest": "English", "th_branch": "Branch Alpha",
                    "status": "New", "notes": "", "version": 1,
                    "creation": "2026-09-16 09:00:00",
                }]
            return []
        desk.project_rows = project_rows
        return desk, calls

    def test_branchless_placement_case_does_not_expose_subject(self):
        desk = _import_desk("reception", roles={"Reception"})
        rows = [{
            "name": "PL-1", "attempt": "ATT-1", "status": "Released",
        }]
        def get_rows(_surface, doctype, _fields, **_kwargs):
            if doctype == desk.ATTEMPT:
                return [{"name": "ATT-1", "case_name": "CASE-1", "status": "Finalized"}]
            if doctype == desk.CASE:
                return [{"name": "CASE-1", "subject": "private@example.test",
                         "status": "Open", "th_branch": ""}]
            return []
        desk.project_rows = get_rows
        self.assertEqual(desk._subject_index(rows), {"PL-1": ""})

    def test_reception_without_branch_assignment_is_denied(self):
        desk, _ = self.desk(placement=False, applicant=False)
        original = desk.frappe.db.get_value
        desk.frappe.db.get_value = lambda doctype, *args, **kwargs: (
            None if doctype == "User Permission" else original(doctype, *args, **kwargs))
        with self.assertRaises(desk.frappe.PermissionError):
            desk.work()

    def test_existing_applicant_gets_create_admission_not_duplicate_record(self):
        desk, _ = self.desk()
        view = desk.work()
        handover = next(x for x in view["sections"] if x["id"] == "handover")["items"]
        people = next(x for x in view["sections"] if x["id"] == "people")["items"]
        self.assertEqual(handover[0]["action"]["endpoint"], "toefl_house.admission.create_admission")
        self.assertEqual(handover[0]["action"]["args"]["student_applicant"], "APP-1")
        self.assertEqual(people[0]["action"]["endpoint"], "toefl_house.admission.create_admission")
        self.assertEqual(people[0]["action"]["args"]["placement_decision"], "PL-1")

    def test_admitted_applicant_reuses_verified_linked_student(self):
        desk, calls = self.desk(applicant_status="Admitted", returning_students=[{
            "name": "STU-1", "student_applicant": "APP-1",
            "student_email_id": "learner@example.test",
        }])
        view = desk.work()
        item = next(x for x in view["sections"] if x["id"] == "handover")["items"][0]
        self.assertEqual(item["action"]["endpoint"], "toefl_house.admission.create_admission")
        self.assertEqual(item["action"]["args"]["existing_student"], "STU-1")
        self.assertEqual(item["action"]["args"]["placement_course_code"], "GE-P1")
        self.assertEqual(item["next_role"], "Admission Officer")
        self.assertIn((desk.STUDENT, {
            "student_applicant": ("in", ["APP-1"]), "enabled": 1}), calls)

    def test_admitted_applicant_with_no_visible_native_student_has_no_dead_button(self):
        desk, _ = self.desk(applicant_status="Admitted")
        view = desk.work()
        item = next(x for x in view["sections"] if x["id"] == "handover")["items"][0]
        self.assertIsNone(item["action"])
        self.assertEqual(item["next_role"], "Academic Manager")
        self.assertIn("Do not create a duplicate", item["next"])

    def test_returning_identity_requires_exact_native_link_and_email(self):
        desk, _ = self.desk(applicant_status="Admitted", returning_students=[
            {"name": "STU-WRONG", "student_applicant": "APP-1",
             "student_email_id": "other@example.test"},
        ])
        view = desk.work()
        item = next(x for x in view["sections"] if x["id"] == "handover")["items"][0]
        self.assertIsNone(item["action"])

    def test_ambiguous_returning_students_are_refused(self):
        desk, _ = self.desk(applicant_status="Admitted", returning_students=[
            {"name": "STU-1", "student_applicant": "APP-1",
             "student_email_id": "learner@example.test"},
            {"name": "STU-2", "student_applicant": "APP-1",
             "student_email_id": "learner@example.test"},
        ])
        item = next(x for x in desk.work()["sections"] if x["id"] == "handover")["items"][0]
        self.assertIsNone(item["action"])

    def test_unrecorded_candidate_uses_record_applicant(self):
        desk, _ = self.desk(applicant=False)
        view = desk.work()
        handover = next(x for x in view["sections"] if x["id"] == "handover")["items"]
        self.assertEqual(handover[0]["action"]["endpoint"], "toefl_house.admission.record_applicant")

    def test_expired_placement_never_offers_intake(self):
        desk, _ = self.desk(expired=True)
        view = desk.work()
        handover = next(x for x in view["sections"] if x["id"] == "handover")["items"]
        self.assertEqual(handover, [])

    def test_reception_student_lookup_uses_own_roster_not_program_coverage(self):
        desk, _ = self.desk(placement=False, applicant=False)
        calls = []
        student = {"name": "STU-1", "student_name": "Registered Learner",
                   "student_email_id": "", "th_candidate_ref": "THV-1",
                   "enabled": 1, "creation": "2026-09-01"}
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            calls.append((doctype, filters))
            if doctype == desk.STUDENT:
                return [student]
            if doctype == desk.ENROLLMENT:
                return [{"name": "PE-1", "student": "STU-1",
                         "program": "GE", "academic_year": "2026",
                         "academic_term": "Term 1", "docstatus": 1,
                         "enrollment_date": "2026-09-12"}]
            if doctype == desk.ROSTER:
                return []
            if doctype == desk.GROUP:
                raise AssertionError("Unrelated class catalog is not membership evidence")
            return []
        desk.project_rows = read
        desk.reception_sections = lambda **kwargs: []
        results = desk.lookup("STU-1")
        self.assertEqual(len(results["students"]), 1)
        item = results["students"][0]
        self.assertEqual(item["stage"], "Enrolled, class not confirmed")
        self.assertIn("2026", item["detail"])
        self.assertIn("Term 1", item["detail"])
        self.assertEqual(item["next_role"], "Teaching Scheduler")
        self.assertTrue(any(doctype == desk.ROSTER for doctype, _ in calls))

    def test_upcoming_meeting_does_not_include_already_finished_today(self):
        desk, _ = self.desk(placement=False, applicant=False)
        now = datetime(2026, 11, 11, 10, 0, 0)
        row = {"schedule_date": "2026-11-11", "to_time": "09:10:00"}
        self.assertEqual(desk._upcoming_session_state(row, now), "elapsed")
        row["to_time"] = "10:30:00"
        self.assertEqual(desk._upcoming_session_state(row, now), "future")
        row["to_time"] = timedelta(hours=10, minutes=30)
        self.assertEqual(desk._upcoming_session_state(row, now), "future")
        row["schedule_date"] = "2026-11-12"
        self.assertEqual(desk._upcoming_session_state(row, now), "future")
        row["schedule_date"] = "2026-11-10"
        self.assertEqual(desk._upcoming_session_state(row, now), "elapsed")
        row["schedule_date"] = "2026-11-11"
        row["to_time"] = "not-a-native-time"
        self.assertEqual(desk._upcoming_session_state(row, now), "invalid")

    def test_class_cannot_be_claimed_from_an_unrelated_open_group(self):
        desk, _ = self.desk(placement=False, applicant=False)
        calls = []
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            calls.append((doctype, filters))
            if doctype == desk.ROSTER:
                return []
            if doctype == desk.GROUP:
                return [{"name": "CLASS-OTHER", "program": "GE",
                         "academic_year": "2026", "academic_term": "Term 1",
                         "th_branch": "Branch Alpha", "th_class_status": "Active",
                         "disabled": 0}]
            return []
        desk.project_rows = read
        info = desk._student_class_information(
            [{"name": "STU-1", "enabled": 1}],
            [{"student": "STU-1", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["STU-1"]["stage"], "Enrolled, class not confirmed")
        self.assertNotIn("CLASS-OTHER", info["STU-1"]["detail"])
        self.assertNotIn((desk.GROUP, None), calls)
        self.assertEqual(calls[0][0], desk.ROSTER)
        self.assertEqual(calls[0][1]["student"], ("in", ["STU-1"]))

    def test_unique_verified_roster_shows_dated_session_and_instructor(self):
        desk, _ = self.desk(placement=False, applicant=False)
        calls = []
        group = {"name": "CLASS-A", "student_group_name": "GE Morning A",
                 "program": "GE", "academic_year": "2026",
                 "academic_term": "Term 1", "th_branch": "Branch Alpha",
                 "th_class_status": "Active", "disabled": 0}
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            calls.append((doctype, filters))
            if doctype == desk.ROSTER:
                return [{"name": "MEM-1", "parent": "CLASS-A",
                         "student": "STU-1", "active": 1}]
            if doctype == desk.GROUP:
                return [group]
            if doctype == desk.SCHEDULE:
                return [{"name": "SESSION-1", "student_group": "CLASS-A",
                         "instructor": "INST-1", "course": "Speaking",
                         "room": "Room 2", "from_time": "08:00:00",
                         "to_time": "09:10:00", "schedule_date": "2026-11-10",
                         "th_session_status": "Scheduled"}]
            if doctype == desk.ASSIGNMENT:
                return [{"name": "ASSIGN-1", "student_group": "CLASS-A",
                         "instructor": "INST-1", "effective_start": "2026-09-01",
                         "effective_end": "", "course_schedule": ""}]
            if doctype == desk.INSTRUCTOR:
                return [{"name": "INST-1", "instructor_name": "Test Instructor",
                         "status": "Active"}]
            return []
        desk.project_rows = read
        info = desk._student_class_information(
            [{"name": "STU-1", "enabled": 1}],
            [{"student": "STU-1", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["STU-1"]["stage"], "Class assigned, sessions scheduled")
        self.assertIn("GE Morning A", info["STU-1"]["detail"])
        self.assertIn("Speaking", info["STU-1"]["next"])
        self.assertIn("Test Instructor", info["STU-1"]["next"])
        self.assertIn("Room 2", info["STU-1"]["next"])
        self.assertIn("not a recurring weekly timetable", info["STU-1"]["next"])
        self.assertIn((desk.SCHEDULE, {
            "student_group": ("in", ["CLASS-A"]),
            "schedule_date": (">=", desk.frappe.utils.today()),
            "th_session_status": "Scheduled",
        }), calls)

    def test_instructor_not_named_without_effective_teaching_assignment(self):
        desk, _ = self.desk(placement=False, applicant=False)
        calls = []
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            calls.append(doctype)
            if doctype == desk.ROSTER:
                return [{"name": "M", "parent": "CLASS-A", "student": "STU", "active": 1}]
            if doctype == desk.GROUP:
                return [{"name": "CLASS-A", "student_group_name": "GE",
                         "program": "GE", "academic_year": "2026",
                         "academic_term": "Term 1", "th_branch": "Branch Alpha",
                         "th_class_status": "Active", "disabled": 0}]
            if doctype == desk.SCHEDULE:
                return [{"name": "SESSION-1", "student_group": "CLASS-A",
                         "instructor": "INST-1", "course": "Writing", "room": "Room 1",
                         "schedule_date": "2026-11-15", "from_time": "08:00:00",
                         "to_time": "09:00:00", "th_session_status": "Scheduled"}]
            if doctype == desk.ASSIGNMENT:
                return [{"name": "OLD-ASSIGN", "student_group": "CLASS-A",
                         "instructor": "INST-1", "course_schedule": "",
                         "effective_start": "2026-01-01",
                         "effective_end": "2026-10-01"}]
            if doctype == desk.INSTRUCTOR:
                raise AssertionError("Do not resolve teacher names without valid assignment")
            return []
        desk.project_rows = read
        info = desk._student_class_information(
            [{"name": "STU", "enabled": 1}],
            [{"student": "STU", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["STU"]["stage"], "Class assigned, sessions scheduled")
        self.assertIn("Writing", info["STU"]["next"])
        self.assertIn("Instructor assignment unverified", info["STU"]["next"])
        self.assertNotIn(desk.INSTRUCTOR, calls)

    def test_suspension_after_scheduling_blocks_wrong_front_counter_promise(self):
        desk, _ = self.desk(placement=False, applicant=False)
        def read(_surface, doctype, fields, filters=None, **_kw):
            if doctype == desk.ROSTER:
                return [{"name": "M", "parent": "CLASS-A", "student": "S", "active": 1}]
            if doctype == desk.GROUP:
                return [{"name": "CLASS-A", "student_group_name": "GE Morning",
                         "program": "GE", "academic_year": "2026",
                         "academic_term": "Term 1", "th_branch": "Branch Alpha",
                         "th_class_status": "Active", "disabled": 0}]
            if doctype == desk.SCHEDULE:
                return [{"name": "SESS-1", "student_group": "CLASS-A",
                         "instructor": "INST-1", "course": "Reading", "room": "A-1",
                         "schedule_date": "2026-11-11", "from_time": "08:00:00",
                         "to_time": "09:00:00", "th_session_status": "Scheduled"}]
            if doctype == desk.ASSIGNMENT:
                return [{"name": "AS-1", "student_group": "CLASS-A", "instructor": "INST-1",
                         "course_schedule": "", "effective_start": "2026-09-01",
                         "effective_end": ""}]
            if doctype == desk.INSTRUCTOR:
                return [{"name": "INST-1", "instructor_name": "Teacher One", "status": "Active"}]
            if doctype == desk.SUSPENSION:
                self.assertNotIn("reason", fields, "private suspension reason must not leave DB")
                self.assertEqual(filters["student_group"], ("in", ["CLASS-A"]))
                return self.suspensions
            return []
        desk.project_rows = read
        self.suspensions = []
        def stage():
            return desk._student_class_information(
                [{"name": "S", "enabled": 1}],
                [{"student": "S", "program": "GE", "academic_year": "2026",
                  "academic_term": "Term 1", "docstatus": 1}])["S"]

        self.assertEqual(stage()["stage"], "Class assigned, sessions scheduled")
        class_row = {"name": "SUSP-1", "student_group": "CLASS-A", "scope": "Class",
                     "student": None, "status": "Active",
                     "from_date": "2026-11-10", "until_date": "2026-11-12"}
        self.suspensions = [class_row]
        blocked = stage()
        self.assertEqual(blocked["stage"], "Class sessions under review")
        self.assertEqual(blocked["next_role"], "Teaching Scheduler")
        self.assertNotIn("Teacher One", blocked["next"])
        self.assertNotIn("A-1", blocked["next"])

        # A restriction on someone ELSE must not alter this Student's view.
        self.suspensions = [{**class_row, "scope": "Student", "student": "OTHER"}]
        self.assertEqual(stage()["stage"], "Class assigned, sessions scheduled")
        self.suspensions = [{**class_row, "scope": "Student", "student": "S"}]
        personal = stage()
        self.assertEqual(personal["stage"], "Attendance eligibility needs review")
        self.assertEqual(personal["next_role"], "Academic Manager")
        self.assertNotIn("Teacher One", personal["next"])
        self.suspensions = [{**class_row, "scope": "Class",
                             "from_date": "2026-11-20", "until_date": "2026-11-21"}]
        self.assertEqual(stage()["stage"], "Class assigned, sessions scheduled")
        self.suspensions = [{**class_row, "scope": "Class", "from_date": "broken"}]
        self.assertEqual(stage()["stage"], "Class assigned, timetable needs review")

    def test_pending_class_transfer_is_not_an_executed_roster_change(self):
        desk, _ = self.desk(placement=False, applicant=False)
        requests = []
        def read(_surface, doctype, fields, filters=None, **_kwargs):
            if doctype == desk.ROSTER:
                return [{"name": "MEM-1", "parent": "CLASS-A",
                         "student": "STU-1", "active": 1}]
            if doctype == desk.GROUP:
                return [{"name": "CLASS-A", "student_group_name": "Morning GE",
                         "program": "GE", "academic_year": "2026",
                         "academic_term": "Term 1", "th_branch": "Branch Alpha",
                         "th_class_status": "Planned", "disabled": 0}]
            if doctype == desk.TRANSFER:
                self.assertNotIn("reason", fields)
                self.assertNotIn("eligibility_json", fields)
                self.assertEqual(filters, {"student": ("in", ["STU-1"]),
                                           "status": "Requested"})
                return list(requests)
            return []
        desk.project_rows = read
        def view():
            return desk._student_class_information(
                [{"name": "STU-1", "enabled": 1}],
                [{"name": "PE-1", "student": "STU-1", "program": "GE",
                  "academic_year": "2026", "academic_term": "Term 1",
                  "docstatus": 1}])["STU-1"]
        self.assertEqual(view()["stage"], "Class planned")
        requests.append({"name": "TRANSFER-1", "student": "STU-1",
                         "from_group": "CLASS-A", "to_group": "CLASS-B",
                         "status": "Requested", "transfer_kind": "Class",
                         "effective_date": "2026-11-12"})
        pending = view()
        self.assertEqual(pending["stage"], "Class planned")
        self.assertIn("Morning GE", pending["detail"])
        self.assertIn("Transfer REQUESTED to class CLASS-B", pending["next"])
        self.assertIn("Current class stays", pending["next"])
        self.assertEqual(pending["next_role"], "Academic Manager")
        # A foreign or old source class is not the learner's verified roster.
        requests[0]["from_group"] = "CLASS-FOREIGN"
        self.assertNotIn("Transfer REQUESTED", view()["next"])
        requests[0]["from_group"] = "CLASS-A"
        requests[0]["status"] = "Executed"
        # A completed transfer isn't a pending request: native roster is
        # authoritative, not a transfer request/decision row.
        requests.clear()
        self.assertNotIn("Transfer REQUESTED", view()["next"])

    def test_multiple_or_overdue_pending_moves_require_academic_review(self):
        desk, _ = self.desk(placement=False, applicant=False)
        requests = [
            {"name": "TR-1", "student": "S", "from_group": "CLASS-A",
             "to_group": "CLASS-B", "status": "Requested",
             "transfer_kind": "Class", "effective_date": "2026-01-01"},
        ]
        def read(_surface, doctype, fields, filters=None, **_kwargs):
            if doctype == desk.ROSTER:
                return [{"name": "MEM", "parent": "CLASS-A", "student": "S", "active": 1}]
            if doctype == desk.GROUP:
                return [{"name": "CLASS-A", "student_group_name": "Morning",
                         "program": "GE", "academic_year": "2026",
                         "academic_term": "Term 1", "th_branch": "Branch Alpha",
                         "th_class_status": "Planned", "disabled": 0}]
            if doctype == desk.TRANSFER:
                return requests
            return []
        desk.project_rows = read
        def info():
            return desk._student_class_information(
                [{"name": "S", "enabled": 1}],
                [{"student": "S", "program": "GE",
                  "academic_year": "2026", "academic_term": "Term 1",
                  "docstatus": 1}])["S"]
        self.assertIn("requested date has passed", info()["next"])
        requests.append({**requests[0], "name": "TR-2", "to_group": "CLASS-C"})
        self.assertEqual(info()["stage"], "Class transfer requests need review")
        self.assertEqual(info()["next_role"], "Academic Manager")
        requests.clear()
        requests.extend({**{"name": f"TR-{i}", "student": "S",
                            "from_group": "CLASS-A", "to_group": "CLASS-B",
                            "status": "Requested", "transfer_kind": "Class",
                            "effective_date": "2026-11-12"}}
                        for i in range(desk.BOUNCE_WINDOW))
        self.assertEqual(info()["stage"], "Class transfer status needs review")

    def test_planned_class_does_not_claim_scheduled_meeting_or_teacher(self):
        desk, _ = self.desk(placement=False, applicant=False)
        group = {"name": "CLASS-PLAN", "student_group_name": "GE Planned",
                 "program": "GE", "academic_year": "2026",
                 "academic_term": "Term 1", "th_branch": "Branch Alpha",
                 "th_class_status": "Planned", "disabled": 0}
        observed = []
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            observed.append(doctype)
            if doctype == desk.ROSTER:
                return [{"name": "MEM-1", "parent": "CLASS-PLAN",
                         "student": "STU-1", "active": 1}]
            if doctype == desk.GROUP:
                return [group]
            return []
        desk.project_rows = read
        info = desk._student_class_information(
            [{"name": "STU-1", "enabled": 1}],
            [{"student": "STU-1", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["STU-1"]["stage"], "Class planned")
        self.assertNotIn(desk.SCHEDULE, observed)
        self.assertNotIn(desk.INSTRUCTOR, observed)

    def test_multiple_class_rosters_do_not_choose_teacher_arbitrarily(self):
        desk, _ = self.desk(placement=False, applicant=False)
        called = []
        def read(_surface, doctype, _fields, filters=None, **_kwargs):
            called.append(doctype)
            if doctype == desk.ROSTER:
                return [{"name": "M1", "parent": "CLASS-1", "student": "S", "active": 1},
                        {"name": "M2", "parent": "CLASS-2", "student": "S", "active": 1}]
            if doctype == desk.GROUP:
                return [{"name": key, "student_group_name": key, "program": "GE",
                         "academic_year": "2026", "academic_term": "Term 1",
                         "th_branch": "Branch Alpha", "th_class_status": "Active",
                         "disabled": 0} for key in ("CLASS-1", "CLASS-2")]
            return []
        desk.project_rows = read
        info = desk._student_class_information(
            [{"name": "S", "enabled": 1}],
            [{"student": "S", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["S"]["stage"], "Multiple class memberships")
        self.assertEqual(info["S"]["next_role"], "Academic Manager")
        self.assertNotIn(desk.SCHEDULE, called)
        self.assertNotIn(desk.INSTRUCTOR, called)

    def test_large_incomplete_roster_refuses_class_and_session_claims(self):
        desk, _ = self.desk(placement=False, applicant=False)
        desk.project_rows = lambda _surface, doctype, _fields, **_kw: (
            [{"name": str(i), "parent": "CLASS", "student": "S", "active": 1}
             for i in range(desk.BOUNCE_WINDOW)] if doctype == desk.ROSTER else [])
        info = desk._student_class_information(
            [{"name": "S", "enabled": 1}],
            [{"student": "S", "program": "GE", "academic_year": "2026",
              "academic_term": "Term 1", "docstatus": 1}])
        self.assertEqual(info["S"]["stage"], "Class details require review")
        self.assertEqual(info["S"]["next_role"], "Academic Manager")

    def test_reception_can_search_student_by_internal_candidate_reference(self):
        desk, calls = self.desk(placement=False, applicant=False)
        ref = "THV-" + "a" * 32
        desk.lookup(ref)
        self.assertIn((desk.STUDENT, {
            "th_candidate_ref": ("like", "%" + ref + "%"), "enabled": ("in", [0, 1])
        }), calls)
        self.assertIn((desk.APPLICANT, {
            "th_candidate_ref": ("like", "%" + ref + "%")
        }), calls)

    def test_reception_can_search_native_student_and_inquiry_ids(self):
        desk, calls = self.desk(placement=False, applicant=False)
        desk.lookup("STU-001")
        self.assertIn((desk.STUDENT, {
            "name": "STU-001", "enabled": ("in", [0, 1])
        }), calls)
        desk.lookup("INQ-001")
        self.assertIn((desk.INQUIRY, {
            "name": "INQ-001"
        }), calls)

    def test_disabled_student_is_visible_as_inactive_not_enrollable(self):
        desk, _calls = self.desk(placement=False, applicant=False)
        ref = "THV-" + "a" * 32
        original = desk.project_rows
        def project_rows(surface, doctype, fields, filters=None, **kwargs):
            if doctype == desk.STUDENT:
                if filters and "th_candidate_ref" in filters:
                    return [{"name": "STU-OLD", "student_name": "Former Learner",
                             "student_email_id": "", "th_candidate_ref": ref,
                             "enabled": 0, "creation": "2025-01-01"}]
                return []
            if doctype == desk.ENROLLMENT or doctype == desk.GROUP:
                return []
            return original(surface, doctype, fields, filters=filters, **kwargs)
        desk.project_rows = project_rows
        desk.reception_sections = lambda **kwargs: []
        student = desk.lookup(ref)["students"][0]
        self.assertEqual(student["status"], "Inactive")
        self.assertEqual(student["stage"], "Inactive student")
        self.assertIn("Academic Manager", student["next"])
        self.assertIn(ref, student["detail"])
        self.assertNotIn("action", student)

    def test_verified_inquiry_name_is_used_in_admission_handover(self):
        desk, calls = self.desk(applicant=False)
        ref = "THV-" + "a" * 32
        desk._subject_index = lambda decisions: {row["name"]: ref for row in decisions}
        real_rows = desk.project_rows
        def project_rows(surface, doctype, fields, filters=None, **kwargs):
            if doctype == desk.CASE:
                return [{"name": "CASE-1", "subject": ref, "th_branch": "Branch Alpha",
                         "reception_inquiry": "INQ-1"}]
            if doctype == desk.INQUIRY and filters and "name" in filters:
                return [{"name": "INQ-1", "person_name": "Visitor Name",
                         "th_branch": "Branch Alpha"}]
            return real_rows(surface, doctype, fields, filters=filters, **kwargs)
        desk.project_rows = project_rows
        row = next(section for section in desk.work()["sections"]
                   if section["id"] == "handover")["items"][0]
        self.assertEqual(row["person"], "Visitor Name")
        self.assertIn(ref, row["detail"])

    def test_wrong_branch_does_not_display_reception_identity(self):
        desk, _ = self.desk(applicant=False)
        ref = "THV-" + "a" * 32
        def project_rows(surface, doctype, fields, filters=None, **kwargs):
            if doctype == desk.CASE:
                return [{"name": "CASE-1", "subject": ref, "th_branch": "Branch Alpha",
                         "reception_inquiry": "INQ-1"}]
            if doctype == desk.INQUIRY:
                return [{"name": "INQ-1", "person_name": "Wrong Branch Name",
                         "th_branch": "Branch Beta"}]
            return []
        desk.project_rows = project_rows
        self.assertEqual(desk._referral_display_names([ref]), {})

    def test_reception_progress_tracks_exact_referral_through_native_student(self):
        desk, _ = self.desk(placement=False, applicant=False)
        ref = "THV-" + "a" * 32
        intake = {"name": "INQ-1", "person_name": "Visitor", "th_branch": "Branch Alpha",
                  "status": "Awaiting Placement", "version": 2}
        facts = {
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Alpha", "reception_inquiry": "INQ-1"}],
            desk.APPLICANT: [{"name": "APP-1", "th_candidate_ref": ref,
                              "th_branch": "Branch Alpha",
                              "th_reception_inquiry": "INQ-1",
                              "application_status": "Admitted"}],
            desk.STUDENT: [{"name": "STU-1", "student_applicant": "APP-1",
                            "th_candidate_ref": ref, "enabled": 1}],
        }
        desk.project_rows = lambda _surface, dt, _fields, **kwargs: list(facts.get(dt, []))
        stage = desk._walkin_progress([intake], [ref])["INQ-1"]
        self.assertEqual(stage[0], "Student profile created")
        item = desk._walkin_item(intake, stage)
        self.assertEqual(item["stage"], "Student profile created")
        self.assertEqual(item["next_role"], "Enrollment Officer")
        self.assertIn("complete Program Enrollment", item["next"])
        self.assertIn("Student ID STU-1", item["next"])
        # An active Student does not imply any Program Enrollment or Fees.
        self.assertNotIn("Enrolled", item["stage"])

    def test_submitted_enrollment_is_distinct_from_student_profile(self):
        desk, _ = self.desk(placement=False, applicant=False)
        ref = "THV-" + "a" * 32
        facts = {
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Alpha", "reception_inquiry": "INQ-1"}],
            desk.APPLICANT: [{"name": "APP-1", "th_candidate_ref": ref,
                              "th_branch": "Branch Alpha", "th_reception_inquiry": "INQ-1"}],
            desk.STUDENT: [{"name": "STU-1", "student_applicant": "APP-1",
                            "th_candidate_ref": ref, "enabled": 1}],
            desk.ENROLLMENT: [{"name": "PE-1", "student": "STU-1",
                               "docstatus": 1, "program": "GE"}],
        }
        desk.project_rows = lambda _surface, dt, _fields, **kwargs: list(facts.get(dt, []))
        progress = desk._walkin_progress([{"name": "INQ-1", "th_branch": "Branch Alpha"}], [ref])
        self.assertEqual(progress["INQ-1"][0], "Enrollment on file")
        self.assertEqual(progress["INQ-1"][2], "Academic Manager")
        self.assertIn("class and upcoming dated sessions", progress["INQ-1"][1])
        self.assertIn("Student ID STU-1", progress["INQ-1"][1])

    def test_reception_progress_does_not_join_wrong_branch_or_reused_phone(self):
        desk, _ = self.desk(placement=False, applicant=False)
        visit = {"name": "INQ-1", "person_name": "Visitor", "th_branch": "Branch Alpha"}
        ref = "THV-" + "a" * 32
        facts = {
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Beta", "reception_inquiry": "INQ-1"}],
            desk.APPLICANT: [{"name": "APP-1", "th_candidate_ref": ref,
                              "th_branch": "Branch Alpha", "th_reception_inquiry": "INQ-1"}],
            desk.STUDENT: [{"name": "STU-1", "student_applicant": "APP-1",
                            "th_candidate_ref": ref, "enabled": 1}],
        }
        desk.project_rows = lambda _surface, dt, _fields, **kwargs: list(facts.get(dt, []))
        self.assertEqual(desk._walkin_progress([visit], [ref]), {})
        facts[desk.CASE][0]["th_branch"] = "Branch Alpha"
        facts[desk.APPLICANT][0]["th_candidate_ref"] = "THV-" + "b" * 32
        self.assertEqual(desk._walkin_progress([visit], [ref])["INQ-1"][0],
                         "Identity review needed")
        facts[desk.APPLICANT][0]["th_candidate_ref"] = ref
        facts[desk.STUDENT][0]["th_candidate_ref"] = "THV-" + "b" * 32
        self.assertEqual(desk._walkin_progress([visit], [ref])["INQ-1"][0],
                         "Identity review needed")

    def test_reception_progress_requires_academic_review_on_duplicate_links(self):
        desk, _ = self.desk(placement=False, applicant=False)
        visit = {"name": "INQ-1", "th_branch": "Branch Alpha"}
        ref = "THV-" + "a" * 32
        facts = {
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Alpha", "reception_inquiry": "INQ-1"}],
            desk.APPLICANT: [
                {"name": "APP-1", "th_candidate_ref": ref,
                 "th_branch": "Branch Alpha", "th_reception_inquiry": "INQ-1"},
                {"name": "APP-2", "th_candidate_ref": ref,
                 "th_branch": "Branch Alpha", "th_reception_inquiry": "INQ-1"}],
        }
        desk.project_rows = lambda _surface, dt, _fields, **kwargs: list(facts.get(dt, []))
        stage = desk._walkin_progress([visit], [ref])["INQ-1"]
        self.assertEqual(stage[0], "Identity review needed")
        self.assertEqual(stage[2], "Academic Manager")

    def test_closed_inquiry_lookup_retains_progress_without_edit_button(self):
        desk, _ = self.desk(placement=False, applicant=False)
        visit = {"name": "INQ-1", "person_name": "Visitor",
                 "status": "Closed", "version": 3, "th_branch": "Branch Alpha"}
        ref = "THV-" + "a" * 32
        facts = {
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Alpha", "reception_inquiry": "INQ-1"}],
            desk.APPLICANT: [{"name": "APP-1", "th_candidate_ref": ref,
                              "th_branch": "Branch Alpha",
                              "th_reception_inquiry": "INQ-1"}],
            desk.STUDENT: [{"name": "STU-1", "student_applicant": "APP-1",
                            "th_candidate_ref": ref, "enabled": 1}],
        }
        original = desk.project_rows
        def read(surface, doctype, fields, filters=None, **kwargs):
            if doctype == desk.INQUIRY:
                return [visit]
            if doctype in facts:
                return list(facts[doctype])
            return original(surface, doctype, fields, filters=filters, **kwargs)
        desk.project_rows = read
        item = desk.lookup("INQ-1")["inquiries"][0]
        self.assertEqual(item["status"], "Closed")
        self.assertEqual(item["stage"], "Student profile created")
        self.assertIsNone(item["action"])

    def test_no_placement_cannot_claim_progressed_student(self):
        desk, _ = self.desk(placement=False, applicant=False)
        desk.project_rows = lambda *_args, **_kwargs: []
        visit = {"name": "INQ-1", "th_branch": "Branch Alpha"}
        self.assertEqual(desk._walkin_progress([visit], []), {})

    def test_reception_typo_correction_is_a_secondary_action_before_placement(self):
        desk, _ = self.desk(placement=False, applicant=False)
        row = {"name": "INQ-1", "person_name": "Visitor", "phone": "0794357509",
               "status": "New", "version": 1}
        item = desk._walkin_item(row)
        self.assertEqual(item["actions"][0]["endpoint"],
                         "toefl_house.reception_intake.correct_walkin_inquiry")
        self.assertEqual(item["actions"][0]["args"]["person_name"], "Visitor")
        self.assertEqual(item["actions"][0]["args"]["reason"], "")
        self.assertEqual(desk._walkin_item(row, ("Placement case opened", "", "Placement Publisher"))["actions"], [])

    def test_awaiting_placement_inquiry_points_to_publisher_not_reception(self):
        desk, _ = self.desk(placement=False, applicant=False)
        row = {"name": "INQ-1", "person_name": "Visitor",
               "status": "Awaiting Placement", "version": 2}
        item = desk._walkin_item(row)
        self.assertEqual(item["stage"], "Awaiting placement allocation")
        self.assertEqual(item["next_role"], "Placement Publisher")
        self.assertIn("INQ-1", item["detail"])

    def test_walkin_registration_is_visible_even_without_placement(self):
        desk, _ = self.desk(placement=False, applicant=False)
        view = desk.work()
        walkins = next(x for x in view["sections"] if x["id"] == "walkins")
        self.assertEqual(view["primary_action"]["endpoint"],
                         "toefl_house.reception_intake.create_walkin_inquiry")
        self.assertIn("(0)", walkins["title"])
        self.assertEqual(walkins["items"][0]["stage"], "Pre-registration")
        self.assertEqual(walkins["actions"][0]["endpoint"],
                         "toefl_house.reception_intake.create_walkin_inquiry")
        self.assertEqual(walkins["items"][0]["action"]["endpoint"],
                         "toefl_house.reception_intake.update_walkin_inquiry")

    def test_walkin_and_student_contact_searches_are_both_scoped(self):
        desk, calls = self.desk(placement=False, applicant=False)
        # The desk may read only through the previously scoped and allowlisted
        # project_rows path. The same user-entered substring must reach both
        # Student email and inquiry phone filters, not unrestricted SQL.
        desk.lookup("700")
        self.assertIn((desk.STUDENT, {"student_email_id": ("like", "%700%"), "enabled": ("in", [0, 1])}), calls)
        self.assertIn((desk.INQUIRY, {"phone": ("like", "%700%")}), calls)

    def test_search_normalizes_phone_separators_and_afghan_digits(self):
        desk, calls = self.desk(placement=False, applicant=False)
        desk.lookup("۰۷۹-۴۳۵ ۷۵۰۹")
        self.assertIn((desk.INQUIRY, {
            "phone": ("like", "%0794357509%")
        }), calls)
        # A non-phone name query remains literal, not stripped of punctuation.
        desk.lookup("Ali-Teacher")
        self.assertIn((desk.INQUIRY, {
            "phone": ("like", "%Ali-Teacher%")
        }), calls)

    def test_search_rejects_nontext_input_before_any_data_read(self):
        desk, calls = self.desk(placement=False, applicant=False)
        with self.assertRaises(desk.frappe.ValidationError):
            desk.lookup({"name": "Someone"})
        self.assertEqual(calls, [])

    def test_targeted_lookup_uses_current_case_release_not_dashboard_page(self):
        desk, _ = self.desk(placement=False, applicant=False)
        ref = "THV-" + "b" * 32
        visit = {"name": "INQ-1", "person_name": "Visitor", "phone": "",
                 "th_branch": "Branch Alpha", "status": "Awaiting Placement",
                 "version": 2}
        facts = {
            desk.INQUIRY: [visit],
            desk.CASE: [{"name": "CASE-1", "subject": ref,
                         "th_branch": "Branch Alpha", "reception_inquiry": "INQ-1"}],
            desk.ATTEMPT: [{"name": "ATT-1", "case_name": "CASE-1",
                            "status": "Finalized"}],
            desk.DECISION: [{"name": "DEC-1", "attempt": "ATT-1",
                             "status": "Released", "expires_at": "2027-01-01 00:00:00"}],
        }
        query_log = []
        def read(surface, doctype, fields, filters=None, **kwargs):
            query_log.append((doctype, filters))
            return list(facts.get(doctype, []))
        desk.project_rows = read
        item = desk.lookup("INQ-1")["inquiries"][0]
        self.assertEqual(item["stage"], "Placement result released")
        self.assertEqual(item["next_role"], "Admission Officer")
        self.assertIn((desk.ATTEMPT, {"case_name": ("in", ["CASE-1"])}), query_log)
        # Expired or unpublished decisions cannot be shown as released.
        facts[desk.DECISION][0]["expires_at"] = "2026-01-01 00:00:00"
        self.assertEqual(desk.lookup("INQ-1")["inquiries"][0]["stage"],
                         "Placement case opened")
        facts[desk.DECISION][0]["expires_at"] = "2027-01-01 00:00:00"
        facts[desk.DECISION][0]["status"] = "Draft"
        self.assertEqual(desk.lookup("INQ-1")["inquiries"][0]["stage"],
                         "Placement case opened")

    def test_afghan_digit_contact_lookup_matches_ascii_phone(self):
        desk, calls = self.desk(placement=False, applicant=False)
        desk.lookup("۷۰۰")
        self.assertIn((desk.INQUIRY, {"phone": ("like", "%700%")}), calls)

    def test_lookup_treats_percent_and_underscore_as_literal_characters(self):
        desk, calls = self.desk(placement=False, applicant=False)
        desk.lookup("A_%")
        self.assertIn((desk.INQUIRY, {"person_name": ("like", r"%A\_\%%")}), calls)
        self.assertIn((desk.STUDENT, {"student_name": ("like", r"%A\_\%%"), "enabled": ("in", [0, 1])}), calls)

    def test_visitors_are_not_misclassified_as_native_applicants(self):
        desk, _ = self.desk(placement=False, applicant=False)
        results = desk.lookup("700")
        self.assertEqual(len(results["inquiries"]), 1)
        self.assertEqual(results["items"], [])
        self.assertIn("+93700000001", results["inquiries"][0]["detail"])
        self.assertIn("English", results["inquiries"][0]["detail"])

    def test_latest_followup_note_is_visible_but_bounded(self):
        desk, _ = self.desk()
        item = desk._walkin_item({
            "name": "INQ-1", "person_name": "Visitor", "status": "Contacted",
            "version": 2, "notes": "A" * 250, "creation": "2026-10-01",
        })
        self.assertIn("Latest note:", item["detail"])
        self.assertIn("…", item["detail"])
        self.assertLess(len(item["detail"]), 160)

    def test_closed_inquiry_has_no_action_that_would_be_denied(self):
        desk, _ = self.desk()
        item = desk._walkin_item({
            "name": "INQ-CLOSED", "person_name": "Visitor", "status": "Closed",
            "version": 2, "notes": "", "creation": "2026-09-01",
        })
        self.assertIsNone(item["action"])
        self.assertIsNone(item["next_role"])
        self.assertIn("closed", item["next"])

    def test_conditions_show_evidence_not_unlawful_conversion(self):
        desk, _ = self.desk()
        item = desk._admission_item(
            {"name": "APP-1", "title": "Learner Name", "program": "GE-P1"},
            {"name": "ADM-1", "status": "Conditional", "accepted": 1,
             "native_student": None, "version": 2})
        self.assertEqual(item["action"]["endpoint"], "toefl_house.admission.satisfy_conditions")
        self.assertEqual(item["action"]["args"]["expected_version"], 2)


if __name__ == "__main__":
    unittest.main()
