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

function Get-AuthenticatedPublicRecord([string]$Path, [string]$Fingerprint) {
    $fingerprint = $Fingerprint.Trim()
    if ($fingerprint -notmatch '^[a-f0-9]{64}$') {
        throw 'Enter the SHA-256 supplied separately by the verified approver.'
    }
    [byte[]]$bytes = Read-ApprovalInput $Path
    if ($bytes.Length -gt 8192) { throw 'The public key record exceeds the supported size.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '') }
    finally { $sha.Dispose() }
    if ($actual -ine $fingerprint) {
        throw 'The public key record does not match its independently confirmed SHA-256.'
    }
    return [Convert]::ToBase64String($bytes)
}

function Assert-ProtectedApprovalStorage([IO.FileSystemInfo]$Item, [switch]$RequireProtectedAcl) {
    $acl = Get-Acl -LiteralPath $Item.FullName
    $operator = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $allowed = @($operator, 'S-1-5-18', 'S-1-5-32-544')
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    $aces = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    $unexpected = @($aces | Where-Object { $_.IdentityReference.Value -notin $allowed })
    if (($RequireProtectedAcl -and !$acl.AreAccessRulesProtected) -or $owner -notin $allowed -or $unexpected.Count) {
        throw 'The installed approval files do not have their expected Windows protection.'
    }
}

function Assert-ProtectedEnrollmentDirectory([IO.DirectoryInfo]$Directory) {
    Assert-ProtectedApprovalStorage $Directory -RequireProtectedAcl
}

function Publish-InitialTrust([IO.DirectoryInfo]$Directory, [byte[]]$Bytes) {
    $Directory = Get-RegularLocalItem $Directory.FullName $true
    Assert-ProtectedEnrollmentDirectory $Directory
    if ($Bytes.Length -lt 1 -or $Bytes.Length -gt 16384) {
        throw 'The validated public trust record has an invalid size.'
    }
    $target = Join-Path $Directory.FullName 'internal-activation-trust.json'
    foreach ($filename in @('internal-activation-trust.json') + $approvalNames) {
        if (Get-Item -LiteralPath (Join-Path $Directory.FullName $filename) -Force -ErrorAction SilentlyContinue) {
            throw 'Approval keys or approval files already exist. Enrollment cannot replace them.'
        }
    }
    $pending = Join-Path $Directory.FullName ('.trust-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $created = $false
    try {
        $stream = [IO.File]::Open($pending, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        try {
            $stream.Write($Bytes, 0, $Bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        [IO.File]::Move($pending, $target)
    } finally {
        if ($created) { [IO.File]::Delete($pending) }
    }
}

function Set-InstalledDockerPath([string]$CurrentPath) {
    foreach ($bin in @((Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin'),
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'))) {
        if (Test-Path -LiteralPath (Join-Path $bin 'docker.exe') -PathType Leaf) {
            $env:Path = $bin + ';' + $CurrentPath
            break
        }
    }
}

function Get-InstalledEnrollment([string[]]$Records) {
    $expected = Join-Path $env:LOCALAPPDATA 'TOEFL House ERP\Customer\product\windows'
    $windows = Get-RegularLocalItem $expected $true
    if ($windows.FullName -ine $PSScriptRoot) {
        throw 'Open this form from the installed Windows ERP launcher.'
    }
    $product = $windows.Parent
    $directory = Get-RegularLocalItem (Join-Path $product.FullName 'data\activation') $true
    Assert-ProtectedEnrollmentDirectory $directory
    if (Test-Path -LiteralPath (Join-Path $product.FullName '.env')) {
        throw 'An unexpected Compose environment file is present. Verify the installed ERP.'
    }
    $verifyDocker = Get-RegularLocalItem (Join-Path $windows.FullName 'Test Local Docker.ps1') $false
    $verifyImage = Get-RegularLocalItem (Join-Path $windows.FullName 'Verify Package Image.ps1') $false
    $powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $savedPath = $env:Path
    Push-Location -LiteralPath $product.FullName
    try {
        Set-InstalledDockerPath $savedPath
        . $verifyDocker.FullName
        Assert-LocalDockerEngine
        $docker = Get-Command docker.exe -CommandType Application | Select-Object -First 1
        $web = @(& $powershell -NoLogo -NoProfile -NonInteractive -File $verifyImage.FullName -VerifyLoadedImage -GetVerifiedWebContainer)
        if ($LASTEXITCODE -ne 0 -or $web.Count -ne 1 -or $web[0] -cnotmatch '^[0-9a-f]{64}$') {
            throw 'The running ERP container failed installed image verification.'
        }
        $status = @(& $docker.Source exec $web[0] python3 /product/activate.py status)
        if ($LASTEXITCODE -ne 0 -or 'Site operational mode: REFUSED' -cnotin $status) {
            throw 'The verified ERP must be running and awaiting initial authorization.'
        }
        $inputJson = ConvertTo-Json -Compress -InputObject @($Records)
        $result = @($inputJson | & $docker.Source exec -i $web[0] python3 /product/activate.py internal-enrollment --confirm $site)
        if ($LASTEXITCODE -ne 0 -or $result.Count -ne 1) {
            throw 'The ERP refused to validate the two public keys. Check the named roles, key validity and independence.'
        }
        $verified = ConvertFrom-Json -InputObject $result[0]
        return @{ Directory = $directory; Trust = [Convert]::FromBase64String($verified.trust_b64);
                  Approvers = $verified.approvers }
    } finally {
        Pop-Location
        $env:Path = $savedPath
    }
}

function Assert-NewApprovalTargets([IO.DirectoryInfo]$Directory) {
    # Registered trust is read from its installed, protected location.
    # It is never imported from the signatures folder or rewritten.
    $trust = Get-RegularLocalItem (Join-Path $Directory.FullName 'internal-activation-trust.json') $false
    Assert-ProtectedApprovalStorage $trust
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
        Assert-ProtectedEnrollmentDirectory $activation
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
            Set-InstalledDockerPath $savedPath
            . $verifyDocker.FullName
            Assert-LocalDockerEngine
            $docker = Get-Command docker.exe -CommandType Application | Select-Object -First 1
            $web = @(& $powershell -NoLogo -NoProfile -NonInteractive -File $verifyImage.FullName -VerifyLoadedImage -GetVerifiedWebContainer)
            if ($LASTEXITCODE -ne 0 -or $web.Count -ne 1 -or $web[0] -cnotmatch '^[0-9a-f]{64}$') {
                throw 'The running ERP container failed installed image verification.'
            }
            & $powershell -NoLogo -NoProfile -NonInteractive -File $verifyBackup.FullName -VerifyExisting | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw 'The current encrypted backup did not verify. Use Verify Backup in the ERP launcher.'
            }
            $status = @(& $docker.Source exec $web[0] python3 /product/activate.py status)
            if ($LASTEXITCODE -ne 0 -or 'Site operational mode: REFUSED' -cnotin $status) {
                throw 'The verified local ERP must be running and awaiting authorization.'
            }
            & $docker.Source exec $web[0] python3 /product/activate.py internal-context --confirm $site | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'The installed ERP did not accept the current activation context.' }

            Publish-InternalApprovals $activation $input {
                $result = @(& $docker.Source exec $web[0] python3 /product/activate.py internal-activate --confirm $site)
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
$enrollButton = New-Object Windows.Forms.Button
$enrollButton.Text = 'Register public keys'
$enrollButton.SetBounds(508,238,196,36)
$form.Controls.Add($enrollButton)
$enrollButton.Add_Click({
    $wizard = New-Object Windows.Forms.Form
    $wizard.Text = 'First enrollment - authorized institute administrator'
    $wizard.StartPosition = 'CenterParent'
    $wizard.ClientSize = [Drawing.Size]::new(686,292)
    $note = New-Object Windows.Forms.Label
    $note.Text = 'Choose each approved public record. Enter its SHA-256 from a separate, authenticated communication. Do not enter a private key or a signature file.'
    $note.SetBounds(16,16,654,44)
    $wizard.Controls.Add($note)
    $paths = @()
    $digests = @()
    foreach ($entry in @(@('Course Owner',70), @('General Manager',144))) {
        $field = New-Object Windows.Forms.TextBox
        $field.ReadOnly = $true
        $field.SetBounds(202,$entry[1],454,23)
        $wizard.Controls.Add($field)
        $paths += $field
        $choose = New-Object Windows.Forms.Button
        $choose.Text = 'Choose ' + $entry[0]
        $choose.SetBounds(16,$entry[1],174,25)
        $choose.Tag = $field
        $wizard.Controls.Add($choose)
        $choose.Add_Click({
            param($sender, $eventArgs)
            $picker = New-Object Windows.Forms.OpenFileDialog
            try {
                $picker.Filter = 'Public key records (*.json)|*.json'
                if ($picker.ShowDialog($sender.FindForm()) -eq 'OK') { $sender.Tag.Text = $picker.FileName }
            } finally { $picker.Dispose() }
        })
        $label = New-Object Windows.Forms.Label
        $label.Text = 'Confirmed SHA-256'
        $label.SetBounds(16,($entry[1]+32),174,25)
        $wizard.Controls.Add($label)
        $digestBox = New-Object Windows.Forms.TextBox
        $digestBox.SetBounds(202,($entry[1]+32),454,23)
        $wizard.Controls.Add($digestBox)
        $digests += $digestBox
    }
    $register = New-Object Windows.Forms.Button
    $register.Text = 'Review and register'
    $register.SetBounds(16,233,174,35)
    $wizard.Controls.Add($register)
    $register.Add_Click({
        try {
            $register.Enabled = $false
            $records = @(Get-AuthenticatedPublicRecord $paths[0].Text $digests[0].Text;
                         Get-AuthenticatedPublicRecord $paths[1].Text $digests[1].Text)
            $verified = Get-InstalledEnrollment $records
            $summary = ($verified.Approvers | ForEach-Object {
                $_.approver_role + ': ' + $_.approver_identity + ' (' + $_.key_id + ')'
            }) -join [Environment]::NewLine
            $question = 'Register these separately authenticated public keys on this installation?' +
                [Environment]::NewLine + $summary
            if ([Windows.Forms.MessageBox]::Show($wizard,$question,$wizard.Text,'YesNo','Question') -eq 'Yes') {
                Publish-InitialTrust $verified.Directory $verified.Trust
                [void][Windows.Forms.MessageBox]::Show($wizard,'Public keys registered. Applying signatures is a separate step.',$wizard.Text)
                $wizard.Close()
            }
        } catch {
            [void][Windows.Forms.MessageBox]::Show($wizard,$_.Exception.Message,$wizard.Text,'OK','Error')
        } finally { $register.Enabled = $true }
    })
    try { [void]$wizard.ShowDialog($form) }
    finally { $wizard.Dispose() }
})

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
