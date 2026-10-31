# PROVIDER ONLY — build a small, publisher-signed TOEFL House Online Setup.
# The program downloads ONE immutable, already signed offline installer from a
# tagged official GitHub Release, verifies bytes and publisher, then launches.
# This does not release, upload, approve production, or alter an Owner site.
param(
    [Parameter(Mandatory=$true)][string]$SignedOfflineSetup,
    [Parameter(Mandatory=$true)][string]$ReleaseTag,
    [Parameter(Mandatory=$true)][string]$OutputExe,
    [Parameter(Mandatory=$true)][string]$SigningCertificateThumbprint,
    [Parameter(Mandatory=$true)][string]$TimestampServer
)
$ErrorActionPreference = 'Stop'
$staging = $null
try {
    if ($ReleaseTag -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$' -or
        $ReleaseTag -match '(^|[.])\.\.?($|[.])' -or
        $SigningCertificateThumbprint -notmatch '^[A-Fa-f0-9]{40}$' -or
        $TimestampServer -notmatch '^http://[A-Za-z0-9.-]+(?::[0-9]{2,5})?(/[^\s]*)?$') {
        throw 'A safe release tag, publisher certificate SHA-1 thumbprint and approved Authenticode timestamp server are required.'
    }
    $signed = (Get-Item -LiteralPath $SignedOfflineSetup -ErrorAction Stop)
    if ($signed.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked release input is forbidden.' }
    if ($signed.Length -lt 1 -or $signed.Length -ge 2147483648) {
        throw 'Offline release asset must be below the official GitHub Release 2 GiB per-asset limit.'
    }
    $sig = Get-AuthenticodeSignature -LiteralPath $signed.FullName
    if ($sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate -or
        $null -eq $sig.TimeStamperCertificate -or
        $sig.SignerCertificate.Thumbprint -ine $SigningCertificateThumbprint) {
        throw 'The offline installer must already have a trusted, timestamped signature from the selected publisher.'
    }
    $certificates = @(Get-ChildItem 'Cert:\CurrentUser\My', 'Cert:\LocalMachine\My' -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -ieq $SigningCertificateThumbprint })
    if ($certificates.Count -ne 1 -or -not $certificates[0].HasPrivateKey -or
        $certificates[0].NotBefore -gt [DateTime]::UtcNow -or
        $certificates[0].NotAfter -le [DateTime]::UtcNow -or
        -not @($certificates[0].EnhancedKeyUsageList |
            Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' }).Count) {
        throw 'An installed, valid code-signing certificate with its private key is required.'
    }
    $output = [IO.Path]::GetFullPath($OutputExe)
    if ([IO.Path]::GetExtension($output) -ine '.exe' -or
        (Test-Path -LiteralPath $output) -or $output -ieq $signed.FullName) {
        throw 'Choose a new online EXE output location. Existing release artifacts are never overwritten.'
    }
    [IO.Directory]::CreateDirectory((Split-Path -Parent $output)) | Out-Null
    $staging = Join-Path (Split-Path -Parent $output) ('.online-setup-' + [guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($staging) | Out-Null
    $plan = Join-Path $staging 'online-plan.txt'
    $hash = (Get-FileHash -LiteralPath $signed.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $uri = 'https://github.com/Frotan2/TOFEL-House-ERP/releases/download/' +
        $ReleaseTag + '/TOEFL-House-ERP-Setup.exe'
    $content = @('TH_ONLINE_PLAN_V1', $uri, $hash, [string]$signed.Length,
        $SigningCertificateThumbprint.ToUpperInvariant()) -join [Environment]::NewLine
    [IO.File]::WriteAllText($plan, ($content + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
    $source = Join-Path $PSScriptRoot 'windows\OnlineSetup.cs'
    $csc = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64/v4.0.30319/csc.exe'
    if (-not (Test-Path -LiteralPath $source) -or -not (Test-Path -LiteralPath $csc)) {
        throw 'The official online setup source and Windows .NET compiler are required on the provider PC.'
    }
    $temporaryExe = Join-Path $staging 'TOEFL-House-ERP-Online-Setup.exe'
    $resourceArg = '/resource:' + $plan + ',TOEFLHouse.OnlinePlan'
    & $csc /nologo /target:winexe /platform:x64 ("/out:" + $temporaryExe) /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $resourceArg $source
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporaryExe -PathType Leaf)) {
        throw 'The small Windows online setup failed to compile.'
    }
    $signedBootstrap = Set-AuthenticodeSignature -LiteralPath $temporaryExe -Certificate $certificates[0] -HashAlgorithm SHA256 -TimestampServer $TimestampServer
    if ($signedBootstrap.Status -ne 'Valid') { throw 'Online installer Authenticode signing failed.' }
    $verify = Get-AuthenticodeSignature -LiteralPath $temporaryExe
    if ($verify.Status -ne 'Valid' -or $verify.SignerCertificate.Thumbprint -ine $SigningCertificateThumbprint -or
        $null -eq $verify.TimeStamperCertificate) { throw 'Online installer signing identity or timestamp mismatch.' }
    if ((Get-Item -LiteralPath $temporaryExe).Length -gt 20MB) {
        throw 'The online bootstrap exceeded its 20 MB small-installer design limit.'
    }
    [IO.File]::Move($temporaryExe, $output)
    [IO.File]::WriteAllText($output + '.sha256',
        ((Get-FileHash -LiteralPath $output).Hash.ToLowerInvariant() + '  ' + [IO.Path]::GetFileName($output) + [Environment]::NewLine))
    Write-Host ('Online setup built and signed: ' + $output)
    Write-Host ('Published offline target must be: ' + $uri)
    Write-Host ('Required signed offline asset SHA-256: ' + $hash)
    Write-Host 'This does not upload a release or authorize production use.'
} finally {
    if ($staging -and (Test-Path -LiteralPath $staging)) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
