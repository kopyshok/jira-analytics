param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Stop-PortProcess {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "[:$Port] free" -ForegroundColor DarkGray
        return
    }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        try {
            $p = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "[:$Port] kill PID $procId ($($p.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Host "[:$Port] PID $procId already gone" -ForegroundColor DarkGray
        }
    }
    Start-Sleep -Milliseconds 400
}

function Start-Backend {
    Write-Host "[backend] starting uvicorn on :$BackendPort" -ForegroundColor Cyan
    Start-Process -FilePath "py" `
        -ArgumentList "-3.10","-m","uvicorn","app.main:app","--reload","--port","$BackendPort" `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Normal
}

function Start-Frontend {
    Write-Host "[frontend] starting vite on :$FrontendPort" -ForegroundColor Cyan
    $frontendDir = Join-Path $RepoRoot "frontend"
    Start-Process -FilePath "cmd" `
        -ArgumentList "/c","npm","run","dev","--","--port","$FrontendPort" `
        -WorkingDirectory $frontendDir `
        -WindowStyle Normal
}

if (-not $FrontendOnly) {
    Stop-PortProcess -Port $BackendPort
    Start-Backend
}

if (-not $BackendOnly) {
    Stop-PortProcess -Port $FrontendPort
    Start-Frontend
}

Write-Host "`nDone. Backend: http://localhost:$BackendPort  |  Frontend: http://localhost:$FrontendPort" -ForegroundColor Green
