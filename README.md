# jev-tune

**PID autotuning where each decision is a typed judgement, not a paragraph.**
A 200 KB model reads the step response and returns one bounded gain step in
**0.19 ms on a laptop CPU** — no autoregressive LLM, no cloud, no GPU.

![tuning a real Simulink DC motor](assets/tuning.gif)

*Every frame above is one real closed-loop experiment on the motor-valve benchmark motor-valve benchmark
DC-motor model in Simulink. The tuner is choosing `Kp`, `Ki`, `Kd` itself; the
right panel is the cost it is minimising. Five experiments took ~0.55 s of
simulation.*

---

## The 15-second version

| | |
| :--- | :--- |
| **What it does** | picks the next PID gain step from the response it just measured |
| **How fast** | **0.19 ms** per decision (ONNX, 1 CPU thread) vs **236–276 ms** for a hosted Jev call and seconds for an LLM agent |
| **How few experiments** | **5 experiments** cut the cost of a real Simulink motor loop by **52 %** |
| **How it generalises** | on a plant family it never saw, **0.57** median cost vs **1.91** for CMA-ES at the same 20-simulation budget |

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

---

## Try it

### Human

```bash
conda create -n jev-tune python=3.12 -y && conda activate jev-tune
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
jev-tune demo            # 12 held-out plants, head vs CMA-ES vs Z-N, ~20 s
```

### Agent

Point your assistant at [`AGENTS.md`](AGENTS.md). The short form:

```bash
bash scripts/agent_setup.sh            # idempotent, no prompts
python -m jev_tune.cli status --json   # exit 0 = ready, 2 = exact fix printed
python -m jev_tune.cli demo --json     # machine-readable result
```

Every script is non-interactive, seeded, and writes JSON on request.

### On your own Simulink model

```matlab
addpath('matlab');
R = jev_tune_model('path/to/YourModel.slx', 'work_dir', 20, 10, 2.5);
```

Needs root-level `Gain_Kp`/`Gain_Ki`/`Gain_Kd` blocks and `Scope-*` blocks.
Fast Restart is enabled for you; the decision runs in-process in MATLAB, with no
Python dependency at runtime.

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

## Benchmarks

**Held-out family (120 plants, two-mass resonance, never seen in training)**
Target = 1.05 × a 240-simulation CMA-ES reference.

| method | final cost (median) | p90 | × reference | sims/plant |
| :--- | ---: | ---: | ---: | ---: |
| **Jev head** | **0.569** | 2.911 | **1.52** | 20 |
| Bayesian optimisation | 0.581 | **1.516** | 1.58 | 20 |
| identify → `pidtune` | 0.747 | 1.712 | 1.84 | 2 |
| relay autotune | 0.905 | 0.934 | 2.34 | 2 |
| CMA-ES | 1.905 | 2.770 | 3.92 | 18 |
| Ziegler-Nichols | 2.501 | 3.158 | 6.06 | 1 |

**Real Simulink model (motor-valve benchmark DC motor)**

| gain set | Kp | Ki | Kd | cost |
| :--- | ---: | ---: | ---: | ---: |
| Z-N start | 240 | 1160 | 12.4 | 1.238 |
| **Jev head, 5 experiments** | 90.7 | 160.9 | 15.5 | **0.598** |
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
                 05 report, 06 matlab weights, 07 demo assets
docs/            research report, architecture, step results
assets/          the GIF and figures used above
```

## Licence

MIT © JIAWEI LI
