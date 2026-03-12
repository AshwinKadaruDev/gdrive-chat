# run.ps1 - Talk-to-a-Folder Run Script
# Runs backend and frontend in the current terminal

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

$backendProc = $null
$frontendProc = $null

try {
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
    Write-Host ""
    Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray
    Write-Host ""

    # Wait for any process to exit
    while ($true) {
        $exited = $false
        if ($backendProc -and $backendProc.HasExited) { $exited = $true }
        if ($frontendProc -and $frontendProc.HasExited) { $exited = $true }
        if ($exited) { break }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow

    foreach ($proc in @($frontendProc, $backendProc)) {
        if ($proc -and -not $proc.HasExited) {
            taskkill /F /T /PID $proc.Id 2>$null | Out-Null
        }
    }

    Write-Host "All services stopped." -ForegroundColor Green
}
