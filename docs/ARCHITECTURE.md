# Architecture

> [English](#english) · [简体中文](#简体中文)


## English

### Contract

Every decision in this project is one of three Jev primitives, answered by a
backend that takes a state and a set of questions. There is no
"regress the gain directly" path — that is the experiment.

```python
# src/jev_tune/decision.py
class DecisionBackend(Protocol):
    def answer(self, feats, curves, questions: Sequence[Question] | None = None) -> Answer: ...
```

* `Choice(question, options, probs)` — pick one of K, with a probability per option
* `Score(question, levels, dist)` — ordered rubric judgement
* `Noul(statement, p_true)` — calibrated yes/no

The primitives are batched: `probs` is `(K,)` for one state and `(N,K)` for the
loop, and the methods return a scalar or an `(N,)` array accordingly. This is
what lets the vectorised evaluator consume `Choice` objects instead of a logit
tensor.

Backends that exist in this repository:

| backend | input | cost per decision | role |
| :--- | :--- | :--- | :--- |
| `NumericBackend` (`decision.py`, torch) | 20 features + 2×64 traces | ~2.4 ms (Python + torch) | training, ablations, any machine with torch |
| `OnnxBackend` (`decision.py`, onnxruntime, 1 thread) | same | **0.19 ms** forward, **~0.5–0.7 ms** including typed-answer assembly and decode | the number the README quotes |

There is **no** `LayaBackend` in the code. Laya appears in
`docs/PHASE0_RESEARCH_REPORT.md` as a planned text baseline; it was never wired
into the runtime, and nothing in the loop depends on it. `docs/JEV_MAPPING.md`
lists the other gaps between the Jev interface and this implementation.

### One tuning iteration

```
plant / Simulink
   │  step response (t, y, u)
   ▼
build_state ──► feats(20) + curves(2×64)
   │                    │
   │                    ▼
   │            NumericBackend / OnnxBackend
   │            one forward pass ──► 3× Choice (7 options), Score (5 bands), Noul
   │                    │
   │                    ▼
   │            decode_answer: E[Δ] with a variance-driven shrink
   │            (argmax instead, when `use_expectation=False`)
   │                    │
   │                    ▼
   │            AbstainPolicy (on by default): if the calibrated p_max is
   │            below tau_act (0.35), hold that axis — Δ = 0, gains untouched.
   │            Below tau_esc (0.25) the hold is also flagged for escalation.
   │                    │
   ▼                    │
apply_step (clip to 1e-4 … 1e3)
   ▲
   └── SafetyGate (deterministic, hand-written, **after** the fact):
       if J > max(3·best + 1, 8) and fewer than 4 rollbacks have fired:
       gains ← 0.6 · best_gains, and the iteration ends without a proposal.
       `noul` is advice; this rule is the veto.
```

The order matters: abstention is *a priori* (the plant is never touched with a
step the model is unsure about), the gate is *a posteriori* (it reacts to a
measurement). `docs/ABSTENTION.md` measures what the first buys and
`docs/ABLATION.md` shows the second never fired on the held-out family.

A one-step lookahead value net (`ValueNet`, `model.py`) exists and is
**disabled by default**: it was trained on single-axis probes but arbitrates
combined multi-axis steps, and measured worse on held-out plants (p90 1.04 →
2.89). `use_value_filter=True` re-enables it; `docs/STEP1_RESULTS.md` records the
measurement.

`interval_refine` (`decode.py`) is implemented and unit-tested but **not on the
runtime path**. It was the intended NumericJev-style refinement stage; once the
expected-value decode landed it added nothing measurable, so it is kept as a
documented alternative rather than being presented as active.

### State (20 features)

Response descriptors a human tuner would use, all scale-free:
overshoot, rise/90-10, settling, steady-state error, log IAE, log ITAE,
oscillation count, saturation fraction, worst overdrive, peak output,
current gains relative to Z-N, **the previous action** (Δlog Kp/Ki/Kd),
**the cost change it produced**, iteration fraction, `Ku/Kp`, `Tu/h`.

The previous-action pair is what turns an open-loop mapping into a closed-loop
search: without it the head cannot tell "gain too high" from "gain too high and
already reduced".

`Ku` and `Tu` are privileged information in the Python benchmark
(`plants.ultimate_gain` computes them analytically). On a real installation they
come from a Kp sweep (`plants.estimate_ultimate_gain`, 7 experiments) or a relay
test; `scripts/03_evaluate.py` reports both an oracle-Ku row and a row that pays
for the sweep.

### Decoders

| decoder | when | why |
| :--- | :--- | :--- |
| multiplicative `choice` | always | bounded, interpretable, matches how a tuner thinks |
| expected value + variance shrink | always | continuous step while staying inside the `choice` format; variance = trust region |
| argmax | ablation only (`use_expectation=False`) | the pure-discrete control |
| explicit abstention (`AbstainPolicy`) | on by default, `p_max < 0.35` | do not touch the plant when unsure; measured in `docs/ABSTENTION.md` |
| `score` band + `noul` threshold | **off by default** | it quits about halfway through the budget and costs 0.19 median (`docs/ABLATION.md`) |

The early-stop predicate used to test the **worst** band (`argmax == 4`), so it
never fired; that was fixed in 0.4.0, measured, and then turned off because the
fixed version makes the result worse.

### What is PID-specific and what is not

This is the split that matters if you want to borrow the architecture
(`docs/TRANSFER.md` has the long version):

| domain-agnostic shell | PID testbed |
| :--- | :--- |
| `decision.py` (question registry, backend protocol, temperature) | `state.py` (20 response features) |
| `primitives.py` (Choice / Score / Noul) | `metrics.py` (the cost) |
| `decode.py` (expectation, shrink, abstention) | `plants.py` (the zoo, Ku/Tu) |
| `evaluate.py` (budget, gate, trace) | `expert.py` (the coordinate line search) |
| `c/jev_head.c` (forward + decode + gate) | the 7-multiplier gain vocabulary |

### Training data

The expert is a coordinate line search over the action vocabulary, not a person
and not CMA-ES:

1. sample a plant zoo (six families, delays tied to the dominant time constant);
2. start at Z-N, and at each step evaluate **every action the decoder can emit**
   — 3 axes × 7 multipliers = 21 single-axis probes — plus one combined probe;
3. the combined probe becomes the next state, so a 20-step trajectory costs
   20 × 22 + 1 = 441 simulations per plant;
4. record (state, the 21 candidate actions and their costs, the best one per
   axis, whether the combined step stayed healthy, the current cost band).

The value net is trained on the same rollout: `(state, action) -> cost`.

### Fairness rules for the benchmark

* identical cost function and identical experiment budget for every method
  (`--budget`, default 20 per plant, including the initial and final runs);
* every method starts from the same Z-N point;
* target = 1.05 × a strong CMA-ES reference (240 simulations/plant), which is
  also reported as a row at the common budget;
* the head's training cost is paid once off-line and is **not** in its per-plant
  budget — the asymmetry is stated in the README, not hidden;
* `two_mass`, the only held-out family, was also used for design decisions
  (it is where the value net was rejected), so it is a **validation** family,
  not a clean test set. `docs/BENCHMARK.md` records this.

---

## 简体中文

### 契约

本项目中的每一次决策都是三个 Jev 原语之一，由后端接收"状态 + 问题集合"后返回。
**没有"直接回归增益"的通道**——这正是本项目要验证的对照点。

```python
# src/jev_tune/decision.py
class DecisionBackend(Protocol):
    def answer(self, feats, curves, questions: Sequence[Question] | None = None) -> Answer: ...
```

* `Choice(question, options, probs)`：K 选一，每个选项带概率
* `Score(question, levels, dist)`：有序分档判断
* `Noul(statement, p_true)`：校准的是/否

原语支持批量：`probs` 单状态是 `(K,)`，整个回路是 `(N,K)`，方法相应返回标量或
`(N,)` 数组。正是这一点让向量化的评测循环消费 `Choice` 对象，而不是裸 logit 张量。

仓库里真实存在的后端：

| 后端 | 输入 | 单次决策成本 | 角色 |
| :--- | :--- | :--- | :--- |
| `NumericBackend`（`decision.py`，torch） | 20 特征 + 2×64 曲线 | 约 2.4 ms（Python + torch） | 训练、消融、任何装了 torch 的机器 |
| `OnnxBackend`（`decision.py`，onnxruntime 单线程） | 同上 | 前向 **0.19 ms**；含类型化答案组装与解码 **约 0.5–0.7 ms** | README 引用的数字 |

代码里**没有** `LayaBackend`。Laya 只出现在 `docs/PHASE0_RESEARCH_REPORT.md`
的计划里，从未接进运行时，回路也不依赖它。其余"Jev 接口 vs 本实现"的差距列在
`docs/JEV_MAPPING.md`。

### 一次调参迭代

```
被控对象 / Simulink
   │  阶跃响应 (t, y, u)
   ▼
build_state ──► feats(20) + curves(2×64)
   │                    │
   │                    ▼
   │            NumericBackend / OnnxBackend
   │            一次前向 ──► 3× Choice（7 档）、Score（5 档）、Noul
   │                    │
   │                    ▼
   │            decode_answer：E[Δ] + 方差缩步
   │            （`use_expectation=False` 时退化为 argmax）
   │                    │
   │                    ▼
   │            AbstainPolicy（默认开启）：校准后 p_max 低于 tau_act（0.35）
   │            时该轴保持——Δ = 0，增益不动；低于 tau_esc（0.25）再打升级标记。
   │                    │
   ▼                    │
apply_step（裁剪到 1e-4 … 1e3）
   ▲
   └── SafetyGate（确定性、手写规则，**事后**）：
       若 J > max(3·best + 1, 8) 且回滚次数 < 4：
       gains ← 0.6 · best_gains，本次迭代不再提提案。
       `noul` 只是建议，这条规则才是否决权。
```

顺序很重要：弃权是**事前**的（模型没把握时根本不碰对象），闸门是**事后**的（对测量
结果作出反应）。前者买到什么测在 `docs/ABSTENTION.md`，后者在留出族上从未触发的
证据在 `docs/ABLATION.md`。

一步前瞻价值网（`ValueNet`，`model.py`）存在但**默认关闭**：它用单轴探针训练，
却要裁决多轴组合步，在留出对象上实测更差（p90 1.04 → 2.89）。`use_value_filter=True`
可重新启用；测量记录在 `docs/STEP1_RESULTS.md`。

`interval_refine`（`decode.py`）实现并有单元测试，但**不在运行路径上**。它原本是
NumericJev 式的区间细化阶段；期望值解码落地后实测没有增益，因此保留为有文档的
备选，而不是包装成"在用"。

### 状态（20 个特征）

人类调参时会看的那些量，全部无量纲化：超调、上升（90-10）、调节时间、稳态误差、
log IAE、log ITAE、振荡次数、饱和占比、最大过冲、峰值输出、当前增益相对 Z-N 的
比值、**上一步动作**（Δlog Kp/Ki/Kd）、**它带来的代价变化**、迭代进度、
`Ku/Kp`、`Tu/h`。

"上一步动作 + 结果"这一对，是把开环映射变成闭环搜索的关键：没有它，模型分不清
"增益太大"和"增益太大但已经在减"。

`Ku`、`Tu` 在 Python 基准里是特权信息（`plants.ultimate_gain` 解析计算）。真实部署
要靠 Kp 扫描（`plants.estimate_ultimate_gain`，7 次实验）或继电实验测得；
`scripts/03_evaluate.py` 同时给出"解析 Ku"和"为扫描付费"两行。

### 解码器

| 解码器 | 何时用 | 为什么 |
| :--- | :--- | :--- |
| 乘法 `choice` | 始终 | 有界、可解释，符合调参者的思维方式 |
| 期望值 + 方差缩步 | 始终 | 在 `choice` 格式内拿到连续步长；方差即信赖域半径 |
| argmax | 仅消融（`use_expectation=False`） | 纯离散对照 |
| 显式弃权（`AbstainPolicy`） | 默认开启，`p_max < 0.35` | 没把握时不动对象；测在 `docs/ABSTENTION.md` |
| `score` 档 + `noul` 阈值早停 | **默认关闭** | 会在预算中途就停，代价中位差 0.19（`docs/ABLATION.md`） |

早停判据过去判的是**最差**档（`argmax == 4`），因此从未触发；0.4.0 修正后实测发现
修好的版本反而更差，于是默认关闭。

### 哪些是 PID 专用、哪些不是

想借用这套架构时，这个划分最重要（长版在 `docs/TRANSFER.md`）：

| 领域无关的决策外壳 | PID 试验场 |
| :--- | :--- |
| `decision.py`（问题注册表、后端协议、温度） | `state.py`（20 个响应特征） |
| `primitives.py`（Choice / Score / Noul） | `metrics.py`（代价函数） |
| `decode.py`（期望、缩步、弃权） | `plants.py`（动物园、Ku/Tu） |
| `evaluate.py`（预算、闸门、轨迹记录） | `expert.py`（坐标线搜索） |
| `c/jev_head.c`（前向 + 解码 + 闸门） | 7 档乘法增益词表 |

### 训练数据

专家是对动作词表的坐标线搜索，不是人、也不是 CMA-ES：

1. 采样植物动物园（6 族，延迟与主时间常数挂钩）；
2. 从 Z-N 出发，每一步评估**解码器能发出的全部动作**——3 轴 × 7 档 = 21 个
   单轴探针——再加 1 个组合探针；
3. 组合探针即下一个状态，因此 20 步轨迹每株要 20 × 22 + 1 = 441 次仿真；
4. 记录（状态、21 个候选动作及其代价、每轴最优、组合步是否健康、当前代价档）。

价值网用同一批轨迹训练 `(state, action) -> cost`。

### 基准的公平性规则

* 同一代价函数、同一实验预算（`--budget`，默认每株 20 次，含首末两次测量）；
* 所有方法从同一个 Z-N 点出发；
* 目标 = 1.05 × 强 CMA-ES 参考（240 次仿真/对象），该参考本身也以同预算列一行；
* 决策头的训练成本一次性离线支付，**不计入**每株预算——这一不对称写在 README 里，
  不藏在脚注；
* 唯一留出族 `two_mass` 也参与过设计决策（价值网就是在它上面被否掉的），所以它是
  **验证族**，不是干净测试集。记录见 `docs/BENCHMARK.md`。
