"""Evaluate delivered scheduling settings and guards without registering a task."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


@unittest.skipUnless(POWERSHELL and os.name == "nt", "Windows PowerShell runtime required")
class WindowsBackupSchedulingTests(unittest.TestCase):
    def probe(self, mode):
        # Only AST-selected settings/principal constructors and boolean guard
        # expressions execute. The launcher, backup and task registration never do.
        command = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:TH_BACKUP_SCHEDULE_SOURCE, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Delivered backup script parse failure' }
function Get-Guard([string]$message) {
    $matches = @($tree.FindAll({param($node)
        if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
        foreach ($clause in $node.Clauses) {
            foreach ($statement in $clause.Item2.Statements) {
                if ($statement -is [System.Management.Automation.Language.ThrowStatementAst] -and
                    $statement.Extent.Text.Contains($message)) { return $true }
            }
        }
        return $false
    }, $true))
    if ($matches.Count -ne 1) { throw "Expected exactly one delivered guard: $message" }
    return [scriptblock]::Create($matches[0].Clauses[0].Item1.Extent.Text)
}
function New-Fixture {
    [pscustomobject]@{
        State = 'Ready'
        Settings = [pscustomobject]@{ WakeToRun = $true }
        Actions = @([pscustomobject]@{Execute = $expectedPowerShell; Arguments = $expectedTaskArgument})
        Triggers = @([pscustomobject]@{DaysInterval = 1})
        Principal = [pscustomobject]@{UserId = 'expected-user'; LogonType = 'Interactive'}
    }
}
function Get-BackupTaskUserSid([string]$identity) {
    if ($identity -eq 'expected-user') { return 'expected-sid' }
    return 'different-sid'
}
$expectedPowerShell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$expectedTaskArgument = '-NoProfile -File "C:\existing-installation\Backup TOEFL House ERP.ps1"'
$expectedTaskUserSid = 'expected-sid'
$policy = [pscustomobject]@{schedule_time = '03:00'}
$task = New-Fixture
$registered = New-Fixture
$taskStart = [datetime]'2026-11-21T03:00:00'
$registeredStart = $taskStart
$registeredTrigger = $registered.Triggers[0]
$taskTrigger = $task.Triggers[0]
switch ($env:TH_BACKUP_SCHEDULE_MODE) {
    'settings' {
        $constructors = @($tree.FindAll({param($node)
            $node -is [System.Management.Automation.Language.CommandAst] -and
            $node.GetCommandName() -eq 'New-ScheduledTaskSettingsSet'
        }, $true))
        if ($constructors.Count -ne 1) { throw 'Expected one settings constructor' }
        $settings = & ([scriptblock]::Create($constructors[0].Extent.Text))
        $principals = @($tree.FindAll({param($node)
            $node -is [System.Management.Automation.Language.CommandAst] -and
            $node.GetCommandName() -eq 'New-ScheduledTaskPrincipal'
        }, $true))
        if ($principals.Count -ne 1) { throw 'Expected one principal constructor' }
        $principal = & ([scriptblock]::Create($principals[0].Extent.Text))
        [ordered]@{
            wake = $settings.WakeToRun
            catch_up = $settings.StartWhenAvailable
            disallow_battery_start = $settings.DisallowStartIfOnBatteries
            stop_on_battery = $settings.StopIfGoingOnBatteries
            limit = $settings.ExecutionTimeLimit
            logon = [string]$principal.LogonType
            privilege = [string]$principal.RunLevel
        } | ConvertTo-Json -Compress
    }
    'wake-guards' {
        $existing = Get-Guard 'The Owner-configured Windows backup task is missing'
        $created = Get-Guard 'The Windows scheduled backup task could not be verified'
        $result = [ordered]@{existing_valid = [bool](& $existing); created_valid = [bool](& $created)}
        $task.Settings.WakeToRun = $false
        $registered.Settings.WakeToRun = $false
        $result.existing_missing_wake = [bool](& $existing)
        $result.created_missing_wake = [bool](& $created)
        $task = $null; $registered = $null
        $result.existing_missing_task = [bool](& $existing)
        $result.created_missing_task = [bool](& $created)
        $result | ConvertTo-Json -Compress
    }
    'existing-authenticity' {
        $action = Get-Guard 'The scheduled task action does not invoke this product'
        $identity = Get-Guard 'The scheduled task does not match the current Owner-selected daily time'
        $taskAction = $task.Actions[0]
        $result = [ordered]@{action_valid = [bool](& $action); identity_valid = [bool](& $identity)}
        $taskAction.Execute = 'foreign.exe'
        $result.foreign_action = [bool](& $action)
        $taskAction = (New-Fixture).Actions[0]
        $taskAction.Arguments = '-ExecutionPolicy Bypass -File foreign.ps1'
        $result.foreign_arguments = [bool](& $action)
        $task.Principal.UserId = 'other-user'
        $result.foreign_user = [bool](& $identity)
        $task.Principal.UserId = 'expected-user'
        $task.Principal.LogonType = 'ServiceAccount'
        $result.foreign_principal = [bool](& $identity)
        $task.Principal.LogonType = 'Interactive'
        $taskStart = $taskStart.AddMinutes(1)
        $result.foreign_time = [bool](& $identity)
        $result | ConvertTo-Json -Compress
    }
    'created-authenticity' {
        $guard = Get-Guard 'The Windows scheduled backup task could not be verified'
        $result = [ordered]@{valid = [bool](& $guard)}
        $registered.Principal.UserId = 'other-user'
        $result.foreign_user = [bool](& $guard)
        $registered.Principal.UserId = 'expected-user'
        $registered.Principal.LogonType = 'ServiceAccount'
        $result.foreign_principal = [bool](& $guard)
        $registered.Principal.LogonType = 'Interactive'
        $registered.Actions[0].Execute = 'foreign.exe'
        $result.foreign_action = [bool](& $guard)
        $registered.Actions[0].Execute = $expectedPowerShell
        $registered.Actions[0].Arguments = 'foreign-arguments'
        $result.foreign_arguments = [bool](& $guard)
        $registered.Actions[0].Arguments = $expectedTaskArgument
        $registeredTrigger.DaysInterval = 2
        $result.foreign_interval = [bool](& $guard)
        $registeredTrigger.DaysInterval = 1
        $registeredStart = $registeredStart.AddMinutes(1)
        $result.foreign_time = [bool](& $guard)
        $result | ConvertTo-Json -Compress
    }
    default { throw 'Unknown test probe' }
}
'''
        environment = dict(os.environ,
            TH_BACKUP_SCHEDULE_SOURCE=str(ROOT / "product/windows/Backup TOEFL House ERP.ps1"),
            TH_BACKUP_SCHEDULE_MODE=mode)
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
            env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_settings_wake_without_relaxing_ac_guards_or_principal(self):
        self.assertEqual(self.probe("settings"), {
            "wake": True, "catch_up": True,
            "disallow_battery_start": True, "stop_on_battery": True,
            "limit": "PT3H", "logon": "Interactive", "privilege": "Limited",
        })

    def test_existing_and_new_task_guards_refuse_missing_wake(self):
        result = self.probe("wake-guards")
        for name, refused in result.items():
            with self.subTest(case=name):
                self.assertEqual(refused, not name.endswith("_valid"))

    def test_existing_task_keeps_action_identity_and_schedule_guards(self):
        result = self.probe("existing-authenticity")
        for name, refused in result.items():
            with self.subTest(case=name):
                self.assertEqual(refused, not name.endswith("_valid"))

    def test_registered_task_keeps_action_identity_and_schedule_guards(self):
        result = self.probe("created-authenticity")
        for name, refused in result.items():
            with self.subTest(case=name):
                self.assertEqual(refused, name != "valid")


if __name__ == "__main__":
    unittest.main()
