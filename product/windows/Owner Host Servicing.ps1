# Authenticated, bounded servicing for the explicitly approved Owner update model.
# This module has no top-level mutations. The signed updater owns authorization;
# these helpers validate exact bytes, preserve prior files and commit a fixed
# code-only allowlist. Customer data, secrets, keys and factory receipts are absent.
$script:OwnerHostPublisher = 'C7A6E773E0F6FA66C8CA0F4EC2E9A0C1931D1722'
$script:OwnerHostFiles = @(
    'docker-compose.yml',
    'windows/Backup TOEFL House ERP.ps1',
    'windows/Update TOEFL House ERP.ps1',
    'windows/Owner Host Servicing.ps1',
    'windows/updater-strings.json',
    'updates/servicing/update_engine.py',
    'updates/servicing/update_host.py',
    'updates/servicing/update_entrypoint.sh',
    'updates/servicing/bootstrap.json',
    'updates/servicing/bootstrap.sig.json'
)

function Get-OwnerHostSha([string]$Path) {
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}

function Assert-OwnerHostOrdinaryPath([string]$Root, [string]$Relative) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
    if (-not $Relative -or $Relative.Contains('\') -or $Relative.Contains(':') -or
        $Relative.StartsWith('/') -or @($Relative.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count) {
        throw 'Unsafe host servicing path.'
    }
    $full = [IO.Path]::GetFullPath((Join-Path $rootFull $Relative))
    if (-not $full.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Host servicing path leaves its exact root.'
    }
    $cursor = $full
    while ($cursor -and -not $cursor.Equals($rootFull,[StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $cursor) {
            if (((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Host servicing never follows a reparse point.'
            }
        }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
    if (-not (Test-Path -LiteralPath $rootFull -PathType Container) -or
        ((Get-Item -LiteralPath $rootFull -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Host servicing root is not an ordinary existing directory.'
    }
    return $full
}

function Assert-OwnerHostScriptPublisher([string]$Path) {
    $sig = Get-AuthenticodeSignature -LiteralPath $Path
    if ([string]$sig.Status -cne 'Valid' -or $null -eq $sig.SignerCertificate -or
        [string]$sig.SignerCertificate.Thumbprint -cne $script:OwnerHostPublisher) {
        throw 'The host servicing code is not signed by the enrolled Windows publisher.'
    }
}

function Read-OwnerHostJson([string]$Path, [int64]$MaximumBytes = 262144) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $item.Length -lt 2 -or $item.Length -gt $MaximumBytes) { throw 'Host servicing document is unsafe.' }
    return ([IO.File]::ReadAllText($Path) | ConvertFrom-Json -ErrorAction Stop)
}

function Assert-OwnerHostFields($Object, [string[]]$Fields) {
    if ($null -eq $Object -or @((Compare-Object @($Object.PSObject.Properties.Name) $Fields)).Count) {
        throw 'Unsupported host servicing document fields.'
    }
}

function Get-VerifiedOwnerServicingRuntime([string]$RuntimeRoot) {
    $manifestPath = Assert-OwnerHostOrdinaryPath $RuntimeRoot 'bootstrap.json'
    $signaturePath = Assert-OwnerHostOrdinaryPath $RuntimeRoot 'bootstrap.sig.json'
    $document = Read-OwnerHostJson $manifestPath
    $signature = Read-OwnerHostJson $signaturePath
    Assert-OwnerHostFields $document @('schema_version','document_type','product','publisher_thumbprint','files')
    Assert-OwnerHostFields $signature @('schema_version','document_type','algorithm','key_id','signature_b64')
    if ($document.schema_version -ne 1 -or
        $document.document_type -cne 'toefl-house-erp-host-servicing-bootstrap' -or
        $document.product -cne 'TOEFL House ERP' -or
        $document.publisher_thumbprint -cne $script:OwnerHostPublisher -or
        $signature.schema_version -ne 1 -or
        $signature.document_type -cne 'toefl-house-erp-host-servicing-bootstrap-signature' -or
        $signature.algorithm -cne 'rsa-pkcs1v15-sha256' -or
        $signature.key_id -cne 'th-owner-c7-20261121') { throw 'Unsupported host servicing authority.' }
    $cert = Get-Item -LiteralPath ('Cert:\CurrentUser\My\' + $script:OwnerHostPublisher)
    $rsa = [Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
    try {
        $raw = [IO.File]::ReadAllBytes($manifestPath)
        $proof = [Convert]::FromBase64String([string]$signature.signature_b64)
        if (-not $rsa.VerifyData($raw,$proof,[Security.Cryptography.HashAlgorithmName]::SHA256,
                                [Security.Cryptography.RSASignaturePadding]::Pkcs1)) {
            throw 'Host servicing runtime signature failed.'
        }
    } finally { if ($rsa) { $rsa.Dispose() } }
    $required = @('update_engine.py','update_host.py','update_entrypoint.sh')
    $names = @($document.files | ForEach-Object { [string]$_.path })
    if ($names.Count -ne 3 -or @((Compare-Object $names $required)).Count) {
        throw 'Host servicing runtime has an unexpected executable set.'
    }
    $files = @()
    foreach ($entry in @($document.files)) {
        Assert-OwnerHostFields $entry @('path','sha256','size_bytes')
        if ([string]$entry.sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            [int64]$entry.size_bytes -lt 1 -or [int64]$entry.size_bytes -gt 1048576) {
            throw 'Host servicing code bounds are invalid.'
        }
        $file = Assert-OwnerHostOrdinaryPath $RuntimeRoot ([string]$entry.path)
        if ((Get-Item -LiteralPath $file).Length -ne [int64]$entry.size_bytes -or
            (Get-OwnerHostSha $file) -cne [string]$entry.sha256) { throw 'Authenticated authorizer bytes changed.' }
        $files += [pscustomobject]@{Path=$file;Name=[string]$entry.path;SHA256=[string]$entry.sha256}
    }
    return [pscustomobject]@{Root=[IO.Path]::GetFullPath($RuntimeRoot);ManifestSHA256=(Get-OwnerHostSha $manifestPath);Files=$files}
}

function Get-OwnerHostObservation([string]$ProductRoot,[string]$RuntimeRoot,[string]$ImageId) {
    if ($ImageId -cnotmatch '^sha256:[0-9a-f]{64}$') { throw 'An immutable observer image is required.' }
    $runtime=Get-VerifiedOwnerServicingRuntime $RuntimeRoot
    $broker=@($runtime.Files|Where-Object{$_.Name -ceq 'update_host.py'})
    if ($broker.Count -ne 1) { throw 'The authenticated observer source is missing.' }
    $root=[IO.Path]::GetFullPath($ProductRoot)
    if (-not (Test-Path -LiteralPath $root -PathType Container) -or
        ((Get-Item -LiteralPath $root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe observation root.' }
    $name='th-owner-observe-'+[guid]::NewGuid().ToString('N')
    $created=$false
    try {
        # This is a short-lived read-only observer, not another ERP installation.
        # It has no network, writable product mount or engine-auth state. The
        # only Docker API reader is the fixed-GET root broker; its client runs
        # as frappe and must pass the existing peer-credential/socket checks.
        $start=@(& docker run --detach --rm --name $name --network none --user root `
            --volume ($root+':/product-root:ro') `
            --volume ($broker[0].Path+':/product/update_host.py:ro') `
            --mount 'type=bind,source=/var/run/docker.sock,target=/run/th-update-docker.sock,readonly' `
            --entrypoint python3 $ImageId /product/update_host.py --serve 2>&1)
        if ($LASTEXITCODE -ne 0) { throw 'The fixed read-only observer could not start.' }
        $created=$true
        $ready=$false
        for($attempt=0;$attempt -lt 50;$attempt++) {
            $probe=@(& docker exec $name /bin/sh -c 'test -f /run/th-update-observer.ready' 2>&1)
            if($LASTEXITCODE -eq 0){$ready=$true;break}
            Start-Sleep -Milliseconds 100
        }
        if(-not $ready){throw 'The authenticated observer did not become ready.'}
        $client="import json,sys;sys.path.insert(0,'/product');import update_host;print(json.dumps(update_host.observe(),sort_keys=True))"
        $raw=@(& docker exec --user frappe $name python3 -c $client 2>&1)
        if($LASTEXITCODE -ne 0){throw 'The independent observer refused the host binding.'}
        $result=($raw -join [char]10)|ConvertFrom-Json -ErrorAction Stop
        if($result.schema_version -ne 1 -or
            [string]$result.identity.storage_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            [string]$result.identity.credentials_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
            [string]$result.identity.site_config_sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'The observer returned no exact installation binding.' }
        return $result
    } finally {
        if($created){
            # Only the exact transient process created above is retired. No
            # production container or volume is ever stopped/deleted here.
            $cleanup=@(& docker container rm --force $name 2>&1)
            if($LASTEXITCODE -ne 0){throw 'The transient observer could not be retired.'}
        }
    }
}

function Write-OwnerHostTransaction($Transaction) {
    $temporary = $Transaction.JournalPath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($temporary,($Transaction | ConvertTo-Json -Depth 12),$utf8)
    if ([IO.File]::Exists($Transaction.JournalPath)) {
        [IO.File]::Replace($temporary,$Transaction.JournalPath,[NullString]::Value)
    } else { [IO.File]::Move($temporary,$Transaction.JournalPath) }
}

function New-OwnerHostServiceTransaction($Plan, [string]$Archive, [string]$ProductRoot,
                                         [string]$WorkRoot, [string]$AuthorizationId) {
    if ([string]$AuthorizationId -cnotmatch '^[a-f0-9]{32}$') { throw 'An authenticated transaction identifier is required.' }
    Assert-OwnerHostFields $Plan @('archive','sha256','size_bytes','files')
    if ([string]$Plan.archive -cne 'toefl-house-erp-host.zip' -or
        [string]$Plan.sha256 -cnotmatch '^[a-f0-9]{64}$' -or
        [int64]$Plan.size_bytes -lt 1 -or [int64]$Plan.size_bytes -gt 16777216 -or
        (Get-Item -LiteralPath $Archive -Force).Length -ne [int64]$Plan.size_bytes -or
        (Get-OwnerHostSha $Archive) -cne [string]$Plan.sha256) { throw 'Host servicing archive differs from its signed plan.' }
    $names = @($Plan.files | ForEach-Object { [string]$_.path })
    if ($names.Count -lt 1 -or $names.Count -gt $script:OwnerHostFiles.Count -or
        @($names | Select-Object -Unique).Count -ne $names.Count -or
        @($names | Where-Object { $script:OwnerHostFiles -cnotcontains $_ }).Count) {
        throw 'Host servicing file set is not allowed.'
    }
    $stage = Assert-OwnerHostOrdinaryPath $WorkRoot 'host-stage'
    $backup = Assert-OwnerHostOrdinaryPath $WorkRoot 'host-before'
    if ((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $backup)) { throw 'Host servicing run was already staged.' }
    New-Item -ItemType Directory -Path $stage | Out-Null
    New-Item -ItemType Directory -Path $backup | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    $rows = @()
    try {
        if ($zip.Entries.Count -ne $names.Count) { throw 'Unexpected host ZIP entry count.' }
        $zipNames = @($zip.Entries | ForEach-Object { $_.FullName })
        if (@($zipNames | Select-Object -Unique).Count -ne $zipNames.Count -or
            @((Compare-Object $zipNames $names)).Count) { throw 'Host ZIP paths differ from the signed plan.' }
        foreach ($entry in @($Plan.files)) {
            Assert-OwnerHostFields $entry @('path','old_sha256','new_sha256','size_bytes')
            $relative = [string]$entry.path
            if ([string]$entry.new_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
                ($null -ne $entry.old_sha256 -and [string]$entry.old_sha256 -cnotmatch '^[a-f0-9]{64}$') -or
                [int64]$entry.size_bytes -lt 1 -or [int64]$entry.size_bytes -gt 1048576) { throw 'Invalid host file identity.' }
            $target = Assert-OwnerHostOrdinaryPath $ProductRoot $relative
            $staged = Assert-OwnerHostOrdinaryPath $stage $relative
            $saved = Assert-OwnerHostOrdinaryPath $backup $relative
            $present = Test-Path -LiteralPath $target -PathType Leaf
            if ($null -eq $entry.old_sha256) {
                if (Test-Path -LiteralPath $target) { throw 'A new servicing destination already exists.' }
            } elseif (-not $present -or (Get-OwnerHostSha $target) -cne [string]$entry.old_sha256) {
                throw 'Installed host code differs from the approved source.'
            }
            $member = $zip.GetEntry($relative)
            if ($null -eq $member -or $member.Length -ne [int64]$entry.size_bytes -or
                (($member.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Host ZIP member is missing or unsafe.' }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($staged)) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($member,$staged,$false)
            if ((Get-OwnerHostSha $staged) -cne [string]$entry.new_sha256) { throw 'Host ZIP member checksum differs.' }
            if ($relative.EndsWith('.ps1',[StringComparison]::OrdinalIgnoreCase)) { Assert-OwnerHostScriptPublisher $staged }
            if ($present) {
                New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($saved)) -Force | Out-Null
                [IO.File]::Copy($target,$saved,$false)
                if ((Get-OwnerHostSha $saved) -cne [string]$entry.old_sha256) { throw 'Host rollback copy failed.' }
            }
            $rows += [pscustomobject]@{Relative=$relative;Target=$target;Staged=$staged;Saved=$saved;
                OldSHA256=$entry.old_sha256;NewSHA256=[string]$entry.new_sha256;CommitStarted=$false;Committed=$false}
        }
    } finally { $zip.Dispose() }
    $transaction = [pscustomobject]@{SchemaVersion=1;DocumentType='toefl-house-erp-host-servicing-transaction';
        AuthorizationId=$AuthorizationId;PlanSHA256=[string]$Plan.sha256;ProductRoot=[IO.Path]::GetFullPath($ProductRoot);WorkRoot=[IO.Path]::GetFullPath($WorkRoot);
        Phase='prepared';JournalPath=(Join-Path $WorkRoot 'host-transaction.json');Files=$rows}
    Assert-OwnerHostTransactionShape $transaction
    Write-OwnerHostTransaction $transaction
    return $transaction
}

function Assert-OwnerHostBeforeCommit($Transaction) {
    Assert-OwnerHostTransactionShape $Transaction
    if ($Transaction.Phase -cne 'prepared') { throw 'Host transaction is not prepared.' }
    foreach ($row in @($Transaction.Files)) {
        $target = Assert-OwnerHostOrdinaryPath $Transaction.ProductRoot $row.Relative
        if ($target -cne $row.Target -or (Get-OwnerHostSha $row.Staged) -cne $row.NewSHA256) { throw 'Staged host code changed.' }
        if ($null -eq $row.OldSHA256) {
            if (Test-Path -LiteralPath $target) { throw 'New host destination changed before commit.' }
        } elseif (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
                  (Get-OwnerHostSha $target) -cne $row.OldSHA256 -or
                  (Get-OwnerHostSha $row.Saved) -cne $row.OldSHA256) { throw 'Original host code changed before commit.' }
    }
}

function Complete-OwnerHostServiceTransaction($Transaction) {
    Assert-OwnerHostBeforeCommit $Transaction
    $Transaction.Phase='committing';Write-OwnerHostTransaction $Transaction
    try {
        foreach ($row in @($Transaction.Files)) {
            $row.CommitStarted=$true
            Write-OwnerHostTransaction $Transaction
            $target = Assert-OwnerHostOrdinaryPath $Transaction.ProductRoot $row.Relative
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
            $temporary = $target + '.' + [guid]::NewGuid().ToString('N') + '.servicing'
            [IO.File]::Copy($row.Staged,$temporary,$false)
            if ((Get-OwnerHostSha $temporary) -cne $row.NewSHA256) { throw 'Host commit copy failed.' }
            if ([IO.File]::Exists($target)) { [IO.File]::Replace($temporary,$target,[NullString]::Value) }
            else { [IO.File]::Move($temporary,$target) }
            $row.Committed=$true
            Write-OwnerHostTransaction $Transaction
            if ((Get-OwnerHostSha $target) -cne $row.NewSHA256) { throw 'Host commit readback failed.' }
        }
        $Transaction.Phase='committed';Write-OwnerHostTransaction $Transaction
    } catch {
        # No DB migration is part of this Owner bridge. Restore only exact code
        # files we committed; never overwrite customer data or unknown bytes.
        Undo-OwnerHostServiceTransaction $Transaction
        throw
    }
}

function Assert-OwnerHostTransactionShape($Transaction) {
    if ($Transaction.SchemaVersion -ne 1 -or $Transaction.DocumentType -cne 'toefl-house-erp-host-servicing-transaction' -or
        [string]$Transaction.AuthorizationId -cnotmatch '^[0-9a-f]{32}$' -or
        [string]$Transaction.PlanSHA256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Malformed host transaction identity.' }
    $work = [IO.Path]::GetFullPath([string]$Transaction.WorkRoot).TrimEnd('\','/')
    $product = [IO.Path]::GetFullPath([string]$Transaction.ProductRoot).TrimEnd('\','/')
    $runs = [IO.Path]::GetFullPath((Join-Path $product 'data/updates/runs')).TrimEnd('\','/')
    if (-not $work.StartsWith($runs+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($work) -cnotmatch '^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$' -or
        $Transaction.JournalPath -cne (Join-Path $work 'host-transaction.json')) { throw 'Host transaction leaves its installation run.' }
    if (@($Transaction.Files).Count -lt 1 -or @($Transaction.Files).Count -gt $script:OwnerHostFiles.Count -or
        @($Transaction.Files.Relative | Select-Object -Unique).Count -ne @($Transaction.Files).Count) { throw 'Malformed host transaction file set.' }
    foreach ($row in @($Transaction.Files)) {
        if ($script:OwnerHostFiles -cnotcontains [string]$row.Relative -or
            [string]$row.NewSHA256 -cnotmatch '^[0-9a-f]{64}$' -or
            ($null -ne $row.OldSHA256 -and [string]$row.OldSHA256 -cnotmatch '^[0-9a-f]{64}$') -or
            $row.Committed -isnot [bool] -or $row.CommitStarted -isnot [bool]) { throw 'Malformed host transaction row.' }
        if ($row.Target -cne (Assert-OwnerHostOrdinaryPath $product $row.Relative) -or
            $row.Staged -cne (Assert-OwnerHostOrdinaryPath $work ('host-stage/'+$row.Relative)) -or
            $row.Saved -cne (Assert-OwnerHostOrdinaryPath $work ('host-before/'+$row.Relative))) { throw 'Host transaction path binding changed.' }
    }
}

function Undo-OwnerHostServiceTransaction($Transaction) {
    Assert-OwnerHostTransactionShape $Transaction
    $Transaction.Phase='rolling-back';Write-OwnerHostTransaction $Transaction
    $rows = @($Transaction.Files);[array]::Reverse($rows)
    foreach ($row in $rows) {
        if (-not $row.CommitStarted -and -not $row.Committed) { continue }
        $target = Assert-OwnerHostOrdinaryPath $Transaction.ProductRoot $row.Relative
        if (Test-Path -LiteralPath $target -PathType Leaf) { $actual=Get-OwnerHostSha $target } else { $actual=$null }
        # A crash may happen after atomic file replacement and before the next
        # journal write. The durable intent marker plus exact byte identities
        # decides whether this row changed; unknown bytes are never overwritten.
        if (($null -eq $row.OldSHA256 -and $null -eq $actual) -or
            ($null -ne $row.OldSHA256 -and $actual -ceq $row.OldSHA256)) {
            $row.Committed=$false;$row.CommitStarted=$false;Write-OwnerHostTransaction $Transaction;continue
        }
        if ($actual -cne $row.NewSHA256) { throw 'Host rollback found unknown bytes; preserve for recovery.' }
        if ($null -eq $row.OldSHA256) { [IO.File]::Delete($target) }
        else {
            if ((Get-OwnerHostSha $row.Saved) -cne $row.OldSHA256) { throw 'Host rollback bytes changed.' }
            $temporary=$target+'.'+[guid]::NewGuid().ToString('N')+'.rollback'
            [IO.File]::Copy($row.Saved,$temporary,$false);[IO.File]::Replace($temporary,$target,[NullString]::Value)
            if ((Get-OwnerHostSha $target) -cne $row.OldSHA256) { throw 'Host rollback readback failed.' }
        }
        $row.Committed=$false;$row.CommitStarted=$false;Write-OwnerHostTransaction $Transaction
    }
    $Transaction.Phase='rolled-back';Write-OwnerHostTransaction $Transaction
}

function Assert-OwnerEnrollmentPublicKey($Key,$CertificateParameters,[string]$OwnerIdentity,[string]$OwnerSid) {
    # These are public parameters obtained from the already pinned, native
    # certificate. A thumbprint label in an input trust file is not key proof.
    $purposes=@('update-manifest','update-policy','owner-update-authorization')
    if ($Key.key_id -cne 'th-owner-c7-20261121' -or $Key.algorithm -cne 'rsa-pkcs1v15-sha256' -or
        $Key.modulus_b64 -cne [Convert]::ToBase64String($CertificateParameters.Modulus) -or
        $Key.exponent_b64 -cne [Convert]::ToBase64String($CertificateParameters.Exponent) -or
        $Key.publisher_thumbprint -cne $script:OwnerHostPublisher -or $Key.approver_identity -cne $OwnerIdentity -or
        $Key.approver_role -cne 'course-owner' -or $Key.approver_windows_sid -cne $OwnerSid -or
        @($Key.purposes).Count -ne 3 -or @(Compare-Object @($Key.purposes) $purposes).Count) {
        throw 'The enrolled public key, Owner or purposes differ from the approved existing publisher.'
    }
}

function Assert-OwnerCompletedReleaseState([string]$ProductRoot,$Release,$Policy,$Recorded,$Completed) {
    # This pure no-mutation binding is called only AFTER native publisher and
    # raw release signatures have passed. It does not approve another update.
    $targetId=[string]$Release.image.config_digest
    if ($Release.image.PSObject.Properties['runtime_id']) { $targetId=[string]$Release.image.runtime_id }
    if ($Recorded.schema_version -ne 1 -or $Recorded.document_type -cne 'toefl-house-erp-installed-image' -or
        $Recorded.provenance -cne 'signed-update' -or $Completed.phase -cne 'completed' -or
        $Completed.schema_version -ne 1 -or $Completed.document_type -cne 'toefl-house-erp-update-journal' -or
        [string]$Completed.transaction_id -cnotmatch '^[0-9a-f]{32}$' -or
        $Release.product -cne 'TOEFL House ERP' -or $Release.release_status -cne 'PRODUCTION RELEASE' -or
        $Release.production_authorization -cne 'AUTHORIZED' -or
        $Recorded.image_id -cne $targetId -or $Recorded.release_version -cne $Release.version -or
        $Recorded.source_revision -cne $Release.source_revision -or $Completed.version -cne $Release.version -or
        $Recorded.original_release_revision -cne $Release.legacy_bridge.source_revision -or
        $Release.version -cne $Policy.transition.target_version -or $targetId -cne $Policy.transition.target_image_id -or
        $Release.source_revision -cne $Policy.transition.target_revision) {
        throw 'Completed setup identity does not match this authenticated release.'
    }
    $hostNames=@()
    foreach ($entry in @($Release.host_service.files)) {
        if ($script:OwnerHostFiles -cnotcontains [string]$entry.path -or $hostNames -ccontains [string]$entry.path -or
            [string]$entry.new_sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Completed setup host plan is invalid.' }
        $target=Assert-OwnerHostOrdinaryPath $ProductRoot ([string]$entry.path)
        if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
            (Get-OwnerHostSha $target) -cne [string]$entry.new_sha256 -or
            (Get-Item -LiteralPath $target).Length -ne [int64]$entry.size_bytes) {
            throw 'Completed setup host code has changed; no replay was attempted.'
        }
        $hostNames += [string]$entry.path
    }
    if (@($hostNames).Count -lt 3 -or
        @(@('docker-compose.yml','windows/Backup TOEFL House ERP.ps1','windows/Update TOEFL House ERP.ps1')|
            Where-Object{$hostNames -cnotcontains $_}).Count) {
        throw 'Completed setup is missing required host corrections.'
    }
    return [pscustomobject]@{RuntimeId=$targetId;Version=[string]$Release.version;SourceRevision=[string]$Release.source_revision}
}
