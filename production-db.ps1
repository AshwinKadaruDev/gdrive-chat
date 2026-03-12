# production-db.ps1 — Smart production database manager
# Usage: .\production-db.ps1
#
# What it does:
#   1. Connects to Supabase using .env.production
#   2. Detects current migration state
#   3. Applies pending migrations (or reports "already up to date")
#   4. Shows a table summary with row counts

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Production Database Manager" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -- Parse .env.production ---------------------------------------------------

$envFile = Join-Path $ProjectRoot ".env.production"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env.production not found." -ForegroundColor Red
    Write-Host "  Run .\setup.ps1 or copy .env.production.example to .env.production" -ForegroundColor Gray
    exit 1
}

$envContent = Get-Content $envFile -Raw

if ($envContent -match '(?m)^DATABASE_URL=(.+)$') {
    $databaseUrl = $Matches[1].Trim()
} else {
    Write-Host "ERROR: DATABASE_URL not found in .env.production" -ForegroundColor Red
    exit 1
}

$maskedUrl = $databaseUrl -replace '(://[^:]+:)[^@]+(@)', '${1}****${2}'
Write-Host "  Database: $maskedUrl" -ForegroundColor Gray
Write-Host ""

# -- Activate venv -----------------------------------------------------------

$venvActivate = Join-Path $ProjectRoot "backend\venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "ERROR: Backend venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}
& $venvActivate

# -- Set env vars ------------------------------------------------------------

$env:DATABASE_URL = $databaseUrl

# -- Helper ------------------------------------------------------------------

function Invoke-External {
    param([string]$Command, [string[]]$CmdArgs)
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $output = & $Command $CmdArgs 2>&1 | Out-String
    $script:lastExit = $LASTEXITCODE
    $ErrorActionPreference = $prevPref
    return $output
}

# Regex to extract 12-char hex revision from alembic output
# Using \w instead of [0-9a-f] to avoid PowerShell type-parsing issues
$revPattern = "(\w{12})"

# -- Test connection ---------------------------------------------------------

Write-Host "[1/3] Testing connection..." -ForegroundColor Yellow
Set-Location (Join-Path $ProjectRoot "backend")

$currentOutput = Invoke-External alembic @("current")
if ($script:lastExit -ne 0) {
    Write-Host "  ERROR: Could not connect to production database." -ForegroundColor Red
    Write-Host "  $($currentOutput.Trim())" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - Check DATABASE_URL in .env.production" -ForegroundColor Gray
    Write-Host "  - Password special chars must be percent-encoded (@ -> %40, # -> %23, + -> %2B, / -> %2F)" -ForegroundColor Gray
    Write-Host "  - Use the Session Pooler URL from Supabase (IPv4 compatible)" -ForegroundColor Gray
    Write-Host "  - Direct connection requires IPv6 - will not work on most networks or Azure" -ForegroundColor Gray
    Set-Location $ProjectRoot
    exit 1
}
Write-Host "  Connected!" -ForegroundColor Green

# -- Detect migration state --------------------------------------------------

Write-Host ""
Write-Host "[2/3] Checking migration state..." -ForegroundColor Yellow

$currentRev = ""
if ($currentOutput -match $revPattern) {
    $currentRev = $Matches[1]
    Write-Host "  Current revision: $currentRev" -ForegroundColor Gray
} else {
    Write-Host "  No migrations applied yet (fresh database)" -ForegroundColor Gray
}

$headOutput = Invoke-External alembic @("heads")
$headRev = ""
if ($headOutput -match $revPattern) {
    $headRev = $Matches[1]
    Write-Host "  Target revision:  $headRev" -ForegroundColor Gray
}

# -- Apply migrations --------------------------------------------------------

Write-Host ""
Write-Host "[3/3] Applying migrations..." -ForegroundColor Yellow

if ($currentRev -eq $headRev -and $currentRev -ne "") {
    Write-Host "  Already up to date!" -ForegroundColor Green
} else {
    if ($currentRev -eq "") {
        Write-Host "  Initializing database from scratch..." -ForegroundColor Gray
    } else {
        Write-Host "  Upgrading from $currentRev to $headRev..." -ForegroundColor Gray
    }

    $upgradeOutput = Invoke-External alembic @("upgrade", "head")
    if ($script:lastExit -ne 0) {
        Write-Host "  ERROR: Migration failed!" -ForegroundColor Red
        Write-Host "  $($upgradeOutput.Trim())" -ForegroundColor Red
        Set-Location $ProjectRoot
        exit 1
    }
    Write-Host "  Migrations applied!" -ForegroundColor Green
}

# -- Show table summary ------------------------------------------------------

Write-Host ""
Write-Host "  Table summary:" -ForegroundColor Cyan

$PythonExe = Join-Path $ProjectRoot "backend\venv\Scripts\python.exe"
$summaryScript = Join-Path $ProjectRoot "backend\scripts\table_summary.py"
& $PythonExe $summaryScript

# -- Done --------------------------------------------------------------------

Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Done!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
