# Create only the unsigned, one-time activation request for a verified Windows installation.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AcceptanceRecord,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PlainItem([string]$Path, [bool]$Directory) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.FullName -notmatch '^[A-Za-z]:\\' -or $item.PSIsContainer -ne $Directory -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Use regular local files and directories for activation preparation.'
    }
    return $item
}

function Read-Object([string]$Path) {
    $item = Get-PlainItem $Path $false
    if ($item.Length -eq 0 -or $item.Length -gt 65536) {
        throw 'An activation record is empty or has an unexpected size.'
    }
    return (Get-Content -LiteralPath $item.FullName -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Require-Digest($Value, [string]$Pattern, [string]$Name) {
    if ($Value -isnot [string] -or $Value -cnotmatch $Pattern) {
        throw "The $Name is missing or invalid."
    }
}

function Read-Approval($Entry, [string]$Role) {
    if ($Entry.approver_role -cne $Role -or $Entry.approver_identity -isnot [string] -or
        $Entry.approver_identity -notmatch '^[^\p{C}]{1,140}$' -or
        $Entry.approver_identity.Trim() -cne $Entry.approver_identity -or
        [string]::IsNullOrWhiteSpace($Entry.approver_identity) -or $Entry.key_id -isnot [string] -or
        $Entry.key_id -cnotmatch '^[a-z0-9][a-z0-9._-]{2,63}$') {
        throw "Record the verified $Role identity and independently authenticated signing key ID."
    }
    return [ordered]@{
        approver_identity = $Entry.approver_identity
        approver_role = $Role
        key_id = $Entry.key_id
    }
}

$record = Read-Object $AcceptanceRecord
$hostName = [Environment]::MachineName
if ($record.schema_version -ne 1 -or $record.host -ine $hostName -or
    [string]::IsNullOrWhiteSpace($record.acceptance_evidence_reference)) {
    throw 'Provide a completed acceptance record for this Windows computer with a review evidence reference.'
}
foreach ($flag in @('windows_host_acceptance_verified', 'private_staff_access_verified',
        'owner_key_custody_verified', 'rehearsal_restore_verified', 'docker_backup_disk_isolation_verified')) {
    if ($record.$flag -isnot [bool] -or !$record.$flag) {
        throw "The independently recorded acceptance check $flag is required."
    }
}
Require-Digest $record.source_revision '^[0-9a-f]{40}$' 'accepted source revision'
Require-Digest $record.setup_sha256 '^[0-9a-f]{64}$' 'independently accepted Setup SHA-256'
if (@($record.approvals).Count -ne 2) {
    throw 'Record exactly two approvers in the order Course Owner and General Manager.'
}
$owner = Read-Approval $record.approvals[0] 'course-owner'
$manager = Read-Approval $record.approvals[1] 'general-manager'
if ($owner.approver_identity -ieq $manager.approver_identity -or $owner.key_id -ceq $manager.key_id) {
    throw 'The Course Owner and General Manager must have distinct identities and keys.'
}

$target = Get-PlainItem $OutputDirectory $true
$customer = Get-PlainItem (Join-Path $env:LOCALAPPDATA 'TOEFL House ERP\Customer') $true
$destination = Join-Path $target.FullName 'internal-activation.json'
$protectedRoot = $customer.FullName.TrimEnd('\')
if ($target.FullName -ieq $protectedRoot -or $target.FullName.StartsWith(
        $protectedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep the unsigned request outside the installed ERP folder.'
}
if (Test-Path -LiteralPath $destination) {
    throw 'The output request already exists. Use a new review folder for a new request.'
}
$product = Get-PlainItem (Join-Path $customer.FullName 'product') $true
$windows = Get-PlainItem (Join-Path $product.FullName 'windows') $true
$verifyImage = Get-PlainItem (Join-Path $windows.FullName 'Verify Package Image.ps1') $false
$verifyBackup = Get-PlainItem (Join-Path $windows.FullName 'Backup TOEFL House ERP.ps1') $false
$activation = Get-PlainItem (Join-Path $product.FullName 'data\activation') $true
$receipt = Get-PlainItem (Join-Path $activation.FullName 'backup-receipt.json') $false
$receiptDigest = (Get-FileHash -LiteralPath $receipt.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$backupRecord = Read-Object $receipt.FullName
$sourceDrive = $product.FullName.Substring(0, 2)
if ($backupRecord.source_drive -ine $sourceDrive -or $backupRecord.backup_drive -isnot [string] -or
    $backupRecord.backup_drive -notmatch '^[A-Za-z]:$' -or $backupRecord.backup_drive -ieq $sourceDrive) {
    throw 'The backup receipt does not identify a distinct fixed local drive from the installation.'
}
$sourcePartitions = @(Get-Partition -DriveLetter $sourceDrive[0])
$backupPartitions = @(Get-Partition -DriveLetter $backupRecord.backup_drive[0])
if ($sourcePartitions.Count -ne 1 -or $backupPartitions.Count -ne 1 -or
    $null -eq $sourcePartitions[0].DiskNumber -or $null -eq $backupPartitions[0].DiskNumber -or
    $sourcePartitions[0].DiskNumber -eq $backupPartitions[0].DiskNumber) {
    throw 'The ERP install and backup drives could not be proven to be on separate local disks.'
}

foreach ($name in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
        'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_ENV_FILES')) {
    if ([Environment]::GetEnvironmentVariable($name)) {
        throw "Remove the $name override before using the verified local ERP installation."
    }
}
if (Test-Path -LiteralPath (Join-Path $product.FullName '.env')) {
    throw 'Unexpected Compose environment file. Verify the installation before continuing.'
}

$docker = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$docker) {
    foreach ($bin in @((Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'),
                       (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'))) {
        $candidate = Join-Path $bin 'docker.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $docker = Get-Item -LiteralPath $candidate
            break
        }
    }
}
if (!$docker) { throw 'Docker Desktop is unavailable. Open the existing ERP installation first.' }
# The built-in Windows verifiers resolve Docker through PATH.
$dockerPath = if ($docker -is [System.Management.Automation.ApplicationInfo]) { $docker.Source } else { $docker.FullName }
$windowsPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$savedPath = $env:PATH
Push-Location -LiteralPath $product.FullName
try {
    $env:PATH = (Split-Path $dockerPath -Parent) + ';' + $savedPath
    $endpoint = (& $dockerPath context inspect --format '{{.Endpoints.docker.Host}}' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $endpoint -cnotin @('npipe:////./pipe/dockerDesktopLinuxEngine',
            'npipe:////./pipe/docker_engine')) {
        throw 'Docker must point to the local Docker Desktop Windows named pipe.'
    }
    $engine = (& $dockerPath info --format '{{.OSType}}' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $engine -cne 'linux') {
        throw 'The current local Docker Desktop engine is not running Linux containers.'
    }
    & $windowsPowerShell -NoLogo -NoProfile -NonInteractive -File $verifyImage.FullName -VerifyLoadedImage | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The installed ERP image did not pass the package check.' }
    & $windowsPowerShell -NoLogo -NoProfile -NonInteractive -File $verifyBackup.FullName -VerifyExisting | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The current encrypted backup did not pass the Windows activation check.' }
    $rows = @(& $dockerPath compose exec -T web python3 /product/activate.py status)
    if ($LASTEXITCODE -ne 0 -or 'Site operational mode: REFUSED' -cnotin $rows) {
        throw 'Activation preparation requires the verified site in REFUSED mode.'
    }
    $site = 'toeflhouse.localhost'
    $rows = @(& $dockerPath compose exec -T web python3 /product/activate.py internal-context --confirm $site)
    if ($LASTEXITCODE -ne 0) { throw 'The running ERP did not accept the current site and backup context.' }
    $context = ($rows -join "`n") | ConvertFrom-Json
} finally {
    Pop-Location
    $env:PATH = $savedPath
}

$installation = $context.installation
Require-Digest $installation.image_id '^sha256:[0-9a-f]{64}$' 'installed image digest'
Require-Digest $installation.internal_installation_id '^[0-9a-f]{32}$' 'installation identity'
$receiptAfter = Get-PlainItem $receipt.FullName $false
$receiptAfterDigest = (Get-FileHash -LiteralPath $receiptAfter.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($context.site -cne $site -or $installation.source_revision -cne $record.source_revision -or
    $installation.internal_setup_sha256 -cne $record.setup_sha256 -or
    $context.backup_receipt_sha256 -cne $receiptDigest -or $receiptAfterDigest -cne $receiptDigest) {
    throw 'The active site, installer, source revision or backup differs from the verified acceptance context.'
}

$now = [DateTime]::UtcNow
$request = [ordered]@{
    schema_version = 2
    document_type = 'toefl-house-erp-internal-activation'
    site = $site
    scope = 'internal-activation'
    operation = 'internal-activation'
    request_id = [guid]::NewGuid().ToString('N')
    issued_utc = $now.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    expires_utc = $now.AddHours(8).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture)
    owner_key_custody_verified = $record.owner_key_custody_verified
    rehearsal_restore_verified = $record.rehearsal_restore_verified
    windows_host_acceptance_verified = $record.windows_host_acceptance_verified
    backup_receipt_sha256 = $receiptDigest
    approvals = @($owner, $manager)
    installation = [ordered]@{
        source_revision = $installation.source_revision
        image_id = $installation.image_id
        internal_setup_sha256 = $installation.internal_setup_sha256
        internal_installation_id = $installation.internal_installation_id
    }
}
$bytes = [Text.UTF8Encoding]::new($false).GetBytes(($request | ConvertTo-Json -Depth 6) + "`n")
$stream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
} finally {
    $stream.Dispose()
}
Write-Output "Unsigned activation request created at $destination"
Write-Output "Request SHA-256 $((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant())"
