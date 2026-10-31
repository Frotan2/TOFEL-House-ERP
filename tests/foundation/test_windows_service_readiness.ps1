$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "../../product/windows/Test Existing Installation.ps1")
$script:Checks = 0
$script:DockerExit = 0
$script:HttpStatus = 200
$script:Healthy = '{"Status":"running","Health":{"Status":"healthy"}}'
$script:Rows = @(0..6 | ForEach-Object { $script:Healthy })
function docker {
    if ($args[0] -cne "inspect" -or $args[1] -cne "--format" -or $args[2] -cne "{{json .State}}" -or $args.Count -ne 10) {
        throw "Unexpected or mutating Docker command in readiness check"
    }
    $global:LASTEXITCODE = $script:DockerExit
    return $script:Rows
}
function Invoke-WebRequest {
    param([string]$Uri, [switch]$UseBasicParsing, [int]$TimeoutSec, [string]$ErrorAction)
    if ($Uri -cne "http://127.0.0.1:8000/" -or -not $UseBasicParsing -or $TimeoutSec -ne 5) {
        throw "Unexpected readiness HTTP target"
    }
    return [pscustomobject]@{StatusCode = $script:HttpStatus}
}
function Assert-NotReady {
    $denied = $false
    try { Test-ProductServicesReady } catch { $denied = $true }
    if (-not $denied) { throw "Unready services were accepted" }
    $script:Checks++
}
try {
    Test-ProductServicesReady
    $script:Checks++
    for ($index = 0; $index -lt 7; $index++) {
        $script:Rows[$index] = '{"Status":"exited","Health":{"Status":"healthy"}}'
        Assert-NotReady
        $script:Rows[$index] = $script:Healthy
    }
    for ($index = 0; $index -lt 5; $index++) {
        $script:Rows[$index] = '{"Status":"running","Health":{"Status":"unhealthy"}}'
        Assert-NotReady
        $script:Rows[$index] = $script:Healthy
    }
    $script:Rows = @($script:Healthy) * 6
    Assert-NotReady
    $script:Rows = @($script:Healthy) * 8
    Assert-NotReady
    $script:Rows = @($script:Healthy) * 7
    $script:Rows[0] = 'malformed JSON'
    Assert-NotReady
    $script:Rows[0] = $script:Healthy
    $script:DockerExit = 7
    Assert-NotReady
    $script:DockerExit = 0
    $script:HttpStatus = 503
    Assert-NotReady
    $script:HttpStatus = 200
    Test-ProductServicesReady
    $script:Checks++
    $global:LASTEXITCODE = 0
    Write-Host "PASS: $script:Checks exact service/HTTP readiness cases; no Docker or file mutation."
} finally {
    Remove-Item Function:docker
    Remove-Item Function:Invoke-WebRequest
}
