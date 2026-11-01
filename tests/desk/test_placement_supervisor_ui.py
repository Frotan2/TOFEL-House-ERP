"""Safety contract for the invigilator-only session interface."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "apps/toefl_house/toefl_house/public/js/th_command_pages.js").read_text(encoding="utf-8")
CSS = (ROOT / "apps/toefl_house/toefl_house/public/css/th_design_system.css").read_text(encoding="utf-8")


class PlacementSupervisorUITests(unittest.TestCase):
    def test_supervised_console_is_role_specific(self):
        self.assertIn('if (surface.role === "Placement Invigilator") mountSupervisedPlacement(page);', JS)
        self.assertIn('function mountSupervisedPlacement(page)', JS)
        self.assertIn('"Invigilator-only staff workstation"', (
            ROOT / "apps/toefl_house/toefl_house/api.py").read_text(encoding="utf-8"))

    def test_never_print_candidate_answer_keys_and_recovers_server_state(self):
        self.assertIn('"toefl_house.api.supervised_attempt_view"', JS)
        self.assertIn('"toefl_house.api.supervised_attempt_status"', JS)
        self.assertIn('"toefl_house.api.supervised_attempt_choices"', JS)
        self.assertIn('"<datalist id=\'th-placement-attempt-choices\'></datalist>"', JS)
        self.assertIn('"toefl_house.api.verify_attempt"', JS)
        self.assertIn('"toefl_house.api.deliver_attempt"', JS)
        self.assertIn('function checkStatus()', JS)
        self.assertIn('type: "GET"', JS)
        self.assertIn('"toefl_house.api.save_response"', JS)
        self.assertIn('expected_revision: Number(saved.revision)', JS)
        self.assertIn('request_key: newRequestKey()', JS)
        self.assertIn('frappe.confirm(', JS)
        self.assertIn('let unsavedSelection = false;', JS)
        self.assertIn('radio.on("change", () => { unsavedSelection = true; });', JS)
        self.assertIn('Save or clear the selected answer before changing questions.', JS)
        self.assertIn('Your selected answer is not saved.', JS)
        self.assertIn('if (pending || pendingWrite) return;', JS)
        self.assertIn('question.prompt).appendTo(form)', JS)
        self.assertIn("option.text).appendTo(label)", JS)
        self.assertIn(".th-placement-option:focus-within", CSS)


if __name__ == "__main__":
    unittest.main()
