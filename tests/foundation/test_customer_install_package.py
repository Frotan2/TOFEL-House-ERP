"""Contracts for the customer's GUI and prebuilt-image installation path.

No customer may need Git, a terminal, or a source-image rebuild when the
provider has supplied a complete and verified image package. This unit test
does not substitute for an actual Windows/Docker lifecycle qualification.
"""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "product" / "windows"
INSTALL = (WINDOWS / "Install TOEFL House ERP.cmd").read_text()
REPAIR = (WINDOWS / "Repair TOEFL House ERP.cmd").read_text()
START = (WINDOWS / "Start TOEFL House ERP.cmd").read_text()
STOP = (WINDOWS / "Stop TOEFL House ERP.cmd").read_text()
GUI = (WINDOWS / "TOEFL House ERP.ps1").read_text()
WORKER = (WINDOWS / "Run TOEFL House ERP.ps1").read_text()
CHECK_PC = (WINDOWS / "Check This PC.ps1").read_text()
EXISTING_PREFLIGHT = (WINDOWS / "Test Existing Installation.ps1").read_text()
VERIFY = (WINDOWS / "Verify Package Image.ps1").read_text()
PACKAGER = (WINDOWS / "Prepare Customer Package.ps1").read_text()
SHORTCUT = (ROOT / "TOEFL House ERP.vbs").read_text()
OWNER_GUIDE = (WINDOWS / "OWNER ACCEPTANCE GUIDE.txt").read_text()
DAILY_GUIDE = (WINDOWS / "DAILY USE GUIDE.txt").read_text()


class CustomerInstallerContract(unittest.TestCase):
    def test_gui_launcher_opens_without_a_visible_console(self):
        self.assertIn("shell.Run command, 0, False", SHORTCUT)
        self.assertIn("product\\windows\\TOEFL House ERP.ps1", SHORTCUT)
        self.assertIn("System.Windows.Forms", GUI)
        self.assertIn("param([switch]$SmokeTest)", GUI)
        self.assertIn("Windows GUI controls initialized", GUI)
        for button in ('"Install"', '"Open / Start"', '"Repair"', '"Stop"',
                       '"Get Docker Desktop"', '"View Administrator Login"',
                       '"Check This PC"', '"Owner Readiness Guide"', '"How to Use"',
                       '"Copy Safe Support Status"'):
            self.assertIn(button, GUI)
        self.assertIn('"http://127.0.0.1:8000/"', GUI)
        self.assertIn('$script:process', GUI)
        self.assertIn("Add_FormClosing", GUI)
        self.assertIn("TH_GUI_MODE", WORKER)
        self.assertIn("ValidateSet", WORKER)
        self.assertNotIn("Invoke-Expression", GUI + WORKER)

    def test_daily_help_is_an_offline_non_developer_button(self):
        self.assertIn('"product/windows/DAILY USE GUIDE.txt"', PACKAGER)
        self.assertIn('$dailyGuideButton.Add_Click', GUI)
        self.assertIn('$dailyGuideButton.Enabled', GUI)
        self.assertIn('$dailyGuideFile = Join-Path $PSScriptRoot "DAILY USE GUIDE.txt"', GUI)
        self.assertIn("Start-Process -FilePath \"notepad.exe\"", GUI)
        for expected in ("Reception", "Finance", "Teacher", "Owner", "Book",
                         "Open / Start", "NO-GO", "No developer"):
            self.assertIn(expected.lower(), DAILY_GUIDE.lower())
        for forbidden in ("git clone", "git pull", "docker compose", "powershell.exe",
                          "MARIADB_ROOT_PASSWORD="):
            self.assertNotIn(forbidden.lower(), DAILY_GUIDE.lower())
        self.assertNotIn('Start-LauncherAction "Activate"', GUI)

    def test_safe_status_is_read_only_and_privacy_filtered(self):
        self.assertIn('$copyStatusButton.Add_Click', GUI)
        self.assertIn('$script:lastCheckPath = $script:stdoutPath', GUI)
        self.assertIn('$copyStatusButton.Enabled', GUI)
        self.assertIn("Clipboard]::SetText", GUI)
        self.assertIn("arbitrary diagnostic", GUI)
        self.assertIn("NOT approval to use real student", GUI)
        self.assertIn("Run Check This PC first", GUI)
        self.assertIn('    $script:lastCheckPath = ""', GUI)
        self.assertIn('$permitted[$key] -cnotcontains $value', GUI)
        self.assertIn('$seen.Count -ne $permitted.Count', GUI)
        self.assertIn('Not a complete read-only check', GUI)
        self.assertIn('Read-only observation. NOT approval to use real student', GUI)
        self.assertNotIn('$Matches[2]', GUI)
        self.assertNotIn("Clipboard]::SetText((Get-Content", GUI)

    def test_repair_requires_explicit_yes_with_safe_no_default(self):
        self.assertIn('Confirm repair with support', GUI)
        self.assertIn('MessageBoxDefaultButton]::Button2', GUI)
        self.assertIn('Repair cancelled. Your installed data was not changed.', GUI)
        self.assertIn('Start-LauncherAction "Repair"', GUI)
        self.assertNotIn('$repair.Add_Click({ Start-LauncherAction "Repair" })', GUI)

    def test_daily_guide_includes_dari_staff_instructions(self):
        for word in ("صاحب کورس", "ریسپشنیست", "شاگرد", "حاضری",
                     "فروش کتاب", "شهریه", "پشتیبانی"):
            self.assertIn(word, DAILY_GUIDE)

    def test_incomplete_customer_folder_never_attempts_source_build(self):
        # Customer packages deliberately omit app.Dockerfile and all source.
        # Their GUI must refuse a missing archive rather than enter a Docker
        # build path that can never succeed on the customer's computer.
        self.assertIn('Join-Path $productRoot "app.Dockerfile"', GUI)
        self.assertIn('"Incomplete customer package"', GUI)
        self.assertIn("Request a complete package from your provider", GUI)
        self.assertIn("if ($answer -ne [System.Windows.Forms.DialogResult]::Yes)", GUI)

    def test_customer_can_open_error_diagnostics_without_terminal(self):
        self.assertIn("View Details", GUI)
        self.assertIn("$script:stdoutPath", GUI)
        self.assertIn("$script:stderrPath", GUI)
        self.assertIn("$errorLog.Length -gt 0", GUI)
        self.assertIn('Start-Process -FilePath "notepad.exe"', GUI)

    def test_headless_wrapper_never_pauses_or_echoes_first_run_password(self):
        for label, script in (
            ("install", INSTALL), ("repair", REPAIR),
            ("start", START), ("stop", STOP),
        ):
            self.assertNotRegex(script, r"(?m)^pause\s*$", label)
            self.assertIn("if not defined TH_GUI_MODE pause", script, label)
            self.assertIn("[TH_STAGE]", script, label)
        self.assertIn("if defined TH_GUI_MODE goto :nowelcome", INSTALL)
        self.assertIn("first-run-credentials.txt", INSTALL)
        self.assertIn("View Administrator Login", GUI)
        self.assertIn('$action -ne "Check"', GUI)
        self.assertIn('Start-LauncherAction "Check"', GUI)

    def test_hidden_launcher_waits_without_interactive_timeout(self):
        # Windows timeout.exe refuses redirected/noninteractive stdin.
        # PowerShell Start-Sleep works from the hidden GUI worker too.
        for name, script in (("Install", INSTALL), ("Start", START),
                             ("Repair", REPAIR)):
            self.assertNotIn("timeout /t", script, name)
            self.assertIn("Start-Sleep -Seconds", script, name)

    def test_read_only_pc_check_is_packaged_and_never_mutates_existing_data(self):
        self.assertIn('"product/windows/Check This PC.ps1"', PACKAGER)
        self.assertIn('"product/windows/OWNER ACCEPTANCE GUIDE.txt"', PACKAGER)
        self.assertIn('$guideButton.Add_Click', GUI)
        self.assertIn('$guideFile = Join-Path $PSScriptRoot "OWNER ACCEPTANCE GUIDE.txt"', GUI)
        for phrase in ("ENGINEERING CANDIDATE ONLY", "FRESH DISPOSABLE WINDOWS TEST PC",
                       "PRESERVATION", "DO NOT", "NO-GO", "REJECTED", "real student",
                       "Check This PC", "synthetic records",
                       "BOOK SHOP PRACTICE", "Item Group", "Update Stock",
                       "Payment Entry", "Credit Note", "converted synthetic",
                       "not a cash refund"):
            self.assertIn(phrase.lower(), OWNER_GUIDE.lower(), phrase)
        self.assertNotIn("MARIADB_ROOT_PASSWORD=", OWNER_GUIDE)
        self.assertIn('"Check"', WORKER)
        self.assertIn('Read-only PC check', CHECK_PC)
        self.assertIn('Result "Production authorization" "NOT VERIFIED"', CHECK_PC)
        self.assertIn('Get-PSDrive', CHECK_PC)
        self.assertIn('DriveType]::Fixed', CHECK_PC)
        self.assertIn('volume inspect "toefl-house-erp_db-data"', CHECK_PC)
        self.assertIn("$dbVolumeVerified = $dbVolumePresent", CHECK_PC)
        self.assertNotIn("$dbVolumeVerified = $true", CHECK_PC)
        self.assertIn('sites\\toeflhouse.localhost', CHECK_PC)
        self.assertIn("Get-ChildItem -LiteralPath $sitesRoot -Force", CHECK_PC)
        self.assertIn('secrets\\db.env', CHECK_PC)
        self.assertIn('BLOCKED: existing site/database but credential file missing', CHECK_PC)
        self.assertIn('Do NOT assume a fresh installation', CHECK_PC)
        self.assertNotIn("Remove-Item", CHECK_PC)
        self.assertNotIn("docker compose up", CHECK_PC)
        self.assertNotIn("docker compose down", CHECK_PC)
        self.assertNotIn("docker volume rm", CHECK_PC)
        self.assertNotIn("docker load", CHECK_PC)
        self.assertNotIn("Backup TOEFL House ERP", CHECK_PC)
        self.assertNotIn("first-run-credentials.txt", CHECK_PC)


    def test_start_and_repair_fail_closed_when_db_credentials_are_missing(self):
        # Both daily workflows must defer to the same on-disk safety preflight
        # as Install. A missing Docker volume alone is NOT evidence of a fresh
        # machine when site files remain or Docker storage cannot be queried.
        for name, script in (("Start", START), ("Repair", REPAIR)):
            missing_secret = script.split("\n:nosecret\n", 1)[1].split(
                "\n:nosecretblocked\n", 1
            )[0]
            self.assertIn("Test Fresh Installation.ps1", missing_secret, name)
            self.assertIn("if errorlevel 1 goto :nosecretblocked", missing_secret, name)
            self.assertNotIn("No database exists yet", script, name)
            self.assertIn("Do NOT reinstall, delete data", script, name)
        preflight = (WINDOWS / "Test Fresh Installation.ps1").read_text()
        self.assertIn(r"data\sites", preflight)
        self.assertIn("Get-ChildItem -LiteralPath $sitesRoot -Force", preflight)
        self.assertIn('docker volume ls --filter "name=toefl-house-erp_db-data"', preflight)
        self.assertIn("Could not check existing database storage", preflight)

    def test_existing_site_and_db_volume_required_before_start_or_repair(self):
        # Without this guard docker compose up can silently create a fresh
        # empty named database volume while original Frappe site files remain.
        self.assertIn('"product/windows/Test Existing Installation.ps1"', PACKAGER)
        self.assertIn("site_config.json", EXISTING_PREFLIGHT)
        self.assertIn("db.env", EXISTING_PREFLIGHT)
        self.assertIn('docker volume ls --filter "name=$volumeName"', EXISTING_PREFLIGHT)
        self.assertIn('$_ .Trim()'.replace(' ', ''), EXISTING_PREFLIGHT)
        self.assertIn("docker volume inspect $volumeName", EXISTING_PREFLIGHT)
        self.assertIn("could create an empty replacement", EXISTING_PREFLIGHT)
        # Scan executable statements, not explanatory comments.
        statements = "\n".join(line for line in EXISTING_PREFLIGHT.splitlines()
                               if not line.lstrip().startswith("#"))
        for forbidden in ("docker compose up", "docker compose down",
                          "docker volume create", "Remove-Item", "Set-Content"):
            self.assertNotIn(forbidden, statements)
        for name, script in (("Start", START), ("Repair", REPAIR)):
            self.assertIn("Test Existing Installation.ps1", script, name)
            self.assertIn("if errorlevel 1 goto :datapreservationhold", script, name)
            self.assertLess(script.index("Test Existing Installation.ps1"),
                            script.index("docker compose up -d"), name)
            self.assertIn(":datapreservationhold", script, name)
            self.assertIn("Copy Safe Support Status", script, name)
            self.assertNotIn("send a photo of this window plus the", script.lower(), name)
        self.assertLess(REPAIR.index("Test Existing Installation.ps1"),
                        REPAIR.index("docker compose down"))

    def test_install_refuses_existing_site_before_creating_or_loading_data(self):
        guard = 'if exist "data\\sites\\toeflhouse.localhost\\site_config.json" goto :alreadyinstalled'
        prior_credentials = 'if exist "data\\secrets\\db.env" goto :alreadyinstalled'
        self.assertIn(guard, INSTALL)
        self.assertIn(prior_credentials, INSTALL)
        self.assertLess(INSTALL.index(prior_credentials), INSTALL.index("where docker"))
        self.assertLess(INSTALL.index(guard), INSTALL.index("where docker"))
        self.assertIn(":alreadyinstalled", INSTALL)
        self.assertIn("no installation attempted", INSTALL)
        self.assertIn("use open / start", INSTALL.lower())
        self.assertIn("Copy Safe Support Status", INSTALL)
        self.assertNotIn("data\\logs folder to TOEFL House", INSTALL)

    def test_customer_package_verifies_before_import_or_boot(self):
        self.assertIn('if exist "release\\toefl-house-erp-app.tar" goto :packagedimage', INSTALL)
        self.assertIn("Verify Package Image.ps1", INSTALL)
        self.assertIn(":packageinvalid", INSTALL)
        self.assertLess(INSTALL.index("Checking package integrity before local installation"),
                        INSTALL.index("if not exist data\\secrets mkdir data\\secrets"))
        self.assertIn('docker load -i "release\\toefl-house-erp-app.tar"', INSTALL)
        self.assertIn("docker compose up -d --no-build", INSTALL)
        self.assertLess(INSTALL.index("Verify Package Image.ps1"),
                        INSTALL.index('docker load -i "release\\toefl-house-erp-app.tar"'))
        self.assertIn("Get-FileHash -LiteralPath $Archive -Algorithm SHA256", VERIFY)
        self.assertIn("^[0-9a-fA-F]{64}$", VERIFY)
        self.assertIn("SHA-256 check", VERIFY)
        self.assertNotIn("docker load", VERIFY)

    def test_repair_reloads_verified_image_and_preserves_data(self):
        self.assertIn('if exist "release\\toefl-house-erp-app.tar" goto :packageimage', REPAIR)
        self.assertLess(REPAIR.index(":packageimage"),
                        REPAIR.index("Verify Package Image.ps1"))
        self.assertIn("docker compose down", REPAIR)
        self.assertNotIn("docker compose down -v", REPAIR)
        self.assertIn('docker load -i "release\\toefl-house-erp-app.tar"', REPAIR)
        self.assertIn("docker compose build", REPAIR)
        self.assertNotIn("git reset --hard", REPAIR)

    def test_packager_allowlists_only_code_and_never_copies_customer_data(self):
        self.assertIn("docker save --output", PACKAGER)
        self.assertIn('"TOEFL House ERP.vbs"', PACKAGER)
        self.assertIn('"product/docker-compose.yml"', PACKAGER)
        self.assertIn('"product/windows/Verify Package Image.ps1"', PACKAGER)
        self.assertIn("reparse", PACKAGER.lower())
        self.assertIn("product\\data", PACKAGER)
        self.assertIn("Get-FileHash", PACKAGER)
        self.assertNotIn("Copy-Item -Recurse", PACKAGER)
        self.assertNotIn("docker volume rm", PACKAGER)
        self.assertNotIn("docker system prune", PACKAGER)
        self.assertNotIn("Remove-Item", PACKAGER)
        # No backup/activation scripts are included in the deliverable.
        section = PACKAGER.split("$files = @(", 1)[1].split("\n    )", 1)[0]
        for forbidden in ("Backup TOEFL House ERP", "Activate TOEFL House ERP",
                          "Deactivate TOEFL House ERP", "data/secrets", "site_config.json"):
            self.assertNotIn(forbidden, section)

    def test_gui_does_not_enable_real_world_operation(self):
        self.assertIn("Real business use requires owner configuration and release approval", GUI)
        self.assertNotIn("activate.py activate", GUI + WORKER)
        self.assertNotIn("docker compose down -v", INSTALL + REPAIR + START + STOP)


if __name__ == "__main__":
    unittest.main()
