[CmdletBinding()]
param([switch]$SmokeTest)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$site = 'toeflhouse.localhost'
$approvalNames = @('internal-activation.owner.sig.json',
    'internal-activation.reviewer.sig.json', 'internal-activation.json')
$maxApprovalBytes = 65536

function Get-RegularLocalItem([string]$Path, [bool]$Directory) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.FullName -notmatch '^[A-Za-z]:\\' -or $item.PSIsContainer -ne $Directory) {
        throw 'Choose a regular local Windows file or directory.'
    }
    $entry = $item
    while ($null -ne $entry) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Linked activation files and folders are not supported.'
        }
        if ($entry.PSIsContainer) { $entry = $entry.Parent }
        else { $entry = $entry.Directory }
    }
    return $item
}

function Read-ApprovalInput([string]$Path) {
    $file = Get-RegularLocalItem $Path $false
    $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open,
        [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($stream.Length -lt 1 -or $stream.Length -gt $maxApprovalBytes) {
            throw 'An approval file is empty or larger than the allowed size.'
        }
        $buffer = New-Object IO.MemoryStream
        try {
            $stream.CopyTo($buffer)
            if ($buffer.Length -lt 1 -or $buffer.Length -gt $maxApprovalBytes) {
                throw 'An approval file changed or exceeds the allowed size.'
            }
            return ,$buffer.ToArray()
        } finally { $buffer.Dispose() }
    } finally { $stream.Dispose() }
}

function Assert-NewApprovalTargets([IO.DirectoryInfo]$Directory) {
    # Registered trust is read from its installed, protected location.
    # It is never imported from the signatures folder or rewritten.
    Get-RegularLocalItem (Join-Path $Directory.FullName 'internal-activation-trust.json') $false | Out-Null
    foreach ($name in $approvalNames) {
        $existing = Get-Item -LiteralPath (Join-Path $Directory.FullName $name) -Force -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            throw 'Approval files are already present. Preserve them and use the approved reconciliation process.'
        }
    }
}

function Publish-InternalApprovals([IO.DirectoryInfo]$Directory, [System.Collections.IDictionary]$Inputs, [scriptblock]$Apply) {
    Assert-NewApprovalTargets $Directory
    $staged = [Collections.Generic.List[object]]::new()
    $ok = $false
    try {
        foreach ($name in $approvalNames) {
            if (!$Inputs.Contains($name) -or $Inputs[$name] -isnot [byte[]] -or
                $Inputs[$name].Length -lt 1 -or $Inputs[$name].Length -gt $maxApprovalBytes) {
                throw 'The exact signed request and both detached signatures are required.'
            }
            $pending = Join-Path $Directory.FullName ('.pending-' + [guid]::NewGuid().ToString('N') + '.json')
            $final = Join-Path $Directory.FullName $name
            $stream = [IO.File]::Open($pending, [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write, [IO.FileShare]::None)
            $item = @{ Pending = $pending; Final = $final; Digest = ''; Published = $false }
            $staged.Add($item)
            try {
                $stream.Write($Inputs[$name], 0, $Inputs[$name].Length)
                $stream.Flush($true)
            } finally { $stream.Dispose() }
            $item.Digest = (Get-FileHash -LiteralPath $pending -Algorithm SHA256).Hash
        }
        foreach ($item in $staged) {
            # The request is published last. File.Move refuses replacement.
            [IO.File]::Move($item.Pending, $item.Final)
            $item.Published = $true
        }
        & $Apply
        $ok = $true
    } finally {
        foreach ($item in $staged) {
            if (!$item.Published) {
                [IO.File]::Delete($item.Pending)
            } elseif (!$ok) {
                $file = Get-Item -LiteralPath $item.Final -Force -ErrorAction SilentlyContinue
                if ($null -ne $file -and !$file.PSIsContainer -and
                    !($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
                    (Get-FileHash -LiteralPath $item.Final -Algorithm SHA256).Hash -ceq $item.Digest) {
                    [IO.File]::Delete($item.Final)
                }
            }
        }
    }
}

function Invoke-InstalledActivation([string[]]$Paths) {
    $mutex = [System.Threading.Mutex]::new($false, 'Local\TOEFLHouseERP.InternalActivation')
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne(0)
        } catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
            throw 'A previous activation was interrupted. Review the installation and any protected approval files before retrying.'
        }
        if (!$acquired) { throw 'An activation is already being applied.' }

        $customer = Join-Path $env:LOCALAPPDATA 'TOEFL House ERP\Customer'
        $product = Get-RegularLocalItem (Join-Path $customer 'product') $true
        $windows = Get-RegularLocalItem (Join-Path $product.FullName 'windows') $true
        $activation = Get-RegularLocalItem (Join-Path $product.FullName 'data\activation') $true
        if (!(Test-Path -LiteralPath (Join-Path $activation.FullName 'internal-activation-trust.json') -PathType Leaf)) {
            throw 'The independently authenticated public key trust has not been registered. Ask the authorized institute administrator to complete enrollment.'
        }
        Assert-NewApprovalTargets $activation
        if (Test-Path -LiteralPath (Join-Path $product.FullName '.env')) {
            throw 'An unexpected Compose environment file is present. Verify the installed ERP before activation.'
        }

        $input = [ordered]@{}
        for ($i = 0; $i -lt $approvalNames.Count; $i++) {
            $input[$approvalNames[$i]] = Read-ApprovalInput $Paths[$i]
        }
        $verifyImage = Get-RegularLocalItem (Join-Path $windows.FullName 'Verify Package Image.ps1') $false
        $verifyBackup = Get-RegularLocalItem (Join-Path $windows.FullName 'Backup TOEFL House ERP.ps1') $false
        $verifyDocker = Get-RegularLocalItem (Join-Path $windows.FullName 'Test Local Docker.ps1') $false
        $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $savedPath = $env:Path
        Push-Location -LiteralPath $product.FullName
        try {
            foreach ($bin in @((Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'),
                    (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'))) {
                if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe') -PathType Leaf) {
                    $env:Path = $bin + ';' + $savedPath
                    break
                }
            }
            . $verifyDocker.FullName
            Assert-LocalDockerEngine
            $docker = Get-Command docker.exe -CommandType Application | Select-Object -First 1
            & $powershell -NoLogo -NoProfile -NonInteractive -File $verifyImage.FullName -VerifyLoadedImage | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'The loaded ERP image failed verification.' }
            & $powershell -NoLogo -NoProfile -NonInteractive -File $verifyBackup.FullName -VerifyExisting | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw 'The current encrypted backup did not verify. Use Verify Backup in the ERP launcher.'
            }
            $status = @(& $docker.Source compose exec -T web python3 /product/activate.py status)
            if ($LASTEXITCODE -ne 0 -or 'Site operational mode: REFUSED' -cnotin $status) {
                throw 'The verified local ERP must be running and awaiting authorization.'
            }
            & $docker.Source compose exec -T web python3 /product/activate.py internal-context --confirm $site | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'The installed ERP did not accept the current activation context.' }

            Publish-InternalApprovals $activation $input {
                $result = @(& $docker.Source compose exec -T web python3 /product/activate.py internal-activate --confirm $site)
                if ($LASTEXITCODE -ne 0) {
                    $reason = $result | Where-Object { $_ -cmatch '^REFUSED: [^\x00-\x1f]{1,500}$' } | Select-Object -First 1
                    if ($reason) { throw $reason }
                    throw 'The ERP could not complete guarded activation. Check its operating mode before retrying.'
                }
            }
        } finally {
            Pop-Location
            $env:Path = $savedPath
        }
    } finally {
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = 'TOEFL House ERP - Apply authorized activation'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = [Drawing.Size]::new(720, 298)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$info = New-Object Windows.Forms.Label
$info.Text = 'Select the original request and the separate signed approvals. The existing registered public keys will be used to verify them.'
$info.Location = [Drawing.Point]::new(16,16)
$info.Size = [Drawing.Size]::new(688,38)
$form.Controls.Add($info)

function Add-ApprovalPicker([string]$Text, [int]$Y) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $Text
    $label.Location = [Drawing.Point]::new(16,$Y)
    $label.Size = [Drawing.Size]::new(206,26)
    $form.Controls.Add($label)
    $field = New-Object Windows.Forms.TextBox
    $field.ReadOnly = $true
    $field.Location = [Drawing.Point]::new(230,$Y)
    $field.Size = [Drawing.Size]::new(340,26)
    $form.Controls.Add($field)
    $button = New-Object Windows.Forms.Button
    $button.Text = 'Choose file'
    $button.Location = [Drawing.Point]::new(585,$Y)
    $button.Size = [Drawing.Size]::new(119,26)
    $button.Tag = $field
    $form.Controls.Add($button)
    $button.Add_Click({
        param($sender, $eventArgs)
        $picker = New-Object Windows.Forms.OpenFileDialog
        try {
            $picker.Filter = 'Authorization files (*.json)|*.json'
            $picker.CheckFileExists = $true
            $picker.Multiselect = $false
            if ($picker.ShowDialog($form) -eq [Windows.Forms.DialogResult]::OK) {
                $sender.Tag.Text = $picker.FileName
            }
        } finally { $picker.Dispose() }
    })
    return $field
}

$requestField = Add-ApprovalPicker 'Original activation request' 62
$ownerField = Add-ApprovalPicker 'Course Owner signature' 102
$reviewerField = Add-ApprovalPicker 'General Manager signature' 142
$confirmed = New-Object Windows.Forms.CheckBox
$confirmed.Text = 'The Course Owner authorized activation on this computer and the approvers independently reviewed the request.'
$confirmed.Location = [Drawing.Point]::new(16,184)
$confirmed.Size = [Drawing.Size]::new(688,38)
$form.Controls.Add($confirmed)

$applyButton = New-Object Windows.Forms.Button
$applyButton.Text = 'Verify and apply'
$applyButton.Location = [Drawing.Point]::new(16,238)
$applyButton.Size = [Drawing.Size]::new(160,36)
$form.Controls.Add($applyButton)
$closeButton = New-Object Windows.Forms.Button
$closeButton.Text = 'Close'
$closeButton.DialogResult = 'Cancel'
$closeButton.Location = [Drawing.Point]::new(194,238)
$closeButton.Size = [Drawing.Size]::new(104,36)
$form.Controls.Add($closeButton)
$form.CancelButton = $closeButton

$applyButton.Add_Click({
    $paths = @($ownerField.Text, $reviewerField.Text, $requestField.Text)
    if (!$confirmed.Checked -or @($paths | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count) {
        [void][Windows.Forms.MessageBox]::Show($form,
            'Select all three authorization files and confirm the approval before continuing.',
            $form.Text, [Windows.Forms.MessageBoxButtons]::OK, [Windows.Forms.MessageBoxIcon]::Warning)
        return
    }
    $applyButton.Enabled = $false
    $form.UseWaitCursor = $true
    try {
        Invoke-InstalledActivation $paths
        [void][Windows.Forms.MessageBox]::Show($form,
            'The signatures verified and internal activation is complete. Open ERP to continue first-run setup.',
            $form.Text, [Windows.Forms.MessageBoxButtons]::OK, [Windows.Forms.MessageBoxIcon]::Information)
        $form.Close()
    } catch {
        [void][Windows.Forms.MessageBox]::Show($form, $_.Exception.Message,
            $form.Text, [Windows.Forms.MessageBoxButtons]::OK, [Windows.Forms.MessageBoxIcon]::Error)
    } finally {
        $form.UseWaitCursor = $false
        $applyButton.Enabled = $true
    }
})

if ($SmokeTest) {
    if ($confirmed.Checked -or $applyButton.Text -cne 'Verify and apply' -or
        $requestField.Text -or $ownerField.Text -or $reviewerField.Text) {
        throw 'The activation importer did not initialize with empty, unconfirmed inputs.'
    }
    $form.Dispose()
    Write-Output 'Activation import form initialized with no inputs or confirmation.'
    exit 0
}
[void]$form.ShowDialog()
$form.Dispose()
