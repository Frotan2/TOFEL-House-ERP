# Publisher-verified prerequisites. Run elevated by the graphical worker.
# The internal package downloads only pinned vendor assets and never modifies ERP data.
param([switch]$Preflight)
$ErrorActionPreference = 'Stop'
$downloadFolder = $null

if ($Preflight) {
    try {
        if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
            throw 'ERP Setup requires x64 Windows.'
        }
        $windows = Get-CimInstance Win32_OperatingSystem
        $build = [int]$windows.BuildNumber
        if ($windows.ProductType -ne 1 -or $build -lt 19045 -or ($build -ge 22000 -and $build -lt 22631)) {
            throw 'This Windows edition or build is below the Docker Desktop baseline.'
        }
        $hardware = Get-CimInstance Win32_ComputerSystem
        if ($hardware.TotalPhysicalMemory -lt 8GB -and $windows.TotalVisibleMemorySize -lt (7GB / 1KB)) {
            throw 'The computer needs at least 8 GB of installed RAM.'
        }
        $virtualization = $hardware.HypervisorPresent -or @(
            Get-CimInstance Win32_Processor | Where-Object VirtualizationFirmwareEnabled
        ).Count -gt 0
        if (-not $virtualization) {
            throw 'Hardware virtualization could not be verified. Check firmware and WSL 2 prerequisites.'
        }
        $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($PSScriptRoot))
        if (-not $drive.IsReady -or $drive.AvailableFreeSpace -lt 20GB) {
            throw 'Keep at least 20 GiB free on the Windows install drive after package extraction.'
        }
        Write-Output '[TH_STAGE] Windows hardware and install drive checks passed.'
        exit 0
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}

function Get-VerifiedPrerequisite($Entry, [string]$Path, [string]$ExpectedHash) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Linked or non-file prerequisite rejected.'
    }
    if ($ExpectedHash -notmatch '^[0-9a-fA-F]{64}$' -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ine $ExpectedHash) {
        throw 'Prerequisite integrity verification failed.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    $publisher = '(?:^|,\s*)O=' + $Entry.publisher + '(?:,|$)'
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch $publisher) {
        throw 'Prerequisite publisher verification failed.'
    }
    return $item.FullName
}

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Windows administrator approval is required.'
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'This package requires Windows x64.'
    }
    $root = Join-Path $PSScriptRoot '..\prerequisites'
    $manifestPath = Join-Path $root 'manifest.json'
    $entries = @(
        @{ key = 'wsl'; file = 'wsl-x64.msi'; publisher = 'Microsoft Corporation'; host = 'github.com' },
        @{ key = 'docker'; file = 'Docker Desktop Installer.exe'; publisher = 'Docker Inc\.?'; host = 'desktop.docker.com' }
    )
    $desktopPaths = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    )
    $wslCommand = Get-Command wsl.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $wslOK = $false
    if ($wslCommand) {
        $wslVersion = @(& $wslCommand.Source --version 2>$null)
        $wslOK = $LASTEXITCODE -eq 0 -and $wslVersion.Count -and
            (($wslVersion[0] -replace '\x00', '') -match '\b(\d+\.\d+\.\d+(?:\.\d+)?)\b')
        if ($wslOK) { $wslOK = [version]$Matches[1] -ge [version]'2.1.5' }
    }
    $needs = @{
        wsl = -not $wslOK
        docker = -not ($desktopPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    }
    $offline = Test-Path -LiteralPath $manifestPath -PathType Leaf
    if ($offline) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } else {
        $catalogPath = Join-Path $root 'vendor-downloads.json'
        if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
            throw 'The installer is missing the signed prerequisites or its verified vendor catalog.'
        }
        $manifest = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json
    }
    if ($manifest.schema_version -ne 1) { throw 'Unsupported prerequisites manifest.' }
    $paths = @{}
    foreach ($entry in $entries) {
        if (-not $needs[$entry.key]) { continue }
        $package = $manifest.($entry.key)
        $path = Join-Path $root $entry.file
        if (-not $offline) {
            if ($package.filename -cne $entry.file -or $package.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
                throw 'The vendor download catalog does not match the expected prerequisite.'
            }
            $uri = [Uri]$package.url
            if (-not $uri.IsAbsoluteUri -or $uri.Scheme -cne 'https' -or
                $uri.Host -cne $entry.host -or -not $uri.IsDefaultPort -or $uri.UserInfo -or
                ($entry.key -eq 'wsl' -and $uri.AbsolutePath -notlike '/microsoft/WSL/releases/download/*') -or
                ($entry.key -eq 'docker' -and $uri.AbsolutePath -notlike '/win/main/amd64/*')) {
                throw 'Unexpected prerequisite vendor URL.'
            }
            if (-not $downloadFolder) {
                $downloadFolder = Join-Path ([IO.Path]::GetTempPath()) ('toefl-vendor-' + [guid]::NewGuid().ToString('N'))
                [void][IO.Directory]::CreateDirectory($downloadFolder)
            }
            $path = Join-Path $downloadFolder $entry.file
            $download = Invoke-WebRequest -Uri $uri -UseBasicParsing -OutFile $path -PassThru -TimeoutSec 1800
            if ($download.BaseResponse.ResponseUri.Scheme -cne 'https') { throw 'Vendor download requires HTTPS.' }
        }
        $paths[$entry.key] = Get-VerifiedPrerequisite $entry $path ([string]$package.sha256)
    }
    $restart = $false
    foreach ($name in @('VirtualMachinePlatform', 'Microsoft-Windows-Subsystem-Linux')) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $name
        if ($feature.State -eq 'EnablePending' -or $feature.State -eq 'DisablePending') {
            $restart = $true
        } elseif ($feature.State -ne 'Enabled') {
            # Refuse missing Windows source rather than silently downloading it.
            $result = Enable-WindowsOptionalFeature -Online -FeatureName $name -All -LimitAccess -NoRestart
            $restart = $restart -or $result.RestartNeeded
        }
    }
    if ($needs.wsl) {
        $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList @(
            '/i', ('"' + $paths.wsl + '"'), '/qn', '/norestart'
        ) -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) { throw 'Microsoft WSL installation failed.' }
        $restart = $restart -or $process.ExitCode -eq 3010
    }
    if ($needs.docker) {
        # Keep Docker's own license/setup UI; never silently accept its agreement.
        $process = Start-Process -FilePath $paths.docker -ArgumentList @('install', '--backend=wsl-2') -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) { throw 'Docker Desktop installation failed.' }
        $restart = $restart -or $process.ExitCode -eq 3010
    }
    if ($restart) { exit 3010 }
    exit 0
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        $_.Exception.Message, 'TOEFL House ERP - computer setup',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
finally {
    if ($downloadFolder) {
        foreach ($entry in $entries) {
            $file = Join-Path $downloadFolder $entry.file
            if (Test-Path -LiteralPath $file -PathType Leaf) { [IO.File]::Delete($file) }
        }
        [IO.Directory]::Delete($downloadFolder)
    }
}
