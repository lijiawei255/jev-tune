# jev-tune agent setup (Windows / PowerShell). Idempotent, no prompts.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repo

function Test-Cmd($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }

if (Test-Cmd conda) {
    $envs = conda env list 2>$null
    if (-not ($envs -match "jev-tune")) {
        Write-Host "[setup] creating conda env jev-tune (python 3.12)"
        conda create -n jev-tune python=3.12 -y | Out-Null
    }
    $py = Join-Path (conda info --base) "envs\jev-tune\python.exe"
    if (-not (Test-Path $py)) {
        Write-Host "[setup] conda env not found, falling back to venv"
        $venv = Join-Path $repo ".venv"
        if (-not (Test-Path $venv)) { python -m venv $venv }
        $py = Join-Path $venv "Scripts\python.exe"
    }
} else {
    Write-Host "[setup] conda unavailable, using venv"
    $venv = Join-Path $repo ".venv"
    if (-not (Test-Path $venv)) { python -m venv $venv }
    $py = Join-Path $venv "Scripts\python.exe"
}

Write-Host "[setup] installing dependencies (CPU only)"
& $py -m pip install --quiet --upgrade pip

# torch CPU wheel first: the default index would pull ~2.5 GB of CUDA libs
& $py -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
& $py -m pip install --quiet numpy scipy scikit-learn pytest pyyaml matplotlib pillow onnx onnxruntime

$env:PYTHONPATH = Join-Path $repo "src"
Write-Host "[setup] environment ready"
& $py -m jev_tune.cli status --json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
