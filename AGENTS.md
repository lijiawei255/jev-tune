# Agent guide

This file is for an automated assistant that a user pointed at this repository.
It is written to be read top-to-bottom and executed without asking questions.

## What this project is

A control-parameter autotuner whose decision step is a **Jev-style typed decision**
(`choice` / `score` / `noul`) produced by a ~200 KB CPU model in **0.19 ms**,
instead of an autoregressive LLM call. It tunes PID gains for a plant it can
only test by simulation.

Two runtimes ship in this repo:

| path | runs where | needs |
| :--- | :--- | :--- |
| Python (`src/jev_tune`, `scripts/00`–`07`) | CPU, any OS | conda/venv, torch, scipy |
| MATLAB (`matlab/jev_tune_model.m`) | MATLAB R2024b + Simulink | the trained weights `.mat` |

## Setup (idempotent, no prompts)

```bash
bash scripts/agent_setup.sh          # macOS / Linux / WSL
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1
```

Both scripts create the conda env `jev-tune` (Python 3.12) if missing, install
the CPU dependency set, export `PYTHONPATH=src`, and finish by printing
`python -m jev_tune.cli status --json`.

If conda is unavailable, the scripts fall back to `python -m venv .venv`.

## Verify

```bash
python -m jev_tune.cli status --json   # exit 0 = ready, 2 = missing prerequisites
python -m jev_tune.cli check           # runs pytest, exit 0 = green
python -m jev_tune.cli demo --plants 12 --json
```

`demo` prints, for held-out plants the model never saw:

```json
{"cost_median": {"jev_head": 0.24, "cmaes_18sims": 1.42, "zn": 2.19}}
```

Lower is better. That is the whole claim of the project, end to end, in ~20 s.

## Reproduce the full pipeline (≈25 min CPU, no GPU)

```bash
python scripts/01_make_dataset.py --plants 500 --steps 20 --seed 0 --out data/g_0.npz
#    ... same for --seed 1..3 (four chunks, they are independent and parallel-safe)
python scripts/00_merge_chunks.py
python scripts/02_train.py --data data/expert_train.npz
python scripts/04_export_onnx.py
python scripts/06_export_weights_mat.py      # only needed for the MATLAB runtime
python scripts/03_evaluate.py --plants 120
python scripts/05_report.py
```

Every script is non-interactive, takes `--seed`, and writes only inside
`data/`, `models/`, `research/`, `assets/` (all git-ignored except `research/`
and `assets/`).

## Simulink runtime

```matlab
addpath('matlab');
R = jev_tune_model('path/to/Model.slx', 'work_dir', 20, 10, 2.5);
% iters=20, stopTime=10 s, stepGain=2.5
```

Requires `models/jev_head_weights.mat` (from `scripts/06_export_weights_mat.py`).
The model must have root-level `Gain_Kp` / `Gain_Ki` / `Gain_Kd` blocks and
Scope blocks named `Scope-*`. See `docs/STEP4_RESULTS.md`.

## Rules for automation

* Never edit files under `data/`, `models/`, or `assets/` by hand; regenerate them.
* The decision contract is `Choice` / `Score` / `Noul` (`src/jev_tune/primitives.py`).
  Do not add a "regress the gain directly" path; that is the thing this project tests.
* `noul` is advice; the deterministic safety gate in `evaluate.py` / `jev_tune_model.m`
  holds the veto. Keep it that way.
* Long jobs: dataset generation and training are the only slow steps. Run the
  four dataset chunks in parallel, then merge.
* Report numbers, not adjectives. If a baseline beats the head, say so — the
  benchmark is the product.

## Where the numbers come from

| file | content |
| :--- | :--- |
| `docs/STEP1_RESULTS.md` | latency, calibration, held-out benchmark table |
| `docs/STEP4_RESULTS.md` | real Simulink model: 5 experiments, cost 1.24 → 0.60 |
| `research/results/eval_heldout_120.json` | raw evaluation output |
| `assets/` | the demo GIF and figures used in the README |
