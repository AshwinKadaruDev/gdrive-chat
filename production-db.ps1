# production-db.ps1 - Manage Supabase production database from local machine
# Usage: .\production-db.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Production Database Manager" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -- Parse .env.production ------------------------------------------------

$envFile = Join-Path $ProjectRoot ".env.production"
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env.production not found at $envFile" -ForegroundColor Red
    exit 1
}

$envContent = Get-Content $envFile -Raw

# Extract DATABASE_URL
if ($envContent -match '(?m)^DATABASE_URL=(.+)$') {
    $databaseUrl = $Matches[1].Trim()
} else {
    Write-Host "ERROR: DATABASE_URL not found in .env.production" -ForegroundColor Red
    exit 1
}

# Extract ADMINS
if ($envContent -match '(?m)^ADMINS=(.+)$') {
    $admins = $Matches[1].Trim()
} else {
    Write-Host "ERROR: ADMINS not found in .env.production" -ForegroundColor Red
    exit 1
}

# Show connection info (mask password)
$maskedUrl = $databaseUrl -replace '(://[^:]+:)[^@]+(@)', '${1}****${2}'
Write-Host "  Database: $maskedUrl" -ForegroundColor Gray
Write-Host "  Admins:   $admins" -ForegroundColor Gray
Write-Host ""

# -- Activate venv --------------------------------------------------------

$venvActivate = Join-Path $ProjectRoot "backend\venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "ERROR: Backend venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}
& $venvActivate

# -- Set env vars (override local .env) -----------------------------------

$env:DATABASE_URL = $databaseUrl
$env:ADMINS = $admins

# -- Helper: run external command (alembic/python write INFO to stderr) ---

function Invoke-External {
    param([string]$Command, [string[]]$CmdArgs)
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $output = & $Command $CmdArgs 2>&1 | Out-String
    $script:lastExit = $LASTEXITCODE
    $ErrorActionPreference = $prevPref
    return $output
}

# -- Test connection ------------------------------------------------------

Write-Host "Testing connection..." -ForegroundColor Yellow
Set-Location (Join-Path $ProjectRoot "backend")

$currentOutput = Invoke-External alembic @("current")
if ($script:lastExit -ne 0) {
    Write-Host "  ERROR: Could not connect to production database." -ForegroundColor Red
    Write-Host "  $($currentOutput.Trim())" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - Check DATABASE_URL in .env.production" -ForegroundColor Gray
    Write-Host "  - If IPv4 issue, use the Session Pooler URL from Supabase dashboard" -ForegroundColor Gray
    Set-Location $ProjectRoot
    exit 1
}
Write-Host "  Connected!" -ForegroundColor Green

Write-Host ""

# -- Prompt for action ----------------------------------------------------

Write-Host "Choose an action:" -ForegroundColor White
Write-Host "  [U] Upgrade (default) - apply new migrations, keep existing data" -ForegroundColor Green
Write-Host "  [R] Reset - DROP all tables, re-migrate, re-seed from JSON" -ForegroundColor Red
Write-Host ""
$choice = Read-Host "Enter choice (U/r)"

if ($choice -eq "r" -or $choice -eq "R") {
    # -- Destructive reset ------------------------------------------------
    Write-Host ""
    Write-Host "  WARNING: This will clear workflow data in the production database!" -ForegroundColor Red
    Write-Host "  Contacts, groups, reports, claims will be wiped and re-seeded." -ForegroundColor Yellow
    Write-Host "  Usage tracking data will be preserved." -ForegroundColor Gray
    Write-Host ""
    $confirm = Read-Host "  Type 'yes' to confirm reset"

    if ($confirm -ne "yes") {
        Write-Host "  Aborted." -ForegroundColor Yellow
        Set-Location $ProjectRoot
        exit 0
    }

    Write-Host ""
    Write-Host "  Resetting production database..." -ForegroundColor Yellow

    # Truncate workflow tables (preserves usage_daily + organizations)
    Write-Host "  [1/2] Clearing workflow tables..." -ForegroundColor Gray
    Invoke-External python @("scripts/reset_seed_tables.py") | Out-Null
    if ($script:lastExit -ne 0) { throw "Reset failed" }
    Write-Host "  [1/2] Workflow tables cleared (usage preserved)." -ForegroundColor Green

    # Seed
    Write-Host "  [2/2] Seeding from data/*.json..." -ForegroundColor Gray
    Invoke-External python @("scripts/migrate_json_to_pg.py") | Out-Null
    if ($script:lastExit -ne 0) { throw "Seed script failed" }
    Write-Host "  [2/2] Database seeded!" -ForegroundColor Green

} else {
    # -- Safe upgrade -----------------------------------------------------
    Write-Host ""
    Write-Host "  Applying migrations..." -ForegroundColor Yellow
    Invoke-External alembic @("upgrade", "head") | Out-Null
    if ($script:lastExit -ne 0) { throw "alembic upgrade head failed" }
    Write-Host "  Migrations applied!" -ForegroundColor Green
}

# -- Done -----------------------------------------------------------------

Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Done!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
