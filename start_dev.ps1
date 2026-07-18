$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = "1"

$env:VIVACITY_WORK_ROOT = if ($env:VIVACITY_WORK_ROOT) {
    $env:VIVACITY_WORK_ROOT
} else {
    (Resolve-Path -LiteralPath "..").Path + "\vivacity_job_runs"
}

New-Item -ItemType Directory -Force -Path $env:VIVACITY_WORK_ROOT | Out-Null

$port = if ($env:VIVACITY_PORT) { $env:VIVACITY_PORT } else { "8000" }

& ".\manim-env\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port $port
