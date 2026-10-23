# Read-only protection for the daily Start and supported Repair paths.
# A missing Docker named database volume MUST NOT be silently recreated by
# docker compose up when the credential file and Frappe site still exist.
# No database/credential/file contents are read; no Docker state is changed.
$ErrorActionPreference = "Stop"

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
        Test-ExistingInstallation -ProductRoot ([System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..")))
        Write-Host "[TH_STAGE] Existing database and site location confirmed (contents NOT verified)."
        exit 0
    } catch {
        [Console]::Error.WriteLine("START/REPAIR BLOCKED TO PRESERVE DATA: " + $_.Exception.Message)
        [Console]::Error.WriteLine("Do not reinstall, delete Docker volumes, regenerate passwords or run restore. Ask trusted TOEFL House support.")
        exit 1
    }
}
