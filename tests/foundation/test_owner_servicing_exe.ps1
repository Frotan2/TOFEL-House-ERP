# Focused native validation of the NEW existing-site installer entry only.
# No installer, application service, database, key or approval is executed.
param([string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputRoot) { $OutputRoot = Join-Path $sourceRoot '..\Validation\CustomerServicingNative' }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$dll = Join-Path $OutputRoot 'CustomerServicingEntry.dll'
$source = Join-Path $sourceRoot 'tools\release\windows\CustomerSetup.cs'
& $csc '/nologo' '/target:library' ('/out:'+$dll) '/r:System.Windows.Forms.dll' '/r:System.Drawing.dll' '/r:System.IO.Compression.dll' '/r:System.IO.Compression.FileSystem.dll' $source
if ($LASTEXITCODE -ne 0) { throw 'Native installer entry did not compile.' }
Add-Type -Path $dll
$env:PSExecutionPolicyPreference = 'Bypass'
$target = "C:\Users\O'Connor\AppData\Local\TOEFL House ERP\Customer"
$staged = "C:\Users\O'Connor\AppData\Local\.th-owner-update"
$exe = "C:\Users\O'Connor\Desktop\TOEFL House ERP Setup.exe"
$start = [CustomerSetup]::CreateServicingStartInfo($target,$staged,$exe)
if ($start.Arguments -match '-ExecutionPolicy') { throw 'Servicing must honor Windows execution policy.' }
if ($start.EnvironmentVariables.ContainsKey('PSExecutionPolicyPreference')) { throw 'Transient policy override inherited.' }
if ($start.EnvironmentVariables.ContainsKey('PSModulePath')) { throw 'Caller module path inherited.' }
if ($start.UseShellExecute -or -not $start.CreateNoWindow) { throw 'Servicing process must stay hidden and bounded.' }
if ($start.Arguments -notlike '*-OwnerApprovalAccepted*' -or $start.Arguments -notlike '*-TargetProductRoot*' -or $start.Arguments -notlike '*-OfflineBundleRoot*' -or $start.Arguments -notlike '*-BootstrapRoot*') { throw 'Servicing arguments incomplete.' }
$prefix = '-Command "'
$position = $start.Arguments.IndexOf($prefix)
if ($position -lt 0 -or -not $start.Arguments.EndsWith('"')) { throw 'Malformed PowerShell argument boundary.' }
$command = $start.Arguments.Substring($position+$prefix.Length)
$command = $command.Substring(0,$command.Length-1)
$tokens = $null; $parseErrors = $null
$null = [Management.Automation.Language.Parser]::ParseInput($command,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Servicing command does not parse for an apostrophe-containing Windows profile.' }
if (($command.Split(@('Get-AuthenticodeSignature'),[StringSplitOptions]::None).Count-1) -ne 3) { throw 'Existing launcher, setup and bridge publisher checks must all precede execution.' }
if ($command.IndexOf('Get-AuthenticodeSignature') -gt $command.IndexOf('& ')) { throw 'New script execution precedes publisher verification.' }
$fixture = Join-Path $OutputRoot 'empty-payload-fixture'
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
if ([CustomerSetup]::HasServicingPayload($fixture)) { throw 'Empty factory payload must not service an existing site.' }
$bootstrap = Join-Path $fixture 'product\updates\bootstrap'
$release = Join-Path $fixture 'product\release'
New-Item -ItemType Directory -Path $bootstrap,$release -Force | Out-Null
foreach ($n in @('Service Existing TOEFL House ERP.ps1','Update TOEFL House ERP.ps1','Owner Host Servicing.ps1','bootstrap.json','bootstrap.sig.json','enrollment.json','enrollment.sig.json')) { [IO.File]::WriteAllText((Join-Path $bootstrap $n),'') }
foreach ($n in @('index.json','update.json','update.json.sig','toefl-house-erp-app.tar')) { [IO.File]::WriteAllText((Join-Path $release $n),'') }
if (-not [CustomerSetup]::HasServicingPayload($fixture)) { throw 'Complete entry inventory not recognized.' }
[IO.File]::Delete((Join-Path $bootstrap 'enrollment.sig.json'))
if ([CustomerSetup]::HasServicingPayload($fixture)) { throw 'Unsigned enrollment must not qualify for the servicing entry.' }
[ordered]@{status='PASS_NEW_NATIVE_EXISTING_SITE_ENTRY';checks=9;compiler='Windows .NET Framework 4 CSC';apostrophe_profile_command_parsed=$true;three_publisher_checks_before_execution=$true;execution_policy_override_absent=$true;missing_signed_enrollment_refused=$true;application_or_installer_executed=$false;database_or_services_or_keys_changed=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $OutputRoot 'result.json') -Encoding utf8
Get-Content -LiteralPath (Join-Path $OutputRoot 'result.json') -Raw
