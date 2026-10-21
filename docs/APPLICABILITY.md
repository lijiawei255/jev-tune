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
