# Verify a supplied customer image BEFORE any Docker import or site change.
# This checksum detects package corruption; it is not a publisher signature.
param(
    [string]$Archive = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar"),
    [string]$Checksum = (Join-Path $PSScriptRoot "..\release\toefl-house-erp-app.tar.sha256"),
    [string]$Manifest = (Join-Path $PSScriptRoot "..\release\release-manifest.json"),
    [string]$ManifestChecksum = "",
    [switch]$VerifyLoadedImage,
    [switch]$RecordFactoryImage,
    [switch]$VerifyProviderImage,
    [switch]$RecordSignedUpdateImage,
    [string]$ExpectedUpdatedImageId = "",
    [string]$ExpectedUpdatedVersion = "",
    [string]$ExpectedUpdatedRevision = "",
    [switch]$ReadArchiveIdentity
)
$ErrorActionPreference = "Stop"

function Get-ProductFileSha256 {
    param([string]$LiteralPath)
    $fullPath = [IO.Path]::GetFullPath($LiteralPath)
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT -and -not $fullPath.StartsWith("\\?\")) {
        if ($fullPath.StartsWith("\\")) { $fullPath = "\\?\UNC\" + $fullPath.Substring(2) }
        else { $fullPath = "\\?\" + $fullPath }
    }
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [IO.File]::OpenRead($fullPath)
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        if ($stream) { $stream.Dispose() }
        $algorithm.Dispose()
    }
}

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
    $rootfs = @($config.rootfs.diff_ids)
    if ($config.rootfs.type -cne 'layers' -or $rootfs.Count -lt 1) {
        throw "The verified release archive has no valid filesystem layers."
    }
    foreach ($layer in $rootfs) {
        if ([string]$layer -cnotmatch '^sha256:[0-9a-f]{64}$') {
            throw "The verified release archive contains an invalid filesystem layer digest."
        }
    }
    return [pscustomobject]@{
        tag = 'toefl-house-erp-app:local'
        config_digest = 'sha256:' + $digest
        labels = $config.config.Labels
        rootfs_layers = $rootfs
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
    if (($RecordFactoryImage -or $VerifyProviderImage -or $RecordSignedUpdateImage) -and -not $VerifyLoadedImage) {
        throw "An image-recording or provider check requires -VerifyLoadedImage."
    }
    if (($RecordFactoryImage -and $RecordSignedUpdateImage) -or
        ($VerifyProviderImage -and ($RecordFactoryImage -or $RecordSignedUpdateImage))) {
        throw "Provider verification and installed-image recording are separate operations."
    }
    if ($VerifyLoadedImage) {
        $loadedJson = & docker image inspect "toefl-house-erp-app:local" --format '{{json .}}' 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $loadedJson) {
            throw "The required application image is not loaded."
        }
        $loaded = $loadedJson | ConvertFrom-Json
        if (-not (@($loaded.RepoTags) -ccontains $release.image.tag) -or
            [string]$loaded.Id -cnotmatch '^sha256:[0-9a-f]{64}$' -or
            $loaded.Config.Labels.'org.toefl-house.source-eol' -cne "lf-v1" -or
            [string]$loaded.Config.Labels.'org.toefl-house.source-revision' -cnotmatch '^[0-9a-fA-F]{40}$' -or
            [string]$loaded.Config.Labels.'org.toefl-house.release-version' -notmatch '^[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}$') {
            throw "The loaded image has an invalid tag or release identity."
        }
        $sourceRevision = [string]$loaded.Config.Labels.'org.toefl-house.source-revision'
        $releaseVersion = [string]$loaded.Config.Labels.'org.toefl-house.release-version'
        $identityPath = Join-Path $PSScriptRoot '..\data\activation\installed-image-identity.json'
        $identityDirectory = Split-Path -Parent $identityPath

        # Both first-install recording and provider export verification bind
        # the real loaded filesystem to the SHA-256 verified original TAR.
        if ($RecordFactoryImage -or $VerifyProviderImage) {
            if ($sourceRevision -cne $release.source_revision -or $releaseVersion -cne $release.version) {
                throw "The original release labels do not match the loaded image."
            }
            if (-not (Test-Path -LiteralPath $Archive -PathType Leaf) -or
                (Get-ProductFileSha256 -LiteralPath $Archive) -cne $release.image.sha256) {
                throw "The factory image archive does not match its verified release checksum."
            }
            $original = Get-ArchiveIdentity $Archive
            if ($original.config_digest -cne $release.image.config_digest) {
                throw "The factory image archive config does not match the verified manifest."
            }
            $expectedLayers = @($original.rootfs_layers)
            $actualLayers = @($loaded.RootFS.Layers)
            if ($expectedLayers.Count -ne $actualLayers.Count) {
                throw "The loaded factory filesystem differs from the verified archive."
            }
            for ($index = 0; $index -lt $expectedLayers.Count; $index++) {
                if ([string]$expectedLayers[$index] -cne [string]$actualLayers[$index]) {
                    throw "The loaded factory filesystem differs from the verified archive."
                }
            }
            if ($VerifyProviderImage) {
                # On the same provider Docker daemon this ID must not change
                # between packaging and final archive verification.
                if ([string]$release.image.provider_image_id -cnotmatch '^sha256:[0-9a-f]{64}$' -or
                    [string]$loaded.Id -cne [string]$release.image.provider_image_id) {
                    throw "Provider image ID changed between export and final verification."
                }
                Write-Host "Provider loaded image ID and filesystem verified."
                exit 0
            }
        }

        if ($RecordFactoryImage -or $RecordSignedUpdateImage) {
            if (-not (Test-Path -LiteralPath $identityDirectory -PathType Container)) {
                throw "Protected installation identity storage is missing."
            }
            if ($RecordFactoryImage -and (Test-Path -LiteralPath $identityPath)) {
                throw "The installed image identity already exists; refusing to overwrite."
            }
            if ($RecordSignedUpdateImage -and
                ($ExpectedUpdatedImageId -cnotmatch '^sha256:[0-9a-f]{64}$' -or
                 $ExpectedUpdatedVersion -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}$' -or
                 $ExpectedUpdatedRevision -cnotmatch '^[0-9a-fA-F]{40}$' -or
                 [string]$loaded.Id -cne $ExpectedUpdatedImageId -or
                 $releaseVersion -cne $ExpectedUpdatedVersion -or
                 $sourceRevision -cne $ExpectedUpdatedRevision -or
                 -not (Test-Path -LiteralPath $identityPath -PathType Leaf))) {
                throw "The signed update image, version or source revision differs from its authorization."
            }
            $record = [ordered]@{
                schema_version = 1
                document_type = 'toefl-house-erp-installed-image'
                provenance = $(if ($RecordFactoryImage) { 'factory' } else { 'signed-update' })
                image_id = [string]$loaded.Id
                source_revision = $sourceRevision
                release_version = $releaseVersion
                original_release_revision = [string]$release.source_revision
            }
            $temporaryIdentity = $identityPath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
            $identityBackup = $identityPath + '.' + [guid]::NewGuid().ToString('N') + '.bak'
            try {
                [IO.File]::WriteAllText($temporaryIdentity, ($record | ConvertTo-Json -Depth 5),
                    (New-Object System.Text.UTF8Encoding($false)))
                if ($RecordFactoryImage) {
                    [IO.File]::Move($temporaryIdentity, $identityPath)
                } else {
                    # Windows PowerShell 5.1/.NET Framework requires a valid
                    # backup path for this atomic replacement overload.
                    # Keep the prior identity recoverable until replacement succeeds.
                    [IO.File]::Replace($temporaryIdentity, $identityPath, $identityBackup)
                }
            } finally {
                if (Test-Path -LiteralPath $temporaryIdentity) {
                    Remove-Item -LiteralPath $temporaryIdentity -Force
                }
                if (Test-Path -LiteralPath $identityBackup) {
                    Remove-Item -LiteralPath $identityBackup -Force
                }
            }
            Write-Host "Verified installed image ID recorded in protected activation storage."
            exit 0
        }

        if (-not (Test-Path -LiteralPath $identityPath -PathType Leaf)) {
            throw "The verified installed-image record is missing. Do not start; contact trusted support for preservation-safe qualification."
        }
        $identityInfo = Get-Item -LiteralPath $identityPath -Force
        if (($identityInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $identityInfo.Length -gt 4096) {
            throw "The installed-image record is unsafe or malformed."
        }
        $identity = [IO.File]::ReadAllText($identityPath) | ConvertFrom-Json
        if ($identity.schema_version -ne 1 -or
            $identity.document_type -cne 'toefl-house-erp-installed-image' -or
            $identity.image_id -cne [string]$loaded.Id -or
            $identity.source_revision -cne $sourceRevision -or
            $identity.release_version -cne $releaseVersion -or
            $identity.original_release_revision -cne $release.source_revision) {
            throw "Loaded Docker image does not match the recorded, verified installed image ID."
        }
        $journalPath = Join-Path $PSScriptRoot '..\data\updates\journal.json'
        $journal = $null
        if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
            $journalInfo = Get-Item -LiteralPath $journalPath -Force
            if (($journalInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                $journalInfo.Length -gt 262144) {
                throw "The update journal is unsafe or malformed; refusing to start."
            }
            $journal = [IO.File]::ReadAllText($journalPath) | ConvertFrom-Json
            if ($journal.schema_version -ne 1 -or
                $journal.document_type -cne 'toefl-house-erp-update-journal' -or
                $journal.phase -cnotin @('idle', 'completed')) {
                throw "An incomplete or unverified signed update requires recovery before daily Start."
            }
        }
        if ($identity.provenance -ceq 'factory') {
            if ($sourceRevision -cne $release.source_revision -or $releaseVersion -cne $release.version -or
                ($null -ne $journal -and $journal.phase -cne 'idle')) {
                throw "Factory installation identity conflicts with the update journal or original release."
            }
        } elseif ($identity.provenance -ceq 'signed-update') {
            if ($null -eq $journal -or $journal.phase -cne 'completed' -or
                $journal.version -cne $releaseVersion) {
                throw "The signed update was not completed or does not match the installed image."
            }
        } else {
            throw "Unknown installed-image provenance; refusing to start."
        }
        Write-Host "Customer installed image identity: approved ID and release record verified."
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
    $actual = (Get-ProductFileSha256 -LiteralPath $Archive)
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
