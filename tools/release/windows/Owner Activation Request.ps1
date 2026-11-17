[CmdletBinding()]
param([switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object Windows.Forms.Form
$form.Text = 'TOEFL House ERP - Prepare activation request'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = [Drawing.Size]::new(720, 538)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

function Add-Label([string]$Text,[int]$Y) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $Text
    $label.Location = [Drawing.Point]::new(16,$Y)
    $label.Size = [Drawing.Size]::new(235,30)
    $form.Controls.Add($label)
}
function Add-Field([string]$Label,[int]$Y) {
    Add-Label $Label $Y
    $field = New-Object Windows.Forms.TextBox
    $field.Location = [Drawing.Point]::new(252,$Y)
    $field.Size = [Drawing.Size]::new(448,26)
    $form.Controls.Add($field)
    return $field
}
function Add-Check([string]$Text,[int]$Y) {
    $check = New-Object Windows.Forms.CheckBox
    $check.Text = $Text
    $check.Location = [Drawing.Point]::new(16,$Y)
    $check.Size = [Drawing.Size]::new(680,26)
    $form.Controls.Add($check)
    return $check
}
function Show-Result([string]$Message,[Windows.Forms.MessageBoxIcon]$Icon) {
    [void][Windows.Forms.MessageBox]::Show($form,$Message,$form.Text,
        [Windows.Forms.MessageBoxButtons]::OK,$Icon)
}

$proof = Add-Field 'Reviewed host evidence reference' 20
$revision = Add-Field 'Independently verified source revision' 52
$setup = Add-Field 'Independently verified installer SHA-256' 84
$owner = Add-Field 'Verified Course Owner identity' 116
$ownerKey = Add-Field 'Course Owner signing key ID' 148
$manager = Add-Field 'Verified General Manager identity' 180
$managerKey = Add-Field 'General Manager signing key ID' 212
$hostChecked = Add-Check 'Windows host acceptance is recorded.' 252
$privateChecked = Add-Check 'Two staff devices and excluded access were verified.' 280
$custodyChecked = Add-Check 'The two signing identities and separate key custody were verified.' 308
$restoreChecked = Add-Check 'Approved isolated recovery evidence was reviewed.' 336
$diskChecked = Add-Check 'The backup disk is physically separate from the Windows ERP and Docker data disks.' 364

Add-Label 'The request uses this computer.' 406
$create = New-Object Windows.Forms.Button
$create.Text = 'Save unsigned request'
$create.Location = [Drawing.Point]::new(16,447)
$create.Size = [Drawing.Size]::new(190,38)
$form.Controls.Add($create)
$close = New-Object Windows.Forms.Button
$close.Text = 'Close'
$close.DialogResult = 'Cancel'
$close.Location = [Drawing.Point]::new(226,447)
$close.Size = [Drawing.Size]::new(100,38)
$form.Controls.Add($close)
$form.CancelButton = $close

$create.Add_Click({
    $reviewed = @($hostChecked,$privateChecked,$custodyChecked,$restoreChecked,$diskChecked)
    if (@($reviewed | Where-Object { -not $_.Checked }).Count) {
        Show-Result 'Review and verify every listed item before requesting authorization.' Warning
        return
    }
    $picker = New-Object Windows.Forms.FolderBrowserDialog
    try {
        $picker.Description = 'Select a controlled folder for the new unsigned request.'
        if ($picker.ShowDialog($form) -ne [Windows.Forms.DialogResult]::OK) { return }
        $selected = $picker.SelectedPath
    } finally {
        $picker.Dispose()
    }

    $record = [ordered]@{
        schema_version = 1
        host = [Environment]::MachineName
        acceptance_evidence_reference = $proof.Text.Trim()
        source_revision = $revision.Text.Trim().ToLowerInvariant()
        setup_sha256 = $setup.Text.Trim().ToLowerInvariant()
        windows_host_acceptance_verified = $hostChecked.Checked
        private_staff_access_verified = $privateChecked.Checked
        owner_key_custody_verified = $custodyChecked.Checked
        rehearsal_restore_verified = $restoreChecked.Checked
        docker_backup_disk_isolation_verified = $diskChecked.Checked
        approvals = @(
            [ordered]@{approver_role='course-owner';approver_identity=$owner.Text.Trim();key_id=$ownerKey.Text.Trim()}
            [ordered]@{approver_role='general-manager';approver_identity=$manager.Text.Trim();key_id=$managerKey.Text.Trim()}
        )
    }
    $temp = Join-Path $env:TEMP ("toefl-erp-acceptance-" + [guid]::NewGuid().ToString('N') + ".json")
    $create.Enabled = $false
    $form.UseWaitCursor = $true
    $acceptanceFileCreated = $false
    try {
        $helper = Join-Path $PSScriptRoot 'Prepare Internal Activation.ps1'
        if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
            throw 'The verified activation request helper is missing.'
        }
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 6))
        $stream = [IO.File]::Open($temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        $acceptanceFileCreated = $true
        try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
        $result = & $helper -AcceptanceRecord $temp -OutputDirectory $selected
        Show-Result (($result -join [Environment]::NewLine) +
            [Environment]::NewLine + 'Send these exact request bytes separately to the two signers.') Information
    } catch {
        Show-Result $_.Exception.Message Error
    } finally {
        if ($acceptanceFileCreated) { [IO.File]::Delete($temp) }
        $form.UseWaitCursor = $false
        $create.Enabled = $true
    }
})

if ($SmokeTest) {
    if ($diskChecked.Checked -or $hostChecked.Checked -or
        $create.Text -cne 'Save unsigned request' -or $form.Controls.Count -lt 20) {
        throw 'The activation form did not start with empty, unconfirmed inputs.'
    }
    $form.Dispose()
    Write-Output 'Activation form initialized with all acceptance confirmations off.'
    exit 0
}
[void]$form.ShowDialog()
$form.Dispose()
