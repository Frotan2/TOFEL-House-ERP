$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "../../product/windows/Test Fresh Installation.ps1")

$root = Join-Path ([System.IO.Path]::GetTempPath()) ("toefl-synthetic-preflight-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $root | Out-Null
$script:dockerResult = @()
$script:dockerExit = 0
$script:dockerCalls = 0
function docker {
    $script:dockerCalls++
    if (($args -join " ") -ne 'volume ls --filter name=toefl-house-erp_db-data --format {{.Name}}') {
        throw "Unexpected or mutating Docker command in storage preflight"
    }
    $global:LASTEXITCODE = $script:dockerExit
    return $script:dockerResult
}
function Assert-Denied([string]$Expected) {
    $denied = $false
    try { Test-FreshInstallation -ProductRoot $root }
    catch {
        $denied = $true
        if ($_.Exception.Message -notlike "*$Expected*") { throw }
    }
    if (-not $denied) { throw "Unsafe installation was allowed: $Expected" }
    if (Test-Path (Join-Path $root "data/secrets/db.env")) { throw "Preflight wrote a credential file" }
}
try {
    Test-FreshInstallation -ProductRoot $root
    if ($script:dockerCalls -ne 1) { throw "Fresh installation did not inspect Docker storage" }
    $script:dockerResult = @("toefl-house-erp_db-data")
    Assert-Denied "existing TOEFL House database"
    $script:dockerResult = @()
    $script:dockerExit = 1
    Assert-Denied "Could not check existing database storage"
    $script:dockerExit = 0
    $site = Join-Path $root "data/sites/toeflhouse.localhost"
    New-Item -ItemType Directory -Path $site -Force | Out-Null
    $sentinel = Join-Path $site "synthetic.txt"
    [System.IO.File]::WriteAllText($sentinel, "SYNTHETIC PRESERVED DATA")
    $before = (Get-FileHash $sentinel).Hash
    $calls = $script:dockerCalls
    Assert-Denied "Existing site files"
    if ($script:dockerCalls -ne $calls) { throw "Site-file refusal should not query Docker" }
    if ((Get-FileHash $sentinel).Hash -ne $before) { throw "Site data changed" }
    Write-Host "PASS: fresh, existing-volume, Docker-error and existing-site preflight; synthetic data preserved."
} catch {
    Write-Output ("::error title=Fresh install synthetic preflight::" + $_.Exception.Message + " at synthetic test line " + $_.InvocationInfo.ScriptLineNumber)
    throw
} finally {
    # Only this process's randomly named synthetic directory is ever removed.
    Remove-Item -LiteralPath $root -Recurse -Force
    Remove-Item Function:docker
}
