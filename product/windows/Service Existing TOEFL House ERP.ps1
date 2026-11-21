# Publisher-authenticated, explicitly enrolled servicing of an existing site.
# This entry never initializes a site, changes credentials, replaces a database,
# generates recovery keys, or treats a factory grant as update authority.
param(
    [Parameter(Mandatory=$true)][string]$TargetProductRoot,
    [Parameter(Mandatory=$true)][string]$OfflineBundleRoot,
    [Parameter(Mandatory=$true)][string]$BootstrapRoot,
    [switch]$OwnerApprovalAccepted,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$publisher='C7A6E773E0F6FA66C8CA0F4EC2E9A0C1931D1722'

function Assert-ServicingPublisher([string]$Path) {
    $item=Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe servicing executable.' }
    $sig=Get-AuthenticodeSignature -LiteralPath $Path
    if ([string]$sig.Status -cne 'Valid' -or $null -eq $sig.SignerCertificate -or
        [string]$sig.SignerCertificate.Thumbprint -cne $publisher) { throw 'The servicing executable has no valid enrolled publisher signature.' }
}

function Copy-ServicingEnrollmentEvidence([string]$Source,[string]$History,[string]$Name,[string]$ExpectedSHA256) {
    if ($Name -cnotin @('enrollment.json','enrollment.sig.json') -or
        $ExpectedSHA256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Unexpected enrollment evidence copy.' }
    $sourceItem=Get-Item -LiteralPath $Source -Force
    if ($sourceItem.PSIsContainer -or ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $sourceItem.Length -lt 2 -or $sourceItem.Length -gt 262144 -or
        (Get-OwnerHostSha $Source) -cne $ExpectedSHA256) { throw 'Authenticated enrollment evidence changed.' }
    $destination=Assert-OwnerHostOrdinaryPath $History $Name
    if (Test-Path -LiteralPath $destination) {
        $existing=Get-Item -LiteralPath $destination -Force
        if ($existing.PSIsContainer -or $existing.Length -ne $sourceItem.Length -or
            (Get-OwnerHostSha $destination) -cne $ExpectedSHA256) { throw 'Existing enrollment audit evidence differs; no overwrite performed.' }
        return
    }
    # Publish a complete evidence file atomically. A crash after publishing one
    # of the two files can resume by accepting only its exact already-saved
    # bytes; neither an unknown file nor a partial copy is overwritten.
    $temporary=$destination+'.'+[guid]::NewGuid().ToString('N')+'.evidence'
    [IO.File]::Copy($Source,$temporary,$false)
    if ((Get-Item -LiteralPath $temporary).Length -ne $sourceItem.Length -or
        (Get-OwnerHostSha $temporary) -cne $ExpectedSHA256) { throw 'Enrollment evidence staging failed.' }
    [IO.File]::Move($temporary,$destination)
}

try {
    Assert-ServicingPublisher $PSCommandPath
    $product=[IO.Path]::GetFullPath($TargetProductRoot).TrimEnd('\','/')
    $expected=[IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'TOEFL House ERP/Customer/product')).TrimEnd('\','/')
    if (-not $product.Equals($expected,[StringComparison]::OrdinalIgnoreCase)) { throw 'Servicing targets only this existing Windows installation.' }
    foreach ($path in @($product,[IO.Path]::GetFullPath($BootstrapRoot),[IO.Path]::GetFullPath($OfflineBundleRoot))) {
        $item=Get-Item -LiteralPath $path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'A servicing root is absent or redirected.' }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $product 'data/secrets/db.env') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $product 'data/sites/toeflhouse.localhost/site_config.json') -PathType Leaf)) {
        throw 'The preserved site and credentials must already exist. Setup will not create them.'
    }
    $helper=Join-Path $BootstrapRoot 'Owner Host Servicing.ps1'
    $updater=Join-Path $BootstrapRoot 'Update TOEFL House ERP.ps1'
    Assert-ServicingPublisher $helper
    Assert-ServicingPublisher $updater
    . $helper
    $runtime=Get-VerifiedOwnerServicingRuntime $BootstrapRoot
    $enrollmentPath=Assert-OwnerHostOrdinaryPath $BootstrapRoot 'enrollment.json'
    $signaturePath=Assert-OwnerHostOrdinaryPath $BootstrapRoot 'enrollment.sig.json'
    $enrollment=Read-OwnerHostJson $enrollmentPath
    $signature=Read-OwnerHostJson $signaturePath
    Assert-OwnerHostFields $enrollment @('schema_version','document_type','product','publisher_thumbprint','owner_identity','owner_windows_sid','approval_record_sha256','files')
    Assert-OwnerHostFields $signature @('schema_version','document_type','algorithm','key_id','signature_b64')
    if ($enrollment.schema_version -ne 1 -or $enrollment.document_type -cne 'toefl-house-erp-owner-update-enrollment' -or
        $enrollment.product -cne 'TOEFL House ERP' -or $enrollment.publisher_thumbprint -cne $publisher -or
        $signature.schema_version -ne 1 -or $signature.document_type -cne 'toefl-house-erp-owner-update-enrollment-signature' -or
        $signature.algorithm -cne 'rsa-pkcs1v15-sha256' -or $signature.key_id -cne 'th-owner-c7-20261121') { throw 'Unsupported Owner enrollment authority.' }
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
    if ([string]$enrollment.owner_windows_sid -cne $identity.User.Value -or
        [string]$enrollment.owner_identity -cnotmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$' -or
        [string]$enrollment.approval_record_sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'The actual Windows Owner does not match the explicit enrollment.' }
    $cert=Get-Item -LiteralPath ('Cert:\CurrentUser\My\'+$publisher)
    $rsa=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
    try {
        if (-not $rsa.VerifyData([IO.File]::ReadAllBytes($enrollmentPath),[Convert]::FromBase64String([string]$signature.signature_b64),
            [Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)) { throw 'Owner enrollment signature failed.' }
    } finally { if ($rsa) { $rsa.Dispose() } }
    $required=@('trust-store.json','owner-policy.json','owner-policy.json.sig','recovery-authorization.json',
        'recovery-authorization.sig','prior-restore-evidence.json','owner-policy-decision.json','owner-channel.json')
    $names=@($enrollment.files|ForEach-Object{[string]$_.path})
    if ($names.Count -ne $required.Count -or @($names|Select-Object -Unique).Count -ne $names.Count -or
        @(Compare-Object $names $required).Count) { throw 'Unexpected enrollment document set.' }
    $enrollmentRoot=Assert-OwnerHostOrdinaryPath $BootstrapRoot 'enrollment'
    $verified=@()
    foreach ($entry in @($enrollment.files)) {
        Assert-OwnerHostFields $entry @('path','sha256','size_bytes')
        if ([string]$entry.sha256 -cnotmatch '^[0-9a-f]{64}$' -or [int64]$entry.size_bytes -lt 2 -or [int64]$entry.size_bytes -gt 262144) { throw 'Enrollment document bounds are invalid.' }
        $source=Assert-OwnerHostOrdinaryPath $enrollmentRoot ([string]$entry.path)
        if ((Get-Item -LiteralPath $source).Length -ne [int64]$entry.size_bytes -or
            (Get-OwnerHostSha $source) -cne [string]$entry.sha256) { throw 'Enrollment document bytes changed.' }
        $verified += [pscustomobject]@{Name=[string]$entry.path;Source=$source;SHA256=[string]$entry.sha256}
    }
    $policy=Read-OwnerHostJson (Join-Path $enrollmentRoot 'owner-policy.json')
    $decision=Read-OwnerHostJson (Join-Path $enrollmentRoot 'owner-policy-decision.json')
    if ($policy.owner_identity -cne $enrollment.owner_identity -or $policy.owner_windows_sid -cne $identity.User.Value -or
        $policy.approval_record_sha256 -cne $enrollment.approval_record_sha256 -or
        (Get-OwnerHostSha (Join-Path $enrollmentRoot 'owner-policy-decision.json')) -cne $enrollment.approval_record_sha256 -or
        $decision.status -cne 'EXPLICIT_OWNER_POLICY_CHANGE_APPROVED' -or $decision.owner_email -cne $enrollment.owner_identity -or
        $decision.windows_sid -cne $identity.User.Value -or $decision.existing_recovery_key_must_be_preserved -ne $true) {
        throw 'The real explicit Owner decision does not bind this policy.'
    }
    # A provisioned update key is new authority only after this explicit Owner
    # enrollment. Its public key must be the actual pinned certificate, not a
    # trust-store entry that merely repeats the certificate thumbprint text.
    $trust=Read-OwnerHostJson (Join-Path $enrollmentRoot 'trust-store.json')
    $keys=@($trust.keys)
    if ($trust.schema_version -ne 1 -or $trust.document_type -cne 'toefl-house-erp-update-trust-store' -or
        $trust.product -cne 'TOEFL House ERP' -or $trust.provisioned -ne $true -or $keys.Count -ne 1) { throw 'Unexpected provisioned update trust.' }
    $key=$keys[0]
    $rsa=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
    try { $parameters=$rsa.ExportParameters($false) } finally { if ($rsa) { $rsa.Dispose() } }
    Assert-OwnerEnrollmentPublicKey $key $parameters ([string]$enrollment.owner_identity) $identity.User.Value

    # Reopening this same authenticated release is an opener, never a replayed
    # authorization. Only a genuinely completed signed-update identity plus
    # every exact new host-file hash can take this no-mutation path. An expired
    # old Owner approval is not reused to perform another update.
    $installedIdentityPath=Join-Path $product 'data/activation/installed-image-identity.json'
    $completedJournalPath=Join-Path $product 'data/updates/journal.json'
    if ((Test-Path -LiteralPath $installedIdentityPath -PathType Leaf) -and
        (Test-Path -LiteralPath $completedJournalPath -PathType Leaf)) {
        $recorded=Read-OwnerHostJson $installedIdentityPath 4096
        $completed=Read-OwnerHostJson $completedJournalPath
        if ($recorded.provenance -ceq 'signed-update' -and $completed.phase -ceq 'completed') {
            $releasePath=Assert-OwnerHostOrdinaryPath $OfflineBundleRoot 'update.json'
            $releaseSignaturePath=Assert-OwnerHostOrdinaryPath $OfflineBundleRoot 'update.json.sig'
            $release=Read-OwnerHostJson $releasePath
            $releaseSignature=Read-OwnerHostJson $releaseSignaturePath
            Assert-OwnerHostFields $releaseSignature @('schema_version','document_type','algorithm','key_id','signature_b64')
            if ($releaseSignature.schema_version -ne 1 -or $releaseSignature.document_type -cne 'toefl-house-erp-update-signature' -or
                $releaseSignature.algorithm -cne 'rsa-pkcs1v15-sha256' -or $releaseSignature.key_id -cne $key.key_id) { throw 'Invalid signed-release envelope for completed setup.' }
            $rsa=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
            try {
                if (-not $rsa.VerifyData([IO.File]::ReadAllBytes($releasePath),[Convert]::FromBase64String([string]$releaseSignature.signature_b64),
                    [Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)) { throw 'Completed setup release signature failed.' }
            } finally { if ($rsa) { $rsa.Dispose() } }
            $completedState=Assert-OwnerCompletedReleaseState $product $release $policy $recorded $completed
            $targetId=$completedState.RuntimeId
            # If the daemon is available, a wrong tag is a hard refusal. If it
            # is stopped, this remains only an opener; daily Start independently
            # starts Docker and verifies the recorded image before any service.
            $dockerInfo=@(& docker info --format '{{.ServerVersion}}' 2>$null)
            if ($LASTEXITCODE -eq 0) {
                $raw=@(& docker image inspect 'toefl-house-erp-app:local' --format '{{json .}}' 2>$null)
                if ($LASTEXITCODE -ne 0) { throw 'The completed update image is absent; use protected recovery.' }
                $loaded=($raw -join [char]10)|ConvertFrom-Json
                if ($loaded.Id -cne $targetId -or $loaded.Config.Labels.'org.toefl-house.source-revision' -cne $release.source_revision -or
                    $loaded.Config.Labels.'org.toefl-house.release-version' -cne $release.version -or
                    $loaded.Config.Labels.'org.toefl-house.source-eol' -cne 'lf-v1') { throw 'The actual loaded image differs from completed setup.' }
            }
            Write-Host 'This exact signed release and host code were already installed by a completed update. No approval or update was replayed.'
            Write-Host 'Use the existing TOEFL House ERP launcher to open or start the system.'
            exit 0
        }
    }

    # The C installation-volume floor remains intact, independently rechecked
    # later by the new engine's live root observer. E is never substituted here.
    $drive=Get-PSDrive -Name ([IO.Path]::GetPathRoot($product).Substring(0,1))
    if ([int64]$drive.Free -lt 32212254720) { throw 'The installation drive has less than the required 30 GiB.' }
    if ($CheckOnly) {
        Write-Host 'Publisher signatures, exact authorizer bytes, explicit Owner enrollment and installation-volume space verified.'
        Write-Host 'Static check only: no trust, site, service or database was changed; engine authorization is still required before installation.'
        exit 0
    }
    if (-not $OwnerApprovalAccepted) { throw 'Explicit Owner approval is required; no enrollment was written.' }
    $updates=Join-Path $product 'data/updates'
    if (Test-Path -LiteralPath (Join-Path $updates 'update.lock')) { throw 'An update is already active; enrollment is preserved.' }
    $journal=Join-Path $updates 'journal.json'
    if (Test-Path -LiteralPath $journal -PathType Leaf) {
        $state=Read-OwnerHostJson $journal
        if ($state.phase -cnotin @('idle','completed','rolled-back')) { throw 'An interrupted update must be resolved before enrollment changes.' }
    }
    New-Item -ItemType Directory -Path $updates -Force|Out-Null
    $account=$identity.Name
    & icacls $updates /inheritance:r /grant:r ($account+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not protect the enrolled update state.' }
    $enrollmentDigest=Get-OwnerHostSha $enrollmentPath
    $history=Join-Path $updates ('enrollment-history/'+$enrollmentDigest)
    $intentPath=Join-Path $history 'intent.json'
    if (Test-Path -LiteralPath $history) {
        # Resume only this exact signed enrollment after a process interruption.
        # Completed enrollment is not silently replayed, and changed/unknown
        # state is never overwritten to manufacture an update authorization.
        $intent=Read-OwnerHostJson $intentPath
        if ($intent.schema_version -ne 1 -or $intent.document_type -cne 'toefl-house-erp-owner-enrollment-intent' -or
            $intent.enrollment_sha256 -cne $enrollmentDigest -or $intent.owner_windows_sid -cne $identity.User.Value -or
            $intent.phase -cnotin @('prepared','committing') -or @($intent.files).Count -ne $verified.Count) { throw 'Existing enrollment state cannot be replayed or rebound.' }
    } else {
        New-Item -ItemType Directory -Path $history -Force|Out-Null
        $before=@()
        foreach ($row in $verified) {
            $destination=Assert-OwnerHostOrdinaryPath $updates $row.Name
            $previous=$null
            if (Test-Path -LiteralPath $destination -PathType Leaf) { $previous=Get-OwnerHostSha $destination }
            $before += [pscustomobject]@{name=$row.Name;old_sha256=$previous;new_sha256=$row.SHA256}
        }
        $intent=[pscustomobject]@{schema_version=1;document_type='toefl-house-erp-owner-enrollment-intent';
            enrollment_sha256=$enrollmentDigest;owner_windows_sid=$identity.User.Value;phase='prepared';files=$before}
        [IO.File]::WriteAllText($intentPath,($intent|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
    }
    $intent.phase='committing'
    $temporaryIntent=$intentPath+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
    [IO.File]::WriteAllText($temporaryIntent,($intent|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
    [IO.File]::Replace($temporaryIntent,$intentPath,[NullString]::Value)
    foreach ($row in $verified) {
        $destination=Assert-OwnerHostOrdinaryPath $updates $row.Name
        $binding=@($intent.files|Where-Object{$_.name -ceq $row.Name})
        if ($binding.Count -ne 1 -or $binding[0].new_sha256 -cne $row.SHA256) { throw 'Enrollment document binding changed.' }
        $actual=$null
        if (Test-Path -LiteralPath $destination -PathType Leaf) { $actual=Get-OwnerHostSha $destination }
        if ($actual -ceq $row.SHA256) { continue }
        if ($actual -cne $binding[0].old_sha256) { throw 'Enrollment found unknown active bytes; no overwrite performed.' }
        if ($null -ne $actual) {
            $saved=Join-Path $history ($row.Name+'.before')
            if (Test-Path -LiteralPath $saved -PathType Leaf) {
                if ((Get-OwnerHostSha $saved) -cne $actual) { throw 'Prior enrollment snapshot changed.' }
            } else { [IO.File]::Copy($destination,$saved,$false) }
        }
        $temporary=$destination+'.'+[guid]::NewGuid().ToString('N')+'.enrollment'
        [IO.File]::Copy($row.Source,$temporary,$false)
        if ((Get-OwnerHostSha $temporary) -cne $row.SHA256) { throw 'Enrollment staging failed.' }
        if ([IO.File]::Exists($destination)) { [IO.File]::Replace($temporary,$destination,[NullString]::Value) }
        else { [IO.File]::Move($temporary,$destination) }
    }
    Copy-ServicingEnrollmentEvidence $enrollmentPath $history 'enrollment.json' $enrollmentDigest
    Copy-ServicingEnrollmentEvidence $signaturePath $history 'enrollment.sig.json' (Get-OwnerHostSha $signaturePath)
    $audit=[ordered]@{schema_version=1;document_type='toefl-house-erp-owner-enrollment-audit';
        recorded_utc=(Get-Date).ToUniversalTime().ToString('o');owner_identity=$enrollment.owner_identity;
        owner_windows_sid=$identity.User.Value;windows_account=$identity.Name;enrollment_sha256=$enrollmentDigest;
        decision_sha256=$enrollment.approval_record_sha256;runtime_sha256=$runtime.ManifestSHA256;
        recovery_key_replaced=$false;factory_authority_repurposed=$false;documents=$verified|Select-Object Name,SHA256}
    [IO.File]::WriteAllText((Join-Path $history 'audit.json'),($audit|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
    $intent.phase='committed'
    $temporaryIntent=$intentPath+'.'+[guid]::NewGuid().ToString('N')+'.tmp'
    [IO.File]::WriteAllText($temporaryIntent,($intent|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
    [IO.File]::Replace($temporaryIntent,$intentPath,[NullString]::Value)
    $native=Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell/v1.0/powershell.exe'
    & $native -NoLogo -NoProfile -NonInteractive -File $updater -Action Install -ConfirmationAccepted `
        -TargetProductRoot $product -OfflineBundleRoot ([IO.Path]::GetFullPath($OfflineBundleRoot)) -BootstrapRoot $runtime.Root
    exit $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('Existing-site servicing stopped safely: '+$_.Exception.Message)
    exit 5
}
