# test.ps1 — Run all backend and frontend tests

$ErrorActionPreference = "Stop"

function Write-Step($n, $total, $msg) {
    Write-Host "`n[$n/$total] $msg" -ForegroundColor Cyan
}

$totalSteps = 3

# ── Backend tests ────────────────────────────────────────────────────
Write-Step 1 $totalSteps "Backend tests (pytest)"
Push-Location backend
$ErrorActionPreference = "Continue"
$backendOut = python -m pytest --tb=short -q 2>&1 | Out-String
$backendExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location

$backendSummary = ($backendOut -split "`n" | Select-String "passed|failed|error" | Select-Object -Last 1)
if ($backendSummary) { Write-Host "  $($backendSummary.ToString().Trim())" }

# ── Frontend tests ───────────────────────────────────────────────────
Write-Step 2 $totalSteps "Frontend tests (vitest)"
Push-Location frontend
$ErrorActionPreference = "Continue"
$frontendOut = npx vitest run 2>&1 | Out-String
$frontendExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location

$frontendOut -split "`n" | Select-String "(Test Files|Tests\s|Duration)" | ForEach-Object { Write-Host "  $($_.ToString().Trim())" }

# ── Frontend type check ──────────────────────────────────────────────
Write-Step 3 $totalSteps "TypeScript type check"
Push-Location frontend
$ErrorActionPreference = "Continue"
$tscOut = npx tsc --noEmit 2>&1 | Out-String
$tscExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Pop-Location

# ── Summary ──────────────────────────────────────────────────────────
Write-Host ""
if ($backendExit -ne 0)  { Write-Host "  Backend:    FAILED" -ForegroundColor Red }
else                      { Write-Host "  Backend:    PASSED" -ForegroundColor Green }
if ($frontendExit -ne 0) { Write-Host "  Frontend:   FAILED" -ForegroundColor Red }
else                      { Write-Host "  Frontend:   PASSED" -ForegroundColor Green }
if ($tscExit -ne 0)      { Write-Host "  TypeScript: FAILED" -ForegroundColor Red }
else                      { Write-Host "  TypeScript: PASSED" -ForegroundColor Green }

if ($backendExit -ne 0 -or $frontendExit -ne 0 -or $tscExit -ne 0) {
    if ($backendExit -ne 0)  { Write-Host "`n--- Backend output ---" -ForegroundColor Yellow; Write-Host $backendOut }
    if ($frontendExit -ne 0) { Write-Host "`n--- Frontend output ---" -ForegroundColor Yellow; Write-Host $frontendOut }
    if ($tscExit -ne 0)      { Write-Host "`n--- TypeScript output ---" -ForegroundColor Yellow; Write-Host $tscOut }
    Write-Host ""
    throw "Tests failed"
}

Write-Host "`nAll tests passed.`n" -ForegroundColor Green
