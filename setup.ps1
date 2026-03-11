# setup.ps1 - Talk-to-a-Folder Setup Script
# One-time setup for local development

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Talk-to-a-Folder - Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------
# 1. Check prerequisites
# ---------------------------------------------------------------
Write-Host "[1/8] Checking prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version
    Write-Host "  Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Python not found. Please install Python 3.12+ from https://python.org" -ForegroundColor Red
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version
    Write-Host "  Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Node.js not found. Please install Node.js 20+ from https://nodejs.org" -ForegroundColor Red
    exit 1
}

# Check npm
try {
    $npmVersion = npm --version
    Write-Host "  npm: v$npmVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: npm not found." -ForegroundColor Red
    exit 1
}

# Check for uv (optional, fall back to pip)
$useUv = $false
try {
    $uvVersion = uv --version 2>$null
    if ($uvVersion) {
        Write-Host "  uv: $uvVersion (will use for faster installs)" -ForegroundColor Green
        $useUv = $true
    }
} catch {
    Write-Host "  uv: not found (using pip instead)" -ForegroundColor Gray
}

# Check for Temporal CLI (optional)
$hasTemporalCli = $false
try {
    $temporalVersion = temporal --version 2>$null
    if ($temporalVersion) {
        Write-Host "  Temporal CLI: $temporalVersion" -ForegroundColor Green
        $hasTemporalCli = $true
    } else {
        Write-Host "  Temporal CLI: not found" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Temporal CLI: not found" -ForegroundColor Gray
}

# Check for Docker (needed if Temporal CLI is not installed)
if (-not $hasTemporalCli) {
    try {
        $dockerVersion = docker --version 2>$null
        if ($dockerVersion) {
            Write-Host "  Docker: $dockerVersion (will use for Temporal dev server)" -ForegroundColor Green
        } else {
            Write-Host "  WARNING: Neither Temporal CLI nor Docker found." -ForegroundColor Yellow
            Write-Host "  Install one of them for the sync worker. See https://docs.temporal.io/cli" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  WARNING: Neither Temporal CLI nor Docker found." -ForegroundColor Yellow
        Write-Host "  Install one of them for the sync worker. See https://docs.temporal.io/cli" -ForegroundColor Yellow
    }
}

Write-Host ""

# ---------------------------------------------------------------
# 2. Create Python virtual environment
# ---------------------------------------------------------------
$VenvPath = "$ProjectRoot\backend\venv"
$PipExe = "$VenvPath\Scripts\pip.exe"
$PythonExe = "$VenvPath\Scripts\python.exe"

if (-not (Test-Path $VenvPath)) {
    Write-Host "[2/8] Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Virtual environment created at backend\venv" -ForegroundColor Green
} else {
    Write-Host "[2/8] Virtual environment already exists." -ForegroundColor Green
}

# ---------------------------------------------------------------
# 3. Install backend Python dependencies
# ---------------------------------------------------------------
Write-Host "[3/8] Installing backend dependencies..." -ForegroundColor Yellow
if ($useUv) {
    uv pip install --python $PythonExe -r "$ProjectRoot\backend\requirements.txt" --quiet
} else {
    & $PipExe install -r "$ProjectRoot\backend\requirements.txt" --quiet
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to install backend dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "  Backend dependencies installed." -ForegroundColor Green

# Install worker dependencies (same venv)
Write-Host "  Installing worker dependencies..." -ForegroundColor Gray
if ($useUv) {
    uv pip install --python $PythonExe -r "$ProjectRoot\worker\requirements.txt" --quiet
} else {
    & $PipExe install -r "$ProjectRoot\worker\requirements.txt" --quiet
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Failed to install worker dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "  Worker dependencies installed." -ForegroundColor Green

# ---------------------------------------------------------------
# 4. Install frontend dependencies
# ---------------------------------------------------------------
Write-Host "[4/8] Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location "$ProjectRoot\frontend"

if (Test-Path "node_modules") {
    Write-Host "  node_modules exists, checking for updates..." -ForegroundColor Gray
}

npm install --no-audit --no-fund 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: npm install failed." -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "  Frontend dependencies installed." -ForegroundColor Green

# ---------------------------------------------------------------
# 5. Create .env from .env.example if it doesn't exist
# ---------------------------------------------------------------
Write-Host "[5/8] Checking .env file..." -ForegroundColor Yellow
$EnvFile = "$ProjectRoot\.env"
$EnvExample = "$ProjectRoot\.env.example"
$envCreated = $false

if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "  .env created from .env.example" -ForegroundColor Green
        $envCreated = $true
    } else {
        Write-Host "  WARNING: .env.example not found. Create .env manually." -ForegroundColor Red
    }
} else {
    Write-Host "  .env already exists." -ForegroundColor Green
}

# ---------------------------------------------------------------
# 6. Generate secrets if not already in .env
# ---------------------------------------------------------------
Write-Host "[6/8] Checking security keys..." -ForegroundColor Yellow

$envContent = Get-Content $EnvFile -Raw -ErrorAction SilentlyContinue

# Generate ENCRYPTION_KEY (Fernet key) if placeholder or missing
if ($envContent -match "ENCRYPTION_KEY=your-fernet-key" -or $envContent -notmatch "ENCRYPTION_KEY=.+") {
    Write-Host "  Generating ENCRYPTION_KEY (Fernet)..." -ForegroundColor Yellow
    $fernetKey = & $PythonExe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>$null
    if ($fernetKey) {
        $envContent = $envContent -replace "ENCRYPTION_KEY=.*", "ENCRYPTION_KEY=$fernetKey"
        Write-Host "  ENCRYPTION_KEY generated." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Could not generate Fernet key (cryptography not installed yet)." -ForegroundColor Yellow
    }
}

# Write back updated .env
if ($envContent) {
    Set-Content -Path $EnvFile -Value $envContent -NoNewline
}

# ---------------------------------------------------------------
# 7. Create database and run migrations
# ---------------------------------------------------------------
Write-Host "[7/8] Setting up database..." -ForegroundColor Yellow

# Try to create the PostgreSQL database (requires psql on PATH)
try {
    $dbExists = psql -U postgres -lqt 2>$null | Select-String "talk_to_folder"
    if (-not $dbExists) {
        Write-Host "  Creating database 'talk_to_folder'..." -ForegroundColor Yellow
        psql -U postgres -c "CREATE DATABASE talk_to_folder;" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Database created." -ForegroundColor Green
        } else {
            Write-Host "  WARNING: Could not create database. Create 'talk_to_folder' manually in PG Admin." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Database 'talk_to_folder' already exists." -ForegroundColor Green
    }
} catch {
    Write-Host "  WARNING: psql not found. Create the 'talk_to_folder' database manually in PG Admin." -ForegroundColor Yellow
}

# Auto-generate migration if models changed, then apply
Write-Host "  Checking for model changes..." -ForegroundColor Gray
Push-Location "$ProjectRoot\backend"
try {
    $autoGenOutput = & $PythonExe -m alembic revision --autogenerate -m "auto" 2>&1
    if ($autoGenOutput -match "No changes in schema detected") {
        Write-Host "  No new model changes detected." -ForegroundColor Gray
    } elseif ($LASTEXITCODE -eq 0) {
        Write-Host "  New migration generated." -ForegroundColor Green
    }
} catch {
    Write-Host "  WARNING: Could not check for model changes." -ForegroundColor Yellow
}

Write-Host "  Running database migrations..." -ForegroundColor Yellow
try {
    & $PythonExe -m alembic upgrade head 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Migrations applied successfully." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Migrations failed. Ensure the database is running and .env is configured." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  WARNING: Could not run migrations: $_" -ForegroundColor Yellow
}
Pop-Location

# ---------------------------------------------------------------
# 8. Ensure test scaffolding exists
# ---------------------------------------------------------------
Write-Host "[8/8] Ensuring test infrastructure..." -ForegroundColor Yellow

# Backend tests directory
$BackendTestsDir = "$ProjectRoot\backend\tests"
if (-not (Test-Path $BackendTestsDir)) {
    New-Item -ItemType Directory -Path $BackendTestsDir -Force | Out-Null
    Write-Host "  Created backend\tests\" -ForegroundColor Green
}
if (-not (Test-Path "$BackendTestsDir\__init__.py")) {
    New-Item -ItemType File -Path "$BackendTestsDir\__init__.py" -Force | Out-Null
    Write-Host "  Created backend\tests\__init__.py" -ForegroundColor Green
}

# Verify pytest.ini exists
if (-not (Test-Path "$ProjectRoot\backend\pytest.ini")) {
    Write-Host "  WARNING: backend\pytest.ini missing. Tests may not run correctly." -ForegroundColor Yellow
} else {
    Write-Host "  backend\pytest.ini present." -ForegroundColor Green
}

# Verify vitest config exists
if (-not (Test-Path "$ProjectRoot\frontend\vitest.config.ts")) {
    Write-Host "  WARNING: frontend\vitest.config.ts missing. Tests may not run correctly." -ForegroundColor Yellow
} else {
    Write-Host "  frontend\vitest.config.ts present." -ForegroundColor Green
}

Write-Host "  Test infrastructure ready." -ForegroundColor Green

# ---------------------------------------------------------------
# Done!
# ---------------------------------------------------------------
Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if ($envCreated) {
    Write-Host "  1. Edit .env with your real API keys:" -ForegroundColor White
    Write-Host "     - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (required for login)" -ForegroundColor Gray
    Write-Host "     - AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_API_KEY" -ForegroundColor Gray
    Write-Host "     - OPENAI_API_KEY" -ForegroundColor Gray
    Write-Host "     - ANTHROPIC_API_KEY (optional)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. Create 'talk_to_folder' database in PG Admin if not done" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. Install Temporal CLI (recommended):" -ForegroundColor White
    Write-Host "     https://docs.temporal.io/cli" -ForegroundColor Gray
    Write-Host "     Or Docker will be used as fallback." -ForegroundColor Gray
    Write-Host ""
    Write-Host "  4. Run the app:" -ForegroundColor White
    Write-Host "     .\run.ps1" -ForegroundColor Gray
} else {
    Write-Host "  1. Run: .\run.ps1" -ForegroundColor White
}
Write-Host ""
