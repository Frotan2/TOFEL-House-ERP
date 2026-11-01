"""Reception queue and guided-action integration tests on the actual desk source."""
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
        self.assertIn("Verify Program Enrollment separately", item["next"])
        # An active Student does not imply any Program Enrollment or Fees.
        self.assertNotIn("Enrolled", item["stage"])

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
                         "Placement result released")
        facts[desk.APPLICANT][0]["th_candidate_ref"] = ref
        facts[desk.STUDENT][0]["th_candidate_ref"] = "THV-" + "b" * 32
        self.assertEqual(desk._walkin_progress([visit], [ref])["INQ-1"][0],
                         "Admission in progress")

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

    def test_no_placement_cannot_claim_progressed_student(self):
        desk, _ = self.desk(placement=False, applicant=False)
        desk.project_rows = lambda *_args, **_kwargs: []
        visit = {"name": "INQ-1", "th_branch": "Branch Alpha"}
        self.assertEqual(desk._walkin_progress([visit], []), {})

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
