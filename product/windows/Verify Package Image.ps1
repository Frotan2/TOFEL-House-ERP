# Verify a supplied customer image BEFORE any Docker import or site change.
# This checksum detects package corruption; it is not a publisher signature.
param(
    [string]$Archive = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar"),
    [string]$Checksum = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar.sha256"),
    [string]$Manifest = (Join-Path $PSScriptRoot "..\release\release-manifest.json"),
    [string]$ManifestChecksum = "",
    [switch]$VerifyLoadedImage,
    [switch]$ReadArchiveIdentity
)
$ErrorActionPreference = "Stop"

function Get-PackageTarPath {
    # Git's GNU tar interprets C:\... as a remote archive even when quoted.
    # Sysnative reaches native System32 from a 32-bit PowerShell process; it
    # does not exist for a native 64-bit process, which uses System32 directly.
    $windowsRoot = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Windows)
    foreach ($directory in @('Sysnative', 'System32')) {
        $candidate = Join-Path $windowsRoot ($directory + '\tar.exe')
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw "Windows built-in tar.exe is missing. Repair the Windows prerequisite before installing this package."
}

function Read-TarMetadata {
    param([string]$Path, [string]$Member)
    # Windows 10/11 include tar.exe. Read stdout bytes, never extract to disk or
    # round-trip config JSON through native text output before hashing it.
    $tar = Get-PackageTarPath
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $tar
    $info.Arguments = '-xOf "' + $resolved + '" -- ' + $Member
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    $buffer = New-Object byte[] 8192
    $bytes = New-Object System.IO.MemoryStream
    $started = $false
    try {
        [void]$process.Start()
        $started = $true
        $errors = $process.StandardError.ReadToEndAsync()
        while (($count = $process.StandardOutput.BaseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($bytes.Length + $count -gt 4MB) { throw "Image archive metadata exceeds the size limit." }
            $bytes.Write($buffer, 0, $count)
        }
        $process.WaitForExit()
        [void]$errors.Result
        if ($process.ExitCode -ne 0 -or $bytes.Length -eq 0) {
            throw "Image archive metadata is missing or unreadable: $Member"
        }
        return ,($bytes.ToArray())
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill() }
        $bytes.Dispose()
        $process.Dispose()
    }
}

function Get-ArchiveIdentity {
    param([string]$Path)
    $encoding = [System.Text.UTF8Encoding]::new($false, $true)
    $text = $encoding.GetString((Read-TarMetadata $Path 'manifest.json'))
    $entries = $text | ConvertFrom-Json
    if ($entries -isnot [array] -or $entries.Count -ne 1 -or
        @($entries[0].RepoTags).Count -ne 1 -or
        $entries[0].RepoTags[0] -cne 'toefl-house-erp-app:local' -or
        $entries[0].Config -notmatch '^(?:[0-9a-f]{64}\.json|blobs/sha256/[0-9a-f]{64})$') {
        throw "The archive must describe exactly one application image with the local tag and a digest-named config."
    }
    $configBytes = Read-TarMetadata $Path $entries[0].Config
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = [BitConverter]::ToString($hasher.ComputeHash($configBytes)).Replace('-', '').ToLowerInvariant()
    } finally { $hasher.Dispose() }
    if ($entries[0].Config -cne "$digest.json" -and $entries[0].Config -cne "blobs/sha256/$digest") {
        throw "The archive config filename does not match its SHA-256 digest."
    }
    $config = $encoding.GetString($configBytes) | ConvertFrom-Json
    if ($null -eq $config.config.Labels -or $config.config.Labels -isnot [pscustomobject]) {
        throw "The archive config labels are missing or malformed."
    }
    foreach ($label in $config.config.Labels.PSObject.Properties) {
        if ($label.Value -isnot [string]) { throw "Archive config labels must be strings." }
    }
    return [pscustomobject]@{
        tag = 'toefl-house-erp-app:local'
        config_digest = 'sha256:' + $digest
        labels = $config.config.Labels
    }
}

try {
    if ($ReadArchiveIdentity) {
        Get-ArchiveIdentity $Archive | ConvertTo-Json -Depth 12 -Compress
        exit 0
    }
    if (-not $ManifestChecksum) { $ManifestChecksum = "$Manifest.sha256" }
    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
        throw "The release manifest is missing. No customer package identity is established."
    }
    if (-not (Test-Path -LiteralPath $ManifestChecksum -PathType Leaf)) {
        throw "The release manifest checksum is missing."
    }
    $manifestChecksumText = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $ManifestChecksum).Path).Trim()
    $manifestName = [regex]::Escape([System.IO.Path]::GetFileName($Manifest))
    if ($manifestChecksumText -notmatch "^([0-9a-fA-F]{64})(?:[ \t]+\*?$manifestName)?$") {
        throw "The release manifest checksum is malformed."
    }
    $manifestExpected = $Matches[1]
    # Hash and parse the same bytes; never parse an unchecked manifest.
    $manifestBytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Manifest).Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $manifestActual = [BitConverter]::ToString($sha.ComputeHash($manifestBytes)).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
    if (-not [string]::Equals($manifestActual, $manifestExpected, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The release manifest failed its SHA-256 check. No import is permitted."
    }
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $release = $utf8.GetString($manifestBytes) | ConvertFrom-Json
    if ($release.schema_version -ne 1 -or $release.product -cne "TOEFL House ERP" -or
        $release.release_status -cne "TEST PACKAGE - NO REAL DATA" -or
        $release.production_authorization -cne "REJECT") {
        throw "The release manifest is not a supported non-production TOEFL House package."
    }
    if ($release.source_revision -notmatch '^[0-9a-fA-F]{40}$' -or
        $release.version -notmatch '^[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}$' -or
        $release.image.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        $release.image.config_digest -notmatch '^sha256:[0-9a-f]{64}$' -or
        $release.image.tag -cne "toefl-house-erp-app:local" -or
        $release.image.labels.'org.toefl-house.source-eol' -cne "lf-v1" -or
        $release.image.labels.'org.toefl-house.source-revision' -cne $release.source_revision -or
        $release.image.labels.'org.toefl-house.release-version' -cne $release.version) {
        throw "The release manifest does not bind the image to its source and version."
    }
    if ($VerifyLoadedImage) {
        $loadedJson = & docker image inspect "toefl-house-erp-app:local" --format '{{json .}}' 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $loadedJson) {
            throw "The packaged application image is not loaded under its required local tag."
        }
        $loaded = $loadedJson | ConvertFrom-Json
        # Docker's containerd store can expose a manifest digest as .Id, not the
        # config digest. Bind config bytes via the archive, and loaded identity
        # via its saved tag and source/version labels instead.
        if (-not (@($loaded.RepoTags) -ccontains $release.image.tag) -or
            $loaded.Config.Labels.'org.toefl-house.source-eol' -cne "lf-v1" -or
            $loaded.Config.Labels.'org.toefl-house.source-revision' -cne $release.source_revision -or
            $loaded.Config.Labels.'org.toefl-house.release-version' -cne $release.version) {
            throw "The loaded image identity does not match the verified release manifest. No start is permitted."
        }
        Write-Host "Customer loaded image identity: verified."
        if ($loaded.Id -match '^sha256:[0-9a-f]{64}$') {
            Write-Host ("Loaded application image ID: " + $loaded.Id)
        }
        exit 0
    }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "The customer image archive is missing."
    }
    if (-not (Test-Path -LiteralPath $Checksum -PathType Leaf)) {
        throw "The checksum file is missing. Never load an unchecked image."
    }
    $checksumText = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Checksum).Path).Trim()
    $archiveName = [regex]::Escape([System.IO.Path]::GetFileName($Archive))
    if ($checksumText -notmatch "^([0-9a-fA-F]{64})(?:[ \t]+\*?$archiveName)?$") {
        throw "The checksum file does not contain exactly one SHA-256 digest."
    }
    $expected = $Matches[1]
    $actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
    if (-not [string]::Equals($actual, $expected,
        [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The customer image failed its SHA-256 check. No import is permitted."
    }
    if (-not [string]::Equals($release.image.sha256, $actual, [System.StringComparison]::OrdinalIgnoreCase) -or
        $release.image.size_bytes -ne (Get-Item -LiteralPath $Archive).Length) {
        throw "The archive does not match the verified release manifest."
    }
    $archiveIdentity = Get-ArchiveIdentity $Archive
    if ($archiveIdentity.config_digest -cne $release.image.config_digest -or
        @($archiveIdentity.labels.PSObject.Properties).Count -ne @($release.image.labels.PSObject.Properties).Count) {
        throw "The archive config does not match the verified release manifest."
    }
    foreach ($label in $archiveIdentity.labels.PSObject.Properties) {
        if ($label.Value -cne $release.image.labels.($label.Name)) {
            throw "The archive config labels do not match the verified release manifest."
        }
    }
    Write-Host "Customer image integrity: verified."
    exit 0
} catch {
    [Console]::Error.WriteLine("Customer image verification failed: " + $_.Exception.Message)
    exit 1
}
