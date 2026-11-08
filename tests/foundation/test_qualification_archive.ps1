param([string]$EvidenceRoot = '')

# Run explicitly with Windows PowerShell 5.1. All fixtures and failed outputs
# are retained in a new directory. No Docker process or existing artifact is used.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ($PSVersionTable.PSVersion.Major -ne 5 -or $env:OS -ne 'Windows_NT') { throw 'This suite requires Windows PowerShell 5.1.' }
$qualificationRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$qualificationLibrary = Join-Path $qualificationRepo 'product\windows\Qualification Archive.ps1'
$qualificationTokens=$null
$qualificationParseErrors=$null
$qualificationAst=[Management.Automation.Language.Parser]::ParseFile($qualificationLibrary,[ref]$qualificationTokens,[ref]$qualificationParseErrors)
if ($qualificationParseErrors.Count -or $qualificationAst.BeginBlock -or $qualificationAst.ProcessBlock -or $qualificationAst.DynamicParamBlock -or
    @($qualificationAst.EndBlock.Statements | Where-Object {$_ -isnot [Management.Automation.Language.FunctionDefinitionAst]}).Count) {
    throw 'The dot-source library must parse and contain function declarations only.'
}
. $qualificationLibrary
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $qualificationRepo ('.foundation\qa-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
}
$EvidenceRoot = Assert-QAPlainPath $EvidenceRoot
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'An existing evidence root cannot be reused.' }
[IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
$qualificationTar = Get-QAWindowsTar
$qualificationUtf8 = [Text.UTF8Encoding]::new($false,$true)
$qualificationResults = [Collections.Generic.List[object]]::new()
$qualificationResults.Add([pscustomobject]@{name='dot-source-library-has-declarations-only';status='pass'})
$qualificationCase = 0

function Assert-QATest {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Write-QATestJson {
    param([string]$Path, $Value)
    [IO.File]::WriteAllText($Path, (ConvertTo-Json -InputObject $Value -Depth 40 -Compress), $qualificationUtf8)
}

function Invoke-QATestTar {
    param([string]$Tree, [string]$Archive, [string[]]$Members = @('manifest.json','index.json','repositories','oci-layout','blobs'))
    Assert-QATest (-not (Test-Path -LiteralPath $Archive)) 'A fixture archive already exists.'
    & $qualificationTar -cf $Archive --format=ustar -C $Tree @Members
    if ($LASTEXITCODE -ne 0) { throw 'Stock Windows tar fixture creation failed.' }
}

function New-QATestFixture {
    param([string]$Directory, [string]$Tag, [switch]$WithoutLabels)
    $tree = Join-Path $Directory 'tree'
    $blobs = Join-Path $tree 'blobs\sha256'
    [IO.Directory]::CreateDirectory($blobs) | Out-Null
    $layerTree = Join-Path $Directory 'layer'
    [IO.Directory]::CreateDirectory($layerTree) | Out-Null
    [IO.File]::WriteAllText((Join-Path $layerTree 'invented.txt'), 'Only synthetic archive fixture data.', $qualificationUtf8)
    $layerTar = Join-Path $Directory 'layer.tar'
    Invoke-QATestTar $layerTree $layerTar @('invented.txt')
    $layer = [IO.File]::ReadAllBytes($layerTar)
    $empty = New-Object byte[] 1024
    $layerHash = Get-QAHexSha256 $layer
    $emptyHash = Get-QAHexSha256 $empty
    [IO.File]::WriteAllBytes((Join-Path $blobs $layerHash), $layer)
    [IO.File]::WriteAllBytes((Join-Path $blobs $emptyHash), $empty)
    # This unreferenced compatibility blob must also remain byte-identical.
    $compat = [Text.Encoding]::UTF8.GetBytes('An unreferenced compatibility blob: '+$Tag)
    $compatHash = Get-QAHexSha256 $compat
    [IO.File]::WriteAllBytes((Join-Path $blobs $compatHash), $compat)
    $diffs = @(('sha256:'+$layerHash), ('sha256:'+$emptyHash), ('sha256:'+$emptyHash))
    $config = [ordered]@{architecture='amd64';os='linux';rootfs=[ordered]@{type='layers';diff_ids=$diffs};
        config=[ordered]@{Labels=[ordered]@{synthetic='true';binding_like_text=$Tag;quoted_text='colon: braces{} brackets[]'}}}
    if ($WithoutLabels) { $config.config.Remove('Labels') }
    $configBytes = $qualificationUtf8.GetBytes((ConvertTo-Json -InputObject $config -Depth 40 -Compress))
    $configHash = Get-QAHexSha256 $configBytes
    [IO.File]::WriteAllBytes((Join-Path $blobs $configHash), $configBytes)
    $layers = @()
    foreach ($row in @(@{Hash=$layerHash;Size=$layer.Length},@{Hash=$emptyHash;Size=$empty.Length},@{Hash=$emptyHash;Size=$empty.Length})) {
        $layers += [ordered]@{mediaType='application/vnd.oci.image.layer.v1.tar';digest='sha256:'+$row.Hash;size=$row.Size}
    }
    $sources = [ordered]@{}
    $sources['sha256:'+$layerHash] = $layers[0]
    $sources['sha256:'+$emptyHash] = $layers[1]
    $ociManifest = [ordered]@{schemaVersion=2;mediaType='application/vnd.oci.image.manifest.v1+json';
        config=[ordered]@{mediaType='application/vnd.oci.image.config.v1+json';digest='sha256:'+$configHash;size=$configBytes.Length};layers=$layers}
    $ociBytes = $qualificationUtf8.GetBytes((ConvertTo-Json -InputObject $ociManifest -Depth 40 -Compress))
    $ociHash = Get-QAHexSha256 $ociBytes
    [IO.File]::WriteAllBytes((Join-Path $blobs $ociHash), $ociBytes)
    $manifest = [pscustomobject]@{Config='blobs/sha256/'+$configHash;RepoTags=@($Tag);
        Layers=@(('blobs/sha256/'+$layerHash),('blobs/sha256/'+$emptyHash),('blobs/sha256/'+$emptyHash));LayerSources=[pscustomobject]$sources}
    Write-QATestJson (Join-Path $tree 'manifest.json') @($manifest)
    $parts = $Tag.Split(':')
    $index = [ordered]@{schemaVersion=2;mediaType='application/vnd.oci.image.index.v1+json';manifests=@(
        [ordered]@{mediaType='application/vnd.oci.image.manifest.v1+json';digest='sha256:'+$ociHash;size=$ociBytes.Length;
            annotations=[ordered]@{'io.containerd.image.name'='docker.io/library/'+$Tag;'org.opencontainers.image.ref.name'=$parts[1]}})}
    Write-QATestJson (Join-Path $tree 'index.json') $index
    Write-QATestJson (Join-Path $tree 'repositories') ([ordered]@{($parts[0])=[ordered]@{($parts[1])=$layerHash}})
    [IO.File]::WriteAllText((Join-Path $tree 'oci-layout'), '{"imageLayoutVersion":"1.0.0"}', $qualificationUtf8)
    $archive = Join-Path $Directory 'source.tar'
    Invoke-QATestTar $tree $archive
    return [pscustomobject]@{Tree=$tree;Archive=$archive;Tag=$Tag;Config='sha256:'+$configHash;
        Sha=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();Compat=$compatHash;Layer=$layerHash;Empty=$emptyHash}
}

function New-QATestCaseDirectory {
    $script:qualificationCase++
    $directory = Join-Path $EvidenceRoot ('n'+$script:qualificationCase.ToString('000'))
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    return $directory
}

function New-QATestMetadataMutation {
    param($Fixture, [scriptblock]$Mutation)
    $directory = New-QATestCaseDirectory
    $tree = Join-Path $directory 'tree'
    Copy-Item -LiteralPath $Fixture.Tree -Destination $tree -Recurse -ErrorAction Stop
    & $Mutation $tree
    $archive = Join-Path $directory 'source.tar'
    Invoke-QATestTar $tree $archive
    return $archive
}

function Set-QATestHeaderField {
    param([byte[]]$Bytes, [int]$Header, [int]$Offset, [int]$Length, [string]$Value)
    $valueBytes = [Text.Encoding]::ASCII.GetBytes($Value)
    if ($valueBytes.Length -gt $Length) { throw 'Test header value exceeds its field.' }
    [Array]::Clear($Bytes,$Header+$Offset,$Length)
    [Array]::Copy($valueBytes,0,$Bytes,$Header+$Offset,$valueBytes.Length)
}

function Set-QATestHeaderChecksum {
    param([byte[]]$Bytes, [int]$Header=0)
    for ($i=148; $i -lt 156; $i++) { $Bytes[$Header+$i]=32 }
    $sum=0
    for ($i=0; $i -lt 512; $i++) { $sum += $Bytes[$Header+$i] }
    Set-QATestHeaderField $Bytes $Header 148 8 ([Convert]::ToString($sum,8).PadLeft(6,'0')+[char]0+' ')
}

function New-QATestRawMutation {
    param($Fixture, [scriptblock]$Mutation)
    $directory = New-QATestCaseDirectory
    $bytes = [IO.File]::ReadAllBytes($Fixture.Archive)
    & $Mutation $bytes
    $archive = Join-Path $directory 'source.tar'
    [IO.File]::WriteAllBytes($archive,$bytes)
    return $archive
}

function Expect-QATestRefusal {
    param([string]$Name, $Fixture, [string]$Archive=$Fixture.Archive, [hashtable]$Overrides=@{}, [string]$Pattern='')
    $directory = New-QATestCaseDirectory
    $destination = Join-Path $directory 'out'
    $arguments = @{Archive=$Archive;DestinationDirectory=$destination;
        ExpectedArchiveSha256=(Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant();
        ExpectedTag=$Fixture.Tag;ExpectedConfigDigest=$Fixture.Config;QualifiedTag='th-qual-archive-tests:isolated'}
    foreach ($key in $Overrides.Keys) { $arguments[$key]=$Overrides[$key] }
    $refused=$false
    try { $null=New-QualifiedDockerArchive @arguments }
    catch {
        $refused=$true
        if ($Pattern -and $_.Exception.Message -notmatch $Pattern) { throw ('Wrong refusal for '+$Name+': '+$_.Exception.Message) }
    }
    Assert-QATest $refused ('Unsafe case accepted: '+$Name)
    Assert-QATest (-not (Test-Path -LiteralPath $destination)) ('Refusal created an output claim: '+$Name)
    $qualificationResults.Add([pscustomobject]@{name=$Name;status='pass';refused_before_output_claim=$true})
}

try {
    $fixtures = @{}
    $qualificationAppReceipt = $null
    foreach ($component in @('app','db','cache')) {
        $tag = if ($component -eq 'app') {'toefl-house-erp-app:local'} else {'toefl-house-erp-'+$component+':bundled'}
        $fixture = New-QATestFixture (Join-Path $EvidenceRoot ('in-'+$component)) $tag
        $fixtures[$component]=$fixture
        $destination = Join-Path $EvidenceRoot ('out-'+$component)
        $receipt = New-QualifiedDockerArchive -Archive $fixture.Archive -DestinationDirectory $destination -ExpectedArchiveSha256 $fixture.Sha `
            -ExpectedTag $fixture.Tag -ExpectedConfigDigest $fixture.Config -QualifiedTag ('th-qual-archive-'+$component+':isolated')
        $derived = Get-QualificationArchiveInspection -Archive $receipt.output_archive -ExpectedArchiveSha256 $receipt.derived_archive_sha256 `
            -ExpectedTag $receipt.qualified_tag -ExpectedConfigDigest $fixture.Config
        Assert-QATest ($receipt.immutable_blobs_verified -eq 5) 'An unreferenced blob was omitted.'
        Assert-QATest ($receipt.ordered_layers.Count -eq 3 -and $receipt.ordered_layers[1] -ceq $receipt.ordered_layers[2]) 'Repeated layer order was not preserved.'
        Assert-QATest (@($derived.LayerSources.PSObject.Properties).Count -eq 2) 'LayerSources coverage changed.'
        Assert-QATest ($receipt.rewritten_metadata_sha256.Count -eq 3) 'The receipt must bind each rewritten metadata member.'
        Assert-QATest ($derived.Labels.binding_like_text -ceq $fixture.Tag) 'A non-binding tag-like value was rewritten.'
        Assert-QATest ((Get-FileHash -LiteralPath $fixture.Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $fixture.Sha) 'Original archive bytes changed.'
        if ($component -eq 'app') { $qualificationAppReceipt = $receipt }
        $qualificationResults.Add([pscustomobject]@{name=('native-tar-'+$component+'-all-tag-bindings-and-immutable-content');status='pass';receipt=$receipt})
    }
    $noLabels=New-QATestFixture (Join-Path $EvidenceRoot 'in-no-labels') 'toefl-house-erp-cache:bundled' -WithoutLabels
    $inspection=Get-QualificationArchiveInspection -Archive $noLabels.Archive -ExpectedArchiveSha256 $noLabels.Sha -ExpectedTag $noLabels.Tag -ExpectedConfigDigest $noLabels.Config
    Assert-QATest ($null -eq $inspection.Labels) 'Optional absent image labels were invented.'
    $qualificationResults.Add([pscustomobject]@{name='native-image-config-without-optional-labels';status='pass'})
    $fixture = $fixtures.app
    $qualificationAlternateLegacyDigest = $fixture.Empty
    $qualificationDerivedFixture = [pscustomobject]@{Tree=(Join-Path $EvidenceRoot 'out-app\files')}
    $changedLegacyArchive = New-QATestMetadataMutation $qualificationDerivedFixture {
        param($tree)
        $repositoriesPath = Join-Path $tree 'repositories'
        $bindings = ConvertFrom-QAJson ([IO.File]::ReadAllBytes($repositoriesPath))
        $bindings.'th-qual-archive-app'.isolated = $qualificationAlternateLegacyDigest
        Write-QATestJson $repositoriesPath $bindings
    }
    $changedLegacySha = (Get-FileHash -LiteralPath $changedLegacyArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    $structuralInspection = Get-QualificationArchiveInspection -Archive $changedLegacyArchive -ExpectedArchiveSha256 $changedLegacySha `
        -ExpectedTag $qualificationAppReceipt.qualified_tag -ExpectedConfigDigest $fixture.Config
    Assert-QATest ($structuralInspection.Metadata.repositories.'th-qual-archive-app'.isolated -ceq $qualificationAlternateLegacyDigest) `
        'The regression archive must pass structural inspection with the changed legacy binding.'
    $changedLegacyStream = [IO.File]::OpenRead($changedLegacyArchive)
    $exactRewriteRefused = $false
    try {
        $null = Read-QAArchive $changedLegacyStream $changedLegacySha $qualificationAppReceipt.qualified_tag $fixture.Config 4096 16GB 1MB `
            -ExpectedRewrittenMetadataSha256 $qualificationAppReceipt.rewritten_metadata_sha256
    } catch {
        if ($_.Exception.Message -cne 'Derived metadata bytes differ from the authorized rewrite: repositories') { throw }
        $exactRewriteRefused = $true
    } finally { $changedLegacyStream.Dispose() }
    Assert-QATest $exactRewriteRefused 'The derived-output verifier accepted a valid-looking changed legacy binding.'
    $qualificationResults.Add([pscustomobject]@{name='exact-rewrite-rejects-structurally-valid-changed-legacy-binding';status='pass';
        structurally_valid=$true;changed_archive_sha256=$changedLegacySha;refused_by='repositories bytes'})
    Expect-QATestRefusal 'wrong-authorized-archive-hash' $fixture -Overrides @{ExpectedArchiveSha256=('0'*64)} -Pattern 'SHA-256'
    Expect-QATestRefusal 'wrong-authorized-config' $fixture -Overrides @{ExpectedConfigDigest=('sha256:'+('0'*64))} -Pattern 'config identity'
    Expect-QATestRefusal 'wrong-original-tag' $fixture -Overrides @{ExpectedTag='toefl-house-erp-db:bundled'} -Pattern 'tag binding'
    Expect-QATestRefusal 'archive-byte-bound' $fixture -Overrides @{MaxArchiveBytes=1024} -Pattern 'size bound'
    Expect-QATestRefusal 'expanded-byte-bound' $fixture -Overrides @{MaxExpandedBytes=1} -Pattern 'expansion bound'
    Expect-QATestRefusal 'entry-bound' $fixture -Overrides @{MaxEntries=2} -Pattern 'entry bound'
    Expect-QATestRefusal 'metadata-byte-bound' $fixture -Overrides @{MaxMetadataBytes=1} -Pattern 'metadata exceeds'
    foreach ($tag in @('toefl-house-erp-app:local','TH-QUAL-test:isolated',('th-qual-'+('a'*250)+':isolated'),("th-qual-test:isolated"+[char]10))) {
        Expect-QATestRefusal ('invalid-qualified-tag-'+$qualificationCase) $fixture -Overrides @{QualifiedTag=$tag}
    }

    foreach ($name in @('../escape','/absolute','C:/drive','\\server\share','manifest.json:ads','manifest.json.','manifest.json ','CON','blobs/../escape','Manifest.json',("manifest.json"+[char]10))) {
        $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes 0 0 100 $name; Set-QATestHeaderChecksum $bytes}
        Expect-QATestRefusal ('tar-path-'+$name) $fixture $archive -Pattern 'Unsafe or unexpected'
    }
    foreach ($kind in @('1','2','3','4','6','7','x','g','L','K','S')) {
        $archive = New-QATestRawMutation $fixture {param($bytes) $bytes[156]=[byte][char]$kind; Set-QATestHeaderChecksum $bytes}
        Expect-QATestRefusal ('tar-unsupported-type-'+$kind) $fixture $archive -Pattern 'links, devices, sparse and extended'
    }
    $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes 0 157 100 'hidden-target'; Set-QATestHeaderChecksum $bytes}
    Expect-QATestRefusal 'tar-hidden-link-target' $fixture $archive -Pattern 'link targets'
    $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes 0 100 8 '0004755'; Set-QATestHeaderChecksum $bytes}
    Expect-QATestRefusal 'tar-special-mode-bits' $fixture $archive -Pattern 'Special TAR mode'
    $archive = New-QATestRawMutation $fixture {param($bytes) $bytes[124]=128; Set-QATestHeaderChecksum $bytes}
    Expect-QATestRefusal 'tar-base256-size' $fixture $archive -Pattern 'unsigned octal'
    $archive = New-QATestRawMutation $fixture {param($bytes) $bytes[153]=$bytes[153] -bxor 1}
    Expect-QATestRefusal 'tar-bad-checksum' $fixture $archive -Pattern 'checksum'
    $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes 0 257 6 'ustar '; Set-QATestHeaderChecksum $bytes}
    Expect-QATestRefusal 'tar-unsupported-dialect' $fixture $archive -Pattern 'USTAR dialect'
    $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes 0 0 100 ('manifest.json'+[char]0+'hidden'); Set-QATestHeaderChecksum $bytes}
    Expect-QATestRefusal 'tar-hidden-name-after-terminator' $fixture $archive -Pattern 'Hidden data'
    $sourceStream=[IO.File]::OpenRead($fixture.Archive)
    try { $sourceIndex=Read-QATarIndex $sourceStream 4096 16GB } finally { $sourceStream.Dispose() }
    $secondHeader=[int]$sourceIndex.Entries[1].Offset-512
    $archive = New-QATestRawMutation $fixture {param($bytes) Set-QATestHeaderField $bytes $secondHeader 0 100 'manifest.json'; Set-QATestHeaderChecksum $bytes $secondHeader}
    Expect-QATestRefusal 'tar-duplicate-metadata-entry' $fixture $archive -Pattern 'Duplicate'
    $first=$sourceIndex.Entries[0]
    $archive = New-QATestRawMutation $fixture {param($bytes) $bytes[[int]($first.Offset+$first.Size)]=1}
    Expect-QATestRefusal 'tar-hidden-member-padding' $fixture $archive -Pattern 'padding'
    $archive = New-QATestRawMutation $fixture {param($bytes) $bytes[$bytes.Length-1]=1}
    Expect-QATestRefusal 'tar-trailing-hidden-data' $fixture $archive -Pattern 'Trailing'

    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); [IO.File]::WriteAllText($p,$s.Replace('"Config":','"Config":"duplicate","Config":'),$qualificationUtf8)}
    Expect-QATestRefusal 'json-duplicate-decoded-key' $fixture $archive -Pattern 'Duplicate or case-colliding JSON key'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); [IO.File]::WriteAllText($p,$s.Replace('"Config":','"\u0043onfig":"duplicate","Config":'),$qualificationUtf8)}
    Expect-QATestRefusal 'json-escaped-key-collision' $fixture $archive -Pattern 'Duplicate or case-colliding JSON key'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); [IO.File]::WriteAllText($p,$s.Replace('"Config":','"config":"duplicate","Config":'),$qualificationUtf8)}
    Expect-QATestRefusal 'json-case-colliding-key' $fixture $archive -Pattern 'Duplicate or case-colliding JSON key'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; [IO.File]::WriteAllText($p,[char]0xFEFF+[IO.File]::ReadAllText($p),$qualificationUtf8)}
    Expect-QATestRefusal 'json-leading-bom' $fixture $archive -Pattern 'BOM'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); $nested='0'; for($level=0;$level -lt 40;$level++){$nested='['+$nested+']'}; [IO.File]::WriteAllText($p,$s.Replace('"Config":',('"nested":'+$nested+',"Config":')),$qualificationUtf8)}
    Expect-QATestRefusal 'json-nesting-bound' $fixture $archive -Pattern 'nesting bound'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $b=[IO.File]::ReadAllBytes($p); $b[0]=255; [IO.File]::WriteAllBytes($p,$b)}
    Expect-QATestRefusal 'json-invalid-utf8' $fixture $archive
    foreach ($suffix in @('/*comment*/',',')) {
        $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); $s=if($suffix -eq ','){$s.Substring(0,$s.Length-1)+',]'}else{$suffix+$s}; [IO.File]::WriteAllText($p,$s,$qualificationUtf8)}
        Expect-QATestRefusal ('json-nonstandard-'+$suffix) $fixture $archive -Pattern 'standard JSON'
    }
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $s=[IO.File]::ReadAllText($p); [IO.File]::WriteAllText($p,$s.Replace('"RepoTags"',('"Repo'+[char]1+'Tags"')),$qualificationUtf8)}
    Expect-QATestRefusal 'json-unescaped-control-character' $fixture $archive -Pattern 'control characters'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m[0].RepoTags=@($fixture.Tag,'unexpected:old'); Write-QATestJson $p $m}
    Expect-QATestRefusal 'docker-additional-tag-binding' $fixture $archive -Pattern 'tag binding'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'index.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.manifests[0].annotations.'io.containerd.image.name'='docker.io/library/unexpected:old'; Write-QATestJson $p $m}
    Expect-QATestRefusal 'oci-hidden-old-tag-binding' $fixture $archive -Pattern 'tag annotations|identity text'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'index.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.manifests[0].annotations.'io.containerd.image.name'+=[char]0xFEFF; Write-QATestJson $p $m}
    Expect-QATestRefusal 'oci-culture-ignorable-tag-character' $fixture $archive -Pattern 'identity text'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'index.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.manifests[0].annotations | Add-Member -NotePropertyName 'unexpected.binding' -NotePropertyValue 'unexpected:old'; Write-QATestJson $p $m}
    Expect-QATestRefusal 'oci-unreviewed-annotation' $fixture $archive -Pattern 'metadata fields'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'repositories'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.'toefl-house-erp-app' | Add-Member -NotePropertyName 'unexpected' -NotePropertyValue ('1'*64); Write-QATestJson $p $m}
    Expect-QATestRefusal 'legacy-hidden-old-tag-binding' $fixture $archive -Pattern 'metadata fields'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'index.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.schemaVersion='2'; Write-QATestJson $p $m}
    Expect-QATestRefusal 'oci-string-integer' $fixture $archive -Pattern 'JSON integers'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'repositories'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.'toefl-house-erp-app'.local=@($m.'toefl-house-erp-app'.local); Write-QATestJson $p $m}
    Expect-QATestRefusal 'legacy-array-instead-of-digest-string' $fixture $archive -Pattern 'JSON strings'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'index.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m.manifests[0].annotations.'io.containerd.image.name'=@($m.manifests[0].annotations.'io.containerd.image.name'); Write-QATestJson $p $m}
    Expect-QATestRefusal 'oci-array-instead-of-tag-string' $fixture $archive -Pattern 'JSON strings'
    $archive = New-QATestMetadataMutation $fixture {param($tree) Write-QATestJson (Join-Path $tree 'oci-layout') ([ordered]@{imageLayoutVersion=$true})}
    Expect-QATestRefusal 'oci-boolean-instead-of-layout-string' $fixture $archive -Pattern 'JSON strings'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m[0].Layers=@($m[0].Layers[1],$m[0].Layers[0],$m[0].Layers[2]); Write-QATestJson $p $m}
    Expect-QATestRefusal 'docker-layer-order-mismatch' $fixture $archive -Pattern 'layer order or multiplicity'
    $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree 'manifest.json'; $m=ConvertFrom-QAJson ([IO.File]::ReadAllBytes($p)); $m[0].LayerSources.PSObject.Properties.Remove('sha256:'+$fixture.Empty); Write-QATestJson $p $m}
    Expect-QATestRefusal 'missing-layer-source' $fixture $archive -Pattern 'LayerSources does not cover'
    foreach ($blob in @($fixture.Compat,$fixture.Config.Substring(7),$fixture.Layer)) {
        $archive = New-QATestMetadataMutation $fixture {param($tree) $p=Join-Path $tree ('blobs\sha256\'+$blob); $b=[IO.File]::ReadAllBytes($p); $b[0]=$b[0] -bxor 1; [IO.File]::WriteAllBytes($p,$b)}
        Expect-QATestRefusal ('changed-content-addressed-blob-'+$blob.Substring(0,8)) $fixture $archive -Pattern 'blob digest'
    }
    foreach ($name in @('bad.','bad ','bad:ads','CON','NUL.txt','COM1','LPT9.txt','bad[1]','bad`name')) {
        $refused=$false
        try { $null=Assert-QAPlainPath ($EvidenceRoot.TrimEnd('\')+'\'+$name) } catch { $refused=$true }
        Assert-QATest $refused ('Host Windows path alias accepted: '+$name)
        $qualificationResults.Add([pscustomobject]@{name=('host-path-'+$name);status='pass'})
    }
    $occupied=Join-Path $EvidenceRoot 'occupied'
    [IO.Directory]::CreateDirectory($occupied) | Out-Null
    $marker=Join-Path $occupied 'preserve.txt'
    [IO.File]::WriteAllText($marker,'Keep this preexisting synthetic marker.',$qualificationUtf8)
    $markerHash=(Get-FileHash -LiteralPath $marker -Algorithm SHA256).Hash
    $refused=$false
    try { $null=New-QualifiedDockerArchive -Archive $fixture.Archive -DestinationDirectory $occupied -ExpectedArchiveSha256 $fixture.Sha -ExpectedTag $fixture.Tag -ExpectedConfigDigest $fixture.Config -QualifiedTag 'th-qual-collision:isolated' }
    catch {$refused=$true}
    Assert-QATest ($refused -and (Get-FileHash -LiteralPath $marker -Algorithm SHA256).Hash -ceq $markerHash) 'An occupied output was reused or changed.'
    $qualificationResults.Add([pscustomobject]@{name='occupied-destination-refused-and-marker-preserved';status='pass'})
    $inside=Join-Path (Split-Path -Parent $fixture.Archive) 'out'
    $refused=$false
    try { $null=New-QualifiedDockerArchive -Archive $fixture.Archive -DestinationDirectory $inside -ExpectedArchiveSha256 $fixture.Sha -ExpectedTag $fixture.Tag -ExpectedConfigDigest $fixture.Config -QualifiedTag 'th-qual-collision:isolated' }
    catch {$refused=$true}
    Assert-QATest ($refused -and -not (Test-Path -LiteralPath $inside)) 'Input archive directory was used for output.'
    $qualificationResults.Add([pscustomobject]@{name='input-tree-output-refused-before-claim';status='pass'})
    $report=[ordered]@{status='pass';scope='REAL WINDOWS POWERSHELL 5.1 AND STOCK TAR; ARCHIVE COMPONENT ONLY';
        production_authorization='REJECT';docker_commands_executed=$false;existing_artifacts_changed=$false;
        powershell_version=$PSVersionTable.PSVersion.ToString();tar=$qualificationTar;checks=$qualificationResults.ToArray();
        test_count=$qualificationResults.Count;library_sha256=(Get-FileHash -LiteralPath (Join-Path $qualificationRepo 'product\windows\Qualification Archive.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()}
    Write-QATestJson (Join-Path $EvidenceRoot 'test-evidence.json') $report
    Write-Output ('Qualification archive component: '+$qualificationResults.Count+' Windows checks passed. Evidence: '+$EvidenceRoot)
} catch {
    $failure=[ordered]@{status='fail';scope='ARCHIVE COMPONENT TESTS ONLY';production_authorization='REJECT';completed_checks=$qualificationResults.Count;
        error_type=$_.Exception.GetType().Name;error=$_.Exception.Message;position=$_.InvocationInfo.PositionMessage}
    Write-QATestJson (Join-Path $EvidenceRoot 'failure-evidence.json') $failure
    throw
}
