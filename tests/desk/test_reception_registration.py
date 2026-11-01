"""Reception queue and guided-action integration tests on the actual desk source."""
import unittest
from tests.desk.test_desk_contract import _import_desk


class RegistrationDeskTests(unittest.TestCase):
    def desk(self, *, placement=True, applicant=True, expired=False):
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
                    "application_status": "Applied", "creation": "2026-09-16",
                }] if applicant else [])
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

    def test_existing_applicant_gets_create_admission_not_duplicate_record(self):
        desk, _ = self.desk()
        view = desk.work()
        handover = next(x for x in view["sections"] if x["id"] == "handover")["items"]
        people = next(x for x in view["sections"] if x["id"] == "people")["items"]
        self.assertEqual(handover[0]["action"]["endpoint"], "toefl_house.admission.create_admission")
        self.assertEqual(handover[0]["action"]["args"]["student_applicant"], "APP-1")
        self.assertEqual(people[0]["action"]["endpoint"], "toefl_house.admission.create_admission")
        self.assertEqual(people[0]["action"]["args"]["placement_decision"], "PL-1")

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

    def test_walkin_registration_is_visible_even_without_placement(self):
        desk, _ = self.desk(placement=False, applicant=False)
        view = desk.work()
        walkins = next(x for x in view["sections"] if x["id"] == "walkins")
        self.assertEqual(view["primary_action"]["endpoint"],
                         "toefl_house.reception_intake.create_walkin_inquiry")
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
        self.assertIn((desk.STUDENT, {"student_email_id": ("like", "%700%"), "enabled": 1}), calls)
        self.assertIn((desk.INQUIRY, {"phone": ("like", "%700%")}), calls)

    def test_afghan_digit_contact_lookup_matches_ascii_phone(self):
        desk, calls = self.desk(placement=False, applicant=False)
        desk.lookup("۷۰۰")
        self.assertIn((desk.INQUIRY, {"phone": ("like", "%700%")}), calls)

    def test_visitors_are_not_misclassified_as_native_applicants(self):
        desk, _ = self.desk(placement=False, applicant=False)
        results = desk.lookup("700")
        self.assertEqual(len(results["inquiries"]), 1)
        self.assertEqual(results["items"], [])
        self.assertIn("+93700000001", results["inquiries"][0]["detail"])
        self.assertIn("English", results["inquiries"][0]["detail"])

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
