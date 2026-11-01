"""Database-level uniqueness protects concurrent placement-case intake."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "apps/toefl_house/toefl_house/placement/doctype/th_placement_case/th_placement_case.json"

class PlacementCaseIndexTests(unittest.TestCase):
    def test_subject_and_nonempty_inquiry_have_unique_native_constraints(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        fields = {item["fieldname"]: item for item in schema["fields"]}
        for field in ("subject", "reception_inquiry"):
            with self.subTest(field=field):
                self.assertEqual(fields[field]["unique"], 1)
        self.assertEqual(fields["reception_inquiry"]["fieldtype"], "Link")
        self.assertEqual(fields["reception_inquiry"]["options"], "TH Reception Inquiry")
        self.assertFalse(fields["reception_inquiry"].get("reqd"))

if __name__ == "__main__":
    unittest.main()
