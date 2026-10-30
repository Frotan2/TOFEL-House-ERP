# PROVIDER ONLY. Assemble one offline Windows EXE from a verified customer kit.
# Downloads happen here on the provider PC, never on the customer PC.
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$WslInstaller,
    [Parameter(Mandatory=$true)][string]$DockerInstaller,
    [Parameter(Mandatory=$true)][string]$OutputExe
)
$ErrorActionPreference = 'Stop'
$staging = $null
$partial = $null
try {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
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
    foreach ($match in [regex]::Matches($allowlistBlock, '(?m)^    "([^"\r\n]+)",')) {
        [void]$allowed.Add($match.Groups[1].Value)
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
    # The EXE remains a test candidate; this builder grants no production approval.
    $manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'product\release\release-manifest.json') -Raw | ConvertFrom-Json
    if ($manifest.production_authorization -cne 'REJECT') { throw 'Expected an engineering candidate manifest.' }
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (
        Join-Path $packageRoot 'product\windows\Verify Package Image.ps1'
    )
    if ($LASTEXITCODE -ne 0) { throw 'Input package verification failed.' }
    foreach ($prereqInput in @(
        @{ path = $WslInstaller; publisher = 'Microsoft Corporation' },
        @{ path = $DockerInstaller; publisher = 'Docker Inc\.?' }
    )) {
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
    foreach ($file in @($all | Where-Object { -not $_.PSIsContainer })) {
        $relative = $file.FullName.Substring($packageRoot.Length).TrimStart('\')
        $destination = Join-Path $kit $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination
    }
    foreach ($required in @('Prepare This PC.ps1', 'Import Offline Runtime.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $kit ('product\windows\' + $required)))) {
            throw 'Rebuild the customer kit from the updated source; do not retrofit an old image release.'
        }
    }
    $prerequisites = Join-Path $kit 'product\prerequisites'
    [IO.Directory]::CreateDirectory($prerequisites) | Out-Null
    Copy-Item -LiteralPath $WslInstaller -Destination (Join-Path $prerequisites 'wsl-x64.msi')
    Copy-Item -LiteralPath $DockerInstaller -Destination (Join-Path $prerequisites 'Docker Desktop Installer.exe')
    $prereqManifest = @{
        schema_version = 1
        wsl = @{ sha256 = (Get-FileHash -LiteralPath (Join-Path $prerequisites 'wsl-x64.msi')).Hash.ToLowerInvariant() }
        docker = @{ sha256 = (Get-FileHash -LiteralPath (Join-Path $prerequisites 'Docker Desktop Installer.exe')).Hash.ToLowerInvariant() }
    }
    [IO.File]::WriteAllText((Join-Path $prerequisites 'manifest.json'), ($prereqManifest | ConvertTo-Json -Depth 5))
    $compose = Get-Content -LiteralPath (Join-Path $kit 'product\docker-compose.yml') -Raw
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
    & $compiler /nologo /target:winexe /platform:x64 "/out:$stub" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll (Join-Path $PSScriptRoot 'windows\CustomerSetup.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Windows setup compilation failed.' }
    $partial = $output + '.part-' + [guid]::NewGuid().ToString('N')
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
    # No partial installer is published at the customer-facing filename.
    [IO.File]::Move($partial, $output)
    $partial = $null
    Write-Output ('Built offline TEST installer: ' + $output)
    Write-Output 'Windows clean-machine acceptance is still required. Production authorization: REJECT.'
} finally {
    if ($partial -and (Test-Path -LiteralPath $partial)) { Remove-Item -LiteralPath $partial -Force }
    if ($staging -and (Test-Path -LiteralPath $staging)) { Remove-Item -LiteralPath $staging -Recurse -Force }
}
