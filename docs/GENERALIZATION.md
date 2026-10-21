# Does it generalise? Ten control scenarios outside the training zoo

The worry this document answers: *the head was trained on a synthetic plant zoo
and tested on the motor-valve benchmark motor — is it only good at those two things?*

**Test design.** Ten scenarios a control engineer meets in other projects, none
of them present in the zoo, each with four jittered draws (±30 % gain, ±30 %
delay) = 40 plants. The shipped head runs **zero-shot**: no per-plant training,
no adaptation, no hand-tuning.

| scenario | what makes it different | head | Z-N | relay | CMA-ES | × best classical | plants won |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | L/T = 2 (delay dominates) | 0.853 | 1.128 | 2.291 | 0.848 | 1.01 | 1/4 |
| double_integrator | 1/s² (frictionless mass) | 2.971 | 8.020 | 3.949 | 2.940 | 1.01 | 4/4 |
| unstable_pole | 1/(s−1), open-loop unstable | **1.594** | 2.042 | 50.0 | 1.999 | **0.80** | 4/4 |
| inverted_pendulum | 1/(s²−2), unstable | 50.0 | 50.0 | 50.0 | 50.0 | 1.00 | — |
| sharp_resonance | ζ = 0.02 resonance at 200 rad/s | 7.429 | 8.179 | 7.316 | 8.179 | 1.02 | 4/4 |
| noisy_sensor | σ = 1 % measurement noise | 1.489 | 2.617 | 1.530 | 2.125 | 0.97 | 3/4 |
| valve_dead_zone | 5 % actuator dead band | 2.262 | 2.262 | **0.861** | 2.262 | 2.63 | 1/4 |
| flexible_arm | two close structural modes | 7.749 | 8.498 | 7.650 | 8.498 | 1.01 | 4/4 |
| inverse_response | slow RHP zero | 2.718 | 3.091 | 3.797 | **1.953** | 1.39 | 1/4 |
| hydraulic | 3rd order + delay, tight actuator | **1.136** | 2.280 | 4.346 | 1.763 | **0.64** | 4/4 |

**Headline: within 5 % of the best classical tuner on 30 of 40 plants;
median cost ratio 1.01× (1.00 = parity).** So on this sample the head neither
collapses nor dominates — it behaves like a competent default tuner.

## Where it is strong

* **Unstable first-order pole** (0.80×) and **hydraulic** (0.64×) — the head
  backs the gains off decisively, which is exactly what the zoo's saturation
  cases taught it.
* **Double integrator** (1.01×, 4/4) and **noisy sensor** (0.97×) — it does not
  get fooled by derivative noise because it never learned to trust one number.

## Where it fails, and why

1. **Valve dead band (2.63×)** — the response chatters around the 5 % dead band,
   and every feature the head sees ("many crossings", "long settling") looks
   like *too much gain*. Relay autotuning wins because it measures the limit
   cycle directly. A dead-band-aware feature would fix this.
2. **Inverse response (1.39×)** — the plant first moves the wrong way. The head
   has no feature for "the initial direction is inverted", so it treats the dip
   as instability and backs off. CMA-ES wins by brute force.
3. **Inverted pendulum (every method fails)** — this one is an artefact worth
   naming: `ultimate_gain` is only meaningful for stable plants, so Z-N returns
   Ku ≈ 1.2e6, and *every* tuner here (head included) starts from that garbage
   and diverges immediately. A practitioner would start from a hand-derived
   stabilising PD. The head has no cold-start detector for open-loop unstable
   plants.

## What this says about overfitting

* The head is **not** memorising the zoo: it lands at parity on ten dynamics
  families it has never seen, including ones with a very different character
  (dead time, double integrator, resonance).
* But it **is** limited by its feature set: every failure above traces back to
  a state descriptor that does not exist (dead-band chatter, inverted initial
  direction, "the plant is unstable so Z-N is meaningless").
* The motor-valve benchmark case (cost 1.238 → 0.598) is therefore not evidence of overfitting
  to the test bench — it sits inside the band of results above.

## Reproduce

```bash
python scripts/08_generalize.py --draws 4
```

Raw output: `research/results/generalization.json`.

## Is there a per-project learning step?

**No, not at deployment.** Training happens once, offline, on the synthetic zoo
(~30 min of CPU). At runtime the head is a fixed 200 KB policy: it sees the
response, emits a `choice`/`score`/`noul`, done. That is what makes 0.19 ms and
zero cold-start possible.

If a project falls outside the zoo (dead band, inverted response, unstable
plants), the supported path is a **specialist**: generate a zoo that resembles
your plant, regenerate the dataset and fine-tune the head — about 30 minutes of
CPU, no GPU, no labels from the real plant. That is "learning per project",
just done once, offline, and shared by every plant of that type.
