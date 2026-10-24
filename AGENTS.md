# Agent guide

This file is for an automated assistant pointed at this repository. Read it
top to bottom. It has two modes; pick the one that matches the request:

* **Use mode** — the user wants a model tuned or the shell applied. Follow
  [Use mode](#use-mode-tune-a-users-model).
* **Build mode** — the user wants this repository changed. Follow
  [Build mode](#build-mode-change-this-repository). The one-question rule of use
  mode does not apply; ask whenever a change is ambiguous.

## What this project is

A **Jev-inspired calibrated decision & safety shell**. A small CPU model answers
typed questions — `Choice` (pick one of K), `Score` (ordered rubric), `Noul`
(calibrated yes/no) — and the shell turns those answers into a bounded action
or an explicit hold. PID autotuning is the complete test bed; a pure-Python VLA
action mask shows the same shell on categorical actions. It uses the Jev
*interface*, not the Jev model: no Jev/Laya weights, no text input, no API, and
**no affiliation with TypeSafe AI**. Say so if asked.

```
src/jev_tune/core/           numpy only, domain-agnostic
  primitives.py              Choice / Score / Noul, softmax, temperature fit, split CP
  policy.py                  decide(): shrink, a-priori Hold, CP veto (default hard_hold)
  calibration.py             temperature + CP from two disjoint labelled splits
  gate.py                    SafetyGate: deterministic post-measurement rollback
src/jev_tune/domains/pid/    complete PID test bed: plants, expert, head, evaluator, MATLAB bridge
src/jev_tune/domains/light/  linear_shell.py (ordered numeric), vla_mask.py (categorical)
src/jev_tune/cli.py, mcp_server.py   user surface
c/                           C99 single-precision port, zero malloc, generated vectors
matlab/                      Simulink bridge and hand-written forward pass
scripts/                     01–22 training/evaluation, 18 C export, archive.py
docs/                        design, results, BOUNDARIES, TRADEOFFS, ARCHIVE
```

Layer defaults: temperature on; split CP `hard_hold` in `core` and the C
config, `monitor` in the PID evaluator and CLI (lower final cost there, see
`docs/TRADEOFFS.md`); `SafetyGate` on. Host timings are not a target-board WCET.

## Use mode: tune a user's model

The common request is "use this project to tune my model" from someone who
knows MATLAB but not shells. Do not send them to the README and do not ask them
to rename blocks.

1. **Find MATLAB.** `jev-tune status --json`; if `ok` is false follow `next`,
   or set `MATLAB_EXE`. Report the exact path tried.
2. **Find the model.** Use the path the user gave. Otherwise look for
   `*.slx` / `*.mdl` in the working directory, newest first: exactly one → use
   it; several → ask once with the list. That is the only question allowed
   before tuning.
3. **On any failure run `jev-tune doctor --model <model>` first** and report its
   `next` line, not the raw error.
4. **Discover, do not assume.** `jev-tune discover --model <model> --json --out discover.json`.
   At `confidence: high` ask nothing. At `medium` quote the candidates and let
   the user pick. Quote the discovery ledger's simulation count.
5. **Tune.** `jev-tune matlab --model <model> --config discover.json --plot before_after.png --write-back --json`.
   Independent loops reported by `discover` → `--all-loops`.
6. **Report in the user's language:** start cost, final cost, experiments, the
   three gains, the path of `*_tuned.slx`. Numbers verbatim from the JSON:
   "1.24 → 0.60", never "about 40 % better".
7. **If it fails** read `code`, follow the table, never retry the same command.

Without MATLAB: `jev-tune loop --num "1" --den "0.5 1 0" --delay 0.05 --json`
tunes a transfer function with the same head (ONNX, no torch required).

Never modify the user's model: `--write-back` writes `<name>_tuned.slx` next to
it and the original stays byte-identical.

| `code` | meaning | what you do |
| :--- | :--- | :--- |
| `matlab_missing` | no MATLAB found | show both install hints, ask for `MATLAB_EXE` |
| `model_not_found` | bad path | ask once more |
| `no_loop` | no feedback loop | may be open-loop; point at `docs/APPLICABILITY.md` |
| `cascade_unsupported` | several masked PID blocks | cascade is out of scope; offer inner-then-outer |
| `cascade_suspect` | nested loops / two integrators | **do not tune**; explain inner-first, offer one loop by name |
| `ambiguous_junction` | no summing junction confirmed | ask the user to run the model once in Simulink |
| `ambiguous_controller` | two plausible Kp blocks | list `candidates`, ask which one |
| `loop_not_found` | `--all-loops` name not verified | re-run `discover`, use a name from `loops` |
| `referenced_model_unsupported` | Model blocks | tune that file or flatten the hierarchy |
| `no_signal` | nothing logged | re-run `discover`; then ask which Scope shows the output |
| `sim_failed`, `model_error` | Simulink refused | needs workspace variables; ask the user to run it once |
| `no_ultimate_gain` | `loop` plant has no phase crossover | add the real delay with `--delay`, or use MATLAB |
| `tune_failed` | anything else | quote `error`; do not guess a fix |

**Before claiming success:** `result["ok"]` is true **and**
`result["final_J"] <= min(result["history"][0]["J"], result.get("own_J", inf))`.
The tuner never returns gains worse than the better of its start and the gains
the model already ran. If a baseline beats the head, say so.

Discovery failing on a model that should work is a bug here: ask the user to
open the "Discovery failed on a real model" issue template with the `--json`
output. Never hard-code block names around it.

More than a couple of jobs: `jev-tune batch --jobs jobs.json` or the MCP server
(`{"mcpServers": {"jev-tune": {"command": "jev-tune-mcp"}}}`; tools
`tune_status`, `tune_probe_matlab`, `tune_doctor`, `tune_discover`,
`tune_simulink`, `tune_apply_gains`, `tune_demo`). A model left in Fast Restart
raises a modal dialog on close: use `jev_close_all`, never `close_system`.

## Porting the shell to another domain

Use `src/jev_tune/domains/light/` as the template and keep `core/` unchanged.

1. **Name the questions.** One `Choice` per actuated axis with ordered numeric
   `Option.delta` payloads, or a categorical token set; optional `Score` and
   `Noul`. Never add a path that regresses the action directly.
2. **Write a backend** returning `core.primitives.Answer` from your own model.
3. **Pick the decoder by action type.** Ordered numeric → `core.policy.decide`
   (expectation + variance shrink + `max_step`). Categorical → never average;
   follow `vla_mask.py` (argmax inside the admissible CP set, else hold).
4. **Calibrate on two disjoint labelled splits** with
   `core.calibration.fit_frozen_calibration`; freeze the model first.
5. **Choose the CP mode explicitly.** `hard_hold` vetoes before actuation;
   `monitor` only records. Measure both as in `docs/TRADEOFFS.md`.
6. **Own the hard rules.** Domain masks (forbidden actions), units, actuator
   bounds and `SafetyGate` thresholds live in the domain, not in `core`.
7. **Test like `tests/test_light_domains.py`:** documented output, forbidden
   actions never executed, holds observable, import without torch.
8. **Embedded target:** export with `scripts/18_export_c.py`; the C port is
   float32 only and its CP threshold is `p_min` from
   `core.primitives.conformal_inclusion_threshold`.

CP coverage is per-axis marginal teacher-label coverage on exchangeable states.
It is not closed-loop stability, joint-action safety or a physical guarantee.

## Build mode: change this repository

Setup: `bash scripts/agent_setup.sh` (macOS/Linux/WSL) or
`powershell -ExecutionPolicy Bypass -File scripts\agent_setup.ps1`; both print
`[setup] python:` — use that interpreter for every command.

Required checks before you report a change:

```bash
python -m pytest -q                      # no Release download needed
make -C c check                          # includes the -Wdouble-promotion -Werror build
python scripts/docs_relink.py --check    # every relative doc link resolves
```

Rules:

* `core/` imports numpy only. Domain code imports `core`, never the reverse.
* Generated files are regenerated, never hand-edited: `c/jev_head_weights.h`,
  `c/jev_config.h`, `c/test_*.h`, `c/test_vectors.json` (`scripts/18_export_c.py`),
  `models/*` (training scripts), `assets/*`.
* Keep Python and C policy semantics identical; a change to `core/policy.py` or
  `core/gate.py` needs a regenerated vector set and a passing `make -C c check`.
* Frozen research, negative results and their verifiers live only at tag
  `v0.10.2-archive` (`python scripts/archive.py [--verify]`, `docs/ARCHIVE.md`).
  Do not copy archived scripts back into `main`.
* Report numbers, not adjectives. If a baseline wins, say so.
* Human-facing docs are bilingual: English first, then 简体中文 in the same file;
  `README` has a separate `README.zh-CN.md`.

## Where the numbers come from

| file | content |
| :--- | :--- |
| `docs/STEP1_RESULTS.md` | latency, calibration, held-out benchmark |
| `docs/STEP4_RESULTS.md` | historical Simulink run and its corrections |
| `docs/GENERALIZATION.md` | out-of-zoo scenarios, where it fails |
| `docs/TRADEOFFS.md` | monitor vs hard_hold: harmful steps, experiments, final cost |
| `docs/BOUNDARIES.md` | negative results, cross-CPU replay, disclaimers |
| `docs/APPLICABILITY.md` | what fits, the no-regression evidence, effort per task |

## 简体中文摘要

本文件供自动化助手使用。**使用模式**：按上文步骤发现并调参，调参前最多问一个问题，
数字原样引用JSON，不得修改用户模型。**构建模式**：修改本仓库时可随时提问；提交前必须
通过`pytest`、`make -C c check`与`python scripts/docs_relink.py --check`。`core/`只依赖numpy，
领域代码依赖core而非相反；生成文件只能重新生成；冻结研究只在`v0.10.2-archive`标签中
（`python scripts/archive.py`）。跨领域移植以`domains/light/`为模板：数值动作用`decide`，
类别动作不得取期望；校准使用两个不相交的标注分区；CP模式须显式选择并实测。
