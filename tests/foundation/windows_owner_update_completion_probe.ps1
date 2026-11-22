param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
. (Join-Path $SourceRoot 'product/windows/Owner Host Servicing.ps1')
$temp=Join-Path ([IO.Path]::GetTempPath()) ('th-owner-completion-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
$passed=New-Object Collections.Generic.List[string]
function Assert-True([bool]$Condition,[string]$Name){if(-not $Condition){throw ('Failed: '+$Name)}}
function Must-Refuse([scriptblock]$Action,[string]$Name){$refused=$false;try{& $Action}catch{$refused=$true};Assert-True $refused $Name;$passed.Add($Name)}
function Copy-Object($Object){return ($Object|ConvertTo-Json -Depth 15|ConvertFrom-Json)}
try {
    # Public-parameter fixtures are identity bytes only: no RSA key, certificate,
    # signature, account or actual production authorization is created.
    $parameters=[pscustomobject]@{Modulus=[byte[]]@(17,23,41,67);Exponent=[byte[]]@(1,0,1)}
    $sid='S-1-5-21-1-2-3-1001';$owner='owner@example.test'
    $key=[pscustomobject]@{key_id='th-owner-c7-20261121';algorithm='rsa-pkcs1v15-sha256';
        modulus_b64=[Convert]::ToBase64String($parameters.Modulus);exponent_b64=[Convert]::ToBase64String($parameters.Exponent);
        publisher_thumbprint=$script:OwnerHostPublisher;approver_identity=$owner;approver_role='course-owner';approver_windows_sid=$sid;
        purposes=@('update-manifest','update-policy','owner-update-authorization')}
    Assert-OwnerEnrollmentPublicKey $key $parameters $owner $sid
    $passed.Add('enrollment binds actual certificate public parameters and exact Owner')
    $bad=Copy-Object $key;$bad.modulus_b64=[Convert]::ToBase64String([byte[]]@(1,2,3,4))
    Must-Refuse {Assert-OwnerEnrollmentPublicKey $bad $parameters $owner $sid} 'thumbprint text cannot substitute a different public key'
    $bad=Copy-Object $key;$bad.approver_windows_sid='S-1-5-21-1-2-3-1002'
    Must-Refuse {Assert-OwnerEnrollmentPublicKey $bad $parameters $owner $sid} 'different Windows Owner refused'
    $bad=Copy-Object $key;$bad.purposes+=@('customer-installation-release')
    Must-Refuse {Assert-OwnerEnrollmentPublicKey $bad $parameters $owner $sid} 'factory authority is not silently added to update key'

    $product=Join-Path $temp 'product';New-Item -ItemType Directory -Path (Join-Path $product 'windows') -Force|Out-Null
    $rows=@()
    foreach($relative in @('docker-compose.yml','windows/Backup TOEFL House ERP.ps1','windows/Update TOEFL House ERP.ps1')){
        $p=Join-Path $product $relative;[IO.File]::WriteAllText($p,'already-authenticated-host-code-'+$relative,[Text.UTF8Encoding]::new($false))
        $rows += [pscustomobject]@{path=$relative;new_sha256=(Get-OwnerHostSha $p);size_bytes=(Get-Item -LiteralPath $p).Length}
    }
    $sourceRevision='5'*40;$targetRevision='e'*40;$image='sha256:'+('a'*64)
    $release=[pscustomobject]@{product='TOEFL House ERP';release_status='PRODUCTION RELEASE';production_authorization='AUTHORIZED';
        version='institute-corrected-fixture';source_revision=$targetRevision;image=[pscustomobject]@{config_digest='sha256:'+('f'*64);runtime_id=$image};
        legacy_bridge=[pscustomobject]@{source_revision=$sourceRevision};host_service=[pscustomobject]@{files=$rows}}
    $policy=[pscustomobject]@{transition=[pscustomobject]@{target_version=$release.version;target_revision=$targetRevision;target_image_id=$image}}
    $record=[pscustomobject]@{schema_version=1;document_type='toefl-house-erp-installed-image';provenance='signed-update';image_id=$image;
        source_revision=$targetRevision;release_version=$release.version;original_release_revision=$sourceRevision}
    $journal=[pscustomobject]@{schema_version=1;document_type='toefl-house-erp-update-journal';phase='completed';version=$release.version;transaction_id='9'*32}
    $state=Assert-OwnerCompletedReleaseState $product $release $policy $record $journal
    Assert-True ($state.RuntimeId -ceq $image) 'completed target retains actual OCI identity'
    $passed.Add('exact completed target reopens without another update approval')
    $bad=Copy-Object $journal;$bad.phase='applying'
    Must-Refuse {Assert-OwnerCompletedReleaseState $product $release $policy $record $bad} 'incomplete update cannot take completed no-op path'
    $bad=Copy-Object $record;$bad.provenance='factory'
    Must-Refuse {Assert-OwnerCompletedReleaseState $product $release $policy $bad $journal} 'factory record is not promoted to completed update'
    $bad=Copy-Object $record;$bad.image_id='sha256:'+('b'*64)
    Must-Refuse {Assert-OwnerCompletedReleaseState $product $release $policy $bad $journal} 'wrong recorded image is not accepted as already installed'
    $bad=Copy-Object $release;$bad.host_service.files[0].path='data/secrets/db.env'
    Must-Refuse {Assert-OwnerCompletedReleaseState $product $bad $policy $record $journal} 'no-op host plan cannot inspect a credential path'
    $changed=Join-Path $product 'docker-compose.yml';[IO.File]::AppendAllText($changed,'unknown')
    Must-Refuse {Assert-OwnerCompletedReleaseState $product $release $policy $record $journal} 'changed host bytes refuse no-op without overwrite'

    # Test only the later-added rollback orchestration, not the eight previously
    # passed transaction or transport cases. All side effects are mocked.
    $errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $SourceRoot 'product/windows/Update TOEFL House ERP.ps1'),[ref]$null,[ref]$errors)
    if($errors.Count){throw 'Updater syntax invalid.'}
    $fn=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name-ceq'Restore-OwnerNonmigratingCode'})
    if($fn.Count-ne1){throw 'Rollback function missing.'};. ([scriptblock]::Create($fn[0].Extent.Text))
    $script:DatabaseIdentitySHA256='d'*64;$script:MockDbIdentity=$script:DatabaseIdentitySHA256;$script:UndoCalls=0;$script:TagCalls=0
    function Get-PreservedDatabaseIdentity{return $script:MockDbIdentity}
    function Undo-OwnerHostServiceTransaction($t){$script:UndoCalls++;$t.Phase='rolled-back'}
    function Invoke-DockerVerbose($args){$script:TagCalls++;return 0}
    function Invoke-UpdateStart($id){return $true}
    function Wait-ForApplication($tries){return $true}
    function Set-JournalState($phase,$version){$script:FinalJournalPhase=$phase;$script:FinalJournalVersion=$version}
    function Save-Result{param($Status,$Section,$Key,$Version)$script:ResultStatus=$Status}
    $previous='sha256:'+('c'*64)
    $check=[pscustomobject]@{Version='fixture-target';Installed=[pscustomobject]@{version='ci-fixture-source';image_id=$previous};
        Response=[pscustomobject]@{plan=[pscustomobject]@{database_migration='none';reversible=$true}}}
    $script:HostTransaction=[pscustomobject]@{Phase='committed'}
    Restore-OwnerNonmigratingCode $check $previous ([pscustomobject]@{status='succeeded'})
    Assert-True ($script:FinalJournalPhase -ceq 'idle' -and $script:FinalJournalVersion -ceq 'ci-fixture-source' -and $script:ResultStatus -ceq 'rolled-back') 'prior factory daily Start remains usable after audited code rollback'
    $passed.Add('successful code-only rollback records idle prior state plus rollback result')
    $before=$script:TagCalls;$script:MockDbIdentity='0'*64
    Must-Refuse {Restore-OwnerNonmigratingCode $check $previous ([pscustomobject]@{status='succeeded'})} 'changed database identity blocks automatic rollback'
    Assert-True ($script:TagCalls-eq$before) 'changed DB triggered no retag'
    $script:MockDbIdentity=$script:DatabaseIdentitySHA256;$bad=Copy-Object $check;$bad.Response.plan.database_migration='supported'
    Must-Refuse {Restore-OwnerNonmigratingCode $bad $previous ([pscustomobject]@{status='succeeded'})} 'migrating release cannot use image-only rollback'
    Must-Refuse {Restore-OwnerNonmigratingCode $check $previous ([pscustomobject]@{status='failed'})} 'unknown apply outcome cannot claim safe code rollback'
    Must-Refuse {Restore-OwnerNonmigratingCode $check ('sha256:'+('8'*64)) ([pscustomobject]@{status='succeeded'})} 'rollback must use exact authorized prior image'
    [ordered]@{status='PASS_NEW_OWNER_UPDATE_COMPLETION_PROBE';checks=$passed.Count;results=@($passed);docker_or_database_access=$false;keys_certificates_or_signatures_created=$false}|ConvertTo-Json -Depth 4 -Compress
} finally {
    $resolved=[IO.Path]::GetFullPath($temp);$base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)-and
        [IO.Path]::GetFileName($resolved)-cmatch'^th-owner-completion-unit-[0-9a-f]{32}$'-and
        -not((Get-Item -LiteralPath $resolved -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }else{throw 'Refused cleanup outside exact new completion fixture.'}
}
