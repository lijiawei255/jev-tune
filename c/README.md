# C99 reference implementation (inference only)

This directory is for people who want to run the decision step somewhere without
Python, and for anyone who wants a second, independent implementation to check a
port against.

**Scope:** inference only. No training, no plant simulation, no file I/O, no
dynamic memory allocation, no global mutable state. The Python package
(`src/jev_tune`) and the MATLAB bridge remain the authorities for experiments and
training.

| file | what it is |
| :--- | :--- |
| `jev_head.h` | the API: state, logits, typed answers, decode, gate, feature assembly |
| `jev_head.c` | conv1d ×2 → avg-pool → MLP → trunk → 3×choice + score + noul, softmax, decode |
| `jev_head_weights.h` | generated weights, float32 written as exact C99 hex literals |
| `test_vectors.json` | **language-neutral** test vectors: inputs, expected logits, probabilities, steps, feature vectors and resampling cases |
| `test_vectors.h`, `test_features.h` | the same vectors as C arrays, so the harness needs no JSON parser |
| `test_forward.c` | parity harness for the network + decode |
| `test_features.c` | parity harness for `jev_build_state` and `jev_resample` |

## Build and verify

```bash
python scripts/18_export_c.py --verify     # regenerates the weights + vectors,
                                           # compiles with gcc and runs both harnesses
```

or by hand:

```bash
gcc -std=c99 -O2 -Wall -Wextra -o test_forward  test_forward.c  jev_head.c -lm
gcc -std=c99 -O2 -Wall -Wextra -o test_features test_features.c jev_head.c -lm
./test_forward && ./test_features
```

Verified on 2026-10-23 with **gcc 4.9.2 (TDM64 / MinGW-w64), Windows 11 x64**.
That is the only compiler and platform this code has been run on. It uses nothing
beyond C99 and `libm` (`expf`, `log10f`, `powf`, `floorf`, `fabsf`, `isnan`,
`isinf`), so other C99 compilers should work, but "should" is not "tested".

Measured parity against PyTorch (24 states from the training rollouts):

| quantity | max abs difference | tolerance |
| :--- | ---: | ---: |
| choice/score/noul logits | 9.5e-06 | 5e-04 |
| probabilities after temperature | 9.5e-07 | 1e-05 |
| decoded gain step | 1.2e-07 | 1e-05 |
| 20 features (`jev_build_state`) | 6.0e-08 | 1e-05 |
| 2×64 curves, 64-point resampling | 0 | exact |

## Using it

```c
#include "jev_head.h"

jev_state s;
float metrics[10] = { /* overshoot, rise, settling, ess, iae, itae,
                         oscillations, saturation fraction, overdrive, mean lag */ };
float y[64], u[64];              /* already resampled, or use jev_resample() */
float gains[3] = {Kp, Ki, Kd}, gzn[3] = { /* Z-N or the loop's own start */ };
float prev_action[3] = {0, 0, 0};

jev_build_state(metrics, y, u, gains, gzn, ku, tu, prev_action,
                prev_cost, cost, iteration, horizon, ref, &s);

jev_logits lg;
jev_probs  p;
jev_action act;
const float temperature[3] = {0.9955f, 0.9191f, 0.9577f};  /* models/calibration.json */

jev_forward(&s, &lg);
jev_answer(&lg, temperature, &p);
jev_decode(&p, &act);            /* expectation + variance shrink + clip to ±0.32 */

/* the shipped a-priori hold: p_max < 0.35 -> delta = 0 on that axis */
jev_policy pol = {0.35f, 0.25f, 0.0f};
int escalations = 0;
jev_abstain(&act, &p, &pol, &escalations);

if (jev_gate_rollback(cost, best_cost, rollbacks, 4)) {
    /* gains <- 0.6 * best_gains; see jev_tune_model.m */
} else {
    jev_apply_step(gains, act.step);
}
```

`jev_decode_argmax()` is the discrete control (A1 in `docs/ABLATION.md`), and
`jev_should_stop()` reproduces the early-stop rule that is **off by default**
because it measured worse. Keep them for reproducing the ablation, not for
production.

### int8 is not a drop-in

Weight-only int8 (symmetric, activations float32), 256 states:

| quantisation | same argmax | step within 1e-3 | max step difference |
| :--- | ---: | ---: | ---: |
| per-tensor | 94.1 % | 36 % | 0.104 |
| per-output-channel | 97.3 % | 55 % | 0.104 |

The hold pattern also changes on some states. So int8 is a reasonable size
reduction for a *screening* model, but it is not bit-compatible with the float32
decision; validate it against `test_vectors.json` before shipping it.

## Porting to another language

1. Read `test_vectors.json`. It contains, for every case, the 20 features, the
   2×64 curves, the temperatures, and the expected logits / probabilities / step.
2. Implement `forward`, `softmax`, and the decode. The vocabulary is
   `{0.50, 0.70, 0.87, 1.00, 1.15, 1.43, 2.00}`, the step is
   `E[log10 multiplier] / (1 + Var/var_ref)`, clipped to ±0.32, and `var_ref` is
   the **population** variance of the seven log10 steps (divide by N, not N−1;
   MATLAB's `var()` default is N−1 and that alone made the two runtimes differ by
   6 %).
3. Compare against the JSON with the tolerances in it. If you match, the port is
   correct to within float32 noise.
4. Tell us which vector version you matched (the `generated_by` and model hash
   are in the JSON) and whether you ran it on hardware.

## What this code does **not** establish

* **No cycle counts and no Flash/RAM figures.** Nothing here has been built with
  a cross toolchain or run on a board, so this repository does not claim a
  Cortex-M target, an interrupt budget, or a memory footprint. Compile it with
  your toolchain and measure.
* **No support claim for any MCU.** "It is C99 with no allocation" is a property
  of the source, not a validation of a target.
* **Feature extraction is included, plant simulation is not.** On a real board
  the expensive parts are usually the trace capture and the decision of what to
  try next, not the 40 k-parameter forward pass.
* **A learned policy is not a safety device.** Current/torque limits, gain hard
  limits and the watchdog belong outside this code. `jev_gate_rollback()` is a
  bookkeeping rule ("we are clearly worse than the best we measured"), not a
  guarantee.

## Community ports

Nothing here yet. If you port this to another language or platform, open a PR
that adds one row: language / maintainer / test-vector version / measured on
hardware? The upstream project only maintains `test_vectors.json` and this C
reference; it does not maintain other ports.

| port | maintainer | vector version | on hardware |
| :--- | :--- | :--- | :--- |
| C99 (this directory) | upstream | `generated_by: scripts/18_export_c.py` | no |

## Licence

MIT, same as the repository.
