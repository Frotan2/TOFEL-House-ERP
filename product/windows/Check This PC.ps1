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
        Result "Current drive free space" ([math]::Round($drive.Free / 1GB, 1).ToString() + " GiB (informational)")
    } else {
        Result "Current drive free space" "Not available"
    }
} catch {
    Result "Current drive free space" "Not available"
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCommand) {
    $candidate = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $dockerCommand = $candidate
    }
}
if (-not $dockerCommand) {
    Result "Docker Desktop" "Docker CLI not found (prerequisite missing)"
} else {
    try {
        $executable = if ($dockerCommand -is [string]) { $dockerCommand } else { $dockerCommand.Source }
        & $executable info *> $null
        if ($LASTEXITCODE -eq 0) {
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

if (Test-Path -LiteralPath (Join-Path $productRoot "data") -PathType Container) {
    Result "Existing local site data" "Present - must be preserved"
} else {
    Result "Existing local site data" "No local site-data folder observed"
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
