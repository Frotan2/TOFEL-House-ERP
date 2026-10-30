# Real importer with synthetic archives and a fake Docker function; no real services.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$temp = Join-Path $env:TEMP ('offline-runtime-test-' + [guid]::NewGuid().ToString('N'))
$release = Join-Path $temp 'product\release'
$windows = Join-Path $temp 'product\windows'
[IO.Directory]::CreateDirectory($release) | Out-Null
[IO.Directory]::CreateDirectory($windows) | Out-Null
try {
    Copy-Item -LiteralPath (Join-Path $root 'product\windows\Import Offline Runtime.ps1') -Destination $windows
    Copy-Item -LiteralPath (Join-Path $root 'product\docker-compose.yml') -Destination (Join-Path $temp 'product\docker-compose.yml')
    $compose = Get-Content -LiteralPath (Join-Path $temp 'product\docker-compose.yml') -Raw
    $images = @()
    $actual = @{}
    foreach ($row in @(
        @{key='db'; repository='mariadb'; tag='toefl-house-erp-db:bundled'; file='db-image.tar'},
        @{key='cache'; repository='redis'; tag='toefl-house-erp-cache:bundled'; file='cache-image.tar'}
    )) {
        $path = Join-Path $release $row.file
        [IO.File]::WriteAllText($path, 'synthetic image')
        $ref = [regex]::Match($compose, $row.repository + '@sha256:[a-f0-9]{64}').Value
        $config = @{ Env=@('SYNTHETIC=yes'); Cmd=@('synthetic'); User=''; Labels=@{a='1';b='2'} }
        $layers = @('sha256:' + ('1' * 64))
        $images += @{key=$row.key; file=$row.file; tag=$row.tag; source=$ref; config=$config; layers=$layers;
            sha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}
        $actual[$row.tag] = @{Os='linux'; Architecture='amd64'; Config=$config; RootFS=@{Layers=$layers}}
    }
    $actualPath = Join-Path $temp 'actual.json'
    [IO.File]::WriteAllText($actualPath, ($actual | ConvertTo-Json -Depth 20))
    $worker = Join-Path $temp 'fake-worker.ps1'
    @'
$ErrorActionPreference = 'Stop'
$env:TOEFL_OFFLINE_TEST_ROOT = $PSScriptRoot
function docker {
    Add-Content -LiteralPath (Join-Path $env:TOEFL_OFFLINE_TEST_ROOT 'calls.txt') -Value ($args -join ' ')
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'image' -and $args[1] -eq 'inspect') {
        $identities = Get-Content -LiteralPath (Join-Path $env:TOEFL_OFFLINE_TEST_ROOT 'actual.json') -Raw | ConvertFrom-Json
        return ($identities.($args[2]) | ConvertTo-Json -Depth 20 -Compress)
    }
    if ($args[0] -ne 'load') { throw 'Unexpected Docker operation in offline importer.' }
}
& (Join-Path $PSScriptRoot 'product\windows\Import Offline Runtime.ps1')
'@ | Set-Content -LiteralPath $worker -Encoding UTF8
    function Save-Manifest {
        [IO.File]::WriteAllText((Join-Path $release 'offline-runtime.json'),
            (@{schema_version=1;images=$images} | ConvertTo-Json -Depth 20))
    }
    Save-Manifest
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $worker
    if ($LASTEXITCODE -ne 0) { throw 'Valid offline import failed.' }
    $callsPath = Join-Path $temp 'calls.txt'
    $calls = @(Get-Content -LiteralPath $callsPath)
    if ($calls.Count -ne 4 -or @($calls | Where-Object { $_ -match 'pull|compose|volume|prune' }).Count -gt 0) {
        throw 'Offline import touched unexpected Docker operations.'
    }
    Remove-Item -LiteralPath $callsPath
    $images[1].sha256 = '0' * 64
    Save-Manifest
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $worker
    if ($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $callsPath)) { throw 'Corrupt second archive was not rejected before the first Docker operation.' }
    $images[1].sha256 = (Get-FileHash -LiteralPath (Join-Path $release 'cache-image.tar')).Hash.ToLowerInvariant()
    Save-Manifest
    # Keep the expected manifest intact but simulate a mismatched loaded image.
    $actual['toefl-house-erp-db:bundled'].Architecture = 'arm64'
    [IO.File]::WriteAllText($actualPath, ($actual | ConvertTo-Json -Depth 20))
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $worker
    if ($LASTEXITCODE -eq 0) { throw 'Wrong loaded image architecture was accepted.' }
    if (@(Get-Content -LiteralPath $callsPath).Count -ne 2) { throw 'Importer continued after an identity mismatch.' }
    Write-Output 'Real offline importer passed success, pre-import corruption refusal, wrong-image refusal and no-download/no-service-operation checks.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
