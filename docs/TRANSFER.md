# Transferring the architecture — module map, porting questions, boundaries

> [English](#english) · [简体中文](#简体中文)

## English

### 1. What this document is

`jev-tune` is an **engineering reference architecture**: a typed, calibrated,
bounded decision loop that runs on a small CPU model and is wrapped in a
deterministic safety rule. **PID autotuning is its first testbed**, not its
subject matter. This page separates the parts that are independent of PID from
the parts that are not, so that someone working on a different closed loop can
see exactly what they would reuse and what they would have to replace.

It is a map, not a claim of applicability. **Nothing in this repository has been
evaluated on a visual policy, a robot, a human subject or a medical device.**

### 2. Domain-general shell vs PID-specific testbed

| module | where | domain-general? | what a port must replace |
| :--- | :--- | :--- | :--- |
| `Question` registry + `DecisionBackend.answer()` | `src/jev_tune/decision.py` | **yes** | question ids and their option labels |
| `Choice` / `Score` / `Noul` primitives (batched) | `src/jev_tune/primitives.py` | **yes** | option payloads (`delta` becomes whatever the option means) |
| temperature calibration from `calibration.json` | `decision.py`, `scripts/02_train.py` | **yes** | refit on your data; the file format is reusable |
| expected-value decode + variance shrink | `decode.py::decode_answer` | **yes** | the meaning of "variance shrink" (it is a trust region, not a probability of success) |
| deterministic rollback gate | `evaluate.py::evaluate_head`, `matlab/jev_tune_model.m` | **yes, as a pattern** | the threshold (`J > 3·best + 1`), and the action (`0.6·best`) |
| budget/accounting harness | `evaluate.py`, `scripts/03_evaluate.py` | **yes** | the definition of "one experiment" |
| 20 features (`build_state`) and 2×64 traces | `src/jev_tune/state.py`, `c/jev_head.c` | **no** | the entire feature set |
| cost function (overshoot, rise, settling, ITAE, saturation) | `src/jev_tune/metrics.py` | **no** | the objective |
| Ku/Tu features and the Kp sweep | `plants.py`, `jev_tune_model.m` | **no** | domain-specific plant identification |
| multiplicative gain vocabulary | `decode.py::DEFAULT_MULTIPLIERS` | **no** | the action vocabulary |
| PID expert (coordinate line search) | `src/jev_tune/expert.py` | **no** | the label source |

The reusable claim is narrow and worth stating precisely: **a bounded typed
answer with a probability, decoded by expectation, shrunk by its own variance,
and vetoed by a rule that does not consult the model** is a composable pattern
with a measurable cost (about 0.2 ms of forward pass, 0.5–0.7 ms for a complete
typed decision) and a documented ablation (`docs/ABLATION.md`).

### 3. If you are working on VLA / hierarchical robot control

**The shape that might transfer.** A perception or planning model proposes
something; a small typed head sits between it and the actuator, answers a fixed
set of questions about the *current* state and the *proposed* action, and a
deterministic envelope checker holds or vetoes. The head never generates text and
never sees the whole observation stream — it sees a small feature vector and
answers in one forward pass.

| this repo | VLA / hierarchical-control analogue |
| :--- | :--- |
| 20 response features | risk descriptors: tracking error, saturation, jerk, clearance, collision margin, out-of-distribution score |
| 3×7 multiplicative gain steps | bounded fallback options: `hold`, `slow to x`, `retreat along the last safe direction`, `hand control back` |
| `choice` per axis | `choice` over the fallback set |
| `score` (5 cost bands) | `score` of scene/task risk |
| `noul` ("will this step keep the loop healthy") | `noul` ("is this action inside the verified envelope") |
| deterministic gate | the envelope checker the runtime already has — keep it, and keep it outside the model |
| 20-experiment budget | one episode is one experiment; labels come from replay, simulation or teleoperation |

Questions to answer **before** reusing anything here:

1. Can the fallback action be enumerated and bounded? If the safe action is a
   continuous trajectory, this pattern does not apply without a new vocabulary.
2. Can you obtain a **single-step outcome label** without putting the robot in
   the state you are trying to avoid? If not, the expert data has to come from
   simulation or from an offline replay buffer, and distribution shift becomes
   the dominant risk.
3. Is the decision allowed to be wrong at 0.5 ms latency, or does the envelope
   checker have to be the last line of defence? (Here it is; it must be there
   too.)
4. What is the base rate of "hold" in your data? A head trained on mostly-hold
   labels learns to hold, which is safe and useless.
5. Who is accountable when the veto fires and the task fails?

What this repository **does not** provide for VLA: any visual encoder, any
evaluation on a manipulation or navigation task, any latency measurement with a
perception stack in the loop, any claim about sim-to-real transfer.

Related entry points (not part of this repo's evidence): the Simplex
architecture (Seto, Krogh, Sha & Chutinan, ACC 1998), shielding for learned
policies (Alshiekh et al., AAAI 2018), selective prediction (Geifman &
El-Yaniv, NeurIPS 2017).

### 4. If you are working on closed-loop stimulation / neuromodulation

**The shape that might transfer.** A state scorer answers "how far is this
window from the target regime", a bounded parameter chooser proposes the next
step, `noul` answers "is this step inside the pre-approved envelope", and a
deterministic limiter — implemented in hardware or in the clinical stack, not in
the model — enforces amplitude, charge, duration and rate limits.

| this repo | constrained-parameter analogue |
| :--- | :--- |
| 20 response features | windowed state descriptors: band power ratios, evoked-response amplitude, artifact flags, impedance, drift |
| multiplicative gain steps | bounded parameter steps with clinical minima/maxima and a hard rate limit |
| `score` of the response | distance from the therapeutic window (ordered bands defined by a clinician) |
| `noul` | "the proposed step stays inside the approved envelope" |
| rollback to `0.6·best` | revert to the last approved parameter set, then require re-approval |
| safety gate | the hard limiter and the watchdog — **outside the model** |
| 20-experiment budget | depends on the protocol; never explore on a subject |

Questions to answer **before** reusing anything here:

1. **Where do single-step labels come from** without exposing a subject to a
   harmful candidate? If the answer is "a biophysical model" or "a retrospective
   cohort", say so explicitly and treat the distribution shift as the main risk.
2. Is the action space bounded by a **hard, external** limiter that the model
   cannot exceed even if it is wrong? If the model is the limiter, stop.
3. Is the objective a single scalar, or a constrained multi-objective problem
   (efficacy versus side-effect load)? This repo optimises one scalar cost; a
   constrained formulation is a different decoder.
4. What is the fallback when the state estimate is out of distribution? The
   `noul` head here is trained on synthetic "healthy" labels; it has no notion of
   a clinical escalation.
5. Who signs off on the escalation rule, and how is it audited?
6. Which artifacts are logged for post-hoc review — every answer, its
   probabilities, the temperature used, and the gate decision?

What this repository **does not** provide for neuromodulation: any physiological
data, any clinical protocol, any safety analysis, any regulatory work. The
non-clinical statement in §6 is not boilerplate.

Related entry points (not part of this repo's evidence): runtime assurance and
Simplex; calibrated abstention; conformal risk control (Angelopoulos et al.,
arXiv:2208.02814) if you want a threshold with a distribution-free guarantee
under an exchangeability assumption you must argue for.

### 4b. Hardware-level checklist, before anything above leaves a simulation

These four items are the ones this repository cannot implement for you, because
they live in the sensor front end and the actuator driver, not in the model.
They are written for closed-loop stimulation and robot hardware; the first one
applies to any deployment.

* **Pre-inference signal sanity (SQI).** The hardware must independently reject
  sensor saturation, disconnection (NaN or a frozen constant), and dropped
  packets *before* the features reach the model. A softmax over out-of-
  distribution inputs can be confidently wrong: high `p_max` here means "the
  network is sure", not "the signal is valid". Rejecting at the source is the
  only defence that does not depend on the model being right.
* **Multi-step abstention decay.** One low-confidence step may `hold` (keep the
  last parameters). But if `N` consecutive steps abstain, or `noul` alarms `N`
  times in a row, the outer state machine must **smoothly decay to a safe
  baseline** instead of holding a high-power output indefinitely. "Hold" is
  safe for a PID; it is not automatically safe for a stimulator or an actuator
  that is holding a load.
* **Actuation cooldown and hysteresis.** For stimulation artefacts or mechanical
  resonance, put a minimum refractory period and a deadband in the outer
  actuator. Without them, a decision at the threshold boundary will chatter at
  the loop rate, which is both a wear problem and an artefact source.
* **Asymmetric risk and DAC quantisation.** Fold in the hardware's minimum DAC
  step and an asymmetric safety cost (e.g. increasing stimulation is more
  dangerous than decreasing it). That means different shrink coefficients for
  positive and negative steps; the symmetric `1/(1+Var/var_ref)` used here is a
  default, not a recommendation for asymmetric risk.

### 5. Preconditions checklist (any domain)

If most of these are false, this architecture is probably the wrong tool.

1. The action can be discretised into a small, bounded, **ordered** set.
2. One step's outcome can be measured before the next decision, cheaply enough
   that spending an experiment is acceptable.
3. There is a resettable environment or a label source that does not require
   harming the thing you are controlling.
4. There is a cheap, monotone cost you are willing to optimise.
5. The calibration set and the deployment distribution are approximately
   exchangeable; otherwise the temperatures and any threshold are decoration.
6. Hard limits, watchdogs and interlocks live **outside** the model.

### 6. Non-clinical, non-safety-critical statement

This is research software. It has not been certified, verified or validated for
medical devices, human subjects, vehicles, industrial interlocks or any other
safety-critical application, and it must not be used to make decisions in those
settings. Nothing in this repository is medical advice or a clinical protocol.
If you intend to borrow the pattern in such a setting, the validation,
regulatory and ethical work is yours; §3–§5 are the minimum set of questions to
answer first.

### 7. Known failures and limits of this repository

* Out of distribution it fails: dead band, inverse response and open-loop
  unstable plants (`docs/GENERALIZATION.md`).
* Fine-tuning sometimes makes things worse (`docs/SPECIALIZE.md`).
* On the one real Simulink model, after the Ku sweep was corrected, the tuner
  returns the lab's own gains rather than improving on them
  (`docs/STEP4_RESULTS.md`).
* Labels need a resettable simulator: 22 simulations per expert state.
* The only held-out family was also used for design decisions
  (`docs/BENCHMARK.md`).
* The typed interface's advantage over a same-size regression head is measured
  in `docs/ABLATION.md`; read the number there, not the adjectives here.

### 8. How to cite

Cite the versioned release, not the default branch (`CITATION.cff`). The right
object to cite is *"an open testbed and reference implementation with its
measured evidence"*, not *"a validated method"*. If a number here disagrees with
`research/results/*.json`, the artifact wins.

---

## 简体中文

### 1. 这份文档是什么

`jev-tune` 是一套**工程参考架构**：一个类型化、带校准、有界的决策回路，跑在很小的
CPU 模型上，外面包一条确定性的安全规则。**PID 自动整定是它的第一个试验场，不是它
的主题。** 本页把"与 PID 无关的部分"和"PID 专用件"分开写清楚，让做其他闭环的人
能直接看到：什么是可以复用的，什么是必须替换的。

它是地图，不是适用性声明。**本仓库没有在视觉策略、机器人、人体受试或医疗器械上
做过任何评估。**

### 2. 通用外壳 vs PID 试验场

| 模块 | 位置 | 是否通用 | 移植时要替换什么 |
| :--- | :--- | :--- | :--- |
| `Question` 注册表 + `DecisionBackend.answer()` | `src/jev_tune/decision.py` | **通用** | 问题 id 与选项标签 |
| `Choice` / `Score` / `Noul` 原语（支持批量） | `src/jev_tune/primitives.py` | **通用** | 选项载荷（`delta` 换成你的选项含义） |
| 从 `calibration.json` 读温度并应用 | `decision.py`、`scripts/02_train.py` | **通用** | 在你的数据上重新拟合；文件格式可沿用 |
| 期望值解码 + 方差缩步 | `decode.py::decode_answer` | **通用** | "方差缩步"的含义（它是信赖域，不是成功概率） |
| 确定性回滚闸门 | `evaluate.py::evaluate_head`、`matlab/jev_tune_model.m` | **通用（作为模式）** | 阈值（`J > 3·best + 1`）与动作（`0.6·best`） |
| 预算与记账框架 | `evaluate.py`、`scripts/03_evaluate.py` | **通用** | "一次实验"的定义 |
| 20 个特征与 2×64 曲线 | `src/jev_tune/state.py`、`c/jev_head.c` | **否** | 整套特征 |
| 代价函数（超调、上升、调节、ITAE、饱和） | `src/jev_tune/metrics.py` | **否** | 目标函数 |
| Ku/Tu 特征与 Kp 扫描 | `plants.py`、`jev_tune_model.m` | **否** | 领域专用的对象辨识 |
| 乘法增益词表 | `decode.py::DEFAULT_MULTIPLIERS` | **否** | 动作词表 |
| PID 专家（坐标线搜索） | `src/jev_tune/expert.py` | **否** | 标签来源 |

可复用的主张很窄，值得说准：**一个带概率的有界类型化答案，用期望值解码、用它自己
的方差收缩、再由一条不看模型的规则否决**，是可组合的模式；它的成本可测（前向约
0.2 ms，含类型化答案组装约 0.5–0.7 ms），消融记录在 `docs/ABLATION.md`。

### 3. 如果你做的是 VLA / 分层机器人控制

**可能迁移的形状。** 感知或规划模型提出动作；一个小的类型化决策头夹在它和执行器
之间，对*当前状态*和*候选动作*回答一组固定问题；再由确定性包络检查器保持或否决。
决策头不生成文本，也不看完整观测流——它只看一个小特征向量，一次前向作答。

| 本仓库 | VLA / 分层控制中的对应物 |
| :--- | :--- |
| 20 个响应特征 | 风险描述子：跟踪误差、饱和、加加速度、间隙、碰撞余量、分布外评分 |
| 3×7 乘法增益步 | 有界回退选项：`保持`、`降速到 x`、`沿最近安全方向后退`、`交还控制权` |
| 每轴 `choice` | 回退集合上的 `choice` |
| `score`（5 个代价档） | 场景/任务风险评分 |
| `noul`（"这一步能否保持闭环健康"） | `noul`（"该动作是否在已验证包络内"） |
| 确定性闸门 | 运行时已有的包络检查器——保留它，并留在模型之外 |
| 20 次实验预算 | 一个 episode 就是一次实验；标签来自回放、仿真或遥操作 |

复用前必须先回答的问题：

1. 回退动作能否枚举并有界？如果"安全动作"是连续轨迹，这套模式在不新建词表的前提下
   不适用。
2. 能否在**不把机器人带入你想避免的状态**的前提下拿到单步结果标签？不能的话，专家
   数据只能来自仿真或离线回放，分布漂移会成为主要风险。
3. 决策在 0.5 ms 内允许出错，还是必须由包络检查器兜底？这里就是兜底的；那边也必须
   如此。
4. 你的数据里"保持"的基率是多少？大部分标签都是"保持"时，训练出来的头只会保持——
   安全但没用。
5. 否决触发、任务失败时，谁负责？

本仓库**不提供**任何视觉编码器、任何操作/导航任务上的评估、任何含感知栈的端到端
延迟测量，也不对 sim-to-real 迁移作任何声明。

相关入口（不属于本仓库证据）：Simplex 架构（Seto, Krogh, Sha & Chutinan, ACC
1998）、学习策略护盾（Alshiekh et al., AAAI 2018）、选择性预测（Geifman &
El-Yaniv, NeurIPS 2017）。

### 4. 如果你做的是闭环刺激 / 神经调控

**可能迁移的形状。** 状态评分器回答"当前窗口离目标状态有多远"，有界参数选择器提出
下一步，`noul` 回答"这一步是否在预先批准的包络内"，确定性限幅器——由硬件或临床栈
实现，不在模型里——执行幅值、电荷、时长与速率上限。

| 本仓库 | 受约束参数调节中的对应物 |
| :--- | :--- |
| 20 个响应特征 | 窗口化状态描述子：频带功率比、诱发响应幅值、伪迹标记、阻抗、漂移 |
| 乘法增益步 | 有临床上下限与硬速率限制的有界参数步 |
| 响应 `score` | 离治疗窗口的距离（由临床医生定义的有序档） |
| `noul` | "提案是否仍在已批准包络内" |
| 回滚到 `0.6·best` | 退回上一次批准的参数组，然后要求重新批准 |
| 安全闸门 | 硬限幅器与看门狗——**在模型之外** |
| 20 次实验预算 | 取决于方案；**绝不在受试者身上探索** |

复用前必须先回答的问题：

1. **单步标签从哪来**，且不需要让受试者接触有害候选？如果答案是"生物物理模型"或
   "回顾性队列"，请写明，并把分布漂移当作主要风险。
2. 动作空间是否由**外部硬限幅**约束，即使模型错了也越不过去？如果模型本身就是限幅器，
   立刻停止。
3. 目标是单个标量，还是带约束的多目标（疗效 vs 副作用负荷）？本仓库优化单个标量代价；
   带约束的表述是另一种解码器。
4. 状态估计分布外时怎么办？这里的 `noul` 用合成"健康"标签训练，它没有临床升级的
   概念。
5. 升级规则由谁批准、如何审计？
6. 事后复核要留哪些记录——每个答案、它的概率、用的温度、闸门决策？

本仓库**不提供**任何生理数据、临床方案、安全分析或法规工作。§6 的非临床声明不是
套话。

相关入口（不属于本仓库证据）：运行时保证 / Simplex；校准弃权；conformal 风险控制
（Angelopoulos et al., arXiv:2208.02814）——如果你想要带分布无关保证的阈值，前提是
你得先论证"可交换"成立。

### 4b. 硬件层清单（在把上面任何东西搬出仿真之前）

下面四条本仓库无法替你实现，因为它们住在传感器前端和执行器驱动里，不在模型里。
它们是按闭环刺激与机器人硬件写的；第一条对任何部署都适用。

* **推理前信号合法性（SQI）。** 硬件端必须在特征进入模型**之前**独立拦截传感器饱和、
  掉线（NaN 或常数卡死）与通信丢包。分布外输入经过 softmax 可以"自信地错"：这里的
  高 `p_max` 只代表"网络很确定"，不代表"信号有效"。在源头拒绝，是唯一不依赖模型
  正确性的防线。
* **多步弃权衰减。** 单步低把握度可以 `hold`（保持上一组参数）；但若连续 `N` 步弃权，
  或 `noul` 连续告警 `N` 次，外层状态机应**平滑衰减到安全基线**，而不是无限维持高功率
  输出。对 PID 来说"保持"是安全的；对刺激器或带载执行器，保持未必安全。
* **执行冷却与迟滞。** 针对刺激伪迹或机械谐振，在外层执行器加入最小不应期与死区。
  没有它们，阈值边界上的决策会按回路频率抖振——既是磨损问题，也是伪迹来源。
* **非对称风险与 DAC 量化。** 把硬件 DAC 的最小步进和非对称安全代价（例如上调刺激
  强度比下调更危险）算进去。这意味着正向与负向缩步系数应当不同；这里的对称
  `1/(1+Var/var_ref)` 只是默认值，不是非对称风险下的推荐值。

### 5. 移植前提清单（任何领域）

以下多数为假时，这套架构多半不是合适的工具。

1. 动作能离散化成一个小、有界、**有序**的集合。
2. 单步结果能在下一次决策前测到，且代价低到值得花一次实验。
3. 有可重置的环境，或不需要伤害被控对象就能获得的标签来源。
4. 有一个廉价、单调、你愿意优化的代价函数。
5. 校准集与部署分布近似可交换，否则温度与任何阈值都是装饰。
6. 硬限幅、看门狗、联锁都在**模型之外**。

### 6. 非临床、非安全关键声明

这是研究软件，未针对医疗器械、人体受试、车辆、工业联锁或其他安全关键应用做过认证、
验证或确认，**不得**用于这些场景中的决策。本仓库的任何内容都不是医疗建议或临床方案。
若要在这些场景借鉴这套模式，验证、合规与伦理工作由你完成；§3–§5 是最低限度要先
回答的问题。

### 7. 本仓库已知的失败与局限

* 分布外会失败：死区、反向响应、开环不稳定对象（`docs/GENERALIZATION.md`）。
* 微调有时变差（`docs/SPECIALIZE.md`）。
* 唯一测过的真实 Simulink 模型上，Ku 扫描修正后返回的是实验室自己的增益，而不是改进
  （`docs/STEP4_RESULTS.md`）。
* 标签需要可重置的仿真器：每个专家状态 22 次仿真。
* 唯一留出族也参与过设计决策（`docs/BENCHMARK.md`）。
* 类型化接口相对同尺寸回归头的优势实测在 `docs/ABLATION.md`；请读那里的数字，不要读
  形容词。

### 8. 如何引用

引用带版本号的发布，不要引默认分支（`CITATION.cff`）。合适的引用对象是"一个开源
测试床与参考实现，附带实测证据"，而不是"一个已被验证的方法"。若本页与
`research/results/*.json` 冲突，以文件为准。
