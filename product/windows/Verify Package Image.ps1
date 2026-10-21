# Verify a supplied customer image BEFORE any Docker import or site change.
# This checksum detects package corruption; it is not a publisher signature.
param(
    [string]$Archive = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar"),
    [string]$Checksum = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar.sha256")
)
$ErrorActionPreference = "Stop"
try {
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "The customer image archive is missing."
    }
    if (-not (Test-Path -LiteralPath $Checksum -PathType Leaf)) {
        throw "The checksum file is missing. Never load an unchecked image."
    }
    $expected = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Checksum).Path).Trim()
    if ($expected -notmatch '^[0-9a-fA-F]{64}$') {
        throw "The checksum file does not contain exactly one SHA-256 digest."
    }
    $actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
    if (-not [string]::Equals($actual, $expected,
        [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The customer image failed its SHA-256 check. No import is permitted."
    }
    Write-Host "Customer image integrity: verified."
    exit 0
} catch {
    [Console]::Error.WriteLine("Customer image verification failed: " + $_.Exception.Message)
    exit 1
}
