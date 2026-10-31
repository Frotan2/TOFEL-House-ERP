# Synthetic Windows-only online installer test: no database, Docker or real site.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '../../tools/release/windows/OnlineSetup.cs'
$csc = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$fixture = Join-Path $PSScriptRoot 'online_installer_http_fixture.py'
$work = Join-Path $env:RUNNER_TEMP ('online-test-' + [Guid]::NewGuid().ToString('N'))
$server = $null
try {
    [IO.Directory]::CreateDirectory($work) | Out-Null
    $data = New-Object byte[] 262144
    (New-Object Random 12345).NextBytes($data)
    $payload = Join-Path $work 'payload.bin'
    [IO.File]::WriteAllBytes($payload, $data)
    $portFile = Join-Path $work 'port.txt'
    $logFile = Join-Path $work 'requests.log'
    $args = @('"' + $fixture + '"', '"' + $payload + '"', '"' + $portFile + '"', '"' + $logFile + '"')
    $python = (Get-Command python -ErrorAction Stop).Source
    $server = Start-Process -FilePath $python -ArgumentList $args -PassThru -WindowStyle Hidden
    for ($n=0; $n -lt 40 -and -not (Test-Path $portFile); $n++) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path $portFile)) { throw 'Local HTTP fixture failed.' }
    $url = 'http://127.0.0.1:' + [IO.File]::ReadAllText($portFile).Trim() + '/setup'
    $hash = (Get-FileHash $payload -Algorithm SHA256).Hash.ToLowerInvariant()
    function Build([string]$name, [string]$sha) {
        $plan = Join-Path $work ($name + '.txt')
        [IO.File]::WriteAllText($plan, ((@('TH_ONLINE_PLAN_V1', $url, $sha,
            [string]$data.Length, ('A' * 40)) -join [Environment]::NewLine) +
            [Environment]::NewLine), (New-Object Text.UTF8Encoding($false)))
        $exe = Join-Path $work ($name + '.exe')
        & $csc /nologo /target:exe /platform:x64 /define:TEST_BUILD ("/out:" + $exe) /reference:System.Windows.Forms.dll /reference:System.Drawing.dll ('/resource:' + $plan + ',TOEFLHouse.OnlinePlan') $source
        if ($LASTEXITCODE -ne 0) { throw 'Online C# compilation failed.' }
        return $exe
    }
    function Probe([string]$exe, [string]$dest, [bool]$success) {
        $prior = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $output = @(& $exe --probe-download $dest 2>&1)
            $exit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $prior }
        if (($exit -eq 0) -ne $success) {
            throw ('Unexpected online probe exit ' + $exit + ': ' + ($output -join ' '))
        }
    }
    $exe = Build 'valid' $hash
    $destRoot = Join-Path $work 'good'
    Probe $exe $destRoot $true
    $dest = Join-Path $destRoot ('Downloads/TOEFL-House-ERP-Setup-' + $hash.Substring(0,16) + '.exe')
    if ((Get-FileHash $dest).Hash.ToLowerInvariant() -ne $hash) { throw 'Bad initial download.' }
    $oldCount = @([IO.File]::ReadAllLines($logFile)).Count
    Probe $exe $destRoot $true
    if (@([IO.File]::ReadAllLines($logFile)).Count -ne $oldCount) { throw 'Cache missed.' }
    Remove-Item $dest -Force
    $prefix = New-Object byte[] 65536
    [Array]::Copy($data, 0, $prefix, 0, $prefix.Length)
    [IO.File]::WriteAllBytes(($dest + '.part'), $prefix)
    Probe $exe $destRoot $true
    if ((Get-FileHash $dest).Hash.ToLowerInvariant() -ne $hash -or
        -not (@([IO.File]::ReadAllLines($logFile)) -contains 'bytes=65536-')) {
        throw 'HTTP Range resume failed.'
    }
    $badHash = 'b' * 64
    if ($badHash -eq $hash) { $badHash = 'c' * 64 }
    $bad = Build 'bad' $badHash
    $badRoot = Join-Path $work 'bad'
    Probe $bad $badRoot $false
    $forbidden = Join-Path $badRoot ('Downloads/TOEFL-House-ERP-Setup-' + $badHash.Substring(0,16) + '.exe')
    if (Test-Path $forbidden) { throw 'Tampered download was published.' }
    $builder = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '../../tools/release/Build Online Installer.ps1'))
    if ($builder.Contains('/define:TEST_BUILD') -or -not $builder.Contains('Set-AuthenticodeSignature')) {
        throw 'Provider signing boundary absent.'
    }
    Write-Host 'Smart online setup: download, cache, range resume, SHA refusal PASS.'
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
}
