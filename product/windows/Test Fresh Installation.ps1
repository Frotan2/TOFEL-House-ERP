# Read-only preflight. Never generate a replacement password for an existing
# database when its local credential file is missing. An inability to inventory
# Docker storage is NOT evidence that the installation is fresh.
$ErrorActionPreference = "Stop"

function Test-FreshInstallation([string]$ProductRoot) {
    if (Test-Path -LiteralPath (Join-Path $ProductRoot "data\sites\toeflhouse.localhost")) {
        throw "Existing site files were found, but the database password file is missing. Stop and recover the original credentials; no password was generated."
    }
    $volumes = @(& docker volume ls --filter "name=toefl-house-erp_db-data" --format "{{.Name}}" 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not check existing database storage. Start Docker Desktop and retry; no password was generated."
    }
    if ($volumes | Where-Object { $_.Trim() -eq "toefl-house-erp_db-data" }) {
        throw "An existing TOEFL House database was found, but its password file is missing. Recover the original credentials; do not reinstall or delete data. No password was generated."
    }
}

# Dot-sourcing exposes the same production function for synthetic Windows CI.
if ($MyInvocation.InvocationName -ne ".") {
    try {
        Test-FreshInstallation -ProductRoot ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")))
        Write-Host "Fresh installation storage check passed."
        exit 0
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}
