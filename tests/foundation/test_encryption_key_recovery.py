"""Guards for the native site encryption key surviving backup -> restore.

Regression coverage for the defect that made the hosted runtime probe report
``site_encryption_key_restored: false``. Frappe writes ``encryption_key`` into
``sites/<site>/site_config.json`` *lazily*, on the first call to
``get_encryption_key()``; ``bench new-site`` does not create it. The source site
therefore had no key when the first backup was taken, and the harness copied it
across only ``if "encryption_key" in original_config`` - a silent no-op that was
recorded as a passive observation rather than a failure.

The lifecycle functions are executed for real in this file: ``fingerprint_key``
and ``restore_key_into_config`` are pure and importable, and the hosted harness
imports that same helper rather than re-implementing it. Ordering and
fail-closed wiring *inside* the harness is asserted statically, because it
cannot execute without a disposable GitHub-hosted runner and real MariaDB.
The actual PASS comes from the hosted runtime run, never from this file.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from runtime_encryption_key import (  # noqa: E402
    assert_no_plaintext_at_rest,
    as_bytes,
    fingerprint_key,
    restore_key_into_config,
    stored_representations,
)

PROBE = (ROOT / "tools/foundation/runtime_encryption_key.py").read_text(encoding="utf-8")
HARNESS = (ROOT / "tools/foundation/runtime_install.py").read_text(encoding="utf-8")

KEY = "a" * 44
SOURCE = {"db_name": "src_db", "db_password": "src_pw", "encryption_key": KEY, "host_name": "foundation.localhost"}
RESTORE = {"db_name": "rst_db", "db_password": "rst_pw", "db_host": "127.0.0.1"}


class NativeEncryptionKeyHelperTests(unittest.TestCase):
    """Executed tests against the real helper the harness calls."""

    def test_fingerprint_never_returns_key_material(self):
        digest = fingerprint_key(KEY)
        self.assertEqual(digest["key_length"], len(KEY))
        self.assertEqual(len(digest["sha256"]), 64)
        self.assertNotIn(KEY, json.dumps(digest))
        self.assertEqual(sorted(digest), ["key_length", "sha256"])

    def test_fingerprint_is_stable_and_key_sensitive(self):
        self.assertEqual(fingerprint_key(KEY)["sha256"], fingerprint_key(KEY)["sha256"])
        self.assertNotEqual(fingerprint_key(KEY)["sha256"], fingerprint_key(KEY[:-1] + "b")["sha256"])

    def test_fingerprint_rejects_missing_or_non_string_key(self):
        for bad in (None, "", 0, {}, []):
            with self.assertRaises(ValueError):
                fingerprint_key(bad)

    def test_restore_carries_key_and_preserves_restore_identity(self):
        result = restore_key_into_config(SOURCE, RESTORE)
        self.assertEqual(result["encryption_key"], KEY)
        self.assertEqual(result["db_name"], "rst_db")
        self.assertEqual(result["db_password"], "rst_pw")
        self.assertNotIn("host_name", result)

    def test_restore_fails_closed_when_source_has_no_key(self):
        """The exact regression: a keyless source must stop the run."""
        for source in (
            {**SOURCE, "encryption_key": None},
            {**SOURCE, "encryption_key": ""},
            {k: v for k, v in SOURCE.items() if k != "encryption_key"},
        ):
            with self.assertRaises(ValueError):
                restore_key_into_config(source, RESTORE)

    def test_restore_refuses_same_database(self):
        with self.assertRaises(ValueError):
            restore_key_into_config(SOURCE, {**RESTORE, "db_name": "src_db"})

    def test_restore_refuses_reused_source_credentials(self):
        with self.assertRaises(ValueError):
            restore_key_into_config(SOURCE, {**RESTORE, "db_password": "src_pw"})

    def test_restore_requires_declared_databases(self):
        with self.assertRaises(ValueError):
            restore_key_into_config({**SOURCE, "db_name": ""}, RESTORE)
        with self.assertRaises(ValueError):
            restore_key_into_config(SOURCE, {**RESTORE, "db_name": None})

    def test_restore_does_not_mutate_its_inputs(self):
        source_copy, restore_copy = dict(SOURCE), dict(RESTORE)
        restore_key_into_config(source_copy, restore_copy)
        self.assertEqual(source_copy, SOURCE)
        self.assertEqual(restore_copy, RESTORE)


class StubDB:
    """Minimal stand-in for ``frappe.db``.

    Used only to exercise the control flow of our own enumeration helper. This
    is contract coverage of repository logic, not evidence about Frappe's
    storage layout; the hosted runtime run supplies that.
    """

    def __init__(self, auth_rows=None, column=None, auth_raises=False, column_raises=False):
        self.auth_rows = auth_rows or []
        self.column = column
        self.auth_raises = auth_raises
        self.column_raises = column_raises
        self.queries = []

    def sql(self, query, values=None):
        self.queries.append(query)
        if self.auth_raises:
            raise RuntimeError("__Auth is not available")
        return self.auth_rows

    def get_value(self, doctype, name, fieldname):
        if self.column_raises:
            raise RuntimeError("column is not readable")
        return self.column


class EncryptedFieldStorageTests(unittest.TestCase):
    """Regression coverage for the failure observed in hosted run 35131838300.

    The first hosted attempt at this fix asserted on the raw model column and
    died with ``Password field was not stored as ciphertext``: Frappe left
    ``tabUser.api_secret`` empty while the encrypted value lived elsewhere, so
    ``not stored`` was true even though encryption had succeeded. The probe now
    enumerates supported storage locations instead of assuming one.
    """

    def test_locates_ciphertext_when_the_model_column_is_null(self):
        token = b"gAAAAABm-ciphertext-token"
        located = stored_representations(
            StubDB(auth_rows=[(token,)], column=None), "User", "Administrator", "api_secret")
        self.assertEqual(located, [("__Auth.password", token)])

    def test_locates_ciphertext_held_in_the_model_column(self):
        located = stored_representations(
            StubDB(auth_rows=[], column="AESBLOB"), "User", "Administrator", "api_secret")
        self.assertEqual(located, [("tabUser.api_secret", "AESBLOB")])

    def test_locates_both_and_orders_auth_first(self):
        located = stored_representations(
            StubDB(auth_rows=[("auth-token",)], column="column-token"),
            "User", "Administrator", "api_secret")
        self.assertEqual([loc for loc, _ in located], ["__Auth.password", "tabUser.api_secret"])

    def test_preferred_location_is_moved_to_the_front(self):
        located = stored_representations(
            StubDB(auth_rows=[("auth-token",)], column="column-token"),
            "User", "Administrator", "api_secret", preferred="tabUser.api_secret")
        self.assertEqual(located[0], ("tabUser.api_secret", "column-token"))

    def test_returns_nothing_when_no_representation_is_stored(self):
        for db in (StubDB(), StubDB(auth_rows=[(None,)], column=""),
                   StubDB(auth_rows=[("",)], column=b"")):
            self.assertEqual(
                stored_representations(db, "User", "Administrator", "api_secret"), [])

    def test_survives_a_missing_auth_table_or_unreadable_column(self):
        self.assertEqual(
            stored_representations(StubDB(auth_raises=True, column="ct"),
                                   "User", "Administrator", "api_secret"),
            [("tabUser.api_secret", "ct")])
        self.assertEqual(
            stored_representations(StubDB(auth_rows=[("tok",)], column_raises=True),
                                   "User", "Administrator", "api_secret"),
            [("__Auth.password", "tok")])
        self.assertEqual(
            stored_representations(StubDB(auth_raises=True, column_raises=True),
                                   "User", "Administrator", "api_secret"), [])

    def test_plaintext_at_rest_is_rejected_in_any_location(self):
        secret = "synthetic-masked-secret"
        for located in (
            [("__Auth.password", secret)],
            [("tabUser.api_secret", secret)],
            [("__Auth.password", b"cipher"), ("tabUser.api_secret", secret)],
            [("tabUser.api_secret", secret.encode())],
        ):
            with self.assertRaises(AssertionError):
                assert_no_plaintext_at_rest(located, secret)

    def test_plaintext_at_rest_check_requires_a_location(self):
        with self.assertRaises(AssertionError):
            assert_no_plaintext_at_rest([], "synthetic-masked-secret")

    def test_ciphertext_proof_is_fingerprint_only_and_deterministic(self):
        secret = "synthetic-masked-secret"
        located = [("__Auth.password", b"gAAAAABm-token")]
        proof = assert_no_plaintext_at_rest(located, secret)
        self.assertEqual(proof["storage_location"], "__Auth.password")
        self.assertEqual(proof["storage_locations_found"], ["__Auth.password"])
        self.assertEqual(len(proof["ciphertext_sha256"]), 64)
        self.assertEqual(proof, assert_no_plaintext_at_rest(located, secret))
        serialized = json.dumps(proof)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("gAAAAABm-token", serialized)

    def test_as_bytes_treats_bytes_and_str_equivalently(self):
        self.assertEqual(as_bytes(b"abc"), as_bytes("abc"))
        self.assertEqual(as_bytes(bytearray(b"abc")), b"abc")
        self.assertNotEqual(as_bytes(b"abc"), as_bytes("abd"))


class ProbeContainmentTests(unittest.TestCase):
    def test_probe_refuses_to_run_outside_a_hosted_runner(self):
        """Executed: the guard must fail closed on any non-Actions machine."""
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/foundation/runtime_encryption_key.py"),
             "initialize", "foundation.localhost"],
            capture_output=True, text=True, cwd=str(ROOT),
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Disposable hosted", completed.stderr + completed.stdout)

    def test_probe_is_limited_to_disposable_sites_and_actions(self):
        self.assertIn('os.environ.get("GITHUB_ACTIONS") != "true"', PROBE)
        self.assertIn('("initialize", "foundation.localhost")', PROBE)
        self.assertIn('("verify", "restore.localhost")', PROBE)
        self.assertIn('("verify", "recovery.localhost")', PROBE)
        self.assertNotIn('("verify", "foundation.localhost")', PROBE)

    def test_probe_never_reports_key_or_secret_plaintext(self):
        """Only fingerprints, byte lengths and pass/fail may reach evidence."""
        self.assertIn("fingerprint_file.chmod(0o600)", PROBE)
        self.assertIn("key and secret omitted", PROBE)
        # The persisted evidence must be built from the digest, never the key.
        self.assertNotIn('"encryption_key": native_key', PROBE)
        self.assertNotIn('"encryption_key": key', PROBE)
        self.assertNotIn('print(native_key', PROBE)
        self.assertIn("native_key = get_encryption_key()", PROBE)
        # The raw-column-only check that failed in hosted run 35131838300 must
        # not come back: an empty model column does not mean encryption failed.
        self.assertNotIn("Password field was not stored as ciphertext", PROBE)
        self.assertIn("assert_no_plaintext_at_rest(located, secret)", PROBE)
        self.assertIn("get_decrypted_password(", PROBE)
        self.assertIn("set_encrypted_password(", PROBE)

    def test_probe_uses_only_native_application_mechanisms(self):
        self.assertIn("from frappe.utils.password import", PROBE)
        self.assertIn("frappe.utils.password.get_encryption_key", PROBE)
        # No hand-rolled cryptography.
        for forbidden in ("from cryptography", "import nacl", "Fernet(", "os.urandom"):
            self.assertNotIn(forbidden, PROBE)


class HarnessWiringTests(unittest.TestCase):
    """Static guards on ordering inside the hosted harness.

    These cannot execute locally (no disposable runner, no real MariaDB); they
    exist so the fix cannot silently regress. Execution evidence is the hosted
    runtime run.
    """

    def test_harness_uses_the_shared_helper_instead_of_reimplementing_it(self):
        self.assertIn("from runtime_encryption_key import restore_key_into_config", HARNESS)
        self.assertEqual(HARNESS.count("restore_key_into_config(original_config"), 2,
                         "both the first restore and the hardened recovery must use the helper")
        # The silent conditional that caused the defect must be gone.
        self.assertNotIn('if "encryption_key" in original_config:', HARNESS)
        self.assertNotIn("if original_config.get(\"encryption_key\"):", HARNESS)

    def test_harness_initializes_the_key_before_the_first_backup(self):
        initialize = HARNESS.index("initialize-native-site-encryption-key")
        prepare = HARNESS.index("prepare-native-encrypted-fixture-before-backup")
        first_backup = HARNESS.index("bench(\"backup-with-files\"")
        self.assertLess(initialize, prepare, "the key must exist before the encrypted fixture")
        self.assertLess(prepare, first_backup, "ciphertext must be written before the backup")
        # Both lifecycle steps must actually invoke the native probe in the
        # bench sites directory, where site_config.json lives.
        self.assertIn('"initialize", site], cwd=bench_dir / "sites")', HARNESS)
        self.assertIn('"prepare", site], cwd=bench_dir / "sites")', HARNESS)

    def test_harness_fails_closed_when_the_key_does_not_survive_restore(self):
        for token in (
            "verify-encryption-key-survived-restore",
            "verify-encryption-key-survived-hardened-recovery",
            'raise RuntimeError("Restored site could not decrypt content encrypted before the backup")',
            'raise RuntimeError("Hardened recovery site could not decrypt content encrypted before the backup")',
            "fingerprint_matches_source",
            "encrypted_content_decrypts_after_restore",
            "ciphertext_matches_source",
        ):
            self.assertIn(token, HARNESS)
        # The reported flag must be derived from verification, not from presence.
        self.assertIn('report["site_encryption_key_restored"] = bool(', HARNESS)
        self.assertIn('report["site_encryption_key_restored_hardened"] = bool(', HARNESS)
        self.assertNotIn('report["site_encryption_key_restored"] = "encryption_key" in original_config', HARNESS)

    def test_hardened_cycle_rerecords_ciphertext_before_its_own_backup(self):
        """Fernet output is randomized per encryption, so each backup cycle needs
        its own recorded ciphertext digest; comparing against the first cycle's
        would make the hardened verification fail for the wrong reason."""
        hardened_prepare = HARNESS.index("prepare-native-encrypted-fixture-before-hardened-backup")
        hardened_backup = HARNESS.index('bench("hardened-backup-with-files"')
        hardened_verify = HARNESS.index("verify-encryption-key-survived-hardened-recovery")
        self.assertLess(hardened_prepare, hardened_backup)
        self.assertLess(hardened_backup, hardened_verify)
        self.assertIn("encryption-key-hardened-prepare.json", HARNESS)
        self.assertIn('"ciphertext_sha256": ciphertext,', PROBE)
        self.assertIn('if ciphertext != recorded.get("ciphertext_sha256"):', PROBE)

    def test_probe_verify_refuses_to_run_on_the_source_site(self):
        """Key survival is only meaningful on a site that is not the source."""
        self.assertIn('if site == recorded["source_site"]:', PROBE)
        self.assertIn('"restored_site_is_not_source": True', PROBE)
        self.assertNotIn('("verify", "foundation.localhost")', PROBE)

    def test_harness_verifies_restore_after_each_restore_cycle(self):
        restore_verify = HARNESS.index("verify-encryption-key-survived-restore")
        hardened_verify = HARNESS.index("verify-encryption-key-survived-hardened-recovery")
        restore_invariants = HARNESS.index('run("restore-verification"')
        hardened_invariants = HARNESS.index('run("hardened-recovery-invariants"')
        self.assertLess(restore_verify, restore_invariants)
        self.assertLess(hardened_verify, hardened_invariants)

    def test_harness_keeps_the_fingerprint_out_of_published_evidence(self):
        """The fingerprint lives in the private runner lab, never in evidence.

        ``lab`` is created 0700 under RUNNER_TEMP and is not the published
        evidence directory (``.foundation/runtime-evidence``), so key custody
        material cannot be uploaded as an artifact. FOUNDATION_LAB must keep
        pointing at ``lab`` itself: ``redact()`` reads ``lab /
        "captured-session.json`` written by the session tool through the same
        variable, so redirecting it to a subdirectory would silently stop
        captured-session values from being redacted.
        """
        self.assertIn("lab.mkdir(mode=0o700)", HARNESS)
        self.assertIn('env["FOUNDATION_LAB"] = str(lab)', HARNESS)
        self.assertIn('lab = Path(os.environ["RUNNER_TEMP"]) / "foundation-runtime"', HARNESS)
        # Evidence-side files hold verification results only, not the key.
        self.assertIn("encryption-key-initialize.json", HARNESS)
        self.assertIn("encryption-key-prepare.json", HARNESS)
        self.assertIn("encryption-key-restore-verify.json", HARNESS)
        self.assertIn("encryption-key-hardened-verify.json", HARNESS)
        # The fingerprint file itself is named only by the probe, which writes it
        # 0600 inside FOUNDATION_LAB - never into the evidence directory.
        self.assertNotIn("site-encryption-key-fingerprint.json", HARNESS)
        self.assertIn("site-encryption-key-fingerprint.json", PROBE)
        self.assertIn('fingerprint_file = private_dir / FINGERPRINT_FILE', PROBE)
        self.assertIn("fingerprint_file.chmod(0o600)", PROBE)


class FingerprintRoundTripTests(unittest.TestCase):
    """Executed end-to-end against real site_config.json files on disk."""

    def test_fingerprint_round_trips_through_site_config_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "foundation.localhost"
            restore_dir = Path(tmp) / "restore.localhost"
            source_dir.mkdir()
            restore_dir.mkdir()
            (source_dir / "site_config.json").write_text(json.dumps(SOURCE))

            from runtime_encryption_key import read_config_fingerprint

            recorded = read_config_fingerprint(source_dir / "site_config.json")
            restored = restore_key_into_config(SOURCE, RESTORE)
            (restore_dir / "site_config.json").write_text(json.dumps(restored))
            self.assertEqual(
                read_config_fingerprint(restore_dir / "site_config.json")["sha256"],
                recorded["sha256"],
            )
            self.assertNotIn(KEY, json.dumps(recorded))


if __name__ == "__main__":
    unittest.main()
