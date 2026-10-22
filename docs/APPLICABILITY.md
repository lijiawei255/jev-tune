> [English](#applicability-what-this-tuner-can-and-cannot-do) · [简体中文](#适用范围这个调参器能做什么不能做什么)

# Applicability: what this tuner can and cannot do

Two questions before pointing it at your loop:

1. **can it make my plant worse?**
2. **which control tasks does it actually fit?**

Both are answered with measurements, not adjectives.

---

## 1. Will it blow up my loop?

Measured over **200 plants**, all zero-shot (no per-plant training):
120 from the training zoo, 40 from an unseen family, and 40 out-of-distribution
scenarios (dead band, unstable pole, inverse response, resonance, noise…).

| population | n | cost at Z-N start | cost reached | improved | same | **worse** | worst final/start | rollbacks | diverged |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| zoo (in-distribution) | 120 | 2.341 | 1.556 | 97 % | 3 % | **0 %** | 1.00 | 0 | 0 |
| held-out family | 40 | 2.367 | 0.381 | 100 % | 0 % | **0 %** | 0.92 | 0 | 0 |
| out-of-distribution | 40 | 3.378 | 2.809 | 80 % | 20 % | **0 %** | 1.00 | 1 | 4 |

**200/200 plants end at or better than the starting point.** The four
"diverged" cases are the inverted-pendulum plants, where the *start* is already
diverged (Z-N is meaningless for an open-loop unstable plant) — the tuner
returns that same start rather than something worse.

### Why it cannot make things worse (two independent layers)

| layer | what it does | where |
| :--- | :--- | :--- |
| **structural** | every returned gain set is the best one *measured*, so the answer can never be worse than the start | `evaluate_head` / `jev_tune_model.m` (`bestGains`) |
| **safety gate** | if a step makes the cost explode (`J > max(3·best + 1, 8)`), retreat to `best × 0.6` instead of trusting the model | same files, `safety_gate` |

The gate fired **once in 200 plants** — it is a second layer, not the reason the
guarantee holds. The guarantee is that the number you get back was *measured* on
your plant before being returned.

Additional bounds that make a runaway impossible in the first place:

* one step can never change a gain by more than **×2.1** (trust region, ±0.32 in
  log10);
* gains are clamped to `[1e-4, 1e3]`;
* the model file is **copied** before loading — your `.slx` is never modified;
* Fast Restart is disabled before any close, so an unattended session cannot be
  blocked by the "exit Fast Restart?" dialog.

Reproduce: `python scripts/11_robustness.py`

---

## 2. Which control tasks fit

| task | support | what you do |
| :--- | :--- | :--- |
| **Parallel PID, three gain blocks** | ✅ out of the box | point it at the model |
| **`PID Controller` block (masked)** | ✅ configuration | `--controller pid_block --pid-block "PID Controller"` |
| PID with a **fixed** derivative filter | ✅ works | the filter time constant is not tuned, but is respected |
| PIDF where you also want to tune `Tf` | 🔶 not supported | tune `Kp/Ki/Kd` first, `Tf` by hand |
| **Series / interacting PID** | ⚠️ adapter needed | convert to parallel form, or replace `set_gains` |
| **Cascade** (position → speed → current) | ❌ not supported | tune one loop with the others fixed, sequentially |
| **MIMO / coupled loops** | ❌ not supported | run loop by loop; coupling is not modelled |
| **Step-response objective** | ✅ default | — |
| **Tracking / ramp / sinusoid** | 🔶 metrics + retrain | new features + specialist run (~2 min) |
| **Disturbance rejection** | 🔶 metrics + retrain | inject the disturbance, change the cost, specialist run |
| Dead-time dominant (L/T ≈ 2) | ✅ measured at parity | — |
| Noisy measurement (σ ≈ 1 %) | ✅ measured at parity | — |
| **Dead band / backlash** | 🔶 specialist | `--scenario valve_dead_zone`, ~2 min |
| **Inverse response (RHP zero)** | 🔶 specialist | `--scenario inverse_response`, ~2 min |
| **Open-loop unstable plant** | ❌ not solved | needs a stabilising start; the specialist cannot fix a meaningless Z-N |
| Fixed-step / discrete models | ✅ works | features are normalised by the horizon |
| Models without Scope blocks | ⚠️ small edit | add `To Workspace`, or export the signal |
| **Real hardware / HIL** | ❌ not supported | no Fast Restart; needs a different bridge |
| Non-PID controllers (LQR, MPC, gain scheduling) | 🔶 interface reusable | the head/decoder are separable from the controller adapter |

Legend: ✅ works as shipped · 🔶 works with a documented extra step ·
⚠️ needs a small code change · ❌ outside the current design.

---

## 3. How much work to adapt (honest estimate)

| you want to… | change | effort |
| :--- | :--- | :--- |
| point it at your Simulink model | rename or pass 5 block names | minutes |
| use a `PID Controller` block | one flag | minutes |
| add a plant family it has never seen | add a sampler in `plants.py`, regenerate the dataset, retrain | ~40 min CPU |
| fix a specific out-of-distribution plant | `10_specialize.py` | ~2 min CPU |
| change the objective (tracking, disturbance) | new metrics in `metrics.py` + a new state feature + retrain | half a day + ~1 h CPU |
| support a series/parallel conversion | one function (`set_gains` / an adapter) | an hour |
| support cascade or MIMO | redesign: one tuner per loop, plus a coordinator | weeks |
| run on hardware in the loop | a new bridge (no Fast Restart), plus safety limits on the real actuator | weeks |

---

## 4. Overall assessment

**Strong fit**: single-input single-output PID loops tuned from a step response,
where the plant is available as a Simulink model or a transfer function and the
cost of an experiment is seconds. That is the majority of servo and process
loops, and it is where all the numbers in this repository were measured.

**Partial fit**: the same loops with a different objective (tracking,
disturbance) — the machinery is reusable, the *policy* is not, and it has to be
retrained. The specialist flow is the intended path.

**Weak fit**: cascade, MIMO, non-PID controllers, hardware in the loop. The
decision head is still usable as a component, but the surrounding bridge,
metrics and safety layer would have to be rebuilt.

**What is genuinely reusable even outside PID**: the `choice / score / noul`
contract, the expected-value decode with a variance trust region, the
"expert = search over the same action vocabulary" training recipe, and the
two-layer safety pattern (measured best-so-far + deterministic rollback). Those
four ideas transfer to any "take a bounded action, measure, repeat" problem.

---

# 适用范围：这个调参器能做什么、不能做什么

把它指向你的回路之前，只有两个问题：

1. **会不会把我的对象调炸？**
2. **哪些控制任务真的适合？**

下面两个都用测量回答，不用形容词。

## 1. 会不会调炸？

**200 个对象**、全部零样本（不做逐对象训练）：120 个来自训练动物园、40 个来自
未见过的族、40 个来自分布外场景（死区、不稳定极点、反向响应、谐振、噪声……）。

| 群体 | 数量 | Z-N 起点代价 | 达到的代价 | 变好 | 持平 | **变差** | 最差终值/起点 | 回滚 | 发散 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 动物园（同分布） | 120 | 2.341 | 1.556 | 97% | 3% | **0%** | 1.00 | 0 | 0 |
| 留出族 | 40 | 2.367 | 0.381 | 100% | 0% | **0%** | 0.92 | 0 | 0 |
| 分布外 | 40 | 3.378 | 2.809 | 80% | 20% | **0%** | 1.00 | 1 | 4 |

**200/200 个对象的最终结果都不差于起点。** 那 4 个"发散"是倒立摆——它们的**起点
本来就已经发散**（Z-N 对开环不稳定对象没有意义），调参器原样返回起点，而不是更差。

### 为什么它不可能把对象调坏（两层独立保障）

| 层 | 作用 | 位置 |
| :--- | :--- | :--- |
| **结构性** | 返回的永远是**实测过最好**的那组增益，所以答案不可能比起点差 | `evaluate_head` / `jev_tune_model.m`（`bestGains`） |
| **安全闸** | 某一步让代价爆炸（`J > max(3·best+1, 8)`）时回退到 `best × 0.6`，而不是信模型 | 同上，`safety_gate` |

安全闸在 200 个对象里**只触发过 1 次**——它是第二层，不是保证成立的原因。保证成立的
原因是：**返回给你的那个数字，是在你的对象上真的测过的。**

此外还有几道一开始就不允许失控的约束：

* 单步最多把增益改 **×2.1**（信赖域，log10 上 ±0.32）；
* 增益被夹在 `[1e-4, 1e3]`；
* 加载前**复制**模型文件，你的 `.slx` 永远不会被改写；
* 关闭前一定先退出 Fast Restart，无人值守的会话不会被弹窗卡住。

复现：`python scripts/11_robustness.py`

## 2. 哪些任务适合

| 任务 | 支持程度 | 你需要做什么 |
| :--- | :--- | :--- |
| **并联 PID，三个独立增益块** | ✅ 开箱即用 | 指向模型即可 |
| **`PID Controller` 掩码块** | ✅ 配置一下 | `--controller pid_block --pid-block "PID Controller"` |
| 带**固定**微分滤波的 PID | ✅ 可用 | 滤波时间常数不参与调优，但会被尊重 |
| PIDF 且想连 `Tf` 一起调 | 🔶 不支持 | 先调 `Kp/Ki/Kd`，`Tf` 手工定 |
| **串联型 / 交互型 PID** | ⚠️ 需适配 | 转成并联形式，或改写 `set_gains` |
| **串级**（位置→速度→电流） | ❌ 不支持 | 其他环固定，逐环单独调 |
| **MIMO / 耦合回路** | ❌ 不支持 | 逐环跑；不建模耦合 |
| **阶跃响应目标** | ✅ 默认 | — |
| **跟踪 / 斜坡 / 正弦** | 🔶 换指标 + 重训 | 新特征 + 专家化（约 2 分钟） |
| **扰动抑制** | 🔶 换指标 + 重训 | 注入扰动、改代价、专家化 |
| 大延迟（L/T ≈ 2） | ✅ 实测持平 | — |
| 测量噪声（σ ≈ 1%） | ✅ 实测持平 | — |
| **死区 / 回差** | 🔶 专家化 | `--scenario valve_dead_zone`，约 2 分钟 |
| **反向响应（右半平面零点）** | 🔶 专家化 | `--scenario inverse_response`，约 2 分钟 |
| **开环不稳定对象** | ❌ 未解决 | 需要稳定的起点；专家化救不了荒谬的 Z-N |
| 定步长 / 离散模型 | ✅ 可用 | 特征按时间窗归一化 |
| 没有 Scope 的模型 | ⚠️ 小改 | 加 `To Workspace`，或导出信号 |
| **真实硬件 / 半实物** | ❌ 不支持 | 没有 Fast Restart，需要另一套桥接 |
| 非 PID 控制器（LQR、MPC、增益调度） | 🔶 接口可复用 | 决策头/解码器与控制器适配层是分离的 |

图例：✅ 出厂即可 · 🔶 有一份文档化的额外步骤 · ⚠️ 少量改代码 · ❌ 超出当前设计。

## 3. 适配工作量（诚实估计）

| 你想… | 要改什么 | 工作量 |
| :--- | :--- | :--- |
| 指向自己的 Simulink 模型 | 改/传 5 个块名 | 几分钟 |
| 用 `PID Controller` 块 | 一个开关 | 几分钟 |
| 加一个它没见过的对象族 | `plants.py` 加采样器，重生成数据集，重训 | 约 40 分钟 CPU |
| 修某个分布外的具体对象 | `10_specialize.py` | 约 2 分钟 CPU |
| 换目标（跟踪、扰动抑制） | `metrics.py` 新指标 + 新状态特征 + 重训 | 半天 + 约 1 小时 CPU |
| 支持串联/并联转换 | 一个函数（`set_gains` / 适配器） | 一小时 |
| 支持串级或 MIMO | 重新设计：每环一个调参器 + 协调层 | 数周 |
| 上真实硬件在环 | 新桥接（没有 Fast Restart）+ 真实执行器限幅 | 数周 |

## 4. 总体评价

**很合适**：单入单出 PID、以阶跃响应为评价、对象能以 Simulink 模型或传递函数
给出、单次实验成本在秒级。这覆盖了大多数伺服与过程回路，也是本仓库所有数字的
测量场景。

**部分合适**：同样的回路但目标不同（跟踪、扰动抑制）——机制可复用，**策略不可
复用**，必须重训。专家化流程就是为这个准备的。

**不太合适**：串级、MIMO、非 PID 控制器、硬件在环。决策头仍可作为组件使用，但
外围的桥接、指标和安全层需要重建。

**即使不做 PID 也可以拿走的东西**：`choice / score / noul` 契约、带方差信赖域的
期望值解码、"专家 = 在同一动作词表上搜索"的训练配方、以及两层安全模式（实测
最优 + 确定性回滚）。这四个想法适用于任何"做有界动作 → 测量 → 重复"的问题。

---

## If you already have an accurate model, use `pidtune`

This is the question every control engineer asks first, so it deserves a
straight answer.

`pidtune` is **model-based design**. You hand it an LTI model and a bandwidth or
phase-margin target; it solves the frequency-domain problem and returns gains.
It never simulates the plant, never runs an experiment, and on a *correct* model
it is better than anything in this repository — faster, cheaper, and with
guarantees you can read off a Bode plot.

| | manual | `pidtune` | this project |
| :--- | :--- | :--- | :--- |
| needs a model | no | **yes, and it must be accurate** | no |
| experiments | many | **0** | 5–20 |
| time to a result | hours | seconds | seconds (simulation) |
| if the model is exact | good | **best** | worse (motor-valve benchmark: 0.598 vs the lab's 0.393) |
| if the model is wrong | varies | **can destabilise** | bounded — never worse than the start |
| what you tune against | your eye | a bandwidth/phase margin spec | your actual cost function |

Two things people miss:

1. **"Build a model" is the expensive part.** Physical derivation, system
   identification (`tfest`, `n4sid`) or linearising a Simulink model
   (`linearize`) at an operating point. The quality of the result is the quality
   of that model.
2. **`pidtune` optimises a specification, not your response.** It targets
   bandwidth and phase margin; if what you actually want is "no overshoot and
   settle in 2 s", you have to translate that into a spec (or move to
   `systune` with time-domain constraints) and iterate by hand.

The strongest model-based competitor in our own benchmark is therefore not
`pidtune` alone but **identify → `pidtune`**: one step test, a FOPDT fit, then a
design. It reaches 0.74 in **2** experiments; this project reaches 0.47 in 20.
If two experiments are acceptable to you, that route is excellent value.

**Rule of thumb.** Exact model and a linear-ish plant → `pidtune`. Model
unavailable, unreliable, or the plant is nonlinear and saturating → this project,
because it only ever claims "the best gain set I actually measured".

---

## 如果你已经有准确的模型，请直接用 `pidtune`

这是控制工程里最常被问的问题，值得正面回答。

`pidtune` 是**基于模型的设计**：你给它一个 LTI 模型和带宽/相位裕度目标，它在频域解
方程，直接返回增益。它不仿真被控对象、不做实验；**模型准确时，它比本仓库里任何方法
都好**——更快、更省，而且有 Bode 图上能读出来的保证。

| | 人工 | `pidtune` | 本项目 |
| :--- | :--- | :--- | :--- |
| 需要模型 | 不需要 | **需要，而且必须准** | 不需要 |
| 实验次数 | 很多 | **0** | 5–20 |
| 出结果时间 | 几小时 | 几秒 | 几秒（仿真） |
| 模型准确时 | 好 | **最好** | 较差（motor-valve benchmark：0.598 vs 人工 0.393） |
| 模型不准时 | 看运气 | **可能发散** | 有界——不比起点差 |
| 优化对象 | 你的眼睛 | 带宽/相位裕度指标 | 你真实的代价函数 |

两个常被忽略的点：

1. **"建模型"才是贵的部分**：物理推导、系统辨识（`tfest`、`n4sid`），或者对 Simulink
   模型做工作点线性化（`linearize`）。模型的精度决定了最后的效果。
2. **`pidtune` 优化的是"指标"，不是"你的响应"**：它盯的是带宽和相位裕度。如果你真正
   要的是"不许超调、2 秒内稳定"，得自己把这句话翻译成指标（或者改用 `systune` 的时域
   约束），再反复手调。

所以本仓库基准里最强的"基于模型"对手不是裸 `pidtune`，而是**辨识 → `pidtune`**：
先做一次阶跃辨识 FOPDT，再设计。它用 **2 次**实验拿到 0.74；本项目用 20 次拿到 0.47。
如果两次实验你能接受，那条路非常划算。

**一句话规则**：模型准确、对象近似线性 → 用 `pidtune`；模型拿不到、不可信、或者对象
非线性且会饱和 → 用本项目，因为它只承诺"我实测过的最好那组增益"。

---

## A Simscape model is not "a model" in the `pidtune` sense

People reasonably assume that building the model is the hard part, and that once
it exists `pidtune` can use it. It depends which of three things you built:

| what you built | what it is | can `pidtune` use it directly? |
| :--- | :--- | :--- |
| a diagram of linear blocks (Gain, Transfer Fcn, Integrator, Sum) | an LTI system | **yes** — `linmod`/`linearize` is exact there |
| a diagram with saturation, dead zone, friction, backlash, lookup tables | piecewise / nonlinear | **no** — linearise first, which discards all of it |
| a Simscape network (multibody, electrical, hydraulic, contact) | a high-fidelity nonlinear physical model | **no** — `linearize` at an operating point, numerically |

The trap is the third row. The friction, the backlash and the contact you
modelled on purpose are exactly what `linearize` throws away, and the linear
model is only valid in a neighbourhood of the operating point you chose. A
contact model is piecewise anyway, so linearising it near contact is close to
meaningless.

**A test you can run in five minutes.** Linearise your model at the operating
point, put the linear and the nonlinear model side by side, apply the same step,
and overlay the two responses. If they nearly coincide, treat the model as
accurate and use `pidtune`. If they diverge — and on a good Simscape model they
usually do once the input gets large — then `pidtune` gives you a nominal design
that still has to be verified against the full model.

This is where the trade-off sits, honestly:

* `pidtune` optimises the **linear surrogate**; it is fast, free and reliable
  *for that surrogate*;
* this project optimises the **nonlinear response you actually simulate**,
  because every "experiment" is a full run. It pays for that with experiments
  (each one costs a simulation, not an equation) and with a cost function that
  has to be defined.

If you have an accurate linear model, `pidtune` is better and cheaper. The more
your value comes from Simscape's nonlinearities, the more a closed-loop,
measurement-driven tuner is worth.

There is a middle route: `systune` with `slTuner` tunes against a Simulink model
at several operating points and can carry saturation as an explicit constraint.
It needs Simulink Control Design, and you still have to state the design
requirement yourself.


---

## 在 `pidtune` 的意义上，Simscape 模型不算"模型"

很多人会自然地认为：建模型是难的那一步，建好之后 `pidtune` 就能直接用。这取决于
你建的是下面三种里的哪一种：

| 你建的是什么 | 它是什么 | `pidtune` 能直接用吗 |
| :--- | :--- | :--- |
| 纯线性框图（Gain、Transfer Fcn、Integrator、Sum） | 一个 LTI 系统 | **能**——`linmod`/`linearize` 在这里是精确等价的 |
| 含饱和、死区、摩擦、齿隙、查表的框图 | 分段 / 非线性 | **不能**——必须先线性化，而线性化会把它们全丢掉 |
| Simscape 物理网络（多体、电气、液压、接触） | 高保真非线性物理模型 | **不能**——只能在某个工作点做数值线性化 |

坑在第三行。你特意建进去的摩擦、齿隙、接触，恰恰是 `linearize` 扔掉的东西；而线性
模型只在你选的那个工作点附近成立。接触本身是分段的，在接触点附近线性化几乎没有意义。

**一个五分钟就能做的验证**：把模型在工作点线性化，把线性模型和非线性模型并排放，
加同一个阶跃，看两条响应。几乎重合 → 可以当"准确模型"，放心用 `pidtune`；明显分叉
（一个好的 Simscape 模型在输入稍大时通常都会分叉）→ `pidtune` 给你的只是一个名义
设计，还得回到完整模型上验证。

这个取舍要讲清楚：

* `pidtune` 优化的是**线性代理模型**，对它而言快、免费、可靠；
* 本项目优化的是**你真正仿出来的非线性响应**，因为每次"实验"就是跑一次完整模型。
  代价是要花实验次数（一次实验=一次仿真，不是一个方程），且要自己定义代价函数。

有准确的线性模型时，`pidtune` 更好也更便宜。你越是依赖 Simscape 里的非线性，一个
闭环、靠测量推进的整定器就越值。

还有一条中间路线：`systune` + `slTuner` 可以在多个工作点上对 Simulink 模型整定，
并且能把饱和作为显式约束。它需要 Simulink Control Design，而且"设计指标"仍然要你自己写。

---

## 换掉 Simulink：适配器的边界在哪

方法是通用的，Simulink 只是"做一次实验"的一种实现：

```
有界动作（改增益） + 一次测量（跑一次，拿到 t, y, u） + 重复
```

本仓库随附两个适配器：

| 适配器 | 位置 | 验证程度 |
| :--- | :--- | :--- |
| Simulink（用 Fast Restart 跑一次仿真） | `matlab/jev_tune_model.m` | **所有对外数字都来自它** |
| Python（ODE 积分一个传递函数） | `jev-tune loop --num 1 --den "1 0.6 1"` | CI 每次推送都跑，保证决策链路不只在 MATLAB 里被测 |

要接第三种（真实台架、PLC、别的仿真工具），你只需要提供一个函数：

```python
def measure(gains) -> tuple[t, y, u]:
    '''跑一次实验，返回时间、被测量、控制量。'''
```

然后照 `evaluate.evaluate_head` 的调用方式把它喂给同一个决策头。硬件事在环**不在**
本项目的设计范围内：它需要限幅、急停和故障注入，是另一个课题，`docs/GENERALIZATION.md`
里写了哪些场景会失效。

诚实地说：换适配器不会让方法变差，但会稀释**可信度**——README 里的数字全部来自
Simulink 上的实测。新增适配器时请按同样的标准报告数字，并跑一遍
`scripts/11_robustness.py` 那样的"不比起点差"检查。

---

## Several loops in one model

The tuner edits **one controller per run**. What that means depends on how the
loops relate:

| topology | what happens | status |
| :--- | :--- | :--- |
| one loop | `jev-tune matlab --auto` | measured, see `docs/STEP4_RESULTS.md` |
| several **independent** loops (four axes, three oven zones) | `--all-loops` tunes each, carries the gains forward, writes one file with all of them | measured on a two-loop model: 2/2 loops tuned, both gain sets present in the final copy |
| **cascade** (inner current loop inside an outer speed loop) | **refused** with `cascade_suspect` | measured: a hand-built cascade is detected and not tuned |
| MIMO / decoupling / MPC | out of scope | documented, not attempted |

### Why a cascade is refused rather than attempted

Tuning the outer loop of a cascade *with the inner loop closed* is legitimate
engineering practice. Tuning it and reporting "your model is tuned" is not: the
inner gains were never touched, and the outer result is only valid for the inner
gains it happened to inherit. Since the honest version of that message is long
and the wrong version is short, the tool stops and says which loops it found.

Three independent signals trigger it, and any one is enough:

* more than one masked PID block in the model;
* two *verified* loops whose measured signals sit inside each other's forward
  path (nesting);
* two integrators **and** more than three scalar gains between the error
  junction and the measured signal — one PID loop has one integrator and three
  gains; a PI-in-PI cascade has two and four.

The last rule is the one that catches a cascade built by hand from Gain and
Integrator blocks, because that is invisible to a block-count and its inner
error junction is hidden inside the outer loop's forward path.

### What the inner-then-outer workflow needs

Not implemented, and deliberately not claimed:

1. enumerate the loops and their nesting order (the discovery code already
   produces the list, it is the ordering that is untested);
2. open or freeze the outer loop on a *copy* while the inner one is tuned — this
   edits topology, and a wrong edit introduces an algebraic loop;
3. re-tune the outer loop afterwards and report the coupling honestly.

Until that exists the recommended path is manual and explicit: name the inner
loop's blocks with `--kp-block/--ki-block/--kd-block`, tune it, then repeat for
the outer loop against the saved `_tuned.slx`. It works today; it is just not
automatic.

### One practical trap

Tuning loop A can make the model stiff (a high gain with a transport delay is
enough), and a variable-step solver then crawls through **every** subsequent
experiment, including loop B's. If a chained run slows down by an order of
magnitude, switch the model to a fixed step before deciding that the tuner is
slow: on the two-loop test model that changed 500 s to 40 s.


---

## 一个模型里有多个回路

调参器**每次只改一个控制器**。这句话的含义取决于回路之间的关系：

| 拓扑 | 行为 | 状态 |
| :--- | :--- | :--- |
| 单回路 | `jev-tune matlab --auto` | 已实测，见 `docs/STEP4_RESULTS.md` |
| 多个**互相独立**的回路（四轴、三温区） | `--all-loops` 逐个调、增益累积写回同一个文件 | 在双回路模型上实测：2/2 全部调通，两套增益都在最终文件里 |
| **串级**（内环电流套在外环速度里） | **拒绝**，返回 `cascade_suspect` | 实测：手搭的串级能被识别且不会被调 |
| MIMO / 解耦 / MPC | 不在范围内 | 已写明，不尝试 |

### 为什么串级是拒绝而不是硬调

"内环已闭合时调外环"本身是正当的工程做法。但调完外环就报告"你的模型调好了"不是：
内环增益根本没动过，而外环的结果只对它恰好继承的那组内环增益成立。诚实的说法很长，
错误的说法很短——所以工具停下来，告诉你它找到了哪几个回路。

三个独立信号任一命中即拒绝：

* 模型里有多个掩码 PID 块；
* 两个**已验证**回路的被测量互相落在对方的前向路径里（嵌套）；
* 误差汇合点到被测量之间有**两个积分器且标量增益多于三个**——单个 PID 回路是一个
  积分器、三个增益；PI 套 PI 的串级是两个积分器、四个增益。

最后这条专门抓"用 Gain + Integrator 手搭的串级"：数块数量抓不到它，而它的内环误差
汇合点藏在外环的前向路径里。

### 先内后外需要什么

没有实现，也刻意不声称支持：

1. 枚举回路并排出嵌套顺序（发现器已经能给出列表，未验证的是排序）；
2. 调内环时在**副本**上断开或冻结外环——这是改拓扑，改错会引入代数环；
3. 之后再调外环，并如实报告耦合。

在它存在之前，推荐的做法是手动且明确：用 `--kp-block/--ki-block/--kd-block`
点名内环的三个块，调完；再对着保存下来的 `_tuned.slx` 调外环。今天就能做，只是不自动。

### 一个实际会踩的坑

调完 A 回路会让模型变刚（高增益 + 传输延迟就够了），变步长求解器随后会在**每一次**
实验上慢慢爬，包括 B 回路的实验。如果串行调参突然慢了一个数量级，先把模型改成定步长
再判断是不是调参器的问题：在双回路测试模型上，这一步把 500 秒变成了 40 秒。
