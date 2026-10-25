"""Contract for the Windows "Check for Updates" workflow (Issue #40).

The Windows scripts cannot run on this Linux CI runner, so these tests pin the
safety properties of the update path: a separate graphical workflow, explicit
Owner confirmation, a read-only engine call, prebuilt-image-only installs, no
destructive Docker command, bilingual messages and updater files inside the
verified customer package. The real PowerShell smoke test runs on the Windows
runner in .github/workflows/windows-customer-package.yml.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "product" / "windows"
UPDATE = (WINDOWS / "Update TOEFL House ERP.ps1").read_text(encoding="utf-8")
GUI = (WINDOWS / "TOEFL House ERP.ps1").read_text(encoding="utf-8")
WORKER = (WINDOWS / "Run TOEFL House ERP.ps1").read_text(encoding="utf-8")
ENTRYPOINT = (ROOT / "product" / "update_entrypoint.sh").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "product" / "app.Dockerfile").read_text(encoding="utf-8")
DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8")
CHANNEL = json.loads((ROOT / "product" / "updates" / "channel.json").read_text(encoding="utf-8"))
CATALOG = json.loads((WINDOWS / "updater-strings.json").read_text(encoding="utf-8"))


class UpdateWorkflowTests(unittest.TestCase):
    def test_the_update_workflow_is_separate_from_install_and_repair(self):
        self.assertNotIn("Install TOEFL House ERP.cmd", UPDATE)
        self.assertNotIn("Repair TOEFL House ERP.cmd", UPDATE)
        self.assertNotIn("Start TOEFL House ERP.cmd", UPDATE)
        self.assertNotIn("Stop TOEFL House ERP.cmd", UPDATE)
        self.assertNotIn("activate.py", UPDATE)

    def test_the_graphical_launcher_exposes_the_two_update_controls(self):
        for caption in ('New-LauncherButton "Check for Updates"', 'New-LauncherButton "Install Update"'):
            self.assertIn(caption, GUI)
        self.assertIn('$updateButton.Add_Click({ Start-LauncherAction "UpdateCheck" })', GUI)
        self.assertIn('Start-LauncherAction "UpdateInstall"', GUI)
        self.assertIn('$updateButton.Text -ne "Check for Updates"', GUI)
        self.assertIn('$installUpdateButton.Text -ne "Install Update"', GUI)
        # Both buttons must be disabled while any operation is running.
        self.assertIn("$copyStatusButton, $updateButton, $installUpdateButton", GUI)

    def test_the_worker_routes_updates_without_touching_lifecycle_commands(self):
        self.assertIn('"Install", "Start", "Repair", "Stop", "Check", "UpdateCheck", "UpdateInstall"', WORKER)
        self.assertIn('Join-Path $PSScriptRoot "Update TOEFL House ERP.ps1"', WORKER)
        self.assertIn("& $updatePath -Action Check", WORKER)
        self.assertIn("& $updatePath -Action Install -ConfirmationAccepted", WORKER)
        update_branch = WORKER[WORKER.index('if ($Action -eq "UpdateCheck"'):]
        update_branch = update_branch[:update_branch.index("$scriptPath = Join-Path")]
        self.assertNotIn(".cmd", update_branch)

    def test_install_requires_an_explicit_owner_confirmation(self):
        self.assertIn("[switch]$ConfirmationAccepted", UPDATE)
        self.assertIn("if (-not $ConfirmationAccepted) {", UPDATE)
        self.assertIn('[System.Windows.Forms.MessageBoxDefaultButton]::Button2', GUI)
        self.assertIn("Update cancelled. Your system was not changed.", GUI)

    def test_install_refuses_before_any_change_when_the_engine_refuses(self):
        install = UPDATE[UPDATE.index("function Invoke-UpdateInstall"):]
        install = install[:install.index("function Invoke-SmokeTest")]
        # The `docker load` and every stack mutation live behind the engine's
        # allow decision, which is produced by Invoke-UpdateCheck before the
        # install pipeline runs at all.
        self.assertLess(UPDATE.index("function Invoke-UpdateCheck"), UPDATE.index("function Invoke-UpdateInstall"))
        self.assertNotIn("docker load", UPDATE[:UPDATE.index("function Invoke-UpdateInstall")])
        self.assertIn("if ($status -ne \"succeeded\")", install)
        self.assertIn("recovery-required", install)

    def test_no_destructive_command_can_appear_in_the_update_path(self):
        combined = "\n".join((UPDATE, WORKER, ENTRYPOINT))
        forbidden = ("down -v", "volume rm", "volume prune", "system prune", "docker compose down",
                     "docker-compose down", "git reset --hard", "git clone", "Invoke-Expression",
                     "--privileged", "docker build", "docker compose build", "bench build",
                     "yarn install", "npm install", "restore.py", "rm -rf")
        self.assertEqual([item for item in forbidden if item in combined], [],
                         "the update path contains a destructive or build command")

    def test_the_engine_is_read_only_and_offline_during_the_check(self):
        engine_call = UPDATE[UPDATE.index("function Invoke-UpdateEngine"):]
        engine_call = engine_call[:engine_call.index("function Read-EngineResponse")]
        self.assertIn('"--network", "none"', engine_call)
        self.assertIn(":ro", engine_call)
        self.assertIn("--entrypoint", engine_call)
        self.assertIn("/product/update_entrypoint.sh", engine_call)
        # The site and log folders are only shared with the migrating engine.
        self.assertIn('if ($Mode -ceq "apply")', engine_call)
        apply_branch = engine_call[engine_call.index('if ($Mode -ceq "apply")'):engine_call.index("} else {")]
        self.assertIn("sitesRoot", apply_branch)
        self.assertNotIn("sitesRoot", engine_call[engine_call.index("} else {"):])

    def test_only_a_prebuilt_verified_image_is_imported(self):
        self.assertTrue('Invoke-DockerVerbose @("load", "--input", $Check.Archive)' in UPDATE,
                        "the verified prebuilt archive is not the only imported image")
        self.assertNotIn("docker build", UPDATE)
        self.assertNotIn("bench build", UPDATE)
        self.assertIn("function Test-AllowedUrl", UPDATE)
        self.assertIn("https", UPDATE)

    def test_the_download_is_https_only_on_an_allowlisted_provider_host(self):
        self.assertIn('if ($uri.Scheme -cne "https") { return $false }', UPDATE)
        self.assertIn("foreach ($allowed in @($AllowedHosts))", UPDATE)
        self.assertIn("$request.AllowAutoRedirect = $false", UPDATE)
        self.assertIn("[System.Net.SecurityProtocolType]::Tls12", UPDATE)
        self.assertIn("Assert-SafeAssetName", UPDATE)
        self.assertIn("$required -cnotcontains $name", UPDATE)

    def test_a_verified_backup_and_owner_recovery_authorization_are_required(self):
        self.assertIn('"activation\\backup-receipt.json"', UPDATE)
        self.assertIn("recovery-authorization.json", UPDATE)
        self.assertIn("data/updates/recovery-authorization.sig", UPDATE)
        self.assertIn("preflight.backup.receipt_missing", UPDATE)
        self.assertIn("recovery_authorization =", UPDATE)
        self.assertIn("backup_dir = $script:BackupDirRelative", UPDATE)

    def test_the_installed_identity_is_derived_from_the_running_image(self):
        self.assertIn("org.toefl-house.release-version", UPDATE)
        self.assertIn("org.toefl-house.source-revision", UPDATE)
        self.assertIn("ConvertTo-ReleaseSequence", UPDATE)
        self.assertIn("release_sequence = $sequence", UPDATE)

    def test_verified_start_does_not_recreate_storage_or_rerun_bootstrap(self):
        start = UPDATE[UPDATE.index("function Invoke-UpdateStart"):UPDATE.index("function Wait-ForApplication")]
        self.assertIn("Test-ExistingInstallation -ProductRoot $productRoot", start)
        self.assertIn("$image.Id -cne $ExpectedImageId", start)
        self.assertIn('"--no-deps", "web", "worker", "scheduler", "socketio"', start)
        self.assertNotIn('"bootstrap"', start)
        self.assertLess(start.index("Test-ExistingInstallation"), start.index('Invoke-Compose'))

    def test_a_failed_migration_is_never_restarted_automatically(self):
        install = UPDATE[UPDATE.index("function Invoke-UpdateInstall"):]
        install = install[:install.index("function Invoke-SmokeTest")]
        self.assertIn('$outcome -ceq "safe-abort"', install)
        recovery = install[install.index("# A migration may already have changed the database."):]
        recovery = recovery[:recovery.index("exit $script:ExitRecoveryRequired")]
        self.assertNotIn("Invoke-UpdateStart", recovery)
        self.assertNotIn("compose", recovery)
        # The journal records a recovery decision instead of a silent restart.
        self.assertIn('Set-JournalState "recovery-required" $Check.Version', install)

    def test_the_journal_blocks_a_second_update_and_reports_interruption(self):
        self.assertIn('document_type = "toefl-house-erp-update-journal"', UPDATE)
        self.assertIn('@("idle", "prepared", "applying", "completed", "rolled-back", "recovery-required")', UPDATE)
        self.assertIn('if ($journalState -ceq "prepared" -or $journalState -ceq "applying")', UPDATE)
        self.assertIn("updater.interrupted", UPDATE)
        self.assertIn("Enter-UpdateLock", UPDATE)
        self.assertIn("[System.IO.FileMode]::CreateNew", UPDATE)

    def test_the_result_document_never_carries_free_text(self):
        save = UPDATE[UPDATE.index("function Save-Result"):]
        save = save[:save.index("function Stop-Update")]
        self.assertIn('document_type = "toefl-house-erp-updater-result"', save)
        self.assertNotIn("Detail", save)
        for field in ("schema_version", "status", "message_section", "message_key", "version", "blockers"):
            self.assertIn(field, save)
        self.assertIn('if (@("messages", "launcher") -cnotcontains $section) { return $null }', GUI)
        self.assertIn('if ($item.Length -gt 65536) { return $null }', GUI)

    def test_the_engine_and_entrypoint_are_shipped_inside_the_image(self):
        self.assertIn("COPY product/update_engine.py /product/update_engine.py", DOCKERFILE)
        self.assertIn("COPY product/update_entrypoint.sh /product/update_entrypoint.sh", DOCKERFILE)
        self.assertIn("/product/update_entrypoint.sh", DOCKERFILE)
        self.assertIn("!product/update_engine.py", DOCKERIGNORE)
        self.assertIn("!product/update_entrypoint.sh", DOCKERIGNORE)
        self.assertTrue(ENTRYPOINT.startswith("#!/bin/sh\n"))
        self.assertIn("python3 /product/update_engine.py --request /update/request.json", ENTRYPOINT)
        self.assertIn("--response /update/response.json", ENTRYPOINT)
        for forbidden in ("docker ", "volume rm", "restore", "activate", "rm -rf", "prune"):
            self.assertNotIn(forbidden, ENTRYPOINT)

    def test_every_customer_visible_message_is_english_and_dari(self):
        self.assertEqual(CATALOG["document_type"], "toefl-house-erp-updater-strings")
        for section in ("messages", "launcher", "ui"):
            self.assertIn(section, CATALOG)
            for key, entry in CATALOG[section].items():
                self.assertEqual(set(entry), {"en", "fa"}, key)
                self.assertTrue(entry["en"].strip(), key)
                self.assertTrue(entry["fa"].strip(), key)
                self.assertRegex(entry["fa"], r"[\u0600-\u06FF\u200c]", key)
        for key in ("updater.checking", "updater.available", "updater.up_to_date", "updater.completed",
                    "updater.failed", "updater.recovery_required", "updater.cancelled", "updater.not_installed",
                    "updater.installed_version_unknown", "updater.engine_failed", "updater.engine_missing",
                    "updater.already_running", "updater.rollback_done", "updater.interrupted",
                    "updater.not_configured", "updater.network_failed", "updater.download_failed",
                    "updater.package_invalid", "updater.guard_blocked"):
            self.assertIn(key, CATALOG["launcher"])

    def test_the_channel_cannot_reach_the_network_until_the_provider_enables_it(self):
        self.assertEqual(CHANNEL["document_type"], "toefl-house-erp-update-channels")
        for entry in CHANNEL["channels"]:
            self.assertFalse(entry["enabled"])
            self.assertTrue(entry["metadata_url"].startswith("https://"))
            self.assertEqual(set(entry["required_assets"]),
                             {"update.json", "update.json.sig", "toefl-house-erp-app.tar"})
        self.assertIn('if ($selected.enabled -ne $true) {', UPDATE)
        self.assertIn('"channel.disabled"', UPDATE)


class TwoPhaseProtocolTests(unittest.TestCase):
    """The Windows updater must never skip a verification phase (#40, review A/B)."""

    def block(self, start: str, end: str) -> str:
        begin = UPDATE.index(start)
        return UPDATE[begin:UPDATE.index(end, begin)]

    def test_the_manifest_phase_runs_before_the_image_is_downloaded(self):
        check = self.block("function Invoke-UpdateCheck", "function Invoke-UpdateStart")
        preflight = check.index('Invoke-EngineStep "preflight"')
        download = check.index("Save-RemoteFile (Resolve-ChannelUrl $channel $archiveName)")
        authorize = check.index('Invoke-EngineStep "authorize"')
        self.assertLess(preflight, download, "the archive must not be fetched before the manifest phase allows it")
        self.assertLess(download, authorize, "the image phase must run after the archive exists")
        self.assertIn('$request.archive = $archiveRelative', check)
        self.assertIn('$request.action = "authorize"', check)
        self.assertIn('$request.transaction = $manifestTransaction', check)

    def test_the_engine_state_is_durable_and_shared_across_runs(self):
        # The authorization record and one-use marker must live outside the
        # per-run work folder so a replay from a later run is refused.
        self.assertIn('$engineStateRoot = Join-Path $updatesRoot "engine-state"', UPDATE)
        self.assertIn('$containerEngineState = "/update-state"', UPDATE)
        engine = self.block("function Invoke-UpdateEngine", "function Invoke-EngineStep")
        self.assertIn('($engineStateRoot + ":" + $containerEngineState)', engine)
        self.assertIn("--state-dir /update-state", ENTRYPOINT)
        self.assertIn("chown -R frappe:frappe /update-state", ENTRYPOINT)

    def test_only_an_authorized_transaction_reaches_apply(self):
        check = self.block("function Invoke-UpdateCheck", "function Invoke-UpdateStart")
        self.assertIn('[string]$transaction.phase -cne "authorized"', check)
        install = self.block("function Invoke-UpdateInstall", "function Invoke-SmokeTest")
        for field in ("transaction = $freshAuthorization.transaction", "archive = ($Check.RunFolder",
                      "backup_receipt =", "backup_dir =",
                      "recovery_authorization =", "recovery_signature ="):
            self.assertIn(field, install, f"the apply request does not carry {field}")
        apply_request = install[install.index("$applyRequest ="):]
        self.assertNotIn("host = $Check.Facts", apply_request)
        self.assertNotIn("journal_state =", apply_request)
        self.assertNotIn("installed =", apply_request)
        self.assertLess(install.index('Invoke-EngineStep "recheck"'), install.index('Set-JournalState "prepared"'))

    def test_old_engine_verifies_archive_then_new_engine_authorizes_live_host(self):
        install = self.block("function Invoke-UpdateInstall", "function Invoke-SmokeTest")
        self.assertLess(UPDATE.index('Invoke-EngineStep "authorize"'),
                        UPDATE.index("function Invoke-UpdateInstall"))
        old_preflight = install.index('Invoke-EngineStep "preflight"')
        old_authorize = install.index('Invoke-EngineStep "authorize"')
        load = install.index('Invoke-DockerVerbose @("load", "--input", $Check.Archive)')
        candidate = install.index('$script:EngineImage = $candidateImageId')
        new_preflight = install.index('Invoke-EngineStep "preflight"', candidate)
        new_authorize = install.index('Invoke-EngineStep "authorize"', candidate)
        recheck = install.index('Invoke-EngineStep "recheck"')
        stop = install.index('Invoke-Compose @("stop"')
        self.assertLess(old_preflight, old_authorize)
        self.assertLess(old_authorize, load)
        self.assertLess(load, candidate)
        self.assertLess(candidate, new_preflight)
        self.assertLess(new_preflight, new_authorize)
        self.assertLess(new_authorize, recheck)
        self.assertLess(recheck, stop)
        self.assertIn('$freshRequest.Remove("transaction")', install)
        self.assertIn('"tag", $previousImageId, $imageTag', install[:new_preflight])
        self.assertIn('"tag", $candidateImageId, $imageTag', install[stop:])
        engine = self.block("function Invoke-UpdateEngine", "function Stop-EngineFailure")
        self.assertIn('if ($script:UseObserver)', engine)
        self.assertIn('source=/var/run/docker.sock,target=/run/th-update-docker.sock,readonly', engine)
        self.assertIn('$script:UseObserver = $false', install[:load])
        self.assertIn('$script:UseObserver = $true', install[load:new_preflight])

    def test_every_engine_request_is_answered_with_a_fresh_document(self):
        self.assertIn('Remove-Item -LiteralPath (Join-Path $script:WorkDir "response.json")', UPDATE)
        self.assertIn("function Invoke-EngineStep", UPDATE)
        self.assertIn('$response.document_type -cne "toefl-house-erp-update-engine-response"', UPDATE)

    def test_the_updater_never_builds_the_application(self):
        for command in ("docker compose build", "docker build", "compose up -d\n"):
            self.assertNotIn(command, UPDATE)
        self.assertIn('Invoke-DockerVerbose @("load", "--input", $Check.Archive)', UPDATE)

    def test_the_new_refusal_codes_are_translatable(self):
        for key in ("transaction.missing", "transaction.invalid", "transaction.expired",
                    "transaction.mismatch", "transaction.replayed", "transaction.unknown",
                    "transaction.tampered", "apply.archive_mismatch",
                    "apply.installed_mismatch", "apply.evidence_mismatch", "apply.identity_mismatch",
                    "apply.host_unsafe", "apply.journal_unsafe"):
            self.assertIn(key, CATALOG["messages"])
            entry = CATALOG["messages"][key]
            self.assertTrue(entry["en"].strip() and entry["fa"].strip(), key)


class PackageMembershipTests(unittest.TestCase):
    def test_the_updater_travels_in_the_verified_customer_package(self):
        for path in ("tools/release/create_customer_package.py", "product/windows/Prepare Customer Package.ps1"):
            text = (ROOT / path).read_text(encoding="utf-8")
            for name in ("product/windows/Update TOEFL House ERP.ps1",
                         "product/windows/updater-strings.json",
                         "product/updates/channel.json"):
                self.assertIn(name, text, f"{name} is missing from {path}")

    def test_the_windows_workflow_reruns_when_the_update_path_changes(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-customer-package.yml").read_text(encoding="utf-8")
        for trigger in ("product/update_engine.py", "product/update_entrypoint.sh", "product/updates/**",
                        "tests/foundation/test_windows_update_path.py"):
            self.assertIn(trigger, workflow, f"{trigger} does not trigger the Windows update smoke")

    def test_the_windows_workflow_parses_and_smoke_tests_the_updater(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-customer-package.yml").read_text(encoding="utf-8")
        self.assertIn("product/windows/Update TOEFL House ERP.ps1", workflow)
        self.assertIn("Update TOEFL House ERP.ps1\" -SmokeTest", workflow)
        self.assertIn("channel.disabled", workflow)
        self.assertIn("paused updates", workflow)


if __name__ == "__main__":
    unittest.main()
