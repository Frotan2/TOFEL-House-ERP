param(
    [switch]$VerifyExisting
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repoRoot
$site = "toeflhouse.localhost"
$taskName = "TOEFL House ERP Backup"
$scriptPath = Join-Path $PSScriptRoot "Backup TOEFL House ERP.ps1"
$compose = @("compose", "-f", "product/docker-compose.yml")
$sourceDrive = $null
$destinationDrive = $null
$sourceDir = Join-Path $repoRoot "product\data\sites\$site\private\backups"
$backupStartedUtc = (Get-Date).ToUniversalTime().AddSeconds(-5)
$mutex = New-Object System.Threading.Mutex($false, "Local\TOEFLHouseERPBackup")
$mutexHeld = $false
$transcriptPath = Join-Path $repoRoot "product\data\logs\backup-schedule.log"
$transcriptStarted = $false
$backupRunStarted = $false
$backupCompleted = $false
$recoveryPublicKeyTempPath = $null
$recoveryPublicKeyContainerPath = $null
$gnupgHomeContainer = $null
$recoveryConfigSourcePath = $null
$exitCode = 0

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose command failed with exit code $LASTEXITCODE."
    }
}

function Get-OwnerBackupPolicy {
    $output = & docker @compose exec -T web /build/tools/bin/bench --site $site execute `
        "toefl_house.operations.owner_configuration.current_backup_policy" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the Course Owner backup policy from ERPNext."
    }
    $jsonLine = @($output | ForEach-Object { [string]$_ } |
        Where-Object { $_.TrimStart().StartsWith("{") } | Select-Object -Last 1)
    if (-not $jsonLine -or -not $jsonLine[0]) {
        throw "ERPNext did not return a machine-readable backup policy."
    }
    try {
        return ($jsonLine[0] | ConvertFrom-Json -ErrorAction Stop)
    }
    catch {
        throw "ERPNext returned an invalid backup policy response."
    }
}

function Get-OwnerRecoveryPublicKeyB64 {
    $output = & docker @compose exec -T web /build/tools/bin/bench --site $site execute `
        "toefl_house.operations.owner_configuration.current_backup_public_key_b64" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the Course Owner's public recovery key from ERPNext."
    }
    $keyLine = @($output | ForEach-Object { ([string]$_).Trim() } |
        Where-Object { $_ -match "^[A-Za-z0-9+/]+=*$" } | Select-Object -Last 1)
    if (-not $keyLine -or -not $keyLine[0]) {
        throw "ERPNext did not return the configured public recovery key."
    }
    return $keyLine[0]
}

function Get-OwnerRecoveryKeyMaterial {
    try {
        $bytes = [Convert]::FromBase64String((Get-OwnerRecoveryPublicKeyB64))
    }
    catch {
        throw "The configured Owner public recovery key could not be retrieved or decoded."
    }
    $armored = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($armored -notmatch "-----BEGIN PGP PUBLIC KEY BLOCK-----" -or
        $armored -notmatch "-----END PGP PUBLIC KEY BLOCK-----" -or
        $armored -match "PRIVATE KEY") {
        throw "The configured Owner recovery key is not ASCII-armored public-key material."
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally { $sha.Dispose() }
    return [pscustomobject]@{ Bytes = $bytes; Hash = $hash; Text = $armored }
}

function Assert-OwnerPolicyMatches {
    param($Receipt)
    $policy = Get-OwnerBackupPolicy
    if ($policy.configured -ne $true -or
        $Receipt.policy_hash -ne $policy.policy_hash -or
        $Receipt.schedule_time -ne $policy.schedule_time -or
        [int]$Receipt.retention_versions -ne [int]$policy.retention_versions -or
        $Receipt.recovery_key_sha256 -ne $policy.recovery_key_sha256) {
        throw "The current verified backup does not match the active Course Owner backup policy."
    }
    return $policy
}

function Get-NativeArtifactSuffixes {
    return @(
        "-database-enc.sql.gz",
        "-files-enc.tar",
        "-private-files-enc.tar"
    )
}

function Get-ArtifactSuffixes {
    return @((Get-NativeArtifactSuffixes) + "-site-config.gpg")
}

function Get-ManifestSha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-ExactBackupSetFiles {
    param([System.IO.DirectoryInfo]$Directory, [string[]]$ArtifactNames)
    if (($Directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        return $false
    }
    $entries = @(Get-ChildItem -LiteralPath $Directory.FullName -Force -ErrorAction Stop)
    if ($entries.Count -ne 5) { return $false }
    foreach ($entry in $entries) {
        if ($entry.PSIsContainer -or
            ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $false
        }
    }
    $expectedNames = @(@("manifest.json") + $ArtifactNames | Sort-Object)
    $actualNames = @($entries | ForEach-Object { $_.Name } | Sort-Object)
    return (($actualNames -join "|") -eq ($expectedNames -join "|"))
}

function Test-ValidRotatableManifest {
    param([System.IO.DirectoryInfo]$Directory)
    if (($Directory.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        return $null
    }
    $path = Join-Path $Directory.FullName "manifest.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try {
        $manifest = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        if ($manifest.schema_version -ne 2 -or
            $manifest.verified -ne $true -or
            $manifest.encrypted -ne $true -or
            $manifest.backup_set -ne $Directory.Name -or
            -not [regex]::IsMatch([string]$manifest.policy_hash, "^[a-f0-9]{64}$") -or
            -not [regex]::IsMatch([string]$manifest.recovery_key_sha256, "^[a-f0-9]{64}$")) {
            return $null
        }
        $expectedNames = @(Get-ArtifactSuffixes | ForEach-Object { "$($manifest.backup_set)$_" } | Sort-Object)
        if (-not (Test-ExactBackupSetFiles -Directory $Directory -ArtifactNames $expectedNames)) {
            return $null
        }
        $items = @($manifest.artifacts)
        $names = @($items | ForEach-Object { [string]$_.name } | Sort-Object)
        if ($items.Count -ne 4 -or ($names -join "|") -ne ($expectedNames -join "|")) {
            return $null
        }
        foreach ($item in $items) {
            $expectedRole = switch -Exact ([string]$item.name) {
                "$($manifest.backup_set)-database-enc.sql.gz" { "database"; break }
                "$($manifest.backup_set)-files-enc.tar" { "public_files"; break }
                "$($manifest.backup_set)-private-files-enc.tar" { "private_files"; break }
                "$($manifest.backup_set)-site-config.gpg" { "recovery_config"; break }
                default { "" }
            }
            $artifactPath = Join-Path $Directory.FullName ([string]$item.name)
            if (-not $expectedRole -or $item.role -ne $expectedRole -or
                -not [regex]::IsMatch([string]$item.sha256, "^[a-f0-9]{64}$") -or
                [long]$item.bytes -le 0 -or
                -not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
                return $null
            }
            $artifact = Get-Item -LiteralPath $artifactPath -Force
            if (($artifact.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $artifact.Length -ne [long]$item.bytes -or
                (Get-ManifestSha256 $artifactPath) -ne [string]$item.sha256) {
                return $null
            }
        }
        if (Get-ChildItem -LiteralPath $Directory.FullName -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue) {
            return $null
        }
        $created = [DateTimeOffset]::Parse([string]$manifest.created_utc).UtcDateTime
        return [pscustomobject]@{ Directory = $Directory; CreatedUtc = $created }
    }
    catch {
        return $null
    }
}

function Remove-ExpiredBackupSets {
    param([string]$Root, [int]$KeepCount, [string]$CurrentSet, [string]$ProtectSet = "")
    $sets = @(Get-ChildItem -LiteralPath $Root -Directory -Force |
        ForEach-Object { Test-ValidRotatableManifest $_ } |
        Where-Object { $_ -ne $null } |
        Sort-Object CreatedUtc -Descending)
    $keep = @($sets | Select-Object -First $KeepCount)
    if (-not ($keep | Where-Object { $_.Directory.Name -eq $CurrentSet })) {
        throw "Retention plan would discard the newly verified backup; no backup sets were rotated."
    }
    $keepNames = @($keep | ForEach-Object { $_.Directory.Name })
    if ($ProtectSet -and ($sets | Where-Object { $_.Directory.Name -eq $ProtectSet })) {
        $keepNames += $ProtectSet
    }
    foreach ($set in $sets) {
        if ($keepNames -notcontains $set.Directory.Name) {
            Remove-Item -LiteralPath $set.Directory.FullName -Recurse -Force
        }
    }
}

function Write-BackupReceipt {
    param($Receipt)
    $receiptPath = Join-Path $repoRoot "product\data\secrets\backup-receipt.json"
    $temporary = "$receiptPath.tmp.$PID"
    $Receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $receiptPath -Force
}

function Verify-ExistingBackup {
    $receiptPath = Join-Path $repoRoot "product\data\secrets\backup-receipt.json"
    if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
        throw "No verified backup receipt exists. Run Backup TOEFL House ERP.cmd first."
    }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    if ($receipt.schema_version -ne 1 -or
        $receipt.source_site -ne $site -or
        $receipt.encrypted -ne $true -or
        $receipt.verified -ne $true -or
        $receipt.automation_ready -ne $true -or
        $receipt.task_name -ne $taskName) {
        throw "The latest backup receipt is not complete, encrypted, verified and scheduled."
    }
    $created = [DateTimeOffset]::Parse([string]$receipt.created_utc).UtcDateTime
    $age = ((Get-Date).ToUniversalTime() - $created).TotalSeconds
    if ($age -lt -300 -or $age -gt 86400) {
        throw "The verified backup receipt is not from the last 24 hours."
    }
    $policy = Assert-OwnerPolicyMatches $receipt
    $recoveryKey = Get-OwnerRecoveryKeyMaterial
    if ($recoveryKey.Hash -ne [string]$policy.recovery_key_sha256) {
        throw "The current Owner public recovery key does not match the verified backup policy."
    }
    if (-not [regex]::IsMatch([string]$receipt.backup_set, "^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")) {
        throw "The verified backup receipt has an unsafe backup-set identity."
    }
    if (-not [regex]::IsMatch([string]$receipt.source_drive, "^[A-Za-z]:$") -or
        -not [regex]::IsMatch([string]$receipt.backup_drive, "^[A-Za-z]:$") -or
        $receipt.source_drive.ToUpperInvariant() -eq $receipt.backup_drive.ToUpperInvariant()) {
        throw "The verified backup receipt does not identify two different local drives."
    }
    if ($repoRoot -notmatch "^[A-Za-z]:" -or
        $receipt.source_drive.ToUpperInvariant() -ne $repoRoot.Substring(0, 2).ToUpperInvariant()) {
        throw "The verified backup receipt does not match the current product source drive."
    }
    $backupDisk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
        Where-Object { $_.DeviceID -eq $receipt.backup_drive.ToUpperInvariant() } |
        Select-Object -First 1
    if (-not $backupDisk) {
        throw "The separate fixed local backup drive is unavailable."
    }
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task -or $task.State -eq "Disabled" -or
        @($task.Actions).Count -ne 1 -or @($task.Triggers).Count -ne 1) {
        throw "The Owner-configured Windows backup task is missing, disabled or incomplete."
    }
    $expectedPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $taskAction = $task.Actions[0]
    if (-not ([string]$taskAction.Execute).Equals($expectedPowerShell, [StringComparison]::OrdinalIgnoreCase) -or
        -not ([string]$taskAction.Arguments).Contains($scriptPath)) {
        throw "The scheduled task action does not invoke this product's backup script."
    }
    $taskTrigger = $task.Triggers[0]
    try { $taskStart = [DateTime]::Parse([string]$taskTrigger.StartBoundary) }
    catch { throw "The scheduled task has an invalid daily start time." }
    if ([int]$taskTrigger.DaysInterval -ne 1 -or
        $taskStart.ToString("HH:mm", [Globalization.CultureInfo]::InvariantCulture) -ne [string]$policy.schedule_time -or
        [string]$task.Principal.LogonType -notmatch "Interactive") {
        throw "The scheduled task does not match the current Owner-selected daily time and interactive Docker user."
    }
    $expectedRoot = Join-Path ([string]$receipt.backup_drive) "TOEFL-House-ERP-Backups"
    if (-not (Test-Path -LiteralPath $expectedRoot -PathType Container) -or
        ((Get-Item -LiteralPath $expectedRoot -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "The separate local backup root is missing or is a junction/symbolic link."
    }
    $backupPath = [System.IO.Path]::GetFullPath([string]$receipt.backup_path)
    $expectedBackupPath = [System.IO.Path]::GetFullPath((Join-Path $expectedRoot ([string]$receipt.backup_set)))
    if (-not $backupPath.Equals($expectedBackupPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw "The verified backup is not the exact expected backup-set directory on the separate local drive."
    }
    if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
        throw "The separate local backup drive or current backup set is unavailable."
    }
    if ((Test-Path -LiteralPath $sourceDir -PathType Container) -and
        (Get-ChildItem -LiteralPath $sourceDir -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue)) {
        throw "A plaintext Frappe site-config sidecar remains in the native backup folder; run a fresh backup before activation."
    }
    if (Get-ChildItem -LiteralPath $backupPath -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue) {
        throw "A plaintext site-config sidecar is present in the backup set; the backup is refused."
    }
    $manifestPath = Join-Path $backupPath "manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        (Get-ManifestSha256 $manifestPath) -ne [string]$receipt.manifest_sha256) {
        throw "The copied backup manifest is missing or changed."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    if ($manifest.schema_version -ne 2 -or
        $manifest.backup_set -ne $receipt.backup_set -or
        $manifest.source_drive -ne $receipt.source_drive -or
        $manifest.backup_drive -ne $receipt.backup_drive -or
        $manifest.created_utc -ne $receipt.created_utc -or
        $manifest.encrypted -ne $true -or
        $manifest.verified -ne $true -or
        $manifest.source_site -ne $site -or
        $manifest.policy_hash -ne $policy.policy_hash -or
        $manifest.recovery_key_sha256 -ne $policy.recovery_key_sha256 -or
        @($manifest.artifacts).Count -ne 4) {
        throw "The copied backup manifest does not match the current verified receipt."
    }
    $suffixes = Get-ArtifactSuffixes
    $expectedNames = @($suffixes | ForEach-Object { "$($receipt.backup_set)$_" } | Sort-Object)
    if (-not (Test-ExactBackupSetFiles -Directory (Get-Item -LiteralPath $backupPath -Force) `
            -ArtifactNames $expectedNames)) {
        throw "The copied backup set must contain only manifest.json and exactly four safe encrypted payload files."
    }
    $receiptNames = @($receipt.artifacts | ForEach-Object { [string]$_.name } | Sort-Object)
    $manifestNames = @($manifest.artifacts | ForEach-Object { [string]$_.name } | Sort-Object)
    if (($expectedNames -join "|") -ne ($receiptNames -join "|") -or
        ($expectedNames -join "|") -ne ($manifestNames -join "|")) {
        throw "The copied backup set does not contain exactly the encrypted database, files and site-config recovery artifacts."
    }
    foreach ($item in $receipt.artifacts) {
        $expectedRole = switch -Exact ([string]$item.name) {
            "$($receipt.backup_set)-database-enc.sql.gz" { "database"; break }
            "$($receipt.backup_set)-files-enc.tar" { "public_files"; break }
            "$($receipt.backup_set)-private-files-enc.tar" { "private_files"; break }
            "$($receipt.backup_set)-site-config.gpg" { "recovery_config"; break }
            default { "" }
        }
        if (-not $expectedRole -or $item.role -ne $expectedRole -or
            -not [regex]::IsMatch([string]$item.sha256, "^[a-f0-9]{64}$") -or
            [long]$item.bytes -le 0) {
            throw "Backup receipt has an invalid role, digest or byte size for $($item.name)."
        }
        $path = Join-Path $backupPath ([string]$item.name)
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne [string]$item.sha256 -or
            (Get-Item -LiteralPath $path -Force).Length -ne [long]$item.bytes) {
            throw "Copied backup artifact failed SHA-256/size verification: $($item.name)"
        }
        $manifestItem = @($manifest.artifacts | Where-Object { $_.name -eq $item.name }) | Select-Object -First 1
        if (-not $manifestItem -or $manifestItem.role -ne $expectedRole -or
            [string]$manifestItem.sha256 -ne [string]$item.sha256 -or
            [long]$manifestItem.bytes -ne [long]$item.bytes) {
            throw "Backup receipt and manifest disagree for $($item.name)."
        }
    }
    Write-Host "The separate local drive, current encrypted backup set, receipt and Owner policy all verify."
}

try {
    if (-not $mutex.WaitOne(0)) {
        throw "Another backup operation is already running."
    }
    $mutexHeld = $true
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $transcriptPath) | Out-Null
    Start-Transcript -LiteralPath $transcriptPath -Append | Out-Null
    $transcriptStarted = $true

    if ($VerifyExisting) {
        Verify-ExistingBackup
    }
    else {
        if ($repoRoot -notmatch "^[A-Za-z]:") {
            throw "Backup requires the TOEFL House product folder to be on a local Windows drive."
        }
        $sourceDrive = $repoRoot.Substring(0, 2).ToUpperInvariant()
        $sourceDisk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
            Where-Object { $_.DeviceID -eq $sourceDrive } | Select-Object -First 1
        if (-not $sourceDisk) {
            throw "Backup source must be on a fixed local Windows drive."
        }
        $policy = Get-OwnerBackupPolicy
        $policyConfigured = ($policy.configured -eq $true -and
            [regex]::IsMatch([string]$policy.schedule_time, "^(?:[01][0-9]|2[0-3]):[0-5][0-9]$") -and
            [int]$policy.retention_versions -ge 2 -and
            [regex]::IsMatch([string]$policy.policy_hash, "^[a-f0-9]{64}$") -and
            [regex]::IsMatch([string]$policy.recovery_key_sha256, "^[a-f0-9]{64}$"))
        if (-not $policyConfigured) {
            throw "OWNER_POLICY_REQUIRED: Configure the Owner nightly backup, multi-version retention and public recovery key in the ERP Configuration desk before backing up."
        }
        $recoveryKey = Get-OwnerRecoveryKeyMaterial
        if ($recoveryKey.Hash -ne [string]$policy.recovery_key_sha256) {
            throw "The Owner public recovery key does not match its effective backup-policy identity."
        }
        $recoveryPublicKeyTempPath = Join-Path $env:TEMP "toefl-house-recovery-public-$PID.asc"
        [System.IO.File]::WriteAllBytes($recoveryPublicKeyTempPath, [byte[]]$recoveryKey.Bytes)
        $gnupgHomeContainer = "/tmp/toefl-house-backup-gpg-$PID"
        $recoveryPublicKeyContainerPath = "$gnupgHomeContainer/recovery-public.asc"
        $destinationDrive = $null
        $protectedReceiptSet = ""
        $oldReceiptPath = Join-Path $repoRoot "product\data\secrets\backup-receipt.json"
        if (Test-Path -LiteralPath $oldReceiptPath -PathType Leaf) {
            try {
                $oldReceipt = Get-Content -LiteralPath $oldReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
                if ([regex]::IsMatch([string]$oldReceipt.backup_drive, "^[A-Za-z]:$") -and
                    $oldReceipt.backup_drive.ToUpperInvariant() -ne $sourceDrive) {
                    if ([regex]::IsMatch([string]$oldReceipt.backup_set, "^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")) {
                        $protectedReceiptSet = [string]$oldReceipt.backup_set
                    }
                    $destinationDrive = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
                        Where-Object { $_.DeviceID -eq $oldReceipt.backup_drive.ToUpperInvariant() } |
                        Select-Object -First 1
                    if (-not $destinationDrive) {
                        throw "The previously selected backup drive $($oldReceipt.backup_drive) is unavailable; insert it before continuing."
                    }
                    if ($destinationDrive.FreeSpace -le 1073741824) {
                        throw "The previously selected backup drive has less than 1 GiB free; free space before continuing."
                    }
                }
            }
            catch {
                if ($_.Exception.Message -like "The previously selected backup drive*") { throw }
                $destinationDrive = $null
            }
        }
        if (-not $destinationDrive) {
            $destinationDrive = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
                Where-Object { $_.DeviceID -ne $sourceDrive -and $_.FreeSpace -gt 1073741824 } |
                Sort-Object FreeSpace -Descending |
                Select-Object -First 1
        }
        if (-not $destinationDrive) {
            throw "Backup refused: no separate fixed local drive with at least 1 GiB free space was found."
        }

        $backupRoot = Join-Path $destinationDrive.DeviceID "TOEFL-House-ERP-Backups"
        New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
        if (((Get-Item -LiteralPath $backupRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Backup refused: the backup root must not be a junction or symbolic link."
        }

        Write-Host "Enabling native encrypted backups..."
        Invoke-Compose @("exec", "-T", "web", "/build/tools/bin/bench", "--site", $site,
            "execute", "frappe.db.set_single_value('System Settings', 'encrypt_backup', 1)")

        Write-Host "Creating full encrypted backup..."
        $backupStartedUtc = (Get-Date).ToUniversalTime().AddSeconds(-5)
        $backupRunStarted = $true
        Invoke-Compose @("exec", "-T", "web", "/build/tools/bin/bench", "--site", $site,
            "backup", "--with-files")

        $database = Get-ChildItem -LiteralPath $sourceDir -Filter "*-database-enc.sql.gz" -File |
            Where-Object { $_.LastWriteTimeUtc -ge $backupStartedUtc } |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (-not $database) {
            throw "Backup refused: no new encrypted database artifact was produced."
        }
        $base = $database.Name -replace "-database-enc\.sql\.gz$", ""
        if (-not [regex]::IsMatch($base, "^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")) {
            throw "Backup refused: the native backup set has an unsafe name."
        }
        $setRoot = Join-Path $backupRoot $base
        if (Test-Path -LiteralPath $setRoot) {
            throw "Backup refused: refusing to overwrite an existing backup set named $base."
        }
        $recoveryConfigName = "$base-site-config.gpg"
        $recoveryConfigSourcePath = Join-Path $sourceDir $recoveryConfigName
        if (Test-Path -LiteralPath $recoveryConfigSourcePath) {
            throw "Backup refused: a recovery artifact with this backup-set name already exists."
        }
        $sidecars = @(Get-ChildItem -LiteralPath $sourceDir -Filter "$base-site_config_backup*.json" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTimeUtc -ge $backupStartedUtc })
        if ($sidecars.Count -ne 1) {
            throw "Backup refused: expected exactly one new Frappe site-config recovery sidecar for this backup set."
        }
        $siteConfigSidecar = $sidecars[0]
        if (($siteConfigSidecar.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $siteConfigSidecar.Length -le 0) {
            throw "Backup refused: the Frappe site-config recovery sidecar is empty or unsafe."
        }
        try {
            $siteConfigText = [System.IO.File]::ReadAllText($siteConfigSidecar.FullName)
            $siteConfigObject = $siteConfigText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "Backup refused: the Frappe site-config recovery sidecar is not valid JSON."
        }
        if (-not $siteConfigObject.encryption_key) {
            throw "Backup refused: the site-config recovery artifact has no native Frappe backup encryption key."
        }
        $siteConfigObject = $null
        $siteConfigText = $null

        $temporaryRoot = Join-Path $backupRoot (".staging-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
        try {
            Invoke-Compose @("exec", "-T", "web", "mkdir", "-m", "700", "-p", $gnupgHomeContainer)
            $copyOutput = & docker @compose cp $recoveryPublicKeyTempPath "web:$recoveryPublicKeyContainerPath" 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "Could not transfer the Owner public recovery key into the disposable container GPG home."
            }
            Invoke-Compose @("exec", "-T", "web", "gpg", "--batch", "--homedir", $gnupgHomeContainer,
                "--import", $recoveryPublicKeyContainerPath)
            $keyListing = & docker @compose exec -T web gpg --batch --homedir $gnupgHomeContainer --with-colons --list-keys 2>&1
            if ($LASTEXITCODE -ne 0) {
                throw "GPG could not enumerate the imported Owner recovery public key."
            }
            $fingerprints = @($keyListing | ForEach-Object {
                $line = [string]$_
                if ($line.StartsWith("fpr:")) {
                    $fields = $line.Split(":")
                    if ($fields.Count -gt 9 -and $fields[9] -match "^[A-Fa-f0-9]{40,64}$") {
                        $fields[9].ToUpperInvariant()
                    }
                }
            } | Where-Object { $_ } | Select-Object -Unique)
            if ($fingerprints.Count -lt 1) {
                throw "GPG did not import a usable Owner recovery public key."
            }
            $recipientIds = @($fingerprints | ForEach-Object { $_.Substring($_.Length - 16) } | Select-Object -Unique)
            $recipientIdPattern = ($recipientIds | ForEach-Object { [regex]::Escape($_) }) -join "|"

            $containerSidecar = "/home/frappe/bench/sites/$site/private/backups/$($siteConfigSidecar.Name)"
            $containerRecoveryConfig = "/home/frappe/bench/sites/$site/private/backups/$recoveryConfigName"
            Invoke-Compose @("exec", "-T", "web", "gpg", "--batch", "--yes", "--no-tty",
                "--homedir", $gnupgHomeContainer, "--trust-model", "always",
                "--recipient", $fingerprints[0], "--output", $containerRecoveryConfig,
                "--encrypt", $containerSidecar)
            if (-not (Test-Path -LiteralPath $recoveryConfigSourcePath -PathType Leaf)) {
                throw "GPG did not create the encrypted site-config recovery artifact."
            }
            $configPackets = & docker @compose exec -T web gpg --batch --homedir $gnupgHomeContainer --list-packets $containerRecoveryConfig 2>&1
            if ($LASTEXITCODE -ne 0 -or
                -not ($configPackets -match ":pubkey enc packet:") -or
                -not ($configPackets -match "(?im)\bkeyid\s+(?:$recipientIdPattern)\b")) {
                throw "The site-config recovery artifact is not an OpenPGP public-key encryption packet for the configured Owner key."
            }

            $requiredCopyBytes = [long](Get-Item -LiteralPath $recoveryConfigSourcePath).Length
            foreach ($suffix in (Get-NativeArtifactSuffixes)) {
                $requiredCopyBytes += [long](Get-Item -LiteralPath (Join-Path $sourceDir "$base$suffix")).Length
            }
            $marginBytes = [long][Math]::Max(67108864, [Math]::Ceiling($requiredCopyBytes * 0.05))
            $currentBackupDisk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
                Where-Object { $_.DeviceID -eq $destinationDrive.DeviceID } | Select-Object -First 1
            if (-not $currentBackupDisk -or
                [long]$currentBackupDisk.FreeSpace -lt ($requiredCopyBytes + $marginBytes)) {
                throw "Backup refused: the separate local drive lacks space for this verified set plus a safety margin."
            }

            $artifacts = @()
            foreach ($suffix in (Get-NativeArtifactSuffixes)) {
                $name = "$base$suffix"
                $source = Join-Path $sourceDir $name
                if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                    throw "Backup refused: required encrypted artifact is missing: $name"
                }
                $sourceItem = Get-Item -LiteralPath $source -Force
                if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
                    $sourceItem.Length -le 0) {
                    throw "Backup refused: required encrypted artifact is empty or unsafe: $name"
                }
                $containerPath = "/home/frappe/bench/sites/$site/private/backups/$name"
                $packetOutput = & docker @compose exec -T web gpg --list-packets $containerPath 2>&1
                if ($LASTEXITCODE -ne 0 -or -not ($packetOutput -match ":symkey enc packet:")) {
                    throw "Backup refused: GPG did not verify actual native encryption packets for $name"
                }
                $destination = Join-Path $temporaryRoot $name
                Copy-Item -LiteralPath $source -Destination $destination
                $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
                $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
                $bytes = (Get-Item -LiteralPath $destination).Length
                if ($destinationHash -ne $sourceHash -or $bytes -le 0) {
                    throw "Backup verification failed for $name"
                }
                $artifacts += [pscustomobject]@{
                    role = switch -Regex ($suffix) {
                        "^-database-" { "database"; break }
                        "^-files-" { "public_files"; break }
                        "^-private-files-" { "private_files"; break }
                    }
                    name = $name
                    sha256 = $destinationHash
                    bytes = $bytes
                }
            }

            $configDestination = Join-Path $temporaryRoot $recoveryConfigName
            Copy-Item -LiteralPath $recoveryConfigSourcePath -Destination $configDestination
            $configSourceHash = (Get-FileHash -LiteralPath $recoveryConfigSourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
            $configDestinationHash = (Get-FileHash -LiteralPath $configDestination -Algorithm SHA256).Hash.ToLowerInvariant()
            $configBytes = (Get-Item -LiteralPath $configDestination).Length
            if ($configDestinationHash -ne $configSourceHash -or $configBytes -le 0) {
                throw "Encrypted site-config recovery artifact failed copy and size verification."
            }
            $artifacts += [pscustomobject]@{
                role = "recovery_config"
                name = $recoveryConfigName
                sha256 = $configDestinationHash
                bytes = $configBytes
            }
            if (@($artifacts | Select-Object -ExpandProperty role -Unique).Count -ne 4) {
                throw "Backup refused: the verified set is missing a unique database/files/recovery role."
            }
            if (Get-ChildItem -LiteralPath $temporaryRoot -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue) {
                throw "Backup refused: a plaintext site-config sidecar entered the backup set."
            }

            # The Frappe sidecar has a misleading -enc suffix but is plaintext.
            # Only its GPG-encrypted, Owner-recipient artifact is retained.
            Get-ChildItem -LiteralPath $sourceDir -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue |
                Remove-Item -Force
            Get-ChildItem -LiteralPath $backupRoot -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0 } |
                ForEach-Object {
                    Get-ChildItem -LiteralPath $_.FullName -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue |
                        Remove-Item -Force
                }

            $created = (Get-Date).ToUniversalTime().ToString("o")
            $manifest = [pscustomobject]@{
                schema_version = 2
                backup_set = $base
                source_site = $site
                source_drive = $sourceDrive
                backup_drive = $destinationDrive.DeviceID
                encrypted = $true
                verified = $true
                policy_hash = [string]$policy.policy_hash
                recovery_key_sha256 = [string]$policy.recovery_key_sha256
                schedule_time = [string]$policy.schedule_time
                retention_versions = [int]$policy.retention_versions
                artifacts = $artifacts
                created_utc = $created
            }
            $manifestPath = Join-Path $temporaryRoot "manifest.json"
            $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
            Move-Item -LiteralPath $temporaryRoot -Destination $setRoot
        }
        catch {
            if (Test-Path -LiteralPath $temporaryRoot) {
                Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
            throw
        }

        foreach ($item in $artifacts) {
            $copiedPath = Join-Path $setRoot $item.name
            if ((Get-FileHash -LiteralPath $copiedPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.sha256 -or
                (Get-Item -LiteralPath $copiedPath).Length -ne [long]$item.bytes) {
                throw "Post-write integrity verification failed for $($item.name)"
            }
        }

        $scheduleAt = [DateTime]::ParseExact([string]$policy.schedule_time, "HH:mm",
            [Globalization.CultureInfo]::InvariantCulture)
        $action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe") `
            -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $scriptPath)
        $trigger = New-ScheduledTaskTrigger -Daily -At $scheduleAt
        $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
            -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 3)
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings `
            -Description "Owner-configured encrypted TOEFL House ERP local backup" -Force | Out-Null
        $registered = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
        if (-not $registered -or $registered.State -eq "Disabled") {
            throw "The Windows scheduled backup task could not be verified."
        }

        Remove-ExpiredBackupSets -Root $backupRoot `
            -KeepCount ([int]$policy.retention_versions) -CurrentSet $base `
            -ProtectSet $protectedReceiptSet

        $manifestPath = Join-Path $setRoot "manifest.json"
        $manifestHash = Get-ManifestSha256 $manifestPath
        $receipt = [pscustomobject]@{
            schema_version = 1
            source_site = $site
            source_drive = $sourceDrive
            backup_drive = $destinationDrive.DeviceID
            backup_root = $backupRoot
            backup_path = $setRoot
            backup_set = $base
            created_utc = $created
            encrypted = $true
            verified = $true
            automation_ready = $true
            task_name = $taskName
            schedule_time = [string]$policy.schedule_time
            retention_versions = [int]$policy.retention_versions
            policy_hash = [string]$policy.policy_hash
            recovery_key_sha256 = [string]$policy.recovery_key_sha256
            manifest_sha256 = $manifestHash
            artifacts = $artifacts
        }
        Write-BackupReceipt $receipt
        $backupCompleted = $true
        Write-Host ""
        Write-Host "Backup completed, GPG-encryption verified, copied and SHA-256 verified."
        Write-Host "Nightly task: $taskName at $($policy.schedule_time) local time"
        Write-Host "Retained verified versions: $($policy.retention_versions)"
        Write-Host "Separate local drive: $($destinationDrive.DeviceID)"
        Write-Host "Backup set: $setRoot"
        Write-Host "Receipt updated only after content, task and retention verification."
    }
}
catch {
    if ($_.Exception.Message -like "OWNER_POLICY_REQUIRED:*") {
        $exitCode = 2
        Write-Host $_.Exception.Message.Substring("OWNER_POLICY_REQUIRED: ".Length) -ForegroundColor Yellow
    }
    else {
        $exitCode = 1
        Write-Host "Backup/verification failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}
finally {
    if ($backupRunStarted) {
        Get-ChildItem -LiteralPath $sourceDir -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
        if ($backupRoot -and (Test-Path -LiteralPath $backupRoot -PathType Container)) {
            Get-ChildItem -LiteralPath $backupRoot -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0 } |
                ForEach-Object {
                    Get-ChildItem -LiteralPath $_.FullName -Filter "*-site_config_backup*.json" -File -ErrorAction SilentlyContinue |
                        Remove-Item -Force -ErrorAction SilentlyContinue
                }
        }
        if (-not $backupCompleted -and $recoveryConfigSourcePath -and
            (Test-Path -LiteralPath $recoveryConfigSourcePath -PathType Leaf)) {
            Remove-Item -LiteralPath $recoveryConfigSourcePath -Force -ErrorAction SilentlyContinue
        }
    }
    if ($gnupgHomeContainer) {
        try {
            & docker @compose exec -T web rm -rf -- $gnupgHomeContainer 2>&1 | Out-Null
        }
        catch { }
    }
    if ($recoveryPublicKeyTempPath -and (Test-Path -LiteralPath $recoveryPublicKeyTempPath -PathType Leaf)) {
        Remove-Item -LiteralPath $recoveryPublicKeyTempPath -Force -ErrorAction SilentlyContinue
    }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
    }
    if ($mutexHeld) {
        try { $mutex.ReleaseMutex() } catch { }
    }
    $mutex.Dispose()
}
exit $exitCode
