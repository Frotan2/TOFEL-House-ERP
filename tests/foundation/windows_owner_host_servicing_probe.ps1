param([string]$SourceRoot=(Join-Path $PSScriptRoot '../..'))
$ErrorActionPreference='Stop'
. (Join-Path $SourceRoot 'product/windows/Owner Host Servicing.ps1')
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('th-owner-host-unit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary|Out-Null
$passed=New-Object Collections.Generic.List[string]
function Assert-True([bool]$Condition,[string]$Label) { if (-not $Condition) { throw ('Failed: '+$Label) } }
function Must-Refuse([scriptblock]$Action,[string]$Label) {
    $refused=$false
    try { & $Action } catch { $refused=$true }
    Assert-True $refused $Label
    $passed.Add($Label)
}
function Fixture([string]$Name,[string[]]$Paths=@('docker-compose.yml')) {
    $root=Join-Path $temporary $Name
    $product=Join-Path $root 'product'
    $work=Join-Path $product 'data/updates/runs/20261121T000000Z-aaaaaaaa'
    $payload=Join-Path $root 'payload'
    New-Item -ItemType Directory -Path $product,$work,$payload -Force|Out-Null
    $rows=@()
    foreach ($relative in $Paths) {
        $old=Join-Path $product $relative;$new=Join-Path $payload $relative
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($old)),([IO.Path]::GetDirectoryName($new)) -Force|Out-Null
        [IO.File]::WriteAllText($old,'old-'+$relative,[Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText($new,'new-'+$relative,[Text.UTF8Encoding]::new($false))
        $rows += [pscustomobject]@{path=$relative;old_sha256=(Get-OwnerHostSha $old);new_sha256=(Get-OwnerHostSha $new);size_bytes=(Get-Item -LiteralPath $new).Length}
    }
    $archive=Join-Path $root 'toefl-house-erp-host.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory($payload,$archive)
    # ZipFile uses a Windows path separator on some .NET runtimes. Rebuild a
    # fixed forward-slash manifest archive exactly as the production builder.
    $members=@($rows|ForEach-Object{[pscustomobject]@{Name=$_.path;Bytes=[IO.File]::ReadAllBytes((Join-Path $payload $_.path))}})
    [IO.File]::Delete($archive)
    $zip=[IO.Compression.ZipFile]::Open($archive,[IO.Compression.ZipArchiveMode]::Create)
    try {foreach($m in $members){$entry=$zip.CreateEntry($m.Name);$stream=$entry.Open();try{$stream.Write($m.Bytes,0,$m.Bytes.Length)}finally{$stream.Dispose()}}}finally{$zip.Dispose()}
    $plan=[pscustomobject]@{archive='toefl-house-erp-host.zip';sha256=(Get-OwnerHostSha $archive);size_bytes=(Get-Item -LiteralPath $archive).Length;files=$rows}
    return [pscustomobject]@{Product=$product;Work=$work;Archive=$archive;Plan=$plan}
}
try {
    Must-Refuse { Assert-OwnerHostOrdinaryPath $temporary '../data/secrets/db.env' } 'path traversal refused'
    $f=Fixture 'allowlist' @('data/secrets/db.env')
    Must-Refuse { New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('1'*32) } 'data or credential path refused'
    Assert-True ([IO.File]::ReadAllText((Join-Path $f.Product 'data/secrets/db.env')) -ceq 'old-data/secrets/db.env') 'credential fixture unchanged'
    $f=Fixture 'old-mismatch'
    $f.Plan.files[0].old_sha256='0'*64
    Must-Refuse { New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('2'*32) } 'unknown installed bytes refused'
    $f=Fixture 'commit'
    $t=New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('3'*32)
    Complete-OwnerHostServiceTransaction $t
    Assert-True ($t.Phase -ceq 'committed') 'commit recorded'
    Assert-True ((Get-OwnerHostSha (Join-Path $f.Product 'docker-compose.yml')) -ceq $f.Plan.files[0].new_sha256) 'new code exact'
    Undo-OwnerHostServiceTransaction $t
    Assert-True ($t.Phase -ceq 'rolled-back') 'rollback recorded'
    Assert-True ((Get-OwnerHostSha (Join-Path $f.Product 'docker-compose.yml')) -ceq $f.Plan.files[0].old_sha256) 'prior code exact'
    $passed.Add('exact commit and reverse rollback')
    $f=Fixture 'crash-intent'
    $t=New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('4'*32)
    $t.Phase='committing';$t.Files[0].CommitStarted=$true;Write-OwnerHostTransaction $t
    [IO.File]::Copy($t.Files[0].Staged,$t.Files[0].Target,$true)
    # Simulate process loss before Committed=true was persisted. Reload actual
    # on-disk journal; rollback must inspect intent plus exact current bytes.
    $restored=Get-Content -LiteralPath $t.JournalPath -Raw|ConvertFrom-Json
    Undo-OwnerHostServiceTransaction $restored
    Assert-True ((Get-OwnerHostSha (Join-Path $f.Product 'docker-compose.yml')) -ceq $f.Plan.files[0].old_sha256) 'interrupted replacement restored'
    $passed.Add('durable intent recovers replacement before journal acknowledgement')
    $f=Fixture 'unknown-after-commit'
    $t=New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('5'*32)
    Complete-OwnerHostServiceTransaction $t
    [IO.File]::WriteAllText($t.Files[0].Target,'unrecognized bytes')
    Must-Refuse { Undo-OwnerHostServiceTransaction $t } 'rollback never overwrites unknown bytes'
    Assert-True ([IO.File]::ReadAllText($t.Files[0].Target) -ceq 'unrecognized bytes') 'unknown bytes preserved'
    $f=Fixture 'saved-path-injection'
    $t=New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('6'*32)
    $t.Files[0].Saved=Join-Path $temporary 'unrelated-secret'
    Must-Refuse { Undo-OwnerHostServiceTransaction $t } 'rollback journal path injection refused'
    $f=Fixture 'stage-tamper'
    $t=New-OwnerHostServiceTransaction $f.Plan $f.Archive $f.Product $f.Work ('7'*32)
    [IO.File]::WriteAllText($t.Files[0].Staged,'tampered')
    Must-Refuse { Complete-OwnerHostServiceTransaction $t } 'stage tamper refused before commit'
    Assert-True ((Get-OwnerHostSha (Join-Path $f.Product 'docker-compose.yml')) -ceq $f.Plan.files[0].old_sha256) 'stage refusal preserved old code'
    [ordered]@{status='PASS_NEW_OWNER_HOST_TRANSACTION_PROBE';checks=$passed.Count;results=@($passed);docker_or_database_access=$false;keys_or_signatures_created=$false}|ConvertTo-Json -Depth 4 -Compress
} finally {
    $resolved=[IO.Path]::GetFullPath($temporary)
    $base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    if ($resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetFileName($resolved) -cmatch '^th-owner-host-unit-[0-9a-f]{32}$' -and
        -not ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    } else { throw 'Refused cleanup outside exact new test fixture.' }
}
