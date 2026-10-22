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
| MATLAB (`matlab/jev_tune_model.m`) | **R2024b verified**, R2019a+ expected (see `docs/SCALE.md`) | the trained weights `.mat` |

## If the user only says one sentence

The common request is *"use this project to tune my model"*, from someone who
knows MATLAB but not shells. Do not send them back to the README, and do not ask
them to rename blocks. Do this:

1. **Find MATLAB.** `jev-tune status --json`; if `ok` is false follow its `next`
   field, or set `MATLAB_EXE`. Report the exact path you tried.
2. **Find the model.** If the user gave a path, use it. If not, look for
   `*.slx` / `*.mdl` in the working directory, newest first. Exactly one → use
   it. More than one → **ask once**, with the list. That is the only question
   you may ask before tuning.
3. **If anything fails, run `jev-tune doctor --model <model>` before asking
   the user.** It prints one line per check and names the missing variable,
   referenced model or cascade. Report its `next` line, not the raw error.
4. **Discover, do not assume.**
   `jev-tune discover --model <model> --json --out discover.json`
   Read `confidence`, `controller`, `measure`, `reference`. At `high`, ask
   nothing: the signal graph and two confirming simulations already agree.
   At `medium`, quote the candidates and let the user pick.
5. **Tune.**
   `jev-tune matlab --model <model> --config discover.json --plot before_after.png --write-back --json`
   If `discover` reported several **independent** loops (a gantry, an oven with
   zones), use `--all-loops` instead: it tunes each one, carries the gains
   forward and writes one file with every loop's gains.
6. **Report, in the user's language:** start cost, final cost, number of
   experiments, the three gains, and the path of `*_tuned.slx`. Numbers come
   from the JSON verbatim; "about 40 % better" is banned, "1.24 → 0.60" is not.
7. **If it fails**, read `code` and follow the table below. Do not retry the
   same command twice.

Never modify the user's model file. `--write-back` writes `<name>_tuned.slx`
next to it; the original stays byte-identical.

Respond in the language the user wrote in: an English-speaking user gets
English, a Chinese-speaking user gets Chinese. Do not translate the JSON keys.

### Error codes

| `code` | meaning | what you do |
| :--- | :--- | :--- |
| `matlab_missing` | no MATLAB on PATH | show both install hints, ask for `MATLAB_EXE` |
| `model_not_found` | bad path | ask once more |
| `no_loop` | no feedback loop found | the model may be open-loop; point at `docs/APPLICABILITY.md` |
| `cascade_unsupported` | several masked PID blocks | say cascade is out of scope; offer inner-then-outer |
| `cascade_suspect` | two loops nested, or two integrators in one path | **do not tune**; explain the inner-first plan and offer to tune one loop by name |
| `ambiguous_junction` | no summing junction could be confirmed | the model probably needs workspace variables; ask the user to run it once in Simulink |
| `ambiguous_controller` | two plausible Kp blocks | list `candidates`, ask which is the controller |
| `loop_not_found` | `--all-loops` asked for a junction that is not verified | re-run `discover` and use a name from `loops` |
| `referenced_model_unsupported` | Model blocks: the contents live in another file | tune that file instead, or flatten the hierarchy |
| `no_signal` | nothing was logged | re-run `discover`; if it still fails, ask which Scope shows the output |
| `sim_failed`, `model_error` | Simulink refused the model | it needs workspace variables; ask the user to run it once in Simulink |
| `tune_failed` | anything else | quote `error`; do not guess a fix |

### When discovery fails on a model that should work

That is a bug in this project, not in the user's model. Ask them to open the
"Discovery failed on a real model" issue template in `.github/ISSUE_TEMPLATE/`
and paste the `--json` output; it already contains every candidate junction and
the reason. Do not patch around it silently by hardcoding block names.

### Before you claim success

`result["ok"]` must be true **and**
`result["final_J"] <= result["history"][0]["J"]`. That inequality is the
project's promise: the tuner never returns a gain set worse than the one it
started from. If a baseline beats the head, say so.

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
python -m jev_tune.cli matlab --model C:/path/Model.slx --auto --json
```
`--auto` runs discovery first, so this works on a model whose blocks are called
anything at all. Options that matter when discovery is not enough:

| flag | when |
| :--- | :--- |
| `--config discovered.json` | reuse what `discover --out` found |
| `--kp-block/--ki-block/--kd-block` | override the discovered gain blocks |
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
`--workers N` runs N warm MATLAB processes in parallel; the ceiling is your
MATLAB licence, not the code.

## MCP server

```jsonc
{ "mcpServers": { "jev-tune": { "command": "jev-tune-mcp" } } }
```

Tools: `tune_status`, `tune_probe_matlab`, `tune_doctor`, `tune_discover`,
`tune_simulink`, `tune_apply_gains`, `tune_demo`. `tune_discover` returns a `config` object
that `tune_simulink` accepts as-is. `tune_simulink` reuses a warm MATLAB; do
not spawn one per call.

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
* Ask at most one question before tuning (the model path, or a block the
  discoverer could not separate). Everything else is a discovered fact.
* Reply in the user's language; never answer a Chinese question with English
  prose or the other way round.
* `jev-tune discover` is cheap (seconds) and safe (it works on a copy). Prefer
  it over reading the model with your own heuristics.

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
