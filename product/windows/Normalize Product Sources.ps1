$ErrorActionPreference = "Stop"

$utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$textExtensions = @(
    ".py", ".sh", ".js", ".json", ".css", ".md", ".txt", ".toml",
    ".yaml", ".yml", ".html", ".xml", ".csv", ".svg", ".jinja", ".jinja2"
)

function Get-FullPathWithinRoot([string]$Root, [string]$RelativePath) {
    $platformSeparator = ([System.IO.Path]::DirectorySeparatorChar).ToString()
    $platformRelative = $RelativePath.Replace("/", $platformSeparator)
    if ($RelativePath -match '(^|[/\\])\.{1,2}([/\\]|$)') {
        throw "Dockerfile COPY source may not use relative traversal: $RelativePath"
    }
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $Root $platformRelative))
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar,
                           [System.IO.Path]::AltDirectorySeparatorChar)
    $prefix = $Root.TrimEnd($trimChars) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Dockerfile source escapes the repository: $RelativePath"
    }
    $current = $Root
    foreach ($part in ($RelativePath -split "[/\\]+")) {
        $current = Join-Path $current $part
        if (Test-Path -LiteralPath $current) {
            $component = Get-Item -LiteralPath $current -Force
            if (($component.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Dockerfile COPY path contains a link/junction; refusing to follow it: $current"
            }
        }
    }
    return $candidate
}

function Add-SourceFiles([string]$Path, [System.Collections.ArrayList]$Files) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Dockerfile COPY source is missing: $Path"
    }
    $sourceItem = Get-Item -LiteralPath $Path -Force
    if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Dockerfile COPY source is a link/junction; refusing to follow it: $Path"
    }
    if ($sourceItem.PSIsContainer) {
        Get-ChildItem -LiteralPath $Path -Recurse -Force |
            ForEach-Object {
                if (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Dockerfile COPY tree contains a link/junction; refusing to follow or rewrite it: $($_.FullName)"
                }
                if (-not $_.PSIsContainer) { [void]$Files.Add($_.FullName) }
            }
    } else {
        [void]$Files.Add([System.IO.Path]::GetFullPath($Path))
    }
}

try {
    $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
    $rootItem = Get-Item -LiteralPath $repositoryRoot -Force
    if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Repository root is a link/junction; refusing to normalize through it: $repositoryRoot"
    }
    $dockerfilePath = Join-Path $repositoryRoot "product\app.Dockerfile"
    if (-not (Test-Path -LiteralPath $dockerfilePath -PathType Leaf)) {
        throw "Product Dockerfile not found: $dockerfilePath"
    }

    $files = New-Object System.Collections.ArrayList
    $seen = @{}
    foreach ($rawLine in [System.IO.File]::ReadAllLines($dockerfilePath, $utf8Strict)) {
        $line = $rawLine.Trim()
        if ($line -match "^ADD\s+") {
            throw "Dockerfile ADD is not supported by the build-context normalizer; audit its source explicitly."
        }
        if ($line -notmatch "^COPY\s+") { continue }
        if ($line.EndsWith([string][char]92)) {
            throw "Multiline Dockerfile COPY syntax is unsupported; update the normalizer before building: $line"
        }
        $parts = $line -split "\s+"
        if ($parts.Length -ne 3 -or $parts[1].StartsWith("--") -or $parts[1].Contains("*")) {
            throw "Unsupported Dockerfile COPY syntax; update the normalizer before building: $line"
        }
        $source = Get-FullPathWithinRoot $repositoryRoot $parts[1]
        if (-not $seen.ContainsKey($source)) {
            $seen[$source] = $true
            Add-SourceFiles $source $files
        }
    }

    # These files govern Docker's context selection and build/runtime wiring.
    # They are not application data and may safely be line-ending normalized.
    foreach ($relative in @(".gitattributes", ".dockerignore", "product\app.Dockerfile",
                            "product\docker-compose.yml")) {
        $path = Get-FullPathWithinRoot $repositoryRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Product build-control file is missing: $relative"
        }
        Add-SourceFiles $path $files
    }

    $changed = 0
    foreach ($path in ($files | Select-Object -Unique)) {
        # These generated Python artifacts are excluded by .dockerignore and
        # are not source files. Runtime state under product/data is never a
        # Dockerfile COPY source and is never traversed here.
        if ($path -match "[\\/]__pycache__[\\/]" -or $path.EndsWith(".pyc",
                [System.StringComparison]::OrdinalIgnoreCase)) { continue }

        $extension = [System.IO.Path]::GetExtension($path).ToLowerInvariant()
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $hasUtf8Bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and
                      $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
        $hasUtf16Bom = $bytes.Length -ge 2 -and
                       (($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) -or
                        ($bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF))
        $hasUtf32Bom = $bytes.Length -ge 4 -and
                       (($bytes[0] -eq 0x00 -and $bytes[1] -eq 0x00 -and
                         $bytes[2] -eq 0xFE -and $bytes[3] -eq 0xFF) -or
                        ($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE -and
                         $bytes[2] -eq 0x00 -and $bytes[3] -eq 0x00))
        $hasCr = [System.Array]::IndexOf($bytes, [byte]0x0D) -ge 0
        $isKnownText = $textExtensions -contains $extension -or
                       $path -match "[\\/]\.gitattributes$" -or
                       $path -match "[\\/]\.dockerignore$" -or
                       $path -match "[\\/]app\.Dockerfile$"

        if (-not $isKnownText) {
            if ($hasUtf8Bom -or $hasUtf16Bom -or $hasUtf32Bom -or $hasCr) {
                throw "Unclassified Dockerfile source contains a BOM or CR byte: $path"
            }
            continue
        }
        if ($hasUtf16Bom -or $hasUtf32Bom) {
            throw "Product build source must be UTF-8, not UTF-16/UTF-32: $path"
        }

        $offset = if ($hasUtf8Bom) { 3 } else { 0 }
        $text = $utf8Strict.GetString($bytes, $offset, $bytes.Length - $offset)
        $normalized = $text.Replace("`r`n", "`n").Replace("`r", "`n")
        $normalizedBytes = $utf8NoBom.GetBytes($normalized)
        $needsWrite = $hasUtf8Bom -or $hasCr
        if ($needsWrite) {
            [System.IO.File]::WriteAllBytes($path, $normalizedBytes)
            $changed++
            Write-Host "Normalized product build source: $path"
        }
    }

    if ($changed -gt 0) {
        Write-Host "NORMALIZED_FILES=$changed"
        exit 10
    }
    Write-Host "NORMALIZED_FILES=0; all product build sources are UTF-8 without BOM and LF-only."
    exit 0
} catch {
    [Console]::Error.WriteLine("Product source normalization failed safely: " + $_.Exception.Message)
    exit 1
}
