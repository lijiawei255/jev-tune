# Worked examples

Three real runs, copied from the terminal on the machine described in
`docs/STEP4_RESULTS.md` (Windows 11, MATLAB R2024b Update 6, Python 3.12).
Nothing here is idealized: the numbers are what came out.

> [中文版在下方](#中文版)

---

## 1. A loop you have never seen

A benchmark lab's motor model: a Simscape plant, three gain blocks, four Scopes, and a
position signal that leaves `Motor_Drive` on **output port 3 of 4**.

### Ask why it might not work

```console
$ jev-tune doctor --model research/sim_tune/jev_lab_model.slx
check       ok?   detail
file        ok    .../jev_lab_model.slx (80 KB)
loads       ok    MATLAB 2024b
referenced  ok    none
protected   ok    none
stateflow   ok    none
compiles    ok    compiles
solver      ok    VariableStepAuto, variable step, StopTime 15.0
signals     ok    4 scopes, 0 To Workspace, 0 outports
tunable     ok    1 verified loop(s); Kp=Gain_Kp Ki=Gain_Ki Kd=Gain_Kd
```

`compiles` is the check that earns its keep: on a model whose gains come from a
setup script you forgot to run, it names the missing variable instead of
reporting "no loop".

### See what it found

```console
$ jev-tune discover --model research/sim_tune/jev_lab_model.slx
model       jev_lab_model.slx
confidence  high
junction    Sum_Error
controller  Kp=Gain_Kp  Ki=Gain_Ki  Kd=Gain_Kd
measured    Motor_Drive port 3
reference   0.5236  (30 x 0.017453)
```

Two details worth pausing on, because they are what "no block names" buys you:

* the measured signal is **port 3**, not the Scope called `Scope-Position`,
  which has two inputs (reference *and* position) and would have handed the tuner
  the reference as if it were the response;
* `0.5236` is `Step(30) × Deg2Rad(π/180)`, read from the model rather than
  guessed from the block name.

### Tune it

```console
$ jev-tune matlab --model research/sim_tune/jev_lab_model.slx \
      --auto --stop-time 10 --plot before_after.png --write-back
model      .../jev_lab_model.slx
gains      [91.4829, 172.2632, 14.0982]
cost       0.615  (start 1.377)
experiments 11  rollbacks 0  wall 77.7 s
plot       before_after.png
written    .../jev_lab_model_tuned.slx
discovered  Motor_Drive (high)
```

The 77.7 s is dominated by MATLAB's ~50 s cold start; the tuning itself is 11
experiments of a 10 s simulation. The start cost 1.377 is the same number as the
run recorded in `docs/STEP4_RESULTS.md`, which is the point: discovery did not
change what is being optimised, only how the blocks were found.

---

## 2. A cascade: refused, with a plan

Built by hand from Gain and Integrator blocks (an outer speed loop around an
inner current loop). Nothing about it looks different from a single loop unless
you count integrators.

```console
$ jev-tune doctor --model research/cascade.slx
check       ok?   detail
...
compiles    ok    compiles
solver      ok    ode45, variable step, StopTime 10
signals     ok    0 scopes, 0 To Workspace, 0 outports
tunable     FAIL  cascade_suspect  (ka | kb | kc)

verdict: discovery refused: cascade_suspect
next:    this is probably a cascade or two controllers in one path; tune the
         inner loop first, or name the blocks explicitly
```

Why refuse: tuning the outer loop with the inner one closed is legitimate, but
reporting "your model is tuned" would not be — the inner gains were never
touched. See
[`docs/APPLICABILITY.md`](APPLICABILITY.md#why-a-cascade-is-refused-rather-than-attempted).

The manual path works today and is explicit:

```console
# inner loop first, naming its blocks
$ jev-tune matlab --model cascade_tuned.slx --kp-block CurrentController/kc \
      --ki-block CurrentController/kd --measure-scope Scope_Current
# then the outer loop against the saved copy
```

---

## 3. Two independent loops

A gantry with two axes is two jobs, not one:

```console
$ jev-tune matlab --model two_axes.slx --all-loops --iters 6
loops      2/2 tuned
  [ok  ] dSum_a           J 1.055 -> 0.894  6 exp  [312.0862, 823.7888, 8.3844]
  [ok  ] dSum_b           J 0.116 -> 0.116  6 exp  [120.0, 96.0, 37.5]
target     .../two_axes_tuned.slx
wall       83.1 s
```

Both gain sets are in the final file — the run chains: loop B starts from the
copy loop A wrote. If a chained run suddenly takes ten times longer, the first
loop probably made the model stiff and the variable-step solver is crawling
through every subsequent experiment; switching to a fixed step took the same
model from 500 s to 40 s.

---

## When it fails anyway

Run `jev-tune doctor` first, then `jev-tune discover --json`. If the JSON shows
a topology the project claims to handle, that is a bug: open the **Discovery
failed on a real model** issue template with that JSON. It already contains every
candidate junction and the reason, which is usually enough to find the problem
without seeing the model.

---

# 中文版

三个真实运行，直接从终端复制（Windows 11 + MATLAB R2024b Update 6 + Python 3.12）。
没有美化，数字就是跑出来的数字。

## 1. 没见过的回路

某门实验课的电机模型：Simscape 被控对象、三个增益块、四个示波器，位置信号从
`Motor_Drive` 的**第 3 个输出口**（共 4 个）引出。

### 先问"为什么可能调不了"

```console
$ jev-tune doctor --model research/sim_tune/jev_lab_model.slx
check       ok?   detail
file        ok    .../jev_lab_model.slx (80 KB)
loads       ok    MATLAB 2024b
referenced  ok    none
protected   ok    none
stateflow   ok    none
compiles    ok    compiles
solver      ok    VariableStepAuto, variable step, StopTime 15.0
signals     ok    4 scopes, 0 To Workspace, 0 outports
tunable     ok    1 verified loop(s); Kp=Gain_Kp Ki=Gain_Ki Kd=Gain_Kd
```

`compiles` 这一格最值钱：如果模型的增益来自某个忘了运行的初始化脚本，它会直接点名
缺哪个变量，而不是含糊地报"没找到回路"。

### 看它找到了什么

```console
$ jev-tune discover --model research/sim_tune/jev_lab_model.slx
model       jev_lab_model.slx
confidence  high
junction    Sum_Error
controller  Kp=Gain_Kp  Ki=Gain_Ki  Kd=Gain_Kd
measured    Motor_Drive port 3
reference   0.5236  (30 x 0.017453)
```

两个细节值得停一下，它们正是"不看块名"换来的：

* 被测量是**第 3 口**，不是那个叫 `Scope-Position` 的示波器——它有两个输入
  （参考 *和* 位置），拿它当响应等于把参考当成了被控量；
* `0.5236` 是 `Step(30) × Deg2Rad(π/180)`，从模型里读出来的，不是按块名猜的。

### 调它

```console
$ jev-tune matlab --model research/sim_tune/jev_lab_model.slx \
      --auto --stop-time 10 --plot before_after.png --write-back
cost       0.615  (start 1.377)
experiments 11  rollbacks 0  wall 77.7 s
written    .../jev_lab_model_tuned.slx
```

77.7 秒里大部分是 MATLAB 约 50 秒的冷启动；调参本身是 11 次 10 秒仿真。起点 1.377 和
`docs/STEP4_RESULTS.md` 里记录的那次完全一致——这说明发现过程没有改变被优化的东西，
只改变了"怎么找到块"。

## 2. 串级：拒绝，并给出方案

用 Gain + Integrator 手搭的（外环速度、内环电流）。除了数积分器，它和单回路看起来没区别。

```console
$ jev-tune doctor --model research/cascade.slx
compiles    ok    compiles
tunable     FAIL  cascade_suspect  (ka | kb | kc)
next:    this is probably a cascade or two controllers in one path; tune the
         inner loop first, or name the blocks explicitly
```

为什么拒绝：内环闭合时调外环本身正当，但报告"你的模型调好了"不正当——内环增益根本没动。
详见 [`docs/APPLICABILITY.md`](APPLICABILITY.md#为什么串级是拒绝而不是硬调)。

手动路径今天就能用，而且是显式的：先点名内环的三个块调内环，再对着保存下来的副本调外环。

## 3. 两个独立回路

两个轴就是两个任务，不是一个：

```console
$ jev-tune matlab --model two_axes.slx --all-loops --iters 6
loops      2/2 tuned
  [ok  ] dSum_a           J 1.055 -> 0.894  6 exp  [312.0862, 823.7888, 8.3844]
  [ok  ] dSum_b           J 0.116 -> 0.116  6 exp  [120.0, 96.0, 37.5]
target     .../two_axes_tuned.slx
```

两套增益都在最终文件里——这次运行是链式的：B 回路从 A 回路写出的副本开始。如果串行
调参突然慢了十倍，多半是第一个回路让模型变刚、变步长求解器在每次实验上慢慢爬；换定步长
把同一个模型从 500 秒压到了 40 秒。

## 实在不行的时候

先跑 `jev-tune doctor`，再跑 `jev-tune discover --json`。如果 JSON 显示的是本项目声称
支持的拓扑，那就是 bug：用 **Discovery failed on a real model** 模板把那段 JSON 贴出来。
它已经包含所有候选汇合点和原因，通常不看模型也能定位。
