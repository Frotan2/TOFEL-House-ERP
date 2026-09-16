"""Static guards for the disposable TOEFL House product restore rehearsal."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = (ROOT / "tools/placement/run_native.py").read_text(encoding="utf-8")
HELPER = (ROOT / "tools/placement/runtime_restore.py").read_text(encoding="utf-8")


class ProductRestoreContractTests(unittest.TestCase):
    def test_helper_is_limited_to_disposable_hosted_sites(self):
        self.assertIn('os.environ.get("GITHUB_ACTIONS") != "true"', HELPER)
        self.assertIn('SOURCE_SITE = "placement-test.localhost"', HELPER)
        self.assertIn('RESTORE_SITE = "placement-restore.localhost"', HELPER)
        self.assertIn('("capture", SOURCE_SITE), ("verify", RESTORE_SITE)', HELPER)

    def test_snapshot_covers_each_implemented_domain_and_private_file(self):
        for doctype in (
            "TH Placement Decision", "TH Admission Decision", "Program Enrollment",
            "Student Group", "Course Schedule", "Student Attendance",
            "TH Instructor Contract", "TH Teaching Assignment", "TH Correction Request",
            "Fees", "Sales Invoice",
        ):
            self.assertIn(f'"{doctype}"', HELPER)
        self.assertIn('"doctype": "File"', HELPER)
        self.assertIn('"is_private": 1', HELPER)
        self.assertIn("private_file_sha256_verified", HELPER)
        self.assertIn("name_digest", HELPER)

    def test_runner_creates_separate_restore_site_and_preserves_non_database_config(self):
        for token in (
            "capture-product-restore-snapshot", "backup-placement-test-with-files",
            "placement-restore.localhost", "restore-placement-test-with-files",
            "verify-product-restore-snapshot", "PLACEMENT_RESTORE_EXPECTATION",
            "PLACEMENT_RESTORE_REPORT", "source_db_credentials_copied"
        ):
            self.assertIn(token, RUNNER)
        self.assertIn("'--with-public-files'", RUNNER)
        self.assertIn("'--with-private-files'", RUNNER)
        self.assertIn("assert source_config['db_name'] != restore_config['db_name']", RUNNER)
        self.assertIn("assert source_config.get('db_password') != restore_config.get('db_password')", RUNNER)
        self.assertIn("restore_config['encryption_key'] = source_config['encryption_key']", RUNNER)

    def test_runner_handles_hosted_mysql_client_to_mariadb_backup_compatibility(self):
        self.assertIn("dump_binary = shutil.which('mysqldump')", RUNNER)
        self.assertIn("' --column-statistics=0'", RUNNER)
        self.assertIn("if '--column-statistics' in dump_help", RUNNER)
        self.assertIn("lab/'tools/bin/mysqldump'", RUNNER)


if __name__ == "__main__":
    unittest.main()
