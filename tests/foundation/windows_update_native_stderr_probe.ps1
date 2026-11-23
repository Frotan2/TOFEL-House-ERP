param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
$file=Join-Path $SourceRoot 'product/windows/Update TOEFL House ERP.ps1'
$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$null,[ref]$errors)
if($errors.Count){throw 'Updater syntax is invalid.'}
foreach($name in @('Invoke-Docker','Invoke-DockerVerbose')){
    $nodes=@($ast.FindAll({param($n)$n-is[Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name-ceq$name})
    if($nodes.Count-ne1){throw 'Actual native wrapper missing.'}
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('th-native-stderr-unit-'+[guid]::NewGuid().ToString('N'))
$originalPath=$env:PATH
New-Item -ItemType Directory -Path $temp|Out-Null
try {
    $source=Join-Path $temp 'NativeDockerFixture.cs'
    [IO.File]::WriteAllText($source,@'
using System;
public class NativeDockerFixture {
    public static int Main(string[] args) {
        if (args.Length != 1) return 19;
        if (args[0] == "progress") {
            Console.Out.WriteLine("stdout-before");
            Console.Error.WriteLine("Container synthetic-socketio Stopping");
            Console.Out.WriteLine("stdout-after");
            return 0;
        }
        if (args[0] == "failure") {
            Console.Error.WriteLine("synthetic native failure");
            return 7;
        }
        if (args[0] == "stdout") {
            Console.Out.WriteLine("{\"unchanged\":true}");
            return 0;
        }
        return 19;
    }
}
'@)
    $csc=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    & $csc /nologo /target:exe ('/out:'+(Join-Path $temp 'docker.exe')) $source
    if($LASTEXITCODE-ne0){throw 'Native fixture compilation failed.'}
    $env:PATH=$temp+';'+$originalPath
    $result=Invoke-Docker @('progress')
    if($result.Code-ne0-or $result.Output.Count-ne3-or
       $result.Output-cnotcontains'Container synthetic-socketio Stopping'-or
       $result.Output-cnotcontains'stdout-before'-or $result.Output-cnotcontains'stdout-after'-or
       @($result.Output|Where-Object{$_-isnot[string]}).Count-ne0-or $ErrorActionPreference-cne'Stop'){
        throw 'Successful native stderr progress was not captured without changing the caller error preference.'
    }
    $code=Invoke-DockerVerbose @('failure')
    if($code-ne7-or $ErrorActionPreference-cne'Stop'){throw 'Verbose transport hid the native failure exit code.'}
    $result=Invoke-Docker @('stdout')
    if($result.Code-ne0-or $result.Output.Count-ne1-or $result.Output[0]-cne'{"unchanged":true}'-or
       $ErrorActionPreference-cne'Stop'){throw 'Native stdout changed.'}
    [ordered]@{status='PASS_NEW_NATIVE_STDERR_TRANSPORT';checks=3;native_stderr_exit0_accepted=$true;native_stderr_exit7_preserved=$true;stdout_unchanged=$true;caller_error_preference_restored=$true;actual_docker_or_production_access=$false}|ConvertTo-Json -Compress
} finally {
    $env:PATH=$originalPath
    $resolved=[IO.Path]::GetFullPath($temp)
    $base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase)-and
       [IO.Path]::GetFileName($resolved)-cmatch'^th-native-stderr-unit-[0-9a-f]{32}$'-and
       -not((Get-Item -LiteralPath $resolved -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }else{throw 'Refused cleanup outside the exact new native fixture.'}
}
