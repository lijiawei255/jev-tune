
> [English](#specialist-fine-tuning-on-one-plant-family) · [简体中文](#每个项目先学一遍specialist-流程)

# Specialist: fine-tuning on one plant family

The shipped head is **zero-shot**: it works out of the box and does no
adaptation. The price is that it only understands the dynamics in its training
zoo (FOPDT, second order, delay, integrating, motor speed/position loops,
two-mass resonance, and actuator-saturation variants).

If a project falls outside that, the right move is not to force it — it is to
train a specialist. Same pipeline, different data.

## One command

```bash
# a named scenario
python scripts/10_specialize.py --scenario valve_dead_zone --name valve

# or describe your own plant
# plant.json: {"num":[1], "den":[0.5,1,0], "delay_s":0.05, "u_max":1.6}
python scripts/10_specialize.py --spec plant.json --name myplant
```

What it does:

1. jitters the plant by ±20 % (gain, delay) to build ~120 siblings;
2. holds out a quarter for validation, runs the expert on the rest
   (coordinate line search, 22 simulations per step);
3. fine-tunes **from the shipped weights** for 30 epochs (lr 1e-3);
4. compares **zero-shot vs specialised** on the same held-out set and writes a
   JSON report.

**1–2 minutes of CPU**, no GPU, no data from the real plant.

## Measured on the two scenarios the head was worst at

30 held-out jitters (gain/delay ±20 %, never seen in training), 90 training,
1 080 states:

| scenario | zero-shot J | specialist J | change | time |
| :--- | ---: | ---: | ---: | ---: |
| valve dead band (`valve_dead_zone`) | 2.242 | **2.207** | **−2 %** | 94 s |
| inverse response (`inverse_response`) | 1.727 | see below | — | — |

Reproduce the first row exactly:

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --plants 120
```

`--plants 120` matters: the script's default (48) means 12 held-out jitters, not
30, and the two do not give the same number.

**A note on the figures, and an apology to the reader.** The v0.2 release
recorded 1.152 (−49 %); v0.3 recorded 1.884 (−16 %). Both were measured on
scenario draws produced by `scenarios.variants`, which used Python's salted
`hash()` as part of its seed — so the *plants themselves* changed from process to
process. As of 0.4.0 the seed is `crc32(name)`, the draw is reproducible, and the
same command lands at **2.207 (−2 %)**: essentially no improvement. The earlier
percentages were partly measuring a different draw, and this file no longer
quotes them. The lesson is the one the release notes keep making: a number
without a reproducible artifact is not a measurement.

The cost is **~100 s of CPU once**, not zero — but also not "redo the project".

## What it cannot fix

Open-loop unstable plants (inverted pendulum): the problem is the **starting
point**, not the policy. Z-N returns an absurd Ku for an unstable plant, and
every method (the specialist included) diverges from that start. A stronger
policy does not help; what is missing is a "stabilise with PD first" cold-start
step — a model-level gap, not a data-level one.

## When it is worth it

| situation | advice |
| :--- | :--- |
| plant inside the zoo (most servo / process loops) | use zero-shot |
| clear structural difference (dead band, inverse response, unstable) | one specialist run, ~2 min |
| dozens of identical machines | specialise once, reuse everywhere |
| every unit differs | zero-shot + the safety gate, or one specialist per unit |

## Not online learning

This is **offline, one-time, per family** — not "each device learns while
running":

* no online weight updates (a fixed policy is what makes 0.19 ms possible);
* no real-device data (the expert comes from search on simulated plants);
* the output is a `.pt` + `.mat` you can copy to another machine.

Learn once, reuse across the whole family — that is how it stays both fast and
reproducible.

---

以下为中文全文。

# "每个项目先学一遍"：specialist 流程

出厂权重是**零样本**的：拿来就用，不做任何适配。代价是它只认识训练动物园里的
动力学（FOPDT、二阶、延迟、积分、电机速度环/位置环、双质量谐振，以及执行器
饱和的变体）。

如果项目落在这个范围外（死区、反向响应、开环不稳定……），正确做法不是硬用它，
而是**训练一个专家**——同一套流程，只换数据。

---

## 一条命令

```bash
# 用内置场景
python scripts/10_specialize.py --scenario valve_dead_zone --name valve

# 或者用你自己的对象描述
# plant.json: {"num":[1], "den":[0.5,1,0], "delay_s":0.05, "u_max":1.6}
python scripts/10_specialize.py --spec plant.json --name myplant
```

做的事：

1. 把对象参数抖动 ±20%（增益、延迟），生成 120 个"同族"对象；
2. 留出 1/4 做验收，其余跑专家轨迹（坐标线搜索，22 次仿真/步）；
3. 从**现有权重**出发微调 30 个 epoch（lr 1e-3）；
4. 在同一批留出对象上比较 **零样本 vs 专家**，输出 JSON 报告。

全程 **1–2 分钟 CPU**，不需要 GPU，不需要真实设备数据。

---

## 实测：阀死区（上面泛化测试里零样本最差的场景）

同一批 30 个留出对象（增益/延迟各抖动 ±20%，训练时从未见过），
90 株训练、30 epoch、1 260 状态：

| 场景 | 零样本 J | 专家 J | 改善 | 耗时 |
| :--- | ---: | ---: | ---: | ---: |
| 阀死区（`valve_dead_zone`） | 2.242 | **2.207** | **−2 %** | 94 s |
| 反向响应（`inverse_response`） | 1.727 | 见下文 | — | — |

第一行可以逐位复现：

```bash
python scripts/10_specialize.py --scenario valve_dead_zone --plants 120
```

`--plants 120` 不能省：脚本默认的 48 意味着 12 个留出抖动，而不是 30 个，两者数字不同。

**关于旧数字，以及向读者的更正。** v0.2 记的是 1.152（−49 %），v0.3 记的是 1.884
（−16 %）。两次都是在 `scenarios.variants` 生成的抽样上测的，而它当时把 Python 加盐的
`hash()` 当作种子的一部分——**对象本身每个进程都不一样**。0.4.0 起种子改成
`crc32(场景名)`，抽样可复现，同一条命令落在 **2.207（−2 %）**：基本没有改善。早先的
百分比有一部分在测另一批对象，本文件不再引用它们。教训就是发布说明里反复写的那条：
**没有可复现产物的数字，不算测量。**

两例都是泛化测试里零样本输给传统方法的场景。专门化之后：

* 阀死区 2.21，对比继电自整定的 0.99（原本差 2.25 倍 → 仍然差 2.2 倍，**没有修好**）；
* 反向响应 0.84，对比 CMA-ES 的 0.83（原本差 1.54 倍 → 追平）。

所以专门化在反向响应上有效，在阀死区上基本无效。上表只列第一行，是因为第二行需要单独
跑一次并手工记录；这里的数字来自 `docs/GENERALIZATION.md` 的当前产物。

代价是**一次性约 100 秒 CPU**，不是零成本，但也不是"重新做一遍整个项目"。

### 它修不好什么

倒立摆（开环不稳定）这类场景，问题不在策略而在**起点**：Z-N 公式对不稳定对象
给出的 Ku 是荒谬的，所有方法（包括专家）都从那个起点出发立刻发散。换更强的策略
无济于事，需要的是"先用 PD 扶稳再调参"的冷启动逻辑——这是模型层面缺失的一步，
不是数据层面的。

诚实的边界：

* 数据量（~1 300 状态）**远小于**主训练集（40 000 状态），所以只能修正"局部偏好"，
  不能重建策略；
* 如果连专家数据里都没有"该往哪走"的信号（比如目标函数本身不可达），微调也救不了；
* 换场景要重训，**不是通用增强**。

---

## 什么时候值得做

| 情况 | 建议 |
| :--- | :--- |
| 对象落在训练动物园内（大部分伺服/过程控制） | 直接用零样本，`jev-tune matlab` |
| 对象有明确的结构差异（死区、反向响应、不稳定） | 跑一次 specialist，约 2 分钟 |
| 有几十台同型号设备 | specialist 一次，全部复用 |
| 每台设备都不一样 | 零样本 + 安全闸，或每台单独 specialist |

---

## 和"在线学习"的区别

这个流程是**离线、一次性、按族**的，不是"每台设备边跑边学"：

* 不做在线更新（推理 0.19 ms 的前提就是权重固定）；
* 不收集真实设备数据（只用仿真，专家轨迹来自搜索算法）；
* 产出是一个新的 `.pt` + `.mat`，可以拷到别的机器上复用。

换句话说：**学一次，用在所有同族对象上**——这也是它能同时做到"快"和"可复现"的原因。
