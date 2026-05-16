#!/usr/bin/env pwsh
# Run the backend test suite against a local Postgres container.
# Usage: .\scripts\run_tests_postgres.ps1 [pytest-args...]
# Example: .\scripts\run_tests_postgres.ps1 -k test_capacity -v
$ErrorActionPreference = "Stop"
$composeFile = Join-Path $PSScriptRoot ".." "docker-compose.test.yml"
$pytestArgs = $args

docker compose -f $composeFile up -d

$exitCode = 1
try {
    # Wait for healthcheck (up to 60s)
    $deadline = (Get-Date).AddSeconds(60)
    $status = ""
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect -f '{{.State.Health.Status}}' jira-analytics-test-pg 2>$null
        if ($status -eq "healthy") { break }
        Start-Sleep -Seconds 1
    }
    if ($status -ne "healthy") {
        throw "Postgres test container did not become healthy within 60s"
    }

    $env:TEST_DATABASE_URL = "postgresql://test:test@localhost:55432/jira_analytics_test"
    if ($pytestArgs.Count -gt 0) {
        py -3.10 -m pytest tests/ @pytestArgs
    } else {
        py -3.10 -m pytest tests/ -q
    }
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    docker compose -f $composeFile down
}
exit $exitCode
