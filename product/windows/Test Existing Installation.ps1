param([switch]$CheckServices)
# Read-only protection for the daily Start and supported Repair paths.
# A missing Docker named database volume MUST NOT be silently recreated by
# docker compose up when the credential file and Frappe site still exist.
# No database/credential/file contents are read; no Docker state is changed.
$ErrorActionPreference = "Stop"

function Test-ProductServicesReady {
    # Docker's Windows CLI emits LF-only lines. CMD findstr /x rejects those
    # even when the state is healthy. Parse native JSON in PowerShell instead;
    # require every exact state, never a substring such as "unhealthy".
    $names = @("web", "db", "redis-queue", "redis-cache", "socketio", "worker", "scheduler")
    $containers = @($names | ForEach-Object { "toefl-house-erp-$_" })
    $states = @(& docker inspect --format "{{json .State}}" @containers 2>$null)
    if ($LASTEXITCODE -ne 0 -or $states.Count -ne $names.Count) {
        throw "All seven product services must be available before opening ERP."
    }
    for ($index = 0; $index -lt $states.Count; $index++) {
        $state = $states[$index] | ConvertFrom-Json -ErrorAction Stop
        if ($state.Status -cne "running") {
            throw ("Product service is not running: " + $names[$index])
        }
        if ($index -lt 5 -and $state.Health.Status -cne "healthy") {
            throw ("Product service is not healthy: " + $names[$index])
        }
    }
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ([int]$response.StatusCode -ne 200) {
        throw "The local ERP page is not ready."
    }
}

function Test-ExistingInstallation([string]$ProductRoot) {
    $secret = Join-Path $ProductRoot "data\secrets\db.env"
    $siteConfig = Join-Path $ProductRoot "data\sites\toeflhouse.localhost\site_config.json"
    if (-not (Test-Path -LiteralPath $secret -PathType Leaf)) {
        throw "Local database credentials are missing; do not start, repair or replace them. Contact authorized support."
    }
    if (-not (Test-Path -LiteralPath $siteConfig -PathType Leaf)) {
        throw "The existing Frappe site configuration is missing or incomplete. Stop; do not recreate or repair the site."
    }

    # Docker Compose fixes the named volume as toefl-house-erp_db-data.
    # Verify exact presence, not just a prefix or a successful Docker command.
    $volumeName = "toefl-house-erp_db-data"
    $volumes = @(& docker volume ls --filter "name=$volumeName" --format "{{.Name}}" 2>$null)
    if ($LASTEXITCODE -ne 0) {
        throw "Docker database storage could not be verified. No start or repair was attempted."
    }
    if (-not @($volumes | Where-Object { $_.Trim() -ceq $volumeName }).Count) {
        throw "The existing named database volume is missing. STOP: starting Compose could create an empty replacement."
    }
    & docker volume inspect $volumeName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The named database volume is not accessible. No start or repair was attempted."
    }
}

# Used by daily Windows scripts; also dot-sourceable for isolated tests.
if ($MyInvocation.InvocationName -ne ".") {
    try {
        if ($CheckServices) {
            Test-ProductServicesReady
            Write-Host "[TH_STAGE] All product services and the local ERP page are ready."
            exit 0
        }
        Test-ExistingInstallation -ProductRoot ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")))
        Write-Host "[TH_STAGE] Existing database and site location confirmed (contents NOT verified)."
        exit 0
    } catch {
        if ($CheckServices) {
            [Console]::Error.WriteLine("Product services are not ready; no lifecycle change was attempted.")
            exit 1
        }
        [Console]::Error.WriteLine("START/REPAIR BLOCKED TO PRESERVE DATA: " + $_.Exception.Message)
        [Console]::Error.WriteLine("Do not reinstall, delete Docker volumes, regenerate passwords or run restore. Ask trusted TOEFL House support.")
        exit 1
    }
}
