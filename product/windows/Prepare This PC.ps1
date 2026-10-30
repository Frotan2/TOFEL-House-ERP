# Offline prerequisite installation. Run elevated by the graphical worker only.
# No URLs, package managers, distro downloads, resets or ERP data mutations.
param()
$ErrorActionPreference = 'Stop'
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
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'The provider did not include the offline Windows prerequisites. Request the complete installer.'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema_version -ne 1) { throw 'Unsupported prerequisites manifest.' }
    $paths = @{}
    # Fixed filenames and publishers: the manifest supplies hashes, never commands.
    foreach ($entry in @(
        @{ key = 'wsl'; file = 'wsl-x64.msi'; publisher = 'Microsoft Corporation' },
        @{ key = 'docker'; file = 'Docker Desktop Installer.exe'; publisher = 'Docker Inc\.?' }
    )) {
        $path = Join-Path $root $entry.file
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked prerequisite rejected.' }
        $hash = [string]$manifest.($entry.key).sha256
        if ($hash -notmatch '^[0-9a-fA-F]{64}$' -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $hash) {
            throw 'Offline prerequisite integrity verification failed.'
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        $publisher = '(?:^|,\s*)O=' + $entry.publisher + '(?:,|$)'
        if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
            $signature.SignerCertificate.Subject -notmatch $publisher) {
            throw 'Offline prerequisite publisher verification failed.'
        }
        $paths[$entry.key] = $path
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
    $wslVersion = @(& wsl.exe --version 2>$null)
    $wslOK = $LASTEXITCODE -eq 0 -and ($wslVersion -join '') -match '(\d+\.\d+\.\d+)'
    if (-not $wslOK -or [version]$Matches[1] -lt [version]'2.1.5') {
        $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList @(
            '/i', ('"' + $paths.wsl + '"'), '/qn', '/norestart'
        ) -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) { throw 'Bundled WSL installation failed.' }
        $restart = $restart -or $process.ExitCode -eq 3010
    }
    $desktopPaths = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    )
    if (-not ($desktopPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })) {
        # Keep Docker's own license/setup UI; never silently accept its agreement.
        $process = Start-Process -FilePath $paths.docker -ArgumentList @('install', '--backend=wsl-2') -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) { throw 'Bundled Docker Desktop installation failed.' }
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
