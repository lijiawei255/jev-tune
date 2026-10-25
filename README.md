[English](README.md) · [简体中文](README.zh-CN.md)

# jev-tune

[![tests](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml/badge.svg)](https://github.com/lijiawei255/jev-tune/actions/workflows/ci.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23624699.svg)](https://doi.org/10.5281/zenodo.23624699)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-blue)](pyproject.toml)
[![MATLAB](https://img.shields.io/badge/MATLAB-R2024b%20verified-orange)](docs/SCALE.md)

**A calibrated decision & safety shell, proven on PID autotuning.** A 200 KB CPU
head answers typed questions — `choice` (which gain step), `score` (how good is
this response), `noul` (is the next step healthy). The shell temperature-scales
those answers, builds split-conformal label sets, can hold an axis *before*
actuation when its set is empty, too wide or contradictory, and lets a
deterministic `SafetyGate` roll back after a bad measurement. The same core runs
as a float32, zero-malloc C99 port, inside MATLAB/Simulink, and on a pure-Python
VLA action mask.

```bash
git clone https://github.com/lijiawei255/jev-tune && cd jev-tune && pip install -e .
jev-tune demo --plants 12                    # held-out plants: head vs Z-N vs CMA-ES, ~20 s
python -m jev_tune.domains.light.vla_mask    # the same shell on categorical robot actions
```

### If you are a human

Start with the [three reading paths](docs/START.md). Agents should continue with
[`AGENTS.md`](AGENTS.md).

| layer | module | default |
| :--- | :--- | :--- |
| temperature scaling | `core.primitives` | on |
| split-conformal sets + veto | `core.policy.ConformalPolicy` | `hard_hold` in core and C; `monitor` in the PID loop ([why](docs/TRADEOFFS.md)) |
| a-priori Hold | `core.policy.decide` | per policy, reason recorded per axis |
| rollback | `core.gate.SafetyGate` | on |

> **Jev-inspired, not affiliated with TypeSafe AI.** It implements the Jev
> *interface* (typed `choice` / `score` / `noul` answers), not the Jev model:
> no Jev or Laya weights, no text input, no API ([what is borrowed](docs/JEV_MAPPING.md)).
> Scope limits, negative results, cross-CPU replay failures and disclaimers:
> [BOUNDARIES](docs/BOUNDARIES.md). Frozen research: [ARCHIVE](docs/ARCHIVE.md).

## Let your agent do it

If you use a coding agent (Claude Code, Codex, OpenCode, Cursor — anything that
can run a shell), you do not need the rest of this file. Paste one sentence,
with your own model path:

> **"Use github.com/lijiawei255/jev-tune to tune the PID gains in
> `C:\work\MyMotor.slx`, then show me the before/after curve."**

The agent reads [`AGENTS.md`](AGENTS.md), which tells it to run `jev-tune
discover` first. Discovery follows the signal graph — not block names — to find
the gains, the measured signal and the reference, then confirms the guess with
confirmation simulations whose attempts are included in the discovery ledger:

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

*The animation uses this project's generated model and actual graph/discovery
records. It shows the error junction, gain-path classification and confirming
perturbation simulations. The diagram uses the generated model and its public graph records.
The public inputs and regeneration recipe are listed in
[`OPEN_SOURCE`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/OPEN_SOURCE.md).
Regenerate with [`scripts/15_make_discovery_gif.py`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/scripts/15_make_discovery_gif.py).*

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
| check the numbers myself | [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md), [`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md), [[`docs/CLAIMS.md`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/CLAIMS.md)](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/CLAIMS.md) |
| drive it from an agent or MCP | [`AGENTS.md`](AGENTS.md) |
| handle a plant family it has not seen | [`docs/SPECIALIZE.md`](docs/SPECIALIZE.md) |
| run hundreds of models | [`docs/SCALE.md`](docs/SCALE.md) |
| compare honestly with `pidtune` | [the pidtune section](docs/APPLICABILITY.md#if-you-already-have-an-accurate-model-use-pidtune) |

![seven methods racing on the same plants](assets/race.gif)

*Seven ways to tune the same 40 unseen plants. **Every number is measured**:
median cost after N experiments from one run of [`scripts/12_make_race.py`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/scripts/12_make_race.py), and
the right panel asks the question that matters — how long until the controller
is usable (J ≤ 0.6) — at 0.4 s per experiment. The hatched row is an agent with a
hosted model in the loop: its turn took a measured **5.3 s median** (GLM-5.3-Flash,
40 calls, 13 of them unparseable). Hand tuning has no curve on purpose — it
produces a single gain set after hours, not a series of experiments.*

![tuning a real Simulink DC motor](assets/tuning.gif)

*Historical run under the earlier objective and sweep; see the corrections in
[`STEP4_RESULTS`](docs/STEP4_RESULTS.md). Every frame is one recorded closed-loop experiment on the example
motor model in Simulink. The tuner is choosing `Kp`, `Ki`, `Kd` itself; the
right panel is the cost it is minimising. The best gains appeared after five
experiments (~0.55 s of simulation); the stall detector stopped the loop at nine.*

---



## The 15-second version

| | |
| :--- | :--- |
| **What it does** | picks the next PID gain step from the measured response and records probability/set diagnostics |
| **How fast** | ONNX forward 0.022 ms median; Python default typed/abstention path 0.375 ms median, 1.230 ms p99. Host timing, not WCET; see [COMPUTE](docs/COMPUTE.md). |
| **Historical MATLAB run** | **5 experiments** on the example motor model cut the recorded cost from **1.238 to 0.598** in v0.2. These are historical measurements under the old objective, not a current rerun; neither the earlier sweep repair nor the v0.9 time-grid correction updates those numbers. See [STEP4_RESULTS](docs/STEP4_RESULTS.md). |
| **How it generalises** | Historical validation median 0.482; frozen thermal median 1.833. Their baselines and oracle priors are shown below; the separate v0.9 fixed-start comparison is in [PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md). |

![before and after](assets/before_after.png)

*Historical v0.2 illustration under the old cost definition, not a current rerun.
Same plant, three gain sets. Grey: the Ziegler-Nichols start. Blue: after five
experiments. Dashed: the example hand-tuned solution. That run started from a
Ziegler-Nichols estimate produced by the Ku sweep as it was in v0.2; the sweep
was wrong in three ways and has since been fixed — see the correction in
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong).*

---

## Why this is different

**vs. LLM-agent tuning.** An agent loop ("read the plot → write a paragraph →
parse the answer") costs seconds per iteration, and the number is buried in
prose. Here the model emits three Jev primitives — `choice` for the step,
`score` for "how good is this response", `noul` for "is this step safe" — so the
decision is a probability vector you can log and calibrate. Optional hold
policies are evaluated in [ABSTENTION](docs/ABSTENTION.md); default CP monitoring
does not veto a proposal. Calibration targets and limits are defined in
[CONFORMAL](docs/CONFORMAL.md), not a calibrated probability of safe execution.

**vs. classical autotune.** Ziegler-Nichols and relay autotuning give you one
shot with no feedback. This keeps iterating, and it learns the *policy* once
across a whole family of plants, so a new plant needs no re-tuning of the tuner.

**Comparison with ordinary heads and optimizers.** Current matched-split regression/argmax controls are in [ABLATION](docs/ABLATION.md). One training checkpoint and three evaluation draws do not establish a general causal advantage of the type interface. The gate, calibrated thresholds and matched-coverage random hold are reported separately.

The fixed-start comparison in [PRACTICAL_BUDGET](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md) reports
returned cost and actual calls together. Results depend on the plant and prior;
the head does not outperform the classical baselines across all groups or metrics.

**Why not just `pidtune`?** With a suitable linear model, include `pidtune` as a
baseline and validate the controller on the full model. The historical
identify→`pidtune` experiment is a separate workflow, with failure limitations
documented in [BENCHMARK](docs/BENCHMARK.md). An accurate model does not guarantee
that its default design minimizes this repository's cost.

**When your plant is outside the training zoo** the head is not magic: it fails
on dead bands, inverse response and open-loop unstable plants (documented in
[`docs/GENERALIZATION.md`](docs/GENERALIZATION.md)). First compare it with bounded
classical search under the same actual simulation allowance. A **specialist** is
an optional separate study, not a guaranteed repair:

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --name valve
```

Specialization uses offline simulation and can also degrade held-out performance. Current measured artifacts and the withdrawn historical provenance explanation are documented in [SPECIALIZE](docs/SPECIALIZE.md).

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
bash scripts/agent_setup.sh            # macOS / Linux / WSL; idempotent, no prompts
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1
```

Setup installs the editable package in its selected Python environment. The setup
subprocess does not activate the caller's shell. Before using bare `python`, run
its printed `[setup] activate:` command in that shell (the selected conda environment
or `.venv`). Agents using separate shells should use the exact `[setup] python:`
path, also reported as `executable` in status JSON, for every Python command.
Replace the example paths below with that reported executable:

```bash
"/path/from/setup/python" -m jev_tune.cli status --json   # exit 0 = ready, 2 = exact fix printed
"/path/from/setup/python" -m jev_tune.cli discover --model YourModel.slx --json
"/path/from/setup/python" -m jev_tune.cli matlab --model YourModel.slx --auto --json
```

```powershell
& "C:/path/from/setup/python.exe" -m jev_tune.cli status --json
& "C:/path/from/setup/python.exe" -m jev_tune.cli discover --model YourModel.slx --json
& "C:/path/from/setup/python.exe" -m jev_tune.cli matlab --model YourModel.slx --auto --json
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

*Historical illustration: 0.111 s simulation and 0.19 ms forward-only timing; current full-decision measurements are in docs/COMPUTE.md;
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

## Historical throughput measurements

These measurements describe the earlier implementation with cross-job model
and Ku-sweep caching. That caching is now disabled; these figures and derived
job totals are historical records, not current throughput promises.

| historical setup | recorded 20-iteration job time |
| :--- | ---: |
| agent in the loop (LLM 3 s/turn) | 60 s |
| **one CLI process per job** | **122 s** ← 50 s startup + 24 s setup + 39 s Kp sweep + 8 s loop (without `--auto`) |
| earlier warm worker (model and sweep cached) | **8.8 s** |
| long-lived MATLAB session | **2.7 s** |

The current worker can keep MATLAB running but repeats model setup and the
sweep for each job. Its current throughput needs fresh measurement. `iters`
limits tuning-loop iterations; discovery, probing and verification can add
simulations. Read `n_total_simulations` for actual attempts.

| jobs | agent in the loop | one process each | warm worker |
| ---: | ---: | ---: | ---: |
| 100 | 1.7 h | 3.4 h | **15 min** |
| 1 000 | 17 h | 34 h | **2.5 h** |

The historical per-job measurements were taken on the reference machine; the
LLM latency and scaled job totals are assumptions/extrapolations. Historical
breakdown, current caveats and version matrix:
[`docs/SCALE.md`](docs/SCALE.md).

## Benchmarks

**Validation family: two_mass, 120 plants.** Historical benchmark used for design decisions. Iterative methods have a maximum budget of 20; one-shot methods report actual runs. The table's iterative counts are allocated caps, not measured calls after early stopping. All analytic-start methods share oracle Ku/Tu; sweep failures use a fixed non-oracle fallback.

| method | median J | p90 J | maximum budget / one-shot actual |
| :--- | ---: | ---: | ---: |
| `jev_head` | 0.482 | 1.030 | 20 |
| `bo` | 0.547 | 1.552 | 20 |
| `jev_head_swept` | 0.510 | 1.014 | 20 |
| `shrunk_zn` | 1.290 | 1.905 | 1 |
| `identify+pidtune_PID` | 0.742 | 1.705 | 2 |
| `swept_zn` | 1.860 | 2.791 | 8 |
| `vocab_hill` | 1.463 | 2.212 | 20 |
| `cmaes` | 1.723 | 2.521 | 20 |
| `simplex` | 2.037 | 2.879 | 20 |
| `zn_classic` | 2.322 | 3.082 | 1 |

**Frozen thermal family: 120 fixed-grid plants.** Frozen after training and re-evaluated during earlier correctness repairs, without selecting a new checkpoint on it. This is not a preregistered prospective test.

| method | median J | p90 J | maximum budget / one-shot actual |
| :--- | ---: | ---: | ---: |
| `vocab_hill` | 1.711 | 2.447 | 20 |
| `jev_head_swept` | 1.785 | 3.800 | 20 |
| `jev_head` | 1.833 | 2.816 | 20 |
| `bo` | 1.878 | 2.684 | 20 |
| `cmaes` | 2.000 | 2.879 | 20 |
| `identify+pidtune_PID` | 2.330 | 3.064 | 2 |
| `zn_classic` | 2.682 | 3.374 | 1 |
| `swept_zn` | 3.580 | 5.334 | 8 |
| `shrunk_zn` | 4.854 | 5.158 | 1 |
| `simplex` | 2.302 | 3.146 | 20 |

These frozen rows are separate from the v0.9 [practical budget study](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md), which reports actual calls and does not show uniform head superiority. Historical identify→pidtune rows retain their original implementation's failure limitations. See [BENCHMARK](docs/BENCHMARK.md) for accounting and [raw tables](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1) for sweep recovery/fallback details.

**Historical Simulink model result (example motor model, old objective)**

This table preserves the v0.2 record. It is not a v0.9 rerun and cannot be
compared numerically with the corrected time-grid objective.

| gain set | Kp | Ki | Kd | cost |
| :--- | ---: | ---: | ---: | ---: |
| Z-N start | 240 | 1160 | 12.4 | 1.238 |
| **Jev head (best at experiment 5)** | 90.7 | 160.9 | 15.5 | **0.598** |
| human hand-tuned | 280 | 300 | 30.0 | 0.393 |

Full numbers, caveats and reproduction: [`docs/STEP1_RESULTS.md`](docs/STEP1_RESULTS.md),
[`docs/STEP4_RESULTS.md`](docs/STEP4_RESULTS.md).

---

## What is not tested

The following are two of the project's unmeasured comparisons. They are listed here so nobody has
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
  coverage/cost trade-off; it implements only per-axis marginal teacher-label split CP under exchangeability; this is not a closed-loop safety guarantee.

## Repository layout

```
src/jev_tune/core/           numpy-only shell: primitives, policy, calibration, gate
src/jev_tune/domains/pid/    PID test bed: plants, metrics, state, expert, model, train,
                             decision backends, evaluate, baselines, MATLAB bridge, plot
src/jev_tune/domains/light/  linear_shell.py (ordered numeric), vla_mask.py (categorical)
src/jev_tune/cli.py          status / demo / doctor / discover / matlab / loop / batch / check
src/jev_tune/mcp_server.py   the seven MCP tools
c/                           C99 float32 reference, zero malloc, generated vectors
matlab/                      Fast Restart bridge, hand-written forward pass, tests
scripts/                     01 dataset, 02 train, 03 evaluate, 04 ONNX, 06 MATLAB weights,
                             10 specialize, 11 robustness, 18 export C, 20 abstention,
                             22 calibrate-only, archive.py, docs_relink.py
docs/                        design, results, BOUNDARIES, TRADEOFFS, ARCHIVE
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

## How to cite

Please cite the **concept DOI [10.5281/zenodo.23624699](https://doi.org/10.5281/zenodo.23624699)**;
it always resolves to the latest archived release. To pin one release, cite its
version DOI, listed on the Zenodo record page.

```bibtex
@software{li_jevtune,
  author  = {Li, Jiawei},
  title   = {jev-tune: a Jev-inspired calibrated decision and safety shell for typed PID autotuning},
  doi     = {10.5281/zenodo.23624699},
  url     = {https://github.com/lijiawei255/jev-tune},
  license = {MIT}
}
```

Machine-readable citation metadata (authors, ORCID, DOI) is in
[`CITATION.cff`](CITATION.cff) at the repository root; GitHub's "Cite this
repository" button reads it.

## Acknowledgements and scope

* **Several test benches, not one.** The method and the shipped head were
  developed on a synthetic plant zoo (2 000 plants across six families) and
  checked on ten out-of-distribution control scenarios plus a small generated
  model (`matlab/make_demo_model.m`). The **example motor model** is
  simply one more bench: a realistic Simulink plant that happened to be at hand.
  The published training code uses synthetic simulations; benchmark observations
  influenced later zoo design, so this is a development example. The current
  source tree and new release omit its original files; historical response plots
  are our own rendering. See
  [`docs/GENERALIZATION.md`](docs/GENERALIZATION.md) for the other benches.
* **Jev** (TypeSafe AI) and **Laya** (Convai Innovations) inspired the interface
  this project implements. There is no affiliation, endorsement or sponsorship.
* **MATLAB** / **Simulink** are trademarks of The MathWorks, Inc.
* Which third-party code is used, what is deliberately absent, and under which
  licences: [`NOTICE.md`](NOTICE.md).
* Complete source/model/data distribution and exclusions: [`OPEN_SOURCE`](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/OPEN_SOURCE.md).

## Licence

MIT © JIAWEI LI — see [`LICENSE`](LICENSE).

---

阅读其他语言：[简体中文](README.zh-CN.md)
