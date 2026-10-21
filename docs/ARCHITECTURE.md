# Architecture

## Contract

Every decision in this project is one of three Jev primitives. There is no
"regress the gain" path — that is the whole point of the experiment.

```python
class DecisionBackend(Protocol):
    def decide(self, state: State, questions: list[Question]) -> dict[str, Answer]: ...
```

* `Choice(question, options, probs)` — pick one of K, with a probability per option
* `Score(question, levels, dist)` — ordered rubric judgement
* `Noul(statement, p_true)` — calibrated yes/no, i.e. the safety primitive

Backends:

| backend | input | cost per decision | role |
| :--- | :--- | :--- | :--- |
| `NumericHead` (this repo) | 20 features + 2×64 traces | **< 1 ms** (ONNX, CPU) | runtime |
| `LayaBackend` (optional) | JSON state rendered as text | 40–90 ms (INT8, ≤120 tokens) | zero-shot baseline, teacher, text states |

## One tuning iteration

```
plant / Simulink
   │  step response (t, y, u)
   ▼
FeatureExtractor ──► State(20) + traces(2×64)
   │                    │
   │                    ▼
   │              DecisionHead ──► choice×3, score, noul
   │                    │
   │                    ▼
   │            ValueNet (1-step lookahead)
   │             top-2×2×2 candidate actions → pick lowest predicted cost
   │                    │
   │                    ▼
   │            decode: E[Δ] with Var-driven trust region
   ▼                    │
accept new gains ◄──────┘
   ▲
   └── SafetyGate (deterministic): |Δlog K| ≤ 0.2, gain box, divergence
       rollback, saturation veto. `noul` is advice, never the final word.
```

## State (20 features)

Response descriptors a human tuner would use, all scale-free:
overshoot, rise/90-10, settling, steady-state error, log IAE, log ITAE,
oscillation count, saturation fraction, worst overdrive, peak output,
current gains relative to Z-N, **the previous action** (Δlog Kp/Ki/Kd),
**the cost change it produced**, iteration fraction, `Ku/Kp`, `Tu/h`.

The previous-action pair is what turns an open-loop mapping into a closed-loop
search: without it the head cannot tell "gain too high" from "gain too high and
already reduced".

## Why these decoders

| decoder | when | why |
| :--- | :--- | :--- |
| multiplicative `choice` | always | bounded, interpretable, matches how a tuner thinks |
| expected value + variance gate | always | continuous step while staying inside the `choice` format; variance = trust region |
| NumericJev interval refinement (K=3) | final ±10 % | exact resolution without the "wrong interval is unrecoverable" failure mode early on |
| `score` threshold | every iteration | calibrated early stop — saves iterations, which dominates wall-clock |

## Training data

The expert is a batched CMA-ES, not a person:

1. sample a plant zoo (5 families, delays tied to the dominant time constant),
2. start at Z-N, walk a gain trajectory,
3. at each step record (state, 8 candidate actions and their costs, the best one,
   whether it stayed healthy, the current cost bucket).

The value net is trained on the same rollout: `(state, action) -> cost`, which is
what lets the head filter its own proposals before spending a simulation.

## Fairness rules for the benchmark

* identical cost function, identical simulation budget accounting
* every method starts from the same Z-N point
* target = 1.05 × a strong CMA-ES reference (240 simulations/plant)
* held-out evaluation uses plants the training zoo never contained
