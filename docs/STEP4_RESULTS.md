# Step 4 — real Simulink model, no Python at runtime

> Plant: the motor-valve benchmark DC-motor position loop (`motor_valve_model.slx`,
> Simscape Multibody butterfly valve, variable-step solver).
> Machine: Windows, MATLAB R2024b, CPU only.

## Why the bridge is built this way

Measured earlier on the same model (`research/bench/`):

| mode | per run |
| :--- | ---: |
| normal (recompile every run) | 869 ms |
| **Fast Restart** | **111 ms** (StopTime = 15 s), 40 ms at StopTime = 1 s |

So a tuning loop that recompiles is 8–19× slower than the decision itself. The
bridge therefore:

1. copies the model to a scratch directory and enables **Fast Restart**
   (compile once, then only tunable gains change),
2. runs the decision head **inside MATLAB** — `matlab/jev_head_forward.m` is a
   hand-written forward pass over the exported weights, so there is no Python,
   no ONNX Runtime and **no IPC** on the critical path,
3. keeps a deterministic safety gate: the best gain set seen so far is always
   returned, and a blow-up triggers `best × 0.6` instead of trusting `noul`.

Parity of the MATLAB forward pass against PyTorch: **max |Δ| = 2.3e-05** (same
as the ONNX export).

## Result on the real model

Reference step 30° = 0.5236 rad. Ultimate gain found by the Kp sweep: Ku ≈ 400,
Tu ≈ 0.414 s → Ziegler-Nichols start `[Kp, Ki, Kd] = [240, 1160, 12.4]`.

| gain set | Kp | Ki | Kd | cost J |
| :--- | ---: | ---: | ---: | ---: |
| lab Z-N (their Ku = 278) | 167 | 673 | 10.4 | 1.290 |
| our Z-N start | 240 | 1160 | 12.4 | 1.238 |
| **Jev head, after 8 experiments** | **223** | **293** | **15.0** | **0.639** |
| human hand-tuned (lab solution) | 280 | 300 | 30.0 | 0.393 |

**−48 % cost in 8 closed-loop experiments.** At 111 ms per Fast Restart run that
is **≈ 0.9 s of simulation** — and the head landed on `Ki = 293` against the
human's `Ki = 300`, i.e. it found the right structure, but under-shot `Kp`/`Kd`
and stopped one step short of the human's tuning.

Convergence (cost at each experiment):

```
1.238 → 1.085 → 0.886 → 0.700 → 0.670 → 0.657 → 0.645 → 0.639  (early stop)
```

The GIF in `assets/tuning.gif` is this run: every frame is one experiment, with
the gains the head chose and the response it produced.

## Honest reading

* The head beats the Z-N start decisively and recovers the integral gain almost
  exactly, but it does **not** reach the human's hand-tuned set. The remaining
  gap is `Kp` (+25 %) and `Kd` (×2), which the head stops short of because its
  action vocabulary is coarse and its training zoo has no position-loop plant.
* `noul` fired no rollback here (the trajectory stayed healthy); the safety gate
  exists for the cases where it does not.
* A model-based `pidtune` would beat all of the above if the transfer function
  were known — it is not, which is the whole point.

## Reproduce

```matlab
addpath('matlab');
R = jev_tune_model('...\motor_valve_model.slx', 'research/sim_tune', 20, 10, 2.5);
```

Then (Python, optional) rebuild the demo assets:

```bash
matlab -batch "addpath('matlab'); save_demo_traces"
python scripts/07_make_demo.py
```

## Next lever

Widen the action vocabulary to a two-stage coarse→fine set (e.g. ×0.5/×0.7/×0.9
then ×0.95/×1.0/×1.05) and add an integrating third-order family to the training
zoo. Both are dataset-and-retrain changes, ≈30 min of CPU each.
