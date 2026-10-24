# Changelog

All notable changes to this project. Numbers quoted here are measured, and the
file that produced them is named next to them.

[English](#english) · [简体中文](#简体中文)

## English

## [0.10.0] - 2026-10-24

* Publish the separable calibrated decision and safety shell, frozen-model peripheral calibration, and a trained non-PID reference-denoising transfer study. Preserve its `negative_stop` result and stop policy deepening; see `docs/NONPID_TRANSFER.md` and `docs/RECALIBRATION.md`.
* Harden checked C99 inference and MATLAB numeric handling. Keep measured host parity, latency and resources distinct from target-board or physical-safety guarantees.
* Preserve the strict cross-CPU temperature-refit and derived-comparison failures. Add independent, explicitly conditional Decimal audits of the original probabilities, calibration, full sets, actual action chains, terminal cache semantics, measured candidates and accounting, plus separately frozen post-incident runtime observations. Do not change the original checkers, tolerances or experiment results.
* Rebuild negative tests for numerical envelopes, positive but incorrect temperatures, source and evidence mutations, cache termination, jointly altered feedback/costs and publication bindings.
* Distribute the formal weights, source, original generated test models and pinned synthetic data. Remove personal-directory dependencies from helpers and examples, replace the discovery illustration with an original generated model, and document current-tree rights boundaries. Retain Git history as requested; do not distribute the original benchmark or geometry.
* Record failed and successful verification work separately from acquisition, retain source-bound receipts and publish bilingual evidence with checksum-verified release assets.

## [0.9.0] - 2026-10-24

* Pause complex risk research while preserving its results and reproduction entry points. Return the mainline to real-model adaptation, out-of-domain boundaries and complete simulation-budget comparisons.
* Add practical adaptation, accounting and preservation checks. Keep learned-risk deployment disabled; see `docs/MODEL_ADAPTATION.md`, `docs/PRACTICAL_BUDGET.md` and the versioned release evidence.

## [0.8.0] - 2026-10-24

* Preserve the previous failed risk study and add a reproducible raw-trajectory diagnosis of training-state shift, reached-sample scarcity and the fixed-path acceptance conflict.
* Register and push the new protocol before collection. Train on multi-round trajectories, fit temperature on independent trajectories, and calibrate each stage using independent reached plants under its frozen prefix.
* Assess a frozen selector over complete joint-action alternatives before CP. Preserve full label sets, the original trajectory risk budget, conservative quota fallbacks and the prohibition on retrying candidates after CP rejection.
* Evaluate the predeclared primary candidate and diagnostic controls on a new paired test cohort. Nominal risk and first-stage execution criteria pass, but mean and p90 cost criteria fail; the primary candidate remains research-only. No diagnostic arm replaces it after testing.
* Reproduce batch-dependent floating-point inference and disclose the additional validity gap: calibration/test mapping equivalence and independent trajectory events are not established. The computed CP/binomial quantities do not establish an implementation-level coverage guarantee. Keep this post-hoc audit separate from the frozen numerical criteria and prohibit deployment.
* Commit compressed raw shards and executing-source snapshots. Independently reconstruct the fitted model, selected actions, stage quantiles, operating histories, simulation ledger and acceptance. Record exact deterministic evaluation replay separately from independent evidence.
* Preserve the Linux strict cohort-hash failure despite matching scientific package versions. Scope exact canonical-record replay to the recorded Windows reference host; distinguish hosted scientific-audit checks from cross-platform runtime support without relaxing identity or numerical comparisons.
* Generate bilingual documentation and claims from the final artifacts; extend evidence-mutation tests and rerun Python, C99 and real MATLAB controller verification. Generic runtime risk-head defaults remain disabled. See `docs/TRAJECTORY_RISK.md` and `docs/RELEASE_VERIFICATION.md`.

## [0.7.0] - 2026-10-24

* Freeze and commit a prospective multi-round risk protocol before collecting fresh stage cohorts and a fixed-size paired evaluation. Preserve the original risk model and temperature.
* Calibrate each stage with new independent plants under its frozen prefix, allocate the finite-horizon risk budget in advance, and retain both labels when the finite-sample rank is unavailable.
* Run matched monitor and whole-action gated research controllers, separating actual operations, rejected diagnostics and calibration measurements. Both stop at the safety veto without introducing uncalibrated recovery actions.
* Publish the failed enablement assessment in `docs/JOINT_RISK_ROLLOUT.md`: the risk bound passes, while the first-stage execution lower bound and final mean/p90 cost criteria fail. The joint-risk policy remains research-only; generic Python/C99/MATLAB defaults are unchanged.
* Unify harmful transitions as strict cost increases, retain the explicitly named legacy greater-than-two-percent metric, and regenerate affected experiments and bilingual documentation. Independently reconstruct calibration, trajectory events, full actions and simulation counts from the committed compressed raw traces in the claims checker.

## [0.6.0] - 2026-10-24

* Default to CP monitor: retain the full label set and independent would-hold reasons while preserving the temperature-scaled continuous proposal. Explicit hard_hold remains a reproducible comparison.
* Stop unchanged deterministic trials without spending another simulation; distinguish terminal proposals from measured transitions and report actual measurement counts. Repeated-observation mode remains explicit.
* Synchronize monitor/hard_hold and diagnostics in Python, C99 and MATLAB, with generated parity fixtures and real MATLAB controller tests.
* Add a fixed-protocol, independently trained/calibrated/evaluated joint-action risk study. It accepts or holds the whole assessed proposal; its one-state unconditional risk boundary does not certify adaptive closed-loop safety. This experimental head is not enabled in deployment.
* Version the mechanism and paired-performance diagnostics, preserve unfavorable hard-hold outcomes, and rerun current studies. Separate proposal admission rates from measured-transition rates after stopping.
* Correct the confidence-interval description to paired normal approximation (mean ±1.96 SE), regenerate bilingual evidence, and extend claims checks to the new reports.


## [0.5.0] - 2026-10-24

### Temperature + Split CP

* Retain temperature scaling and fit split-conformal `1-p(teacher label)` quantiles on a separate plant-level sample. A third sample measures empirical coverage; evaluation labels never select thresholds.
* Default alpha is 0.10 and k_max is 3. Empty, wide or opposing-direction sets hold axes before actuation; full-distribution expectation and variance shrink are retained. Python, MATLAB and C share vectors and metadata.
* The guarantee is per-axis marginal teacher-label inclusion under exchangeability on fresh initial states. It does not imply joint, adaptive-loop or safety coverage. Empirical results, including an axis below nominal, are published in `docs/CONFORMAL.md`.
* Matched E1/E2 controls show higher cost for CP than temperature-only and ordinary regression here. CP has a lower p90 than its coverage-matched random-hold control, but a higher median; all results are retained without retuning alpha or q_hat.

### Fixed

* Record each measured transition once, account for partial-axis holds, separate rollback events, and make gates independent across plants.
* Early stopping now stops simulations. Real per-plant measurement counts replace stop-index estimates.
* CMA-ES, BO and grid search return the measured winning gains. CMA/BO measure their shared initial point inside the budget.
* Keep noisy simulations invariant under subsets and reordering. Forward horizon/reference settings into evaluator and expert metrics/features.
* Reject nonfinite numbers, invalid probabilities and nonpositive temperatures. Stable softmax handles tiny positive temperatures; zero steps preserve parameter bits. Repair the opt-in ValueNet path.
* Validate numeric Option payloads against explicit PID schemas; support a standalone arbitrary-axis numeric decoder and additive non-PID toy.
* Repair MATLAB escalation totals and first-iteration rollback/history, with a shared decoder and tau_noul support.
* C tests now reject NaN/Inf and cover every head plus policy boundaries; confident zero actions are distinct from abstention. Remove mutable static initialization.
* Normalize ELF/COFF section accounting and unavailable resource values. Distinguish static RAM, stack frames, host readonly storage and full integer inference.

### Evidence and documentation

* Refit A0 on the matched 90% training split with expectation-preserving interpolation and a cache manifest. Keep the single-training-checkpoint limitation explicit.
* Separate threshold selection and independent validation; add matched-coverage random hold, four calibration adaptation arms and actual acquisition counts. In the CP-off adaptation experiment, temperature-only improves slightly while threshold-only and combined worsen; thermal hill climbing still beats the default CP head.
* Regenerate both 120-plant benchmarks, E1/E2/calibration, robustness, generalization, specialization, disturbance study, animation, C/MATLAB vectors and hardware/latency evidence from scripts.
* Measure the actual default typed/abstention path with 2000 raw timing samples. Host timing is not target-board WCET.
* Check registered prose and bilingual README/table rows against artifacts; manual evidence cannot count as an automatic pass.
* Update English/Chinese architecture, applicability, benchmark, transfer, specialization, claims and experiment documentation; clearly version historical study pages.

## [0.4.1] - 2026-10-24

### Added

* **A frozen test family (P3).** `plants.TEST_FAMILIES` adds `thermal_deadtime`:
  120 first-order plants with large dead time, generated from a fixed parameter
  grid with **no RNG**, so there is no seed to drift. It was defined after the
  shipped head was trained and evaluated once. `two_mass` is relabelled the
  **validation** family, because it was used to reject the lookahead net and to
  compare vocabulary v1 with v3.
* `scripts/03_evaluate.py --family thermal_deadtime` and
  `research/results/eval_thermal_deadtime_120.json`. The result: the head is
  **second** on this family — 1.737 median against 1.711 for a plain hill climb
  over the same vocabulary (p90 2.871 vs 2.447); it is still ahead of BO (1.877),
  CMA-ES (1.976) and the one-shot classical tuners. README, `STEP1_RESULTS.md`
  and `BENCHMARK.md` now state that, and say which numbers played a role in
  design decisions.
* **A coverage gate**: `pytest --cov --cov-fail-under=66`, measured at 69 % with
  the three MATLAB-only modules omitted (they cannot execute on a runner without
  a licence). 19 new tests: baselines, expert rollouts, identification,
  scenarios, the MCP handshake and the end-to-end evaluate script.
* `models/ablation_a0.pt` is committed, so reproducing `docs/ABLATION.md` does
  not retrain the regression control for four minutes.

### Fixed

* `03_evaluate.py` skipped `jev_head_swept` instead of crashing when the budget
  cannot pay for the 7-run Ku/Tu sweep.
* `run_bo` clamps its initial design to the budget (a budget below 6 used to
  spend more experiments than it was given); `run_simplex` no longer overshoots
  on its last iteration. At 20 experiments both are unchanged.
* `docs/CLAIMS.md` still quoted `2.242 → 1.884` for the valve specialist in its
  main table; the reproducible figure is 2.207.
* The generated C test vectors used `sin`/`cos`, which differ in the last ULP
  between libm builds, so `test_vectors.json` was not byte-reproducible across
  platforms. They now use exact arithmetic only.

## [0.4.0] - 2026-10-23

This release is mostly about making the published numbers true and putting the
typed decision layer on the execution path. Several headline figures changed,
some of them for the worse.

### Fixed

* **The returned gains and the reported cost could disagree.** The last
  measurement updated `best_cost` but not `best_gains`, so on 6 of 120 plants the
  reported cost belonged to gains the loop had not returned. Both are now updated
  together and `tests/test_evaluate.py` asserts that re-simulating the returned
  gains reproduces `best_j` exactly.
* **The budget was not the budget that was written.** `03_evaluate.py` defaulted
  to `--iters 24`, and the loop measured the start plus every proposal plus one
  final run: the head got **25** experiments while CMA-ES got 18, and the prose
  said "the same 20-simulation budget". Every method now spends exactly 20
  (`budget=20`), the head included, and the budget is written into the JSON.
* **The early-stop predicate was inverted.** It tested the *worst* cost band
  (`argmax(score) == 4`), so it never fired. Fixed, measured — and turned **off**
  by default, because when it does fire it quits halfway and costs 0.27 median
  (`docs/ABLATION.md`, A6).
* **`scenarios.variants` was not reproducible.** It seeded with Python's salted
  `hash(name)`, so every out-of-zoo plant was different in every process. Several
  published numbers (generalisation, robustness, the specialist table) were
  measured on a draw that cannot be regenerated. Now `crc32(name)`; the affected
  artifacts were regenerated and the old figures are retracted in
  `docs/SPECIALIZE.md` and `docs/GENERALIZATION.md`.
* **MATLAB decoded with the sample variance.** `var(d)` divides by N−1 while
  `numpy.var` divides by N, so the variance shrink differed by ~6 % between the
  two runtimes. `var(d, 1)` now; the full step (temperature → softmax →
  expectation → shrink → abstention → clip) matches Python to **2.6e-08**.
* **`race.json` had lost the measured LLM turn.** Re-running the race script
  overwrote it with a 3.0 s assumption while the README quoted 5.34 s. The script
  now reads the measurement from `agent_baseline_900.json`.

### Added

* **`src/jev_tune/decision.py`** — `DecisionBackend`, `NumericBackend`,
  `OnnxBackend`, a fixed question registry, and `load_backend()`. The evaluator,
  the CLI, the demo and the MCP server all go through it; a bare `JevHead` is
  wrapped by `as_backend()` and keeps its fitted temperatures.
* **Temperature scaling is applied in the main loop**, from
  `models/calibration.json`, with `calibrate=False` for the ablation.
* **Explicit a-priori abstention** (`decode.AbstainPolicy`): execute / hold /
  hold-and-flag, per axis, on the calibrated `p_max`. On by default at
  `tau_act = 0.35`; `abstain=None` disables it. Measured in
  `docs/ABSTENTION.md` and ablated as A5.
* **`scripts/17_ablation.py`** — regression head, argmax, expectation, shrink,
  abstention, gate and early stop, at the same budget, three draws
  (`docs/ABLATION.md`).
* **`scripts/20_abstention.py`** — coverage/cost/harm curve for the threshold.
* **`scripts/21_hardware.py`** — parameters, MACs, p99, C footprint, int8
  agreement (`docs/COMPUTE.md`).
* **`scripts/22_calibrate_only.py`** — freeze the weights, fit T and tau on a few
  dozen samples (`docs/CALIBRATE_ONLY.md`). It **did not help** on the out-of-zoo
  family; the negative result is in the file.
* **`c/`** — a zero-dependency C99 inference reference (no `malloc`, fixed
  arrays), generated weights, and language-neutral `test_vectors.json`.
  `python scripts/18_export_c.py --verify` compiles it and checks forward,
  features and resampling against Python.
* **Docs** — `docs/JEV_MAPPING.md` (what is borrowed from Jev, what is not),
  `docs/TRANSFER.md` (module map and porting questions for other domains),
  `docs/BENCHMARK.md` (accounting and holdout hygiene), plus the generated
  `ABLATION.md`, `ABSTENTION.md`, `COMPUTE.md`, `CALIBRATE_ONLY.md`.

### Changed

* **The headline benchmark** (`research/results/eval_heldout_120.json`, 120
  plants, every method at 20 experiments):

  | method | before | now |
  | :--- | ---: | ---: |
  | Jev head | 0.468 (at 25 experiments) | **0.440** |
  | Bayesian optimisation | 0.567 | 0.567 |
  | CMA-ES | 1.813 (at 18) | 1.705 |
  | identify → `pidtune` | 0.742 | 0.742 |
  | relay autotune | 0.906 (broken: no limit cycle) | removed, replaced by `swept_zn` 1.860 |

* `research/results/benchmark_table.md` is now generated by
  `scripts/03_evaluate.py` from the same JSON; the hand-edited stale copy is gone.
* The README's first screen says **Jev-inspired / not affiliated with TypeSafe
  AI**, and a Related Work section lists the lineage instead of leaving it
  implicit.
* `ARCHITECTURE.md` no longer describes components that do not exist
  (`DecisionBackend` and `NumericHead` are real now; `LayaBackend` is stated as
  never wired in), and it labels each module as domain-agnostic shell or PID
  testbed.
* `expert.py`'s docstring said "5 bins, 16 simulations"; it is 7 bins × 3 axes +
  1 combined = 22.

### Known consequences

* With abstention on by default, the out-of-zoo study improves **32 of 40**
  plants instead of 37, and its median ratio goes from 0.97 to 1.014. Holding
  when unsure is a safety trade, not a free win; `docs/ABSTENTION.md` has the
  curve.
* The valve dead-band specialist now improves **2 %**, not 16 %, on a
  reproducible draw.

## [0.3.1] - 2026-10-23

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

### Docs

* The README's 15-second table quoted a motor-valve benchmark re-run (`11 experiments, 1.377 →
  0.615`) beside the recorded run (`1.238 → 0.598`, best at experiment 5) and a
  GIF caption that said "five", so three numbers described one model. The table
  now quotes the recorded run only.
* Removed `236–276 ms for a hosted Jev call`: it was a Phase-0 estimate and is
  labelled as one now. The "how fast" row uses the measured 5.34 s LLM turn.
* Removed the `10–90×` pointer. `docs/SCALE.md` never contained that range; the
  two ratios it does contain are 14× and 22×, and the README quotes those.
* `docs/SCALE.md` now says the phase table describes `jev-tune matlab` **without**
  `--auto`; with it, the load and compile are paid inside `discover` (measured:
  setup 0.7 s, sweep 3.6 s, versus 24.3 s and 38.7 s).
* The platform badge no longer claims Linux and macOS for the MATLAB bridge,
  which has only been run on Windows. `docs/SCALE.md` keeps the version matrix.
* `CONTRIBUTING.md` lists the three comparisons that have not been made: typed
  interface against a regression head, a local language model, an outside model.
* Repository layout in both READMEs regenerated (scripts 00–16, the eight
  subcommands, the modules that were missing), and the Chinese README's
  "试一试" link now points at the heading that exists.

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

## 简体中文

## [0.10.0] - 2026-10-24

* 发布可拆解校准决策与安全边界参考壳、冻结模型的外围标定，以及真实训练的非PID参考去噪迁移实验。保留`negative_stop`结果并停止策略深化，见`docs/NONPID_TRANSFER.md`与`docs/RECALIBRATION.md`。
* 加固C99检查入口和MATLAB数值处理，将宿主对齐、延迟和资源实测与目标板或物理安全保证严格区分。
* 保留严格跨CPU温度重新拟合及派生比较失败，新增明确受条件限制的独立Decimal审计，核验原概率、校准、完整集合、实际动作链、终止缓存语义、实测候选和计账，并单独冻结事后运行观测。不修改原检查器、容差或实验结果。
* 加固数值包络、有限正值错误温度、源码与证据篡改、缓存终止、反馈与成本联合伪造，以及发布绑定等负测。
* 分发正式权重、源码、原创生成测试模型与固定合成数据；移除辅助程序和示例对个人目录的依赖，发现动画改用原创生成模型，说明当前公开树的权利边界。按用户要求保留Git历史，不分发原始基准模型或几何文件。
* 将失败及成功复核计算与前瞻采集分开计账，保留绑定源码的凭据，并分发中英文证据及经过校验和核对的发布附件。

## [0.9.0] - 2026-10-24

* 暂停复杂风险研究并保留结果与复现入口，主线转回真实模型适配、域外失效边界和完整仿真预算对照。
* 增加实际适配、计账与历史保留检查，学习风险头部署继续关闭，见`docs/MODEL_ADAPTATION.md`、`docs/PRACTICAL_BUDGET.md`及相应版本的发布证据。

## [0.8.0] - 2026-10-24

* 保留上次风险研究的失败结果，纳入基于原始轨迹的可复现诊断，分析训练状态偏移、到达样本不足和固定路径下的验收冲突。
* 在采样前注册并推送新协议。使用多轮轨迹训练、独立轨迹温度拟合，以及各步冻结前缀下的独立到达对象校准。
* 先由冻结选择器选择完整联合动作，再计算CP。保留完整标签集、原整段风险预算、样本配额不足时的保守回退，以及CP拒绝后不重试候选的规则。
* 用全新配对测试集验证预定主候选和诊断对照。名义风险与首步执行率通过数值门槛，平均代价及p90未通过，主候选保持研究模式；不在测试后改选诊断组替代主候选。
* 复现批处理相关浮点推理差异，披露额外有效性缺口：校准与测试的映射一致性、轨迹事件独立性尚未建立，算出的CP/二项统计量不能证明机器实现的覆盖保证。事后有效性审计与冻结数值门槛分开记录，继续禁止部署。
* 保留Linux在科学包版本一致时仍发生的严格对象哈希失败。规范化记录精确重放限定于记录的Windows参考宿主，区分托管科学审计与跨平台运行时支持，不放宽身份或数值比较。
* 提交压缩原始分片和实际执行源码快照，独立复算模型、选择动作、逐步分位数、操作历史、仿真账目和验收。确定性评估重放单独记账，不冒充独立证据。
* 根据最终产物生成中英文文档及claims，增加证据变异测试，重跑Python、C99和MATLAB真实控制器验证。通用运行时仍不默认启用风险头；详情见`docs/TRAJECTORY_RISK.md`与`docs/RELEASE_VERIFICATION.md`。

## [0.7.0] - 2026-10-24

* 在采集新逐步校准批次和固定样本配对评估之前，冻结并提交多轮风险验证协议；保留既有风险模型和温度。
* 每步使用已冻结前缀下的新独立对象校准，预先分配整段风险预算。有限样本秩不可实现时保留两个标签并保持，不降低覆盖要求。
* 真实运行匹配的monitor与整组门控研究控制器，区分操作、被拒绝动作诊断和校准测量。两组在安全门触发时停止，不引入未经校准的回退动作。
* 在`docs/JOINT_RISK_ROLLOUT.md`公布未通过的启用验收：风险上界通过，第一步执行率下界与最终均值/p90代价门槛未通过。联合风险策略保持研究模式，通用Python/C99/MATLAB默认行为不变。
* 将有害转移统一为严格代价上升，显式保留旧的超过2%口径，重新生成受影响实验和中英文文档。claims检查从已提交的压缩原始轨迹独立重建校准、轨迹事件、完整动作和仿真计数。

## [0.6.0] - 2026-10-24

* 默认CP monitor保留完整标签集合及独立would_hold原因，保持温度缩放后的连续提案；hard_hold保留为可复现的显式对照。
* 确定性参数不变时停止重复试验；区分终止提案和已测转移，报告真实测量次数，重复观测须显式开启。
* 同步Python/C99/MATLAB模式与诊断，重新生成测试向量并运行真实MATLAB闭环验证。
* 新增固定协议、独立训练/校准/评估的联合动作风险实验，整组接纳或保持被评估提案；单次初态无条件风险边界不证明自适应闭环安全，研究头不默认部署。
* 将机制及配对性能诊断纳入仓库，保留硬保持的不利结果，重跑当前实验；停止后分别报告提案接纳率与已测转移接纳率。
* 将置信区间表述纠正为配对正态近似（均值±1.96标准误），重新生成中英证据，claims覆盖新增报告。


### 0.5.0 — 审计修复与证据重算

每条实测转移只记一次，部分轴保持计入统计；回滚逐株独立，早停真正减少仿真。
CMA/BO计入共同实测起点，CMA/BO/网格返回实测赢家。噪声在子集与重排下按对象保持一致，
时长/参考值同步传入状态与代价。数值边界显式校验，极小温度稳定计算，零步保持参数位值；
可选ValueNet恢复可执行。数值Option载荷契约统一，并增加非PID两轴加法示例。

MATLAB修复首次回滚、历史错配和累计升级，并支持tau_noul独立解码。C校验覆盖全部头与策略，
NaN/Inf变体必须失败，主动零动作不再冒充弃权；移除可变静态初始化。资源统计正确处理ELF/COFF，
分别列静态RAM、栈帧、宿主只读占用与量化语义。

A0采用同一90%训练划分及保持期望的插值；阈值选择与独立验证分开，增加匹配覆盖随机保持和
四臂校准适配，采样按真实仿真计费。显式关闭CP的适配中，温度单独调整略有改善，阈值及组合变差；热工族仍由同词表爬山胜出。
两族120株基准、消融、弃权、校准、鲁棒性、泛化、专门化、扰动研究、动画、端口向量和硬件证据均由脚本重算。
时延测量覆盖默认弃权路径并保存2000个原始样本，不作板端WCET保证。注册正文及双语表格与产物独立比对，
人工证据不计自动通过。当前文档双语同步，历史结果明确标注版本，训练种子重复等未测研究继续如实列明。

保留温度缩放，并在独立对象样本上拟合分裂CP分位数，第三组样本只作经验评估。默认alpha=0.10、
k_max=3；空集、过宽或正负矛盾集合事前保持，保留完整分布期望与方差缩步，Python/MATLAB/C同步。
覆盖定理只适用于初态交换性下逐轴专家标签的边际包含率，不保证联合、自适应闭环或安全。
实测第三轴低于名义水平，未重调阈值；E1中CP代价及p90劣于温度单独校准，E2中CP中位代价劣于
匹配随机保持而p90更低，均照实发布。
