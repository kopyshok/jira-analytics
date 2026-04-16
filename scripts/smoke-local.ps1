param(
    [switch]$SkipMigrate,
    [switch]$NoStart,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SmokeArgs = @(
    "scripts/local_smoke.py",
    "--backend-port",
    "$BackendPort",
    "--frontend-port",
    "$FrontendPort"
)

if ($SkipMigrate) {
    $SmokeArgs += "--skip-migrate"
}

if ($NoStart) {
    $SmokeArgs += "--no-start"
}

Push-Location $RepoRoot
try {
    py -3.10 @SmokeArgs
}
finally {
    Pop-Location
}
