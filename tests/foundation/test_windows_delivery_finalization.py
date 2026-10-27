"""Windows delivery finalization contracts (Agent 4 scope).

Covers the Windows installer/launcher, Start/Stop/Repair lifecycle, package
integrity and exact-version checks, updater failure semantics and customer
onboarding documents. These are static, Linux-safe contracts: they pin the
fail-closed wording and ordering that a nontechnical operator depends on.
They do not substitute for real Windows + Docker Desktop qualification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "product" / "windows"


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


INSTALL = read_utf8(WINDOWS / "Install TOEFL House ERP.cmd")
START = read_utf8(WINDOWS / "Start TOEFL House ERP.cmd")
STOP = read_utf8(WINDOWS / "Stop TOEFL House ERP.cmd")
REPAIR = read_utf8(WINDOWS / "Repair TOEFL House ERP.cmd")
GUI = read_utf8(WINDOWS / "TOEFL House ERP.ps1")
WORKER = read_utf8(WINDOWS / "Run TOEFL House ERP.ps1")
CHECK_PC = read_utf8(WINDOWS / "Check This PC.ps1")
FRESH_PREFLIGHT = read_utf8(WINDOWS / "Test Fresh Installation.ps1")
EXISTING_PREFLIGHT = read_utf8(WINDOWS / "Test Existing Installation.ps1")
VERIFY = read_utf8(WINDOWS / "Verify Package Image.ps1")
PS1_PACKAGER = read_utf8(WINDOWS / "Prepare Customer Package.ps1")
PY_PACKAGER = read_utf8(ROOT / "tools" / "release" / "create_customer_package.py")
UPDATE = read_utf8(WINDOWS / "Update TOEFL House ERP.ps1")
CATALOG = json.loads(read_utf8(WINDOWS / "updater-strings.json"))
HANDBOOK = read_utf8(WINDOWS / "OWNER HANDBOOK.txt")
OWNER_GUIDE = read_utf8(WINDOWS / "OWNER ACCEPTANCE GUIDE.txt")
DAILY_GUIDE = read_utf8(WINDOWS / "DAILY USE GUIDE.txt")

CUSTOMER_CMDS = (("Install", INSTALL), ("Start", START),
                 ("Stop", STOP), ("Repair", REPAIR))
CUSTOMER_PS1 = (("GUI", GUI), ("worker", WORKER), ("Check This PC", CHECK_PC),
                ("fresh preflight", FRESH_PREFLIGHT),
                ("existing preflight", EXISTING_PREFLIGHT),
                ("verifier", VERIFY), ("updater", UPDATE))


def code_lines(script: str) -> str:
    """CMD source without REM comments (comments may discuss FOR freely)."""
    kept = []
    for line in script.splitlines():
        if re.match(r"(?i)^\s*rem(\s|$)", line):
            continue
        kept.append(line)
    return "\n".join(kept)


class OwnerHandbookDeliveryTests(unittest.TestCase):
    def test_gui_opens_the_handbook_read_only(self):
        self.assertIn('$handbookFile = Join-Path $PSScriptRoot "OWNER HANDBOOK.txt"', GUI)
        self.assertIn('"Owner Handbook"', GUI)
        self.assertIn("$handbookButton.Add_Click", GUI)
        self.assertIn("$handbookButton.Enabled", GUI)
        self.assertIn("Owner handbook is missing. Ask your provider for a complete installer.", GUI)
        # The smoke test must fail if the handbook wiring regresses.
        self.assertIn('$handbookButton.Text -ne "Owner Handbook"', GUI)
        self.assertIn("-not (Test-Path -LiteralPath $handbookFile -PathType Leaf)", GUI)

    def test_both_packagers_ship_the_handbook_and_exclude_data_controls(self):
        ps1_section = PS1_PACKAGER.split("$files = @(", 1)[1].split("\n    )", 1)[0]
        self.assertIn('"product/windows/OWNER HANDBOOK.txt"', ps1_section)
        self.assertIn('"product/windows/OWNER HANDBOOK.txt"', PY_PACKAGER)
        for name, section in (("PS1 packager", ps1_section), ("Python packager", PY_PACKAGER)):
            for forbidden in ("Backup TOEFL House ERP", "Activate TOEFL House ERP",
                              "Deactivate TOEFL House ERP"):
                self.assertNotIn(forbidden, section, name)

    def test_handbook_describes_the_gated_updater_without_authorizing_it(self):
        for phrase in ("Check for Updates", "Install Update", "signed release",
                       "verified", "backup", "recovery", "NO-GO"):
            self.assertIn(phrase, HANDBOOK, phrase)
        # The updater exists but is safety-gated and channel-disabled; the old
        # "no updater" wording must not contradict the shipped launcher.
        self.assertNotIn("Do not install an updater", HANDBOOK)
        self.assertNotIn("PR #46 remains", HANDBOOK)


class LifecyclePreservationTests(unittest.TestCase):
    def test_no_customer_script_contains_a_destructive_command(self):
        for name, script in CUSTOMER_CMDS:
            with self.subTest(script=name):
                lowered = script.lower()
                self.assertNotIn("docker compose down -v", lowered)
                self.assertNotIn("docker volume rm", lowered)
                self.assertNotIn("docker system prune", lowered)
                self.assertNotIn("git reset --hard", lowered)
        for name, script in CUSTOMER_PS1:
            with self.subTest(script=name):
                self.assertNotIn("docker compose down -v", script)
                self.assertNotIn("docker volume rm", script)
                self.assertNotIn("docker system prune", script)
                self.assertNotIn("git reset --hard", script)

    def test_cmd_launchers_keep_the_proven_linear_style(self):
        # Multiline parenthesized blocks and FOR commands parse differently
        # under LF vs CRLF delivery; the launchers stay linear by design.
        for name, script in CUSTOMER_CMDS:
            with self.subTest(script=name):
                code = code_lines(script)
                self.assertIsNone(
                    re.search(r"(?im)^\s*for[\s/]", code),
                    f"{name} must not use a FOR command",
                )

    def test_install_orders_verification_before_credentials_and_data(self):
        self.assertLess(
            INSTALL.index("Checking package integrity before local installation"),
            INSTALL.index("if not exist data\\secrets mkdir data\\secrets"),
        )
        self.assertLess(
            INSTALL.index("Test Fresh Installation.ps1"),
            INSTALL.index("Generating a private database password"),
        )
        self.assertLess(
            INSTALL.index('docker load -i "release\\toefl-house-erp-app.tar"'),
            INSTALL.index("docker compose up -d --no-build"),
        )

    def test_install_reports_a_changed_package_with_partial_state_guidance(self):
        self.assertIn("if errorlevel 1 goto :packagechanged", INSTALL)
        self.assertIn("\n:packagechanged", INSTALL)
        changed = INSTALL.split("\n:packagechanged", 1)[1].split("exit /b 1", 1)[0]
        for phrase in ("A partial installation was preserved",
                       "do NOT run Install again",
                       "Check This PC", "Copy Safe Support Status"):
            self.assertIn(phrase, changed, phrase)

    def test_repair_binds_the_loaded_image_to_the_verified_manifest(self):
        self.assertLess(
            REPAIR.index('docker load -i "release\\toefl-house-erp-app.tar"'),
            REPAIR.index("-VerifyLoadedImage"),
        )
        self.assertLess(
            REPAIR.index("-VerifyLoadedImage"),
            REPAIR.index("docker compose up -d"),
        )
        # A bare tag-existence check cannot prove exact-version identity.
        self.assertNotIn("docker image inspect toefl-house-erp-app:local >nul", REPAIR)

    def test_unknown_storage_is_never_classified_as_disposable(self):
        self.assertIn("Could not check existing database storage", FRESH_PREFLIGHT)
        self.assertIn("no password was generated", FRESH_PREFLIGHT.lower())
        self.assertIn("Do NOT assume a fresh installation", CHECK_PC)
        self.assertIn("could not be ruled out", CHECK_PC)
        for name, script in (("Start", START), ("Repair", REPAIR)):
            self.assertIn("Test Fresh Installation.ps1", script, name)
            self.assertIn("NOT proof that old data cannot exist elsewhere", script, name)


class PackageIntegrityTests(unittest.TestCase):
    def test_verifier_keeps_the_non_production_safety_gate(self):
        self.assertIn("TEST PACKAGE - NO REAL DATA", VERIFY)
        self.assertIn("production_authorization", VERIFY)
        self.assertIn('"REJECT"', VERIFY)
        self.assertIn("org.toefl-house.source-eol", VERIFY)
        self.assertIn("toefl-house-erp-app:local", VERIFY)
        self.assertNotIn("docker load", VERIFY)

    def test_customer_kit_never_builds_from_source(self):
        for name, script in (("Install", INSTALL), ("Repair", REPAIR)):
            with self.subTest(script=name):
                self.assertNotIn("docker build", script)
                self.assertNotIn("docker compose build", script)
                self.assertNotIn("--build", script)
                self.assertNotIn("Normalize Product Sources.ps1", script)
                self.assertIn(":packagemissing", script)


class UpdaterFailureSemanticsTests(unittest.TestCase):
    def test_documented_exit_codes_are_stable(self):
        self.assertIn("$script:ExitAllowed = 0", UPDATE)
        self.assertIn("$script:ExitRefused = 3", UPDATE)
        self.assertIn("$script:ExitRequestInvalid = 4", UPDATE)
        self.assertIn("$script:ExitFailed = 5", UPDATE)
        self.assertIn("$script:ExitRecoveryRequired = 6", UPDATE)

    def test_a_failed_update_demands_a_recovery_decision(self):
        self.assertIn('Set-JournalState "recovery-required"', UPDATE)
        self.assertIn('"updater.recovery_required"', UPDATE)
        self.assertIn('"updater.recovery_steps"', UPDATE)
        # Best-effort retag of the previous image is not an automatic restart.
        self.assertIn("never means safe automatic restart", UPDATE)
        self.assertIn("Never start the", UPDATE)

    def test_recovery_catalogue_entries_are_bilingual(self):
        for key in ("updater.recovery_required", "updater.recovery_steps",
                    "updater.rollback_done", "updater.rollback_blocked",
                    "updater.completed", "updater.failed"):
            entry = CATALOG["launcher"][key]
            self.assertTrue(entry["en"].strip(), key)
            self.assertTrue(entry["fa"].strip(), key)
            self.assertRegex(entry["fa"], r"[\u0600-\u06FF\u200c]", key)


if __name__ == "__main__":
    unittest.main()
