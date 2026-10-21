# Agent guide

This file is for an automated assistant that a user pointed at this repository.
It is written to be read top-to-bottom and executed without asking questions.

## What this project is

A control-parameter autotuner whose decision step is a **Jev-style typed decision**
(`choice` / `score` / `noul`) produced by a ~200 KB CPU model in **0.19 ms**,
instead of an autoregressive LLM call. It tunes PID gains for a plant it can
only test by simulation.

**It uses the Jev *interface*, not the Jev model.** Laya's 421 M text encoder is
not in the runtime; the policy is trained in this repo. Say so if a user asks.

Two runtimes ship in this repo:

| path | runs where | needs |
| :--- | :--- | :--- |
| Python (`src/jev_tune`, `scripts/00`–`09`) | CPU, any OS | conda/venv, torch, scipy |
| MATLAB (`matlab/jev_tune_model.m`) | MATLAB R2019a+ + Simulink | the trained weights `.mat` |

## Setup (idempotent, no prompts)

```bash
bash scripts/agent_setup.sh          # macOS / Linux / WSL
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1
```

Both scripts create the conda env `jev-tune` (Python 3.12) if missing, install
the CPU dependency set, export `PYTHONPATH=src`, and finish by printing
`python -m jev_tune.cli status --json`. Without conda they fall back to `.venv`.

## Verify

```bash
python -m jev_tune.cli status --json   # exit 0 = ready, 2 = missing prerequisites
python -m jev_tune.cli check           # pytest, exit 0 = green
python -m jev_tune.cli demo --plants 12 --json
python -m jev_tune.cli matlab --probe --json   # MATLAB release and capabilities
```

## Tune a model

```bash
python -m jev_tune.cli matlab --model C:/path/Model.slx --json
```
Options that matter when the model is not the reference one:

| flag | when |
| :--- | :--- |
| `--kp-block/--ki-block/--kd-block` | gains are not `Gain_Kp/Gain_Ki/Gain_Kd` |
| `--controller pid_block --pid-block "PID Controller"` | the controller is a masked PID block |
| `--measure-scope/--input-scope` | scopes are not `Scope_Position/Scope_Current` |
| `--ref-source 0.5236` | the reference cannot be inferred from `Step × Deg2Rad` |
| `--stop-time` | model horizon differs from its own `StopTime` |

A JSON `warnings` array is returned when the setup is far from the training
distribution (e.g. `StopTime` far from 10 s).

## Specialise on one plant family

The shipped head is zero-shot. When a project sits outside the training zoo
(dead band, inverse response, unstable plant), fine-tune a specialist instead of
hoping:

```bash
python scripts/10_specialize.py --spec plant.json --name myplant
# plant.json: {"num":[1], "den":[0.5,1,0], "delay_s":0.05, "u_max":1.6}
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

It jitters the plant, runs the expert on a small zoo, fine-tunes for a few
epochs (~1–3 min CPU) and reports zero-shot vs specialised on held-out jitters.

## Throughput (read before running many jobs)

Measured on the reference machine: MATLAB cold start ≈ 50 s, model setup ≈ 28 s,
Kp sweep ≈ 40 s, simulation ≈ 0.4 s per experiment.

* **one process per job is SLOWER than an agent loop** (122 s vs 60 s);
* a warm worker gives 8.8 s per job; a long-lived session 2.7 s.

So: for more than a couple of jobs use `jev-tune batch --jobs jobs.json`
(one MATLAB for the whole queue) or the MCP server, which keeps a worker alive.

## MCP server

```jsonc
{ "mcpServers": { "jev-tune": { "command": "jev-tune-mcp" } } }
```

Tools: `tune_status`, `tune_probe_matlab`, `tune_simulink`, `tune_demo`.
`tune_simulink` reuses a warm MATLAB; do not spawn one per call.

## Before pointing it at a user's model

Read `docs/APPLICABILITY.md`. Cascade, MIMO, non-PID controllers and hardware
in the loop are outside the design; tracking/disturbance objectives need new
metrics and a retrain. The tuner never returns a gain set worse than the one
it started from, and `scripts/11_robustness.py` reproduces that claim.

## Rules for automation

* Never edit `data/`, `models/`, `assets/` by hand; regenerate them.
* The decision contract is `Choice` / `Score` / `Noul` (`primitives.py`). Do not
  add a "regress the gain directly" path; that is what this project tests.
* `noul` is advice; the deterministic safety gate holds the veto.
* **A model left in Fast Restart raises a modal dialog on close.** The tuner
  disables caching in desktop sessions, and `jev_close_all` closes everything
  safely. Never call `close_system` on a Fast-Restart model directly.
* Report numbers, not adjectives. If a baseline beats the head, say so.

## Documentation languages

Every human-facing document is bilingual: English first, then 简体中文 in the
same file, with a language switcher at the top (`README` has a separate
`README.zh-CN.md`). Keep that structure when you edit docs.

## Where the numbers come from

| file | content |
| :--- | :--- |
| `docs/STEP1_RESULTS.md` | latency, calibration, held-out benchmark |
| `docs/STEP4_RESULTS.md` | real Simulink model: 5 experiments, cost 1.24 → 0.60 |
| `docs/GENERALIZATION.md` | ten out-of-zoo scenarios, where it fails and why |
| `docs/SCALE.md` | throughput economics, concurrency, version matrix |
| `docs/APPLICABILITY.md` | what fits, the no-regression evidence, per-task effort |
| `research/results/*.json` | raw evaluation output |
