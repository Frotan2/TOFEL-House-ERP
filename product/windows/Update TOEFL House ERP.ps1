# TOEFL House ERP - signed, fail-closed update workflow for Windows.
#
# Check   reads the provider's trusted update channel, downloads a signed
#         release index, manifest, signature and prebuilt image archive, and
#         asks the update engine for an allow/refuse decision.  It changes no
#         site file, no Docker volume and no service state.
# Install repeats Check and only when the engine allows it: stops the
#         application services, imports the verified prebuilt image, runs the
#         supported migration with a business-record census, starts the stack
#         and verifies health.  It never builds Frappe, never removes a Docker
#         volume or prunes Docker state, never resets Docker and never restores
#         over live data.
#
# The engine (product/update_engine.py, shipped inside the application image)
# owns every trust decision.  A SHA-256 sidecar alone is never accepted as
# publisher identity; only a manifest signed by a key in the provisioned trust
# store can authorize an update.  When any precondition cannot be verified the
# script stops before changing anything and explains why in English and Dari.
param(
    [ValidateSet("Check", "Install")]
    [string]$Action = "Check",
    [switch]$ConfirmationAccepted,
    [switch]$SmokeTest
)
$ErrorActionPreference = "Stop"

$script:ExitAllowed = 0
$script:ExitRefused = 3
$script:ExitRequestInvalid = 4
$script:ExitFailed = 5
$script:ExitRecoveryRequired = 6

$productRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$dataRoot = Join-Path $productRoot "data"
$updatesRoot = Join-Path $dataRoot "updates"
$runsRoot = Join-Path $updatesRoot "runs"
$sitesRoot = Join-Path $dataRoot "sites"
$logsRoot = Join-Path $dataRoot "logs"
$channelPath = Join-Path $productRoot "updates\channel.json"
$trustStorePath = Join-Path $updatesRoot "trust-store.json"
$journalPath = Join-Path $updatesRoot "journal.json"
$resultPath = Join-Path $updatesRoot "last-result.json"
$lockPath = Join-Path $updatesRoot "update.lock"
$backupReceiptPath = Join-Path $dataRoot "activation\backup-receipt.json"
$recoveryAuthorizationPath = Join-Path $updatesRoot "recovery-authorization.json"
$recoverySignaturePath = Join-Path $updatesRoot "recovery-authorization.sig"
$composeFile = Join-Path $productRoot "docker-compose.yml"
$catalogPath = Join-Path $PSScriptRoot "updater-strings.json"
$siteName = "toeflhouse.localhost"
$imageTag = "toefl-house-erp-app:local"
$volumeName = "toefl-house-erp_db-data"
$composeProject = "toefl-house-erp"
$containerProductRoot = "/product-root"
$containerWorkRoot = "/update"
$maxIndexBytes = 1048576
$maxJsonBytes = 262144
$maxArchiveBytes = [int64]17179869184
$minArchiveBytes = [int64]4096
$minFreeBytes = [int64]32212254720

$script:Catalog = $null
$script:WorkDir = ""
$script:BackupDirRelative = ""

# ---------------------------------------------------------------------------
# Bilingual catalogue, result document and stage output
# ---------------------------------------------------------------------------

function Get-Catalog {
    if ($null -ne $script:Catalog) { return $script:Catalog }
    if (-not (Test-Path -LiteralPath $catalogPath -PathType Leaf)) {
        throw "The update message catalogue is missing from this package."
    }
    $encoding = New-Object System.Text.UTF8Encoding($false, $true)
    $text = [System.IO.File]::ReadAllText($catalogPath, $encoding)
    $catalog = $text | ConvertFrom-Json -ErrorAction Stop
    if ($catalog.schema_version -ne 1 -or
        $catalog.document_type -cne "toefl-house-erp-updater-strings") {
        throw "The update message catalogue is not supported."
    }
    $script:Catalog = $catalog
    return $catalog
}

function Get-Text([string]$Section, [string]$Key) {
    $catalog = Get-Catalog
    $entries = $catalog.$Section
    if ($null -eq $entries) { return $null }
    $entry = $entries.$Key
    if ($null -eq $entry) { return $null }
    if (-not ($entry.en -is [string]) -or -not ($entry.fa -is [string])) { return $null }
    if (-not $entry.en -or -not $entry.fa) { return $null }
    return $entry
}

function Write-Stage([string]$Key) {
    $entry = Get-Text "launcher" $Key
    if ($null -eq $entry) {
        Write-Host ("[TH_STAGE] " + $Key)
        return
    }
    Write-Host ("[TH_STAGE] " + $entry.en)
    Write-Host ("[TH_STAGE-FA] " + $entry.fa)
}

function Write-Bilingual([string]$Section, [string]$Key) {
    $entry = Get-Text $Section $Key
    if ($null -eq $entry) {
        Write-Host ("[" + $Section + "] " + $Key)
        return
    }
    Write-Host $entry.en
    Write-Host $entry.fa
}

function Save-Result {
    param(
        [string]$Status,
        [string]$Section,
        [string]$Key,
        [string]$Version,
        [string[]]$Blockers = @()
    )
    try {
        if (-not (Test-Path -LiteralPath $updatesRoot -PathType Container)) {
            New-Item -ItemType Directory -Path $updatesRoot -Force | Out-Null
        }
        $document = [ordered]@{
            schema_version = 1
            document_type = "toefl-house-erp-updater-result"
            status = $Status
            message_section = $Section
            message_key = $Key
            version = $Version
            blockers = $Blockers
            generated_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        }
        $text = $document | ConvertTo-Json -Depth 6
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($resultPath, $text + [Environment]::NewLine, $encoding)
    } catch {
        # A result document is a convenience for the graphical launcher.  The
        # console output and exit code remain authoritative if it cannot be
        # written, so a failure here never changes the safety decision.
    }
}

function Stop-Update {
    param(
        [int]$Code,
        [string]$Status,
        [string]$Section,
        [string]$Key,
        [string]$Version = "",
        [string[]]$Blockers = @()
    )
    Save-Result -Status $Status -Section $Section -Key $Key -Version $Version -Blockers $Blockers
    Write-Host ""
    Write-Bilingual $Section $Key
    if ($Blockers.Count -gt 0) {
        Write-Host ""
        foreach ($code in $Blockers) {
            Write-Bilingual "messages" $code
        }
    }
    exit $Code
}

# ---------------------------------------------------------------------------
# Small validators (also exercised by -SmokeTest)
# ---------------------------------------------------------------------------

function Read-JsonFile([string]$Path, [string]$Label, [int64]$MaximumBytes) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw ($Label + " is missing.") }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Length -gt $MaximumBytes) { throw ($Label + " is larger than allowed.") }
    $encoding = New-Object System.Text.UTF8Encoding($false, $true)
    $text = [System.IO.File]::ReadAllText($Path, $encoding)
    $value = $null
    try { $value = $text | ConvertFrom-Json -ErrorAction Stop } catch { throw ($Label + " is not valid JSON.") }
    if ($null -eq $value -or $value -isnot [pscustomobject]) { throw ($Label + " must be a JSON object.") }
    return $value
}

function Assert-SafeAssetName([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return $false }
    if ($Name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') { return $false }
    if ($Name.Contains("..")) { return $false }
    return $true
}

function Test-AllowedUrl([string]$Url, $AllowedHosts) {
    if ([string]::IsNullOrWhiteSpace($Url)) { return $false }
    $uri = $null
    if (-not [System.Uri]::TryCreate($Url, [System.UriKind]::Absolute, [ref]$uri)) { return $false }
    if ($uri.Scheme -cne "https") { return $false }
    if ($uri.UserInfo) { return $false }
    if ($uri.Fragment) { return $false }
    if (-not $uri.IsDefaultPort) { return $false }
    $hostName = $uri.Host.ToLowerInvariant()
    foreach ($allowed in @($AllowedHosts)) {
        if ($hostName -ceq ([string]$allowed).ToLowerInvariant()) { return $true }
    }
    return $false
}

function ConvertTo-ReleaseSequence([string]$Version) {
    if ([string]::IsNullOrWhiteSpace($Version)) { throw "Version is empty." }
    $match = [regex]::Match($Version, '^([0-9]{1,4})(?:\.([0-9]{1,2}))?(?:\.([0-9]{1,2}))?(?:\.([0-9]{1,2}))?$')
    if (-not $match.Success) { throw "Version is not a plain numeric release." }
    $numbers = @(0, 0, 0, 0)
    for ($index = 1; $index -le 4; $index++) {
        $group = $match.Groups[$index]
        if ($group.Success) { $numbers[$index - 1] = [int]$group.Value }
    }
    if ($numbers[0] -lt 1 -or $numbers[0] -gt 2147) { throw "Version year is outside the supported range." }
    for ($index = 1; $index -le 3; $index++) {
        if ($numbers[$index] -gt 99) { throw "Version component is outside the supported range." }
    }
    $value = [int64]$numbers[0] * 1000000 + [int64]$numbers[1] * 10000 +
             [int64]$numbers[2] * 100 + [int64]$numbers[3]
    if ($value -lt 1 -or $value -gt 2147483647) { throw "Release sequence is outside the supported range." }
    return [int]$value
}

# ---------------------------------------------------------------------------
# Journal, lock and folder protection
# ---------------------------------------------------------------------------

function Get-JournalState {
    if (-not (Test-Path -LiteralPath $journalPath -PathType Leaf)) { return "idle" }
    try {
        $journal = Read-JsonFile $journalPath "The update journal" $maxJsonBytes
    } catch {
        return "unknown"
    }
    if ($journal.schema_version -ne 1 -or $journal.document_type -cne "toefl-house-erp-update-journal") {
        return "unknown"
    }
    $phase = [string]$journal.phase
    foreach ($allowed in @("idle", "prepared", "applying", "completed", "rolled-back", "recovery-required")) {
        if ($phase -ceq $allowed) { return $phase }
    }
    return "unknown"
}

function Set-JournalState([string]$Phase, [string]$Version) {
    try {
        if (-not (Test-Path -LiteralPath $updatesRoot -PathType Container)) {
            New-Item -ItemType Directory -Path $updatesRoot -Force | Out-Null
        }
        $document = [ordered]@{
            schema_version = 1
            document_type = "toefl-house-erp-update-journal"
            phase = $Phase
            version = $Version
            updated_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        }
        $text = $document | ConvertTo-Json -Depth 4
        $temporary = $journalPath + ".tmp"
        $encoding = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($temporary, $text + [Environment]::NewLine, $encoding)
        Move-Item -LiteralPath $temporary -Destination $journalPath -Force
    } catch {
        # The journal protects the next run from resuming over a half-finished
        # update.  If it cannot be written the caller treats the run as failed
        # and never starts a migration.
        throw "The update journal could not be written. No update was started."
    }
}

function Enter-UpdateLock {
    if (-not (Test-Path -LiteralPath $updatesRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $updatesRoot -Force | Out-Null
    }
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        $age = (Get-Date) - (Get-Item -LiteralPath $lockPath).LastWriteTime
        if ($age.TotalHours -lt 6) { return $false }
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
    try {
        $stream = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::CreateNew,
                                         [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes(
                (Get-Date).ToUniversalTime().ToString("o") + " pid=" + $PID)
            $stream.Write($bytes, 0, $bytes.Length)
        } finally {
            $stream.Dispose()
        }
        return $true
    } catch {
        return $false
    }
}

function Exit-UpdateLock {
    try { Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue } catch { }
}

function Protect-UpdateFolder {
    try {
        if (-not (Test-Path -LiteralPath $updatesRoot -PathType Container)) {
            New-Item -ItemType Directory -Path $updatesRoot -Force | Out-Null
            # Best-effort: the folder holds the trust anchor and downloaded
            # release bytes.  Its contents are never readable by other local
            # users on a default NTFS profile; a non-NTFS drive keeps its own
            # inherited rights and the engine still fails closed.
            & icacls $updatesRoot /inheritance:r /grant:r "$env:USERDOMAIN\$env:USERNAME:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /T *> $null
        }
    } catch { }
}

# ---------------------------------------------------------------------------
# Docker access
# ---------------------------------------------------------------------------

function Invoke-Docker([string[]]$DockerArguments) {
    $output = @(& docker @DockerArguments 2>&1)
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Code = [int]$code; Output = $output }
}

function Invoke-DockerVerbose([string[]]$DockerArguments) {
    $result = Invoke-Docker $DockerArguments
    foreach ($line in @($result.Output)) { Write-Host ([string]$line) }
    return $result.Code
}

function Get-DockerCommand {
    if (Get-Command docker -ErrorAction SilentlyContinue) { return "docker" }
    $candidate = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $env:PATH = (Split-Path -Parent $candidate) + ";" + $env:PATH
        return "docker"
    }
    return ""
}

function Test-DockerEngine {
    $result = Invoke-Docker @("info")
    return ($result.Code -eq 0)
}

function Get-ContainerStatus([string]$Name) {
    $result = Invoke-Docker @("inspect", "--format", "{{.State.Status}}", $Name)
    if ($result.Code -ne 0) { return $null }
    $text = (($result.Output | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if (-not $text) { return $null }
    return ($text -ceq "running")
}

function Get-InstalledImage {
    $result = Invoke-Docker @("image", "inspect", $imageTag, "--format", "{{json .}}")
    if ($result.Code -ne 0) { return $null }
    $text = (($result.Output | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if (-not $text) { return $null }
    try { $image = $text | ConvertFrom-Json -ErrorAction Stop } catch { return $null }
    if ($null -eq $image -or $image -isnot [pscustomobject]) { return $null }
    return $image
}

function Get-DriveFreeBytes([string]$Path) {
    $root = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($Path))
    $name = $root.Substring(0, 1)
    $drive = Get-PSDrive -Name $name -ErrorAction Stop
    return [int64]$drive.Free
}

function Invoke-Compose([string[]]$ComposeArguments) {
    $all = @("compose", "--file", $composeFile) + $ComposeArguments
    return (Invoke-DockerVerbose $all)
}

# ---------------------------------------------------------------------------
# Host facts and installed identity
# ---------------------------------------------------------------------------

function Get-HostFacts($Image) {
    $imageId = ""
    $labelMap = [ordered]@{}
    if ($null -ne $Image) {
        if ($null -ne $Image.Id) { $imageId = [string]$Image.Id }
        if ($null -ne $Image.Config.Labels) {
            foreach ($property in $Image.Config.Labels.PSObject.Properties) {
                $labelMap[[string]$property.Name] = [string]$property.Value
            }
        }
    }
    $labelObject = $null
    if ($labelMap.Count -gt 0) { $labelObject = [pscustomobject]$labelMap }

    $volumeList = Invoke-Docker @("volume", "ls", "--filter", ("name=" + $volumeName), "--format", "{{.Name}}")
    $volumePresent = $false
    foreach ($line in @($volumeList.Output)) {
        if (([string]$line).Trim() -ceq $volumeName) { $volumePresent = $true }
    }
    $volumeVerified = $false
    if ($volumePresent) {
        $inspect = Invoke-Docker @("volume", "inspect", $volumeName)
        $volumeVerified = ($inspect.Code -eq 0)
    }

    $free = [int64]0
    try { $free = Get-DriveFreeBytes $productRoot } catch { $free = [int64]0 }

    return [pscustomobject][ordered]@{
        disk_free_bytes = $free
        volume_present = [bool]$volumePresent
        volume_verified = [bool]$volumeVerified
        services = [pscustomobject][ordered]@{
            db = (Get-ContainerStatus "toefl-house-erp-db")
            redis_cache = (Get-ContainerStatus "toefl-house-erp-redis-cache")
            redis_queue = (Get-ContainerStatus "toefl-house-erp-redis-queue")
            web = (Get-ContainerStatus "toefl-house-erp-web")
        }
        image_present = ($null -ne $Image)
        image_id = $imageId
        image_labels = $labelObject
        site_credentials_present = (Test-Path -LiteralPath (Join-Path $dataRoot "secrets\db.env") -PathType Leaf)
        site_config_present = (Test-Path -LiteralPath (Join-Path $sitesRoot ($siteName + "\site_config.json")) -PathType Leaf)
    }
}

function New-InstalledIdentity($Facts) {
    $version = ""
    $revision = ""
    if ($null -ne $Facts.image_labels) {
        $labels = $Facts.image_labels
        if ($null -ne $labels.'org.toefl-house.release-version') {
            $version = [string]$labels.'org.toefl-house.release-version'
        }
        if ($null -ne $labels.'org.toefl-house.source-revision') {
            $revision = [string]$labels.'org.toefl-house.source-revision'
        }
    }
    $sequence = $null
    try { $sequence = ConvertTo-ReleaseSequence $version } catch { $sequence = $null }
    return [pscustomobject][ordered]@{
        version = $version
        release_sequence = $sequence
        source_revision = $revision
        image_labels = $Facts.image_labels
        image_id = [string]$Facts.image_id
    }
}

# ---------------------------------------------------------------------------
# Trusted channel download
# ---------------------------------------------------------------------------

function Get-Channel {
    if (-not (Test-Path -LiteralPath $channelPath -PathType Leaf)) {
        Stop-Update $script:ExitRefused "not-configured" "launcher" "updater.not_configured"
    }
    try {
        $config = Read-JsonFile $channelPath "The update channel configuration" $maxJsonBytes
    } catch {
        Stop-Update $script:ExitRefused "not-configured" "launcher" "updater.not_configured"
    }
    if ($config.schema_version -ne 1 -or
        $config.document_type -cne "toefl-house-erp-update-channels" -or
        $config.product -cne "TOEFL House ERP") {
        Stop-Update $script:ExitRefused "not-configured" "launcher" "updater.not_configured"
    }
    $selected = $null
    foreach ($entry in @($config.channels)) {
        if ([string]$entry.id -ceq [string]$config.default_channel) { $selected = $entry }
    }
    if ($null -eq $selected) {
        Stop-Update $script:ExitRefused "not-configured" "launcher" "updater.not_configured"
    }
    if ($selected.enabled -ne $true) {
        Stop-Update $script:ExitRefused "refused" "messages" "channel.disabled"
    }
    $allowed = @($selected.allowed_hosts)
    if ($allowed.Count -lt 1 -or $allowed.Count -gt 8) {
        Stop-Update $script:ExitRefused "refused" "messages" "channel.invalid"
    }
    if (-not (Test-AllowedUrl ([string]$selected.metadata_url) $allowed)) {
        Stop-Update $script:ExitRefused "refused" "messages" "channel.invalid"
    }
    return [pscustomobject]@{
        id = [string]$selected.id
        provider = [string]$selected.provider
        metadata_url = [string]$selected.metadata_url
        allowed_hosts = $allowed
        required_assets = @($selected.required_assets)
    }
}

function Get-TrustStorePresence {
    if (-not (Test-Path -LiteralPath $trustStorePath -PathType Leaf)) {
        Stop-Update $script:ExitRefused "refused" "messages" "trust.not_provisioned"
    }
    try {
        $store = Read-JsonFile $trustStorePath "The update trust store" $maxJsonBytes
    } catch {
        Stop-Update $script:ExitRefused "refused" "messages" "trust.invalid"
    }
    if ($store.document_type -cne "toefl-house-erp-update-trust-store" -or
        $store.provisioned -ne $true -or
        $null -eq $store.keys -or
        @($store.keys).Count -lt 1) {
        Stop-Update $script:ExitRefused "refused" "messages" "trust.not_provisioned"
    }
}

function Save-RemoteFile([string]$Url, [string]$Path, [int64]$MaximumBytes) {
    $partial = $Path + ".part"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue }
    $previousProtocol = [System.Net.ServicePointManager]::SecurityProtocol
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = "GET"
        $request.AllowAutoRedirect = $false
        $request.Timeout = 60000
        $request.ReadWriteTimeout = 120000
        $request.UserAgent = "TOEFL-House-ERP-Updater/1"
        $response = $request.GetResponse()
        try {
            if ([int]$response.StatusCode -ne 200) { throw "The update server did not answer with a file." }
            if ($response.ContentLength -gt $MaximumBytes) { throw "The update file is larger than allowed." }
            # $input is a read-only automatic variable in PowerShell; the
            # response stream needs its own name or the download always fails.
            $responseStream = $response.GetResponseStream()
            $output = [System.IO.File]::Create($partial)
            try {
                $buffer = New-Object byte[] 131072
                [int64]$total = 0
                while (($read = $responseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $total = $total + $read
                    if ($total -gt $MaximumBytes) { throw "The update file is larger than allowed." }
                    $output.Write($buffer, 0, $read)
                }
            } finally {
                $output.Dispose()
                $responseStream.Dispose()
            }
        } finally {
            $response.Dispose()
        }
        Move-Item -LiteralPath $partial -Destination $Path -Force
    } catch {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue }
        throw
    } finally {
        [System.Net.ServicePointManager]::SecurityProtocol = $previousProtocol
    }
}

function Resolve-ChannelUrl($Channel, [string]$Name) {
    if (-not (Assert-SafeAssetName $Name)) { throw "The update file name is not safe." }
    $baseUri = [System.Uri]::new([string]$Channel.metadata_url)
    $resolved = [System.Uri]::new($baseUri, $Name)
    if (-not (Test-AllowedUrl $resolved.AbsoluteUri $Channel.allowed_hosts)) {
        throw "The update file is not on an allowed provider host."
    }
    return $resolved.AbsoluteUri
}

# ---------------------------------------------------------------------------
# Engine protocol
# ---------------------------------------------------------------------------

function Invoke-UpdateEngine([string]$Mode) {
    $arguments = @(
        "run", "--rm", "--user", "root",
        "--volume", ($productRoot + ":" + $containerProductRoot + ":ro"),
        "--volume", ($script:WorkDir + ":" + $containerWorkRoot),
        "--entrypoint", "/product/update_entrypoint.sh"
    )
    if ($Mode -ceq "apply") {
        $arguments += @("--network", ($composeProject + "_default"))
        $arguments += @("--volume", ($sitesRoot + ":/home/frappe/bench/sites"))
        $arguments += @("--volume", ($logsRoot + ":/home/frappe/bench/logs"))
        if ($script:BackupDirRelative) {
            $arguments += @("--volume", ($script:BackupMount + ":" + $containerProductRoot + "/" + $script:BackupDirRelative + ":ro"))
        }
    } else {
        $arguments += @("--network", "none")
        if ($script:BackupDirRelative) {
            $arguments += @("--volume", ($script:BackupMount + ":" + $containerProductRoot + "/" + $script:BackupDirRelative + ":ro"))
        }
    }
    $arguments += $imageTag
    return (Invoke-DockerVerbose $arguments)
}

function Invoke-EngineStep([string]$Mode, $Request, [string]$Version) {
    # One request, one response, one fresh document.  A stale response from an
    # earlier phase must never be read back as if it belonged to this one.
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $script:WorkDir "request.json"),
        ($Request | ConvertTo-Json -Depth 12), $encoding)
    Remove-Item -LiteralPath (Join-Path $script:WorkDir "response.json") -Force -ErrorAction SilentlyContinue
    Write-Stage "updater.verifying"
    $engineExit = Invoke-UpdateEngine $Mode
    $response = Read-EngineResponse
    if ($null -eq $response) {
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.engine_failed" $Version
    }
    if ($response.document_type -cne "toefl-house-erp-update-engine-response") {
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.engine_failed" $Version
    }
    if ($engineExit -ne $script:ExitAllowed -and $engineExit -ne $script:ExitRefused) {
        # Exit 4/5 means the engine itself could not decide.  A stray allow in
        # that state would be a fail-open, so treat it as a hard stop.
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.engine_failed" $Version
    }
    return $response
}

function Assert-EngineAllowed($Response, [string]$Version) {
    $blockers = @(Get-BlockerCodes $Response)
    if ($Response.decision -ceq "allow") { return $blockers }
    $onlyDowngrade = ($blockers.Count -gt 0)
    foreach ($code in $blockers) {
        if ($code -cne "compat.downgrade") { $onlyDowngrade = $false }
    }
    if ($onlyDowngrade) {
        Save-Result -Status "up-to-date" -Section "launcher" -Key "updater.up_to_date" -Version $Version
        Write-Host ""
        Write-Bilingual "launcher" "updater.up_to_date"
        exit $script:ExitAllowed
    }
    $primary = "updater.failed"
    if ($blockers.Count -gt 0 -and $null -ne (Get-Text "messages" $blockers[0])) { $primary = $blockers[0] }
    Save-Result -Status "refused" -Section "messages" -Key $primary -Version $Version -Blockers $blockers
    Write-Host ""
    Write-Bilingual "messages" $primary
    if ($blockers.Count -gt 1) {
        Write-Host ""
        foreach ($code in $blockers) { Write-Bilingual "messages" $code }
    }
    exit $script:ExitRefused
}

function Read-EngineResponse {
    $responsePath = Join-Path $script:WorkDir "response.json"
    if (-not (Test-Path -LiteralPath $responsePath -PathType Leaf)) { return $null }
    try {
        return (Read-JsonFile $responsePath "The update engine response" 1048576)
    } catch {
        return $null
    }
}

function Get-BlockerCodes($Response) {
    $codes = @()
    if ($null -ne $Response -and $null -ne $Response.blockers) {
        foreach ($blocker in @($Response.blockers)) {
            if ($null -ne $blocker -and $null -ne $blocker.code) { $codes += [string]$blocker.code }
        }
    }
    return $codes
}

# ---------------------------------------------------------------------------
# Check pipeline (read-only)
# ---------------------------------------------------------------------------

function Invoke-UpdateCheck {
    Write-Stage "updater.checking"

    $docker = Get-DockerCommand
    if (-not $docker) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.engine_missing"
    }
    if (-not (Test-DockerEngine)) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.guard_blocked"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $dataRoot "secrets\db.env") -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $sitesRoot ($siteName + "\site_config.json")) -PathType Leaf)) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.not_installed"
    }
    $journalState = Get-JournalState
    if ($journalState -ceq "recovery-required") {
        Write-Stage "updater.recovery_steps"
        Stop-Update $script:ExitRecoveryRequired "recovery-required" "launcher" "updater.recovery_required"
    }
    if ($journalState -ceq "prepared" -or $journalState -ceq "applying") {
        Set-JournalState "recovery-required" ""
        Stop-Update $script:ExitRecoveryRequired "recovery-required" "launcher" "updater.interrupted"
    }
    if ($journalState -ceq "unknown") {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.interrupted"
    }

    $channel = Get-Channel
    Get-TrustStorePresence

    $image = Get-InstalledImage
    $facts = Get-HostFacts $image
    $installed = New-InstalledIdentity $facts
    if (-not $installed.release_sequence) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.installed_version_unknown"
    }

    # A verified independent backup must exist before any bytes are downloaded.
    # The engine re-verifies the same receipt and every artifact hash; this
    # early check only reports the reason without using the network.
    $script:BackupDirRelative = ""
    $script:BackupMount = ""
    if (-not (Test-Path -LiteralPath $backupReceiptPath -PathType Leaf)) {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.backup.receipt_missing"
    }
    $receipt = $null
    try { $receipt = Read-JsonFile $backupReceiptPath "The verified backup receipt" $maxJsonBytes } catch {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.backup.receipt_unreadable"
    }
    $backupPath = [string]$receipt.backup_path
    $backupDrive = [string]$receipt.backup_drive
    $backupSet = [string]$receipt.backup_set
    if (-not $backupPath -or -not $backupDrive -or -not (Assert-SafeAssetName $backupSet)) {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.backup.receipt_invalid"
    }
    if (-not (Test-Path -LiteralPath $backupPath -PathType Container)) {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.backup.artifact_invalid"
    }
    $expectedRoot = [System.IO.Path]::GetFullPath((Join-Path ($backupDrive + "\") "TOEFL-House-ERP-Backups"))
    $expectedSet = [System.IO.Path]::GetFullPath((Join-Path $expectedRoot $backupSet))
    if (-not [string]::Equals([System.IO.Path]::GetFullPath($backupPath), $expectedSet,
                              [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.backup.receipt_invalid"
    }
    $script:BackupMount = $backupPath
    $script:BackupDirRelative = "data/update-backup-set"

    $free = [int64]0
    try { $free = Get-DriveFreeBytes $productRoot } catch { $free = [int64]0 }
    if ($free -lt ($minFreeBytes + $minArchiveBytes)) {
        Stop-Update $script:ExitRefused "refused" "messages" "preflight.disk.insufficient"
    }

    # Download into a private run folder.  Nothing is extracted or executed.
    if (-not (Test-Path -LiteralPath $runsRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $runsRoot -Force | Out-Null
    }
    $runId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
    $script:WorkDir = Join-Path $runsRoot $runId
    New-Item -ItemType Directory -Path $script:WorkDir -Force | Out-Null

    Write-Stage "updater.downloading"
    $indexPath = Join-Path $script:WorkDir "index.json"
    try {
        Save-RemoteFile $channel.metadata_url $indexPath $maxIndexBytes
    } catch {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.network_failed"
    }
    try {
        $index = Read-JsonFile $indexPath "The update index" $maxIndexBytes
    } catch {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.package_invalid"
    }
    if ($index.schema_version -ne 1 -or
        $index.document_type -cne "toefl-house-erp-update-index" -or
        $index.product -cne "TOEFL House ERP" -or
        [string]$index.channel -cne $channel.id -or
        $null -eq $index.latest) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.package_invalid"
    }
    $latest = $index.latest
    $targetVersion = [string]$latest.version
    $manifestName = [string]$latest.manifest
    $signatureName = [string]$latest.signature
    $archiveName = [string]$latest.archive
    if (-not (Assert-SafeAssetName $targetVersion) -or
        -not (Assert-SafeAssetName $manifestName) -or
        -not (Assert-SafeAssetName $signatureName) -or
        -not (Assert-SafeAssetName $archiveName)) {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.package_invalid"
    }
    # The index only names files. When the provider pins an asset list, a name
    # outside it is refused before the network is touched.
    $required = @($channel.required_assets)
    if ($required.Count -gt 0) {
        foreach ($name in @($manifestName, $signatureName, $archiveName)) {
            if ($required -cnotcontains $name) {
                Stop-Update $script:ExitRefused "refused" "launcher" "updater.package_invalid"
            }
        }
    }

    $manifestPath = Join-Path $script:WorkDir "manifest.json"
    $signaturePath = Join-Path $script:WorkDir "signature.json"
    $archivePath = Join-Path $script:WorkDir "toefl-house-erp-app.tar"
    Write-Stage "updater.verifying"
    # Only the small signed documents are fetched first.  The image archive is
    # downloaded after the manifest phase allows it, so a forged, unauthorized
    # or incompatible release never costs the customer a single image byte.
    try {
        Save-RemoteFile (Resolve-ChannelUrl $channel $manifestName) $manifestPath $maxJsonBytes
        Save-RemoteFile (Resolve-ChannelUrl $channel $signatureName) $signaturePath $maxJsonBytes
    } catch {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.download_failed"
    }

    $workRelative = "data/updates/runs/" + $runId
    $archiveRelative = $workRelative + "/toefl-house-erp-app.tar"
    $request = [ordered]@{
        action = "preflight"
        now_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        site = $siteName
        product_root = $containerProductRoot
        host_updater_version = [string]$installed.version
        trust_store = "data/updates/trust-store.json"
        channel = "updates/channel.json"
        manifest = $workRelative + "/manifest.json"
        signature = $workRelative + "/signature.json"
        archive = ""
        backup_receipt = "data/activation/backup-receipt.json"
        backup_dir = $script:BackupDirRelative
        recovery_authorization = ""
        recovery_signature = ""
        installed = [pscustomobject]@{
            version = [string]$installed.version
            release_sequence = $installed.release_sequence
            source_revision = [string]$installed.source_revision
            image_labels = $installed.image_labels
            image_id = [string]$installed.image_id
        }
        journal_state = $journalState
        host = $facts
    }
    if (Test-Path -LiteralPath $recoveryAuthorizationPath -PathType Leaf) {
        $request.recovery_authorization = "data/updates/recovery-authorization.json"
    }
    if (Test-Path -LiteralPath $recoverySignaturePath -PathType Leaf) {
        $request.recovery_signature = "data/updates/recovery-authorization.sig"
    }
    # Phase A: signed manifest, authorization, compatibility and local
    # readiness.  Nothing is downloaded into the image path until this allows.
    $response = Invoke-EngineStep "preflight" $request $targetVersion
    [void](Assert-EngineAllowed $response $targetVersion)
    $manifestTransaction = $response.transaction
    if ($null -eq $manifestTransaction -or $null -eq $manifestTransaction.transaction_id) {
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.engine_failed" $targetVersion
    }

    Write-Stage "updater.downloading"
    try {
        Save-RemoteFile (Resolve-ChannelUrl $channel $archiveName) $archivePath $maxArchiveBytes
    } catch {
        Stop-Update $script:ExitRefused "refused" "launcher" "updater.download_failed"
    }
    $archiveItem = Get-Item -LiteralPath $archivePath -Force
    if ($archiveItem.Length -lt $minArchiveBytes -or $archiveItem.Length -gt $maxArchiveBytes) {
        Stop-Update $script:ExitRefused "refused" "messages" "release.archive.size_mismatch" $targetVersion
    }
    # Transport check only: the signed manifest is the authority, and the
    # engine re-verifies the same bytes inside the container below.
    if ($null -ne $latest.archive_size_bytes -and [int64]$latest.archive_size_bytes -ne $archiveItem.Length) {
        Stop-Update $script:ExitRefused "refused" "messages" "release.archive.size_mismatch" $targetVersion
    }
    if ($null -ne $latest.archive_sha256) {
        $actual = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -cne ([string]$latest.archive_sha256).ToLowerInvariant()) {
            Stop-Update $script:ExitRefused "refused" "messages" "release.archive.hash_mismatch" $targetVersion
        }
    }

    # Phase B: bind the downloaded image to the manifest decision.  The engine
    # re-reads every mutable fact and issues a short-lived authorization; apply
    # accepts nothing else.
    $request.action = "authorize"
    $request.archive = $archiveRelative
    $request.transaction = $manifestTransaction
    $response = Invoke-EngineStep "authorize" $request $targetVersion
    [void](Assert-EngineAllowed $response $targetVersion)
    $transaction = $response.transaction
    if ($null -eq $transaction -or [string]$transaction.phase -cne "authorized") {
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.engine_failed" $targetVersion
    }

    $sequence = $null
    if ($null -ne $response.target -and $null -ne $response.target.image) {
        $sequence = $response.target.release_sequence
    }
    return [pscustomobject]@{
        Allowed = $true
        Version = $targetVersion
        Archive = $archivePath
        Sequence = $sequence
        Transaction = $transaction
        Installed = $installed
        Manifest = $workRelative + "/manifest.json"
        Signature = $workRelative + "/signature.json"
        RunFolder = $workRelative
        Response = $response
    }
}

# ---------------------------------------------------------------------------
# Install pipeline (mutating, engine-gated)
# ---------------------------------------------------------------------------

function Invoke-UpdateStart {
    $code = Invoke-Compose @("up", "-d", "--no-build")
    return ($code -eq 0)
}

function Wait-ForApplication([int]$Tries) {
    for ($index = 0; $index -lt $Tries; $index++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/" -TimeoutSec 10
            if ([int]$response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 10
    }
    return $false
}

function Invoke-UpdateInstall($Check) {
    if (-not $ConfirmationAccepted) {
        Stop-Update $script:ExitRefused "cancelled" "launcher" "updater.cancelled"
    }
    Write-Stage "updater.applying"

    $previousImageId = ""
    $image = Get-InstalledImage
    if ($null -ne $image -and $null -ne $image.Id) { $previousImageId = [string]$image.Id }

    Set-JournalState "prepared" $Check.Version
    Write-Stage "updater.verifying"
    $stopped = Invoke-Compose @("stop", "web", "worker", "scheduler", "socketio")
    if ($stopped -ne 0) {
        Set-JournalState "rolled-back" ""
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.failed" $Check.Version
    }

    $loaded = Invoke-DockerVerbose @("load", "--input", $Check.Archive)
    if ($loaded -ne 0) {
        # The tag may or may not have changed.  Restore the previous identity
        # explicitly, then bring the untouched installation back.
        if ($previousImageId) {
            Invoke-DockerVerbose @("tag", $previousImageId, $imageTag) | Out-Null
        }
        $restarted = Invoke-UpdateStart
        if ($restarted) { Set-JournalState "rolled-back" "" } else { Set-JournalState "recovery-required" "" }
        Stop-Update $script:ExitFailed "failed" "launcher" "updater.rollback_done" $Check.Version
    }

    Set-JournalState "applying" $Check.Version
    $applyRequest = [ordered]@{
        action = "apply"
        site = $siteName
        product_root = $containerProductRoot
        manifest = $Check.Manifest
        signature = $Check.Signature
        trust_store = "data/updates/trust-store.json"
        archive = ($Check.RunFolder + "/toefl-house-erp-app.tar")
        transaction = $Check.Transaction
        installed = [pscustomobject]@{
            version = [string]$Check.Installed.version
            release_sequence = $Check.Installed.release_sequence
            source_revision = [string]$Check.Installed.source_revision
            image_labels = $Check.Installed.image_labels
            image_id = [string]$Check.Installed.image_id
        }
        backup_receipt = "data/activation/backup-receipt.json"
        backup_dir = $script:BackupDirRelative
        recovery_authorization = ""
        recovery_signature = ""
        sites_dir = "/home/frappe/bench/sites"
        bench = "/build/tools/bin/bench"
        host_updater_version = [string]$Check.Installed.version
        migrate_replays = 2
        command_timeout_seconds = 1800
    }
    if (Test-Path -LiteralPath $recoveryAuthorizationPath -PathType Leaf) {
        $applyRequest.recovery_authorization = "data/updates/recovery-authorization.json"
    }
    if (Test-Path -LiteralPath $recoverySignaturePath -PathType Leaf) {
        $applyRequest.recovery_signature = "data/updates/recovery-authorization.sig"
    }

    $report = Invoke-EngineStep "apply" $applyRequest $Check.Version
    $outcome = "safe-abort"
    $status = "failed"
    if ($null -ne $report) {
        if ($null -ne $report.transaction_outcome) { $outcome = [string]$report.transaction_outcome }
        if ($null -ne $report.status) { $status = [string]$report.status }
    }
    if ($status -ne "succeeded") {
        $blockers = Get-BlockerCodes $report
        if ($outcome -ceq "safe-abort") {
            if ($previousImageId) {
                Invoke-DockerVerbose @("tag", $previousImageId, $imageTag) | Out-Null
            }
            $restarted = Invoke-UpdateStart
            if ($restarted) { Set-JournalState "rolled-back" "" } else { Set-JournalState "recovery-required" "" }
            $primary = "updater.rollback_done"
            if ($blockers.Count -gt 0 -and $null -ne (Get-Text "messages" $blockers[0])) { $primary = $blockers[0] }
            Save-Result -Status "failed" -Section "messages" -Key $primary -Version $Check.Version -Blockers $blockers
            Write-Host ""
            Write-Bilingual "launcher" "updater.rollback_done"
            Write-Bilingual "messages" $primary
            exit $script:ExitFailed
        }
        # A migration may already have changed the database.  Never start the
        # stack as if the update succeeded, and never restore over live data.
        Set-JournalState "recovery-required" $Check.Version
        $primary = "updater.recovery_required"
        if ($blockers.Count -gt 0 -and $null -ne (Get-Text "messages" $blockers[0])) { $primary = $blockers[0] }
        Save-Result -Status "recovery-required" -Section "launcher" -Key "updater.recovery_required" `
            -Version $Check.Version -Blockers $blockers
        Write-Host ""
        Write-Bilingual "launcher" "updater.recovery_required"
        Write-Bilingual "messages" $primary
        if ($blockers.Count -gt 1) {
            foreach ($code in $blockers) { Write-Bilingual "messages" $code }
        }
        exit $script:ExitRecoveryRequired
    }

    Write-Stage "updater.applying"
    if (-not (Invoke-UpdateStart)) {
        Set-JournalState "recovery-required" $Check.Version
        Save-Result -Status "recovery-required" -Section "launcher" -Key "updater.recovery_required" -Version $Check.Version
        Write-Host ""
        Write-Bilingual "launcher" "updater.recovery_required"
        exit $script:ExitRecoveryRequired
    }
    if (-not (Wait-ForApplication 180)) {
        Set-JournalState "recovery-required" $Check.Version
        Save-Result -Status "recovery-required" -Section "launcher" -Key "updater.recovery_required" -Version $Check.Version
        Write-Host ""
        Write-Bilingual "launcher" "updater.recovery_required"
        exit $script:ExitRecoveryRequired
    }
    Set-JournalState "completed" $Check.Version
    Save-Result -Status "completed" -Section "launcher" -Key "updater.completed" -Version $Check.Version
    Write-Host ""
    Write-Bilingual "launcher" "updater.completed"
    return $true
}

# ---------------------------------------------------------------------------
# Offline smoke test (no Docker, no network, no customer data)
# ---------------------------------------------------------------------------

function Invoke-SmokeTest {
    $failures = New-Object System.Collections.ArrayList

    # The catalogue must contain every section and key the launcher uses.
    try {
        $catalog = Get-Catalog
        foreach ($section in @("messages", "launcher", "ui")) {
            if ($null -eq $catalog.$section) { [void]$failures.Add("missing section " + $section) }
        }
        foreach ($key in @("updater.checking", "updater.available", "updater.completed", "updater.failed",
                           "updater.recovery_required", "updater.installed_version_unknown", "updater.not_installed",
                           "updater.engine_failed", "updater.engine_missing", "updater.cancelled")) {
            if ($null -eq (Get-Text "launcher" $key)) { [void]$failures.Add("missing launcher " + $key) }
        }
        foreach ($key in @("button.check", "button.install", "label.current", "label.available", "window.title")) {
            if ($null -eq (Get-Text "ui" $key)) { [void]$failures.Add("missing ui " + $key) }
        }
    } catch {
        [void]$failures.Add("catalogue: " + $_.Exception.Message)
    }

    # URL policy: https only, allowlisted host, no credentials, no port, no fragment.
    $hosts = @("updates.toefl-house.example")
    if (-not (Test-AllowedUrl "https://updates.toefl-house.example/stable/index.json" $hosts)) {
        [void]$failures.Add("allowed https URL was rejected")
    }
    foreach ($bad in @("http://updates.toefl-house.example/stable/index.json",
                       "https://evil.example/stable/index.json",
                       "https://user:secret@updates.toefl-house.example/index.json",
                       "https://updates.toefl-house.example:8443/index.json",
                       "https://updates.toefl-house.example/index.json#fragment")) {
        if (Test-AllowedUrl $bad $hosts) { [void]$failures.Add("unsafe URL was accepted: " + $bad) }
    }

    # Asset names never carry a path, a traversal or an absolute root.
    foreach ($bad in @("..", "../manifest.json", "a/b.json", "/etc/passwd", "C:\secret", "", ".hidden")) {
        if (Assert-SafeAssetName $bad) { [void]$failures.Add("unsafe asset name was accepted: " + $bad) }
    }
    foreach ($good in @("toefl-house-erp-app.tar", "update.json", "update.json.sig")) {
        if (-not (Assert-SafeAssetName $good)) { [void]$failures.Add("safe asset name was rejected: " + $good) }
    }

    # Release sequence table must match product/update_engine.py exactly.
    $expected = @{
        "2026.10.24" = 2026102400
        "2026.11.01" = 2026110100
        "2027.1.2" = 2027010200
        "2026.11" = 2026110000
        "2026.11.01.2" = 2026110102
        "2026" = 2026000000
    }
    foreach ($version in $expected.Keys) {
        try {
            if ((ConvertTo-ReleaseSequence $version) -ne $expected[$version]) {
                [void]$failures.Add("sequence mismatch for " + $version)
            }
        } catch {
            [void]$failures.Add("sequence rejected for " + $version)
        }
    }
    foreach ($bad in @("ci-windows-package", "2026.11.01-rc1", "v2026.11.01", "", "..", "9999.1.1")) {
        $threw = $false
        try { [void](ConvertTo-ReleaseSequence $bad) } catch { $threw = $true }
        if (-not $threw) { [void]$failures.Add("unsupported version accepted: " + $bad) }
    }

    # A non-terminal journal must stop a second update from starting.
    # Get-JournalState reads the script scope, so the probe must replace the
    # script-scope path; a local copy would test the customer's real journal.
    $originalJournal = $script:journalPath
    $script:journalPath = Join-Path $env:TEMP ("toefl-house-journal-" + [guid]::NewGuid().ToString("N") + ".json")
    try {
        [System.IO.File]::WriteAllText($script:journalPath,
            '{"schema_version":1,"document_type":"toefl-house-erp-update-journal","phase":"applying"}')
        if ((Get-JournalState) -cne "applying") { [void]$failures.Add("journal phase was not read") }
        [System.IO.File]::WriteAllText($script:journalPath, '{"phase":"nonsense"}')
        if ((Get-JournalState) -cne "unknown") { [void]$failures.Add("invalid journal was not rejected") }
        Remove-Item -LiteralPath $script:journalPath -Force -ErrorAction SilentlyContinue
        if ((Get-JournalState) -cne "idle") { [void]$failures.Add("absent journal was not idle") }
    } finally {
        Remove-Item -LiteralPath $script:journalPath -Force -ErrorAction SilentlyContinue
        $script:journalPath = $originalJournal
    }

    if ($failures.Count -gt 0) {
        foreach ($failure in $failures) { Write-Host ("FAILED: " + $failure) }
        throw "Windows update controls failed their offline checks."
    }
    Write-Host "Windows update controls initialized; fail-closed checks verified."
    exit 0
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if ($SmokeTest) { Invoke-SmokeTest }

Protect-UpdateFolder
if (-not (Enter-UpdateLock)) {
    Stop-Update $script:ExitRefused "busy" "launcher" "updater.already_running"
}
try {
    $check = Invoke-UpdateCheck
    if ($Action -eq "Install") {
        [void](Invoke-UpdateInstall $check)
        exit $script:ExitAllowed
    } else {
        Save-Result -Status "update-available" -Section "launcher" -Key "updater.available" -Version $check.Version
        Write-Stage "updater.available"
        Write-Bilingual "launcher" "updater.available"
        Write-Host ("Target version: " + $check.Version)
        exit $script:ExitAllowed
    }
} catch {
    $message = $_.Exception.Message
    Write-Host ""
    Write-Host ("Update stopped safely: " + $message)
    Save-Result -Status "failed" -Section "launcher" -Key "updater.failed" -Version ""
    exit $script:ExitFailed
} finally {
    Exit-UpdateLock
}
