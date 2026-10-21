# Contributing

Thanks for looking. This project is small and opinionated; the fastest way to
get a change merged is to read the four rules below and then send something
focused.

## Ground rules

1. **Numbers, not adjectives.** Any claim about speed or quality must come with
   a measurement and the command that produced it. "Faster" without a number
   will be asked for one.
2. **Never regress the benchmark silently.** If your change moves
   `scripts/03_evaluate.py` or `scripts/08_generalize.py`, include the before/after
   table in the PR. A worse tail is acceptable if it is stated.
3. **Keep the decision contract.** Everything the tuner outputs must be a
   `choice`, a `score`, or a `noul` (`src/jev_tune/primitives.py`). PRs that add
   a "predict the gain directly" path will be declined — that is the thing this
   project tests the alternative to.
4. **Keep `noul` advisory.** Hard limits, rollback and the safety veto live in
   deterministic code (`evaluate.py`, `jev_tune_model.m`). Do not move them into
   the model.

## Getting set up

```bash
bash scripts/agent_setup.sh            # or scripts/agent_setup.ps1 on Windows
python -m jev_tune.cli check           # pytest, must be green
python -m jev_tune.cli demo --plants 12
```

For MATLAB work you need R2019a+ with Simulink; `jev-tune matlab --probe` tells
you what your release supports.

## What is most useful right now

These are the open gaps, roughly in order of value:

| Area | What it needs | Size |
| :--- | :--- | :--- |
| **Objective presets** | tracking / disturbance-rejection metrics next to the step-response cost (see `metrics.py`) | medium |
| **Concurrent workers** | run N MATLAB workers in parallel for large batches (`matlab_worker.py`) | medium |
| **Cross-model cache** | reuse the compiled model when several jobs share one `.slx` | small |
| **Dead-band feature** | a state descriptor that distinguishes "chattering in a dead band" from "too much gain" | small |
| **More plant families** | anything with published dynamics the zoo lacks (e.g. thermal with large dead time, cascaded loops) | small |
| **Docs / translations** | we have English and 简体中文; other languages welcome | small |
| **A second external benchmark** | run the tuner on *your* model and publish the table | medium |

Good first issues are tagged `good first issue` on GitHub.

## Sending a change

1. Fork, branch from `main` (`feat/…`, `fix/…`, `docs/…`).
2. Keep the diff focused; unrelated reformatting makes review slow.
3. Add or update a test if you touch code under `src/`.
4. Run `python -m jev_tune.cli check` and, if you touched the tuner,
   `python -m jev_tune.cli demo --plants 12`.
5. Open a PR using the template. Say what you measured, on what machine.

Commit messages: one line, imperative, under ~72 characters; the body explains
*why* and quotes any number you are claiming.

## Reporting a bug

Use the issue template. The three things that make a report actionable:

* the exact command,
* the JSON output (`--json`),
* your MATLAB release and OS if the MATLAB path is involved.

Please do **not** attach a company's Simulink model. If the plant is sensitive,
describe its dynamics or reproduce with `matlab/make_demo_model.m`.

## Licence of contributions

By opening a PR you agree that your contribution is licensed under the MIT
licence of this repository. No contributor licence agreement is required.
