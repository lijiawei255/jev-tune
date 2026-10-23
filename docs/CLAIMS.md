# Where every published number comes from

> [中文版在下方](#每个数字的来源)

This project's only real asset is that its numbers are measured. A sentence in a
README drifts the moment a script changes: the code gets fixed, the model gets
retrained, and the old figure stays in the prose. Two things prevent that here:

1. **`docs/claims.json`** — every number the repository publishes, with the
   artifact it is read from.
2. **`scripts/16_check_claims.py`** — re-reads each artifact and fails when it no
   longer matches. It runs in CI, so a stale sentence breaks the build instead of
   quietly misleading someone.

```console
$ python scripts/16_check_claims.py
  [ok  ] decision_ms                0.1892 vs 0.189 (tol 0.01)
  [ok  ] heldout_head_median        0.439579 vs 0.44 (tol 0.001)
  ...
33/33 claims match their artifacts
```

## The table

| claim | value | artifact | reproduce with |
| :--- | ---: | :--- | :--- |
| model forward (ONNX, 1 thread) | 0.189 ms | `research/results/latency.json` | `scripts/04_export_onnx.py` |
| complete typed decision | 0.73 ms (p99 1.36) | `latency.json`, `hardware.json` | `scripts/04_export_onnx.py`, `21_hardware.py` |
| held-out median cost, 120 plants | 0.440 (p90 1.038) | `research/results/eval_heldout_120.json` | `scripts/03_evaluate.py --plants 120 --budget 20` |
| every method's budget | 20 experiments | same file → `budget_per_plant` | same |
| Bayesian optimisation, same budget | 0.567 | same | same |
| CMA-ES, same budget | 1.705 | same | same |
| identify → `pidtune` | 0.742 (2 experiments) | same | same |
| shrunken Z-N | 1.290 (1 experiment) | same | same |
| typed vs regression head | 0.439 vs 0.494 | `research/results/ablation.json` | `scripts/17_ablation.py` |
| abstention coverage / threshold | 0.62 at `tau_act = 0.35` | `research/results/abstention.json` | `scripts/20_abstention.py` |
| 40-plant race, head / CMA-ES | 0.463 / 1.569 | `research/results/race.json` | `scripts/12_make_race.py` |
| hosted-model turn, median | 5.34 s | `race.json` → `assumptions` | `scripts/14_agent_baseline.py` |
| unparseable answers | 13 of 40 | same | same |
| plants not worse than their start | 200 of 200 | `research/results/robustness.json` | `scripts/11_robustness.py` |
| out-of-zoo plants within 5 % | 32 of 40 | `research/results/generalization.json` | `scripts/08_generalize.py` |
| parameters / MACs per decision | 40 683 / 83 584 | `research/results/hardware.json` | `scripts/21_hardware.py` |
| C99 static flash / RAM | 168 260 B / 16 B | same | same |
| int8 per-channel: same argmax | 97.3 % | same | same |
| experiment cost, Fast Restart | 111 ms | `research/bench/bench_log_15s.txt` | `research/bench/bench_run.m` |
| MATLAB forward vs exported reference | 3.8e-06 (logits), 2.6e-08 (step) | `models/jev_head_weights.mat` | `scripts/06_export_weights_mat.py` + MATLAB |
| valve dead band, zero-shot → specialised | 2.242 → 1.884 | `models/specialized/*.pt` (manual) | `scripts/10_specialize.py --scenario valve_dead_zone --plants 120` |
| calibration-only adaptation, valve dead band | 2.193 → 2.318 (**worse**) | `research/results/calibrate_only.json` | `scripts/22_calibrate_only.py` |
| motor-valve benchmark tuning | 1.238 → 0.598 (v0.2 sweep) | `docs/STEP4_RESULTS.md` | that run is history; the corrected sweep is documented there |

## Numbers that were published and then found wrong

Being explicit about this is the point of the file.

| number | what happened |
| :--- | :--- |
| **"0.468 at the same 20-simulation budget"** | The head actually ran 25 experiments (`--iters 24` plus the final measurement) while CMA-ES ran 18. In 0.4.0 every method runs **20**; the head is **0.440**. This was the most misleading number the project published. |
| **"relay autotune 0.906 / p90 0.935"** | The relay never sustained a limit cycle on the held-out family (0/120 plants), so the row was a constant gain set, not a relay tuner. Replaced by `swept_zn`, which pays for its own 7-run Ku/Tu sweep. |
| **`best_j` and `best_gains` could disagree** | The final measurement updated the reported cost but not the returned gains. They are now updated together and a test enforces it (`tests/test_evaluate.py`). |
| **"200/200 never worse" next to the safety gate** | It is a construction (the start is measured first and the loop keeps a running minimum). The gate fired once in the whole study. Stated as construction; the gate's effect is reported separately. |
| **`Ku ≈ 400` and the start `[240, 1160, 12.4]` on motor-valve benchmark** | The sweep's grid ended at 400, it took the *last* oscillating point, and a damped response counted as oscillation. Fixed in v0.3; the consequence is written up in `docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong`. |
| **MATLAB/PyTorch parity `6.1e-05`** | Re-measured in v0.3: **7.6e-06** for the logits. In 0.4.0 the parity test also covers the decode (temperature, shrink, abstention, clip): **2.6e-08**. |
| **`2.242 → 1.152 (−49 %)` for the valve dead band** | Reproducing it needs `--plants 120` (30 held-out), not the script's default of 48 (12 held-out). The command is now written next to the number. |
| **`11 experiments, 1.377 → 0.615` in the 15-second table** | A re-run that was never written up. Removed in v0.3.1. |
| **`236–276 ms for a hosted Jev call`** | Never measured here — a Phase-0 estimate. Removed in v0.3.1. |
| **`10–90×`** | The README pointed at `docs/SCALE.md`, which never contained that range. Removed. |
| **`28 s setup` / `40 s Kp sweep`** | True for `jev-tune matlab` **without** `--auto`. With `--auto` the load and compile are paid inside `discover`. `docs/SCALE.md` now says which path the table describes. |

## When you change a script

1. re-run it, read the new number;
2. update the value in `docs/claims.json`;
3. update the sentence in the document that quotes it;
4. run `python scripts/16_check_claims.py`;
5. commit both together, in one commit, with the number in the message.

If the artifact is expensive to regenerate (a 120-plant benchmark, a MATLAB
session), update the artifact and the claim in the same commit even if the prose
changes later.

---

# 每个数字的来源

这个项目唯一真正值钱的东西，是它的数字都测过。脚本一改，README 里那句话就开始漂：
代码修好了、模型重训了，而句子还是旧的。这里用两样东西防住它：

1. **`docs/claims.json`**：仓库对外发布的每个数字，以及它读自哪个产物；
2. **`scripts/16_check_claims.py`**：逐个重新读取产物，对不上就失败。它跑在 CI 里，
   所以一句话过期会让构建失败，而不是悄悄误导读者。

## 表格

| 声明 | 数值 | 产物 | 复现命令 |
| :--- | ---: | :--- | :--- |
| 模型前向（ONNX，单线程） | 0.189 ms | `research/results/latency.json` | `scripts/04_export_onnx.py` |
| 完整类型化决策 | 0.73 ms（p99 1.36） | `latency.json`、`hardware.json` | `scripts/04_export_onnx.py`、`21_hardware.py` |
| 120 株留出对象中位代价 | 0.440（p90 1.038） | `research/results/eval_heldout_120.json` | `scripts/03_evaluate.py --plants 120 --budget 20` |
| 每个方法的预算 | 20 次实验 | 同文件 → `budget_per_plant` | 同上 |
| 贝叶斯优化（同预算） | 0.567 | 同上 | 同上 |
| CMA-ES（同预算） | 1.705 | 同上 | 同上 |
| 辨识 → `pidtune` | 0.742（2 次实验） | 同上 | 同上 |
| 缩小 Z-N | 1.290（1 次实验） | 同上 | 同上 |
| 类型化 vs 回归头 | 0.439 vs 0.494 | `research/results/ablation.json` | `scripts/17_ablation.py` |
| 弃权覆盖率 / 阈值 | 0.62，`tau_act = 0.35` | `research/results/abstention.json` | `scripts/20_abstention.py` |
| 40 对象对比，本项目 / CMA-ES | 0.463 / 1.569 | `research/results/race.json` | `scripts/12_make_race.py` |
| 大模型单轮延迟（中位） | 5.34 s | `race.json` → `assumptions` | `scripts/14_agent_baseline.py` |
| 无法解析的回答 | 13/40 | 同上 | 同上 |
| 不比起点差的对象 | 200/200 | `research/results/robustness.json` | `scripts/11_robustness.py` |
| 分布外 5% 以内的对象 | 32/40 | `research/results/generalization.json` | `scripts/08_generalize.py` |
| 参数量 / 每次决策 MACs | 40 683 / 83 584 | `research/results/hardware.json` | `scripts/21_hardware.py` |
| C99 静态 Flash / RAM | 168 260 B / 16 B | 同上 | 同上 |
| int8 逐通道：argmax 一致 | 97.3% | 同上 | 同上 |
| 单次实验耗时（开 Fast Restart） | 111 ms | `research/bench/bench_log_15s.txt` | `research/bench/bench_run.m` |
| MATLAB 前向 vs 导出参考 | 3.8e-06（logits）、2.6e-08（步长） | `models/jev_head_weights.mat` | `scripts/06_export_weights_mat.py` + MATLAB |
| 阀死区，零点 → 专门化 | 2.242 → 1.884 | `models/specialized/*.pt`（需手工核对） | `scripts/10_specialize.py --scenario valve_dead_zone --plants 120` |
| 仅校准适配（阀死区） | 2.193 → 2.318（**更差**） | `research/results/calibrate_only.json` | `scripts/22_calibrate_only.py` |
| motor-valve benchmark 整定 | 1.238 → 0.598（v0.2 的扫描） | `docs/STEP4_RESULTS.md` | 那次是历史；修正后的扫描写在同文件里 |

## 发布过、后来发现错掉的数字

写清楚这个，正是本文件的意义。

| 数字 | 发生了什么 |
| :--- | :--- |
| **"同预算 20 次下 0.468"** | 决策头实际跑了 25 次（`--iters 24` + 最后一次测量），CMA-ES 只跑 18 次。0.4.0 起所有方法 **20 次**；决策头是 **0.440**。这是本项目发布过的最误导的数字。 |
| **"继电 0.906 / p90 0.935"** | 继电在留出族上从未形成极限环（0/120 株），那一行其实是固定增益组，不是继电整定。换成 `swept_zn`，它自己付 7 次 Ku/Tu 扫描。 |
| **`best_j` 与 `best_gains` 可能不一致** | 最后一次测量更新了报告代价却没更新返回增益。现在两者同步更新，并有测试守护（`tests/test_evaluate.py`）。 |
| **把"200/200 不比起点差"写在安全门旁边** | 它是构造性质（起点最先测、回路保持运行最小值）。整项研究里门只触发过 1 次。现在明确写成构造性质，门的收益单独报告。 |
| **motor-valve benchmark 上的 `Ku ≈ 400` 与起点 `[240, 1160, 12.4]`** | 扫描网格上限 400、取的是**最后**一个振荡点、把阻尼响应也算成振荡。v0.3 修好；后果写在 `docs/STEP4_RESULTS.md` 的更正一节。 |
| **MATLAB/PyTorch 偏差 `6.1e-05`** | v0.3 用当前权重重测：**7.6e-06**（仅 logits）。0.4.0 的对比还覆盖解码（温度、缩步、弃权、裁剪）：**2.6e-08**。 |
| **阀死区 `2.242 → 1.152（−49%）`** | 复现需要 `--plants 120`（30 个留出），而不是脚本默认的 48（12 个留出）。命令现在写在数字旁边。 |
| **15 秒表里的 `11 次实验，1.377 → 0.615`** | 一次没有写进任何文档的重跑。v0.3.1 删除。 |
| **`托管 Jev 236–276 ms`** | 本仓库从未测过，是 Phase 0 的估算。v0.3.1 删除。 |
| **`10–90×`** | README 指向 `docs/SCALE.md`，但那份文档里从来没有这个区间。已删除。 |
| **吞吐表里的 `28 s 建模` / `40 s 扫 Ku`** | 对**不带** `--auto` 的 `jev-tune matlab` 成立。带 `--auto` 时加载与编译在 `discover` 里付掉。`docs/SCALE.md` 现在写明表格对应哪条路径。 |

## 改了脚本之后

1. 重跑，读新数；
2. 改 `docs/claims.json` 里的值；
3. 改引用它的那句话；
4. 跑 `python scripts/16_check_claims.py`；
5. 两者放在同一个 commit 里，提交信息里写上这个数。

如果产物很贵（120 对象的基准、一次 MATLAB 会话），至少要把产物和 claims 一起更新，
哪怕正文晚一次再改。

## What is not tested

Two comparisons are missing, and they are the only places in this project where a
number is absent rather than unflattering. Saying so is cheaper than letting a
reader assume the comparison happened.

**1. A language model that is not on the network.** The only language baseline is
a hosted API — 5.34 s per turn, 13 of 40 answers unparseable — which mixes three
things: the language layer, the round trip, and the parsing. A local 1.5B–4B
model in the same loop would separate them. Without it, "an LLM is too slow for
the loop" is only proven for *cloud* LLMs.

**2. An external user.** Every plant in every benchmark is ours. "Point it at
your model" is a design goal backed by a test suite, not an observation. The
discovery work is the part most likely to break on someone else's model, which is
why there is an issue template for exactly that.

> The typed-interface question used to be item 1 on this list. It is measured
> now: `docs/ABLATION.md`.

## 没有做的对照

这两项是**有意缺失**的，也是本仓库里唯一"没有数字"的地方——写清楚比让读者以为
做过要好。

**1. 不在网络上的语言模型。** 目前唯一语言基线是云端 API——单轮 5.34 秒、40 次里
13 次无法解析——它把三件事混在一起：语言层、网络往返、输出解析。同一个回路里换成本地
1.5B–4B 模型才能分开。没有它，"大模型太慢不适合进环"只对**云端**成立。

**2. 外部使用者。** 所有基准里的对象都是我们自己的。"拿它去调你的模型"是有测试支撑的
设计目标，不是观察结果。最容易在别人的模型上出问题的是发现（discover）那一段，所以专门
开了一个 issue 模板收这类反馈。

> 类型化接口那条原来在本节第一条，现在已实测：`docs/ABLATION.md`。
