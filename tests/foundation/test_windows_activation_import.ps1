$ErrorActionPreference = 'Stop'
$script = Join-Path (Join-Path $PSScriptRoot '..\..') 'tools\release\windows\Apply Internal Activation.ps1'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$names = @('Get-RegularLocalItem', 'Read-ApprovalInput', 'Assert-NewApprovalTargets', 'Publish-InternalApprovals')
foreach ($node in $ast.EndBlock.Statements) {
    if ($node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names) {
        . ([scriptblock]::Create($node.Extent.Text))
    }
}

$approvalNames = @('internal-activation.owner.sig.json', 'internal-activation.reviewer.sig.json', 'internal-activation.json')
$maxApprovalBytes = 65536
$root = Join-Path $env:TEMP ('toefl-activation-fixture-' + [guid]::NewGuid().ToString('N'))
$directory = [IO.Directory]::CreateDirectory($root)
$trust = Join-Path $root 'internal-activation-trust.json'
$source = Join-Path $root 'request-fixture.json'
$approved = [ordered]@{
    'internal-activation.owner.sig.json' = [byte[]](0x7b,0x7d,0x0a)
    'internal-activation.reviewer.sig.json' = [byte[]](0x7b,0x7d,0x0d,0x0a)
    'internal-activation.json' = [byte[]](0x7b,0x20,0x7d,0x0d,0x0a)
}
function Expect-Refusal([scriptblock]$Action, [string]$Pattern) {
    try { & $Action }
    catch {
        if ($_.Exception.Message -notlike $Pattern) { throw }
        return
    }
    throw 'The unapproved input was accepted.'
}
try {
    Expect-Refusal { Assert-NewApprovalTargets $directory } '*cannot find path*'
    [IO.File]::WriteAllText($trust, 'already registered fixture')
    $originalTrustHash = (Get-FileHash -LiteralPath $trust).Hash
    [IO.File]::WriteAllBytes($source, $approved['internal-activation.json'])
    $fromDisk = Read-ApprovalInput $source
    if ($fromDisk -isnot [byte[]] -or
        [Convert]::ToBase64String($fromDisk) -ne [Convert]::ToBase64String($approved['internal-activation.json'])) {
        throw 'The file picker reader did not preserve the exact signed bytes.'
    }
    [IO.File]::WriteAllBytes($source, [byte[]]::new($maxApprovalBytes + 1))
    Expect-Refusal { Read-ApprovalInput $source } '*larger*'

    $script:applications = 0
    Expect-Refusal {
        Publish-InternalApprovals $directory $approved {
            $script:applications++
            foreach ($name in $approvalNames) {
                $bytes = [IO.File]::ReadAllBytes((Join-Path $root $name))
                if ([Convert]::ToBase64String($bytes) -cne [Convert]::ToBase64String($approved[$name])) {
                    throw 'The applied bytes differed from the signed bytes.'
                }
            }
            throw 'fixture verifier refused the signature'
        }
    } '*fixture verifier refused*'
    if ($script:applications -ne 1 -or
        @((Get-ChildItem -LiteralPath $root -Force | Where-Object Name -Like '.pending-*')).Count) {
        throw 'The failed invocation did not clean its staged files.'
    }
    Assert-NewApprovalTargets $directory

    $oldSignature = Join-Path $root $approvalNames[0]
    [IO.File]::WriteAllText($oldSignature, 'previously preserved signature')
    Expect-Refusal { Publish-InternalApprovals $directory $approved { throw 'must not apply' } } '*already present*'
    if ([IO.File]::ReadAllText($oldSignature) -cne 'previously preserved signature') {
        throw 'A previously preserved authorization file changed.'
    }
    [IO.File]::Delete($oldSignature)
    Publish-InternalApprovals $directory $approved { $script:applications++ }
    if ($script:applications -ne 2 -or (Get-FileHash -LiteralPath $trust).Hash -cne $originalTrustHash) {
        throw 'Publication failed or changed the existing trust store.'
    }
    foreach ($name in $approvalNames) {
        if (![IO.File]::Exists((Join-Path $root $name))) { throw 'Successful approvals were not preserved.' }
    }
    'Activation importer preserved raw inputs and registered trust, refused conflicts, and cleaned its failed staging.'
} finally {
    # Only remove the files created in this exact disposable fixture.
    foreach ($name in $approvalNames + @('request-fixture.json','internal-activation-trust.json')) {
        [IO.File]::Delete((Join-Path $root $name))
    }
    [IO.Directory]::Delete($root)
}
