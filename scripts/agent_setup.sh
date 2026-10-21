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
  py="$(conda info --base)/envs/jev-tune/bin/python"
  if [ ! -x "$py" ]; then
    echo "[setup] conda env missing, falling back to venv"
    python3 -m venv .venv && py=".venv/bin/python"
  fi
else
  echo "[setup] conda unavailable, using venv"
  python3 -m venv .venv && py=".venv/bin/python"
fi

echo "[setup] installing dependencies (CPU only)"
"$py" -m pip install --quiet --upgrade pip
"$py" -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
"$py" -m pip install --quiet numpy scipy scikit-learn pytest pyyaml matplotlib pillow onnx onnxruntime

export PYTHONPATH="$repo/src"
echo "[setup] environment ready"
exec "$py" -m jev_tune.cli status --json
