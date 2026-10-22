# Step 4 — real Simulink model, no Python at runtime

> [English](#step-4--real-simulink-model-no-python-at-runtime) · [简体中文](#step-4-结果中文)


> Plant: a DC-motor position-loop benchmark (`motor_valve_model.slx`,
> Simscape Multibody butterfly valve, variable-step solver, 30° = 0.5236 rad step).
> **This is one of several test benches** — the synthetic zoo and ten
> out-of-distribution scenarios in [`GENERALIZATION.md`](GENERALIZATION.md) are
> the others. The benchmark is used here because it is a realistic Simulink
> plant, not because the method was built around it; it is not part of the
> repository and does not train the shipped head.
> Machine: Windows, MATLAB R2024b, CPU only.

## Why the bridge is built this way

Measured earlier on the same model (`research/bench/`):

| mode | per run |
| :--- | ---: |
| normal (recompile every run) | 869 ms |
| **Fast Restart** | **111 ms** (StopTime = 15 s), 40 ms at StopTime = 1 s |

A loop that recompiles is 8–19× slower than the decision itself. The bridge
therefore:

1. copies the model to a scratch directory and enables **Fast Restart**
   (compile once, then only tunable gains change),
2. runs the decision head **inside MATLAB** — `matlab/jev_head_forward.m` is a
   hand-written forward pass over the exported weights, so there is no Python,
   no ONNX Runtime and **no IPC** on the critical path,
3. keeps a deterministic safety gate: the best gain set seen so far is always
   returned, and a blow-up triggers `best × 0.6` instead of trusting `noul`.

Parity of the MATLAB forward pass against the exported reference: **max |Δ| = 7.6e-06**, re-measured in v0.3 against the current weights (the earlier figure, 6.1e-05, predated a re-export; see `docs/CLAIMS.md`).

## Result

Reference step 0.5236 rad. Ultimate gain from the Kp sweep: Ku ≈ 400, Tu ≈
0.414 s → Ziegler-Nichols start `[Kp, Ki, Kd] = [240, 1160, 12.4]`.

| gain set | Kp | Ki | Kd | cost J | experiments |
| :--- | ---: | ---: | ---: | ---: | ---: |
| lab Z-N (their Ku = 278) | 167 | 673 | 10.4 | 1.290 | — |
| our Z-N start | 240 | 1160 | 12.4 | 1.238 | 0 |
| **Jev head (shipped, best at exp. 5)** | **90.7** | **160.9** | **15.5** | **0.598** | **5 / 9** |
| human hand-tuned (lab solution) | 280 | 300 | 30.0 | 0.393 | hours |

**−52 % cost, best found at experiment five** ≈ 0.55 s of simulation at 111 ms
per run. The stall detector stopped the loop at experiment nine.

```
cost: 1.238 → 0.631 → 0.601 → 0.613 → 0.598   (early stop after 5)
gains: [240 1160 12.4] → [185 594 18.7] → [144 303 16.9] → [109 299 17.7] → [90.7 161 15.5]
```

The GIF in `assets/tuning.gif` is this run: every frame is one experiment, with
the gains the head chose and the response it produced.

### Correction: the Ku sweep was wrong

*Added in v0.3.0.* The Ziegler-Nichols start above was produced by a sweep with
three defects, all of which pushed the estimate towards the top of the grid:

1. the grid was fixed at `logspace(0.5, 400, 7)`, so any plant needing more than
   400 looked like "no oscillation" and fell back to a guess;
2. the code took the **last** oscillating grid point instead of the first, which
   is the top of the grid whenever anything oscillates;
3. "oscillation" was counted as mean crossings, and a damped second-order
   response crosses its mean three or four times, so it qualified.

Each one alone would be a bug; together they made Ku equal to the ceiling. On
this plant that produced `Ku ≈ 400` — the top of the grid, not a measurement —
and a start of `[240, 1160, 12.4]`.

With the sweep fixed (auto-ranging, first crossing, decay ratio >= 0.9):

| | start | final | experiments |
| :--- | ---: | ---: | ---: |
| v0.2 sweep (the table above) | 1.238 | 0.598 | 5 / 9 |
| v0.3 sweep | 0.674 | 0.674 | 6 (no improvement) |
| the lab's own gains (280/300/30) | 0.392 | --- | --- |

The head does not improve the corrected start: it proposes smaller gains, they
are worse, the stall detector stops it, and the safety gate returns the start.
That is the guarantee working, not a tuning success. **The honest reading is that
this plant is already well served by its lab gains, and the -52 % above measured
recovery from an over-aggressive start produced by a broken sweep.**

The Kp sweep also shows why "ultimate gain" is a weak idea here: with I and D at
zero the loop's decay ratio stays between 0.90 and 1.06 for every gain from 40 to
600 — it is marginally stable over a wide band rather than oscillating from one
particular gain. Ziegler-Nichols assumes a clear boundary; this plant has none.

The v0.2 numbers stay in place rather than being rewritten: they are what that
release measured, and `assets/tuning.gif` is that run.

With the own-gains floor added afterwards, the same model returns the lab's own
gains (J = 0.3925) rather than the ZN start, because nothing the head tries beats
them. That is the correct outcome, and the reason the promise is now worded as
"never worse than the better of the start and your existing gains".


## What the plant actually wants (one-at-a-time sensitivity)

`Kp = 280, Ki = 300`, sweeping Kd:

| Kd | 5 | 10 | 20 | **30** | 45 | 60 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 1.45 | 0.92 | 0.54 | **0.39** | 0.51 | 0.60 |

and sweeping Kp at `Ki = 300, Kd = 30`:

| Kp | 150 | 200 | 240 | **280** | 320 | 400 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 0.54 | 0.47 | 0.43 | **0.39** | 0.39 | 0.41 |

So this plant wants **2.4× the Z-N derivative gain** and a fairly wide Kp
plateau. The head found a different but valid point: much lower Kp/Ki, Kd 15.5.
It reached 0.598, i.e. **1.5× the hand-tuned cost** — good for five experiments,
not equal to a human who can iterate for hours.

## The regression that is worth recording

An intermediate model (7-option vocabulary **without** actuator-saturation
plants in the zoo) *increased* Kd's error instead of decreasing it:

| model | Kd chosen | cost |
| :--- | ---: | ---: |
| intermediate (v2) | 12.4 → 6.2 | **1.238 (no improvement)** |
| shipped (v3) | 12.4 → 15.5 | 0.598 |

Diagnosis: v2's zoo only had generous actuators, so the expert never had to use
derivative action for damping — every plant could be fixed by backing off the
proportional gain. The lab motor cannot (it saturates), which is why adding
tight-actuator plants (headroom 1.0 / 1.6 / 2.5) fixed the transfer, at the cost
of a heavier tail on the synthetic benchmark.

That trade-off is the honest state of the project: **the model that transfers to
the real plant is not the model that wins the synthetic benchmark.**

## Reproduce

```matlab
addpath('matlab');
R = jev_tune_model('...\motor_valve_model.slx', 'research/sim_tune', 20, 10, 1.0);
% iters=20 (early stop at 5), stopTime=10 s, stepGain=1.0
```

Then rebuild the demo assets:

```bash
matlab -batch "addpath('matlab'); save_demo_traces"
python scripts/07_make_demo.py
```

## Next levers

1. Add a **decay-ratio** feature (successive peak ratio) so the head can tell
   "growing oscillation → back off" from "decaying but overshooting → add
   damping". That is the single feature the failure analysis points at.
2. Mixture of two heads (generous vs tight actuator) selected by the measured
   saturation fraction — recovers v2's tail without losing v3's transfer.
3. Both are dataset-and-retrain changes, ≈30 min of CPU each.

---

## Step 4 结果（中文）

> 被控对象：直流电机位置环基准（`motor_valve_model.slx`，Simscape
> Multibody 蝶阀，变步长求解器，30° = 0.5236 rad 阶跃）。
> **这只是多个实验场之一**——另外还有合成动物园和
> [`GENERALIZATION.md`](GENERALIZATION.md) 里的 10 个分布外场景。用基准模型，
> 是因为它是一个比较真实的 Simulink 被控对象，而不是因为方法是围着它做的；
> 它不在仓库里，也不参与训练出厂权重。
> 机器：Windows，MATLAB R2024b，纯 CPU。

### 桥接为什么这么做

同一模型上的实测（`research/bench/`）：

| 模式 | 每次 |
| :--- | ---: |
| 普通（每次重编译） | 869 ms |
| **Fast Restart** | **111 ms**（StopTime=15 s），StopTime=1 s 时 40 ms |

重编译的循环比决策本身慢 8–19 倍。因此桥接：

1. 把模型复制到临时目录并开启 **Fast Restart**（编译一次，之后只改可调增益）；
2. 决策头**在 MATLAB 内运行**——`matlab/jev_head_forward.m` 是对导出权重的手写
   前向，没有 Python、没有 ONNX Runtime，关键路径上**没有 IPC**；
3. 保留确定性安全闸：始终返回历史最优增益，爆炸时回退 `best × 0.6`，而不是听
   `noul` 的。

MATLAB 前向与 PyTorch 的偏差：**6.1e-05**。

### 结果

参考阶跃 0.5236 rad。Kp 扫描得 Ku ≈ 400、Tu ≈ 0.414 s → Z-N 起点
`[Kp, Ki, Kd] = [240, 1160, 12.4]`。

| 增益组 | Kp | Ki | Kd | 代价 J | 实验次数 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 实验课 Z-N（他们的 Ku=278） | 167 | 673 | 10.4 | 1.290 | — |
| 我们的 Z-N 起点 | 240 | 1160 | 12.4 | 1.238 | 0 |
| **Jev 头（发布版，第 5 次找到）** | **90.7** | **160.9** | **15.5** | **0.598** | **5 / 9** |
| 实验课人工调参 | 280 | 300 | 30.0 | 0.393 | 数小时 |

**代价 −52%，最好的一组出现在第 5 次实验**，约 0.55 s 仿真（111 ms/次）。
停滞检测在第 9 次停下。

```
代价: 1.238 → 0.631 → 0.601 → 0.613 → 0.598   （第 5 次后早停）
增益: [240 1160 12.4] → [185 594 18.7] → [144 303 16.9] → [109 299 17.7] → [90.7 161 15.5]
```

`assets/tuning.gif` 就是这一轮：每一帧一次实验。

### 更正：Ku 扫描当时是错的

*于 v0.3.0 补充。* 上面那次 Ziegler-Nichols 起点来自一个有**三处缺陷**的扫描，三处都把
估计值推向网格顶端：

1. 网格写死为 `logspace(0.5, 400, 7)`，任何需要大于 400 的对象都会被判成"不振荡"，
   然后退化成猜；
2. 取的是**最后一个**振荡网格点而不是第一个——只要有振荡，这个点永远是网格顶端；
3. "振荡"按穿均值次数判定，而二阶阻尼响应本来就会穿均值三四次，于是也算数。

任何一条单独都是 bug；三条合起来让 Ku 等于网格上限。在这台电机上得到的是 `Ku ≈ 400`
——网格顶端，不是测量值——起点因此是 `[240, 1160, 12.4]`。

扫描修好之后（自动扩展量程、取第一个穿越点、要求峰值衰减比 ≥ 0.9）：

| | 起点 | 终点 | 实验次数 |
| :--- | ---: | ---: | ---: |
| v0.2 的扫描（上表） | 1.238 | 0.598 | 5 / 9 |
| v0.3 的扫描 | 0.674 | 0.674 | 6（未改善） |
| 实验课自带的增益（280/300/30） | 0.392 | — | — |

决策头没有改善修正后的起点：它提出更小的增益，结果更差，停滞检测把它停下，安全闸把
起点原样返回。**这是"不比起点差"这条保证在起作用，不是整定成功。** 诚实的结论是：
这台电机本来就有不错的实验课增益，上面那个 −52% 测的是"从一个被坏扫描推得过激的起点
恢复回来"。

Kp 扫描还说明为什么"极限增益"在这里不好用：把 I、D 置零后，从 40 到 600 的每个增益上
衰减比都在 0.90–1.06 之间——它在一大段范围里都临界稳定，并不是在某个增益上开始振荡。
Ziegler-Nichols 假设存在清晰边界，这台对象没有。

v0.2 的数字原样保留而不是改写：那是那个版本测出来的东西，`assets/tuning.gif` 就是那次运行。


### 被控对象真正想要什么（单变量敏感性）

固定 `Kp = 280, Ki = 300`，扫 Kd：

| Kd | 5 | 10 | 20 | **30** | 45 | 60 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 1.45 | 0.92 | 0.54 | **0.39** | 0.51 | 0.60 |

固定 `Ki = 300, Kd = 30`，扫 Kp：

| Kp | 150 | 200 | 240 | **280** | 320 | 400 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| J | 1.54 | 0.47 | 0.43 | **0.39** | 0.39 | 0.41 |

所以这个对象想要 **Z-N 微分增益的 2.4 倍**，Kp 则有一个很宽的平顶。决策头找到了
另一个同样有效的点：Kp/Ki 更低、Kd 15.5。它到 0.598，即**人工代价的 1.5 倍**——
对五次实验来说很好，但不等于一个能迭代几小时的人。

### 一个值得记录的退步

中间版本（7 档词表但动物园里**没有**执行器饱和对象）在那台实验课上把 Kd 越调越错：

| 版本 | 选中的 Kd | 代价 |
| :--- | ---: | ---: |
| 中间版（v2） | 12.4 → 6.2 | **1.238（没有改善）** |
| 发布版（v3） | 12.4 → 15.5 | 0.598 |

诊断：v2 的动物园只有宽松执行器，专家从来不需要用微分来阻尼——每株都能靠退比例
增益解决。实验台电机做不到（它会饱和），这就是加入紧执行器对象（余量 1.0 / 1.6 /
2.5）修好了迁移、却让合成基准尾部变重的原因。

这个取舍就是项目的诚实状态：**能迁移到真实对象的那一版，不是基准上最好看的那一版。**

### 复现

```matlab
addpath('matlab');
R = jev_tune_model('...\motor_valve_model.slx', 'research/sim_tune', 20, 10, 1.0);
% iters=20（第 5 次后早停），stopTime=10 s，stepGain=1.0
```

重建演示素材：

```bash
matlab -batch "addpath('matlab'); save_demo_traces"
python scripts/07_make_demo.py
```

### 下一步

1. 加**衰减比**特征（相邻峰值比），让模型能区分"振荡在发散 → 退增益"和"振荡在
   衰减但超调大 → 加阻尼"。这是失败分析唯一指向的特征。
2. 两个头混合（宽松执行器 / 紧执行器），按实测饱和比例选择——拿回 v2 的尾部又不
   丢 v3 的迁移。
3. 两者都只是数据 + 重训的改动，各约 30 分钟 CPU。
