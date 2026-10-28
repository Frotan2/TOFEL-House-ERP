# Execute the actual updater functions with isolated Docker/engine substitutes.
# No customer data, network request, Docker daemon or persistent file is used.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '../../product/windows/Update TOEFL House ERP.ps1'
$tokens = $null
$problems = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    [System.IO.Path]::GetFullPath($source), [ref]$tokens, [ref]$problems)
if ($problems.Count) { throw 'Updater syntax errors' }
function Import-ProbeFunction([string]$Name, [bool]$CatchExit = $false) {
    $node = $ast.Find({ param($item)
        $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -ceq $Name
    }.GetNewClosure(), $true)
    if ($null -eq $node) { throw ('Missing actual updater function: ' + $Name) }
    $text = $node.Extent.Text
    # Preserve terminal control flow while making its exit observable to the
    # test process. Only the common recovery exit is intercepted, not branches.
    if ($CatchExit) { $text = $text.Replace('exit $script:ExitRecoveryRequired', 'throw "PROBE_RECOVERY_EXIT"') }
    return [scriptblock]::Create($text)
}
$script:ExitAllowed = 0
$script:ExitRefused = 3
$script:ExitFailed = 5
$script:ExitRecoveryRequired = 6
$script:WorkDir = Join-Path $env:TEMP ('th-update-failure-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $script:WorkDir | Out-Null
try {
    . (Import-ProbeFunction 'Invoke-EngineStep')
    . (Import-ProbeFunction 'Stop-EngineFailure')
    function Write-Stage { }
    function Stop-Update { param($Code, $Status, $Section, $Key, $Version) throw $Key }
    function Set-JournalState { param($Phase, $Version) $script:LastPhase = $Phase }
    function Invoke-UpdateEngine { return $script:FakeExit }
    function Read-EngineResponse { return $script:FakeReport }
    $script:FakeExit = 5
    foreach ($outcome in @('safe-abort', 'recovery-required')) {
        $script:FakeReport = [pscustomobject]@{
            document_type = 'toefl-house-erp-update-engine-response'
            status = 'failed'; transaction_outcome = $outcome
        }
        $result = Invoke-EngineStep 'apply' @{ action = 'apply' } 'test-version'
        if ($result.transaction_outcome -cne $outcome) { throw 'Structured failure did not reach recovery handler' }
    }
    $script:FakeReport = [pscustomobject]@{
        document_type = 'toefl-house-erp-update-engine-response'
        status = 'succeeded'; transaction_outcome = 'completed'
    }
    $script:LastPhase = ''
    try { Invoke-EngineStep 'apply' @{} 'test-version'; throw 'inconsistent exit was accepted' }
    catch { if ($_.Exception.Message -cne 'updater.recovery_required') { throw } }
    if ($script:LastPhase -cne 'recovery-required') { throw 'Engine failure did not persist recovery hold' }
    $script:FakeReport = $null
    try { Invoke-EngineStep 'apply' @{} 'test-version'; throw 'missing report was accepted' }
    catch { if ($_.Exception.Message -cne 'updater.recovery_required') { throw } }
    $script:FakeReport = [pscustomobject]@{document_type='toefl-house-erp-update-engine-response';decision='allow'}
    $script:FakeExit = 3
    try { Invoke-EngineStep 'recheck' @{} 'test-version'; throw 'inconsistent check was accepted' }
    catch { if ($_.Exception.Message -cne 'updater.engine_failed') { throw } }

    # Exercise the real installed-engine compatibility probe without a
    # Docker daemon. A missing broker is legacy; transport/probe failures must
    # not be treated as permission to run without the observer.
    . (Import-ProbeFunction 'Test-ImageRequiresObserver')
    function Invoke-Docker { param($Arguments)
        $script:ProbeArguments = @($Arguments)
        return [pscustomobject]@{ Code = $script:ProbeExit }
    }
    $imageId = 'sha256:' + ('a' * 64)
    $script:ProbeExit = 0
    if (-not (Test-ImageRequiresObserver $imageId)) { throw 'Hardened image was not detected' }
    if (@($script:ProbeArguments) -ccontains '/run/th-update-docker.sock') {
        throw 'Capability probe unexpectedly mounted a Docker socket'
    }
    $script:ProbeExit = 1
    if (Test-ImageRequiresObserver $imageId) { throw 'Legacy image was granted observer access' }
    $script:ProbeExit = 125
    try { Test-ImageRequiresObserver $imageId; throw 'Probe infrastructure failure was accepted' }
    catch { if ($_.Exception.Message -cne 'updater.guard_blocked') { throw } }

    . (Import-ProbeFunction 'Invoke-UpdateInstall' $true)
    function Invoke-EngineStep {
        param($Mode, $Request, $Version)
        [void]$script:Calls.Add(('engine ' + $Mode))
        if ($Mode -ceq 'preflight') { return [pscustomobject]@{decision='allow';transaction=[pscustomobject]@{transaction_id=('c' * 32);phase='manifest'}} }
        if ($Mode -ceq 'authorize') { return [pscustomobject]@{
            decision='allow';transaction=[pscustomobject]@{transaction_id=('d' * 32);phase='authorized'}
            target=[pscustomobject]@{image=[pscustomobject]@{config_digest=('sha256:' + ('b' * 64))}}
        } }
        if ($Mode -ceq 'recheck') { return [pscustomobject]@{decision='allow'} }
        return $script:ApplyReport
    }
    function Get-InstalledImage { return [pscustomobject]@{Id=('sha256:' + ('b' * 64))} }
    function Assert-EngineAllowed { param($Response, $Version)
        if ($Response.decision -cne 'allow') { throw 'not allowed' }
    }
    function Invoke-Compose { param($Arguments)
        [void]$script:Calls.Add(('compose ' + ($Arguments -join ' ')))
        return $script:StopExit
    }
    function Invoke-DockerVerbose { param($Arguments)
        [void]$script:Calls.Add(($Arguments -join ' '))
        if ($Arguments[0] -ceq 'load') { return $script:LoadExit }
        return 0
    }
    function Invoke-UpdateStart { $script:StartCount++; return $true }
    function Wait-ForApplication { return $true }
    function Get-BlockerCodes { return @('apply.host_unsafe') }
    function Get-Text { return $null }
    function Save-Result { }
    function Write-Bilingual { }
    $ConfirmationAccepted = $true
    $imageTag = 'toefl-house-erp-app:local'
    $check = [pscustomobject]@{
        Version = 'test-version'; Archive = 'synthetic.tar'; RunFolder = 'data/updates/runs/test'
        Installed = [pscustomobject]@{image_id=('sha256:' + ('a' * 64));version='old'}
        Transaction = [pscustomobject]@{transaction_id=('a' * 32)}
        Response = [pscustomobject]@{target=[pscustomobject]@{image=[pscustomobject]@{config_digest=('sha256:' + ('b' * 64))}}}
        Request = @{ action='authorize';transaction=@{} }
        Manifest='manifest.json';Signature='manifest.sig'
    }
    # These paths are read-only existence checks and deliberately absent here.
    $recoveryAuthorizationPath = Join-Path $script:WorkDir 'missing-authorization'
    $recoverySignaturePath = Join-Path $script:WorkDir 'missing-signature'
    $recoverySignature2Path = Join-Path $script:WorkDir 'missing-signature-2'
    foreach ($scenario in @('stop-failed', 'load-failed', 'safe-abort', 'migration-failed')) {
        $script:Calls = New-Object System.Collections.ArrayList
        $script:StartCount = 0
        $script:LastPhase = ''
        $script:StopExit = 0; $script:LoadExit = 0
        $script:EngineImage = $null; $script:UseObserver = $false
        if ($scenario -ceq 'stop-failed') { $script:StopExit = 1 }
        if ($scenario -ceq 'load-failed') { $script:LoadExit = 1 }
        $outcome = 'recovery-required'
        if ($scenario -ceq 'safe-abort') { $outcome = 'safe-abort' }
        $script:ApplyReport = [pscustomobject]@{status='failed';transaction_outcome=$outcome}
        try { Invoke-UpdateInstall $check; throw 'failed update returned success' }
        catch {
            if (@('updater.recovery_required','PROBE_RECOVERY_EXIT') -cnotcontains $_.Exception.Message) { throw }
        }
        if ($script:StartCount -ne 0) { throw ('Unsafe automatic restart: ' + $scenario) }
        if ($script:LastPhase -cne 'recovery-required') { throw ('Missing durable hold: ' + $scenario) }
        if ($scenario -cne 'load-failed') {
            $order = $script:Calls -join '|'
            if ($order -cnotmatch 'engine preflight.*engine authorize.*load --input synthetic.tar.*engine preflight.*engine authorize.*engine recheck') {
                throw ('The candidate did not establish a fresh authorization: ' + $scenario)
            }
            if ($scenario -cne 'stop-failed' -and $order -cnotmatch 'engine recheck.*compose stop.*tag sha256:.*engine apply') {
                throw ('The candidate did not recheck before stopping and applying: ' + $scenario)
            }
        }
    }
    Write-Host 'PASS: structured failures preserved; no automatic restart on stop/import/apply failure.'
} finally {
    Remove-Item -LiteralPath $script:WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}
