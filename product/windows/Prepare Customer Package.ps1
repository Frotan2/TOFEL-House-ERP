# Provider-side packaging: create a clean, customer-facing folder.
# Requires a verified, locally built app image; never copies site data.
# A checksum protects against accidental corruption, not publisher impersonation.
param([string]$Destination = "")
$ErrorActionPreference = "Stop"

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
    $labelsJson = & docker image inspect "toefl-house-erp-app:local" --format '{{json .Config.Labels}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $labelsJson) {
        throw "Build and verify the application image before preparing a customer package."
    }
    $labels = $labelsJson | ConvertFrom-Json
    if ($labels.'org.toefl-house.source-eol' -ne "lf-v1") {
        throw "The application image lacks the mandatory Linux source-line-ending contract."
    }

    $packageName = "TOEFL-House-ERP-Customer-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $packageRoot = Join-Path $destinationFull $packageName
    if (Test-Path -LiteralPath $packageRoot) {
        throw "The destination package already exists; refusing to overwrite it."
    }
    [System.IO.Directory]::CreateDirectory($packageRoot) | Out-Null

    # Deliberate allowlist: no apps, Docker build context, git, data/secrets,
    # database storage, Administrator password, backups or activation receipts.
    $files = @(
        "TOEFL House ERP.vbs",
        "product/docker-compose.yml",
        "product/windows/TOEFL House ERP.ps1",
        "product/windows/Run TOEFL House ERP.ps1",
        "product/windows/Check This PC.ps1",
        "product/windows/Verify Package Image.ps1",
        "product/windows/Install TOEFL House ERP.cmd",
        "product/windows/Start TOEFL House ERP.cmd",
        "product/windows/Stop TOEFL House ERP.cmd",
        "product/windows/Repair TOEFL House ERP.cmd",
        "product/windows/Test Fresh Installation.ps1"
    )
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
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(
        $checksum, $hash + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $packageRoot "product\windows\Verify Package Image.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "The exported image failed post-packaging verification."
    }

    $instructions = @'
TOEFL HOUSE ERP - CUSTOMER INSTALLATION

1. On the Windows 10/11 (64-bit) main computer, install Docker Desktop from
   https://www.docker.com/products/docker-desktop/ and finish WSL 2 setup.
   This one-time prerequisite may need administrator approval and a restart.
2. Keep this entire package together on a local drive, not inside OneDrive,
   a synchronized folder or a network share.
3. Double-click "TOEFL House ERP.vbs". Select Install. No terminal commands,
   Git download or source-code build are required on this computer.
4. When ready, use Open / Start to access http://127.0.0.1:8000/
   View Administrator Login only on the trusted main computer.
5. Select Check This PC for a read-only technical summary. It does not
   perform backup, restore or production authorization.
6. Future days: double-click the same launcher and choose Open / Start.
   Use Stop to shut down services, Repair for a failed/incomplete setup.

Never delete product\data: it contains site files, secrets and runtime state.
The database is stored in a named local Docker volume. Moving this package
to another computer does NOT transfer the database or existing student data.

IMPORTANT: This is a packaging workflow, not authorization to use real
student or financial records. Follow the current release, policy and backup
holds; verify a clean Windows installation and recovery before delivery.
The SHA-256 sidecar detects corruption but does not authenticate the publisher.
'@
    [System.IO.File]::WriteAllText(
        (Join-Path $packageRoot "READ ME FIRST.txt"), $instructions,
        [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath (Join-Path $packageRoot "product\data")) {
        throw "The customer package unexpectedly contains product data."
    }
    Write-Host "Customer package created (do not deliver until release gates pass): $packageRoot"
    exit 0
} catch {
    [Console]::Error.WriteLine("Customer packaging failed safely: " + $_.Exception.Message)
    [Console]::Error.WriteLine("Any partially created package is NOT deliverable.")
    exit 1
}
