# Windows PowerShell 5.1 regression for the actual installed-image receipt writer.
# Isolated throwaway files only: never read or modify Owner site data.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\..\product\windows\Verify Package Image.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path -LiteralPath $script).Path, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw 'Installed-image verifier did not parse.' }

foreach ($name in @('Test-InstalledIdentityContents', 'Write-VerifiedInstalledImageIdentity')) {
    $definition = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }, $true)
    if (-not $definition) { throw ("Missing installed-image writer: " + $name) }
    Invoke-Expression $definition.Extent.Text
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('th-identity-test-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $root)
try {
    $identity = Join-Path $root 'installed-image-identity.json'
    $previous = '{"version":"previous"}'
    $updated = '{"version":"updated"}'
    $failed = $false

    # Factory receipt is created exactly once.
    Write-VerifiedInstalledImageIdentity -Path $identity -Contents $previous -CreateOnly
    if ([IO.File]::ReadAllText($identity) -cne $previous) {
        throw 'Factory receipt did not persist exactly.'
    }
    try {
        Write-VerifiedInstalledImageIdentity -Path $identity -Contents $updated -CreateOnly
    } catch { $failed = $true }
    if (-not $failed -or [IO.File]::ReadAllText($identity) -cne $previous) {
        throw 'A repeated factory install overwrote the prior receipt.'
    }

    # Successful signed-update replacement commits its new receipt and deletes
    # only its now-unneeded backup.
    Write-VerifiedInstalledImageIdentity -Path $identity -Contents $updated
    if ([IO.File]::ReadAllText($identity) -cne $updated -or
        @(Get-ChildItem -LiteralPath $root -Filter '*.bak' -File).Count -ne 0) {
        throw 'Successful receipt replacement or cleanup failed.'
    }

    # Force the post-Replace read-back check to fail. File.Replace has already
    # put the previous receipt into the .bak file. The backup MUST survive.
    [IO.File]::WriteAllText($identity, $previous)
    function Test-InstalledIdentityContents {
        param([string]$Path, [string]$Contents)
        return $false
    }
    $failed = $false
    try {
        Write-VerifiedInstalledImageIdentity -Path $identity -Contents $updated
    } catch {
        $failed = $_.Exception.Message -like '*read-back failed*'
    }
    $backups = @(Get-ChildItem -LiteralPath $root -Filter '*.bak' -File)
    $temporaries = @(Get-ChildItem -LiteralPath $root -Filter '*.tmp' -File)
    if (-not $failed -or $backups.Count -ne 1 -or $temporaries.Count -ne 0 -or
        [IO.File]::ReadAllText($backups[0].FullName) -cne $previous) {
        throw 'Failed receipt verification destroyed the recoverable previous identity.'
    }

    # Prove a reviewer can recover the original bytes from this isolated
    # backup without touching production files.
    [IO.File]::Delete($identity)
    [IO.File]::Move($backups[0].FullName, $identity)
    if ([IO.File]::ReadAllText($identity) -cne $previous) {
        throw 'Previous receipt could not be recovered exactly.'
    }

    # Restore the actual validator and verify a failed replacement (missing
    # destination) does not create a new installed-image receipt.
    $definition = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq 'Test-InstalledIdentityContents'
    }, $true)
    Invoke-Expression $definition.Extent.Text
    $missing = Join-Path $root 'missing.json'
    $failed = $false
    try {
        Write-VerifiedInstalledImageIdentity -Path $missing -Contents $updated
    } catch { $failed = $true }
    if (-not $failed -or [IO.File]::Exists($missing) -or
        @(Get-ChildItem -LiteralPath $root -Filter '*.tmp' -File).Count -ne 0) {
        throw 'Failed atomic replacement created a bogus receipt or left a temporary.'
    }

    Write-Host 'PASS: isolated installed-image receipt replacement, failure backup, and recovery.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
