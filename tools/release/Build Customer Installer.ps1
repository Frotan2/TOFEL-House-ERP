# PROVIDER ONLY. Assemble one offline Windows EXE from a verified customer kit.
# The internal variant includes an offline ERP payload and a pinned vendor catalog.
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$WslInstaller = "",
    [string]$DockerInstaller = "",
    [switch]$InternalDelivery,
    [string]$PrivateHttpsArchive = "",
    [Parameter(Mandatory=$true)][string]$OutputExe,
    [string]$RuntimeBundle = "",
    [string]$SigningCertificateThumbprint = "",
    [string]$TimestampServer = "",
    [string]$CustomerReleaseGrant = "",
    [string]$CustomerReleaseSignature = ""
)
$ErrorActionPreference = 'Stop'
$staging = $null
$partial = $null
function Copy-ArchiveInput([string]$Origin, [string]$Destination) {
    # Same-volume provider artifacts can share large, immutable TAR bytes.
    # This is a hard link, never a symlink/junction in the customer archive.
    try {
        New-Item -ItemType HardLink -Path $Destination -Target $Origin -ErrorAction Stop | Out-Null
    } catch { Copy-Item -LiteralPath $Origin -Destination $Destination -ErrorAction Stop }
}

function Get-InstallerSigningCertificate([string]$Thumbprint, [string]$Timestamp) {
    if ($Thumbprint -notmatch '^[0-9a-fA-F]{40}$' -or
        $Timestamp -notmatch '^http://[A-Za-z0-9.-]+(?::[0-9]{2,5})?(/[^\s]*)?$') {
        throw 'A code-signing certificate and Authenticode-compatible HTTP timestamp server are required.'
    }
    $certificates = @(Get-ChildItem 'Cert:\CurrentUser\My', 'Cert:\LocalMachine\My' -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -ieq $Thumbprint })
    $now = [DateTime]::UtcNow
    if ($certificates.Count -ne 1 -or -not $certificates[0].HasPrivateKey -or
        $certificates[0].NotBefore.ToUniversalTime() -gt $now -or
        $certificates[0].NotAfter.ToUniversalTime() -le $now -or
        -not @($certificates[0].EnhancedKeyUsageList |
            Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' }).Count) {
        throw 'One currently valid code-signing certificate with a private key is required.'
    }
    return $certificates[0]
}

function Set-VerifiedFileSignature([string]$Path, $Certificate, [string]$Timestamp) {
    $name = [IO.Path]::GetFileName($Path)
    $signed = Set-AuthenticodeSignature -LiteralPath $Path -Certificate $Certificate -HashAlgorithm SHA256 -TimestampServer $Timestamp
    if ($signed.Status -ne 'Valid') { throw ('Could not sign ' + $name + '.') }
    $identity = Get-AuthenticodeSignature -LiteralPath $Path
    if ($identity.Status -ne 'Valid' -or $null -eq $identity.TimeStamperCertificate -or
        $null -eq $identity.SignerCertificate -or $identity.SignerCertificate.Thumbprint -ine $Certificate.Thumbprint) {
        throw ('Signature, publisher, or timestamp verification failed for ' + $name + '.')
    }
}

try {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if ($TimestampServer -and -not $SigningCertificateThumbprint) {
        throw 'A timestamp server cannot be used without a code-signing certificate.'
    }
    $signingCertificate = $null
    if ($SigningCertificateThumbprint) {
        $signingCertificate = Get-InstallerSigningCertificate $SigningCertificateThumbprint $TimestampServer
    }
    $packageRoot = (Get-Item -LiteralPath $Package).FullName
    $output = [IO.Path]::GetFullPath($OutputExe)
    if ([IO.Path]::GetExtension($output) -ine '.exe' -or (Test-Path -LiteralPath $output)) {
        throw 'Choose a new EXE output path.'
    }
    if ($output.StartsWith($packageRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Output must be outside the input package.'
    }
    if (Test-Path -LiteralPath (Join-Path $packageRoot 'product\data')) {
        throw 'Customer data must never be packaged.'
    }
    $all = @(Get-ChildItem -LiteralPath $packageRoot -Recurse -Force)
    if (@($all | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count -gt 0) {
        throw 'Linked package content is forbidden.'
    }
    # Reuse the provider packager's explicit source allowlist without requiring
    # Python on this Windows build host. Unknown extra files are never copied.
    $packagerSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'create_customer_package.py') -Raw
    $allowlistBlock = [regex]::Match($packagerSource, '(?s)ALLOWED_FILES = \(\r?\n(.*?)\r?\n\)').Groups[1].Value
    if (-not $allowlistBlock) { throw 'Cannot resolve the provider package allowlist.' }
    $allowed = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $sourceFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($match in [regex]::Matches($allowlistBlock, '(?m)^    "([^"\r\n]+)",')) {
        [void]$allowed.Add($match.Groups[1].Value)
        [void]$sourceFiles.Add($match.Groups[1].Value)
    }
    foreach ($name in @('READ ME FIRST.txt', 'product/release/toefl-house-erp-app.tar',
        'product/release/toefl-house-erp-app.tar.sha256', 'product/release/release-manifest.json',
        'product/release/release-manifest.json.sha256', 'product/release/ci-gates.json',
        'product/release/ci-gates.json.sha256')) { [void]$allowed.Add($name) }
    foreach ($file in @($all | Where-Object { -not $_.PSIsContainer })) {
        $relative = $file.FullName.Substring($packageRoot.Length).TrimStart('\').Replace('\', '/')
        if (-not $allowed.Contains($relative)) { throw 'The input kit contains unexpected files. Use a clean qualified provider artifact.' }
    }
    foreach ($relative in $allowed) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageRoot $relative) -PathType Leaf)) {
            throw ('Qualified provider kit component is missing: ' + $relative)
        }
    }
    # Engineering kit receipts remain TEST. Production permission can only
    # come from an independently signed, image-bound customer release grant.
    $manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'product\release\release-manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.production_authorization -cne 'REJECT') { throw 'Expected an engineering candidate manifest.' }
    if ($InternalDelivery) {
        if ($WslInstaller -or $DockerInstaller) {
            throw 'Internal delivery must obtain Windows prerequisites from their publishers.'
        }
        $caddy = Get-Item -LiteralPath $PrivateHttpsArchive -Force
        if ($caddy.PSIsContainer -or ($caddy.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (Get-FileHash -LiteralPath $caddy.FullName).Hash -ine 'ad93112d335ee687100c4c9f11bced16ca590377976b7fe7883882b9e797e472') {
            throw 'Use the qualified stock Caddy 2.11.9 Windows AMD64 archive.'
        }
        $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
        $head = & git --no-optional-locks -C $repoRoot rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or ([string]$head).Trim() -cne $manifest.source_revision) {
            throw 'Internal installer tools must come from the exact verified source revision.'
        }
        $pending = @(& git --no-optional-locks -C $repoRoot status --porcelain --untracked-files=all)
        if ($LASTEXITCODE -ne 0 -or $pending.Count) { throw 'Use a clean source checkout for internal packaging.' }
        $verify = Join-Path $repoRoot 'product\windows\Verify Package Image.ps1'
    } elseif (-not $WslInstaller -or -not $DockerInstaller -or $PrivateHttpsArchive) {
        throw 'Supply the signed WSL and Docker installers for the offline provider build.'
    } else {
        $verify = Join-Path $packageRoot 'product\windows\Verify Package Image.ps1'
    }
    $release = Join-Path $packageRoot 'product\release'
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verify `
        -Archive (Join-Path $release 'toefl-house-erp-app.tar') `
        -Checksum (Join-Path $release 'toefl-house-erp-app.tar.sha256') `
        -Manifest (Join-Path $release 'release-manifest.json') `
        -ManifestChecksum (Join-Path $release 'release-manifest.json.sha256')
    if ($LASTEXITCODE -ne 0) { throw 'Input package verification failed.' }
    foreach ($prereqInput in @(if (-not $InternalDelivery) {
        @{ path = $WslInstaller; publisher = 'Microsoft Corporation' },
        @{ path = $DockerInstaller; publisher = 'Docker Inc\.?' }
    })) {
        $file = Get-Item -LiteralPath $prereqInput.path -Force
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked prerequisite rejected.' }
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
            $signature.SignerCertificate.Subject -notmatch ('(?:^|,\s*)O=' + $prereqInput.publisher + '(?:,|$)')) {
            throw 'Use valid publisher-signed Microsoft WSL and Docker Desktop offline installers.'
        }
    }
    $parent = Split-Path -Parent $output
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $staging = Join-Path $parent ('.customer-build-' + [guid]::NewGuid().ToString('N'))
    $kit = Join-Path $staging 'kit'
    [IO.Directory]::CreateDirectory($kit) | Out-Null
    if ($CustomerReleaseGrant -or $CustomerReleaseSignature) {
        if (-not ($CustomerReleaseGrant -and $CustomerReleaseSignature -and $InternalDelivery -and $signingCertificate)) {
            throw 'Factory customer release requires the signed Windows builder and both production authorization files.'
        }
        $releaseDir = Join-Path $kit 'product\release'
        [IO.Directory]::CreateDirectory($releaseDir) | Out-Null
        foreach ($document in @(
            @{Input=$CustomerReleaseGrant; Name='customer-release.json'},
            @{Input=$CustomerReleaseSignature; Name='customer-release.sig.json'}
        )) {
            $file = Get-Item -LiteralPath $document.Input -ErrorAction Stop
            if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                $file.Length -lt 1 -or $file.Length -gt 8192) {
                throw 'A production authorization input is invalid.'
            }
            [IO.File]::Copy($file.FullName, (Join-Path $releaseDir $document.Name), $false)
        }
        $configDigest = [string]$manifest.image.config_digest
        if ($configDigest -cnotmatch '^sha256:[a-f0-9]{64}$' -or $staging.Contains(',')) {
            throw 'Could not verify the exact provider image for this release.'
        }
        $docker = Get-Command docker.exe -CommandType Application -ErrorAction Stop
        . (Join-Path $packageRoot 'product\windows\Test Local Docker.ps1')
        Assert-LocalDockerEngine
        $archiveDetails = & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verify `
            -Archive (Join-Path $release 'toefl-house-erp-app.tar') -ReadArchiveIdentity
        if ($LASTEXITCODE -ne 0 -or -not $archiveDetails) { throw 'Could not read the verified release archive identity.' }
        $archiveDetails = $archiveDetails | ConvertFrom-Json
        if ($archiveDetails.config_digest -cne $configDigest) {
            throw 'The release archive configuration differs from the verified manifest.'
        }
        $grant = Get-Content -LiteralPath (Join-Path $releaseDir 'customer-release.json') -Raw | ConvertFrom-Json
        if ([string]$grant.oci_manifest_digest -cne [string]$archiveDetails.oci_manifest_digest) {
            throw 'The production authorization must name the verified OCI manifest digest when present.'
        }
        # Classic Docker identifies an image by its config, while containerd
        # identifies it by the OCI manifest verified against that same config.
        $imageId = $null
        foreach ($reference in @($configDigest, $archiveDetails.oci_manifest_digest)) {
            if ($reference -cnotmatch '^sha256:[a-f0-9]{64}$') { continue }
            $loadedId = @(& $docker.Source image inspect $reference --format '{{.Id}}' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $loadedId.Count -eq 1 -and $loadedId[0] -ceq $reference) {
                $imageId = $reference
                break
            }
        }
        if (-not $imageId) { throw 'The verified release archive image is not loaded on the provider.' }
        $releaseCheck = Join-Path $staging 'release-check'
        [IO.Directory]::CreateDirectory($releaseCheck) | Out-Null
        foreach ($name in @('customer-release.json', 'customer-release.sig.json')) {
            [IO.File]::Copy((Join-Path $releaseDir $name), (Join-Path $releaseCheck $name), $false)
        }
        $identity = @{
            schema_version=1; document_type='toefl-house-erp-installed-image'
            provenance='factory'; source_revision=[string]$manifest.source_revision
            image_id=$imageId; factory_release_image_id=$configDigest
        } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText((Join-Path $releaseCheck 'installed-image-identity.json'), $identity)
        $checkArgs = @('run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
            '--mount', "type=bind,source=$releaseCheck,target=/run/activation,readonly",
            '--entrypoint', '/home/frappe/bench/env/bin/python', $imageId, '-c',
            'import sys; sys.path.insert(0, "/product"); from pathlib import Path; from customer_release import verify; print(verify(Path("/run/activation")))')
        & $docker.Source @checkArgs
        if ($LASTEXITCODE -ne 0) {
            throw 'The exact provider image refused the production release grant. No installer was signed.'
        }
    }
    foreach ($relative in $allowed) {
        $source = if ($InternalDelivery -and $sourceFiles.Contains($relative)) {
            $local = Get-Item -LiteralPath (Join-Path $repoRoot $relative) -Force
            if ($local.PSIsContainer -or ($local.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'An installer source file is linked or is not a regular file.'
            }
            $local.FullName
        } else { Join-Path $packageRoot $relative }
        $destination = Join-Path $kit $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        if ($relative -ieq 'product/release/toefl-house-erp-app.tar') {
            Copy-ArchiveInput $source $destination
        } else { Copy-Item -LiteralPath $source -Destination $destination }
    }
    foreach ($required in @('Prepare This PC.ps1', 'Import Offline Runtime.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $kit ('product\windows\' + $required)))) {
            throw 'Rebuild the customer kit from the updated source; do not retrofit an old image release.'
        }
    }
    $prerequisites = Join-Path $kit 'product\prerequisites'
    [IO.Directory]::CreateDirectory($prerequisites) | Out-Null
    if ($InternalDelivery) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows-prerequisites.json') -Destination (
            Join-Path $prerequisites 'vendor-downloads.json')
        $windowsTools = Join-Path $kit 'product\windows'
        $providerWindows = Join-Path $PSScriptRoot 'windows'
        $sourceWindows = Join-Path $repoRoot 'product\windows'
        $operatorFiles = @('Private HTTPS Setup.ps1', 'Private HTTPS Setup.cmd', 'Caddyfile.template')
        $httpsGuide = 'Private HTTPS Setup.md'
        if ($CustomerReleaseGrant) {
            $dariGuide = Join-Path $providerWindows 'Factory Owner Guide - Dari.md'
            $httpsGuide = 'Factory Private HTTPS Setup.md'
            Copy-Item -LiteralPath (Join-Path $repoRoot 'LICENSE') -Destination $kit
        } else {
            $operatorFiles += @(
                'Owner Activation Request.ps1', 'Owner Activation Request.vbs', 'Prepare Internal Activation.ps1',
                'Apply Internal Activation.ps1', 'Apply Internal Activation.vbs'
            )
            Copy-Item -LiteralPath (Join-Path $sourceWindows 'Activate TOEFL House ERP.cmd') -Destination $windowsTools
            $dariSuffix = [string]([char]0x062F) + [char]0x0631 + [char]0x06CC
            $dariGuides = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'docs\engineering') -File -Filter '*.md' |
                Where-Object { $_.BaseName.EndsWith($dariSuffix) })
            if ($dariGuides.Count -ne 1) { throw 'Expected one Dari Owner guide.' }
            $dariGuide = $dariGuides[0].FullName

            $signing = Join-Path $kit 'Approval Signing'
            foreach ($relative in @('tools/release/Sign Internal Activation.pyw','tools/release/create_update_bundle.py',
                                     'product/update_engine.py','product/update_host.py','LICENSE')) {
                $target = Join-Path $signing $relative
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
                Copy-Item -LiteralPath (Join-Path $repoRoot $relative) -Destination $target
            }
        }
        foreach ($name in $operatorFiles) {
            Copy-Item -LiteralPath (Join-Path $providerWindows $name) -Destination $windowsTools
        }
        Copy-Item -LiteralPath (Join-Path $sourceWindows 'Deactivate TOEFL House ERP.cmd') -Destination $windowsTools
        Copy-Item -LiteralPath $caddy.FullName -Destination (Join-Path $windowsTools 'caddy-windows-amd64.zip')
        Copy-Item -LiteralPath $dariGuide -Destination (Join-Path $windowsTools 'Owner Guide - Dari.md')
        Copy-Item -LiteralPath (Join-Path $providerWindows $httpsGuide) -Destination (Join-Path $windowsTools 'Private HTTPS Setup.md')
        $utf8 = New-Object Text.UTF8Encoding($false)
        foreach ($scriptFile in @(Get-ChildItem -LiteralPath $kit -File -Recurse |
            Where-Object Extension -in @('.ps1','.cmd','.vbs'))) {
            $text = [IO.File]::ReadAllText($scriptFile.FullName)
            $filtered = $text -replace '(?i) -ExecutionPolicy Bypass(?=\s|$)', ''
            $filtered = $filtered -replace "(?i)[`"']-ExecutionPolicy[`"'],\s*[`"']Bypass[`"'],\s*", ''
            if ($filtered -match '(?i)ExecutionPolicy[^\r\n]{0,24}Bypass|Unblock-File') {
                throw 'An internal installer script attempts to override Windows trust policy.'
            }
            if ($filtered -cne $text) { [IO.File]::WriteAllText($scriptFile.FullName, $filtered, $utf8) }
        }
    } else {
        Copy-Item -LiteralPath $WslInstaller -Destination (Join-Path $prerequisites 'wsl-x64.msi')
        Copy-Item -LiteralPath $DockerInstaller -Destination (Join-Path $prerequisites 'Docker Desktop Installer.exe')
        $prereqManifest = @{
            schema_version = 1
            wsl = @{ sha256 = (Get-FileHash -LiteralPath (Join-Path $prerequisites 'wsl-x64.msi')).Hash.ToLowerInvariant() }
            docker = @{ sha256 = (Get-FileHash -LiteralPath (Join-Path $prerequisites 'Docker Desktop Installer.exe')).Hash.ToLowerInvariant() }
        }
        [IO.File]::WriteAllText((Join-Path $prerequisites 'manifest.json'), ($prereqManifest | ConvertTo-Json -Depth 5))
    }
    $compose = Get-Content -LiteralPath (Join-Path $kit 'product\docker-compose.yml') -Raw
    if ($RuntimeBundle) {
        # Hosted Windows runners do not need a nested Linux Docker engine.
        # Consume only the three files exported by the same qualified Linux job.
        $runtime = Get-Content -LiteralPath (Join-Path $RuntimeBundle 'offline-runtime.json') -Raw | ConvertFrom-Json
        if ($runtime.schema_version -ne 1 -or $runtime.source_revision -cne $manifest.source_revision -or
            @($runtime.images).Count -ne 2) { throw 'Runtime export does not match this qualified source revision.' }
        $expectedRuntime = @{
            db = @{file='db-image.tar'; tag='toefl-house-erp-db:bundled'; repository='mariadb'}
            cache = @{file='cache-image.tar'; tag='toefl-house-erp-cache:bundled'; repository='redis'}
        }
        $seen = @{}
        foreach ($image in $runtime.images) {
            $key = [string]$image.key
            if (-not $expectedRuntime.ContainsKey($key) -or $seen.ContainsKey($key)) { throw 'Unexpected runtime export entry.' }
            $seen[$key] = $true
            $expectedImage = $expectedRuntime[$key]
            if ($image.file -cne $expectedImage.file -or $image.tag -cne $expectedImage.tag -or
                $image.source -notmatch ('^' + $expectedImage.repository + '@sha256:[a-f0-9]{64}$') -or
                -not $compose.Contains([string]$image.source) -or $image.sha256 -notmatch '^[a-f0-9]{64}$') {
                throw 'Unexpected runtime export identity.'
            }
            $origin = Join-Path $RuntimeBundle $expectedImage.file
            if ((Get-Item -LiteralPath $origin -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime export rejected.' }
            if ((Get-FileHash -LiteralPath $origin).Hash -ine $image.sha256) { throw 'Runtime export integrity verification failed.' }
            $destination = Join-Path $kit ('product\release\' + $expectedImage.file)
            Copy-ArchiveInput $origin $destination
            if ((Get-FileHash -LiteralPath $destination).Hash -ine $image.sha256) { throw 'Runtime export changed while copying.' }
        }
        [IO.File]::WriteAllText((Join-Path $kit 'product\release\offline-runtime.json'), ($runtime | ConvertTo-Json -Depth 30))
    } else {
        $images = @()
        foreach ($row in @(
            @{ key='db'; repository='mariadb'; tag='toefl-house-erp-db:bundled'; file='db-image.tar' },
            @{ key='cache'; repository='redis'; tag='toefl-house-erp-cache:bundled'; file='cache-image.tar' }
        )) {
            $pattern = '(?m)^\s+image:\s+(' + $row.repository + '@sha256:[a-f0-9]{64})\s*$'
            $sourceMatches = [regex]::Matches($compose, $pattern)
            $refs = @($sourceMatches | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
            if ($refs.Count -ne 1) { throw 'Expected one pinned registry identity for each runtime component.' }
            $ref = $refs[0]
            & docker pull --platform linux/amd64 $ref
            if ($LASTEXITCODE -ne 0) { throw 'Provider could not fetch the pinned runtime image.' }
            & docker tag $ref $row.tag
            if ($LASTEXITCODE -ne 0) { throw 'Provider runtime tagging failed.' }
            $raw = & docker image inspect $row.tag --format '{{json .}}'
            if ($LASTEXITCODE -ne 0) { throw 'Provider runtime inspection failed.' }
            $identity = $raw | ConvertFrom-Json
            if ($identity.Os -cne 'linux' -or $identity.Architecture -cne 'amd64') { throw 'Wrong runtime platform.' }
            $archive = Join-Path $kit ('product\release\' + $row.file)
            & docker save --output $archive $row.tag
            if ($LASTEXITCODE -ne 0) { throw 'Provider runtime export failed.' }
            $images += @{
                key=$row.key; source=$ref; tag=$row.tag; file=$row.file
                sha256=(Get-FileHash -LiteralPath $archive).Hash.ToLowerInvariant()
                config=$identity.Config; layers=$identity.RootFS.Layers
            }
        }
        [IO.File]::WriteAllText((Join-Path $kit 'product\release\offline-runtime.json'),
            (@{schema_version=1; images=$images} | ConvertTo-Json -Depth 30))
    }
    $override = @'
services:
  bootstrap:
    pull_policy: never
  web:
    pull_policy: never
  worker:
    pull_policy: never
  scheduler:
    pull_policy: never
  socketio:
    pull_policy: never
  db:
    image: toefl-house-erp-db:bundled
    pull_policy: never
  redis-queue:
    image: toefl-house-erp-cache:bundled
    pull_policy: never
  redis-cache:
    image: toefl-house-erp-cache:bundled
    pull_policy: never
'@
    [IO.File]::WriteAllText((Join-Path $kit 'product\docker-compose.override.yml'), $override)
    [IO.File]::WriteAllText((Join-Path $kit 'READ ME FIRST.txt'), @'
TOEFL HOUSE ERP - OFFLINE WINDOWS TEST INSTALLER
Open the supplied Setup EXE. Follow the Windows permission and license dialogs.
If Windows requests a restart, save your work and restart; open Setup again,
then select Install. No commands, websites or separate downloads are required.
Hardware virtualization must be enabled. Windows component source files must
already be available locally; missing components require provider preparation.
TEST PACKAGE - NO REAL DATA. Production authorization remains REJECT.
'@)
    if ($InternalDelivery) {
        [IO.File]::WriteAllLines((Join-Path $kit 'READ ME FIRST.txt'), [string[]]@(
            'TOEFL HOUSE ERP - CONTROLLED INTERNAL WINDOWS INSTALLER',
            'Open Setup and select Install. Windows may ask you to approve official WSL and Docker Desktop downloads.',
            'Review each publisher prompt. Open the launcher again after a requested restart.',
            'Use the Dari Owner guide for initial setup and maintenance.',
            'Real records require verified Windows, staff access, encrypted backup and independently signed activation.',
            'Public release authorization remains REJECT.'
        ))
    }
    if ($CustomerReleaseGrant) {
        [IO.File]::WriteAllLines((Join-Path $kit 'READ ME FIRST.txt'), [string[]]@(
            'TOEFL HOUSE ERP - WINDOWS INSTALLER',
            'Open Setup. Follow official Windows prerequisite and restart prompts.',
            'When the ERP opens, create your named administrator in its setup wizard.',
            'In the Owner Configuration desk, set up recovery and confirm the first encrypted backup.',
            'Once that backup verifies, the ERP applies the provider release authorization automatically.',
            'Keep your recovery kit in separate custody. Never keep it on the same disk as your backups.',
            'Select Owner Guide - Dari in the TOEFL House ERP launcher for step-by-step instructions.'
        ))
    }
    # Sign the bytes which will actually be compressed and installed. The
    # internal variant rewrites staged scripts above before signing them.
    if ($signingCertificate) {
        foreach ($scriptFile in Get-ChildItem -LiteralPath $kit -File -Recurse -Filter '*.ps1') {
            Set-VerifiedFileSignature $scriptFile.FullName $signingCertificate $TimestampServer
        }
    }
    $payload = Join-Path $staging 'payload.zip'
    $zip = [IO.Compression.ZipFile]::Open($payload, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($file in Get-ChildItem -LiteralPath $kit -File -Recurse) {
            $relative = $file.FullName.Substring($kit.Length).TrimStart('\').Replace('\', '/')
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relative,
                [IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }
    } finally { $zip.Dispose() }
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    $stub = Join-Path $staging 'stub.exe'
    $variant = @()
    if ($InternalDelivery) { $variant += '/define:INTERNAL_UNSIGNED_SETUP' }
    & $compiler @variant /nologo /target:winexe /platform:x64 "/out:$stub" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll (Join-Path $PSScriptRoot 'windows\CustomerSetup.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Windows setup compilation failed.' }
    $partial = $output + '.part-' + [guid]::NewGuid().ToString('N') + '.exe'
    $stream = [IO.File]::Create($partial)
    try {
        foreach ($path in @($stub, $payload)) {
            $inputStream = [IO.File]::OpenRead($path)
            try { $inputStream.CopyTo($stream) } finally { $inputStream.Dispose() }
        }
        $writer = New-Object IO.BinaryWriter($stream)
        $writer.Write([Text.Encoding]::ASCII.GetBytes('THSETUP1'))
        $writer.Write([long](Get-Item -LiteralPath $payload).Length)
        $hash = (Get-FileHash -LiteralPath $payload).Hash
        $bytes = for ($i=0; $i -lt 64; $i+=2) { [Convert]::ToByte($hash.Substring($i,2),16) }
        $writer.Write([byte[]]$bytes)
        $writer.Flush()
    } finally { $stream.Dispose() }
    # Signed publisher identity is separate from the embedded payload hash.
    # Uncertified artifacts can only be used as disposable engineering tests.
    if ($signingCertificate) {
        # PE certificate-table offsets are 32-bit; do not claim to sign a
        # single-file installer that exceeds the supported address range.
        if ((Get-Item -LiteralPath $partial).Length -ge [int64]4294960000) {
            throw 'The offline EXE exceeds the safe PE Authenticode signing limit; shrink the provider image.'
        }
        Set-VerifiedFileSignature $partial $signingCertificate $TimestampServer
    } else {
        Write-Warning 'UNSIGNED TEST INSTALLER ONLY. Not a signed customer deliverable.'
    }
    # Verify the ACTUAL assembled executable, including the signed footer
    # layout and every ZIP payload byte, before publishing the output filename.
    # Windows PowerShell's call operator can return before a GUI EXE exits.
    $verification = Start-Process -FilePath $partial -ArgumentList '--verify-payload' -Wait -PassThru -WindowStyle Hidden
    if ($verification.ExitCode -ne 0) {
        throw 'The assembled Windows installer failed self-verification.'
    }
    # No partial installer is published at the customer-facing filename.
    [IO.File]::Move($partial, $output)
    $partial = $null
    if ($CustomerReleaseGrant) {
        Write-Output ('Built signed factory Windows installer: ' + $output)
        Write-Output 'Publisher signature and payload verified. Qualify this exact executable on Windows before distribution.'
    } else {
        Write-Output ('Built offline TEST installer: ' + $output)
        Write-Output 'Windows clean-machine acceptance is still required. Production authorization: REJECT.'
    }
} finally {
    if ($partial -and (Test-Path -LiteralPath $partial)) { Remove-Item -LiteralPath $partial -Force }
    if ($staging -and (Test-Path -LiteralPath $staging)) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
