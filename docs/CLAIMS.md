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
  [ok  ] decision_ms            0.188 vs 0.188 (tol 0.005)
  [ok  ] heldout_head_median    0.467973 vs 0.468 (tol 0.001)
  ...
13/13 claims match their artifacts
```

## The table

| claim | value | artifact | reproduce with |
| :--- | ---: | :--- | :--- |
| decision latency (ONNX, 1 thread) | 0.19 ms | `research/results/agent_baseline.json` | `scripts/03_evaluate.py` |
| held-out median cost, 120 plants | 0.468 | `research/results/eval_heldout_120.json` | `scripts/03_evaluate.py` |
| CMA-ES at the same budget | 1.813 | same file | same |
| 40-plant race, head / CMA-ES | 0.476 / 1.752 | `research/results/race.json` | `scripts/12_make_race.py --reuse` |
| hosted-model turn, median | 5.34 s | `race.json` → `assumptions` | `scripts/14_agent_baseline.py` |
| unparseable answers | 13 of 40 | same | same |
| plants not worse than their start | 200 of 200 | `research/results/robustness.json` | `scripts/11_robustness.py` |
| out-of-zoo plants beaten | 30 of 40 | `research/results/generalization.json` | `scripts/08_generalize.py` |
| experiment cost, Fast Restart | 111 ms | `research/bench/bench_log_15s.txt` | `research/bench/bench_run.m` |
| experiment cost, no Fast Restart | 869 ms | same | same |
| MATLAB forward vs exported reference | 7.6e-06 | `models/jev_head_weights.mat` | see the row in `claims.json` |
| valve dead band, zero-shot → specialised | 2.242 → 1.884 | `models/specialized/*.pt` (manual) | `scripts/10_specialize.py --scenario valve_dead_zone --plants 120` |
| motor-valve benchmark tuning | 1.238 → 0.598 (v0.2 sweep) | `docs/STEP4_RESULTS.md` | that run is history; the corrected sweep is documented there |

## Numbers that were published and then found wrong

Being explicit about this is the point of the file.

| number | what happened |
| :--- | :--- |
| `Ku ≈ 400` and the start `[240, 1160, 12.4]` on motor-valve benchmark | The sweep's grid ended at 400, it took the *last* oscillating point, and a damped response counted as oscillation. Fixed in v0.3; the consequence (the start was an artifact, and from a corrected start the head does not improve) is written up in `docs/STEP4_RESULTS.md#correction-the-ku-sweep-was-wrong`. |
| MATLAB/PyTorch parity `6.1e-05` | Measured again in v0.3 against the current weights: **7.6e-06**. The old figure was kept in a document that nobody re-ran. |
| `2.242 → 1.152 (−49 %)` for the valve dead band | Reproducing it needs `--plants 120` (30 held-out), not the script's default of 48 (12 held-out). The command is now written next to the number. |

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
| 决策延迟（ONNX，单线程） | 0.19 ms | `research/results/agent_baseline.json` | `scripts/03_evaluate.py` |
| 120 个留出对象的中位代价 | 0.468 | `research/results/eval_heldout_120.json` | `scripts/03_evaluate.py` |
| 同预算的 CMA-ES | 1.813 | 同上 | 同上 |
| 40 对象对比，本项目 / CMA-ES | 0.476 / 1.752 | `research/results/race.json` | `scripts/12_make_race.py --reuse` |
| 大模型单轮延迟（中位） | 5.34 s | `race.json` → `assumptions` | `scripts/14_agent_baseline.py` |
| 无法解析的回答 | 13/40 | 同上 | 同上 |
| 不比起点差的对象 | 200/200 | `research/results/robustness.json` | `scripts/11_robustness.py` |
| 打赢的对象（分布外） | 30/40 | `research/results/generalization.json` | `scripts/08_generalize.py` |
| 单次实验耗时（开 Fast Restart） | 111 ms | `research/bench/bench_log_15s.txt` | `research/bench/bench_run.m` |
| 单次实验耗时（不开） | 869 ms | 同上 | 同上 |
| MATLAB 前向 vs 导出参考 | 7.6e-06 | `models/jev_head_weights.mat` | 见 `claims.json` 对应行 |
| 阀死区，零点 → 专门化 | 2.242 → 1.884 | `models/specialized/*.pt`（需手工核对） | `scripts/10_specialize.py --scenario valve_dead_zone --plants 120` |
| motor-valve benchmark 整定 | 1.238 → 0.598（v0.2 的扫描） | `docs/STEP4_RESULTS.md` | 那次是历史；修正后的扫描写在同文件里 |

## 发布过、后来发现错掉的数字

写清楚这个，正是本文件的意义。

| 数字 | 发生了什么 |
| :--- | :--- |
| motor-valve benchmark 上的 `Ku ≈ 400` 与起点 `[240, 1160, 12.4]` | 扫描的网格上限是 400、取的是**最后**一个振荡点、而且把阻尼响应也算成振荡。v0.3 修好；后果（起点是假象，从修正后的起点出发决策头不再改善）写在 `docs/STEP4_RESULTS.md` 的更正一节。 |
| MATLAB/PyTorch 偏差 `6.1e-05` | v0.3 用当前权重重测：**7.6e-06**。旧数字留在没人重跑的文档里。 |
| 阀死区 `2.242 → 1.152（−49%）` | 复现需要 `--plants 120`（30 个留出），而不是脚本默认的 48（12 个留出）。命令现在写在数字旁边。 |

## 改了脚本之后

1. 重跑，读新数；
2. 改 `docs/claims.json` 里的值；
3. 改引用它的那句话；
4. 跑 `python scripts/16_check_claims.py`；
5. 两者放在同一个 commit 里，提交信息里写上这个数。

如果产物很贵（120 对象的基准、一次 MATLAB 会话），至少要把产物和 claims 一起更新，
哪怕正文晚一次再改。

## What is not tested

Three comparisons are missing on purpose, and they are the only places in this
project where a number is absent rather than unflattering. Saying so is cheaper
than letting a reader assume the comparison happened.

**1. The typed interface against a plain regression head.** Same features, same
expert data, same training budget, one difference: `choice / score / noul` versus
regressing the three gain deltas directly. Until this exists, the interface has
measured *properties* (ECE 0.02–0.031, 0.19 ms, thresholdable, auditable) and no
measured *performance advantage* over a small non-typed policy of the same size.
What it would take: one training run on `data/expert_train.npz` and the existing
evaluation harness. What it decides: whether the README's opening sentence is a
performance claim or an engineering one.

**2. A language model that is not on the network.** The only language baseline is
a hosted API — 5.34 s per turn, 13 of 40 answers unparseable — which mixes three
things: the language layer, the round trip, and the parsing. A local 1.5B–4B
model in the same loop would separate them. Without it, "an LLM is too slow for
the loop" is only proven for *cloud* LLMs.

**3. An external user.** Every plant in every benchmark is ours. "Point it at your
model" is a design goal backed by a test suite, not an observation. The discovery
work is the part most likely to break on someone else's model, which is why there
is an issue template for exactly that.


## 没有做的对照

这三项是**有意缺失**的，也是本仓库里唯一"没有数字"的地方——写清楚比让读者以为
做过要好。

**1. 类型化接口 vs 普通回归头。** 同样特征、同样专家数据、同样训练预算，只差一处：
`choice / score / noul` 对比"直接回归三个增益增量"。在它出现之前，这个接口有的是
**已测的性质**（ECE 0.02–0.031、0.19 ms、可阈值、可审计），没有**已测的性能优势**——
相对于同尺寸的非类型化策略。补上它需要：用 `data/expert_train.npz` 训一次，跑现有评估。
它决定的是：README 开头那句到底是性能主张还是工程主张。

**2. 不在网络上的语言模型。** 目前唯一语言基线是云端 API——单轮 5.34 秒、40 次里
13 次无法解析——它把三件事混在一起：语言层、网络往返、输出解析。同一个回路里换成本地
1.5B–4B 模型才能分开。没有它，"大模型太慢不适合进环"只对**云端**成立。

**3. 外部使用者。** 所有基准里的对象都是我们自己的。"拿它去调你的模型"是有测试支撑的
设计目标，不是观察结果。最容易在别人的模型上出问题的是发现（discover）那一段，所以专门
开了一个 issue 模板收这类反馈。
