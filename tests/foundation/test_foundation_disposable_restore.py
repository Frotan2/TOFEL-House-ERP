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

    def test_hardened_restore_site_matches_all_native_recovery_probes(self):
        """A disposable fixture must use one restore-named site throughout.

        This regression would have detected the hosted gate failure where
        hardened restore completed but a native secret verifier still accepted
        only the obsolete recovery.localhost name.
        """
        site = "restore-recovery.localhost"
        sources = {
            "install": HARNESS.read_text(encoding="utf-8"),
            "encryption": (ROOT / "tools/foundation/runtime_encryption_key.py").read_text(encoding="utf-8"),
            "secret": (ROOT / "tools/foundation/runtime_recovery_secret.py").read_text(encoding="utf-8"),
            "session": (ROOT / "tools/foundation/runtime_recovery_session.py").read_text(encoding="utf-8"),
            "isolation": (ROOT / "tools/foundation/runtime_isolation.py").read_text(encoding="utf-8"),
        }
        self.assertIn(f'recovered_site = "{site}"', sources["install"])
        self.assertIn(f'{site} {site};', sources["install"])
        self.assertIn(f'"{site}", "upstream-tests.localhost"', sources["install"])
        self.assertIn(f'("verify", "{site}")', sources["encryption"])
        self.assertIn(f'["verify", "{site}"]', sources["secret"])
        self.assertIn(f"('{site}',403)", sources["session"])
        self.assertIn(site, sources["isolation"])
        self.assertNotIn("'recovery.localhost'", sources["isolation"])
        self.assertNotIn('recovered_site = "recovery.localhost"', sources["install"])
        self.assertNotIn('["verify", "recovery.localhost"]', sources["secret"])
        # The full native restore policy remains in force for this fixture.
        self.assertIn('target = payload.get("target", "production")',
                      RESTORE.read_text(encoding="utf-8"))
        self.assertIn('if target == "disposable" and (site == PRODUCTION_SITE or "restore" not in site)',
                      RESTORE.read_text(encoding="utf-8"))

    def test_production_restore_still_requires_two_approvers(self):
        source = RESTORE.read_text(encoding="utf-8")
        self.assertIn('EMERGENCY_RESTORE_KEY_PURPOSE = "emergency-restore"', source)
        self.assertIn('EMERGENCY_APPROVER_ROLES', source)
        self.assertIn('PRODUCTION_SITE =', source)
        self.assertIn('"production"', source)
        self.assertIn('"disposable"', source)


if __name__ == "__main__":
    unittest.main()
