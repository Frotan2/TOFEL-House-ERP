"""Run the delivered Windows backup selector against real temporary files."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
SUFFIXES = ("-database-enc.sql.gz", "-files-enc.tar",
            "-private-files-enc.tar", "-site_config_backup-enc.json")


@unittest.skipUnless(POWERSHELL and os.name == "nt", "Windows PowerShell runtime required")
class WindowsBackupDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def seed(self, prefix):
        for suffix in SUFFIXES:
            path = self.folder / (prefix + suffix)
            if os.name == "nt":
                path = Path("\\\\?\\" + str(path))
            path.write_bytes(b"synthetic backup fixture")
            # Intentionally older than the run and older than previous sets.
            os.utime(path, (946684800, 946684800))

    def select(self, previous=(), attempts=1, delayed=False):
        environment = dict(os.environ,
            TH_BACKUP_SOURCE=str(ROOT / "product/windows/Backup TOEFL House ERP.ps1"),
            TH_BACKUP_TEST_DIRECTORY=str(self.folder),
            TH_BACKUP_PREVIOUS=json.dumps(list(previous)),
            TH_BACKUP_ATTEMPTS=str(attempts), TH_BACKUP_DELAYED=str(int(delayed)))
        command = r'''
$ErrorActionPreference='Stop'
$errors=$null; $tokens=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:TH_BACKUP_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Backup script parse failure'}
foreach($functionName in @('ConvertTo-BackupFilePath','Find-NewNativeBackupSet','Get-BackupFileHash','Get-NextBackupStart','Get-BackupTaskUserSid','Invoke-ComposeCapture')) {
    $definition=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName},$true)
    if(-not $definition){throw 'Delivered backup helper missing'}
    Invoke-Expression $definition.Extent.Text
}
$previous=@{}
$names=ConvertFrom-Json $env:TH_BACKUP_PREVIOUS
foreach($name in $names){$previous[$name]=$true}
if($env:TH_BACKUP_DELAYED -eq '1') {
    $script:sidecarReads=0
    function Get-ChildItem {
        param($LiteralPath,$Filter,[switch]$File)
        if($Filter -like '*site_config_backup*') {
            $script:sidecarReads++
            if($script:sidecarReads -eq 1){return}
        }
        Microsoft.PowerShell.Management\Get-ChildItem -LiteralPath $LiteralPath -Filter $Filter -File:$File
    }
}
try {
    $result=Find-NewNativeBackupSet -Directory $env:TH_BACKUP_TEST_DIRECTORY -PreviousNames $previous -Attempts ([int]$env:TH_BACKUP_ATTEMPTS)
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    if((Get-BackupTaskUserSid $identity.Name) -ne $identity.User.Value){throw 'Current Windows account did not resolve to its SID'}
    if((Get-BackupTaskUserSid $identity.User.Value) -ne $identity.User.Value){throw 'Current SID representation rejected'}
    if((Get-BackupTaskUserSid 'S-1-0-0') -eq $identity.User.Value){throw 'Foreign task identity accepted'}
    if((Get-BackupTaskUserSid 'S-1-invalid') -ne ''){throw 'Malformed task identity accepted'}
    $compose=@('compose')
    function docker { Write-Error 'synthetic copy progress'; $global:LASTEXITCODE=0 }
    $captured=Invoke-ComposeCapture @('cp','synthetic-public-key','synthetic-target')
    if($captured.ExitCode -ne 0 -or $ErrorActionPreference -ne 'Stop'){throw 'Successful native progress was treated as failure'}
    function docker { Write-Error 'synthetic failure'; $global:LASTEXITCODE=7 }
    $failed=Invoke-ComposeCapture @('cp','synthetic-public-key','synthetic-target')
    if($failed.ExitCode -ne 7 -or $ErrorActionPreference -ne 'Stop'){throw 'Native failure exit code was hidden'}
    $now=[DateTime]'2026-10-27T21:00:00'
    $next=Get-NextBackupStart -Time '02:00' -Now $now
    if($next -ne [DateTime]'2026-10-28T02:00:00'){throw 'Missed nightly schedule could run immediately'}
    $future=Get-NextBackupStart -Time '23:00' -Now $now
    if($future -ne [DateTime]'2026-10-27T23:00:00'){throw 'Future nightly schedule moved unnecessarily'}
    $readLength=[IO.File]::ReadAllText($result.Sidecar.FullName).Length
    $hash=(Get-BackupFileHash -LiteralPath $result.Sidecar.FullName -Algorithm SHA256).Hash
    $copy=[IO.Path]::Combine((ConvertTo-BackupFilePath $env:TH_BACKUP_TEST_DIRECTORY),'20261027_213345-toeflhouse_localhost-copy-check.bin')
    Copy-Item -LiteralPath $result.Sidecar.FullName -Destination $copy
    if((Get-BackupFileHash -LiteralPath $copy).Hash -ne $hash){throw 'Long-path copy changed contents'}
    if(-not(Test-Path -LiteralPath $copy -PathType Leaf)){throw 'Long-path copy invisible'}
    Remove-Item -LiteralPath $copy -Force
    if(Test-Path -LiteralPath $copy){throw 'Long-path cleanup failed'}
    @{base=$result.Base;sidecar=$result.Sidecar.Name;read_length=$readLength;sha256=$hash} | ConvertTo-Json -Compress
} catch {
    Write-Output $_.Exception.Message
    exit 3
}
'''
        return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
            env=environment, capture_output=True, text=True, timeout=30)

    def test_new_set_is_selected_despite_old_host_modification_times(self):
        self.seed("previous")
        previous = [path.name for path in self.folder.iterdir()]
        self.seed("new")
        result = self.select(previous)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["base"], "new")
        self.assertEqual(json.loads(result.stdout)["sha256"].lower(),
                         hashlib.sha256(b"synthetic backup fixture").hexdigest())

    def test_preexisting_set_never_qualifies_as_a_new_backup(self):
        self.seed("previous")
        result = self.select(path.name for path in self.folder.iterdir())
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

    def test_two_new_sets_are_ambiguous_even_when_one_is_complete(self):
        self.seed("first")
        (self.folder / "second-database-enc.sql.gz").write_bytes(b"second")
        result = self.select()
        self.assertEqual(result.returncode, 3)
        self.assertIn("multiple new native database sets", result.stdout)

    def test_configuration_from_another_set_cannot_be_selected(self):
        self.seed("new")
        sidecar = self.folder / ("new" + SUFFIXES[-1])
        sidecar.rename(self.folder / ("other" + SUFFIXES[-1]))
        self.assertEqual(self.select().returncode, 3)

    def test_empty_file_archive_does_not_complete_a_set(self):
        self.seed("new")
        (self.folder / "new-files-enc.tar").write_bytes(b"")
        self.assertEqual(self.select().returncode, 3)

    def test_delayed_directory_visibility_is_retried(self):
        self.seed("new")
        result = self.select(attempts=3, delayed=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["base"], "new")

    def test_long_customer_path_supports_real_file_reads_and_hashes(self):
        while len(str(self.folder)) < 210:
            self.folder = self.folder / "existing-installation"
        self.folder.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, "\\\\?\\" + str(self.folder))
        prefix = "20261027_213345-toeflhouse_localhost"
        self.seed(prefix)
        self.assertGreater(len(str(self.folder / (prefix + SUFFIXES[-1]))), 260)
        result = self.select()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["base"], prefix)
