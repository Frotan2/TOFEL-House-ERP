"""Native PowerShell streaming hashes work without Get-FileHash or short paths."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
POWERSHELL=shutil.which('powershell.exe') or shutil.which('pwsh')
SCRIPTS=('Verify Package Image.ps1','Update TOEFL House ERP.ps1','Prepare Customer Package.ps1')


@unittest.skipUnless(POWERSHELL and os.name=='nt','Windows PowerShell required')
class WindowsPackageHashTests(unittest.TestCase):
    def test_all_hash_paths_match_known_digest_without_the_optional_cmdlet(self):
        content=bytes(range(256))*8192
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'image.tar'
            path.write_bytes(content)
            expected=hashlib.sha256(content).hexdigest()
            for name in SCRIPTS:
                with self.subTest(script=name):
                    result=self.run_hash(name,path)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout.strip(),expected)

    def test_long_existing_installation_file_matches_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            while len(str(folder))<220:
                folder=folder/'preserved-installation'
            folder.mkdir(parents=True)
            extended=Path('\\\\?\\'+str(folder))
            try:
                path=extended/('customer-image-'+('x'*45)+'.tar')
                path.write_bytes(b'preserved customer image')
                normal=Path(str(path)[4:])
                self.assertGreater(len(str(normal)),260)
                for name in SCRIPTS:
                    result=self.run_hash(name,normal)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout.strip(),hashlib.sha256(path.read_bytes()).hexdigest())
            finally:
                shutil.rmtree(extended)

    def test_missing_image_fails_instead_of_returning_a_digest(self):
        for name in SCRIPTS:
            result=self.run_hash(name,ROOT/'missing-customer-image-for-hash-test.tar')
            self.assertNotEqual(result.returncode,0)

    def run_hash(self,name,path):
        environment=dict(os.environ,TH_HASH_SOURCE=str(ROOT/'product/windows'/name),TH_HASH_INPUT=str(path))
        command=r'''
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($env:TH_HASH_SOURCE,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Delivered script failed to parse'}
$definition=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-ProductFileSha256'},$true)
if(-not $definition){throw 'Streaming hash helper absent'}
Invoke-Expression $definition.Extent.Text
function Get-FileHash {throw 'Optional hash cmdlet is deliberately unavailable'}
Get-ProductFileSha256 -LiteralPath $env:TH_HASH_INPUT
'''
        return subprocess.run([POWERSHELL,'-NoProfile','-NonInteractive','-Command',command],
            env=environment,capture_output=True,text=True,timeout=30)
