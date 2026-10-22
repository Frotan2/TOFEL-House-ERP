param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Install", "Start", "Repair", "Stop", "Check")]
    [string]$Action
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
    if ($LASTEXITCODE -eq 0) { exit 0 }
    exit 1
} catch {
    [Console]::Error.WriteLine("The operation failed; see product service status.")
    exit 1
}
