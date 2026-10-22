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
VERIFY = (WINDOWS / "Verify Package Image.ps1").read_text()
PACKAGER = (WINDOWS / "Prepare Customer Package.ps1").read_text()
SHORTCUT = (ROOT / "TOEFL House ERP.vbs").read_text()


class CustomerInstallerContract(unittest.TestCase):
    def test_gui_launcher_opens_without_a_visible_console(self):
        self.assertIn("shell.Run command, 0, False", SHORTCUT)
        self.assertIn("product\\windows\\TOEFL House ERP.ps1", SHORTCUT)
        self.assertIn("System.Windows.Forms", GUI)
        self.assertIn("param([switch]$SmokeTest)", GUI)
        self.assertIn("Windows GUI controls initialized", GUI)
        for button in ('"Install"', '"Open / Start"', '"Repair"', '"Stop"',
                       '"Get Docker Desktop"', '"View Administrator Login"',
                       '"Check This PC"'):
            self.assertIn(button, GUI)
        self.assertIn('"http://127.0.0.1:8000/"', GUI)
        self.assertIn('$script:process', GUI)
        self.assertIn("Add_FormClosing", GUI)
        self.assertIn("TH_GUI_MODE", WORKER)
        self.assertIn("ValidateSet", WORKER)
        self.assertNotIn("Invoke-Expression", GUI + WORKER)

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
        self.assertIn('"Check"', WORKER)
        self.assertIn('Read-only PC check', CHECK_PC)
        self.assertIn('Result "Production authorization" "NOT VERIFIED"', CHECK_PC)
        self.assertIn('Get-PSDrive', CHECK_PC)
        self.assertNotIn("Remove-Item", CHECK_PC)
        self.assertNotIn("docker compose up", CHECK_PC)
        self.assertNotIn("docker compose down", CHECK_PC)
        self.assertNotIn("docker volume rm", CHECK_PC)
        self.assertNotIn("docker load", CHECK_PC)
        self.assertNotIn("Backup TOEFL House ERP", CHECK_PC)
        self.assertNotIn("first-run-credentials.txt", CHECK_PC)

    def test_customer_package_verifies_before_import_or_boot(self):
        self.assertIn('if exist "release\\toefl-house-erp-app.tar" goto :packagedimage', INSTALL)
        self.assertIn("Verify Package Image.ps1", INSTALL)
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
