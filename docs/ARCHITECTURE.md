# Architecture

> [English](#architecture) · [简体中文](#架构中文)


## Contract

Every decision in this project is one of three Jev primitives. There is no
"regress the gain" path — that is the whole point of the experiment.

```python
class DecisionBackend(Protocol):
    def decide(self, state: State, questions: list[Question]) -> dict[str, Answer]: ...
```

* `Choice(question, options, probs)` — pick one of K, with a probability per option
* `Score(question, levels, dist)` — ordered rubric judgement
* `Noul(statement, p_true)` — calibrated yes/no, i.e. the safety primitive

Backends:

| backend | input | cost per decision | role |
| :--- | :--- | :--- | :--- |
| `NumericHead` (this repo) | 20 features + 2×64 traces | **< 1 ms** (ONNX, CPU) | runtime |
| `LayaBackend` (optional) | JSON state rendered as text | 40–90 ms (INT8, ≤120 tokens) | zero-shot baseline, teacher, text states |

## One tuning iteration

```
plant / Simulink
   │  step response (t, y, u)
   ▼
FeatureExtractor ──► State(20) + traces(2×64)
   │                    │
   │                    ▼
   │              DecisionHead ──► choice×3, score, noul
   │                    │
   │                    ▼
   │            ValueNet (1-step lookahead)
   │             top-2×2×2 candidate actions → pick lowest predicted cost
   │                    │
   │                    ▼
   │            decode: E[Δ] with Var-driven trust region
   ▼                    │
accept new gains ◄──────┘
   ▲
   └── SafetyGate (deterministic): |Δlog K| ≤ 0.2, gain box, divergence
       rollback, saturation veto. `noul` is advice, never the final word.
```

## State (20 features)

Response descriptors a human tuner would use, all scale-free:
overshoot, rise/90-10, settling, steady-state error, log IAE, log ITAE,
oscillation count, saturation fraction, worst overdrive, peak output,
current gains relative to Z-N, **the previous action** (Δlog Kp/Ki/Kd),
**the cost change it produced**, iteration fraction, `Ku/Kp`, `Tu/h`.

The previous-action pair is what turns an open-loop mapping into a closed-loop
search: without it the head cannot tell "gain too high" from "gain too high and
already reduced".

## Why these decoders

| decoder | when | why |
| :--- | :--- | :--- |
| multiplicative `choice` | always | bounded, interpretable, matches how a tuner thinks |
| expected value + variance gate | always | continuous step while staying inside the `choice` format; variance = trust region |
| NumericJev interval refinement (K=3) | final ±10 % | exact resolution without the "wrong interval is unrecoverable" failure mode early on |
| `score` threshold | every iteration | calibrated early stop — saves iterations, which dominates wall-clock |

## Training data

The expert is a batched CMA-ES, not a person:

1. sample a plant zoo (5 families, delays tied to the dominant time constant),
2. start at Z-N, walk a gain trajectory,
3. at each step record (state, 8 candidate actions and their costs, the best one,
   whether it stayed healthy, the current cost bucket).

The value net is trained on the same rollout: `(state, action) -> cost`, which is
what lets the head filter its own proposals before spending a simulation.

## Fairness rules for the benchmark

* identical cost function, identical simulation budget accounting
* every method starts from the same Z-N point
* target = 1.05 × a strong CMA-ES reference (240 simulations/plant)
* held-out evaluation uses plants the training zoo never contained

---

## 架构（中文）

### 契约

本项目中的每一次决策都是三个原语之一，**没有"直接回归增益"的通道**——这正是本
项目要验证的对照点。

```python
class DecisionBackend(Protocol):
    def decide(self, state: State, questions: list[Question]) -> dict[str, Answer]: ...
```

* `Choice(question, options, probs)`：K 选一，每个选项带概率
* `Score(question, levels, dist)`：有序分档判断
* `Noul(statement, p_true)`：校准的是/否，即安全原语

后端：

| 后端 | 输入 | 单次成本 | 角色 |
| :--- | :--- | :--- | :--- |
| `NumericHead`（本仓库） | 20 特征 + 2×64 曲线 | **< 1 ms**（ONNX，CPU） | 运行时 |
| `LayaBackend`（可选） | JSON 状态渲染成文本 | 40–90 ms（INT8，≤120 token） | 零样本基线 / 教师 / 文本状态 |

### 一次调参迭代

```
被控对象 / Simulink
   │  阶跃响应 (t, y, u)
   ▼
特征提取 ──► State(20) + traces(2×64)
   │                    │
   │                    ▼
   │              DecisionHead ──► choice×3, score, noul
   │                    │
   │                    ▼
   │            ValueNet（一步前瞻）
   │             每轴 top-2×2×2 候选 → 选预测代价最低的
   │                    │
   │                    ▼
   │            解码：E[Δ] + 由方差驱动的信赖域
   ▼                    │
接受新增益 ◄────────────┘
   ▲
   └── SafetyGate（确定性）：|Δlog K| ≤ 0.2、增益边界、发散回滚、
       饱和否决。`noul` 只是建议，永远不是最终裁决。
```

### 状态（20 个特征）

人类调参时会看的那些量，全部无量纲化：超调、上升（90-10）、调节时间、稳态误差、
log IAE、log ITAE、振荡次数、饱和占比、最大过冲、峰值输出、当前增益相对 Z-N 的
比值、**上一步动作**（Δlog Kp/Ki/Kd）、**它带来的代价变化**、迭代进度、
`Ku/Kp`、`Tu/h`。

"上一步动作 + 结果"这一对，是把开环映射变成闭环搜索的关键：没有它，模型分不清
"增益太大"和"增益太大但已经在减"。

### 为什么用这几个解码器

| 解码器 | 何时用 | 为什么 |
| :--- | :--- | :--- |
| 乘法 `choice` | 始终 | 有界、可解释，符合调参者的思维方式 |
| 期望值 + 方差门 | 始终 | 在 `choice` 格式内拿到连续步长；方差即信赖域半径 |
| NumericJev 区间细化（K=3） | 最后 ±10% | 拿到精确分辨率，同时避开"早期错区间不可恢复" |
| `score` 阈值 | 每次迭代 | 校准过的早停——省下的迭代次数比单次延迟更重要 |

### 训练数据

专家是批量 CMA-ES / 坐标线搜索，不是人：

1. 采样植物动物园（5–6 族，延迟与主时间常数挂钩）；
2. 从 Z-N 出发走一条增益轨迹；
3. 每一步记录（状态、8 个候选动作及其代价、最好的那个、是否保持健康、当前代价档）。

价值网用同一批轨迹训练 `(state, action) -> cost`，让决策头在花掉一次仿真之前就
能过滤自己的提案。

### 基准的公平性规则

* 同一代价函数、同一仿真预算记账；
* 所有方法从同一个 Z-N 点出发；
* 目标 = 1.05 × 强 CMA-ES 参考（240 次仿真/对象）；
* 留出评估使用训练动物园从未包含的对象。
