# Step 4 — real Simulink model, no Python at runtime

> Plant: the motor-valve benchmark DC-motor position loop (`motor_valve_model.slx`,
> Simscape Multibody butterfly valve, variable-step solver, 30° = 0.5236 rad step).
> Machine: Windows, MATLAB R2024b, CPU only.

## Why the bridge is built this way

Measured earlier on the same model (`research/bench/`):

| mode | per run |
| :--- | ---: |
| normal (recompile every run) | 869 ms |
| **Fast Restart** | **111 ms** (StopTime = 15 s), 40 ms at StopTime = 1 s |

A loop that recompiles is 8–19× slower than the decision itself. The bridge
therefore:

1. copies the model to a scratch directory and enables **Fast Restart**
   (compile once, then only tunable gains change),
2. runs the decision head **inside MATLAB** — `matlab/jev_head_forward.m` is a
   hand-written forward pass over the exported weights, so there is no Python,
   no ONNX Runtime and **no IPC** on the critical path,
3. keeps a deterministic safety gate: the best gain set seen so far is always
   returned, and a blow-up triggers `best × 0.6` instead of trusting `noul`.

Parity of the MATLAB forward pass against PyTorch: **max |Δ| = 6.1e-05**.

## Result

Reference step 0.5236 rad. Ultimate gain from the Kp sweep: Ku ≈ 400, Tu ≈
0.414 s → Ziegler-Nichols start `[Kp, Ki, Kd] = [240, 1160, 12.4]`.

| gain set | Kp | Ki | Kd | cost J | experiments |
| :--- | ---: | ---: | ---: | ---: | ---: |
| lab Z-N (their Ku = 278) | 167 | 673 | 10.4 | 1.290 | — |
| our Z-N start | 240 | 1160 | 12.4 | 1.238 | 0 |
| **Jev head (shipped)** | **90.7** | **160.9** | **15.5** | **0.598** | **5** |
| human hand-tuned (lab solution) | 280 | 300 | 30.0 | 0.393 | hours |

**−52 % cost in five closed-loop experiments** ≈ 0.55 s of simulation at 111 ms
per run.

```
cost: 1.238 → 0.631 → 0.601 → 0.613 → 0.598   (early stop after 5)
gains: [240 1160 12.4] → [185 594 18.7] → [144 303 16.9] → [109 299 17.7] → [90.7 161 15.5]
```

The GIF in `assets/tuning.gif` is this run: every frame is one experiment, with
the gains the head chose and the response it produced.

## What the plant actually wants (one-at-a-time sensitivity)

`Kp = 280, Ki = 300`, sweeping Kd:

| Kd | 5 | 10 | 20 | **30** | 45 | 60 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 1.45 | 0.92 | 0.54 | **0.39** | 0.51 | 0.60 |

and sweeping Kp at `Ki = 300, Kd = 30`:

| Kp | 150 | 200 | 240 | **280** | 320 | 400 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 0.54 | 0.47 | 0.43 | **0.39** | 0.39 | 0.41 |

So this plant wants **2.4× the Z-N derivative gain** and a fairly wide Kp
plateau. The head found a different but valid point: much lower Kp/Ki, Kd 15.5.
It reached 0.598, i.e. **1.5× the hand-tuned cost** — good for five experiments,
not equal to a human who can iterate for hours.

## The regression that is worth recording

An intermediate model (7-option vocabulary **without** actuator-saturation
plants in the zoo) *increased* Kd's error instead of decreasing it:

| model | Kd chosen | cost |
| :--- | ---: | ---: |
| intermediate (v2) | 12.4 → 6.2 | **1.238 (no improvement)** |
| shipped (v3) | 12.4 → 15.5 | 0.598 |

Diagnosis: v2's zoo only had generous actuators, so the expert never had to use
derivative action for damping — every plant could be fixed by backing off the
proportional gain. The lab motor cannot (it saturates), which is why adding
tight-actuator plants (headroom 1.0 / 1.6 / 2.5) fixed the transfer, at the cost
of a heavier tail on the synthetic benchmark.

That trade-off is the honest state of the project: **the model that transfers to
the real plant is not the model that wins the synthetic benchmark.**

## Reproduce

```matlab
addpath('matlab');
R = jev_tune_model('...\motor_valve_model.slx', 'research/sim_tune', 20, 10, 1.0);
% iters=20 (early stop at 5), stopTime=10 s, stepGain=1.0
```

Then rebuild the demo assets:

```bash
matlab -batch "addpath('matlab'); save_demo_traces"
python scripts/07_make_demo.py
```

## Next levers

1. Add a **decay-ratio** feature (successive peak ratio) so the head can tell
   "growing oscillation → back off" from "decaying but overshooting → add
   damping". That is the single feature the failure analysis points at.
2. Mixture of two heads (generous vs tight actuator) selected by the measured
   saturation fraction — recovers v2's tail without losing v3's transfer.
3. Both are dataset-and-retrain changes, ≈30 min of CPU each.
