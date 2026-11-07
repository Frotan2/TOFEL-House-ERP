# Pure Windows PowerShell 5.1 archive component. Dot-sourcing has no side effects.
# This file never imports images, changes Docker tags, or operates on a site.

function Get-QAHexSha256 {
    param([byte[]]$Bytes)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}

function Get-QARangeSha256 {
    param([IO.Stream]$Stream, [long]$Offset, [long]$Length)
    $Stream.Position = $Offset
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $buffer = New-Object byte[] (1024 * 1024)
        $remaining = $Length
        while ($remaining -gt 0) {
            $count = $Stream.Read($buffer, 0, [int][Math]::Min($remaining, $buffer.Length))
            if ($count -le 0) { throw 'Archive ended before its declared boundary.' }
            $null = $hash.TransformBlock($buffer, 0, $count, $buffer, 0)
            $remaining -= $count
        }
        $null = $hash.TransformFinalBlock([byte[]]@(), 0, 0)
        return [BitConverter]::ToString($hash.Hash).Replace('-', '').ToLowerInvariant()
    } finally { $hash.Dispose() }
}

function Assert-QAPlainPath {
    param([string]$Path, [switch]$MustExist)
    $provided = $Path.Replace('/','\')
    $full = [IO.Path]::GetFullPath($provided)
    if ($provided.StartsWith('\\',[StringComparison]::Ordinal) -or $full -notmatch '^[A-Za-z]:\\') {
        throw 'Use a local drive path without device or UNC syntax.'
    }
    # GetFullPath can strip trailing dots or spaces. Check the caller's spelling
    # as well as the resolved path before any filesystem operation.
    foreach ($pathForm in @($provided,$full)) {
        $tail = $pathForm -replace '^[A-Za-z]:\\',''
        foreach ($part in $tail.Split('\')) {
            if ($part -in @('','.','..')) { continue }
            if ($part -match '[<>:"|?*\[\]`\x00-\x1f]' -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
                $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9\u00b9\u00b2\u00b3]|LPT[1-9\u00b9\u00b2\u00b3])(?:\.|$)') {
                throw 'Alternate streams, wildcard syntax, device names and Windows path aliases are forbidden.'
            }
        }
    }
    if ($MustExist -and -not (Test-Path -LiteralPath $full)) { throw 'Required archive path is missing.' }
    $current = $full
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $attributes = [IO.File]::GetAttributes($current)
            if ($attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked archive paths are forbidden.' }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
    return $full
}

function Read-QAField {
    param([byte[]]$Header, [int]$Offset, [int]$Length)
    $end = $Offset + $Length
    $zero = -1
    for ($i = $Offset; $i -lt $end; $i++) {
        if ($Header[$i] -gt 127) { throw 'Non-ASCII TAR header fields are unsupported.' }
        if ($Header[$i] -eq 0 -and $zero -lt 0) { $zero = $i }
        elseif ($zero -ge 0 -and $Header[$i] -ne 0) { throw 'Hidden data after a TAR field terminator is forbidden.' }
    }
    if ($zero -lt 0) { $zero = $end }
    return [Text.Encoding]::ASCII.GetString($Header, $Offset, $zero - $Offset)
}

function Read-QAOctal {
    param([byte[]]$Header, [int]$Offset, [int]$Length)
    $text = [Text.Encoding]::ASCII.GetString($Header, $Offset, $Length).Trim([char[]]@([char]0, [char]32))
    if ($text -notmatch '^[0-7]+\z') { throw 'Only bounded unsigned octal TAR numbers are supported.' }
    return [Convert]::ToInt64($text, 8)
}

function Read-QATarIndex {
    param([IO.Stream]$Stream, [int]$MaxEntries, [long]$MaxExpandedBytes)
    if ($Stream.Length -lt 1024 -or $Stream.Length % 512 -ne 0) { throw 'Expected an uncompressed, block-aligned TAR.' }
    $entries = [Collections.Generic.List[object]]::new()
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $metadataNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($value in @('manifest.json','index.json','repositories','oci-layout')) { $null=$metadataNames.Add($value) }
    $directoryNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($value in @('blobs','blobs/','blobs/sha256','blobs/sha256/')) { $null=$directoryNames.Add($value) }
    $position = [long]0
    $expanded = [long]0
    $terminated = $false
    $header = New-Object byte[] 512
    while ($position -lt $Stream.Length) {
        $Stream.Position = $position
        if ($Stream.Read($header, 0, 512) -ne 512) { throw 'Truncated TAR header.' }
        $nonzero = $false
        foreach ($value in $header) { if ($value -ne 0) { $nonzero = $true; break } }
        if (-not $nonzero) {
            if ($Stream.Length - $position -lt 1024) { throw 'TAR requires two end blocks.' }
            $Stream.Position = $position
            $tail = New-Object byte[] 8192
            while (($count = $Stream.Read($tail, 0, $tail.Length)) -gt 0) {
                for ($i = 0; $i -lt $count; $i++) { if ($tail[$i] -ne 0) { throw 'Trailing or concatenated TAR data is forbidden.' } }
            }
            $terminated = $true
            break
        }
        if ([Text.Encoding]::ASCII.GetString($header, 257, 6) -cne "ustar`0" -or
            [Text.Encoding]::ASCII.GetString($header, 263, 2) -cne '00') {
            throw 'Only the reviewed plain USTAR dialect is supported.'
        }
        $sum = [long]0
        for ($i = 0; $i -lt 512; $i++) { if ($i -ge 148 -and $i -lt 156) { $sum += 32 } else { $sum += $header[$i] } }
        if ($sum -ne (Read-QAOctal $header 148 8)) { throw 'TAR header checksum failed.' }
        if ((Read-QAOctal $header 100 8) -gt 511) { throw 'Special TAR mode bits are unsupported.' }
        $name = Read-QAField $header 0 100
        $prefix = Read-QAField $header 345 155
        if ($prefix) { $name = $prefix + '/' + $name }
        if (Read-QAField $header 157 100) { throw 'TAR link targets are forbidden.' }
        $size = Read-QAOctal $header 124 12
        $type = [int]$header[156]
        if ($type -eq 53) {
            if ($size -ne 0 -or -not $directoryNames.Contains($name)) {
                throw 'Unexpected TAR directory or nonempty directory entry.'
            }
            $name = $name.TrimEnd('/') + '/'
        } elseif ($type -eq 0 -or $type -eq 48) {
            if (-not $metadataNames.Contains($name) -and
                $name -cnotmatch '^blobs/sha256/[0-9a-f]{64}\z') {
                throw 'Unsafe or unexpected Docker archive member.'
            }
        } else { throw 'TAR links, devices, sparse and extended headers are forbidden.' }
        if (-not $seen.Add($name)) { throw 'Duplicate or Windows-colliding TAR member.' }
        if ($entries.Count -ge $MaxEntries) { throw 'TAR entry bound exceeded.' }
        $expanded += $size
        if ($expanded -gt $MaxExpandedBytes) { throw 'TAR expansion bound exceeded.' }
        $offset = $position + 512
        $next = $offset + [long]([Math]::Ceiling($size / 512.0) * 512)
        if ($next -gt $Stream.Length - 1024) { throw 'TAR member exceeds the archive boundary.' }
        $padding = $next - $offset - $size
        if ($padding -gt 0) {
            $Stream.Position = $offset + $size
            $pad = New-Object byte[] ([int]$padding)
            if ($Stream.Read($pad, 0, $pad.Length) -ne $pad.Length -or @($pad | Where-Object { $_ -ne 0 }).Count) {
                throw 'Nonzero or truncated TAR member padding is forbidden.'
            }
        }
        $entries.Add([pscustomobject]@{Name=$name; Size=$size; Directory=($type -eq 53); Offset=$offset})
        $position = $next
    }
    if (-not $terminated) { throw 'TAR end markers are missing.' }
    foreach ($required in @('manifest.json', 'index.json', 'repositories', 'oci-layout')) {
        if (-not $seen.Contains($required)) { throw 'Required Docker archive metadata is missing.' }
    }
    return [pscustomobject]@{Entries=$entries.ToArray(); ExpandedBytes=$expanded}
}

function Read-QAEntryBytes {
    param([IO.Stream]$Stream, $Entry, [int]$MaxMetadataBytes)
    if ($Entry.Size -gt $MaxMetadataBytes) { throw 'Archive JSON metadata exceeds its bound.' }
    $bytes = New-Object byte[] ([int]$Entry.Size)
    $Stream.Position = $Entry.Offset
    $offset = 0
    while ($offset -lt $bytes.Length) {
        $count = $Stream.Read($bytes, $offset, $bytes.Length - $offset)
        if ($count -le 0) { throw 'Truncated archive metadata.' }
        $offset += $count
    }
    return ,$bytes
}

function ConvertFrom-QAJson {
    param([byte[]]$Bytes)
    $text = [Text.UTF8Encoding]::new($false, $true).GetString($Bytes)
    if ($text.Length -gt 0 -and $text[0] -eq [char]0xFEFF) { throw 'JSON BOMs are unsupported.' }
    # Tokenize strings before braces so braces/colons inside strings are inert.
    # Conversion below validates grammar; this pass also rejects duplicate and
    # case-colliding decoded object keys, which PowerShell cannot distinguish.
    $stack = [Collections.Generic.List[object]]::new()
    $pattern = '"(?:\\.|[^"\\])*"|[{}\[\]]'
    foreach ($token in [regex]::Matches($text, $pattern)) {
        $value = $token.Value
        if ($value.StartsWith('"') -and $value -match '[\x00-\x1f]') { throw 'Unescaped JSON control characters are forbidden.' }
        if ($value -eq '{') { $stack.Add([pscustomobject]@{Kind='object'; Keys=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)}) }
        elseif ($value -eq '[') { $stack.Add([pscustomobject]@{Kind='array'; Keys=$null}) }
        elseif ($value -eq '}' -or $value -eq ']') {
            if ($stack.Count -eq 0) { throw 'Unbalanced archive JSON.' }
            $expected = if ($value -eq '}') {'object'} else {'array'}
            if ($stack[$stack.Count-1].Kind -cne $expected) { throw 'Unbalanced archive JSON.' }
            $stack.RemoveAt($stack.Count-1)
        } elseif ($stack.Count -gt 0 -and $stack[$stack.Count-1].Kind -eq 'object') {
            $after = $token.Index + $token.Length
            while ($after -lt $text.Length -and [char]::IsWhiteSpace($text[$after])) { $after++ }
            if ($after -lt $text.Length -and $text[$after] -eq ':') {
                $key = (ConvertFrom-Json -InputObject ('{"key":' + $value + '}') -ErrorAction Stop).key
                if (-not $stack[$stack.Count-1].Keys.Add($key)) { throw 'Duplicate or case-colliding JSON key.' }
            }
        }
        if ($stack.Count -gt 32) { throw 'Archive JSON nesting bound exceeded.' }
    }
    if ($stack.Count -ne 0) { throw 'Unbalanced archive JSON.' }
    $masked = [regex]::Replace($text, '"(?:\\.|[^"\\])*"', '""')
    if ($masked -match '[^{}\[\]:,0-9eE+.\-truefalsnul \t\r\n"]' -or $masked -match ',[ \t\r\n]*[}\]]') {
        throw 'Only standard JSON syntax is supported.'
    }
    $decoded = ConvertFrom-Json -InputObject $text -ErrorAction Stop
    if ($decoded -is [array]) {
        # Windows PowerShell can attach array wrapper properties while decoding.
        # Copy the elements so ConvertTo-Json emits a JSON array on re-encoding.
        $plain = [array]::CreateInstance([object], $decoded.Length)
        [array]::Copy($decoded, $plain, $decoded.Length)
        return ,$plain
    }
    return ,$decoded
}

function Assert-QAProperties {
    param($Object, [string[]]$Names)
    if ($null -eq $Object -or $Object -isnot [pscustomobject]) { throw 'Expected a Docker metadata object.' }
    $actual = @($Object.PSObject.Properties.Name)
    if ($actual.Count -ne $Names.Count) { throw 'Unsupported Docker metadata fields.' }
    $allowed=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($name in $Names) { $null=$allowed.Add($name) }
    foreach ($name in $actual) { if (-not $allowed.Contains($name)) { throw 'Unsupported Docker metadata field spelling.' } }
}

function Assert-QAInteger {
    param($Value, [long]$Expected)
    if (($Value -isnot [int] -and $Value -isnot [long]) -or $Value -lt 0 -or $Value -ne $Expected) {
        throw 'Docker descriptor numbers must be exact nonnegative JSON integers.'
    }
}

function Assert-QAString {
    param($Value)
    if ($Value -isnot [string]) { throw 'Docker identity fields must be exact JSON strings.' }
}

function Assert-QAExactString {
    param($Value, [string]$Expected)
    Assert-QAString $Value
    if (-not [string]::Equals($Value,$Expected,[StringComparison]::Ordinal)) { throw 'Docker identity text differs from its exact expected value.' }
}

function Read-QAArchive {
    param([IO.Stream]$Stream, [string]$ExpectedArchiveSha256, [string]$ExpectedTag,
          [string]$ExpectedConfigDigest, [int]$MaxEntries, [long]$MaxExpandedBytes, [int]$MaxMetadataBytes,
          [hashtable]$ExpectedRewrittenMetadataSha256)
    if ($ExpectedTag -cnotmatch '^[a-z0-9]+(?:[._-][a-z0-9]+)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\z') { throw 'Unsupported image tag syntax.' }
    $sha = Get-QARangeSha256 $Stream 0 $Stream.Length
    if ($sha -cne $ExpectedArchiveSha256) { throw 'Original archive SHA-256 does not match its authorized identity.' }
    $index = Read-QATarIndex $Stream $MaxEntries $MaxExpandedBytes
    $byName = @{}
    $blobs = @{}
    foreach ($entry in $index.Entries) {
        $byName[$entry.Name] = $entry
        if ($entry.Name -cmatch '^blobs/sha256/([0-9a-f]{64})\z') {
            $expected = $Matches[1]
            if ((Get-QARangeSha256 $Stream $entry.Offset $entry.Size) -cne $expected) { throw 'A content-addressed blob digest is invalid.' }
            $blobs[$entry.Name] = $expected
        }
    }
    $metadata = @{}
    foreach ($name in @('manifest.json', 'index.json', 'repositories', 'oci-layout')) {
        $bytes = Read-QAEntryBytes $Stream $byName[$name] $MaxMetadataBytes
        if ($null -ne $ExpectedRewrittenMetadataSha256 -and $name -cne 'oci-layout' -and
            (Get-QAHexSha256 $bytes) -cne $ExpectedRewrittenMetadataSha256[$name]) {
            throw "Derived metadata bytes differ from the authorized rewrite: $name"
        }
        $metadata[$name] = ConvertFrom-QAJson $bytes
    }
    $manifest = $metadata['manifest.json']
    if ($manifest -isnot [array] -or $manifest.Count -ne 1) { throw 'Exactly one Docker manifest entry is required.' }
    $image = $manifest[0]
    Assert-QAProperties $image @('Config', 'RepoTags', 'Layers', 'LayerSources')
    Assert-QAString $image.Config
    if ($image.RepoTags -isnot [array] -or $image.RepoTags.Count -ne 1 -or $image.RepoTags[0] -cne $ExpectedTag) { throw 'Unexpected image tag binding.' }
    Assert-QAExactString $image.RepoTags[0] $ExpectedTag
    if ($image.Config -cnotmatch '^blobs/sha256/([0-9a-f]{64})\z' -or 'sha256:'+$Matches[1] -cne $ExpectedConfigDigest -or
        -not $byName.ContainsKey($image.Config)) { throw 'Unexpected Docker config identity.' }
    $config = ConvertFrom-QAJson (Read-QAEntryBytes $Stream $byName[$image.Config] $MaxMetadataBytes)
    Assert-QAExactString $config.os 'linux'
    Assert-QAExactString $config.architecture 'amd64'
    Assert-QAExactString $config.rootfs.type 'layers'
    if ($config.os -cne 'linux' -or $config.architecture -cne 'amd64' -or $config.rootfs.type -cne 'layers') { throw 'Expected Linux/amd64 layer-based image.' }
    if ($image.Layers -isnot [array] -or $image.Layers.Count -lt 1 -or $image.Layers.Count -gt 256) { throw 'Image layer bound is invalid.' }
    $digests = [Collections.Generic.List[string]]::new()
    foreach ($layer in $image.Layers) {
        Assert-QAString $layer
        if ($layer -cnotmatch '^blobs/sha256/([0-9a-f]{64})\z' -or -not $byName.ContainsKey($layer)) { throw 'Layer blob is missing or unsafe.' }
        $digests.Add('sha256:' + $Matches[1])
    }
    if ($config.rootfs.diff_ids -isnot [array] -or $config.rootfs.diff_ids.Count -ne $image.Layers.Count -or
        ($config.rootfs.diff_ids -join '|') -cne ($digests.ToArray() -join '|')) { throw 'Config rootfs layer order or multiplicity differs.' }
    for ($i=0; $i -lt $image.Layers.Count; $i++) { Assert-QAExactString $config.rootfs.diff_ids[$i] $digests[$i] }
    if ($image.LayerSources -isnot [pscustomobject]) { throw 'LayerSources metadata is required.' }
    $unique = @($digests.ToArray() | Select-Object -Unique)
    if (@($image.LayerSources.PSObject.Properties).Count -ne $unique.Count) { throw 'LayerSources does not cover unique layers.' }
    foreach ($property in $image.LayerSources.PSObject.Properties) {
        if ($property.Name -cnotmatch '^sha256:[0-9a-f]{64}\z' -or $property.Name -cnotin $unique) { throw 'Unexpected LayerSources identity.' }
        Assert-QAProperties $property.Value @('mediaType', 'size', 'digest')
        Assert-QAExactString $property.Value.digest $property.Name
        Assert-QAExactString $property.Value.mediaType 'application/vnd.oci.image.layer.v1.tar'
        Assert-QAInteger $property.Value.size $byName['blobs/sha256/'+$property.Name.Substring(7)].Size
        if ($property.Value.digest -cne $property.Name -or $property.Value.mediaType -cne 'application/vnd.oci.image.layer.v1.tar' -or
            $property.Value.size -ne $byName['blobs/sha256/'+$property.Name.Substring(7)].Size) { throw 'LayerSources descriptor differs from its blob.' }
    }
    $oci = $metadata['index.json']
    Assert-QAProperties $oci @('schemaVersion', 'mediaType', 'manifests')
    Assert-QAExactString $oci.mediaType 'application/vnd.oci.image.index.v1+json'
    Assert-QAInteger $oci.schemaVersion 2
    if ($oci.schemaVersion -ne 2 -or $oci.mediaType -cne 'application/vnd.oci.image.index.v1+json' -or
        $oci.manifests -isnot [array] -or $oci.manifests.Count -ne 1) { throw 'Unsupported OCI index.' }
    $descriptor = $oci.manifests[0]
    Assert-QAProperties $descriptor @('mediaType', 'digest', 'size', 'annotations')
    Assert-QAExactString $descriptor.mediaType 'application/vnd.oci.image.manifest.v1+json'
    Assert-QAString $descriptor.digest
    Assert-QAProperties $descriptor.annotations @('io.containerd.image.name', 'org.opencontainers.image.ref.name')
    $tagParts = $ExpectedTag.Split(':')
    Assert-QAExactString $descriptor.annotations.'io.containerd.image.name' ('docker.io/library/'+$ExpectedTag)
    Assert-QAExactString $descriptor.annotations.'org.opencontainers.image.ref.name' $tagParts[1]
    if ($descriptor.mediaType -cne 'application/vnd.oci.image.manifest.v1+json' -or $descriptor.digest -cnotmatch '^sha256:([0-9a-f]{64})\z') { throw 'Unsupported OCI image descriptor.' }
    $ociPath = 'blobs/sha256/' + $Matches[1]
    if (-not $byName.ContainsKey($ociPath) -or $byName[$ociPath].Size -ne $descriptor.size) { throw 'OCI manifest blob is missing or has a wrong size.' }
    Assert-QAInteger $descriptor.size $byName[$ociPath].Size
    if ($descriptor.annotations.'io.containerd.image.name' -cne ('docker.io/library/'+$ExpectedTag) -or
        $descriptor.annotations.'org.opencontainers.image.ref.name' -cne $tagParts[1]) { throw 'OCI tag annotations differ from the expected tag.' }
    $ociManifest = ConvertFrom-QAJson (Read-QAEntryBytes $Stream $byName[$ociPath] $MaxMetadataBytes)
    Assert-QAProperties $ociManifest @('schemaVersion', 'mediaType', 'config', 'layers')
    Assert-QAProperties $ociManifest.config @('mediaType', 'digest', 'size')
    Assert-QAExactString $ociManifest.mediaType 'application/vnd.oci.image.manifest.v1+json'
    Assert-QAExactString $ociManifest.config.mediaType 'application/vnd.oci.image.config.v1+json'
    Assert-QAExactString $ociManifest.config.digest $ExpectedConfigDigest
    Assert-QAInteger $ociManifest.schemaVersion 2
    Assert-QAInteger $ociManifest.config.size $byName[$image.Config].Size
    if ($ociManifest.schemaVersion -ne 2 -or $ociManifest.mediaType -cne $descriptor.mediaType -or
        $ociManifest.config.mediaType -cne 'application/vnd.oci.image.config.v1+json' -or
        $ociManifest.config.digest -cne $ExpectedConfigDigest -or $ociManifest.config.size -ne $byName[$image.Config].Size -or
        $ociManifest.layers -isnot [array] -or $ociManifest.layers.Count -ne $image.Layers.Count) { throw 'OCI image config or layer structure differs.' }
    for ($i=0; $i -lt $image.Layers.Count; $i++) {
        $layer = $ociManifest.layers[$i]
        Assert-QAProperties $layer @('mediaType', 'digest', 'size')
        Assert-QAExactString $layer.mediaType 'application/vnd.oci.image.layer.v1.tar'
        Assert-QAExactString $layer.digest $digests[$i]
        Assert-QAInteger $layer.size $byName[$image.Layers[$i]].Size
        if ($layer.digest -cne $digests[$i] -or $layer.mediaType -cne 'application/vnd.oci.image.layer.v1.tar' -or
            $layer.size -ne $byName[$image.Layers[$i]].Size) { throw 'OCI layer order, size or identity differs.' }
    }
    $repositories = $metadata['repositories']
    Assert-QAProperties $repositories @($tagParts[0])
    Assert-QAProperties $repositories.($tagParts[0]) @($tagParts[1])
    Assert-QAString $repositories.($tagParts[0]).($tagParts[1])
    if ($repositories.($tagParts[0]).($tagParts[1]) -cnotmatch '^[0-9a-f]{64}\z') { throw 'Malformed legacy repository identity.' }
    Assert-QAProperties $metadata['oci-layout'] @('imageLayoutVersion')
    Assert-QAExactString $metadata['oci-layout'].imageLayoutVersion '1.0.0'
    if ($metadata['oci-layout'].imageLayoutVersion -cne '1.0.0') { throw 'Unsupported OCI layout version.' }
    $labels=$null
    if ($config.PSObject.Properties['config'] -and $config.config -is [pscustomobject] -and $config.config.PSObject.Properties['Labels']) {
        $labels=$config.config.Labels
    }
    return [pscustomobject]@{ArchiveSha256=$sha; ConfigDigest=$ExpectedConfigDigest; Tag=$ExpectedTag;
        Entries=$index.Entries; ExpandedBytes=$index.ExpandedBytes; Metadata=$metadata;
        Blobs=$blobs; Layers=$image.Layers; LayerSources=$image.LayerSources; Labels=$labels;
        OciLayoutSha256=(Get-QARangeSha256 $Stream $byName['oci-layout'].Offset $byName['oci-layout'].Size)}
}

function Get-QualificationArchiveInspection {
    param([Parameter(Mandatory=$true)][string]$Archive,
          [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}\z')][string]$ExpectedArchiveSha256,
          [Parameter(Mandatory=$true)][string]$ExpectedTag,
          [Parameter(Mandatory=$true)][ValidatePattern('^sha256:[0-9a-f]{64}\z')][string]$ExpectedConfigDigest,
          [ValidateRange(1,4096)][int]$MaxEntries=4096,
          [ValidateRange(1,17179869184)][long]$MaxArchiveBytes=17179869184,
          [ValidateRange(1,17179869184)][long]$MaxExpandedBytes=17179869184,
          [ValidateRange(1,1048576)][int]$MaxMetadataBytes=1048576)
    $ErrorActionPreference = 'Stop'
    $path = Assert-QAPlainPath $Archive -MustExist
    $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($stream.Length -gt $MaxArchiveBytes) { throw 'Archive size bound exceeded.' }
        return Read-QAArchive $stream $ExpectedArchiveSha256 $ExpectedTag $ExpectedConfigDigest $MaxEntries $MaxExpandedBytes $MaxMetadataBytes
    } finally { $stream.Dispose() }
}

function Get-QAWindowsTar {
    $windows = [Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)
    foreach ($directory in @('Sysnative','System32')) {
        $candidate = Join-Path $windows ($directory+'\tar.exe')
        if ([IO.File]::Exists($candidate)) { return $candidate }
    }
    throw 'The built-in Windows tar.exe is required.'
}

function New-QualifiedDockerArchive {
    param([Parameter(Mandatory=$true)][string]$Archive,
          [Parameter(Mandatory=$true)][string]$DestinationDirectory,
          [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}\z')][string]$ExpectedArchiveSha256,
          [Parameter(Mandatory=$true)][ValidateSet('toefl-house-erp-app:local','toefl-house-erp-db:bundled','toefl-house-erp-cache:bundled')][string]$ExpectedTag,
          [Parameter(Mandatory=$true)][ValidatePattern('^th-qual-[a-z0-9]+(?:[._-][a-z0-9]+)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\z')][string]$QualifiedTag,
          [Parameter(Mandatory=$true)][ValidatePattern('^sha256:[0-9a-f]{64}\z')][string]$ExpectedConfigDigest,
          [ValidateRange(1,4096)][int]$MaxEntries=4096,
          [ValidateRange(1,17179869184)][long]$MaxArchiveBytes=17179869184,
          [ValidateRange(1,17179869184)][long]$MaxExpandedBytes=17179869184,
          [ValidateRange(1,1048576)][int]$MaxMetadataBytes=1048576)
    $ErrorActionPreference = 'Stop'
    if ($QualifiedTag.Length -gt 255 -or $QualifiedTag -cnotmatch '^th-qual-[a-z0-9]+(?:[._-][a-z0-9]+)*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\z') {
        throw 'Use a bounded qualification-only image alias with a lowercase repository.'
    }
    $source = Assert-QAPlainPath $Archive -MustExist
    $destination = Assert-QAPlainPath $DestinationDirectory
    $parent = [IO.Path]::GetDirectoryName($destination)
    $sourceParent = [IO.Path]::GetDirectoryName($source).TrimEnd('\')+'\'
    if (-not [IO.Directory]::Exists($parent) -or (Test-Path -LiteralPath $destination) -or
        $destination.StartsWith($sourceParent, [StringComparison]::OrdinalIgnoreCase) -or $destination.Length+96 -gt 248) {
        throw 'Choose a new short destination outside the input archive directory.'
    }
    $mutexKey = Get-QAHexSha256 ([Text.Encoding]::UTF8.GetBytes($destination.ToLowerInvariant()))
    $mutex = [Threading.Mutex]::new($false, 'Local\TOEFLHouseArchiveQualification-'+$mutexKey)
    $locked = $false
    $stream = $null
    try {
        $locked = $mutex.WaitOne(0)
        if (-not $locked -or (Test-Path -LiteralPath $destination)) { throw 'Another archive derivation already owns this destination.' }
        $stream = [IO.File]::Open($source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($stream.Length -gt $MaxArchiveBytes) { throw 'Archive size bound exceeded.' }
        $original = Read-QAArchive $stream $ExpectedArchiveSha256 $ExpectedTag $ExpectedConfigDigest $MaxEntries $MaxExpandedBytes $MaxMetadataBytes
        $free = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($destination)).AvailableFreeSpace
        if ($free -lt $original.ExpandedBytes+$stream.Length+64MB) { throw 'Insufficient space for verified archive staging and output.' }
        $tar = Get-QAWindowsTar
        $manifest = $original.Metadata['manifest.json']
        $manifest[0].RepoTags = @($QualifiedTag)
        $index = $original.Metadata['index.json']
        $index.manifests[0].annotations.'io.containerd.image.name' = 'docker.io/library/'+$QualifiedTag
        $index.manifests[0].annotations.'org.opencontainers.image.ref.name' = $QualifiedTag.Split(':')[1]
        $oldParts = $ExpectedTag.Split(':')
        $newParts = $QualifiedTag.Split(':')
        $legacyDigest = $original.Metadata['repositories'].($oldParts[0]).($oldParts[1])
        $repositories = [pscustomobject]@{($newParts[0])=[pscustomobject]@{($newParts[1])=$legacyDigest}}
        $encoding = [Text.UTF8Encoding]::new($false,$true)
        $rewrittenBytes = @{}
        $rewrittenHashes = @{}
        $rewriteObjects = @{'manifest.json'=$manifest; 'index.json'=$index; 'repositories'=$repositories}
        foreach ($name in $rewriteObjects.Keys) {
            $bytes = $encoding.GetBytes((ConvertTo-Json -InputObject $rewriteObjects[$name] -Depth 40 -Compress))
            if ($bytes.Length -gt $MaxMetadataBytes) { throw 'Generated archive metadata exceeds its bound.' }
            $rewrittenBytes[$name] = $bytes
            $rewrittenHashes[$name] = Get-QAHexSha256 $bytes
        }
        New-Item -ItemType Directory -Path ([Management.Automation.WildcardPattern]::Escape($destination)) -ErrorAction Stop | Out-Null
        $null = Assert-QAPlainPath $destination -MustExist
        $files = Join-Path $destination 'files'
        [IO.Directory]::CreateDirectory((Join-Path $files 'blobs\sha256')) | Out-Null
        $buffer = New-Object byte[] (1024 * 1024)
        foreach ($entry in $original.Entries) {
            if ($entry.Directory -or $rewrittenBytes.ContainsKey($entry.Name)) { continue }
            $target = Join-Path $files $entry.Name.Replace('/','\')
            $output = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $stream.Position = $entry.Offset
                $remaining = $entry.Size
                while ($remaining -gt 0) {
                    $count = $stream.Read($buffer,0,[int][Math]::Min($remaining,$buffer.Length))
                    if ($count -le 0) { throw 'Source archive changed or ended during staging.' }
                    $output.Write($buffer,0,$count); $remaining -= $count
                }
            } finally { $output.Dispose() }
        }
        foreach ($name in $rewrittenBytes.Keys) {
            $bytes = $rewrittenBytes[$name]
            $output = [IO.File]::Open((Join-Path $files $name), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $output.Write($bytes,0,$bytes.Length) } finally { $output.Dispose() }
        }
        $partial = Join-Path $destination 'qualified-image.partial.tar'
        $info = [Diagnostics.ProcessStartInfo]::new()
        $info.FileName = $tar
        $info.Arguments = '-cf "'+$partial+'" --format=ustar -C "'+$files+'" manifest.json index.json repositories oci-layout blobs'
        $info.UseShellExecute=$false; $info.CreateNoWindow=$true; $info.RedirectStandardError=$true
        $process = [Diagnostics.Process]::new(); $process.StartInfo=$info
        try {
            $null=$process.Start(); $errors=$process.StandardError.ReadToEnd(); $process.WaitForExit()
            if ($process.ExitCode -ne 0) { throw 'Stock Windows tar could not produce the isolated archive.' }
        } finally { $process.Dispose() }
        $derivedStream = [IO.File]::OpenRead($partial)
        try {
            $derivedSha = Get-QARangeSha256 $derivedStream 0 $derivedStream.Length
            $derived = Read-QAArchive $derivedStream $derivedSha $QualifiedTag $ExpectedConfigDigest $MaxEntries $MaxExpandedBytes $MaxMetadataBytes `
                -ExpectedRewrittenMetadataSha256 $rewrittenHashes
        } finally { $derivedStream.Dispose() }
        if (($original.Layers -join '|') -cne ($derived.Layers -join '|') -or
            (ConvertTo-Json -InputObject $original.LayerSources -Depth 30 -Compress) -cne (ConvertTo-Json -InputObject $derived.LayerSources -Depth 30 -Compress) -or
            $original.Blobs.Count -ne $derived.Blobs.Count) { throw 'Derived archive changed immutable image descriptors.' }
        if ($original.OciLayoutSha256 -cne $derived.OciLayoutSha256) { throw 'Derived archive changed immutable OCI layout bytes.' }
        foreach ($name in $original.Blobs.Keys) { if ($derived.Blobs[$name] -cne $original.Blobs[$name]) { throw 'Derived archive changed a blob.' } }
        foreach ($entry in $original.Entries) {
            if ($entry.Directory -or $entry.Name -cin @('manifest.json','index.json','repositories')) { continue }
            $after = @($derived.Entries | Where-Object {$_.Name -ceq $entry.Name})
            if ($after.Count -ne 1 -or $after[0].Size -ne $entry.Size) { throw 'Derived archive changed an immutable member.' }
        }
        $final = Join-Path $destination 'qualified-image.tar'
        [IO.File]::Move($partial,$final)
        $receipt = [ordered]@{schema='toefl-house-isolated-archive/1';scope='ARCHIVE DERIVATION ONLY; NO DOCKER IMPORT';
            production_authorization='REJECT';original_archive_sha256=$ExpectedArchiveSha256;derived_archive_sha256=$derivedSha;
            original_tag=$ExpectedTag;qualified_tag=$QualifiedTag;config_digest=$ExpectedConfigDigest;
            ordered_layers=@($derived.Layers);layer_sources=$derived.LayerSources;
            immutable_oci_layout_sha256=$derived.OciLayoutSha256;
            blob_sha256=$derived.Blobs;immutable_blobs_verified=$derived.Blobs.Count;
            changed_members=@('manifest.json','index.json','repositories');rewritten_metadata_sha256=$rewrittenHashes;output_archive=$final}
        $receiptStream = [IO.File]::Open((Join-Path $destination 'qualification.json'),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $receiptBytes = $encoding.GetBytes(($receipt | ConvertTo-Json -Depth 40))
            $receiptStream.Write($receiptBytes,0,$receiptBytes.Length)
        } finally { $receiptStream.Dispose() }
        return [pscustomobject]$receipt
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
