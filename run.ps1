# run.ps1 - Talk-to-a-Folder Run Script
# Runs Temporal, backend, worker, and frontend in the current terminal

$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Talk-to-a-Folder - Run" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if setup has been run
if (-not (Test-Path "$ProjectRoot\frontend\node_modules")) {
    Write-Host "ERROR: Frontend not set up. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$ProjectRoot\backend\venv")) {
    Write-Host "ERROR: Backend not set up. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$temporalProc = $null
$backendProc = $null
$workerProc = $null
$frontendProc = $null

try {
    # ---------------------------------------------------------------
    # Start Temporal dev server
    # ---------------------------------------------------------------
    $useDocker = $false
    try {
        $temporalVersion = temporal --version 2>$null
        if ($temporalVersion) {
            Write-Host "Starting Temporal dev server (CLI)..." -ForegroundColor Yellow
            $temporalProc = Start-Process -NoNewWindow -PassThru -FilePath "temporal" `
                -ArgumentList "server", "start-dev", "--port", "7233", "--ui-port", "8233", "--db-filename", ".temporal.db"
        } else {
            $useDocker = $true
        }
    } catch {
        $useDocker = $true
    }

    if ($useDocker) {
        Write-Host "Temporal CLI not found. Starting via Docker..." -ForegroundColor Yellow
        $temporalProc = Start-Process -NoNewWindow -PassThru -FilePath "docker" `
            -ArgumentList "run", "--rm", "--name", "temporal-dev", `
                "-p", "7233:7233", "-p", "8233:8233", `
                "temporalio/auto-setup:1.22"
    }

    # Give Temporal time to initialize
    Start-Sleep -Seconds 3

    # ---------------------------------------------------------------
    # Start backend (FastAPI on port 8000)
    # ---------------------------------------------------------------
    Write-Host "Starting backend (FastAPI on port 8000)..." -ForegroundColor Yellow
    $backendProc = Start-Process -NoNewWindow -PassThru `
        -WorkingDirectory "$ProjectRoot\backend" `
        -FilePath "$ProjectRoot\backend\venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"

    # Give backend a moment to start
    Start-Sleep -Seconds 2

    # ---------------------------------------------------------------
    # Start Temporal worker (runs from project root)
    # ---------------------------------------------------------------
    Write-Host "Starting Temporal worker..." -ForegroundColor Yellow
    $workerProc = Start-Process -NoNewWindow -PassThru `
        -WorkingDirectory "$ProjectRoot" `
        -FilePath "$ProjectRoot\backend\venv\Scripts\python.exe" `
        -ArgumentList "-m", "worker.main"

    # ---------------------------------------------------------------
    # Start frontend (Vite dev server on port 5173)
    # ---------------------------------------------------------------
    Write-Host "Starting frontend (Vite on port 5173)..." -ForegroundColor Yellow
    $frontendProc = Start-Process -NoNewWindow -PassThru `
        -WorkingDirectory "$ProjectRoot\frontend" `
        -FilePath "cmd" -ArgumentList "/c", "npm run dev"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  All Services Running!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Frontend:    http://localhost:5173" -ForegroundColor Cyan
    Write-Host "  Backend:     http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "  Temporal UI: http://localhost:8233" -ForegroundColor Cyan
    Write-Host "  Temporal:    localhost:7233 (gRPC)" -ForegroundColor Cyan
    Write-Host "  Worker:      polling talk-to-folder-sync queue" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray
    Write-Host ""

    # Wait for any process to exit
    while ($true) {
        $exited = $false
        if ($backendProc -and $backendProc.HasExited) { $exited = $true }
        if ($workerProc -and $workerProc.HasExited) { $exited = $true }
        if ($frontendProc -and $frontendProc.HasExited) { $exited = $true }
        if ($exited) { break }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow

    # Kill app processes first, Temporal last (others depend on it)
    foreach ($proc in @($frontendProc, $workerProc, $backendProc, $temporalProc)) {
        if ($proc -and -not $proc.HasExited) {
            taskkill /F /T /PID $proc.Id 2>$null | Out-Null
        }
    }

    # If we started Temporal via Docker, stop the container
    docker stop temporal-dev 2>$null | Out-Null

    Write-Host "All services stopped." -ForegroundColor Green
}
