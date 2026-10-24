# jev-tune agent setup (Windows / PowerShell). Idempotent, no prompts.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repo

function Test-Cmd($name) { $null -ne (Get-Command $name -ErrorAction SilentlyContinue) }
function Invoke-SetupPython {
    & $py @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$activate = "(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression; conda activate jev-tune"

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
        $activate = "& '$($venv.Replace("'", "''"))\Scripts\Activate.ps1'"
    }
} else {
    Write-Host "[setup] conda unavailable, using venv"
    $venv = Join-Path $repo ".venv"
    if (-not (Test-Path $venv)) { python -m venv $venv }
    $py = Join-Path $venv "Scripts\python.exe"
    $activate = "& '$($venv.Replace("'", "''"))\Scripts\Activate.ps1'"
}

Write-Host "[setup] installing dependencies (CPU only)"
Invoke-SetupPython -m pip install --quiet --upgrade pip

# torch CPU wheel first: the default index would pull ~2.5 GB of CUDA libs
Invoke-SetupPython -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
Invoke-SetupPython -m pip install --quiet numpy scipy scikit-learn pytest matplotlib onnx onnxruntime
Invoke-SetupPython -m pip install --quiet --no-deps -e $repo

Write-Host "[setup] python: $py"
Write-Host "[setup] activate: $activate"
Write-Host "[setup] environment ready"
Invoke-SetupPython -m jev_tune.cli status --json
