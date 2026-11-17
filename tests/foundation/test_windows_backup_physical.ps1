$ErrorActionPreference = 'Stop'
$path = Join-Path (Join-Path $PSScriptRoot '..\..') 'product\windows\Backup TOEFL House ERP.ps1'
$tokens = $null
$errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if ($errors) { throw ($errors | Out-String) }
$names = @('Get-BackupPhysicalDiskNumber','Assert-SeparateBackupDisk')
$functions = @($tree.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names
},$true))
if ($functions.Count -ne $names.Count) { throw 'Physical disk guards missing.' }
foreach ($function in $functions) { . ([ScriptBlock]::Create($function.Extent.Text)) }
function Get-Partition([string]$DriveLetter) {
    switch ($DriveLetter) {
        'C' { [pscustomobject]@{DiskNumber=0} }
        'D' { [pscustomobject]@{DiskNumber=0} }
        'E' { [pscustomobject]@{DiskNumber=1} }
        'V' { [pscustomobject]@{DiskNumber=2} }
        'M' { [pscustomobject]@{DiskNumber=1}; [pscustomobject]@{DiskNumber=2} }
    }
}
function Get-Disk([int]$Number) {
    [pscustomobject]@{BusType=(@('NVMe','SATA','FileBackedVirtual')[$Number])}
}
Assert-SeparateBackupDisk 'C:' 'E:'
foreach ($invalid in @('D:','V:','M:','N:','bad')) {
    $refused = $false
    try { Assert-SeparateBackupDisk 'C:' $invalid }
    catch { $refused = $true }
    if (!$refused) { throw "Unsafe backup destination accepted: $invalid" }
}
'Windows backup guard accepted a separate disk and refused same-disk, virtual, missing and ambiguous targets.'
