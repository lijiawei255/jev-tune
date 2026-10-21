# jev-tune

System-1 (Jev-style) decision heads for control-parameter autotuning — on CPU,
without any autoregressive decoding.

A tuner built this way does not write text. It reads the closed-loop response,
asks three typed questions, and returns one bounded gain step in a single
forward pass:

| Jev primitive | Question it answers | Used for |
| :--- | :--- | :--- |
| `choice` × 3 | "Which multiplicative step should Kp / Ki / Kd take?" | the gain update |
| `score` | "How good is the current response, on a 5-level rubric?" | early stopping |
| `noul` | "Will this step keep the loop healthy?" | safety gate |

Everything downstream consumes only those primitives, so the backend is
swappable: a 1M-parameter numeric head (milliseconds on CPU) or a Jev-compatible
text model such as [Laya](https://github.com/NandhaKishorM/laya).

## Why not just Bayesian optimisation

For one known plant, classical optimisers are excellent. A decision head earns
its keep when it is **amortised**: trained once on a family of plants, it
proposes the next gain step in **< 1 ms**, generalises to plants it never saw,
and stops early because `score` is calibrated. The comparison that matters is
therefore *simulations required to reach a target response*, not raw latency.

## Install

```powershell
conda create -n jev-tune python=3.12 -y
conda activate jev-tune
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e .
```

## Run

```powershell
python scripts/01_make_dataset.py --plants 2000 --gens 60 --lam 8
python scripts/02_train.py
python scripts/03_evaluate.py --plants 120
```

`01` samples a plant zoo (first-order + delay, second-order, third-order with an
RHP zero, integrating, PMSM speed loop), lets a batched CMA-ES play expert tuner,
and records every state/action/outcome. `02` fits the decision head plus a
one-step lookahead net. `03` compares the head against Z-N, relay autotune,
simplex, CMA-ES and Bayesian optimisation on **held-out families** (a two-mass
resonant drive that appears nowhere in training).

## Layout

```
src/jev_tune/
  plants.py      plant zoo + vectorised closed-loop simulation
  metrics.py     metrics -> scalar cost
  state.py       20 hand-crafted features + 2x64 resampled traces
  primitives.py  Choice / Score / Noul
  decode.py      expected-value decode, trust region, interval refinement
  baselines.py   Z-N, relay, simplex, CMA-ES, BO
  expert.py      batched CMA-ES expert rollouts
  model.py       decision head + lookahead value net
  train.py       imitation + safety training
  evaluate.py    closed-loop evaluation
```

## Design notes

* **Log-gain action space.** Steps act on `log10 K`, so one vocabulary
  (`x0.80 ... x1.25`) covers gains spanning four decades.
* **Expected-value decoding.** The `choice` distribution is still a `choice`,
  but `E[Δ]` gives a continuous step and `Var[Δ]` sets the trust region: an
  uncertain head automatically takes smaller steps.
* **Safety is deterministic.** `noul` is advice; the hard bounds, the
  divergence check and the rollback live in ordinary code.
* **No setpoint kick.** The derivative acts on the measurement, as in any real
  PID implementation, otherwise every plant would be scored by its own step
  transient.

## License

MIT © JIAWEI LI
