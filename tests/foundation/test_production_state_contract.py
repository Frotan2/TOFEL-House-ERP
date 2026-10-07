"""A PRODUCTION site mode must never be presented as release approval."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/toefl_house/toefl_house"


class ProductionStateContractTests(unittest.TestCase):
    def test_control_snapshot_exposes_mode_and_authorization_as_distinct_keys(self):
        source = (APP / "administration.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "get_control_center_snapshot")
        returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
        self.assertEqual(len(returns), 1)
        result = ast.unparse(returns[0].value)
        self.assertIn("site_mode", result)
        self.assertIn("production_authorization", result)
        self.assertNotIn("production_state", result)
        self.assertIn('PRODUCTION_AUTHORIZATION = "REJECT"', source)
        self.assertIn("security.site_mode()", result)

    def test_owner_cockpit_labels_operational_mode_and_release_approval_separately(self):
        source = (APP / "desk/owner.py").read_text(encoding="utf-8")
        self.assertIn('"label": "Site operational mode"', source)
        self.assertIn('"label": "Production authorization"', source)
        self.assertIn('"value": "REJECT"', source)
        self.assertIn('def _site_mode()', source)
        self.assertIn('return security.site_mode()', source)
        self.assertNotIn('"label": "Production"', source)

    def test_command_attention_ui_has_no_mode_authorization_conflation(self):
        source = (APP / "public/js/th_command_pages.js").read_text(encoding="utf-8")
        self.assertIn('snapshot.site_mode || "REFUSED"', source)
        self.assertIn('snapshot.production_authorization || "REJECT"', source)
        self.assertNotIn("snapshot.production_state", source)
        self.assertIn('reject: "danger"', source)

    def test_product_status_and_owner_activation_keep_release_rejected(self):
        source = (ROOT / "product/activate.py").read_text(encoding="utf-8")
        self.assertIn('PRODUCTION_AUTHORIZATION = "REJECT"', source)
        self.assertIn('print(f"Production authorization: {PRODUCTION_AUTHORIZATION}")', source)
        self.assertIn("PRODUCTION site mode is not approval", source)

    def test_native_posture_probe_uses_distinct_mode_and_authorization_facts(self):
        source = (ROOT / "tools/native/native_checks.py").read_text(encoding="utf-8")
        self.assertIn("posture['Site operational mode']=='SYNTHETIC'", source)
        self.assertIn("posture['Production authorization']=='REJECT'", source)
        self.assertNotIn("posture['Production']", source)


if __name__ == "__main__":
    unittest.main()
