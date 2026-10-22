"""Unit guards for the native synthetic restore rehearsal and restart checks."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_RESTORE_PATH = ROOT / "tools/native/runtime_restore.py"
SPEC = importlib.util.spec_from_file_location("native_runtime_restore_test", RUNTIME_RESTORE_PATH)
RUNTIME_RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME_RESTORE)


class FakeFrappe:
    def __init__(self, root, docs):
        self.root = Path(root)
        self.docs = docs

    def get_site_path(self, *parts):
        return str(self.root.joinpath(*parts))

    def get_all(self, doctype, **kwargs):
        if kwargs.get("pluck")=="name":
            return ["SYN-ROW-1"]
        return [{"name":"SYN-ROW-1","synthetic_value":"preserved"}]

    def get_doc(self, doctype, name):
        return self.docs[name]


class NativeRestoreRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public_dir = self.root / "public" / "files"
        self.private_dir = self.root / "private" / "files"
        self.public_dir.mkdir(parents=True)
        self.private_dir.mkdir(parents=True)
        self.public_bytes = b"synthetic public file"
        self.private_bytes = b"synthetic private file"
        self.public_path = self.public_dir / "public-marker.txt"
        self.private_path = self.private_dir / "private-marker.txt"
        self.public_path.write_bytes(self.public_bytes)
        self.private_path.write_bytes(self.private_bytes)
        self.docs = {
            "PUBLIC-FILE": SimpleNamespace(
                name="PUBLIC-FILE", file_name=self.public_path.name,
                file_url="/files/public-marker.txt", is_private=0,
                attached_to_doctype="TH Placement Decision",
                attached_to_name="SYN-DECISION-1",
                get_content=lambda: self.public_bytes),
            "PRIVATE-FILE": SimpleNamespace(
                name="PRIVATE-FILE", file_name=self.private_path.name,
                file_url="/private/files/private-marker.txt", is_private=1,
                attached_to_doctype="TH Placement Decision",
                attached_to_name="SYN-DECISION-1",
                get_content=lambda: self.private_bytes),
        }
        self.frappe = FakeFrappe(self.root, self.docs)

    def _file_expected(self, doc, content, path):
        stat = path.stat()
        import hashlib
        return {
            "name": doc.name,
            "file_name": doc.file_name,
            "file_url": doc.file_url,
            "is_private": int(doc.is_private),
            "attached_to_doctype": doc.attached_to_doctype,
            "attached_to_name_digest": hashlib.sha256(
                doc.attached_to_name.encode()).hexdigest(),
            "sha256": hashlib.sha256(content).hexdigest(),
            "storage": {
                "size": stat.st_size,
                "mode": stat.st_mode & 0o777,
                "uid": stat.st_uid,
                "gid": stat.st_gid,
            },
        }

    def _expected(self):
        return {
            "status": "captured",
            "scope": "synthetic test",
            "doctypes": {
                "TH Test": {
                    "count": 1,
                    "name_digest": RUNTIME_RESTORE._digest(["SYN-ROW-1"]),
                    "row_digest": RUNTIME_RESTORE._row_digest(
                        [{"name":"SYN-ROW-1","synthetic_value":"preserved"}]),
                }
            },
            "files": {
                "public_file": self._file_expected(
                    self.docs["PUBLIC-FILE"], self.public_bytes, self.public_path),
                "private_file": self._file_expected(
                    self.docs["PRIVATE-FILE"], self.private_bytes, self.private_path),
            },
        }

    def test_verifier_checks_both_public_and_private_file_metadata_bytes_and_mode(self):
        result = RUNTIME_RESTORE._verify(self.frappe, self._expected())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(set(result["files_verified"]), {"public_file", "private_file"})
        self.assertTrue(all(
            item["content_sha256_verified"] and item["metadata_verified"]
            for item in result["files_verified"].values()))

    def test_verifier_rejects_changed_public_file_bytes(self):
        expected = self._expected()
        self.docs["PUBLIC-FILE"].get_content = lambda: b"tampered public file"
        with self.assertRaisesRegex(AssertionError, "content digest"):
            RUNTIME_RESTORE._verify(self.frappe, expected)

    def test_verifier_rejects_privacy_url_mismatch(self):
        self.docs["PRIVATE-FILE"].file_url = "/files/private-marker.txt"
        with self.assertRaisesRegex(AssertionError, "File URL"):
            RUNTIME_RESTORE._verify(self.frappe, self._expected())

    def test_verifier_rejects_filesystem_permission_mismatch(self):
        expected = self._expected()
        expected["files"]["private_file"]["storage"]["mode"] ^= 0o100
        with self.assertRaisesRegex(AssertionError, "size/mode/uid/gid"):
            RUNTIME_RESTORE._verify(self.frappe, expected)


class NativeRestartWiringTests(unittest.TestCase):
    def test_restore_target_is_reverified_after_web_service_restart(self):
        text = (ROOT / "tools/native/run_native.py").read_text(encoding="utf-8")
        self.assertIn("placement-restore.localhost", text)
        self.assertIn("verify-product-restore-after-service-restart", text)
        self.assertIn("source_backup_hashes_unchanged", text)
        self.assertIn("shutil.disk_usage(restore_backup_dir).free", text)
        self.assertIn("copy_hashes_verified", text)
        self.assertIn("Isolated restore artifact copy failed size/hash verification", text)
        self.assertIn("isolated-restore-bench", text)
        self.assertIn("'isolated_site_data_root':True", text)
        self.assertIn("'source_sites_root_mounted':False", text)
        self.assertIn("cwd=restore_sites", text)
        self.assertIn("'BENCH_DIR':str(restore_bench)", text)
        # The restored-site health probe is an authenticated login API
        # request (no asset rendering, no get_logged_user-without-session).
        self.assertIn("api/method/login", text)

    def test_isolated_restore_migration_is_runner_only_and_root_bound(self):
        helper=(ROOT/"tools/native/migrate_restore_site.py").read_text(encoding="utf-8")
        self.assertIn('GITHUB_ACTIONS',helper)
        self.assertIn('PLACEMENT_RESTORE_SITES_ROOT',helper)
        self.assertIn('Path.cwd().resolve(strict=True)!=root',helper)
        self.assertIn('SiteMigration().run(site=RESTORE_SITE)',helper)

    def test_all_eight_policy_resolvers_are_compared_across_restart(self):
        text = (ROOT / "tools/native/policy_restart_check.py").read_text(encoding="utf-8")
        for policy in (
            "catalog_linkage", "returning_student", "enrollment_exit", "billing",
            "roster_change", "attendance_correction", "adjustment_posting",
            "owner_operations",
        ):
            self.assertIn(f'"{policy}"', text)
        self.assertIn("Policy state/resolvers changed across service restart", text)


if __name__ == "__main__":
    unittest.main()
