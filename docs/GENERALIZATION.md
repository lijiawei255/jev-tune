# Does it generalise? Ten control scenarios outside the training zoo

> [English](#does-it-generalise-ten-control-scenarios-outside-the-training-zoo) · [简体中文](#泛化测试中文)


The worry this document answers: *the head was trained on a synthetic plant zoo
and tested on the motor-valve benchmark motor — is it only good at those two things?*

**Test design.** Ten scenarios a control engineer meets in other projects, none
of them present in the zoo, each with four jittered draws (±30 % gain, ±30 %
delay) = 40 plants. The shipped head runs **zero-shot**: no per-plant training,
no adaptation, no hand-tuning.

| scenario | what makes it different | head | Z-N | relay | CMA-ES | × best classical | plants won |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| dead_time | L/T = 2 (delay dominates) | 0.853 | 1.128 | 2.291 | 0.848 | 1.01 | 1/4 |
| double_integrator | 1/s² (frictionless mass) | 2.971 | 8.020 | 3.949 | 2.940 | 1.01 | 4/4 |
| unstable_pole | 1/(s−1), open-loop unstable | **1.594** | 2.042 | 50.0 | 1.999 | **0.80** | 4/4 |
| inverted_pendulum | 1/(s²−2), unstable | 50.0 | 50.0 | 50.0 | 50.0 | 1.00 | — |
| sharp_resonance | ζ = 0.02 resonance at 200 rad/s | 7.429 | 8.179 | 7.316 | 8.179 | 1.02 | 4/4 |
| noisy_sensor | σ = 1 % measurement noise | 1.489 | 2.617 | 1.530 | 2.125 | 0.97 | 3/4 |
| valve_dead_zone | 5 % actuator dead band | 2.262 | 2.262 | **0.861** | 2.262 | 2.63 | 1/4 |
| flexible_arm | two close structural modes | 7.749 | 8.498 | 7.650 | 8.498 | 1.01 | 4/4 |
| inverse_response | slow RHP zero | 2.718 | 3.091 | 3.797 | **1.953** | 1.39 | 1/4 |
| hydraulic | 3rd order + delay, tight actuator | **1.136** | 2.280 | 4.346 | 1.763 | **0.64** | 4/4 |

**Headline: within 5 % of the best classical tuner on 30 of 40 plants;
median cost ratio 1.01× (1.00 = parity).** So on this sample the head neither
collapses nor dominates — it behaves like a competent default tuner.

## Where it is strong

* **Unstable first-order pole** (0.80×) and **hydraulic** (0.64×) — the head
  backs the gains off decisively, which is exactly what the zoo's saturation
  cases taught it.
* **Double integrator** (1.01×, 4/4) and **noisy sensor** (0.97×) — it does not
  get fooled by derivative noise because it never learned to trust one number.

## Where it fails, and why

1. **Valve dead band (2.63×)** — the response chatters around the 5 % dead band,
   and every feature the head sees ("many crossings", "long settling") looks
   like *too much gain*. Relay autotuning wins because it measures the limit
   cycle directly. A dead-band-aware feature would fix this.
2. **Inverse response (1.39×)** — the plant first moves the wrong way. The head
   has no feature for "the initial direction is inverted", so it treats the dip
   as instability and backs off. CMA-ES wins by brute force.
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
* The motor-valve benchmark case (cost 1.238 → 0.598) is therefore not evidence of overfitting
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

本项目要回答的疑问：*决策头是在合成动物园上训练的、又在 motor-valve benchmark 上测过——是不是只会这两样？*

**测试设计。** 10 个其他项目里会遇到的场景，**都不在动物园里**，每个 4 组抖动
（增益 ±30%、延迟 ±30%）= 40 株。发布的决策头**零样本**运行：不做逐对象训练、不
在线适配、不手工微调。

| 场景 | 难在哪 | 决策头 | Z-N | 继电 | CMA-ES | × 最好传统法 | 胜出株数 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 大延迟 | L/T = 2（延迟主导） | 0.853 | 1.128 | 2.291 | 0.848 | 1.01 | 1/4 |
| 双积分器 | 1/s²（无摩擦质量） | 2.971 | 8.020 | 3.949 | 2.940 | 1.01 | 4/4 |
| 不稳定一阶 | 1/(s−1)，开环发散 | **1.594** | 2.042 | 50.0 | 1.999 | **0.80** | 4/4 |
| 倒立摆 | 1/(s²−2)，不稳定 | 50.0 | 50.0 | 50.0 | 50.0 | 1.00 | — |
| 尖锐谐振 | ζ=0.02，200 rad/s | 7.429 | 8.179 | 7.316 | 8.179 | 1.02 | 4/4 |
| 传感器噪声 | σ = 1% | 1.489 | 2.617 | 1.530 | 2.125 | 0.97 | 3/4 |
| 阀门死区 | 5% 死区 | 2.262 | 2.262 | **0.861** | 2.262 | 2.63 | 1/4 |
| 柔性臂 | 两个靠近的模态 | 7.749 | 8.498 | 7.650 | 8.498 | 1.01 | 4/4 |
| 反向响应 | 慢右半平面零点 | 2.718 | 3.091 | 3.797 | **1.953** | 1.39 | 1/4 |
| 液压执行器 | 三阶 + 延迟 + 紧限幅 | **1.136** | 2.280 | 4.346 | 1.763 | **0.64** | 4/4 |

**核心结论：40 株里有 30 株与最强传统方法在 5% 以内，中位比值 1.01×（1.00 = 持平）。**
所以在这个样本上，它既没有崩，也没有碾压——表现像一个"还不错的默认调参器"。

### 强在哪

* **不稳定一阶**（0.80×）与**液压**（0.64×）——决策头决断地退增益，这正是动物园里
  饱和案例教给它的。
* **双积分器**（1.01×，4/4）与**噪声传感器**（0.97×）——它不会被微分噪声骗到，因为
  它从没学会信任某一个数字。

### 输在哪，以及为什么

1. **阀门死区（2.63×）**——响应在 5% 死区里抖动，而它看到的每个特征（"交点很多"、
   "收敛很慢"）都长得像"增益太大"，于是它一路退增益。继电自整定赢，因为它直接
   测量极限环。一个死区感知的特征能修好这一点。
2. **反向响应（1.39×）**——对象一开始先往反方向走。模型没有"初始方向反了"这个
   特征，于是把下凹当成失稳并退增益。CMA-ES 靠暴力赢。
3. **倒立摆（所有方法全废）**——这一条值得点名：`ultimate_gain` 只对稳定对象有意义，
   Z-N 给出 Ku ≈ 1.2e6，于是**所有方法**（包括决策头）都从这个垃圾起点出发并立刻
   发散。真人会先用 PD 把摆扶稳。决策头没有"开环不稳定"的冷启动检测。

### 这对"过拟合"意味着什么

* 决策头**没有记住动物园**：它在十类从未见过的动力学上达到持平，包括性格很不一样的
  对象（延迟主导、双积分、谐振）。
* 但它**受限于特征集**：上面每一个失败都能追溯到某个不存在的状态描述（死区抖动、
  初始方向反向、"对象不稳定所以 Z-N 无意义"）。
* 所以 motor-valve benchmark 的结果（1.238 → 0.598）**不是过拟合测试台的证据**——它落在这 40 株的
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
