#!/usr/bin/env bash
# jev-tune agent setup (macOS / Linux / WSL). Idempotent, no prompts.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

if command -v conda >/dev/null 2>&1; then
  if ! conda env list | grep -q '^jev-tune '; then
    echo "[setup] creating conda env jev-tune (python 3.12)"
    conda create -n jev-tune python=3.12 -y >/dev/null
  fi
  conda_base="$(conda info --base)"
  py="$conda_base/envs/jev-tune/bin/python"
  printf -v activate 'source %q && conda activate jev-tune' "$conda_base/etc/profile.d/conda.sh"
  if [ ! -x "$py" ]; then
    echo "[setup] conda env missing, falling back to venv"
    python3 -m venv .venv && py="$repo/.venv/bin/python"
    printf -v activate 'source %q' "$repo/.venv/bin/activate"
  fi
else
  echo "[setup] conda unavailable, using venv"
  python3 -m venv .venv && py="$repo/.venv/bin/python"
  printf -v activate 'source %q' "$repo/.venv/bin/activate"
fi

echo "[setup] installing dependencies (CPU only)"
"$py" -m pip install --quiet --upgrade pip
"$py" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
"$py" -m pip install --quiet numpy scipy scikit-learn pytest pyyaml matplotlib pillow onnx onnxruntime
"$py" -m pip install --quiet --no-deps -e "$repo"

echo "[setup] python: $py"
echo "[setup] activate: $activate"
echo "[setup] environment ready"
exec "$py" -m jev_tune.cli status --json
