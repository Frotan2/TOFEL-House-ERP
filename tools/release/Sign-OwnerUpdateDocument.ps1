# Native signer for an explicitly enrolled existing Windows publisher key.
# It exports public parameters only; no new, recovery or factory key is opened.
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$SignaturePath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9A-Fa-f]{40}$')][string]$CertificateThumbprint,
    [Parameter(Mandatory=$true)][ValidateSet(
        'toefl-house-erp-update-signature',
        'toefl-house-erp-owner-update-policy-signature',
        'toefl-house-erp-owner-update-approval-signature',
        'toefl-house-erp-host-servicing-bootstrap-signature',
        'toefl-house-erp-owner-update-enrollment-signature'
    )][string]$DocumentType,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$')][string]$KeyId='th-owner-c7-20261121',
    [string]$PublicParametersPath
)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $SignaturePath) { throw 'A signature already exists. Do not overwrite approval evidence.' }
$inputFile=Get-Item -LiteralPath $InputPath -Force
if ($inputFile.PSIsContainer -or ($inputFile.Attributes-band[IO.FileAttributes]::ReparsePoint) -or $inputFile.Length-lt2 -or $inputFile.Length-gt1048576) { throw 'Refused document input.' }
$bytes=[IO.File]::ReadAllBytes($inputFile.FullName)
$strictUtf8=New-Object Text.UTF8Encoding($false,$true)
$doc=ConvertFrom-Json -InputObject $strictUtf8.GetString($bytes)
if ($doc.schema_version-ne1 -or -not $doc.document_type) { throw 'Unsupported signed document.' }
$expected=@{
    'toefl-house-erp-update-signature'='toefl-house-erp-update'
    'toefl-house-erp-owner-update-policy-signature'='toefl-house-erp-owner-update-policy'
    'toefl-house-erp-owner-update-approval-signature'='toefl-house-erp-owner-update-approval'
    'toefl-house-erp-host-servicing-bootstrap-signature'='toefl-house-erp-host-servicing-bootstrap'
    'toefl-house-erp-owner-update-enrollment-signature'='toefl-house-erp-owner-update-enrollment'
}
if ($doc.document_type-cne$expected[$DocumentType]) { throw 'Document and signature purposes differ.' }
$cert=Get-Item -LiteralPath ('Cert:\CurrentUser\My\'+$CertificateThumbprint.ToUpperInvariant())
$now=[DateTime]::UtcNow
if (-not $cert.HasPrivateKey -or $cert.NotBefore.ToUniversalTime()-gt$now -or $cert.NotAfter.ToUniversalTime()-lt$now) { throw 'The selected existing publisher key is unavailable or outside validity.' }
$eku=@($cert.Extensions|Where-Object{$_.Oid.Value -eq '2.5.29.37'})
if ($eku.Count -ne 1 -or @($eku[0].EnhancedKeyUsages|Where-Object{$_.Value -eq '1.3.6.1.5.5.7.3.3'}).Count -ne 1) { throw 'The selected certificate is not a code-signing publisher.' }
$rsa=$null;$publicRsa=$null
try {
    $rsa=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($cert)
    $publicRsa=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($cert)
    if (-not $rsa -or $rsa.KeySize-lt3072) { throw 'Publisher must use an existing RSA key of at least 3072 bits.' }
    $proof=$rsa.SignData($bytes,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
    if (-not $publicRsa.VerifyData($bytes,$proof,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)) { throw 'Native signature self-verification failed.' }
    $envelope=[ordered]@{schema_version=1;document_type=$DocumentType;algorithm='rsa-pkcs1v15-sha256';key_id=$KeyId;signature_b64=[Convert]::ToBase64String($proof)}
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($SignaturePath),($envelope|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
    if ($PublicParametersPath) {
        if (Test-Path -LiteralPath $PublicParametersPath) { throw 'Public parameter output already exists; preserve it.' }
        $pub=$publicRsa.ExportParameters($false)
        $parameters=[ordered]@{key_id=$KeyId;algorithm='rsa-pkcs1v15-sha256';publisher_thumbprint=$cert.Thumbprint.ToUpperInvariant();modulus_b64=[Convert]::ToBase64String($pub.Modulus);exponent_b64=[Convert]::ToBase64String($pub.Exponent);not_before_utc=$cert.NotBefore.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');not_after_utc=$cert.NotAfter.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')}
        [IO.File]::WriteAllText([IO.Path]::GetFullPath($PublicParametersPath),($parameters|ConvertTo-Json -Compress),(New-Object Text.UTF8Encoding($false)))
    }
    [ordered]@{status='SIGNED_AND_NATIVE_RSA_VERIFIED';document_type=$doc.document_type;key_id=$KeyId;publisher_thumbprint=$cert.Thumbprint.ToUpperInvariant();private_key_exported=$false;new_key_generated=$false}|ConvertTo-Json -Compress
} finally {if($rsa){$rsa.Dispose()};if($publicRsa){$publicRsa.Dispose()}}
