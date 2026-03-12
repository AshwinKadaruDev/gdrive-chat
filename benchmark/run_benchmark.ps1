# Benchmark launcher — activates venv, sets PYTHONPATH, forwards args to run.py
param([Parameter(ValueFromRemainingArguments)]$args)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

Push-Location $projectRoot
try {
    $venv = "backend\.venv\Scripts\Activate.ps1"
    if (Test-Path $venv) { & $venv }
    $env:PYTHONPATH = "backend"
    python benchmark/run.py @args
} finally {
    Pop-Location
}
