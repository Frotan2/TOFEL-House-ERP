param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
. (Join-Path $SourceRoot 'product/windows/Owner Host Servicing.ps1')
$file=Join-Path $SourceRoot 'product/windows/Service Existing TOEFL House ERP.ps1'
$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$null,[ref]$errors)
if($errors.Count){throw 'Bootstrap syntax invalid.'}
$fn=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name-ceq'Copy-ServicingEnrollmentEvidence'})
if($fn.Count-ne1){throw 'Exact evidence copy helper missing.'};. ([scriptblock]::Create($fn[0].Extent.Text))
$temp=Join-Path ([IO.Path]::GetTempPath()) ('th-owner-evidence-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
$passed=New-Object Collections.Generic.List[string]
function Assert-True([bool]$Condition,[string]$Name){if(-not $Condition){throw ('Failed: '+$Name)}}
function Must-Refuse([scriptblock]$Action,[string]$Name){$no=$false;try{& $Action}catch{$no=$true};Assert-True $no $Name;$passed.Add($Name)}
try {
    $source=Join-Path $temp 'source';$history=Join-Path $temp 'history'
    New-Item -ItemType Directory -Path $source,$history|Out-Null
    $document=Join-Path $source 'enrollment.json';$signature=Join-Path $source 'enrollment.sig.json'
    # Plain identity fixtures only: no certificate/key/signature generation or
    # real production approval/enrollment takes place in this isolated check.
    [IO.File]::WriteAllText($document,'{"fixture":"document"}',[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($signature,'{"fixture":"signature-envelope"}',[Text.UTF8Encoding]::new($false))
    $docSHA=Get-OwnerHostSha $document;$sigSHA=Get-OwnerHostSha $signature
    Copy-ServicingEnrollmentEvidence $document $history 'enrollment.json' $docSHA
    # Simulate the exact newly reviewed crash point: the first audit file was
    # published, the second was not. Resume must retain the first exact file
    # and publish the absent second file, without replaying an update.
    Copy-ServicingEnrollmentEvidence $document $history 'enrollment.json' $docSHA
    Copy-ServicingEnrollmentEvidence $signature $history 'enrollment.sig.json' $sigSHA
    Assert-True ((Get-OwnerHostSha (Join-Path $history 'enrollment.json'))-ceq$docSHA) 'existing document exact'
    Assert-True ((Get-OwnerHostSha (Join-Path $history 'enrollment.sig.json'))-ceq$sigSHA) 'absent signature evidence published'
    $passed.Add('resume after first evidence file was copied')
    Copy-ServicingEnrollmentEvidence $document $history 'enrollment.json' $docSHA
    Copy-ServicingEnrollmentEvidence $signature $history 'enrollment.sig.json' $sigSHA
    $passed.Add('resume after both evidence files were copied')
    $saved=Join-Path $history 'enrollment.sig.json';[IO.File]::WriteAllText($saved,'unknown audit bytes')
    Must-Refuse {Copy-ServicingEnrollmentEvidence $signature $history 'enrollment.sig.json' $sigSHA} 'unknown existing audit evidence refuses overwrite'
    Assert-True ([IO.File]::ReadAllText($saved)-ceq'unknown audit bytes') 'unknown evidence preserved'
    Must-Refuse {Copy-ServicingEnrollmentEvidence $document $history 'enrollment.json' ('0'*64)} 'source evidence digest mismatch refuses'
    [ordered]@{status='PASS_NEW_OWNER_ENROLLMENT_EVIDENCE_CRASH_RESUME';checks=$passed.Count;results=@($passed);production_or_database_access=$false;private_keys_or_signatures_used=$false;prior_host_checks_repeated=$false}|ConvertTo-Json -Depth 4 -Compress
}finally{
    $resolved=[IO.Path]::GetFullPath($temp);$base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)-and[IO.Path]::GetFileName($resolved)-cmatch'^th-owner-evidence-unit-[0-9a-f]{32}$'-and
        -not((Get-Item -LiteralPath $resolved -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }else{throw 'Refused cleanup outside exact new evidence fixture.'}
}
