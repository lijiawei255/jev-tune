# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2019a%2B-orange)](docs/SCALE.md)
[![decision latency](https://img.shields.io/badge/decision-0.19%20ms-brightgreen)](docs/STEP1_RESULTS.md)
[![model size](https://img.shields.io/badge/model-200%20KB-lightgrey)](docs/STEP1_RESULTS.md)
[![platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#install)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![中文](https://img.shields.io/badge/README-简体中文-red)](README.zh-CN.md)

**PID autotuning where each decision is a typed judgement, not a paragraph.**
A 200 KB model reads the step response and returns one bounded gain step in
**0.19 ms on a laptop CPU** — no autoregressive LLM, no cloud, no GPU.

> **What "Jev" means here.** It uses the *Jev interface* — the three typed
> primitives `choice` / `score` / `noul` with calibrated probabilities — not
> the hosted Jev model or Laya's 421 M text encoder. The runtime policy is a
> 200 KB numeric head trained in this repo; Laya is only useful as an
> optional text backend.

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

**Several loops in one model?** Independent loops (four axes, three zones) are
tuned one after another with `--all-loops`. A **cascade** is refused on purpose:
`cascade_suspect` comes back with the loops it found, because tuning one loop of
a cascade and reporting success would be worse than saying so. See
[`docs/APPLICABILITY.md`](docs/APPLICABILITY.md#several-loops-in-one-model).

## Where to read next

| I want to… | go to |
| :--- | :--- |
| see it run in a minute | [Try it](#try-it) |
| know whether my model qualifies | [`docs/APPLICABILITY.md`](docs/APPLICABILITY.md) |
| understand the decision contract | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| check the numbers myself | [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md), [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md) |
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

*Every frame above is one real closed-loop experiment on the motor-valve benchmark motor-valve benchmark
DC-motor model in Simulink. The tuner is choosing `Kp`, `Ki`, `Kd` itself; the
right panel is the cost it is minimising. The best gains appeared after five
experiments (~0.55 s of simulation); the stall detector stopped the loop at nine.*

---

## The 15-second version

| | |
| :--- | :--- |
| **What it does** | picks the next PID gain step from the response it just measured |
| **How fast** | **0.19 ms** per decision (ONNX, 1 CPU thread) vs **236–276 ms** for a hosted Jev call and seconds for an LLM agent |
| **How few experiments** | **5 experiments** (0.55 s of simulation) cut a real Simulink motor loop's cost by **52 %** |
| **How it generalises** | on a plant family it never saw, **0.47** median cost vs **1.81** for CMA-ES at the same 20-simulation budget |

![before and after](assets/before_after.png)

*Same plant, three gain sets. Grey: the Ziegler-Nichols start. Blue: after five
experiments. Dashed: the lab's hand-tuned solution.*

---

## Why this is different

**vs. LLM-agent tuning.** An agent loop ("read the plot → write a paragraph →
parse the answer") costs seconds per iteration, and the number is buried in
prose. Here the model emits three Jev primitives — `choice` for the step,
`score` for "how good is this response", `noul` for "is this step safe" — so the
decision is a probability vector you can threshold, log and calibrate. Measured
ECE after temperature fitting: **0.02**.

**vs. classical autotune.** Ziegler-Nichols and relay autotuning give you one
shot with no feedback. This keeps iterating, and it learns the *policy* once
across a whole family of plants, so a new plant needs no re-tuning of the tuner.

**vs. Bayesian optimisation.** BO re-fits a surrogate at every step. This is
amortised: one forward pass, and it already beats CMA-ES by 3× on the same
simulation budget — it just does not beat BO's tail, and the benchmark says so.

**When your plant is outside the training zoo** the head is not magic: it fails
on dead bands, inverse response and open-loop unstable plants (documented in
[`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)). The supported answer is a
**specialist** — one command, ~1.5 min of CPU:

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

Measured on a family the head had never seen: median cost **2.242 → 1.152
(−49 %)** over 30 held-out jitters. Details:
[`docs/SPECIALIZE.md`](docs/SPECIALIZE.md).

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

Tools exposed: `tune_status`, `tune_probe_matlab`, `tune_discover`,
`tune_simulink`, `tune_apply_gains`, `tune_demo`. `tune_discover` tells the
agent which blocks are the controller and which signal is measured;
`tune_simulink` returns the final gains, the cost at every experiment and the
rollback count. One tool call instead of twenty.

![agent in the loop vs agent as supervisor](assets/agent_vs_head.png)

*Per-iteration numbers are measured (0.111 s simulation, 0.19 ms decision);
the LLM latency is an assumption and labelled as such. Where the 10–90× comes
from, and how it scales to hundreds of plants:
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
| **one CLI process per job** | **122 s** ← 50 s startup + 28 s setup + 40 s Kp sweep |
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

**Held-out family (120 plants, two-mass resonance, never seen in training)**
Target = 1.05 × a 240-simulation CMA-ES reference.

| method | final cost (median) | p90 | × reference | sims/plant |
| :--- | ---: | ---: | ---: | ---: |
| **Jev head** | **0.468** | 1.037 | **1.29** | 20 |
| Bayesian optimisation | 0.567 | 1.510 | 1.56 | 20 |
| identify → `pidtune` | 0.742 | 1.705 | 1.91 | 2 |
| relay autotune | 0.906 | **0.935** | 2.36 | 2 |
| CMA-ES | 1.813 | 2.618 | 3.75 | 18 |
| Ziegler-Nichols | 2.322 | 3.082 | 5.74 | 1 |

**Real Simulink model (motor-valve benchmark DC motor)**

| gain set | Kp | Ki | Kd | cost |
| :--- | ---: | ---: | ---: | ---: |
| Z-N start | 240 | 1160 | 12.4 | 1.238 |
| **Jev head (best at experiment 5)** | 90.7 | 160.9 | 15.5 | **0.598** |
| human hand-tuned | 280 | 300 | 30.0 | 0.393 |

Full numbers, caveats and reproduction: [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md),
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md).

---

## Repository layout

```
src/jev_tune/
  plants.py      plant zoo + vectorised closed-loop simulation
  metrics.py     response -> scalar cost
  state.py       20 features + 2x64 traces
  primitives.py  Choice / Score / Noul   (the only output surface)
  decode.py      expected-value decode, trust region, interval refinement
  model.py       the decision head and the lookahead value net
  baselines.py   Z-N, relay, simplex, CMA-ES, BO
  identified.py  identify -> pidtune (the practitioner baseline)
  cli.py         status / demo / check
matlab/          Fast Restart bridge + hand-written MATLAB forward pass
scripts/         00 dataset, 01 chunks, 02 train, 03 evaluate, 04 onnx,
                 05 report, 06 matlab weights, 07 demo assets,
                 08 generalisation, 09 figure, 10 specialize
docs/            research report, architecture, step results
assets/          the GIF and figures used above
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
  model (`matlab/make_demo_model.m`). The **motor-valve benchmark model** is
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
