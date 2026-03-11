# deploy.ps1 — Build and push container(s) to Azure Container Registry
# Usage: .\deploy.ps1              # deploy API (default)
#        .\deploy.ps1 -Target api  # deploy API
#        .\deploy.ps1 -Target worker  # deploy Worker

param(
    [ValidateSet("api", "worker")]
    [string]$Target = "api"
)

$ErrorActionPreference = "Stop"

$envFile = "$PSScriptRoot\.env.deploy"
if (!(Test-Path $envFile)) { throw "Missing $envFile — copy .env.deploy.example and fill in values" }
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+?)\s*=\s*(.+)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
    }
}

$registry    = $env:ACR_REGISTRY
$acrUsername = $env:ACR_USERNAME
$acrPassword = $env:ACR_PASSWORD

if ($Target -eq "api") {
    $image      = "$registry/recap:latest"
    $dockerfile = "Dockerfile"
    $label      = "API"
    $totalSteps = 4
} else {
    $image      = "$registry/recap-worker:latest"
    $dockerfile = "Dockerfile.worker"
    $label      = "Worker"
    $totalSteps = 3
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$step = 0

function Write-Step($msg) {
    $script:step++
    Write-Host "`n[$script:step/$totalSteps] $msg" -ForegroundColor Cyan
}

# ── Tests ────────────────────────────────────────────────────────────
Write-Step "Running tests"
& "$PSScriptRoot\test.ps1"

# ── Bump version (API only) ─────────────────────────────────────────
if ($Target -eq "api") {
    Write-Step "Bumping version"
    Push-Location "$PSScriptRoot\frontend"
    npm version patch --no-git-tag-version | Out-Null
    $newVersion = (Get-Content package.json | ConvertFrom-Json).version
    Pop-Location
    Write-Host "  v$newVersion" -ForegroundColor Green
}

# ── Docker build ─────────────────────────────────────────────────────
Write-Step "Building $label Docker image"

$ErrorActionPreference = "Continue"
$acrPassword | docker login $registry -u $acrUsername --password-stdin 2>$null | Out-Null
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) { throw "Docker login failed" }
Write-Host "  Logged in to ACR"

$ErrorActionPreference = "Continue"
$buildOut = docker build -t $image -f $dockerfile --quiet . 2>&1 | Out-String
$buildExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($buildExit -ne 0) {
    Write-Host "  Build failed - pruning Docker build cache and retrying..." -ForegroundColor Yellow
    docker builder prune -f 2>$null | Out-Null
    $ErrorActionPreference = "Continue"
    $buildOut = docker build -t $image -f $dockerfile --quiet . 2>&1 | Out-String
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($buildExit -ne 0) {
        Write-Host "`n--- Docker build output ---" -ForegroundColor Yellow
        Write-Host $buildOut
        throw "Docker build failed"
    }
}
Write-Host "  Image built" -ForegroundColor Green

# ── Docker push ──────────────────────────────────────────────────────
Write-Step "Pushing to ACR"

$ErrorActionPreference = "Continue"
$pushOut = docker push $image 2>&1 | Out-String
$pushExit = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pushExit -ne 0) {
    Write-Host $pushOut
    throw "Docker push failed"
}
Write-Host "  Pushed $image" -ForegroundColor Green

# ── Done ─────────────────────────────────────────────────────────────
$sw.Stop()
$mins = [math]::Floor($sw.Elapsed.TotalMinutes)
$secs = $sw.Elapsed.Seconds
Write-Host "`n$label deploy complete ($mins`m $secs`s)" -ForegroundColor Green
Write-Host "  Image: $image"
Write-Host "  Restart the $label App Service from Azure Portal.`n"
