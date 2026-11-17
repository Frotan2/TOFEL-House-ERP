param([switch]$AllowStopped)
$ErrorActionPreference = 'Stop'

function Assert-NoDockerOverrides {
    foreach ($name in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG',
                       'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_PROFILES',
                       'COMPOSE_ENV_FILES', 'COMPOSE_PATH_SEPARATOR')) {
        if ([Environment]::GetEnvironmentVariable($name, 'Process')) {
            throw "ERP refused the $name override. Open the launcher in the standard Windows environment."
        }
    }
}

function Assert-LocalDockerEngine([switch]$AllowStopped) {
    Assert-NoDockerOverrides
    # Get-Command can list more than one executable. Validate the first path,
    # which is the one the normal Docker command resolves on this process PATH.
    $docker = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $docker) {
        throw 'Docker Desktop was not found. Install it directly from Docker and reopen the launcher.'
    }
    $endpoint = @(& $docker.Source context inspect --format '{{.Endpoints.docker.Host}}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or $endpoint.Count -ne 1 -or
        $endpoint[0] -notin @('npipe:////./pipe/dockerDesktopLinuxEngine','npipe:////./pipe/docker_engine')) {
        throw 'ERP refused a Docker context other than the local Windows Docker Desktop pipe.'
    }
    if (-not $AllowStopped) {
        $engine = @(& $docker.Source info --format '{{.OSType}}' 2>$null)
        if ($LASTEXITCODE -ne 0 -or $engine.Count -ne 1 -or $engine[0] -cne 'linux') {
            throw 'The local Docker Desktop Linux engine is not ready. Open Docker Desktop and select its Linux engine.'
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Assert-LocalDockerEngine -AllowStopped:$AllowStopped
        exit 0
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}
