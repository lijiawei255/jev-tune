> [English](#applicability-what-this-tuner-can-and-cannot-do) · [简体中文](#适用范围这个调参器能做什么不能做什么)

# Applicability: what this tuner can and cannot do

Two questions before pointing it at your loop:

1. **can it make my plant worse?**
2. **which control tasks does it actually fit?**

Both are answered with measurements, not adjectives.

---

## 1. Returned cost versus search risk

| group | n | start J | returned J | improved % | worse % | rollbacks | final diverged | search diverged |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| zoo | 120 | 2.341 | 1.382 | 97.5 | 0.0 | 0 | 0 | 0 |
| heldout | 40 | 2.367 | 0.463 | 100.0 | 0.0 | 0 | 0 | 0 |
| outofzoo | 40 | 3.983 | 3.016 | 82.5 | 0.0 | 0 | 5 | 5 |

Across 200 plants, returned measured-best costs have worse_pct as listed above. This is bookkeeping, not a bound on trial costs or stability. OOD search divergence: 5; final divergence: 5. Total rollbacks: 0. Gate-on/off unchanged pairs: 40/40 at absolute tolerance 1e-06.

Parameter bounds do not prove stability. A 0.6×best rollback proposal must be measured. Per-plant budget is 20; original model files are copied. Source: [`research/results/robustness.json`](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1), reproduced by `python scripts/11_robustness.py`.

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
| **Tracking / ramp / sinusoid** | 🔶 new task definition | new metrics/features, matching expert data and fresh validation; existing specialist command is not sufficient |
| **Disturbance rejection** | 🔶 metrics + retrain | inject the disturbance, change the cost, specialist run |
| Dead-time dominant (L/T ≈ 2) | evaluated; see GENERALIZATION | — |
| Noisy measurement (σ ≈ 1 %) | evaluated; see GENERALIZATION | — |
| **Dead band / backlash** | 🔶 failure boundary | specialist training is an experiment, not a guaranteed remedy; see [SPECIALIZE](SPECIALIZE.md) |
| **Inverse response (RHP zero)** | 🔶 failure boundary | compare with a classical search under the same measured budget |
| **Open-loop unstable plant** | ❌ not solved | needs a stabilising start; the specialist cannot fix a meaningless Z-N |
| Fixed-step / discrete models | configuration dependent | verify sample time, PID form, fixed filter and measured reference; horizon normalization alone is insufficient |
| Models without Scope blocks | ⚠️ small edit | add `To Workspace`, or export the signal |
| **Real hardware / HIL** | ❌ not supported | no Fast Restart; needs a different bridge |
| Non-PID controllers (LQR, MPC, gain scheduling) | 🔶 interface reusable | the head/decoder are separable from the controller adapter |

Legend: ✅ supported within the stated adapter scope · 🔶 requires additional work and validation ·
⚠️ needs a small code change · ❌ outside the current design.

The current MATLAB adapter accepts a finite positive step reference (numeric
`--ref-source` or configuration, or a resolved `auto` reference). It validates
controller conversion and logged signals before reporting success. Configuration
and runtime checks do not certify an arbitrary user model; the release's
[adapter evidence](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1) identifies the
generated fixtures actually tested.

---

## 3. How much work to adapt (honest estimate)

| you want to… | change | effort |
| :--- | :--- | :--- |
| point it at your Simulink model | run discovery/doctor; supply a configuration only for unresolved signals or controllers | depends on model setup |
| use a `PID Controller` block | one flag | minutes |
| add a plant family it has never seen | add a sampler in `plants.py`, regenerate the dataset, retrain | ~40 min CPU |
| investigate a specific out-of-distribution plant | compare the unchanged head with bounded classical search; specialist training is a separate optional study | measure actual experiment cost; no guaranteed repair time |
| change the objective (tracking, disturbance) | new metrics in `metrics.py` + a new state feature + retrain | half a day + ~1 h CPU |
| support a series/parallel conversion | one function (`set_gains` / an adapter) | an hour |
| support cascade or MIMO | redesign: one tuner per loop, plus a coordinator | weeks |
| run on hardware in the loop | a new bridge (no Fast Restart), plus safety limits on the real actuator | weeks |

---

## 4. Overall assessment

**Strong fit**: single-input single-output PID loops tuned from a step response,
where the plant is available as a Simulink model or a transfer function and the
cost of an experiment is acceptable. Evidence here covers the named Python
simulation families and explicitly reported MATLAB fixtures/models, not the
majority of industrial servo and process loops.

**Partial fit**: the same loops with a different objective (tracking,
disturbance) — the machinery is reusable, the *policy* is not, and it has to be
retrained and independently validated. The current specialist script retains
the step-response task; changing its plant alone does not implement a new objective.

**Weak fit**: cascade, MIMO, non-PID controllers, hardware in the loop. The
decision head is still usable as a component, but the surrounding bridge,
metrics and safety layer would have to be rebuilt.

**What is genuinely reusable even outside PID**: the `choice / score / noul`
contract, the expected-value decode with a variance trust region, the
"expert = search over the same action vocabulary" training recipe, and the
measured-best storage and deterministic rollback rule. Reusing these components
requires a domain-specific action adapter, metric, state and data validation.
Neither gain bounds nor a rollback proposal establish safe experiments.

The [practical budget study](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md) separates actual calls from
allowed budgets and preserves bad starts and failed trials. It does not enable
the paused joint-risk research policy or replace validation on a user's model.

---

# 适用范围：这个调参器能做什么、不能做什么

把它指向你的回路之前，只有两个问题：

1. **会不会把我的对象调炸？**
2. **哪些控制任务真的适合？**

下面两个都用测量回答，不用形容词。

## 1. 返回代价与搜索风险

| group | n | start J | returned J | improved % | worse % | rollbacks | final diverged | search diverged |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| zoo | 120 | 2.341 | 1.382 | 97.5 | 0.0 | 0 | 0 | 0 |
| heldout | 40 | 2.367 | 0.463 | 100.0 | 0.0 | 0 | 0 | 0 |
| outofzoo | 40 | 3.983 | 3.016 | 82.5 | 0.0 | 0 | 5 | 5 |

200株返回实测最优值，其worse_pct如上表；这是记账性质，不约束试验过程代价或证明稳定性。分布外搜索发散5株，最终发散5株，总回滚0次。门开关有40/40对在绝对容差1e-06下无实质差异。

参数限幅不证明稳定性，0.6×best回滚提案仍需测量。逐株预算20，原模型先复制再整定。证据见[`research/results/robustness.json`](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)，复现用`python scripts/11_robustness.py`。

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
| **跟踪 / 斜坡 / 正弦** | 🔶 新任务定义 | 新指标/特征、匹配的专家数据与独立验证；现有专家化命令不足以完成 |
| **扰动抑制** | 🔶 换指标 + 重训 | 注入扰动、改代价、专家化 |
| 大延迟（L/T ≈ 2） | 已评测，见GENERALIZATION | — |
| 测量噪声（σ ≈ 1%） | 已评测，见GENERALIZATION | — |
| **死区 / 回差** | 🔶 失效边界 | 专家化是实验，不保证修复，见[SPECIALIZE](SPECIALIZE.md) |
| **反向响应（右半平面零点）** | 🔶 失效边界 | 与同一真实预算下的传统搜索比较 |
| **开环不稳定对象** | ❌ 未解决 | 需要稳定的起点；专家化救不了荒谬的 Z-N |
| 定步长 / 离散模型 | 取决于配置 | 核实采样时间、PID形式、固定滤波与实测参考值；时间窗归一化本身不足以保证适配 |
| 没有 Scope 的模型 | ⚠️ 小改 | 加 `To Workspace`，或导出信号 |
| **真实硬件 / 半实物** | ❌ 不支持 | 没有 Fast Restart，需要另一套桥接 |
| 非 PID 控制器（LQR、MPC、增益调度） | 🔶 接口可复用 | 决策头/解码器与控制器适配层是分离的 |

图例：✅ 在所述适配边界内支持 · 🔶 需要额外工作与验证 · ⚠️ 需改代码 · ❌ 超出当前设计。

当前MATLAB适配器接受有限正阶跃参考值：数值`--ref-source`、配置，或已确定的`auto`。
报告成功前检查控制器转换与记录信号。配置和运行检查不证明任意用户模型都正确；本次发布的
[适配验证证据](https://github.com/lijiawei255/jev-tune/releases/tag/v0.10.1)列明实际测试的生成夹具。

## 3. 适配工作量（诚实估计）

| 你想… | 要改什么 | 工作量 |
| :--- | :--- | :--- |
| 指向自己的 Simulink 模型 | 运行发现器/doctor，仅对未确定的信号或控制器提供配置 | 取决于模型准备情况 |
| 用 `PID Controller` 块 | 一个开关 | 几分钟 |
| 加一个它没见过的对象族 | `plants.py` 加采样器，重生成数据集，重训 | 约 40 分钟 CPU |
| 检查某个分布外的具体对象 | 固定现有head，与有界传统搜索比较；专家化是另一个可选研究 | 实测实验成本，不保证修复耗时 |
| 换目标（跟踪、扰动抑制） | `metrics.py` 新指标 + 新状态特征 + 重训 | 半天 + 约 1 小时 CPU |
| 支持串联/并联转换 | 一个函数（`set_gains` / 适配器） | 一小时 |
| 支持串级或 MIMO | 重新设计：每环一个调参器 + 协调层 | 数周 |
| 上真实硬件在环 | 新桥接（没有 Fast Restart）+ 真实执行器限幅 | 数周 |

## 4. 总体评价

**很合适**：单入单出 PID、以阶跃响应为评价、对象能以 Simulink 模型或传递函数
给出、单次实验成本可以接受。现有证据仅覆盖所列Python仿真族与明确报告的MATLAB
夹具/模型，不能外推为大多数工业伺服或过程回路均适用。

**部分合适**：同样的回路但目标不同（跟踪、扰动抑制）——机制可复用，**策略不可
复用**，需重训并独立验证。当前专家化脚本仍保留阶跃任务，仅替换对象不等于实现新目标。

**不太合适**：串级、MIMO、非 PID 控制器、硬件在环。决策头仍可作为组件使用，但
外围的桥接、指标和安全层需要重建。

**即使不做 PID 也可以拿走的东西**：`choice / score / noul` 契约、带方差信赖域的
期望值解码、"专家 = 在同一动作词表上搜索"的训练配方、实测最优存储与确定性回滚规则。
复用仍需领域专用动作适配、指标、状态与数据验证；增益限幅和回滚提案都不保证试验安全。

[实用预算评测](https://github.com/lijiawei255/jev-tune/blob/v0.10.2-archive/docs/PRACTICAL_BUDGET.md)分别报告实际次数与预算上限，保留差初态和失败试验。
它不启用已暂停的联合风险研究策略，也不替代用户模型上的实际验证。

---

## If you already have an accurate model, use `pidtune`

This is the question every control engineer asks first, so it deserves a
straight answer.

`pidtune` is **model-based design**. You hand it an LTI model and a bandwidth or
phase-margin target; it solves the frequency-domain problem and returns gains.
Its design stage uses the supplied model; obtaining that model and validating
the controller can still require experiments. It balances response and stability
margins for that model, rather than minimizing this repository's particular
simulation cost. Inspect the returned stability/margin information and validate
the intended full-model response. An accurate model does not imply that its
default design must beat every search on every objective.
[MathWorks: pidtune](https://www.mathworks.com/help/control/ref/dynamicsystem.pidtune.html).

| | manual | `pidtune` | this project |
| :--- | :--- | :--- | :--- |
| needs a model | no | **yes, and it must be accurate** | no |
| experiments | task dependent | design needs no plant trial; identification/validation are additional | report all actual simulations |
| if the model is exact | depends on design | useful model-based baseline; not guaranteed best for this J | compare on the same objective |
| if the model is wrong | validate on the real model | validate on the real model | trials can diverge; returned measured-best retention is not a stability guarantee |
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

The historical benchmark includes **identify → `pidtune`**: one linear step
probe, a FOPDT fit, design and one closed-loop verification. Read its recorded
cost and budget together in [BENCHMARK](BENCHMARK.md); it is a different workflow
from supplying an accurate model. Earlier implementations could silently use
analytic Z-N when MATLAB/design failed. Future runs report those failures and
omit the method, and reject unsupported nonlinear/noisy probe physics. These
repairs do not retroactively validate a historical row or relabel it as a new run.
The motor-valve hand-tuned result is not a `pidtune` result.

**Practical choice.** With a suitable linear model, include `pidtune` as a
baseline and verify its controller on the full model. With an expensive or
nonlinear simulation, compare measured improvement per actual simulation against
a bounded classical search. Nonlinearity alone is not evidence that this head wins.

---

## 如果你已经有准确的模型，请直接用 `pidtune`

这是控制工程里最常被问的问题，值得正面回答。

`pidtune` 是**基于模型的设计**：你给它一个 LTI 模型和带宽/相位裕度目标，它在频域解
方程，返回增益。设计阶段使用已有模型，但获得模型与验证控制器仍可能需要实验。
它在该模型上平衡响应与稳定裕度，不直接最小化本仓库的特定仿真代价。应检查返回的
稳定性/裕度信息，再验证完整模型的目标响应；模型准确不等于默认设计在任意目标下必胜。
见[MathWorks：pidtune](https://www.mathworks.com/help/control/ref/dynamicsystem.pidtune.html)。

| | 人工 | `pidtune` | 本项目 |
| :--- | :--- | :--- | :--- |
| 需要模型 | 不需要 | **需要，而且必须准** | 不需要 |
| 实验次数 | 取决于任务 | 设计不需要对象试验，辨识/验证另计 | 报告全部实际仿真 |
| 模型准确时 | 取决于设计 | 有价值的模型基线，不保证该J最优 | 在同一目标下比较 |
| 模型不准时 | 在完整模型验证 | 在完整模型验证 | 试验仍可发散；保留实测最优不保证稳定性 |
| 优化对象 | 你的眼睛 | 带宽/相位裕度指标 | 你真实的代价函数 |

两个常被忽略的点：

1. **"建模型"才是贵的部分**：物理推导、系统辨识（`tfest`、`n4sid`），或者对 Simulink
   模型做工作点线性化（`linearize`）。模型的精度决定了最后的效果。
2. **`pidtune` 优化的是"指标"，不是"你的响应"**：它盯的是带宽和相位裕度。如果你真正
   要的是"不许超调、2 秒内稳定"，得自己把这句话翻译成指标（或者改用 `systune` 的时域
   约束），再反复手调。

历史基准包含**辨识 → `pidtune`**：一次线性阶跃探测、FOPDT拟合、设计，再做一次闭环验证。
其代价与预算应一起从[BENCHMARK](BENCHMARK.md)读取，它不等于直接提供准确模型。
旧实现可能在MATLAB不可用或设计失败时静默换成解析ZN；新运行将明确报告并省略失败方法，
同时拒绝线性探测器未实现的非线性/噪声条件。修复不追认旧行的有效性，也不把旧结果改称新运行。
电机阀门模型的人工整定结果不是`pidtune`结果。

**实际选择**：有合适线性模型时，将`pidtune`作为基线并回到完整模型验证。仿真昂贵或非线性时，
按实际仿真次数比较head与有界传统搜索的改善。存在非线性本身不证明head更好。

---

## A Simscape model still needs a suitable `pidtune` input

People reasonably assume that building the model is the hard part, and that once
it exists `pidtune` can use it. It depends which of three things you built:

| what you built | what it is | can `pidtune` use it directly? |
| :--- | :--- | :--- |
| a diagram of linear blocks (Gain, Transfer Fcn, Integrator, Sum) | potentially an LTI system | obtain the correct input/output model, preserving sample times and delays |
| a diagram with saturation, dead zone, friction, backlash, lookup tables | piecewise / nonlinear | derive or identify a local linear model, then validate outside the local approximation |
| a Simscape network (multibody, electrical, hydraulic, contact) | a physical simulation model | check that a suitable linearization and operating point exist; the network itself is not an LTI input to `pidtune` |

Local linearization represents behavior near its operating point. Switching,
contact transitions and saturation may make a single linear approximation
inadequate; they do not make every linearization meaningless.

**A useful validation.** Linearise your model at the operating
point, put the linear and the nonlinear model side by side, apply the same step,
and overlay the two responses at the intended amplitudes and operating points.
Agreement supports that particular use of the linear approximation; it is not
a global model certificate. Validate either controller against the full model.

This is where the trade-off sits, honestly:

* `pidtune` designs for a **linear surrogate**; model acquisition, toolbox
  requirements and nonlinear validation are separate costs;
* this project optimises the **nonlinear response you actually simulate**,
  because every "experiment" is a full run. It pays for that with experiments
  (each one costs a simulation, not an equation) and with a cost function that
  has to be defined.

The useful comparison is final controller quality and actual evaluation cost
under the same task. Neither accurate linear modeling nor extra nonlinear
detail establishes a universal winner.

Other model-based workflows can tune against multiple linearizations and stated
requirements. They still need full nonlinear validation; this repository has
not benchmarked them. See [MathWorks: tuning, analysis and validation](https://www.mathworks.com/help/control/tuning-1.html).


---

## Simscape 模型仍需转换为合适的 `pidtune` 输入

很多人会自然地认为：建模型是难的那一步，建好之后 `pidtune` 就能直接用。这取决于
你建的是下面三种里的哪一种：

| 你建的是什么 | 它是什么 | `pidtune` 能直接用吗 |
| :--- | :--- | :--- |
| 纯线性框图（Gain、Transfer Fcn、Integrator、Sum） | 可能是LTI系统 | 需获取正确输入输出模型，保留采样时间与延时 |
| 含饱和、死区、摩擦、齿隙、查表的框图 | 分段 / 非线性 | 推导或辨识局部线性模型，再验证局部近似以外的响应 |
| Simscape物理网络（多体、电气、液压、接触） | 物理仿真模型 | 先核实合适的线性化及工作点；网络本身不是`pidtune`的LTI输入 |

局部线性化描述所选工作点附近的行为。切换、接触转换与饱和可能使单一线性近似不足，
但不能据此认定所有线性化都没有意义。

**一个有用的验证**：把模型在工作点线性化，将线性与非线性模型在计划使用的幅度和工作点
施加同一阶跃并比较响应。一致只能支持该特定条件下的近似，不是全局模型证明；任一控制器
都应回到完整模型验证。

这个取舍要讲清楚：

* `pidtune`依据**线性代理模型**设计；建模、工具箱要求与非线性验证成本另计；
* 本项目优化的是**你真正仿出来的非线性响应**，因为每次"实验"就是跑一次完整模型。
  代价是要花实验次数（一次实验=一次仿真，不是一个方程），且要自己定义代价函数。

有意义的比较是在同一任务下的最终控制器质量与实际评估成本；准确线性模型或更多非线性
细节都不能单独证明哪种方法普遍更优。

其他模型方法可以针对多个线性化模型与明确需求整定，仍需要完整非线性验证；本仓库尚未
基准评测这些方法。见[MathWorks：整定、分析与验证](https://www.mathworks.com/help/control/tuning-1.html)。

---

## Replacing Simulink: the adapter boundary

The measurement interface is one component of a domain adaptation. Python's
discretized transfer-function simulator supplies the zoo, out-of-zoo and most
algorithm comparisons; the Simulink bridge supplies the explicitly named model
and fixture checks. Neither set of results validates the other environment.

A new bridge must return time, output and control input, while preserving action
mapping, objective normalization, state features, reset behavior and measured-call
accounting. It may change numerical behavior and controller quality. Record the
returned point and failed trials as well as actual simulation cost. Merely
retaining a best-so-far point is not an effectiveness or safety test. Hardware
and HIL remain outside the current scope and require a separate operating-safety
design and validation.

## 换掉 Simulink：适配器的边界在哪

Simulink是本项目测量接口的一种实现；迁移领域仍需要专用适配与验证：

```
有界动作（改增益） + 一次测量（跑一次，拿到 t, y, u） + 重复
```

本仓库随附两个适配器：

| 适配器 | 位置 | 验证程度 |
| :--- | :--- | :--- |
| Simulink（完整模型仿真） | `matlab/jev_tune_model.m` | 仅对应明确列出的MATLAB模型/夹具验证 |
| Python（离散化传递函数的批量仿真） | `jev-tune loop --num 1 --den "1 0.6 1"` | 仿真族、域外场景与多数算法对照数字来自此路径 |

要接第三种环境，需要实现测量接口，并核实动作映射、状态、指标、噪声、重置语义及适用边界：

```python
def measure(gains) -> tuple[t, y, u]:
    '''跑一次实验，返回时间、被测量、控制量。'''
```

然后照 `evaluate.evaluate_head` 的调用方式把它喂给同一个决策头。硬件事在环**不在**
本项目的设计范围内：它需要限幅、急停和故障注入，是另一个课题，`docs/GENERALIZATION.md`
里写了哪些场景会失效。

换适配器可能改变数值与方法性能，必须重新报告实际证据。README混合列出Python仿真与
明确标注的MATLAB结果，不能互相替代。新增适配器应检查实耗预算、返回最优的实测对应关系
以及试验过程失败；仅复现“不比起点差”不证明安全或有效。

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
