# Changelog

All notable changes to this project. Numbers quoted here are measured, and the
file that produced them is named next to them.

## [Unreleased]

### Added

* **`jev-tune discover`** — finds the error junction, the measured signal, the
  reference value and the three gain blocks by following the signal graph, not by
  matching block names. Subsystem Inports/Outports are transparent, so a
  controller drawn inside a subsystem is found too. Candidates are confirmed by
  one simulation (reference vs steady-state output) and each gain by two more
  (does doubling it move the response). Measured: 4–5 s on the motor-valve benchmark model,
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

### Fixed

* `code` / `error` / `warnings` were written into pass-by-value copies of the
  report struct, so failures came back with no code and no message.
* The gain classifier walked around the feedback loop and found an integrator
  belonging to a different gain, turning a plain P gain into `Ki`.
* `jev_metrics` indexed an empty response (`y(end)`) instead of reporting that
  nothing had simulated.
* The `Motor_Drive` measurement ignored the output port, tuning against speed
  instead of position on the motor-valve benchmark model.

## [0.2.0] - 2026-10-22

First public release: the typed-decision tuner (0.19 ms per decision, 200 KB
model), the Simulink bridge with Fast Restart and a deterministic safety gate, the
six-method benchmark, the robustness study (200/200 plants not worse than the
start) and the scale economics. See the release notes.
