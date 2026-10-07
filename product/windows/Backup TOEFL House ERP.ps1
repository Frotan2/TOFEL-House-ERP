$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot

$sourceDrive = ((Get-Location).Path.Substring(0, 2)).ToUpperInvariant()
$destinationDrive = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
    Where-Object { $_.DeviceID -ne $sourceDrive -and $_.FreeSpace -gt 1073741824 } |
    Sort-Object FreeSpace -Descending |
    Select-Object -First 1

if (-not $destinationDrive) {
    throw "Backup refused: no second fixed drive with at least 1 GiB free space was found."
}

$backupRoot = Join-Path $destinationDrive.DeviceID "TOEFL-House-ERP-Backups"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

Write-Host "Enabling native encrypted backups..."
& docker compose -f product/docker-compose.yml exec -T web /build/tools/bin/bench --site toeflhouse.localhost execute "frappe.db.set_single_value('System Settings', 'encrypt_backup', 1)"
if ($LASTEXITCODE -ne 0) { throw "Could not enable native backup encryption." }

Write-Host "Creating full encrypted backup..."
& docker compose -f product/docker-compose.yml exec -T web /build/tools/bin/bench --site toeflhouse.localhost backup --with-files
if ($LASTEXITCODE -ne 0) { throw "Backup command failed." }

$sourceDir = Join-Path $repoRoot "product\data\sites\toeflhouse.localhost\private\backups"
$db = Get-ChildItem -LiteralPath $sourceDir -Filter "*-database-enc.sql.gz" -File |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

if (-not $db) { throw "Backup refused: encrypted database backup was not produced." }

$base = $db.Name -replace "-database-enc\.sql\.gz$", ""
$names = @(
    "$base-database-enc.sql.gz",
    "$base-files-enc.tar",
    "$base-private-files-enc.tar",
    "$base-site_config_backup-enc.json"
)

$setRoot = Join-Path $backupRoot $base
New-Item -ItemType Directory -Force -Path $setRoot | Out-Null

$manifest = @()
foreach ($name in $names) {
    $source = Join-Path $sourceDir $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Backup refused: required artifact is missing: $name"
    }
    $destination = Join-Path $setRoot $name
    Copy-Item -LiteralPath $source -Destination $destination -Force
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($hash -ne $sourceHash) {
        throw "Backup verification failed for $name"
    }
    $manifest += [pscustomobject]@{
        name = $name
        sha256 = $hash
        bytes = (Get-Item -LiteralPath $destination).Length
    }
}

$manifestPath = Join-Path $setRoot "manifest.json"
[pscustomobject]@{
    schema_version = 1
    backup_set = $base
    source_drive = $sourceDrive
    backup_drive = $destinationDrive.DeviceID
    encrypted = $true
    artifacts = $manifest
    created_utc = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

foreach ($item in $manifest) {
    $path = Join-Path $setRoot $item.name
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) {
        throw "Post-write integrity verification failed for $($item.name)"
    }
}

Write-Host ""
Write-Host "Backup completed and verified."
Write-Host "Backup drive: $($destinationDrive.DeviceID)"
Write-Host "Backup set:  $setRoot"
Write-Host "Encryption: native Frappe encrypted backup"
Write-Host "Integrity:  SHA-256 verified"
