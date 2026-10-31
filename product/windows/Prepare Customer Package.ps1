# Provider-side packaging: create a clean, customer-facing folder.
# Requires a verified, locally built app image; never copies site data.
# A checksum protects against accidental corruption, not publisher impersonation.
param(
    [string]$Destination = "",
    [string]$Version = "",
    [string]$SourceRevision = ""
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

try {
    Add-Type -AssemblyName System.Windows.Forms
    if (-not $Destination) {
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = "Choose where to create a new TOEFL House ERP customer package"
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            Write-Host "Cancelled without changing any existing files."
            exit 0
        }
        $Destination = $dialog.SelectedPath
    }
    $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
    $destinationFull = [System.IO.Path]::GetFullPath($Destination)
    $sourcePrefix = $repositoryRoot.TrimEnd('\') + '\'
    if ($destinationFull.Equals($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $destinationFull.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Choose an output location outside the source repository and its runtime data."
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker Desktop must be installed on the packaging computer."
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Start Docker Desktop on the packaging computer."
    }
    $imageJson = & docker image inspect "toefl-house-erp-app:local" --format '{{json .}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $imageJson) {
        throw "Build and verify the application image before preparing a customer package."
    }
    $image = $imageJson | ConvertFrom-Json
    $labels = $image.Config.Labels
    if ($labels.'org.toefl-house.source-eol' -ne "lf-v1") {
        throw "The application image lacks the mandatory Linux source-line-ending contract."
    }
    if (-not $SourceRevision) {
        $SourceRevision = (& git --no-optional-locks -C $repositoryRoot rev-parse HEAD 2>$null).Trim()
    }
    if ($SourceRevision -notmatch '^[0-9a-fA-F]{40}$') {
        throw "Provide a full source commit SHA; the package must be bound to an exact revision."
    }
    if (-not $Version) { $Version = "local-" + $SourceRevision.Substring(0, 12) }
    if ($Version -notmatch '^[A-Za-z0-9][A-Za-z0-9._+\-]{0,95}$') {
        throw "Package version contains unsupported characters."
    }
    if ($labels.'org.toefl-house.source-revision' -ne $SourceRevision -or
        $labels.'org.toefl-house.release-version' -ne $Version) {
        throw "The image identity does not match the requested source revision and package version. Rebuild the image with those labels."
    }

    # Deliberate allowlist: no apps, Docker build context, git, data/secrets,
    # database storage, Administrator password, backups or activation receipts.
    $files = @(
        "TOEFL House ERP.vbs",
        "product/docker-compose.yml",
        "product/windows/TOEFL House ERP.ps1",
        "product/windows/Run TOEFL House ERP.ps1",
        "product/windows/Prepare This PC.ps1",
        "product/windows/Import Offline Runtime.ps1",
        "product/windows/Check This PC.ps1",
        "product/windows/OWNER ACCEPTANCE GUIDE.txt",
        "product/windows/OWNER HANDBOOK.txt",
        "product/windows/DAILY USE GUIDE.txt",
        "product/windows/Verify Package Image.ps1",
        "product/windows/Install TOEFL House ERP.cmd",
        "product/windows/Start TOEFL House ERP.cmd",
        "product/windows/Stop TOEFL House ERP.cmd",
        "product/windows/Backup TOEFL House ERP.cmd",
        "product/windows/Backup TOEFL House ERP.ps1",
        "product/windows/Repair TOEFL House ERP.cmd",
        "product/windows/Test Fresh Installation.ps1",
        "product/windows/Test Existing Installation.ps1",
        "product/windows/Update TOEFL House ERP.ps1",
        "product/windows/updater-strings.json",
        "product/updates/channel.json"
    )
    $sourceHead = & git --no-optional-locks -C $repositoryRoot rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0 -or -not [string]::Equals(
        ([string]$sourceHead).Trim(), $SourceRevision, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Source checkout HEAD does not match the requested source revision."
    }
    $sourcePaths = @($files) + @('docs/engineering/foundation-version-matrix.json')
    $dirtyFiles = & git --no-optional-locks -C $repositoryRoot status --porcelain=v1 --untracked-files=all -- $sourcePaths 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Cannot verify the selected source checkout." }
    if ($dirtyFiles) { throw "Source checkout has dirty package files or dependency matrix." }
    foreach ($relative in $sourcePaths) {
        $source = Join-Path $repositoryRoot ($relative.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $source -PathType Leaf) -or
            ((Get-Item -LiteralPath $source -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Required package input is missing or linked: $relative"
        }
    }
    $packageName = "TOEFL-House-ERP-Customer-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $packageRoot = Join-Path $destinationFull $packageName
    if (Test-Path -LiteralPath $packageRoot) {
        throw "The destination package already exists; refusing to overwrite it."
    }
    [System.IO.Directory]::CreateDirectory($packageRoot) | Out-Null
    foreach ($relative in $files) {
        $source = Join-Path $repositoryRoot ($relative.Replace('/', '\'))
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Required package component is missing: $relative"
        }
        $file = Get-Item -LiteralPath $source -Force
        if (($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "A package source is a link/junction; refusing to follow it: $relative"
        }
        $target = Join-Path $packageRoot ($relative.Replace('/', '\'))
        [System.IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -ErrorAction Stop
    }

    $releaseDir = Join-Path $packageRoot "product\release"
    [System.IO.Directory]::CreateDirectory($releaseDir) | Out-Null
    $archive = Join-Path $releaseDir "toefl-house-erp-app.tar"
    $checksum = "$archive.sha256"
    Write-Host "Exporting the verified application image into the customer package..."
    & docker save --output $archive "toefl-house-erp-app:local"
    if ($LASTEXITCODE -ne 0) {
        throw "The image export failed. This incomplete folder is NOT deliverable."
    }
    $archiveIdentityJson = & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $packageRoot "product\windows\Verify Package Image.ps1") -Archive $archive -ReadArchiveIdentity
    if ($LASTEXITCODE -ne 0 -or -not $archiveIdentityJson) {
        throw "The exported Docker archive has no valid image identity."
    }
    $archiveIdentity = $archiveIdentityJson | ConvertFrom-Json
    if (@($archiveIdentity.labels.PSObject.Properties).Count -ne @($labels.PSObject.Properties).Count) {
        throw "The exported image labels differ from the inspected application image."
    }
    foreach ($label in $labels.PSObject.Properties) {
        if ($label.Value -cne $archiveIdentity.labels.($label.Name)) {
            throw "The exported image labels differ from the inspected application image."
        }
    }
    $hash = (Get-ProductFileSha256 -LiteralPath $archive)
    [System.IO.File]::WriteAllText(
        $checksum, $hash + "  toefl-house-erp-app.tar" + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
    $matrixPath = Join-Path $repositoryRoot "docs\engineering\foundation-version-matrix.json"
    $matrixHash = (Get-ProductFileSha256 -LiteralPath $matrixPath)
    $matrix = Get-Content -LiteralPath $matrixPath -Raw | ConvertFrom-Json
    $dependencies = @($matrix.components | ForEach-Object {
        $row = [ordered]@{ name = $_.name }
        foreach ($key in @("selected_version", "commit", "digest", "tarball_sha256")) {
            if ($null -ne $_.$key) { $row[$key] = $_.$key }
        }
        [pscustomobject]$row
    })
    $manifest = [ordered]@{
        schema_version = 1
        product = "TOEFL House ERP"
        version = $Version
        release_status = "TEST PACKAGE - NO REAL DATA"
        production_authorization = "REJECT"
        source_revision = $SourceRevision
        image = [ordered]@{
            tag = "toefl-house-erp-app:local"
            config_digest = $archiveIdentity.config_digest
            provider_image_id = $image.Id
            archive = "product/release/toefl-house-erp-app.tar"
            sha256 = $hash
            size_bytes = (Get-Item -LiteralPath $archive).Length
            labels = $labels
        }
        dependency_matrix_sha256 = $matrixHash
        dependencies = $dependencies
        provider_attestation = [ordered]@{
            type = "Local provider package; attach an external signed or GitHub-attested release record before delivery"
            required_for_delivery = $true
        }
        generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    $manifestPath = Join-Path $releaseDir "release-manifest.json"
    $manifestText = $manifest | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText($manifestPath, $manifestText + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
    $manifestHash = (Get-ProductFileSha256 -LiteralPath $manifestPath)
    [System.IO.File]::WriteAllText((Join-Path $releaseDir "release-manifest.json.sha256"),
        $manifestHash + "  release-manifest.json" + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $packageRoot "product\windows\Verify Package Image.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The exported image failed post-packaging verification."
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $packageRoot "product\windows\Verify Package Image.ps1") -VerifyLoadedImage
    if ($LASTEXITCODE -ne 0) {
        throw "The application image tag changed during export. This incomplete folder is NOT deliverable."
    }

    $instructions = @"
TOEFL HOUSE ERP - CUSTOMER INSTALLATION ($Version)

This folder is an engineering kit, not the final one-file customer delivery.
The provider must assemble the offline Setup EXE with the signed Windows
prerequisites and database/cache images before customer handover.

1. Use the provider-supplied Setup EXE on the Windows x64 main computer.
   Follow its Windows permission/license dialogs and restart if requested.
2. Keep this entire package together on a local drive, not inside OneDrive,
   a synchronized folder or a network share.
3. Double-click "TOEFL House ERP.vbs". Select Install. No terminal commands,
   Git download or source-code build are required on this computer.
4. When ready, use Open / Start to access http://127.0.0.1:8000/
   View Administrator Login only on the trusted main computer.
5. Select Check This PC for a read-only technical summary. It does not
   perform backup, restore or production authorization.
   Select Owner Readiness Guide to open safe tests and explicit HOLD warnings.
   Select How to Use for daily, nontechnical instructions for each staff role.
6. Future days: double-click the same launcher and choose Open / Start.
   Use Stop to shut down services, Repair for a failed/incomplete setup.

Never delete product\data: it contains site files, secrets and runtime state.
The database is stored in a named local Docker volume. Moving this package
to another computer does NOT transfer the database or existing student data.

The provider release manifest is in product\release\release-manifest.json.
It binds this package to source revision $SourceRevision, the prebuilt image,
and the dependency matrix. Keep the separately issued provider/GitHub
attestation with this package; a bare checksum detects corruption but does
not identify the publisher.

IMPORTANT: This is a packaging workflow, not authorization to use real
student or financial records. Follow the current release, policy and backup
holds; verify a clean Windows installation and recovery before delivery.
Production authorization remains REJECT until the Owner gates are closed.
"@
    [System.IO.File]::WriteAllText(
        (Join-Path $packageRoot "READ ME FIRST.txt"), $instructions,
        [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath (Join-Path $packageRoot "product\data")) {
        throw "The customer package unexpectedly contains product data."
    }
    Write-Host "Customer package created (version $Version; do not deliver until release gates pass): $packageRoot"
    exit 0
} catch {
    [Console]::Error.WriteLine("Customer packaging failed safely: " + $_.Exception.Message)
    [Console]::Error.WriteLine("Any partially created package is NOT deliverable.")
    exit 1
}
