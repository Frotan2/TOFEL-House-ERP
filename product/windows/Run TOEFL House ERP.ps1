param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Install", "Start", "Repair", "Stop", "Check", "UpdateCheck", "UpdateInstall", "Prepare", "Backup", "VerifyBackup")]
    [string]$Action,
    [ValidatePattern("^[A-Za-z]:$")][string]$BackupDrive
)
$ErrorActionPreference = "Stop"
$scriptNames = @{
    Install = "Install TOEFL House ERP.cmd"
    Start = "Start TOEFL House ERP.cmd"
    Repair = "Repair TOEFL House ERP.cmd"
    Stop = "Stop TOEFL House ERP.cmd"
}
if ($Action -eq "Check") {
    # This self-check is intentionally independent of Docker availability and
    # never invokes any lifecycle, backup, restore or activation command.
    $checkPath = Join-Path $PSScriptRoot "Check This PC.ps1"
    if (-not (Test-Path -LiteralPath $checkPath -PathType Leaf)) {
        [Console]::Error.WriteLine("The read-only computer check is missing.")
        exit 1
    }
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $checkPath
    if ($LASTEXITCODE -eq 0) { exit 0 }
    exit 1
}
if ($Action -eq "UpdateCheck" -or $Action -eq "UpdateInstall") {
    # Updates are their own workflow. This branch never installs a new site,
    # repairs, stops or starts anything by itself; the signed update script and
    # its engine make every decision and report a documented exit code.
    $updatePath = Join-Path $PSScriptRoot "Update TOEFL House ERP.ps1"
    if (-not (Test-Path -LiteralPath $updatePath -PathType Leaf)) {
        [Console]::Error.WriteLine("The verified update workflow is missing from this package.")
        exit 1
    }
    # Run in this process instead of re-quoting a path that contains spaces
    # into a child command line. The update script always ends with its own
    # documented exit code, which becomes this process's exit code.
    try {
        if ($Action -eq "UpdateCheck") {
            & $updatePath -Action Check
        } else {
            & $updatePath -Action Install -ConfirmationAccepted
        }
    } catch {
        [Console]::Error.WriteLine("The update workflow stopped safely: " + $_.Exception.Message)
        exit 5
    }
    # The update script exits on every path; this line only runs if it ever
    # returns normally without a decision.
    exit 5
}
# Discover both supported Docker Desktop installation layouts in every new worker.
foreach ($bin in @("$env:ProgramFiles\Docker\Docker\resources\bin",
                   "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin")) {
    if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe')) { $env:PATH = $bin + ';' + $env:PATH }
}
if ($Action -in @('Backup', 'VerifyBackup')) {
    $backupPath = Join-Path $PSScriptRoot 'Backup TOEFL House ERP.ps1'
    $backupArgs = @()
    if ($Action -eq 'VerifyBackup') { $backupArgs += '-VerifyExisting' }
    if ($Action -eq 'Backup' -and $BackupDrive) { $backupArgs += @('-BackupDrive', $BackupDrive) }
    & (Join-Path $PSHOME 'powershell.exe') -NoLogo -NoProfile -NonInteractive -File $backupPath @backupArgs
    exit $LASTEXITCODE
}
if ($Action -eq 'Install') {
    $productRoot = Join-Path $PSScriptRoot '..'
    foreach ($relative in @('data\secrets\db.env', 'data\sites\toeflhouse.localhost\site_config.json', 'data\.installation-claim')) {
        if (Test-Path -LiteralPath (Join-Path $productRoot $relative)) {
            [Console]::Error.WriteLine('Existing or partial ERP installation preserved. Use Open / Start or contact support.')
            exit 1
        }
    }
    # Alternate Frappe site names and partial common_site_config are equally
    # protected. Inspect names only, without reading private files or data.
    $sitesRoot = Join-Path $productRoot 'data\sites'
    if (Test-Path -LiteralPath $sitesRoot) {
        try {
            if (@(Get-ChildItem -LiteralPath $sitesRoot -Force -ErrorAction Stop |
                    Select-Object -First 1).Count -gt 0) {
                [Console]::Error.WriteLine('Previous or partial ERP site files exist. No installation or Windows prerequisites were changed.')
                exit 1
            }
        } catch {
            [Console]::Error.WriteLine('Existing ERP site storage cannot be inventoried. Installation refused.')
            exit 1
        }
    }
}
if ($Action -eq 'Install') {
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Verify Package Image.ps1')
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
if ($Action -eq 'Install' -or $Action -eq 'Prepare') {
    $preparePath = Join-Path $PSScriptRoot 'Prepare This PC.ps1'
    . (Join-Path $PSScriptRoot 'Test Local Docker.ps1')
    try {
        Assert-NoDockerOverrides
        if (Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue) {
            Assert-LocalDockerEngine -AllowStopped
        }
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '..\prerequisites\vendor-downloads.json') -PathType Leaf) {
        & powershell.exe -NoLogo -NoProfile -NonInteractive -File $preparePath -Preflight
        if ($LASTEXITCODE -ne 0) { exit 1 }
    }
    $engineReady = $false
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        & docker info *> $null
        $engineReady = $LASTEXITCODE -eq 0
    }
    # An installed but stopped Docker Desktop is not a missing prerequisite.
    # The Install CMD launcher starts it and waits for a responding engine.
    # Do not request Windows administrator privileges just to open Docker.
    $desktopInstalled = [bool](@(
        @("$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
          "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe") |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    ).Count -gt 0)
    $wslReady = $false
    $wsl = Get-Command wsl.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wsl) {
        $version = @(& $wsl.Source --version 2>$null)
        if ($LASTEXITCODE -eq 0 -and $version.Count -and
            (($version[0] -replace '\x00', '') -match '\b(\d+\.\d+\.\d+(?:\.\d+)?)\b')) {
            $wslReady = [version]$Matches[1] -ge [version]'2.1.5'
        }
    }
    if ($Action -eq 'Install' -and -not $engineReady -and $desktopInstalled -and $wslReady) {
        Write-Output '[TH_STAGE] Docker Desktop is installed; checking its engine without changing Windows prerequisites...'
    } elseif (-not $engineReady) {
        try {
            Write-Output '[TH_STAGE] Preparing Windows with verified Microsoft WSL and Docker Desktop installers...'
            $preparation = Start-Process -FilePath "$PSHOME\powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @(
                '-NoLogo', '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                '-File', ('"' + $preparePath + '"')
            )
            if ($preparation.ExitCode -ne 0) { exit $preparation.ExitCode }
        } catch {
            [Console]::Error.WriteLine('Computer setup cancelled or could not start. No ERP installation was attempted.')
            exit 1
        }
        # A newly installed CLI is not in this process's inherited PATH yet.
        foreach ($bin in @("$env:ProgramFiles\Docker\Docker\resources\bin",
                           "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin")) {
            if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe')) { $env:PATH = $bin + ';' + $env:PATH }
        }
    }
    if ($Action -eq 'Prepare') { exit 0 }
}
$scriptPath = Join-Path $PSScriptRoot $scriptNames[$Action]
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    [Console]::Error.WriteLine("The selected product launcher is missing.")
    exit 1
}
# This is inherited only by the child process. It disables CMD pause and
# printing initial Administrator credentials to redirectable console output.
$env:TH_GUI_MODE = "1"
try {
    & $scriptPath
    if ($LASTEXITCODE -ne 0) { exit 1 }
    if ($Action -eq 'Install') {
        & powershell.exe -NoLogo -NoProfile -NonInteractive -STA -File (Join-Path $PSScriptRoot 'Create ERP Desktop Shortcut.ps1')
        if ($LASTEXITCODE -ne 0) {
            Write-Output '[TH_SHORTCUT] The desktop shortcut needs attention. Open View Details.'
        }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("The operation failed; see product service status.")
    exit 1
}
