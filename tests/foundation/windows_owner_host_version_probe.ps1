param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
$file=Join-Path $SourceRoot 'product/windows/Update TOEFL House ERP.ps1'
$text=[IO.File]::ReadAllText($file)
$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$null,[ref]$errors)
if($errors.Count){throw 'Updated host script syntax is invalid.'}
if($text -notmatch "\`$script:HostUpdaterVersion = '2026\.11\.22'"){throw 'Actual numeric host version declaration is missing.'}
$fields=@([regex]::Matches($text,'(?m)^\s*host_updater_version\s*=\s*(.+)$'))
if($fields.Count-ne2-or @($fields|Where-Object{$_.Groups[1].Value.Trim() -cne '$script:HostUpdaterVersion'}).Count){throw 'Both engine requests must send host version, not the application label.'}
$fn=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name-ceq'ConvertTo-ReleaseSequence'})
if($fn.Count-ne1){throw 'Release sequence parser missing.'};. ([scriptblock]::Create($fn[0].Extent.Text))
if((ConvertTo-ReleaseSequence '2026.11.22') -ne 2026112200){throw 'Declared host version is not supported numeric protocol.'}
if($text -notmatch 'version = \$version' -or $text -notmatch "source_version -ceq \`$version"){throw 'Actual application label/legacy identity was rewritten.'}
[ordered]@{status='PASS_NEW_OWNER_HOST_VERSION_BINDING';checks=3;host_version='2026.11.22';request_fields=2;application_image_labels_rewritten=$false;docker_database_or_key_access=$false}|ConvertTo-Json -Compress
