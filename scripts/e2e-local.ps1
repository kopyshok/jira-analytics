param(
    [switch]$InstallBrowsers,
    [int]$BackendPort = 8010,
    [int]$FrontendPort = 5174
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $RepoRoot "frontend"
$PreviousBackendPort = $env:E2E_BACKEND_PORT
$PreviousFrontendPort = $env:E2E_FRONTEND_PORT

$env:E2E_BACKEND_PORT = "$BackendPort"
$env:E2E_FRONTEND_PORT = "$FrontendPort"

Push-Location $FrontendDir
try {
    if ($InstallBrowsers) {
        npm run e2e:install
    }

    npm run e2e
}
finally {
    if ($null -eq $PreviousBackendPort) {
        Remove-Item Env:\E2E_BACKEND_PORT -ErrorAction SilentlyContinue
    }
    else {
        $env:E2E_BACKEND_PORT = $PreviousBackendPort
    }

    if ($null -eq $PreviousFrontendPort) {
        Remove-Item Env:\E2E_FRONTEND_PORT -ErrorAction SilentlyContinue
    }
    else {
        $env:E2E_FRONTEND_PORT = $PreviousFrontendPort
    }

    Pop-Location
}
