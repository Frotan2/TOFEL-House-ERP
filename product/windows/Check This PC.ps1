# TOEFL House ERP - read-only Windows readiness observation.
# Safe even while the Owner preservation/restore HOLD remains active.
# Never creates/changes a site, backup, policy, secret, container or volume.
$ErrorActionPreference = "Stop"
Write-Output "[TH_STAGE] Read-only PC check is running..."
Write-Output "TOEFL HOUSE ERP - READ-ONLY TECHNICAL CHECK"
Write-Output "This is an observation, not a setup, repair, release approval or backup rehearsal."
function Result([string]$name, [string]$state) {
    Write-Output ($name + ": " + $state)
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Result "Windows" "Not detected"
} elseif ([Environment]::Is64BitOperatingSystem) {
    Result "Windows" "64-bit detected"
} else {
    Result "Windows" "Unsupported 32-bit system"
}

try {
    $drive = Get-PSDrive -Name ((Get-Location).Drive.Name) -PSProvider FileSystem -ErrorAction Stop
    if ($drive.Free -is [ValueType] -and $drive.Free -ge 0) {
        $freeGiB = [math]::Round($drive.Free / 1GB, 1)
        if ($drive.Free -lt 30GB) {
            Result "Current drive free space" ($freeGiB.ToString() + " GiB; below the documented ~30 GiB installation guideline")
        } else {
            Result "Current drive free space" ($freeGiB.ToString() + " GiB (informational)")
        }
    } else {
        Result "Current drive free space" "Not available"
    }
} catch {
    Result "Current drive free space" "Not available"
}

try {
    # A distinct letter can still be a partition of the same physical disk:
    # this is discovery, never evidence of an approved backup destination.
    $fixedDrives = @([System.IO.DriveInfo]::GetDrives() | Where-Object {
        $_.DriveType -eq [System.IO.DriveType]::Fixed -and $_.IsReady
    })
    if ($fixedDrives.Count -ge 2) {
        Result "Potential local backup volume" "Multiple fixed volumes visible; physical independence and write/recovery checks NOT VERIFIED"
    } else {
        Result "Potential local backup volume" "No second fixed volume observed; actual backup drive NOT VERIFIED"
    }
} catch {
    Result "Potential local backup volume" "Cannot inventory; actual backup drive NOT VERIFIED"
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) {
    $candidate = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $dockerCommand = $candidate
    }
}
$dockerReady = $false
$dockerExe = $null
if (-not $dockerCommand) {
    Result "Docker Desktop" "Docker CLI not found (prerequisite missing)"
} else {
    try {
        $dockerExe = if ($dockerCommand -is [string]) { $dockerCommand } else { $dockerCommand.Source }
        & $dockerExe info *> $null
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            Result "Docker Desktop" "Docker engine responding"
        } else {
            Result "Docker Desktop" "Installed, but engine not responding"
        }
    } catch {
        Result "Docker Desktop" "Cannot verify engine"
    }
}

$productRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (Test-Path -LiteralPath (Join-Path $productRoot "release\toefl-house-erp-app.tar") -PathType Leaf) {
    Result "Prebuilt customer image" "Present (checksum and publisher approval NOT checked by this report)"
} elseif (Test-Path -LiteralPath (Join-Path $productRoot "app.Dockerfile") -PathType Leaf) {
    Result "Installation material" "Developer source checkout, not a ready-to-deliver customer package"
} else {
    Result "Installation material" "Prebuilt image missing; incomplete customer package"
}

$dataRoot = Join-Path $productRoot "data"
$sitePresent = Test-Path -LiteralPath (Join-Path $dataRoot "sites\toeflhouse.localhost") -PathType Container
# A parent folder alone is not an operational Frappe site.
$siteConfigPresent = Test-Path -LiteralPath (Join-Path $dataRoot "sites\toeflhouse.localhost\site_config.json") -PathType Leaf
$sitesRoot = Join-Path $dataRoot "sites"
$siteInventoryVerified = $true
if (Test-Path -LiteralPath $sitesRoot) {
    try {
        # A renamed or partly initialized site is still customer data.
        # Existence only: never read contents or private credentials.
        $sitePresent = $sitePresent -or (@(Get-ChildItem -LiteralPath $sitesRoot -Force -ErrorAction Stop | Select-Object -First 1).Count -gt 0)
    } catch {
        $siteInventoryVerified = $false
    }
}
$secretPresent = Test-Path -LiteralPath (Join-Path $dataRoot "secrets\db.env") -PathType Leaf
$dbVolumePresent = $false
$dbVolumeVerified = $false
if ($dockerReady) {
    try {
        # A successful name inventory distinguishes a genuinely absent volume
        # from an inaccessible Docker API. A failed single-volume inspect
        # cannot distinguish those states on a fresh customer installation.
        # Never read volume contents or print unrelated names/data paths.
        $volumeNames = @(& $dockerExe volume ls --format "{{.Name}}" 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $dbVolumePresent = @($volumeNames | Where-Object {
                $_.Trim() -ceq "toefl-house-erp_db-data"
            }).Count -gt 0
            $dbVolumeVerified = $true
        }
    } catch {
        $dbVolumeVerified = $false
    }
}
if (Test-Path -LiteralPath $dataRoot -PathType Container) {
    Result "Existing local site data" "Present - must be preserved"
} else {
    Result "Existing local site data" "No local site-data folder observed"
}
if (-not $secretPresent -and ($sitePresent -or $dbVolumePresent)) {
    Result "Database credential safety" "BLOCKED: existing site/database but credential file missing. Do NOT reinstall, repair, delete or regenerate credentials."
} elseif ($secretPresent -and -not $siteConfigPresent) {
    Result "Database credential safety" "BLOCKED: credentials exist but site configuration is missing. Do NOT install, start or repair."
} elseif ($secretPresent -and (-not $dbVolumeVerified -or -not $dbVolumePresent)) {
    # A stopped Docker engine, missing volume and Docker API denial all need
    # the same safe response: no Start/Repair or credentials reset until checked.
    Result "Database credential safety" "NOT VERIFIED: credentials exist but the database volume could not be confirmed. Start Docker Desktop and check again; do NOT reinstall."
} elseif ($secretPresent) {
    Result "Database credential safety" "Local credential file present (contents not read; database match NOT VERIFIED)"
} elseif (-not $dbVolumeVerified -or -not $siteInventoryVerified) {
    Result "Database credential safety" "No credential file; local site or database storage could not be ruled out. Do NOT assume a fresh installation."
} else {
    Result "Database credential safety" "No credential file or existing site/database observed (informational, not permission to install)"
}

try {
    $request = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ([int]$request.StatusCode -eq 200) {
        Result "Local browser endpoint" "Responding; authenticated login not verified"
    } else {
        Result "Local browser endpoint" "Not verified"
    }
} catch {
    Result "Local browser endpoint" "Not responding or not yet installed"
}

Result "Owner backup/restore" "HOLD - not tested by this check"
Result "Actual Tailscale staff access" "NOT VERIFIED"
Result "Production authorization" "NOT VERIFIED"
Write-Output "No repair, installation, site change, policy write, backup, restore, activation or data cleanup was attempted."
Write-Output "End of read-only PC check."
