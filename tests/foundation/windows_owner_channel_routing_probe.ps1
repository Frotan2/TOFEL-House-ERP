param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
$file=Join-Path $SourceRoot 'product/windows/Update TOEFL House ERP.ps1'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$null,[ref]$errors)
if($errors.Count){throw 'Updated host script syntax is invalid.'}
$fn=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name-ceq'Get-EngineChannelRelativePath'})
if($fn.Count-ne1){throw 'Exact channel routing helper is missing.'}
. ([scriptblock]::Create($fn[0].Extent.Text))
$text=[IO.File]::ReadAllText($file)
if($text -notmatch '(?m)^\s*channel = Get-EngineChannelRelativePath\s*$'){throw 'Engine request does not use the selected channel route.'}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('th-owner-channel-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
$passed=New-Object Collections.Generic.List[string]
function Assert-Equal([string]$Actual,[string]$Expected,[string]$Name){if($Actual-cne$Expected){throw ('Failed: '+$Name)};$passed.Add($Name)}
function Must-Refuse([scriptblock]$Action,[string]$Name){$refused=$false;try{& $Action}catch{$refused=$true};if(-not$refused){throw ('Failed: '+$Name)};$passed.Add($Name)}
try {
    $productRoot=$temp
    $ownerChannelPath=Join-Path $productRoot 'data/updates/owner-channel.json'
    $channelPath=Join-Path $productRoot 'updates/channel.json'
    $script:ServicingRuntime=$null
    Assert-Equal (Get-EngineChannelRelativePath) 'updates/channel.json' 'legacy request retains exact factory channel'
    $script:ServicingRuntime=[pscustomobject]@{Root='authenticated-runtime-fixture'}
    Assert-Equal (Get-EngineChannelRelativePath) 'updates/channel.json' 'absent Owner channel retains factory selection'
    New-Item -ItemType Directory -Path (Split-Path -Parent $ownerChannelPath)-Force|Out-Null
    [IO.File]::WriteAllText($ownerChannelPath,'isolated-channel-fixture')
    $channelPath=$ownerChannelPath
    Assert-Equal (Get-EngineChannelRelativePath) 'data/updates/owner-channel.json' 'authenticated Owner request reads selected Owner channel'
    $script:ServicingRuntime=$null
    Must-Refuse {Get-EngineChannelRelativePath} 'Owner route without authenticated runtime refuses'
    $script:ServicingRuntime=[pscustomobject]@{Root='authenticated-runtime-fixture'}
    [IO.File]::Delete($ownerChannelPath)
    Must-Refuse {Get-EngineChannelRelativePath} 'disappeared selected Owner channel refuses'
    $channelPath=Join-Path $productRoot 'unexpected/channel.json'
    Must-Refuse {Get-EngineChannelRelativePath} 'arbitrary channel path refuses'
    [ordered]@{status='PASS_NEW_OWNER_CHANNEL_ROUTING';checks=$passed.Count;results=@($passed);factory_channel_file_or_settings_changed=$false;production_or_docker_or_keys_accessed=$false}|ConvertTo-Json -Depth 4 -Compress
} finally {
    $resolved=[IO.Path]::GetFullPath($temp)
    $base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)-and[IO.Path]::GetFileName($resolved)-cmatch'^th-owner-channel-unit-[0-9a-f]{32}$'-and-not((Get-Item -LiteralPath $resolved -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }else{throw 'Refused cleanup outside exact new channel fixture.'}
}
