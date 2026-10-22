# Changelog

All notable changes to this project. Numbers quoted here are measured, and the
file that produced them is named next to them.

## [Unreleased]

### Fixed

* The tuner started from Ziegler-Nichols and never looked at the controller the
  model already had, so "never worse than the start" meant "never worse than ZN".
  On a model whose own gains are better than ZN it could hand back something worse
  than the user was already running. The existing gains are now measured once and
  become the floor the safety gate defends; `own_J` is reported in the JSON.
  Self-check: a fixture tuned to 1.607, with those gains written back, comes back
  unchanged at 1.607.
* Gains were written with `num2str`'s default five significant digits, both to
  the tuned copy and to the model on every iteration, so 55.4793 was applied as
  55.479. Now written at full precision.

## [0.3.0] - 2026-10-22

### Added

* **`jev-tune discover`** — finds the error junction, the measured signal, the
  reference value and the three gain blocks by following the signal graph, not by
  matching block names. Subsystem Inports/Outports are transparent, so a
  controller drawn inside a subsystem is found too. Candidates are confirmed by
  one simulation (reference vs steady-state output) and each gain by two more
  (does doubling it move the response). Measured: 4–5 s on the lab model,
  0.6 s on the generated fixtures.
* **`jev-tune doctor`** — nine checks that say *why* a model cannot be tuned:
  loads, referenced models, protected models, Stateflow, compiles (this is the
  one that names a missing workspace variable), solver, logging, and whether a
  loop can be found at all.
* **`jev-tune matlab --auto`** — discovery then tuning in one MATLAB session.
* **`--all-loops`** — tunes each *independent* loop of a model in turn, carrying
  the gains forward into one `_tuned.slx`. Measured on a two-loop model: 2/2
  loops, both gain sets present in the final copy.
* **`--write-back`, `--plot`** — save `<name>_tuned.slx` (never the original) and
  draw the before/after response.
* **`jev-tune loop`** — tunes a transfer function from the command line with no
  MATLAB, the second plant adapter and the path CI exercises on every push.
* **MCP**: `tune_discover`, `tune_apply_gains`, `tune_doctor`.
* **`matlab/jev_dump_graph.m`** — the top-level signal graph as JSON, used by the
  README animation and the fastest way to see why a model was not understood.
* `docs/EXAMPLES.md` (three worked runs), `assets/discover.gif`, a discovery
  issue template.

### Changed

* A cascade is **refused** (`cascade_suspect`) instead of silently tuned as if it
  were one loop: two verified loops nested in each other, or ≥2 integrators and
  >3 scalar gains in one path.
* A referenced model is refused with the file names
  (`referenced_model_unsupported`) instead of the vaguer `no_loop`.
* A masked PID block in the `Ideal`/`Standard` form is converted to the parallel
  form on the working copy before tuning. The two encodings now produce the same
  result (self-check: parallel J=1.438, ideal J=1.438, identical gains).
* A gain that barely moves the response is reported, never removed.
* A simulation that fails mid-tuning is scored as an infinitely bad candidate and
  handed to the safety gate instead of aborting the run.
* The MATLAB badge says `R2024b verified`: that is the only release the
  self-check has been run on.

### Changed

* **Every published number is now checked.** `docs/claims.json` lists each figure
  with the artifact it comes from, `scripts/16_check_claims.py` re-reads them, and
  CI runs it — a stale sentence fails the build. Three figures had drifted:
  * MATLAB/PyTorch parity was documented as 6.1e-05; measured again it is
    **7.6e-06** (the weights were re-exported since).
  * valve dead-band specialisation was documented as 2.242 → 1.152 (−49 %); the
    same command against the retrained head gives **2.242 → 1.884 (−16 %)**.
  * the README's ECE was "0.02"; the proportional axis is **0.031**, the other two
    are 0.02, so it now says so.
  * the README's generalisation row now names the benchmark (120 held-out plants)
    it belongs to, instead of mixing it with the 40-plant race.

### Fixed

* The Ku sweep reported the **top of its grid** as the ultimate gain: the grid was
  fixed at 0.5-400, it took the last oscillating point instead of the first, and
  it counted mean crossings so a damped response qualified. It now auto-ranges,
  takes the first gain whose peaks stop decaying, and says when the value is a
  bound. Consequence documented in `docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong`:
  on the motor-valve benchmark model the old start was an artifact, and from the corrected start
  the head makes no further improvement.
* A model whose step block is not called `Step` now still gets its reference: the
  search is by block type. If that fails, one probe run supplies the steady state
  instead of silently assuming a reference of 1.
* A Scope that logs several signals is refused (`wide_signal`) instead of handing
  the tuner column 1 — which, on a two-input scope, is the reference.
* Scope names are passed through `matlab.lang.makeValidName`, so a block called
  `Scope Position` logs instead of silently producing nothing.
* Missing gain blocks are reported as `no_gains` with the names it looked for,
  instead of a Simulink "Invalid object name".
* The instrumentation never deletes a block that is not its own.
* `status` and the pidtune baseline use the same MATLAB lookup as everything else
  instead of a hard-coded `C:\Program Files\MATLAB\R2024b`.
* Repository hygiene: the local username path and benchmark/reference environment names are
  gone from the tree (see the note in NOTICE.md).

* `code` / `error` / `warnings` were written into pass-by-value copies of the
  report struct, so failures came back with no code and no message.
* The gain classifier walked around the feedback loop and found an integrator
  belonging to a different gain, turning a plain P gain into `Ki`.
* `jev_metrics` indexed an empty response (`y(end)`) instead of reporting that
  nothing had simulated.
* The `Motor_Drive` measurement ignored the output port, tuning against speed
  instead of position on lab model.

## [0.2.0] - 2026-10-22

First public release: the typed-decision tuner (0.19 ms per decision, 200 KB
model), the Simulink bridge with Fast Restart and a deterministic safety gate, the
six-method benchmark, the robustness study (200/200 plants not worse than the
start) and the scale economics. See the release notes.
