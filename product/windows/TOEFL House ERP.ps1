param([switch]$SmokeTest)
# TOEFL House ERP - Windows graphical launcher.
# A customer uses the root .vbs shortcut; no console, Git or typed commands.
# Supports Windows PowerShell 5.1 and the existing guarded CMD lifecycle.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$productRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$worker = Join-Path $PSScriptRoot "Run TOEFL House ERP.ps1"
$credentialFile = Join-Path $productRoot "data\sites\toeflhouse.localhost\private\first-run-credentials.txt"
$logDirectory = Join-Path $env:LOCALAPPDATA "TOEFL House ERP\Launcher"
$desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
$dockerCli = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$powershellExe = Join-Path $PSHOME "powershell.exe"
$script:process = $null
$script:activeAction = ""
$script:stdoutPath = ""
$script:stderrPath = ""

$form = New-Object System.Windows.Forms.Form
$form.Text = "TOEFL House ERP"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(720, 428)
$form.MinimumSize = New-Object System.Drawing.Size(736, 467)
$form.MaximizeBox = $false
$form.FormBorderStyle = "FixedDialog"
$form.BackColor = [System.Drawing.Color]::FromArgb(247, 249, 252)

$heading = New-Object System.Windows.Forms.Label
$heading.Text = "TOEFL House ERP"
$heading.Font = New-Object System.Drawing.Font("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
$heading.ForeColor = [System.Drawing.Color]::FromArgb(24, 45, 76)
$heading.Location = New-Object System.Drawing.Point(28, 22)
$heading.Size = New-Object System.Drawing.Size(630, 44)
$form.Controls.Add($heading)

$subheading = New-Object System.Windows.Forms.Label
$subheading.Text = "Install and manage your course system without a command window."
$subheading.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$subheading.Location = New-Object System.Drawing.Point(30, 73)
$subheading.Size = New-Object System.Drawing.Size(655, 25)
$form.Controls.Add($subheading)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Choose Install on a new computer, or Open on an existing installation."
$status.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$status.Location = New-Object System.Drawing.Point(30, 122)
$status.Size = New-Object System.Drawing.Size(655, 60)
$status.AutoEllipsis = $true
$form.Controls.Add($status)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(30, 190)
$progress.Size = New-Object System.Drawing.Size(656, 15)
$progress.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
$form.Controls.Add($progress)

function New-LauncherButton([string]$title, [int]$left, [int]$top, [int]$width) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $title
    $button.Location = New-Object System.Drawing.Point($left, $top)
    $button.Size = New-Object System.Drawing.Size($width, 39)
    $button.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $button.FlatStyle = "System"
    $form.Controls.Add($button)
    return $button
}

$install = New-LauncherButton "Install" 30 229 145
$open = New-LauncherButton "Open / Start" 185 229 145
$repair = New-LauncherButton "Repair" 340 229 145
$stop = New-LauncherButton "Stop" 495 229 145
$dockerButton = New-LauncherButton "Get Docker Desktop" 30 285 205
$credentials = New-LauncherButton "View Administrator Login" 248 285 222
$logButton = New-LauncherButton "View Details" 485 285 155

$disclaimer = New-Object System.Windows.Forms.Label
$disclaimer.Text = "Docker Desktop must be installed once. Real business use requires owner configuration and release approval."
$disclaimer.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$disclaimer.ForeColor = [System.Drawing.Color]::FromArgb(96, 105, 119)
$disclaimer.Location = New-Object System.Drawing.Point(30, 344)
$disclaimer.Size = New-Object System.Drawing.Size(655, 47)
$form.Controls.Add($disclaimer)

function Set-Busy([bool]$busy) {
    foreach ($button in @($install, $open, $repair, $stop, $dockerButton)) {
        $button.Enabled = -not $busy
    }
    $credentials.Enabled = (-not $busy) -and (Test-Path -LiteralPath $credentialFile -PathType Leaf)
    $logButton.Enabled = ((-not $busy) -and [bool]$script:stdoutPath -and (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf))
    if ($busy) {
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
    } else {
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
    }
}

function Test-DockerClient {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return $true }
    if (Test-Path -LiteralPath $dockerCli -PathType Leaf) {
        $env:PATH = (Split-Path -Parent $dockerCli) + ";" + $env:PATH
        return $true
    }
    return $false
}

function Start-LauncherAction([string]$action) {
    if ($null -ne $script:process) { return }
    if (-not (Test-DockerClient)) {
        $status.Text = "Docker Desktop is not installed. Click 'Get Docker Desktop', finish its Windows installer, then return here."
        return
    }
    if ($action -eq "Install" -and -not (Test-Path -LiteralPath (Join-Path $productRoot "release\toefl-house-erp-app.tar"))) {
        # A provider package has no Docker build context. A missing image must
        # stop with a clear message instead of triggering a doomed source build.
        if (-not (Test-Path -LiteralPath (Join-Path $productRoot "app.Dockerfile") -PathType Leaf)) {
            $status.Text = "This customer package is incomplete. Ask your provider for a complete TOEFL House ERP installer."
            [System.Windows.Forms.MessageBox]::Show(
                "The prebuilt application image is missing. No installation was started, and your existing ERP data was not changed. Request a complete package from your provider.",
                "Incomplete customer package", [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
            return
        }
        $answer = [System.Windows.Forms.MessageBox]::Show(
            "This is a developer source checkout, not a customer package. Building from source can take a long time and needs an internet connection. Continue?",
            "Developer source installation", [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question)
        if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    }
    try {
        [System.IO.Directory]::CreateDirectory($logDirectory) | Out-Null
        $runId = [guid]::NewGuid().ToString("N")
        $script:stdoutPath = Join-Path $logDirectory "$runId.out.txt"
        $script:stderrPath = Join-Path $logDirectory "$runId.err.txt"
        $script:activeAction = $action
        $args = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                  "-WindowStyle", "Hidden", "-File", ('"' + $worker + '"'),
                  "-Action", $action)
        $launch = @{
            FilePath = $powershellExe
            ArgumentList = $args
            WorkingDirectory = $productRoot
            WindowStyle = "Hidden"
            PassThru = $true
            RedirectStandardOutput = $script:stdoutPath
            RedirectStandardError = $script:stderrPath
        }
        $script:process = Start-Process @launch
        $status.Text = "$action is running. Keep this window open. The first installation can take some time."
        Set-Busy $true
    } catch {
        $script:process = $null
        Set-Busy $false
        $status.Text = "Could not start $action. Verify the package files and Windows permissions."
    }
}

$install.Add_Click({ Start-LauncherAction "Install" })
$open.Add_Click({ Start-LauncherAction "Start" })
$repair.Add_Click({ Start-LauncherAction "Repair" })
$stop.Add_Click({ Start-LauncherAction "Stop" })
$dockerButton.Add_Click({
    [System.Diagnostics.Process]::Start("https://www.docker.com/products/docker-desktop/") | Out-Null
    $status.Text = "Install Docker Desktop for Windows, complete WSL 2 setup if prompted, and restart Windows if required. Reopen this app."
})
$credentials.Add_Click({
    if (Test-Path -LiteralPath $credentialFile -PathType Leaf) {
        Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $credentialFile + '"')
    }
})
$logButton.Add_Click({
    [System.Windows.Forms.MessageBox]::Show(
        "The diagnostics folder contains operation details that may be private. Share files only with trusted TOEFL House support.",
        "Private diagnostics", [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    # Docker, PowerShell and Compose can report failure only on stderr. Show
    # both output files rather than hiding the actual failure from support.
    if (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf) {
        Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $script:stdoutPath + '"')
    }
    if (Test-Path -LiteralPath $script:stderrPath -PathType Leaf) {
        $errorLog = Get-Item -LiteralPath $script:stderrPath
        if ($errorLog.Length -gt 0) {
            Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $script:stderrPath + '"')
        }
    }
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1200
$timer.Add_Tick({
    if ($null -eq $script:process) { return }
    try {
        if (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf) {
            $stages = @(Get-Content -LiteralPath $script:stdoutPath -Tail 100 -ErrorAction SilentlyContinue |
                Where-Object { $_ -match '^\[TH_STAGE\]\s+(.+)$' })
            if ($stages.Count -gt 0) {
                $status.Text = ($stages[-1] -replace '^\[TH_STAGE\]\s+', "")
            }
        }
        $script:process.Refresh()
        if (-not $script:process.HasExited) { return }
        $exitCode = $script:process.ExitCode
        $completedAction = $script:activeAction
        $script:process.Dispose()
        $script:process = $null
        Set-Busy $false
        if ($exitCode -eq 0) {
            if ($completedAction -eq "Stop") {
                $status.Text = "TOEFL House ERP has stopped safely. Your data remains stored."
            } else {
                $status.Text = "TOEFL House ERP is ready. Opening in your browser."
                [System.Diagnostics.Process]::Start("http://127.0.0.1:8000/") | Out-Null
            }
        } else {
            $status.Text = "$completedAction could not finish safely. Nothing has been reset. Select View Details, or contact your support provider."
        }
    } catch {
        $status.Text = "The launcher could not read the operation status. Check View Details."
    }
})
$form.Add_FormClosing({
    param($sender, $eventArgs)
    if ($null -ne $script:process) {
        $script:process.Refresh()
        if (-not $script:process.HasExited) {
            $eventArgs.Cancel = $true
            [System.Windows.Forms.MessageBox]::Show(
                "Setup is still running. Keep this window open until it finishes.",
                "TOEFL House ERP", [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
        }
    }
})
if ($SmokeTest) {
    if ($install.Text -ne "Install" -or $open.Text -ne "Open / Start" -or
        $repair.Text -ne "Repair" -or $stop.Text -ne "Stop") {
        throw "Graphical lifecycle actions were not initialized."
    }
    Write-Host "Windows GUI controls initialized without displaying a desktop window."
    exit 0
}
Set-Busy $false
$timer.Start()
[void]$form.ShowDialog()
$timer.Stop()
