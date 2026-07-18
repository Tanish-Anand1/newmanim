$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = "1"

$env:VIVACITY_WORK_ROOT = if ($env:VIVACITY_WORK_ROOT) {
    $env:VIVACITY_WORK_ROOT
} else {
    (Resolve-Path -LiteralPath "..").Path + "\vivacity_job_runs"
}
$env:VIVACITY_CACHE_ROOT = if ($env:VIVACITY_CACHE_ROOT) {
    $env:VIVACITY_CACHE_ROOT
} else {
    (Resolve-Path -LiteralPath "..").Path + "\vivacity_cache"
}
$executionMode = if ($env:JOB_EXECUTION_MODE) { $env:JOB_EXECUTION_MODE } else { "worker" }
$env:JOB_EXECUTION_MODE = $executionMode

New-Item -ItemType Directory -Force -Path $env:VIVACITY_WORK_ROOT | Out-Null
New-Item -ItemType Directory -Force -Path $env:VIVACITY_CACHE_ROOT | Out-Null

if ($executionMode -eq "rq") {
    & ".\manim-env\Scripts\python.exe" -m app.rq_worker
} else {
    & ".\manim-env\Scripts\python.exe" -m app.worker
}
