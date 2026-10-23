# Verify a supplied customer image BEFORE any Docker import or site change.
# This checksum detects package corruption; it is not a publisher signature.
param(
    [string]$Archive = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar"),
    [string]$Checksum = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar.sha256"),
    [string]$Manifest = (Join-Path $PSScriptRoot "..\release\release-manifest.json")
)
$ErrorActionPreference = "Stop"
try {
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "The customer image archive is missing."
    }
    if (-not (Test-Path -LiteralPath $Checksum -PathType Leaf)) {
        throw "The checksum file is missing. Never load an unchecked image."
    }
    $checksumText = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Checksum).Path).Trim()
    $checksumParts = @($checksumText -split '\s+' | Where-Object { $_ })
    $expected = if ($checksumParts.Count -gt 0) { $checksumParts[0] } else { "" }
    if ($expected -notmatch '^[0-9a-fA-F]{64}$') {
        throw "The checksum file does not contain exactly one SHA-256 digest."
    }
    $actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
    if (-not [string]::Equals($actual, $expected,
        [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The customer image failed its SHA-256 check. No import is permitted."
    }
    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
        throw "The release manifest is missing. No customer package identity is established."
    }
    $release = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
    if ($release.schema_version -ne 1 -or $release.product -ne "TOEFL House ERP" -or
        $release.release_status -ne "TEST PACKAGE - NO REAL DATA" -or
        $release.production_authorization -ne "REJECT") {
        throw "The release manifest is not a supported non-production TOEFL House package."
    }
    if ($release.source_revision -notmatch '^[0-9a-fA-F]{40}$' -or
        $release.version -notmatch '^[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}$' -or
        $release.image.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        -not [string]::Equals($release.image.sha256, $actual,
            [System.StringComparison]::OrdinalIgnoreCase) -or
        $release.image.labels.'org.toefl-house.source-eol' -ne "lf-v1" -or
        $release.image.labels.'org.toefl-house.source-revision' -ne $release.source_revision -or
        $release.image.labels.'org.toefl-house.release-version' -ne $release.version) {
        throw "The release manifest does not bind the image to its source and version."
    }
    Write-Host "Customer image integrity: verified."
    exit 0
} catch {
    [Console]::Error.WriteLine("Customer image verification failed: " + $_.Exception.Message)
    exit 1
}
