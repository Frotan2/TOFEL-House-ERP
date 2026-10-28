"""Foundation restore rehearsal must be explicitly disposable and isolated.

Do not loosen the production restore policy in product/restore.py.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools/foundation/runtime_install.py"
RESTORE = ROOT / "product/restore.py"


class FoundationRehearsalRestoreTests(unittest.TestCase):
    def test_disposable_target_is_explicitly_in_product_restore_payload(self):
        tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "product_restore"]
        self.assertEqual(len(funcs), 1)
        payloads = [n for n in ast.walk(funcs[0])
                    if isinstance(n, ast.Dict)]
        self.assertTrue(any(
            isinstance(key, ast.Constant) and key.value == "target"
            and isinstance(value, ast.Constant) and value.value == "disposable"
            for node in payloads for key, value in zip(node.keys, node.values)
        ), "Foundation native restore rehearsal must opt in to disposable mode")

    def test_rehearsal_target_name_is_restore_named(self):
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn('restored_site = "restore.localhost"', source)
        self.assertIn('create_site("new-restore-site", restored_site, restore_password)', source)
        self.assertIn('product_restore("restore-with-files", restored_site, backup_set', source)

    def test_production_restore_still_requires_two_approvers(self):
        source = RESTORE.read_text(encoding="utf-8")
        self.assertIn('EMERGENCY_RESTORE_KEY_PURPOSE = "emergency-restore"', source)
        self.assertIn('EMERGENCY_APPROVER_ROLES', source)
        self.assertIn('PRODUCTION_SITE =', source)
        self.assertIn('"production"', source)
        self.assertIn('"disposable"', source)


if __name__ == "__main__":
    unittest.main()
