"""Schema + projection-integrity tests for the final closure register (mission §2)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/engineering/final-closure-register.json"
TARGET = ROOT / "docs/engineering/FINAL-CLOSURE-REGISTER.md"

REQUIRED_FIELDS = ("id", "source", "requirement", "current_state", "reason",
                   "dependency", "responsible",
                   "implementation_or_evidence_required", "acceptance_test",
                   "disposition")
VAGUE = ("TODO", "TBD", "to be determined", "minor remaining",
         "various improvements", "etc.")


class ClosureRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.register = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_every_item_carries_all_required_fields(self):
        for item in self.register["items"]:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, item, item.get("id"))
                self.assertTrue(str(item[field]).strip(), f"{item.get('id')}.{field}")

    def test_ids_unique_and_dispositions_closed_vocabulary(self):
        ids = [item["id"] for item in self.register["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        allowed = set(self.register["dispositions"])
        self.assertEqual(allowed, {"IMPLEMENTABLE NOW", "OWNER DECISION REQUIRED",
                                   "EXTERNAL/UPSTREAM BLOCKED",
                                   "REAL-ENVIRONMENT EVIDENCE REQUIRED",
                                   "INTENTIONALLY DEFERRED", "CLOSED"})
        for item in self.register["items"]:
            self.assertIn(item["disposition"], allowed, item["id"])

    def test_no_vague_placeholders(self):
        blob = json.dumps(self.register)
        for phrase in VAGUE:
            self.assertNotIn(phrase, blob)

    def test_implementable_items_have_no_owner_or_upstream_dependency(self):
        for item in self.register["items"]:
            if item["disposition"] == "IMPLEMENTABLE NOW":
                self.assertNotIn("Owner", item["dependency"], item["id"])
                self.assertNotIn("Upstream", item["dependency"], item["id"])

    def test_projection_is_current(self):
        before = TARGET.read_text(encoding="utf-8")
        result = subprocess.run([sys.executable,
                                 "tools/foundation/project_closure_register.py"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = TARGET.read_text(encoding="utf-8")
        self.assertEqual(before, after, "FINAL-CLOSURE-REGISTER.md drifted from its JSON source")

    def test_active_branch_matches_session_boundary(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "session_branch", ROOT / "tools/session_branch.py")
        boundary = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(boundary)
        self.assertEqual(self.register["active_branch"], boundary.ACTIVE_BRANCH)


if __name__ == "__main__":
    unittest.main()
