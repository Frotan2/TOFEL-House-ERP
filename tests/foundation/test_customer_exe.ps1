# Execute the real C# extractor on Windows without installing any prerequisites.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$temp = Join-Path $env:TEMP ('customer-exe-test-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    $assembly = Join-Path $temp 'extractor.dll'
    & $compiler /nologo /target:library /platform:x64 /define:INTERNAL_UNSIGNED_SETUP "/out:$assembly" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll (Join-Path $root 'tools\release\windows\CustomerSetup.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Actual customer setup code did not compile.' }
    Add-Type -Path $assembly
    function Make-Zip([string]$path, [string[]]$names) {
        $zip = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($name in $names) {
                $entry = $zip.CreateEntry($name)
                $writer = New-Object IO.StreamWriter($entry.Open())
                try { $writer.Write('synthetic') } finally { $writer.Dispose() }
            }
        } finally { $zip.Dispose() }
    }
    $good = Join-Path $temp 'good.zip'
    Make-Zip $good @('product/windows/test.txt')
    $destination = Join-Path $temp 'good'
    [CustomerSetup]::ExtractPayload($good, $destination)
    if ((Get-Content -LiteralPath (Join-Path $destination 'product/windows/test.txt') -Raw) -cne 'synthetic') {
        throw 'Valid customer payload was not extracted.'
    }
    # Use the entry and path depth that triggered the actual .NET Framework failure.
    $profile = Join-Path $temp ('profile-' + ('x' * [Math]::Max(1, 152 - $temp.Length)))
    $product = Join-Path $profile 'TOEFL House ERP'
    $null = [IO.Directory]::CreateDirectory($product)
    $entry = 'product/release/ci-gates.json.sha256'
    $old = Join-Path $product ('.setup-' + ('a' * 32) + '\files')
    if ((Join-Path $old $entry).Length -lt 260) {
        throw 'The long profile fixture does not reproduce the old path length.'
    }
    $longProfileZip = Join-Path $temp 'deep-profile.zip'
    $longest = 'product/release/toefl-house-erp-app.tar.sha256'
    Make-Zip $longProfileZip @($entry, $longest)
    $staging = [CustomerSetup]::CreateStagingDirectory($profile)
    $stagedFiles = Join-Path $staging 'p'
    if ((Split-Path -Parent $staging) -ine [IO.Path]::GetFullPath($profile)) {
        throw 'Setup did not place staging directly in the per-user profile.'
    }
    if ((Join-Path $stagedFiles $longest).Length -ge 260) {
        throw 'Setup did not leave enough Windows path space for the payload.'
    }
    [CustomerSetup]::ExtractPayload($longProfileZip, $stagedFiles)
    $published = Join-Path $product 'Customer'
    [IO.Directory]::Move($stagedFiles, $published)
    if ([IO.File]::ReadAllText((Join-Path $published $longest)) -cne 'synthetic') {
        throw 'The short-path extraction did not publish the complete payload.'
    }
    $installer = Join-Path $temp 'downloaded-setup-fixture.exe'
    $launchFile = Join-Path $destination 'product/windows/start.ps1'
    [IO.File]::WriteAllText($installer, 'synthetic setup')
    [IO.File]::WriteAllText($launchFile, 'synthetic script')
    [CustomerSetup]::PreserveDownloadMarker($installer, $destination)
    if (Get-Item -LiteralPath $launchFile -Stream Zone.Identifier -ErrorAction SilentlyContinue) {
        throw 'Local setup unexpectedly marked an extracted script.'
    }
    $marker = "[ZoneTransfer]`r`nZoneId=3`r`n"
    Set-Content -LiteralPath $installer -Stream Zone.Identifier -Encoding ascii -NoNewline -Value $marker
    [CustomerSetup]::PreserveDownloadMarker($installer, $destination)
    if ((Get-Content -LiteralPath $launchFile -Stream Zone.Identifier -Raw) -cne $marker -or
        [IO.File]::ReadAllText($launchFile) -cne 'synthetic script' -or
        (Get-Item -LiteralPath (Join-Path $destination 'product/windows/test.txt') -Stream Zone.Identifier -ErrorAction SilentlyContinue)) {
        throw 'Setup failed to preserve the download marker on the extracted script only.'
    }
    foreach ($names in @(
        @('good.txt', '../escape.txt'), @('good.txt', '/absolute.txt'),
        @('good.txt', 'C:\escape.txt'), @('good.txt', 'file:stream'),
        @('same.txt', 'SAME.txt'),
        @('good.txt', 'level./child.txt'),
        @('good.txt', 'level /child.txt'),
        @('good.txt', 'CON.txt'),
        @('good.txt', 'AUX'),
        @('good.txt', 'COM1/child.txt'),
        @('good.txt', 'LPT9.txt'),
        @('good.txt', 'folder\child.txt')
    )) {
        $id = [guid]::NewGuid().ToString('N')
        $bad = Join-Path $temp ($id + '.zip')
        Make-Zip $bad $names
        $destination = Join-Path $temp $id
        $refused = $false
        try { [CustomerSetup]::ExtractPayload($bad, $destination) } catch { $refused = $true }
        if (-not $refused) { throw 'Unsafe installer payload was accepted.' }
        if (Test-Path -LiteralPath (Join-Path $destination 'good.txt')) { throw 'Extractor wrote files before validating the archive.' }
    }
    # A high file-count archive must fail before creating even the first file.
    $many = Join-Path $temp 'many.zip'
    $manyNames = @(1..4097 | ForEach-Object { ('entry-{0:d4}.txt' -f $_) })
    Make-Zip $many $manyNames
    $manyTarget = Join-Path $temp 'many'
    $manyRejected = $false
    try { [CustomerSetup]::ExtractPayload($many, $manyTarget) } catch { $manyRejected = $true }
    if (-not $manyRejected -or (Test-Path -LiteralPath (Join-Path $manyTarget 'entry-0001.txt'))) {
        throw 'Excessive archive entries were not refused before extraction.'
    }
    $footer = Join-Path $temp 'footer.bin'
    $bytes = New-Object byte[] 148
    [Array]::Copy([Text.Encoding]::ASCII.GetBytes('THSETUP1'), 0, $bytes, 100, 8)
    [IO.File]::WriteAllBytes($footer, $bytes)
    $stream = [IO.File]::OpenRead($footer)
    try { if ([CustomerSetup]::FindFooter($stream) -ne 100) { throw 'Unsigned payload footer was not found.' } }
    finally { $stream.Dispose() }
    # A PE32+ certificate table follows a padded payload after Authenticode signing.
    $bytes = New-Object byte[] 1112
    [Array]::Copy([BitConverter]::GetBytes([int]128), 0, $bytes, 60, 4)
    [Array]::Copy([BitConverter]::GetBytes([uint32]0x4550), 0, $bytes, 128, 4)
    [Array]::Copy([BitConverter]::GetBytes([uint16]0x20b), 0, $bytes, 152, 2)
    [Array]::Copy([BitConverter]::GetBytes([uint32]1048), 0, $bytes, 296, 4)
    [Array]::Copy([BitConverter]::GetBytes([uint32]64), 0, $bytes, 300, 4)
    [Array]::Copy([Text.Encoding]::ASCII.GetBytes('THSETUP1'), 0, $bytes, 997, 8)
    [IO.File]::WriteAllBytes($footer, $bytes)
    $stream = [IO.File]::OpenRead($footer)
    try { if ([CustomerSetup]::FindFooter($stream) -ne 997) { throw 'Signed payload footer was not found.' } }
    finally { $stream.Dispose() }
    Write-Output 'Real Windows setup code compiled; deep-profile publication, safe extraction, download-marker preservation, ZIP traversal refusal, duplicate refusal, prevalidation and unsigned/signed footer layout passed.'
} finally {
    # The loaded test DLL can stay locked until this process exits; clean what can be removed.
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
