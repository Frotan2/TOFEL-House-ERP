param([switch]$SmokeTest, [switch]$AutoInstall)
# TOEFL House ERP - Windows graphical launcher.
# A customer uses the root .vbs shortcut; no console, Git or typed commands.
# Supports Windows PowerShell 5.1 and the existing guarded CMD lifecycle.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$productRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$worker = Join-Path $PSScriptRoot "Run TOEFL House ERP.ps1"
$guiPath = Join-Path $PSScriptRoot "TOEFL House ERP.ps1"
$credentialFile = Join-Path $productRoot "data\sites\toeflhouse.localhost\private\first-run-credentials.txt"
$guideFile = Join-Path $PSScriptRoot "OWNER ACCEPTANCE GUIDE.txt"
$handbookFile = Join-Path $PSScriptRoot "OWNER HANDBOOK.txt"
$dailyGuideFile = Join-Path $PSScriptRoot "DAILY USE GUIDE.txt"
$updaterStrings = Join-Path $PSScriptRoot "updater-strings.json"
$updateResultFile = Join-Path $productRoot "data\updates\last-result.json"
$logDirectory = Join-Path $env:LOCALAPPDATA "TOEFL House ERP\Launcher"
$desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
$dockerCli = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
$powershellExe = Join-Path $PSHOME "powershell.exe"
$script:process = $null
$script:activeAction = ""
$script:stdoutPath = ""
$script:stderrPath = ""
$script:lastCheckPath = ""

$form = New-Object System.Windows.Forms.Form
$form.Text = "TOEFL House ERP"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(720, 612)
$form.MinimumSize = New-Object System.Drawing.Size(736, 651)
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
$dockerButton = New-LauncherButton "Prepare This Computer" 30 285 205
$credentials = New-LauncherButton "View Administrator Login" 248 285 222
$logButton = New-LauncherButton "View Details" 485 285 155
$checkButton = New-LauncherButton "Check This PC" 30 339 165
$guideButton = New-LauncherButton "Owner Readiness Guide" 205 339 235
$dailyGuideButton = New-LauncherButton "How to Use" 450 339 190
$copyStatusButton = New-LauncherButton "Copy Safe Support Status" 30 395 275
$handbookButton = New-LauncherButton "Owner Handbook" 315 395 220
# Updates are deliberately separate from Install and Repair: a customer can
# check for a signed release without any lifecycle action being reachable.
$updateButton = New-LauncherButton "Check for Updates" 30 451 269
$installUpdateButton = New-LauncherButton "Install Update" 309 451 220

$disclaimer = New-Object System.Windows.Forms.Label
$disclaimer.Text = "Windows setup uses the included installers. Real business use requires owner configuration and release approval."
$disclaimer.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$disclaimer.ForeColor = [System.Drawing.Color]::FromArgb(96, 105, 119)
$disclaimer.Location = New-Object System.Drawing.Point(30, 524)
$disclaimer.Size = New-Object System.Drawing.Size(655, 47)
$form.Controls.Add($disclaimer)

# The read-only check can finish writing its complete report before the
# wrapper process has exited. Do not make safe copying depend on ExitCode,
# a second button refresh or a working Docker engine. Every candidate is still
# fully validated against literal allowed fields when the user clicks Copy.
function Get-CompletedCheckPath {
    if ($script:activeAction -ne "Check") { return "" }
    $candidate = if ($script:lastCheckPath) { $script:lastCheckPath } else { $script:stdoutPath }
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { return "" }
    try {
        $firstLines = @(Get-Content -LiteralPath $candidate -TotalCount 2 -ErrorAction Stop)
        $lastLine = @(Get-Content -LiteralPath $candidate -Tail 1 -ErrorAction Stop)
        if ($firstLines -cnotcontains "TOEFL HOUSE ERP - READ-ONLY TECHNICAL CHECK" -or
            $lastLine.Count -ne 1 -or
            $lastLine[0] -cne "End of read-only PC check.") {
            return ""
        }
        return $candidate
    } catch {
        return ""
    }
}

# Update results are rendered only from fixed catalogue text. The result file
# can never inject a free-text message, URL or command into this window.
function Get-UpdaterCatalog {
    if (-not (Test-Path -LiteralPath $updaterStrings -PathType Leaf)) { return $null }
    try {
        $encoding = New-Object System.Text.UTF8Encoding($false, $true)
        $catalog = [System.IO.File]::ReadAllText($updaterStrings, $encoding) | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    if ($null -eq $catalog -or $catalog.schema_version -ne 1 -or
        $catalog.document_type -cne "toefl-house-erp-updater-strings" -or
        $catalog.language -cne "en" -or $catalog.fallback -cne "en") {
        return $null
    }
    return $catalog
}

function Get-UpdaterText([string]$Section, [string]$Key) {
    $catalog = Get-UpdaterCatalog
    if ($null -eq $catalog) { return $null }
    $entries = $catalog.$Section
    if ($null -eq $entries) { return $null }
    $entry = $entries.$Key
    if ($null -eq $entry) { return $null }
    if (-not ($entry.en -is [string]) -or [string]::IsNullOrWhiteSpace($entry.en)) { return $null }
    return $entry
}

function Get-UpdateResult {
    if (-not (Test-Path -LiteralPath $updateResultFile -PathType Leaf)) { return $null }
    try {
        $item = Get-Item -LiteralPath $updateResultFile -Force
        if ($item.Length -gt 65536) { return $null }
        $encoding = New-Object System.Text.UTF8Encoding($false, $true)
        $result = [System.IO.File]::ReadAllText($updateResultFile, $encoding) | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
    if ($null -eq $result -or $result.document_type -cne "toefl-house-erp-updater-result") { return $null }
    $statuses = @("update-available", "up-to-date", "refused", "failed", "completed",
                  "recovery-required", "cancelled", "busy", "not-configured")
    if ($statuses -cnotcontains ([string]$result.status)) { return $null }
    $section = [string]$result.message_section
    if (@("messages", "launcher") -cnotcontains $section) { return $null }
    $entry = Get-UpdaterText $section ([string]$result.message_key)
    if ($null -eq $entry) { return $null }
    $version = ""
    if ([string]$result.version -match '^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$') { $version = [string]$result.version }
    return [pscustomobject]@{ en = $entry.en; version = $version; status = [string]$result.status }
}

function Show-UpdateResult {
    $result = Get-UpdateResult
    if ($null -eq $result) { return "" }
    $body = $result.en
    if ($result.version) {
        $body = $body + [Environment]::NewLine + [Environment]::NewLine + "Version: " + $result.version
    }
    $icon = [System.Windows.Forms.MessageBoxIcon]::Information
    if ($result.status -eq "refused" -or $result.status -eq "failed" -or $result.status -eq "recovery-required") {
        $icon = [System.Windows.Forms.MessageBoxIcon]::Warning
    }
    [System.Windows.Forms.MessageBox]::Show($body, "TOEFL House ERP update",
        [System.Windows.Forms.MessageBoxButtons]::OK, $icon) | Out-Null
    return $result.en
}

function Set-Busy([bool]$busy) {
    foreach ($button in @($install, $open, $repair, $stop, $dockerButton, $checkButton, $guideButton, $handbookButton, $dailyGuideButton, $copyStatusButton, $updateButton, $installUpdateButton)) {
        $button.Enabled = -not $busy
    }
    $credentials.Enabled = (-not $busy) -and (Test-Path -LiteralPath $credentialFile -PathType Leaf)
    $guideButton.Enabled = (-not $busy) -and (Test-Path -LiteralPath $guideFile -PathType Leaf)
    $handbookButton.Enabled = (-not $busy) -and (Test-Path -LiteralPath $handbookFile -PathType Leaf)
    $dailyGuideButton.Enabled = (-not $busy) -and (Test-Path -LiteralPath $dailyGuideFile -PathType Leaf)
    # A finished, read-only status is safe to copy even if the child process
    # is still closing, and even if Docker cannot be reached on this PC.
    $copyStatusButton.Enabled = [bool](Get-CompletedCheckPath)
    $logButton.Enabled = ((-not $busy) -and [bool]$script:stdoutPath -and (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf))
    if ($busy) {
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Marquee
    } else {
        $progress.Style = [System.Windows.Forms.ProgressBarStyle]::Continuous
    }
}

function Test-DockerClient {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return $true }
    foreach ($bin in @("$env:ProgramFiles\Docker\Docker\resources\bin",
                       "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin")) {
        if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe') -PathType Leaf) {
            $env:PATH = $bin + ';' + $env:PATH
            return $true
        }
    }
    return $false
}

function Start-LauncherAction([string]$action) {
    if ($null -ne $script:process) { return }
    # Any attempted lifecycle action invalidates the previous PC check.
    $script:lastCheckPath = ""
    Set-Busy $false
    if ($action -ne "Check" -and $action -ne "Install" -and $action -ne "Prepare" -and -not (Test-DockerClient)) {
        $status.Text = "Select Prepare This Computer to install the included Windows prerequisites."
        return
    }
    if ($action -eq "Install" -and -not (Test-Path -LiteralPath (Join-Path $productRoot "release\toefl-house-erp-app.tar"))) {
        # The customer installer has no source-build path.  Never present
        # a developer checkout as a usable one-click customer installer:
        # even an affirmative prompt cannot manufacture the signed package.
        $status.Text = "This customer package is incomplete. Ask your provider for a complete TOEFL House ERP installer."
        [System.Windows.Forms.MessageBox]::Show(
            "The prebuilt application image is missing. No installation was started, and your existing ERP data was not changed. Request a complete package from your provider.",
            "Incomplete customer package", [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        return
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
        if ($action -eq "UpdateCheck" -or $action -eq "UpdateInstall") {
            # Updates may take several minutes but change nothing until every
            # check passes; the first installation message would be misleading.
            $status.Text = "The update workflow is running. Keep this window open. Your records are only touched after every check passes."
        } else {
            $status.Text = "$action is running. Keep this window open. The first installation can take some time."
        }
        Set-Busy $true
    } catch {
        $script:process = $null
        Set-Busy $false
        $status.Text = "Could not start $action. Verify the package files and Windows permissions."
    }
}

$install.Add_Click({ Start-LauncherAction "Install" })
$open.Add_Click({ Start-LauncherAction "Start" })
$repair.Add_Click({
    # Repair is not a routine daily action. Prevent accidental one-click
    # mutation on a machine with an existing site; default is "No".
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Repair is for a problem with an installation and should be done only with TOEFL House support. It may update application files. It is NOT a backup or data recovery. Do not use it to fix missing student records. Continue with Repair?",
        "Confirm repair with support",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-LauncherAction "Repair"
    } else {
        $status.Text = "Repair cancelled. Your installed data was not changed."
    }
})
$stop.Add_Click({ Start-LauncherAction "Stop" })
$checkButton.Add_Click({ Start-LauncherAction "Check" })
$guideButton.Add_Click({
    # No data mutation or production operation: only open the local text guide.
    if (Test-Path -LiteralPath $guideFile -PathType Leaf) {
        Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $guideFile + '"')
    } else {
        $status.Text = "Owner readiness guide missing; ask your provider for a complete package."
    }
})
$handbookButton.Add_Click({
    # Offline no-code Owner operating guide. Reading it changes no student,
    # payment, account, Docker volume, backup or operational release setting.
    if (Test-Path -LiteralPath $handbookFile -PathType Leaf) {
        Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $handbookFile + '"')
    } else {
        $status.Text = "Owner handbook is missing. Ask your provider for a complete installer."
    }
})
$dailyGuideButton.Add_Click({
    # Offline no-code user help. Reading a guide changes no student, payment,
    # account, Docker volume, backup or operational release setting.
    if (Test-Path -LiteralPath $dailyGuideFile -PathType Leaf) {
        Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $dailyGuideFile + '"')
    } else {
        $status.Text = "Daily use guide is missing. Ask your provider for a complete installer."
    }
})
$copyStatusButton.Add_Click({
    # Read-only checks shared using these fixed states alone.
    # Never copy stdout verbatim; other operations may include private logs.
    $completedCheck = Get-CompletedCheckPath
    if (-not $completedCheck) {
        $status.Text = "A complete read-only PC report is not available yet. Run Check This PC and let the report finish."
        return
    }
    # Whitelist exact status VALUES as well as names. An arbitrary diagnostic
    # or altered local log must never be sent to the owner's clipboard.
    $permitted = [ordered]@{
        "Windows" = @("Not detected", "64-bit detected", "Unsupported 32-bit system")
        "Docker Desktop" = @("Docker CLI not found (prerequisite missing)",
            "Docker engine responding", "Installed, but engine not responding",
            "Cannot verify engine")
        "Existing local site data" = @("Present - must be preserved",
            "No local site-data folder observed")
        "Database credential safety" = @(
            "BLOCKED: existing site/database but credential file missing. Do NOT reinstall, repair, delete or regenerate credentials.",
            "Local credential file present (contents not read; database match NOT VERIFIED)",
            "BLOCKED: credentials exist but site configuration is missing. Do NOT install, start or repair.",
            "NOT VERIFIED: credentials exist but the database volume could not be confirmed. Start Docker Desktop and check again; do NOT reinstall.",
            "No credential file; local site or database storage could not be ruled out. Do NOT assume a fresh installation.",
            "No credential file or existing site/database observed (informational, not permission to install)")
        "Local browser endpoint" = @("Responding; authenticated login not verified",
            "Not verified", "Not responding or not yet installed")
        "Owner backup/restore" = @("HOLD - not tested by this check")
        "Actual Tailscale staff access" = @("NOT VERIFIED")
        "Production authorization" = @("NOT VERIFIED")
    }
    try {
        $lines = @(Get-Content -LiteralPath $completedCheck -ErrorAction Stop)
        if ($lines -cnotcontains "TOEFL HOUSE ERP - READ-ONLY TECHNICAL CHECK" -or
            $lines -cnotcontains "End of read-only PC check.") {
            throw "Not a complete read-only check"
        }
        $seen = @{}
        foreach ($line in $lines) {
            foreach ($key in $permitted.Keys) {
                $prefix = $key + ": "
                if (-not $line.StartsWith($prefix, [System.StringComparison]::Ordinal)) { continue }
                $value = $line.Substring($prefix.Length)
                if ($permitted[$key] -cnotcontains $value -or $seen.ContainsKey($key)) {
                    throw ("Invalid or repeated category: " + $key)
                }
                $seen[$key] = $value
                break
            }
        }
        if ($seen.Count -ne $permitted.Count) { throw "Incomplete machine status" }
        $safe = @("TOEFL House ERP - Safe Support Status",
                  "Read-only observation. NOT approval to use real student or financial data.")
        foreach ($key in $permitted.Keys) { $safe += ($key + ": " + $seen[$key]) }
        [System.Windows.Forms.Clipboard]::SetText(($safe -join [Environment]::NewLine))
        $status.Text = "Safe status copied. Paste it to trusted support; no passwords or raw logs."
    } catch {
        $status.Text = "Cannot verify a safe summary. Run Check This PC again."
    }
})
$updateButton.Add_Click({ Start-LauncherAction "UpdateCheck" })
$installUpdateButton.Add_Click({
    # Explicit Owner authorization before any mutating step. The update script
    # still refuses unless the signed release, verified backup, recovery
    # authorization and every host precondition pass.
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Installing an update changes the application and may upgrade the database. It runs only when the provider's signed release and every safety check pass, including a verified backup. Continue?",
        "Confirm update",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($answer -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-LauncherAction "UpdateInstall"
    } else {
        $status.Text = "Update cancelled. Your system was not changed."
    }
})
$dockerButton.Add_Click({
    Start-LauncherAction "Prepare"
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
            # Display the latest English stage from the controlled worker.
            $tail = @(Get-Content -LiteralPath $script:stdoutPath -Tail 100 -ErrorAction SilentlyContinue)
            $stages = @($tail | Where-Object { $_ -match '^\[TH_STAGE\]\s+(.+)
        }
        # Refresh the Copy button from the complete report itself, not only
        # from process-exit timing. The copy handler enforces field allowlists.
        if ($script:activeAction -eq "Check") {
            $copyStatusButton.Enabled = [bool](Get-CompletedCheckPath)
        }
        $script:process.Refresh()
        if (-not $script:process.HasExited) { return }
        $exitCode = $script:process.ExitCode
        $completedAction = $script:activeAction
        $script:process.Dispose()
        $script:process = $null
        Set-Busy $false
        if ($exitCode -eq 3010) {
            $status.Text = "Windows setup needs a restart. Save your work, restart Windows, then reopen TOEFL House ERP and click Install."
            [System.Windows.Forms.MessageBox]::Show($status.Text, "Restart required") | Out-Null
        } elseif ($exitCode -eq 0) {
            if ($completedAction -eq "Prepare") {
                $status.Text = "Windows prerequisites are prepared. Select Install to continue."
            } elseif ($completedAction -eq "Stop") {
                $status.Text = "TOEFL House ERP has stopped safely. Your data remains stored."
            } elseif ($completedAction -eq "Check") {
                $script:lastCheckPath = $script:stdoutPath
                Set-Busy $false
                $status.Text = "Read-only PC check completed. This is not release approval. See View Details."
                if (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf) {
                    Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $script:stdoutPath + '"')
                }
            } elseif ($completedAction -eq "UpdateCheck" -or $completedAction -eq "UpdateInstall") {
                $summary = Show-UpdateResult
                if (-not $summary) {
                    $summary = "The update action finished. Select View Details for the recorded result."
                }
                $status.Text = $summary
                if ($completedAction -eq "UpdateInstall") {
                    [System.Diagnostics.Process]::Start("http://127.0.0.1:8000/") | Out-Null
                }
            } else {
                if ($completedAction -eq "Install") {
                    try {
                        $shell = New-Object -ComObject WScript.Shell
                        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'TOEFL House ERP.lnk'))
                        $shortcut.TargetPath = $powershellExe
                        $shortcut.Arguments = '-NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $guiPath + '" -AutoInstall'
                        $shortcut.WorkingDirectory = $productRoot
                        $shortcut.Save()
                    } catch { # A restricted Desktop does not invalidate a successful installation.
                    }
                }
                $status.Text = "TOEFL House ERP is ready. Opening in your browser."
                [System.Diagnostics.Process]::Start("http://127.0.0.1:8000/") | Out-Null
            }
        } else {
            if ($completedAction -eq "UpdateCheck" -or $completedAction -eq "UpdateInstall") {
                $summary = Show-UpdateResult
                if ($summary) { $status.Text = $summary } else { $status.Text = "The update stopped safely. Select View Details, or contact your support provider." }
            } else {
                $status.Text = "$completedAction could not finish safely. Nothing has been reset. Select View Details, or contact your support provider."
            }
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
        $repair.Text -ne "Repair" -or $stop.Text -ne "Stop" -or
        $checkButton.Text -ne "Check This PC" -or
        $updateButton.Text -ne "Check for Updates" -or
        $installUpdateButton.Text -ne "Install Update" -or
        $guideButton.Text -ne "Owner Readiness Guide" -or
        $handbookButton.Text -ne "Owner Handbook" -or
        $dailyGuideButton.Text -ne "How to Use" -or
        $copyStatusButton.Text -ne "Copy Safe Support Status" -or
        -not (Test-Path -LiteralPath $guideFile -PathType Leaf) -or
        -not (Test-Path -LiteralPath $handbookFile -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dailyGuideFile -PathType Leaf)) {
        throw "Graphical lifecycle actions were not initialized."
    }
    # Simulate the exact Owner case: check writes a full report while the
    # wrapper still exists, then the GUI must allow safe copying. No real
    # clipboard access, Docker use, site change or credentials in this test.
    $syntheticCheck = [System.IO.Path]::GetTempFileName()
    try {
        $script:activeAction = "Check"
        $script:stdoutPath = $syntheticCheck
        $script:lastCheckPath = ""
        Set-Content -LiteralPath $syntheticCheck -Value @(
            "[TH_STAGE] Read-only PC check is running...",
            "TOEFL HOUSE ERP - READ-ONLY TECHNICAL CHECK",
            "Windows: 64-bit detected") -Encoding UTF8
        Set-Busy $true
        if ($copyStatusButton.Enabled) { throw "Copy activated before PC check completed." }
        Add-Content -LiteralPath $syntheticCheck -Value "End of read-only PC check."
        Set-Busy $true
        if (-not $copyStatusButton.Enabled) { throw "Complete read-only PC check cannot be copied while wrapper is closing." }
        Set-Busy $false
        if (-not $copyStatusButton.Enabled) { throw "Copy disabled after completed PC check." }
        $script:activeAction = "Start"
        $script:lastCheckPath = ""
        Set-Busy $false
        if ($copyStatusButton.Enabled) { throw "Previous PC check leaked into a different lifecycle action." }
    } finally {
        Remove-Item -LiteralPath $syntheticCheck -ErrorAction SilentlyContinue
    }
    Write-Host "Windows GUI controls initialized; completed-report copy availability verified."
    exit 0
}
Set-Busy $false
if ($AutoInstall) {
    $form.Add_Shown({
        if (Test-Path -LiteralPath (Join-Path $productRoot 'data\secrets\db.env')) {
            Start-LauncherAction "Start"
        } else { Start-LauncherAction "Install" }
    })
}
$timer.Start()
[void]$form.ShowDialog()
$timer.Stop()
 })
            if ($stages.Count -gt 0) {
                $status.Text = ($stages[-1] -replace '^\[TH_STAGE\]\s+', "")
            }
        }
        # Refresh the Copy button from the complete report itself, not only
        # from process-exit timing. The copy handler enforces field allowlists.
        if ($script:activeAction -eq "Check") {
            $copyStatusButton.Enabled = [bool](Get-CompletedCheckPath)
        }
        $script:process.Refresh()
        if (-not $script:process.HasExited) { return }
        $exitCode = $script:process.ExitCode
        $completedAction = $script:activeAction
        $script:process.Dispose()
        $script:process = $null
        Set-Busy $false
        if ($exitCode -eq 3010) {
            $status.Text = "Windows setup needs a restart. Save your work, restart Windows, then reopen TOEFL House ERP and click Install."
            [System.Windows.Forms.MessageBox]::Show($status.Text, "Restart required") | Out-Null
        } elseif ($exitCode -eq 0) {
            if ($completedAction -eq "Prepare") {
                $status.Text = "Windows prerequisites are prepared. Select Install to continue."
            } elseif ($completedAction -eq "Stop") {
                $status.Text = "TOEFL House ERP has stopped safely. Your data remains stored."
            } elseif ($completedAction -eq "Check") {
                $script:lastCheckPath = $script:stdoutPath
                Set-Busy $false
                $status.Text = "Read-only PC check completed. This is not release approval. See View Details."
                if (Test-Path -LiteralPath $script:stdoutPath -PathType Leaf) {
                    Start-Process -FilePath "notepad.exe" -ArgumentList ('"' + $script:stdoutPath + '"')
                }
            } elseif ($completedAction -eq "UpdateCheck" -or $completedAction -eq "UpdateInstall") {
                $summary = Show-UpdateResult
                if (-not $summary) {
                    $summary = "The update action finished. Select View Details for the recorded result."
                }
                $status.Text = $summary
                if ($completedAction -eq "UpdateInstall") {
                    [System.Diagnostics.Process]::Start("http://127.0.0.1:8000/") | Out-Null
                }
            } else {
                if ($completedAction -eq "Install") {
                    try {
                        $shell = New-Object -ComObject WScript.Shell
                        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'TOEFL House ERP.lnk'))
                        $shortcut.TargetPath = $powershellExe
                        $shortcut.Arguments = '-NoLogo -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $guiPath + '" -AutoInstall'
                        $shortcut.WorkingDirectory = $productRoot
                        $shortcut.Save()
                    } catch { # A restricted Desktop does not invalidate a successful installation.
                    }
                }
                $status.Text = "TOEFL House ERP is ready. Opening in your browser."
                [System.Diagnostics.Process]::Start("http://127.0.0.1:8000/") | Out-Null
            }
        } else {
            if ($completedAction -eq "UpdateCheck" -or $completedAction -eq "UpdateInstall") {
                $summary = Show-UpdateResult
                if ($summary) { $status.Text = $summary } else { $status.Text = "The update stopped safely. Select View Details, or contact your support provider." }
            } else {
                $status.Text = "$completedAction could not finish safely. Nothing has been reset. Select View Details, or contact your support provider."
            }
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
        $repair.Text -ne "Repair" -or $stop.Text -ne "Stop" -or
        $checkButton.Text -ne "Check This PC" -or
        $updateButton.Text -ne "Check for Updates" -or
        $installUpdateButton.Text -ne "Install Update" -or
        $guideButton.Text -ne "Owner Readiness Guide" -or
        $handbookButton.Text -ne "Owner Handbook" -or
        $dailyGuideButton.Text -ne "How to Use" -or
        $copyStatusButton.Text -ne "Copy Safe Support Status" -or
        -not (Test-Path -LiteralPath $guideFile -PathType Leaf) -or
        -not (Test-Path -LiteralPath $handbookFile -PathType Leaf) -or
        -not (Test-Path -LiteralPath $dailyGuideFile -PathType Leaf)) {
        throw "Graphical lifecycle actions were not initialized."
    }
    # Simulate the exact Owner case: check writes a full report while the
    # wrapper still exists, then the GUI must allow safe copying. No real
    # clipboard access, Docker use, site change or credentials in this test.
    $syntheticCheck = [System.IO.Path]::GetTempFileName()
    try {
        $script:activeAction = "Check"
        $script:stdoutPath = $syntheticCheck
        $script:lastCheckPath = ""
        Set-Content -LiteralPath $syntheticCheck -Value @(
            "[TH_STAGE] Read-only PC check is running...",
            "TOEFL HOUSE ERP - READ-ONLY TECHNICAL CHECK",
            "Windows: 64-bit detected") -Encoding UTF8
        Set-Busy $true
        if ($copyStatusButton.Enabled) { throw "Copy activated before PC check completed." }
        Add-Content -LiteralPath $syntheticCheck -Value "End of read-only PC check."
        Set-Busy $true
        if (-not $copyStatusButton.Enabled) { throw "Complete read-only PC check cannot be copied while wrapper is closing." }
        Set-Busy $false
        if (-not $copyStatusButton.Enabled) { throw "Copy disabled after completed PC check." }
        $script:activeAction = "Start"
        $script:lastCheckPath = ""
        Set-Busy $false
        if ($copyStatusButton.Enabled) { throw "Previous PC check leaked into a different lifecycle action." }
    } finally {
        Remove-Item -LiteralPath $syntheticCheck -ErrorAction SilentlyContinue
    }
    Write-Host "Windows GUI controls initialized; completed-report copy availability verified."
    exit 0
}
Set-Busy $false
if ($AutoInstall) {
    $form.Add_Shown({
        if (Test-Path -LiteralPath (Join-Path $productRoot 'data\secrets\db.env')) {
            Start-LauncherAction "Start"
        } else { Start-LauncherAction "Install" }
    })
}
$timer.Start()
[void]$form.ShowDialog()
$timer.Stop()
