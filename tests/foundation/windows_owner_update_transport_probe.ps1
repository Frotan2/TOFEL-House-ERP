param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
$updater=Join-Path $SourceRoot 'product/windows/Update TOEFL House ERP.ps1'
$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($updater,[ref]$null,[ref]$parseErrors)
if($parseErrors.Count){throw 'Updater syntax is invalid.'}
foreach($name in @('Save-OfflineFile','Get-AuthorizedRuntimeImageId','Get-Text')) {
    $functions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name -ceq $name})
    if($functions.Count -ne 1){throw 'Expected one trusted source function.'}
    . ([scriptblock]::Create($functions[0].Extent.Text))
}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('th-owner-transport-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
$passed=New-Object Collections.Generic.List[string]
function Assert-True([bool]$Condition,[string]$Name){if(-not $Condition){throw ('Failed: '+$Name)}}
function Must-Refuse([scriptblock]$Action,[string]$Name){$refused=$false;try{& $Action}catch{$refused=$true};Assert-True $refused $Name;$passed.Add($Name)}
try {
    $updatesRoot=Join-Path $temp 'updates';$offlineInbox=Join-Path $temp 'offline';$run=Join-Path $temp 'run'
    New-Item -ItemType Directory -Path $updatesRoot,$offlineInbox,$run|Out-Null
    $bytes=New-Object byte[] 8192
    for($i=0;$i-lt$bytes.Length;$i++){$bytes[$i]=[byte]($i%251)}
    $source=Join-Path $offlineInbox 'toefl-house-erp-app.tar'
    [IO.File]::WriteAllBytes($source,$bytes)
    [IO.File]::WriteAllText((Join-Path $offlineInbox 'toefl-house-erp-host.zip'),'fixture-host-code')
    $script:ServicingRuntime=$null
    Must-Refuse {Save-OfflineFile 'toefl-house-erp-host.zip' (Join-Path $run 'legacy-host.zip') 1024} 'legacy transport does not acquire a host-code exception'
    Must-Refuse {Save-OfflineFile '../data/secrets/db.env' (Join-Path $run 'unsafe') 1024} 'offline asset traversal refused'
    $legacy=Join-Path $run 'legacy.tar'
    Save-OfflineFile 'toefl-house-erp-app.tar' $legacy 16384
    [IO.File]::AppendAllText($legacy,'separate')
    Assert-True ((Get-Item -LiteralPath $source).Length -eq 8192) 'legacy ordinary copy remains separate'
    $passed.Add('legacy copy behavior preserved')
    $script:ServicingRuntime=[pscustomobject]@{Root='authenticated-runtime-fixture'}
    $linked=Join-Path $run 'owner.tar'
    Save-OfflineFile 'toefl-house-erp-app.tar' $linked 16384
    Assert-True (-not ((Get-Item -LiteralPath $linked -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)) 'archive hardlink is not a reparse point'
    [IO.File]::AppendAllText($linked,'linked')
    Assert-True ((Get-Item -LiteralPath $source).Length -eq (8192+6)) 'one physical archive backs both ordinary names'
    $passed.Add('same-volume ordinary hardlink avoids duplicate image storage')
    Must-Refuse {Save-OfflineFile 'toefl-house-erp-app.tar' (Join-Path $run 'too-large.tar') 1} 'size bound checked before linking'
    Save-OfflineFile 'toefl-house-erp-host.zip' (Join-Path $run 'owner-host.zip') 1024
    Assert-True ([IO.File]::ReadAllText((Join-Path $run 'owner-host.zip')) -ceq 'fixture-host-code') 'new opt-in host archive copied exactly'
    $passed.Add('host transport exception requires authenticated runtime')
    $config='sha256:'+('1'*64);$oci='sha256:'+('2'*64)
    Assert-True ((Get-AuthorizedRuntimeImageId ([pscustomobject]@{config_digest=$config;runtime_id=$oci})) -ceq $oci) 'runtime OCI identity selected'
    Assert-True ((Get-AuthorizedRuntimeImageId ([pscustomobject]@{config_digest=$config})) -ceq $config) 'normal config identity preserved'
    $passed.Add('runtime identity remains distinct from config identity')
    $entry=Get-Text 'messages' 'warning.separate_key_custody_pending'
    Assert-True ($entry.en -match 'not yet been verified') 'honest custody warning before catalog commit'
    $passed.Add('pending custody warning renders before old catalog replacement')
    [ordered]@{status='PASS_NEW_OWNER_UPDATE_TRANSPORT_PROBE';checks=$passed.Count;results=@($passed);docker_or_database_access=$false;keys_or_signatures_created=$false}|ConvertTo-Json -Depth 4 -Compress
} finally {
    $resolved=[IO.Path]::GetFullPath($temp)
    $base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)-and
        [IO.Path]::GetFileName($resolved)-cmatch '^th-owner-transport-unit-[0-9a-f]{32}$'-and
        -not((Get-Item -LiteralPath $resolved -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }else{throw 'Refused cleanup outside exact new transport fixture.'}
}
