# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2024b%20verified-orange)](docs/SCALE.md#4-matlab-versions)
[![decision latency](https://img.shields.io/badge/decision-0.19%20ms-brightgreen)](docs/STEP1_RESULTS.md)
[![model size](https://img.shields.io/badge/model-200%20KB-lightgrey)](docs/STEP1_RESULTS.md)
[![platform](https://img.shields.io/badge/platform-Python%20any%20OS%20%C2%B7%20MATLAB%20Windows-lightgrey)](docs/SCALE.md#4-matlab-versions)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![中文](https://img.shields.io/badge/README-简体中文-red)](README.zh-CN.md)

**PID autotuning where each decision is a typed judgement, not a paragraph.**
A 200 KB model reads the step response and returns one bounded gain step in
**0.19 ms on a laptop CPU** — no autoregressive LLM, no cloud, no GPU. The
shipped loop also **holds** a gain axis when its calibrated confidence is low;
it does not touch the plant when it is unsure.

> **Jev-inspired, not affiliated.** It uses the *Jev interface* — the three typed
> primitives `choice` / `score` / `noul` with calibrated probabilities — not the
> hosted Jev model or Laya's 421 M text encoder. The runtime policy is a 200 KB
> numeric head trained in this repo; Laya is only mentioned as a text baseline
> that was never wired in. This project is **not affiliated with, endorsed by, or
> sponsored by TypeSafe AI**. What is borrowed and what is not:
> [`docs/JEV_MAPPING.md`](docs/JEV_MAPPING.md).

## Let your agent do it

If you use a coding agent (Claude Code, Codex, OpenCode, Cursor — anything that
can run a shell), you do not need the rest of this file. Paste one sentence,
with your own model path:

> **"Use github.com/lijiawei255/jev-tune to tune the PID gains in
> `C:\work\MyMotor.slx`, then show me the before/after curve."**

The agent reads [`AGENTS.md`](AGENTS.md), which tells it to run `jev-tune
discover` first. Discovery follows the signal graph — not block names — to find
the gains, the measured signal and the reference, then confirms the guess with
two extra simulations:

```bash
jev-tune discover --model MyMotor.slx --json      # what the agent runs first
jev-tune matlab --model MyMotor.slx --auto --plot before_after.png --write-back
```

No block renames, no scope called `Scope_Position`, no reference typed by hand.
When the model is ambiguous the command says `confidence: medium` instead of
guessing, and the agent asks you one question.

If something refuses or fails, `jev-tune doctor --model <file>` explains why in
nine lines — does it load, does it compile, does it use referenced or protected
models, what solver, can a loop be found at all:

```console
$ jev-tune doctor --model MyMotor.slx
check       ok?   detail
file        ok    MyMotor.slx (95 KB)
loads       ok    MATLAB 2024b
referenced  ok    none
protected   ok    none
stateflow   ok    none
compiles    FAIL  Unrecognized function or variable 'Tsim'.
                  -> define the variables the model asks for, then run it once
solver      ...
```

**Several loops in one model?** Independent loops (four axes, three zones) are
tuned one after another with `--all-loops`. A **cascade** is refused on purpose:
`cascade_suspect` comes back with the loops it found, because tuning one loop of
a cascade and reporting success would be worse than saying so. See
[`docs/APPLICABILITY.md`](docs/APPLICABILITY.md#several-loops-in-one-model).

![discovery on an unseen model](assets/discover.gif)

*What `discover` does on a lab motor, **step by step and from the model
itself**: the error junction is confirmed by one run (the reference and the
steady-state output are the same quantity), each gain is classified by what sits
between it and that junction, and two extra simulations say whether doubling it
actually moves the response. The block names above are never used to decide
anything — `Gain_Kp` could be called `alpha` and the result would be identical.
Regenerate with `scripts/15_make_discovery_gif.py`.*

## Where to read next

| I want to… | go to |
| :--- | :--- |
| see it run in a minute | [Try it](#try-it) |
| watch a full run, with real output | [`docs/EXAMPLES.md`](docs/EXAMPLES.md) |
| know why my model will not tune | `jev-tune doctor --model <file>` |
| know whether my model qualifies | [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) |
| understand the decision contract | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| see what is borrowed from Jev, and what is not | [`docs/JEV_MAPPING.md`](docs/JEV_MAPPING.md) |
| know whether the typed path actually helps | [`docs/ABLATION.md`](docs/ABLATION.md) |
| know what "hold when unsure" costs | [`docs/ABSTENTION.md`](docs/ABSTENTION.md) |
| check the compute numbers (MACs, RAM, int8) | [`docs/COMPUTE.md`](docs/COMPUTE.md) |
| borrow the pattern for another domain | [`docs/TRANSFER.md`](docs/TRANSFER.md) |
| check how the budget is accounted | [`docs/BENCHMARK.md`](docs/BENCHMARK.md) |
| check the numbers myself | [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md), [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md), [`docs/CLAIMS.md`](docs/CLAIMS.md) |
| drive it from an agent or MCP | [`AGENTS.md`](AGENTS.md) |
| handle a plant family it has not seen | [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) |
| run hundreds of models | [`docs/SCALE.md`](docs/SCALE.md) |
| compare honestly with `pidtune` | [the pidtune section](docs/APPLICABILITY.md#if-you-already-have-an-accurate-model-use-pidtune) |

![seven methods racing on the same plants](assets/race.gif)

*Seven ways to tune the same 40 unseen plants. **Every number is measured**:
median cost after N experiments from one run of `scripts/12_make_race.py`, and
the right panel asks the question that matters — how long until the controller
is usable (J ≤ 0.6) — at 0.4 s per experiment. The hatched row is an agent with a
hosted model in the loop: its turn took a measured **5.3 s median** (GLM-5.3-Flash,
40 calls, 13 of them unparseable). Hand tuning has no curve on purpose — it
produces a single gain set after hours, not a series of experiments.*

![tuning a real Simulink DC motor](assets/tuning.gif)

*Every frame above is one real closed-loop experiment on the lab
DC-motor model in Simulink. The tuner is choosing `Kp`, `Ki`, `Kd` itself; the
right panel is the cost it is minimising. The best gains appeared after five
experiments (~0.55 s of simulation); the stall detector stopped the loop at nine.*

---

## The 15-second version

| | |
| :--- | :--- |
| **What it does** | picks the next PID gain step from the response it just measured, and holds when it is not confident |
| **How fast** | **0.19 ms** for the model forward, **0.73 ms** for a complete typed decision (ONNX, 1 CPU thread; p99 1.36 ms) vs **5.34 s** per turn for a hosted LLM agent (measured, 40 calls) |
| **How few experiments** | **5 experiments** on a real Simulink motor cut the cost from **1.238 to 0.598** (the recorded run; with the corrected gain sweep the same model starts better and the tuner returns the lab's own gains instead — [why](docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong)); the result is never worse than the better of the start and the gains your model already had |
| **How it generalises** | **validation family** (120 plants, used during design): **0.440** median / **1.038** p90 vs 0.567 / 1.705 for BO and CMA-ES. **Frozen test family** (120 thermal + dead-time plants, never used for any decision): **1.737** — **second**, behind a same-vocabulary hill climb at **1.711**, ahead of BO 1.877 and CMA-ES 1.976 |

![before and after](assets/before_after.png)

*Same plant, three gain sets. Grey: the Ziegler-Nichols start. Blue: after five
experiments. Dashed: the lab's hand-tuned solution. That run started from a
Ziegler-Nichols estimate produced by the Ku sweep as it was in v0.2; the sweep
was wrong in three ways and has since been fixed — see the correction in
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong).*

---

## Why this is different

**vs. LLM-agent tuning.** An agent loop ("read the plot → write a paragraph →
parse the answer") costs seconds per iteration, and the number is buried in
prose. Here the model emits three Jev primitives — `choice` for the step,
`score` for "how good is this response", `noul` for "is this step safe" — so the
decision is a probability vector you can threshold, log and calibrate. That
threshold is used **before** the plant is touched: `docs/ABSTENTION.md` measures
the coverage/cost trade-off of holding.

**vs. classical autotune.** Ziegler-Nichols and relay autotuning give you one
shot with no feedback. This keeps iterating, and it learns the *policy* once
across a whole family of plants, so a new plant needs no re-tuning of the tuner.

**vs. Bayesian optimisation and a same-size regression head.** At the same 20
experiments the head is at 0.440 median / 1.038 p90, BO at 0.567 / 1.510 and
CMA-ES at 1.705 / 2.519. Against a **regression head with the same encoder, the
same data and the same budget** the typed path is 0.439 vs 0.494, with a much
lighter tail (p90 1.039 vs 1.508) — that ablation is
[`docs/ABLATION.md`](docs/ABLATION.md), and it also shows that the deterministic
safety gate contributes nothing on this plant family.

**Why not just `pidtune`?** If you have an accurate model, use `pidtune`: two
experiments reach 0.742 here, and [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md#if-you-already-have-an-accurate-model-use-pidtune)
says so. This is for the case where you do not.

**When your plant is outside the training zoo** the head is not magic: it fails
on dead bands, inverse response and open-loop unstable plants (documented in
[`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)). The supported answer is a
**specialist** — one command, ~1.5 min of CPU:

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

Measured on a family the head had never seen: median cost **2.242 → 2.207 (−2 %)** after ~95 s of CPU on 30 held-out
jitters — i.e. the specialist is not a fix for this family. The v0.2/v0.3 figures
(−49 %, −16 %) were measured on scenario draws that were not reproducible before
0.4.0; `docs/SPECIALIZE.md` says so and no longer quotes them. Details: `docs/SPECIALIZE.md` — the v0.2 figure of −49 % came
from a head that has since been retrained, and does not reproduce.

---

## Try it

### Human

```bash
git clone https://github.com/lijiawei255/jev-tune && cd jev-tune
conda create -n jev-tune python=3.12 -y && conda activate jev-tune
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
jev-tune demo            # 12 held-out plants, head vs CMA-ES vs Z-N, ~20 s
```

Then, on **your** model, run the doctor before the tuner. It takes ~40 s (almost
all of it MATLAB starting) and answers the question that decides everything else:
can this model be tuned at all?

```bash
jev-tune doctor  --model C:/path/YourModel.slx          # loads, compiles, solver, loop
jev-tune matlab  --model C:/path/YourModel.slx --auto --plot before_after.png
```

If the `compiles` line fails, nothing downstream will work and it names the
missing workspace variable; if `tunable` fails, the reason is in that line and in
`--json`. Nine checks, one line each — see
[`docs/EXAMPLES.md`](docs/EXAMPLES.md) for the real output.

**Clone, do not `pip install jev-tune`.** The MATLAB bridge (`matlab/*.m`) and
the trained weights (`models/`, 600 KB) travel with the repository, so a wheel
from PyPI would be an incomplete package — the command would run and then fail
to find the thing that does the work. The repository *is* the distribution unit;
nothing here needs PyPI, Docker or a GPU. If `git clone` is slow on your
network, the green **Code → Download ZIP** button gives the same tree.

### Agent

Point your assistant at [`AGENTS.md`](AGENTS.md). The short form:

```bash
bash scripts/agent_setup.sh            # idempotent, no prompts
python -m jev_tune.cli status --json   # exit 0 = ready, 2 = exact fix printed
python -m jev_tune.cli discover --model YourModel.slx --json
python -m jev_tune.cli matlab --model YourModel.slx --auto --json
```

Or register the MCP server so the agent can call it as a tool:

```jsonc
{ "mcpServers": { "jev-tune": { "command": "jev-tune-mcp" } } }
```

Tools exposed: `tune_status`, `tune_probe_matlab`, `tune_doctor`, `tune_discover`,
`tune_simulink`, `tune_apply_gains`, `tune_demo`. `tune_doctor` explains a refusal;
`tune_discover` tells the agent which blocks are the controller and which signal
is measured;
`tune_simulink` returns the final gains, the cost at every experiment and the
rollback count. One tool call instead of twenty.

![agent in the loop vs agent as supervisor](assets/agent_vs_head.png)

*Per-iteration numbers are measured (0.111 s simulation, 0.19 ms decision);
the LLM latency is an assumption and labelled as such. Where the two speedups
in the table come from (122 s → 8.8 s, 60 s → 2.7 s), and how it scales to
hundreds of plants:
[`docs/SCALE.md`](docs/SCALE.md).*

### On your own Simulink model

```matlab
addpath('matlab');
R = jev_tune_model('path/to/YourModel.slx', 'work_dir', 20, 10, 2.5);
```

With `--auto` the block names do not matter: discovery follows the signal
graph to find the controller, the measured signal and the reference, and taps a
logging Scope on a copy if the model has none. Without `--auto` it expects
root-level `Gain_Kp`/`Gain_Ki`/`Gain_Kd` and `Scope-*` blocks. Fast Restart is
enabled for you; the decision runs in-process in MATLAB, with no Python
dependency at runtime.

### No MATLAB? Tune a transfer function instead

```bash
jev-tune loop --num 1 --den "1 0.6 1" --delay 0.02
```

Same head, same decision contract, a different plant adapter: the experiment is
an ODE integration instead of a Simulink run. It is also what CI exercises on
every push, so the decision path is never only tested through MATLAB.

---

## How a step works

```
plant / Simulink  ──►  response (t, y, u)
                          │
                          ▼
              20 features + 2×64 traces           ← overshoot, rise, settling,
                          │                         IAE/ITAE, saturation, and
                          ▼                         the previous action + its result
        ┌─────────────────────────────────┐
        │  decision head (~200 KB, ONNX)  │
        │  choice ×3   score   noul       │
        └────────────────┬────────────────┘
                         ▼
   expected-value decode + variance trust region      ← uncertain ⇒ small step
                         ▼
   deterministic safety gate (bounds, rollback)       ← `noul` is advice only
                         ▼
                 new Kp, Ki, Kd
```

More detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Where the speed actually pays off — and where it does not

The decision inside the loop is what the agent no longer has to do. But the
measurement is blunt about the conditions:

| how you run it | per 20-experiment job |
| :--- | ---: |
| agent in the loop (LLM 3 s/turn) | 60 s |
| **one CLI process per job** | **122 s** ← 50 s startup + 24 s setup + 39 s Kp sweep + 8 s loop (without `--auto`) |
| warm worker (model and sweep cached) | **8.8 s** |
| long-lived MATLAB session | **2.7 s** |

So the advantage is **not** "the model is fast"; it is "keep MATLAB warm and
stop recompiling". The MCP server and `jev-tune batch` do exactly that; the
first job in a session still pays ~77 s.

| jobs | agent in the loop | one process each | warm worker |
| ---: | ---: | ---: | ---: |
| 100 | 1.7 h | 3.4 h | **15 min** |
| 1 000 | 17 h | 34 h | **2.5 h** |

Measured on this machine; the LLM latency is the only assumption. The
breakdown, the blocking/concurrency trade-off and the version matrix:
[`docs/SCALE.md`](docs/SCALE.md).

## Benchmarks

**Validation family (120 two-mass plants, 20 experiments for every method).**
This family was used for two design decisions — rejecting the lookahead value
net, and comparing vocabulary v1 with v3 — so it is a validation set, not a
clean test.

| method | final cost (median) | p90 | × reference | success | sims to target | experiments |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Jev head** | **0.440** | **1.038** | **1.31** | **41 %** | **5.0** | 20 |
| Bayesian optimisation | 0.567 | 1.510 | 1.56 | 35 % | 8.5 | 20 |
| identify → `pidtune` | 0.742 | 1.705 | 1.91 | 29 % | 2.0 | 2 |
| shrunken Z-N (factors chosen on the training zoo) | 1.290 | 1.905 | 4.48 | 30 % | 1.0 | 1 |
| Z-N from a measured Ku/Tu (7-run sweep) | 1.860 | 2.791 | 2.99 | 16 % | 8.0 | 8 |
| hill climb over the same vocabulary | 1.463 | 2.212 | 2.35 | 15 % | 5.0 | 20 |
| CMA-ES | 1.705 | 2.519 | 3.58 | 13 % | 4.0 | 20 |
| simplex | 2.037 | 2.879 | 4.43 | 7 % | 4.0 | 20 |
| Ziegler-Nichols (analytic Ku/Tu) | 2.322 | 3.082 | 5.74 | 6 % | 1.0 | 1 |

**Frozen test family (120 thermal plants with large dead time).** Generated from
a fixed grid with **no RNG**, defined after the head was trained, and evaluated
**once**; no design decision was made on it.

| method | final cost (median) | p90 | × reference | success | sims to target | experiments |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| hill climb over the same vocabulary | **1.711** | **2.447** | **1.14** | **27 %** | 9.5 | 20 |
| **Jev head** | 1.737 | 2.871 | 1.30 | 16 % | 13.0 | 20 |
| Bayesian optimisation | 1.877 | 2.662 | 1.32 | 5 % | 13.0 | 20 |
| CMA-ES | 1.976 | 2.879 | 1.36 | 4 % | 16.0 | 20 |
| identify → `pidtune` | 2.330 | 3.064 | 1.49 | 1 % | 2.0 | 2 |
| Ziegler-Nichols | 2.682 | 3.374 | 1.76 | 0 % | inf | 1 |

**Reading the two tables together.** On the family it was validated on, the head
is the best method that does not know the model. On a frozen family it had never
seen, it is **second**: a plain greedy hill climb over the same seven gain
multipliers reaches a lower median and a much lighter tail. So the honest claim is
"a useful default that beats the classical one-shot tuners and BO/CMA-ES at this
budget", not "the best tuner on unseen plants". The 7-run Ku/Tu sweep failed to
recover Ku on 0/120 thermal plants (the sweep window is shorter than the dead
time), so the two `swept` rows fall back and should be read with that in mind.

**Real Simulink model (lab DC motor)**

| gain set | Kp | Ki | Kd | cost |
| :--- | ---: | ---: | ---: | ---: |
| Z-N start | 240 | 1160 | 12.4 | 1.238 |
| **Jev head (best at experiment 5)** | 90.7 | 160.9 | 15.5 | **0.598** |
| human hand-tuned | 280 | 300 | 30.0 | 0.393 |

Full numbers, caveats and reproduction: [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md),
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md).

---

## What is not tested

Two comparisons this project does not make. They are listed here so nobody has
to infer the boundaries from the benchmark:

| not tested | why it matters | what would close it |
| :--- | :--- | :--- |
| **A language model that is not on the network** | The only language baseline is a hosted API — 5.34 s per turn, 13 of 40 answers unparseable — which mixes the language layer with the round trip and the parsing | a local 1.5B–4B model in the same loop |
| **An external user** | Every model in the benchmarks is ours. "You can point it at your project" is a design goal with a test suite behind it, not something observed | one colleague's model |

The typed-interface question used to be on this list. It is now measured:
[`docs/ABLATION.md`](docs/ABLATION.md) compares the shipped head with a
same-size regression head and with every intermediate decode, all at 20
experiments. The answer is in that file, including where the typed path does
*not* help.

## Related work

The lineage this project sits in, with the caveat that it cites them as context,
not as validation of anything measured here:

* **Jev / TypeSafe AI** — the `choice` / `score` / `noul` interface and the idea
  of a calibrated, typed answer instead of generated text
  ([architecture](https://www.jevtypesafeai.com/jev/architecture)). This
  repository borrows the interface, not the model.
* **Laya / Convai Innovations** — a 421 M open typed-decision assessor, used here
  only as the published calibration reference (ECE 0.466 as shipped) and as the
  text baseline that was planned but never wired in.
* **Early neural PID tuning** — Ruano (1992) and the neural/iterative-relay line;
  Leva & Piroddi (ACC 2004). These establish that a learned mapping from response
  to gains is an old idea; what is new here is the typed-decision interface and
  the calibration/abstention story, not the idea of learning to tune.
* **Reinforcement-learning tuning** — including the stability-preserving RL
  tuning line and the industrial RL-tuning patents (US 10,915,073,
  US 11,307,562). Those optimise a policy end to end; this predicts one bounded
  step from a small labelled dataset.
* **Runtime assurance** — the Simplex architecture (Seto, Krogh, Sha & Chutinan,
  ACC 1998) and shielding (Alshiekh et al., AAAI 2018). The deterministic gate in
  `evaluate.py` is a primitive version of the same idea.
* **Calibration and abstention** — temperature scaling (Guo et al., 2017),
  selective prediction (Geifman & El-Yaniv, NeurIPS 2017), conformal risk control
  (Angelopoulos et al., arXiv:2208.02814). `docs/ABSTENTION.md` measures the
  coverage/cost trade-off; it does not implement a conformal guarantee.

## Repository layout

```
src/jev_tune/
  primitives.py  Choice / Score / Noul           (domain-agnostic shell)
  decision.py    backend protocol, question registry, temperature  (shell)
  decode.py      expectation, variance shrink, explicit abstention (shell)
  evaluate.py    budget accounting, gate, per-decision trace      (shell)
  plants.py      plant zoo + vectorised closed-loop simulation    (PID testbed)
  metrics.py     response -> scalar cost                          (PID testbed)
  state.py       20 features + 2x64 traces                        (PID testbed)
  expert.py      coordinate line search over the vocabulary       (PID testbed)
  model.py       the decision head and the lookahead value net
  train.py       dataset -> head
  baselines.py   Z-N, swept Z-N, shrunken Z-N, relay, hill climb, simplex, CMA-ES, BO
  identified.py  identify -> pidtune (the practitioner baseline)
  discover.py    find the gains, signal and reference of an unknown model
  plot.py        the before/after figure
  scenarios.py   10 out-of-zoo scenarios, for generalisation
  simulink.py, matlab_runner.py, matlab_worker.py   MATLAB bridge and worker
  mcp_server.py  the seven MCP tools
  cli.py         status / demo / doctor / discover / matlab / loop / batch / check
c/               C99 inference reference + language-neutral test vectors
matlab/          Fast Restart bridge, hand-written forward pass, test_discover.m
scripts/         00 merge chunks, 00b relabel, 01 dataset, 02 train, 03 evaluate,
                 04 onnx + latency, 05 report, 06 matlab weights, 07 demo assets,
                 08 generalise, 09 arch figure, 10 specialize, 11 robustness,
                 12 race, 13 tracking demo, 14 agent baseline, 15 gifs,
                 16 check claims, 17 ablation, 18 export C, 20 abstention,
                 21 hardware, 22 calibrate-only
docs/            architecture, benchmark accounting, step results, claims,
                 JEV mapping, transfer guide, ablation, abstention, compute
assets/          the GIFs and figures used above
```

## Is it for my problem?

| your task | fit |
| :--- | :--- |
| SISO PID loop, step response, model available in Simulink or as a transfer function | **out of the box** |
| masked `PID Controller` block instead of three gain blocks | out of the box (one flag) |
| dead band, inverse response, or a plant unlike the training zoo | one specialist run, ~2 min |
| tracking / disturbance-rejection objective | metrics + retrain (the policy is objective-specific) |
| cascade, MIMO, non-PID controllers, hardware in the loop | outside the current design |

On 200 plants measured zero-shot, **none ended worse than the Z-N starting
point** — the returned gains are always the best set actually measured, and a
deterministic gate rolls back if a step explodes. Full scope, the robustness
table and per-task effort estimates: [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md).

## Documentation languages

Everything a human reads is available in **English and 简体中文** in the same
file: the English text comes first, the Chinese translation follows under a
language switcher at the top. That applies to this README
([中文](README.zh-CN.md)), `NOTICE`, `CONTRIBUTING`, `SECURITY`,
`CODE_OF_CONDUCT` and every file under `docs/`.

| document | what it answers |
| :--- | :--- |
| [`docs/PHASE0_RESEARCH_REPORT.md`](docs/PHASE0_RESEARCH_REPORT.md) | what the ecosystem actually offers, and the CPU-latency reality check |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | the `choice`/`score`/`noul` contract and one tuning iteration |
| [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md) | latency, calibration, held-out benchmark |
| [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) | the real Simulink model, and the regression that was worth recording |
| [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md) | ten out-of-zoo scenarios, and exactly where it fails |
| [`docs/SCALE.md`](docs/SCALE.md) | throughput economics, concurrency, MATLAB versions |
| [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) | the per-project fine-tune path |
| [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) | what fits, what does not, and how much work each gap is |

## Contributing

Issues and PRs are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md); the
ground rules are short: **numbers, not adjectives**, never regress the benchmark
silently, and keep the `choice` / `score` / `noul` contract.

The gaps where help is most useful right now:

| Area | What it needs |
| :--- | :--- |
| Objective presets | tracking / disturbance-rejection metrics beside the step cost |
| Concurrent workers | N MATLAB workers for large batches |
| Dead-band feature | a descriptor that tells "chattering" from "too much gain" |
| More plant families | anything with published dynamics the zoo lacks |
| Translations | we have English and 简体中文 |

Good first issues are labelled on GitHub.

## Citation

```bibtex
@software{li2026jevtune,
  author = {Li, Jiawei},
  title  = {jev-tune: System-1 typed decisions for PID autotuning},
  year   = {2026},
  url    = {https://github.com/lijiawei255/jev-tune},
  license = {MIT}
}
```

There is also a [`CITATION.cff`](CITATION.cff) if your tool reads it.

## Scope and references

* **Several test benches, not one.** The method and the shipped head were
  developed on a synthetic plant zoo (2 000 plants across six families) and
  checked on ten out-of-distribution control scenarios plus a small generated
  model (`matlab/make_demo_model.m`). The **lab motor model** is
  simply one more bench: a realistic Simulink plant that happened to be at hand.
  It is *not* used to train the shipped head, and the repository does not contain
  it — the demo figures show our own plotted output only. See
  [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md) for the other benches.
* **Jev** (TypeSafe AI) and **Laya** (Convai Innovations) inspired the interface
  this project implements. There is no affiliation, endorsement or sponsorship.
* **MATLAB** / **Simulink** are trademarks of The MathWorks, Inc.
* Which third-party code is used, what is deliberately absent, and under which
  licences: [`NOTICE.md`](NOTICE.md).

## Licence

MIT © JIAWEI LI — see [`LICENSE`](LICENSE).

---

阅读其他语言：[简体中文](README.zh-CN.md)
