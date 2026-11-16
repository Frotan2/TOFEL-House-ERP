param([string]$PinnedArchive)

$ErrorActionPreference = 'Stop'
$source = Join-Path (Join-Path $PSScriptRoot '..\..') 'tools\release\windows'
. (Join-Path $source 'Private HTTPS Setup.ps1') -FunctionsOnly

function Expect-Refusal([scriptblock]$Action, [string]$Pattern) {
    try { & $Action }
    catch {
        if ($_.Exception.Message -notlike $Pattern) { throw }
        return
    }
    throw 'The private HTTPS check accepted an invalid input.'
}

$tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')
$root = Join-Path $tempRoot ('toefl-https-test-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
try {
    $config = ConvertTo-PrivateHttpsConfiguration 'erp.staff.internal' '192.168.15.10' '192.168.16.0/26' (Join-Path $source 'Caddyfile.template')
    if ($config -notmatch '(?m)^\s*bind 192\.168\.15\.10$' -or
        $config -notmatch '(?m)^\s*@excluded not remote_ip 192\.168\.16\.0/26$') {
        throw 'The configuration did not retain its two separate address restrictions.'
    }
    $archive = Join-Path $root 'mock.zip'
    [IO.File]::WriteAllText($archive, 'This is deliberately not the approved ZIP.')
    Expect-Refusal { Save-PrivateProxyFiles $root $archive $config } '*failed its release checksum*'
    if (@(Get-ChildItem -LiteralPath $root -Force).Count -ne 1) {
        throw 'An unapproved archive created output.'
    }
    $protected = Join-Path $root 'marked.exe'
    [IO.File]::WriteAllText($protected, 'Only a synthetic empty executable name.')
    Set-Content -LiteralPath $archive -Stream Zone.Identifier -Value "[ZoneTransfer]`r`nZoneId=4"
    Set-ProxyDownloadMarker $protected @($archive)
    if ((Get-Content -LiteralPath $protected -Stream Zone.Identifier -Raw) -notmatch 'ZoneId=4') {
        throw 'Proxy preparation stripped the existing restricted download mark.'
    }
    $certPath = Join-Path $root 'root.crt'
    [IO.File]::WriteAllText($certPath, "-----BEGIN PRIVATE KEY-----`nZmFrZQ==`n-----END PRIVATE KEY-----`n")
    Expect-Refusal { Read-PrivateHttpsPublicCertificate $certPath } '*exactly one public PEM certificate*'
    $key = [Security.Cryptography.RSACng]::new(2048)
    try {
        $request = New-Object Security.Cryptography.X509Certificates.CertificateRequest(
            'CN=ERP synthetic test CA', $key, [Security.Cryptography.HashAlgorithmName]::SHA256,
            [Security.Cryptography.RSASignaturePadding]::Pkcs1)
        [void]$request.CertificateExtensions.Add(
            [Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($true,$false,0,$true))
        $ca = $request.CreateSelfSigned([DateTimeOffset]::Now.AddMinutes(-5),[DateTimeOffset]::Now.AddDays(1))
        try { $certBytes = $ca.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert) }
        finally { $ca.Dispose() }
        [IO.File]::WriteAllText($certPath, "-----BEGIN CERTIFICATE-----`n" +
            [Convert]::ToBase64String($certBytes) + "`n-----END CERTIFICATE-----`n")
        $actual = Read-PrivateHttpsPublicCertificate $certPath
        if ([Convert]::ToBase64String($actual) -cne [Convert]::ToBase64String($certBytes)) {
            throw 'Public export changed the certificate.'
        }
    } finally { $key.Dispose() }

    if ($PinnedArchive) {
        $saved = Save-PrivateProxyFiles $root $PinnedArchive $config
        $exe = Join-Path $saved 'caddy.exe'
        if (![IO.File]::Exists($exe) -or ([IO.File]::ReadAllText((Join-Path $saved 'Caddyfile'))) -cne $config -or
            (Get-Content -LiteralPath $exe -Stream Zone.Identifier -Raw) -notmatch 'ZoneId=[34]') {
            throw 'The real archive did not stage the executable, exact configuration and Windows download marker.'
        }
        Expect-Refusal { Save-PrivateProxyFiles $root $PinnedArchive $config } '*already exists*'
        [IO.File]::Delete($exe)
        [IO.File]::Delete((Join-Path $saved 'Caddyfile'))
        [IO.Directory]::Delete($saved)
    }
    'Private HTTPS preparation and public certificate checks passed.'
} finally {
    foreach ($name in @('root.crt','marked.exe','mock.zip')) { [IO.File]::Delete((Join-Path $root $name)) }
    if (@(Get-ChildItem -LiteralPath $root -Force).Count -eq 0) { [IO.Directory]::Delete($root) }
}
