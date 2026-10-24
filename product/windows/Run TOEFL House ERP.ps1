param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Install", "Start", "Repair", "Stop", "Check", "UpdateCheck", "UpdateInstall")]
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
