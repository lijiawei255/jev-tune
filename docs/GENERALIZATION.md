# Does it generalise? Ten control scenarios outside the training zoo

> [English](#does-it-generalise-ten-control-scenarios-outside-the-training-zoo) · [简体中文](#泛化测试中文)


The worry this document answers: *the head was trained on a synthetic plant zoo
and tested on the lab motor — is it only good at those two things?*

**Test design.** Ten scenarios a control engineer meets in other projects, none
of them present in the zoo, each with four jittered draws (±30 % gain, ±30 %
delay) = 40 plants. The shipped head runs **zero-shot**: no per-plant training,
no adaptation, no hand-tuning.

| scenario | what makes it different | head | Z-N | relay | CMA-ES | × best classical | plants won |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | L/T = 2 (delay dominates) | 0.778 | 1.055 | 2.077 | 0.760 | 1.02 | 2/4 |
| double_integrator | 1/s² (frictionless mass) | 3.144 | 9.036 | 3.965 | 3.047 | 1.03 | 4/4 |
| unstable_pole | 1/(s−1), open-loop unstable | 26.068 | 26.620 | 50.000 | 26.037 | 1.00 | 4/4 |
| inverted_pendulum | 1/(s²−2), unstable | 50.0 | 50.0 | 50.0 | 50.0 | 1.00 | 4/4 |
| sharp_resonance | ζ = 0.02 resonance at 200 rad/s | 7.383 | 8.133 | 7.269 | 8.133 | 1.02 | 4/4 |
| noisy_sensor | σ = 1 % measurement noise | 1.442 | 2.884 | 1.581 | 2.404 | **0.91** | 4/4 |
| valve_dead_zone | 5 % actuator dead band | 2.229 | 2.237 | **0.990** | 2.226 | 2.25 | 1/4 |
| flexible_arm | two close structural modes | 7.748 | 8.497 | 7.649 | 8.497 | 1.01 | 4/4 |
| inverse_response | slow RHP zero | 1.278 | 1.428 | 5.468 | **0.832** | 1.54 | 1/4 |
| hydraulic | 3rd order + delay, tight actuator | **1.156** | 2.339 | 4.299 | 1.678 | **0.69** | 4/4 |

**Headline: within 5 % of the best classical tuner on 32 of 40 plants;
median cost ratio 1.014× (1.00 = parity).** So on this sample the head neither
collapses nor dominates — it behaves like a competent default tuner.

> These rows are the current artifact (`research/results/generalization.json`)
> with the shipped configuration, which includes abstention. With
> `abstain=None` the same script reported 37/40 and 0.97×; holding when unsure
> costs a few out-of-zoo improvements and buys fewer parameter changes. That is
> the trade-off measured in `docs/ABSTENTION.md`. The scenario seeds are stable
> across processes (crc32 of the scenario name) as of 0.4.0; before that they
> used Python's salted `hash()` and were not reproducible.

## Where it is strong

* **Hydraulic** (0.69×) and **noisy sensor** (0.91×) — the head backs the gains
  off decisively on the tight-actuator case, and it is not fooled by derivative
  noise because it never learned to trust one number.
* **Dead time** (1.02×) is parity, which is what a one-step policy should manage
  when the delay dominates: it can only react to what it has already measured.

## Where it fails, and why

1. **Inverse response (1.54×)** — the plant first moves the wrong way. The head
   has no feature for "the initial direction is inverted", so it treats the dip
   as instability and backs off. CMA-ES wins by brute force.
2. **Valve dead band (2.25×)** — the response chatters around the 5 % dead band,
   and every feature the head sees ("many crossings", "long settling") looks
   like *too much gain*. Relay autotuning wins because it measures the limit
   cycle directly. A dead-band-aware feature would fix this.
3. **Inverted pendulum (every method fails)** — this one is an artefact worth
   naming: `ultimate_gain` is only meaningful for stable plants, so Z-N returns
   Ku ≈ 1.2e6, and *every* tuner here (head included) starts from that garbage
   and diverges immediately. A practitioner would start from a hand-derived
   stabilising PD. The head has no cold-start detector for open-loop unstable
   plants.

## What this says about overfitting

* The head is **not** memorising the zoo: it lands at parity on ten dynamics
  families it has never seen, including ones with a very different character
  (dead time, double integrator, resonance).
* But it **is** limited by its feature set: every failure above traces back to
  a state descriptor that does not exist (dead-band chatter, inverted initial
  direction, "the plant is unstable so Z-N is meaningless").
* The lab case (cost 1.238 → 0.598) is therefore not evidence of overfitting
  to the test bench — it sits inside the band of results above.

## Reproduce

```bash
python scripts/08_generalize.py --draws 4
```

Raw output: `research/results/generalization.json`.

## Is there a per-project learning step?

**No, not at deployment.** Training happens once, offline, on the synthetic zoo
(~30 min of CPU). At runtime the head is a fixed 200 KB policy: it sees the
response, emits a `choice`/`score`/`noul`, done. That is what makes 0.19 ms and
zero cold-start possible.

If a project falls outside the zoo (dead band, inverted response, unstable
plants), the supported path is a **specialist**: generate a zoo that resembles
your plant, regenerate the dataset and fine-tune the head — about 30 minutes of
CPU, no GPU, no labels from the real plant. That is "learning per project",
just done once, offline, and shared by every plant of that type.

---

## 泛化测试（中文）

本项目要回答的疑问：*决策头是在合成动物园上训练的、又在一台实验课电机上测过——是不是只会这两样？*

**测试设计。** 10 个其他项目里会遇到的场景，**都不在动物园里**，每个 4 组抖动
（增益 ±30%、延迟 ±30%）= 40 株。发布的决策头**零样本**运行：不做逐对象训练、不
在线适配、不手工微调。

| 场景 | 难在哪 | 决策头 | Z-N | 继电 | CMA-ES | × 最好传统法 | 胜出株数 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 大延迟 | L/T = 2（延迟主导） | 0.778 | 1.055 | 2.077 | 0.760 | 1.02 | 2/4 |
| 双积分器 | 1/s²（无摩擦质量） | 3.144 | 9.036 | 3.965 | 3.047 | 1.03 | 4/4 |
| 不稳定一阶 | 1/(s−1)，开环发散 | 26.068 | 26.620 | 50.000 | 26.037 | 1.00 | 4/4 |
| 倒立摆 | 1/(s²−2)，不稳定 | 50.0 | 50.0 | 50.0 | 50.0 | 1.00 | 4/4 |
| 尖锐谐振 | ζ=0.02，200 rad/s | 7.383 | 8.133 | 7.269 | 8.133 | 1.02 | 4/4 |
| 传感器噪声 | σ = 1% | 1.442 | 2.884 | 1.581 | 2.404 | **0.91** | 4/4 |
| 阀门死区 | 5% 死区 | 2.229 | 2.237 | **0.990** | 2.226 | 2.25 | 1/4 |
| 柔性臂 | 两个靠近的模态 | 7.748 | 8.497 | 7.649 | 8.497 | 1.01 | 4/4 |
| 反向响应 | 慢右半平面零点 | 1.278 | 1.428 | 5.468 | **0.832** | 1.54 | 1/4 |
| 液压执行器 | 三阶 + 延迟 + 紧限幅 | **1.156** | 2.339 | 4.299 | 1.678 | **0.69** | 4/4 |

**核心结论：40 株里有 32 株与最强传统方法在 5% 以内，中位比值 1.014×（1.00 = 持平）。**
所以在这个样本上，它既没有崩，也没有碾压——表现像一个"还不错的默认调参器"。

> 上面是当前产物（`research/results/generalization.json`）与发布配置（含弃权）的数字。
> 同一脚本在 `abstain=None` 时报告的是 37/40 与 0.97×；**不确定时保持**会少改进几株
> 分布外对象，换来更少的参数改动。这个权衡测在 `docs/ABSTENTION.md`。0.4.0 起场景
> 种子对进程稳定（`crc32(场景名)`）；此前用的是 Python 加盐的 `hash()`，**不可复现**。

### 强在哪

* **液压**（0.69×）与**噪声传感器**（0.91×）——紧限幅下它决断地退增益，也不被微分
  噪声骗到，因为它从没学会信任某一个数字。
* **大延迟**（1.02×）是持平，这正是一步策略在延迟主导时应有的表现：它只能对已经测到
  的东西作反应。

### 输在哪，以及为什么

1. **反向响应（1.54×）**——对象一开始先往反方向走。模型没有"初始方向反了"这个
   特征，于是把下凹当成失稳并退增益。CMA-ES 靠暴力赢。
2. **阀门死区（2.25×）**——响应在 5% 死区里抖动，而它看到的每个特征（"交点很多"、
   "收敛很慢"）都长得像"增益太大"，于是它一路退增益。继电自整定赢，因为它直接
   测量极限环。一个死区感知的特征能修好这一点。
3. **倒立摆（所有方法全废）**——这一条值得点名：`ultimate_gain` 只对稳定对象有意义，
   Z-N 给出 Ku ≈ 1.2e6，于是**所有方法**（包括决策头）都从这个垃圾起点出发并立刻
   发散。真人会先用 PD 把摆扶稳。决策头没有"开环不稳定"的冷启动检测。

### 这对"过拟合"意味着什么

* 决策头**没有记住动物园**：它在十类从未见过的动力学上达到持平，包括性格很不一样的
  对象（延迟主导、双积分、谐振）。
* 但它**受限于特征集**：上面每一个失败都能追溯到某个不存在的状态描述（死区抖动、
  初始方向反向、"对象不稳定所以 Z-N 无意义"）。
* 所以这台电机的实验结果（1.238 → 0.598）**不是过拟合测试台的证据**——它落在这 40 株的
  分布带里。

### 复现

```bash
python scripts/08_generalize.py --draws 4
```

原始输出：`research/results/generalization.json`。

### 部署时有没有"逐项目学习"？

**没有。** 训练是一次性的、离线的，在合成动物园上（约 30 分钟 CPU）。运行时是固定
的 200 KB 策略。这正是 0.19 ms 和零冷启动的前提。

如果项目落在动物园之外（死区、反向响应、不稳定对象），受支持的路径是**专家化**：
生成一个像你的对象的小动物园，重跑数据集并微调决策头——约 30 分钟 CPU，不需要
GPU，也不需要真实设备标签。那是"按项目学习"，只是离线、一次性、同族共用。
