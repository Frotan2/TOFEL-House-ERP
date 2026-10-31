# Import the provider's database/cache images without registry access.
$ErrorActionPreference = 'Stop'
function Canonical($value) {
    if ($null -eq $value) { return 'null' }
    if ($value -is [System.Management.Automation.PSCustomObject]) {
        $parts = @($value.PSObject.Properties | Sort-Object Name | ForEach-Object {
            (ConvertTo-Json -InputObject $_.Name -Compress) + ':' + (Canonical $_.Value)
        })
        return '{' + ($parts -join ',') + '}'
    }
    if ($value -is [Array]) {
        return '[' + ((@($value | ForEach-Object { Canonical $_ })) -join ',') + ']'
    }
    return ConvertTo-Json -InputObject $value -Compress
}
try {
    $release = Join-Path $PSScriptRoot '..\release'
    $manifest = Get-Content -LiteralPath (Join-Path $release 'offline-runtime.json') -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or @($manifest.images).Count -ne 2) {
        throw 'Offline runtime manifest is invalid.'
    }
    $expected = @{
        db = @{ tag = 'toefl-house-erp-db:bundled'; file = 'db-image.tar'; repository = 'mariadb' }
        cache = @{ tag = 'toefl-house-erp-cache:bundled'; file = 'cache-image.tar'; repository = 'redis' }
    }
    $seen = @{}
    $compose = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\docker-compose.yml') -Raw
    # Verify EVERY input before the first image import.
    foreach ($image in $manifest.images) {
        $key = [string]$image.key
        if (-not $expected.ContainsKey($key) -or $seen.ContainsKey($key)) { throw 'Unexpected runtime image.' }
        $seen[$key] = $true
        $item = $expected[$key]
        if ($image.tag -cne $item.tag -or $image.file -cne $item.file -or
            $image.source -notmatch ('^' + $item.repository + '@sha256:[a-f0-9]{64}$') -or
            -not $compose.Contains([string]$image.source) -or
            $image.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Runtime identity is invalid.' }
        $path = Join-Path $release $item.file
        if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Linked runtime archive rejected.'
        }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $image.sha256) {
            throw 'Offline runtime archive integrity verification failed.'
        }
    }
    foreach ($image in $manifest.images) {
        & docker load --input (Join-Path $release $image.file)
        if ($LASTEXITCODE -ne 0) { throw 'Offline runtime import failed.' }
        $raw = & docker image inspect $image.tag --format '{{json .}}'
        if ($LASTEXITCODE -ne 0) { throw 'Imported runtime image is missing.' }
        $actual = $raw | ConvertFrom-Json
        if ($actual.Os -cne 'linux' -or $actual.Architecture -cne 'amd64' -or
            (Canonical $actual.Config) -cne (Canonical $image.config) -or
            (Canonical $actual.RootFS.Layers) -cne (Canonical $image.layers)) {
            throw 'Imported runtime image does not match the supplied identity.'
        }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine('Offline runtime verification failed. No ERP services were started.')
    exit 1
}
