# Agent guide

## Initial clone and optional evidence / 首次克隆与按需证据

The v0.10.1 distribution separates experimental payloads from reachable Git
history. An ordinary clone needs no special flags and retains complete source,
formal PID artifacts and six non-PID model/calibration JSON files:

```sh
git clone https://github.com/lijiawei255/jev-tune.git
cd jev-tune
```

Runtime use needs no research records. Restore the optional motor-valve benchmark
separately with `python scripts/65_restore_benchmark.py`. Before pytest or scientific claims run
`python scripts/59_research_data.py --fetch all`, followed by
`python scripts/history_sources.py --root . --restore-pinned`; both accept `--from-dir`
for pinned offline assets. Script 60 prepares a new checkout and performs complete
verification. The source capsule supplies selected original scientific source/tree
objects, not complete old Git history. Public manifests distinguish unchanged
original objects from sanitized metadata derivatives. Script-42 maintenance commands
are not promised to work directly; use the current script-44/16 frozen verifiers
after restoration. Publication acceptance requires actual pinned assets and
verification receipts; do not infer it from these instructions, rewrite an existing
user's checkout, or publish a history transition without authorization.
See [distribution and history boundaries](docs/DISTRIBUTION.md).

v0.10.1分发从可达Git历史移出实验载荷。以上普通克隆无需特殊参数，保留完整源码、
正式PID产物及六份非PID模型/校准JSON。运行复用不需要研究记录；可选电机阀门基准通过
`python scripts/65_restore_benchmark.py`单独恢复。pytest或科学claims前
先执行59的`--fetch all`，再执行`history_sources.py --root . --restore-pinned`；两者均
支持`--from-dir`离线附件。60脚本在新目录完成恢复与完整核验。源码胶囊提供选定的原始
科学源码/tree对象，并非完整旧Git历史；公开清单区分未改动的原对象与脱敏元数据派生件。
旧42维护命令不保证直接可用，恢复后使用当前44/16冻结核验入口。发布验收以真实固定
附件和核验收据为准，不能仅从本文推断；不要重写用户既有检出，或未经授权发布历史切换。
详见[分发与历史边界](docs/DISTRIBUTION.md)。

This file is for an automated assistant that a user pointed at this repository.
It is written to be read top-to-bottom and executed without asking questions.

## What this project is

A control-parameter autotuner whose decision step is a **Jev-style typed decision**
(`choice` / `score` / `noul`) produced by a small CPU model,
instead of an autoregressive LLM call. It tunes PID gains for a plant it can
only test by simulation.

**It uses the Jev *interface*, not the Jev model.** Laya's 421 M text encoder is
not in the runtime; the policy is trained in this repo. Say so if a user asks.
This project is **Jev-inspired and not affiliated with TypeSafe AI**; it contains
no Jev weights, no text input and no API access. `docs/JEV_MAPPING.md` lists what
is borrowed and what is not. `docs/COMPUTE.md` separates measured forward latency
from the complete typed decision and default abstention path. Host measurements
are not a target-board worst-case timing guarantee.

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
   nothing: the signal graph and confirming simulations already agree. Read
   the discovery ledger for the actual number of simulation attempts.
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
`result["final_J"] <= min(result["history"][0]["J"], result.get("own_J", float("inf")))`.

That inequality is the project's promise: the tuner never returns a gain set worse
than the better of its own starting point and the gains the model already ran.
`own_J` is the cost of those existing gains; it is reported so you can quote both.
If a baseline beats the head, say so.

## Setup (idempotent, no prompts)

```bash
bash scripts/agent_setup.sh          # macOS / Linux / WSL
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1
```

Both scripts create the conda env `jev-tune` (Python 3.12) if missing, or fall
back to `.venv`. They install CPU dependencies and the editable project with
`--no-deps` in that selected interpreter, then print status, `[setup] python:`
and `[setup] activate:`. The subprocess does not activate the caller's shell.
Before the bare `python` commands below, run the printed activation command in
the current shell. For agents using separate shells, use the exact reported
Python path (also `executable` in status JSON) for every Python command, including
restoration. Replace these example paths with the actual executable:

```bash
"/path/from/setup/python" -m jev_tune.cli status --json
```

```powershell
& "C:/path/from/setup/python.exe" -m jev_tune.cli status --json
```

两个脚本在缺少时创建conda环境`jev-tune`（Python 3.12），或回退到`.venv`；在所选解释器
中先安装CPU依赖，再用`--no-deps`以editable方式安装项目，并输出status、`[setup] python:`
和`[setup] activate:`。子进程不会激活调用者的shell。执行下文裸`python`前，先在当前
shell执行输出的激活命令。Agent使用独立shell时，每条Python命令（包括恢复命令）均应
显式调用所报告的解释器路径（status JSON的`executable`），按以上Bash或PowerShell
写法替换示例路径，不能假定后续shell的PATH已切换。

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

**v0.9.0 scope:** the timing figures below are historical. Cross-job compiled
model and sweep caches are disabled: each job copies its original source again,
so original-gain comparisons and changed configurations cannot inherit a prior
job's tuned state. The process stays warm and Fast Restart is retained within
each job. Report current `timings` and `n_total_simulations`, including discovery
and setup. `iters` is not an end-to-end hard simulation cap.

**v0.9.0范围：**下列耗时为历史数据。跨任务编译模型与扫描缓存已停用，每次从原件
重新复制，避免原增益比较或新配置继承上一任务的调参状态。进程仍常驻，单任务内保留
Fast Restart。报告当前`timings`及包含发现和准备阶段的`n_total_simulations`；
`iters`不是端到端仿真硬上限。

Measured on the reference machine: MATLAB cold start ≈ 50 s, then ≈ 0.11 s per
simulation (Fast Restart, 10 s horizon). **Without** `--auto` the model setup is
≈ 24 s and the Kp sweep ≈ 39 s; **with** `--auto` discovery pays the load and
compile first, so `timings` reports setup ≈ 1 s and sweep ≈ 4 s for the same job.
(The "0.4 s per experiment" in older notes was the Python zoo, not MATLAB.)

* **one process per job is SLOWER than an agent loop** (122 s vs 60 s);
* a warm worker gives 8.8 s per job; a long-lived session 2.7 s (both measured
  without `--auto`; with it, each job also pays the discovery pass).

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
